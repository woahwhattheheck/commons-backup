#!/usr/bin/env python3
"""Offline newsletter workshop: source-linked previews and unsent MIME drafts.

Standard library only. No network client, email delivery, or scheduler is used.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import re
import sys
import zipfile
from datetime import datetime
from email import policy
from email.message import EmailMessage
from email.utils import format_datetime, formataddr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
MAX_REQUEST = 2_000_000


class InputError(ValueError):
    """An actionable workspace input error."""


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value):
    raise InputError(f"Non-finite JSON value: {value}")


def load_json(raw: str | bytes) -> dict:
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise InputError(f"Invalid workspace JSON: {exc}") from exc


def _obj(value, label):
    if not isinstance(value, dict):
        raise InputError(f"{label} must be an object")
    return value


def _list(value, label):
    if not isinstance(value, list):
        raise InputError(f"{label} must be an array")
    return value


def _text(value, label, *, multiline=False, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise InputError(f"{label} must be {'a' if empty else 'a nonempty'} string")
    if any((ord(c) < 32 and not (multiline and c in '\n\t')) or ord(c) == 127 for c in value):
        raise InputError(f"{label} contains unsupported control characters")
    # Reject lone surrogates before rendering or encoding MIME content.
    try:
        value.encode('utf-8')
    except UnicodeError as exc:
        raise InputError(f"{label} must contain valid Unicode") from exc
    return value


def _slug(value, label):
    _text(value, label)
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', value):
        raise InputError(f"{label} must use lowercase words separated by hyphens")
    return value


def _email(value, label):
    _text(value, label)
    # Deliberately documented simple addr-spec subset; not a deliverability check.
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}", value):
        raise InputError(f"{label} must be a simple email address, without a display name")
    local, domain = value.rsplit('@', 1)
    if local.startswith('.') or local.endswith('.') or '..' in local or any(not part or part.startswith('-') or part.endswith('-') for part in domain.split('.')):
        raise InputError(f"{label} has an invalid email dot or domain label")
    return value


def _url(value, label):
    _text(value, label)
    try:
        parsed = urlsplit(value)
        valid = parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username and not parsed.password
        parsed.port  # Diagnose invalid/out-of-range port syntax.
    except ValueError as exc:
        raise InputError(f"{label} must be an HTTP(S) source URL") from exc
    if not valid or any(c.isspace() for c in value):
        raise InputError(f"{label} must be an HTTP(S) source URL without embedded credentials")
    return value


def _canonical(value):
    try:
        return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise InputError(f"Workspace must contain finite, UTF-8 JSON values: {exc}") from exc


def validate(workspace: dict) -> dict:
    """Validate the entire input before producing any output. Never fetch sources."""
    w = _obj(workspace, 'workspace')
    if type(w.get('schema_version')) is not int or w['schema_version'] != 1:
        raise InputError('schema_version must be the integer 1')
    pub = _obj(w.get('publication'), 'publication')
    for field in ('name', 'sender_name', 'signoff'):
        _text(pub.get(field), f'publication.{field}', multiline=field == 'signoff')
    for field in ('sender_email', 'reply_email'):
        _email(pub.get(field), f'publication.{field}')
    issue = _obj(w.get('issue'), 'issue')
    for field in ('slug', 'topic'):
        _slug(issue.get(field), f'issue.{field}')
    for field in ('subject', 'preheader', 'intro'):
        _text(issue.get(field), f'issue.{field}', multiline=field == 'intro')
    raw_time = _text(issue.get('planned_at'), 'issue.planned_at')
    try:
        when = datetime.fromisoformat(raw_time.replace('Z', '+00:00'))
        if when.tzinfo is None or when.utcoffset() is None:
            raise ValueError('include a timezone offset')
        format_datetime(when)
    except (ValueError, OverflowError) as exc:
        raise InputError(f'issue.planned_at must be a timezone-aware ISO datetime: {exc}') from exc
    sources = {}
    for index, raw in enumerate(_list(w.get('sources'), 'sources')):
        source = _obj(raw, f'sources[{index}]')
        source_id = _slug(source.get('id'), f'sources[{index}].id')
        if source_id in sources:
            raise InputError(f'Duplicate source id: {source_id}')
        _text(source.get('title'), f'source {source_id}.title')
        _text(source.get('text'), f'source {source_id}.text', multiline=True)
        _url(source.get('url'), f'source {source_id}.url')
        sources[source_id] = source
    sections = _list(issue.get('sections'), 'issue.sections')
    if not sections:
        raise InputError('issue.sections must contain at least one section')
    for index, raw in enumerate(sections):
        section = _obj(raw, f'issue.sections[{index}]')
        _text(section.get('heading'), f'section {index + 1}.heading')
        source_id = _slug(section.get('source_id'), f'section {index + 1}.source_id')
        if source_id not in sources:
            raise InputError(f'section {index + 1} references unknown source {source_id}')
        quote = _text(section.get('quote'), f'section {index + 1}.quote', multiline=True)
        if quote not in sources[source_id]['text']:
            raise InputError(f'section {index + 1} quote is not an exact excerpt of source {source_id}')
        _text(section.get('commentary'), f'section {index + 1}.commentary', multiline=True, empty=True)
    seen = set()
    eligible = []
    excluded = []
    for index, raw in enumerate(_list(w.get('subscribers'), 'subscribers')):
        subscriber = _obj(raw, f'subscribers[{index}]')
        email = _email(subscriber.get('email'), f'subscribers[{index}].email')
        key = email.casefold()
        if key in seen:
            raise InputError(f'Duplicate subscriber email: {email}; consolidate preferences before building')
        seen.add(key)
        _text(subscriber.get('name'), f'subscribers[{index}].name')
        status = subscriber.get('status')
        if not isinstance(status, str) or status not in ('subscribed', 'unsubscribed', 'paused'):
            raise InputError(f'subscribers[{index}].status must be subscribed, unsubscribed, or paused')
        topics = _list(subscriber.get('topics'), f'subscribers[{index}].topics')
        for topic in topics:
            _slug(topic, f'subscribers[{index}].topics item')
        reason = status if status != 'subscribed' else ('topic_not_selected' if issue['topic'] not in topics else '')
        if reason:
            excluded.append({'email': email, 'reason': reason})
        else:
            eligible.append(subscriber)
    _canonical(w)  # Reject exponent overflow or unserializable values, including extra fields.
    return {'when': when, 'sources': sources, 'eligible': eligible, 'excluded': excluded}


def render(workspace: dict, checked: dict | None = None) -> tuple[str, str]:
    checked = checked or validate(workspace)
    pub, issue = workspace['publication'], workspace['issue']
    esc = html.escape
    paragraphs = lambda s: '<p>' + esc(s).replace('\n', '<br>') + '</p>'
    blocks = []
    text = [pub['name'], issue['subject'], issue['planned_at'], '', issue['intro'], '']
    for number, section in enumerate(issue['sections'], 1):
        source = checked['sources'][section['source_id']]
        blocks.append(f'<section><h2>{esc(section["heading"])}</h2><blockquote>{esc(section["quote"])}</blockquote>{paragraphs(section["commentary"])}<p class="source">Source [{number}]: <a href="{esc(source["url"], quote=True)}">{esc(source["title"])}</a></p></section>')
        text.extend([section['heading'], f'"{section["quote"]}"', section['commentary'], f'Source [{number}]: {source["title"]} — {source["url"]}', ''])
    text.extend([pub['signoff'], '', f'To change preferences or unsubscribe, reply to {pub["reply_email"]}.'])
    document = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(issue['subject'])}</title><style>
body{{margin:0;background:#f1f5f4;color:#182923;font:17px/1.65 system-ui,sans-serif}}main{{max-width:700px;margin:32px auto;background:white;padding:40px;border-top:7px solid #306954}}h1{{line-height:1.15}}h2{{line-height:1.3}}.eyebrow,.source,footer{{font-size:14px;color:#40584b}}blockquote{{margin:12px 0;padding:12px 20px;border-left:3px solid #306954;background:#f1f5f4;white-space:pre-wrap}}a{{color:#245841;overflow-wrap:anywhere}}section{{margin:32px 0}}@media(max-width:600px){{main{{margin:0;padding:24px}}}}
</style></head><body><main><header><p class="eyebrow">{esc(pub['name'])} · {esc(issue['planned_at'])}</p><h1>{esc(issue['subject'])}</h1><p>{esc(issue['preheader'])}</p></header>{paragraphs(issue['intro'])}{''.join(blocks)}{paragraphs(pub['signoff'])}<footer>To change preferences or unsubscribe, reply to <a href="mailto:{esc(pub['reply_email'], quote=True)}">{esc(pub['reply_email'])}</a>.</footer></main></body></html>'''
    return document, '\n'.join(text) + '\n'


def build_files(workspace: dict) -> dict[str, bytes]:
    checked = validate(workspace)
    document, plain = render(workspace, checked)
    saved = _canonical(workspace)
    digest = hashlib.sha256(saved).hexdigest()
    issue, pub = workspace['issue'], workspace['publication']
    files = {'preview.html': document.encode(), 'newsletter.txt': plain.encode(), 'workspace.json': saved}
    plan = io.StringIO(newline='')
    writer = csv.writer(plan, lineterminator='\n')
    csv_address = lambda value: ("'" + value) if value[:1] in '=+-@' else value
    writer.writerow(['email', 'planned_at', 'state', 'reason', 'draft_path'])
    for subscriber in checked['eligible']:
        address_id = hashlib.sha256(subscriber['email'].casefold().encode()).hexdigest()[:24]
        path = f'drafts/{address_id}.eml'
        message = EmailMessage(policy=policy.SMTP)
        message['From'] = formataddr((pub['sender_name'], pub['sender_email']))
        message['To'] = formataddr((subscriber['name'], subscriber['email']))
        message['Reply-To'] = pub['reply_email']
        message['Subject'] = issue['subject']
        message['Date'] = format_datetime(checked['when'])
        message['Message-ID'] = f'<{digest[:24]}.{address_id}@newsletter-workshop.invalid>'
        message['X-Unsent'] = '1'
        message['X-Newsletter-State'] = 'prepared-not-sent'
        message['List-Unsubscribe'] = f'<mailto:{pub["reply_email"]}?subject=unsubscribe>'
        message.set_content(plain)
        message.add_alternative(document, subtype='html')
        message.set_boundary(f'newsletter-{digest[:24]}-{address_id}')
        files[path] = message.as_bytes()
        writer.writerow([csv_address(subscriber['email']), issue['planned_at'], 'PREPARED_NOT_SENT', '', path])
    for item in checked['excluded']:
        writer.writerow([csv_address(item['email']), issue['planned_at'], 'EXCLUDED', item['reason'], ''])
    files['delivery-plan.csv'] = plan.getvalue().encode('utf-8')
    source_map = {'workspace_sha256': digest, 'check': 'exact excerpt in supplied source text; not independent fact verification', 'sections': []}
    for number, section in enumerate(issue['sections'], 1):
        source = checked['sources'][section['source_id']]
        source_map['sections'].append({'section': number, 'source_id': source['id'], 'title': source['title'], 'url': source['url'], 'quote': section['quote'], 'source_text_sha256': hashlib.sha256(source['text'].encode()).hexdigest()})
    files['source-map.json'] = _canonical(source_map)
    files['START-HERE.txt'] = ("NEWSLETTER WORKSPACE EXPORT\n\nOpen preview.html for the issue; newsletter.txt is the plain-text edition.\nEdit workspace.json and rebuild using the workshop compiler.\nThe drafts/ files are UNSENT email messages. No delivery or scheduling occurred.\nThe delivery plan excludes paused, unsubscribed, and unselected-topic records.\nOld exports do not change when preferences change; rebuild before any delivery.\nReview source truth, commentary, recipients, and your email platform's current\npreferences independently before using its normal authorized delivery workflow.\nThis export contains recipient information. Keep real customer exports private.\n").encode()
    files['manifest.json'] = _canonical({'schema_version': 1, 'state': 'PREPARED_NOT_SENT', 'issue': issue['slug'], 'workspace_sha256': digest, 'eligible': len(checked['eligible']), 'excluded': checked['excluded'], 'files': {name: {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)} for name, data in sorted(files.items())}})
    return files


def build_zip(workspace: dict) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(build_files(workspace).items()):
            entry = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    return out.getvalue()


def write_new(path: Path, content: bytes):
    """Preserve every existing file; completed content is prepared before this call."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(content)


def handler_class():
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, data, content_type, filename=None):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            if filename:
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            route = urlsplit(self.path).path
            if route == '/':
                self.reply(200, (HERE / 'workshop.html').read_bytes(), 'text/html; charset=utf-8')
            elif route == '/example.json':
                self.reply(200, (HERE / 'example.json').read_bytes(), 'application/json; charset=utf-8')
            else:
                self.reply(404, b'Not found\n', 'text/plain; charset=utf-8')

        def do_POST(self):
            route = urlsplit(self.path).path
            if route not in ('/build', '/validate'):
                return self.reply(404, b'Not found\n', 'text/plain; charset=utf-8')
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_REQUEST:
                    raise InputError('Workspace body must be between 1 byte and 2 MB')
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise InputError('Incomplete workspace body')
                workspace = load_json(raw)
                if route == '/validate':
                    validate(workspace)
                    return self.reply(200, _canonical(workspace), 'application/json; charset=utf-8')
                data = build_zip(workspace)
                self.reply(200, data, 'application/zip', f'{workspace["issue"]["slug"]}.zip')
            except (InputError, ValueError) as exc:
                self.reply(400, _canonical({'error': str(exc)}), 'application/json; charset=utf-8')

        def log_message(self, fmt, *args):
            pass  # Do not put recipient details into a request log.
    return Handler


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init', help='Copy the original fictional starter workspace')
    init.add_argument('path', type=Path)
    check = commands.add_parser('validate', help='Validate without writing outputs')
    check.add_argument('path', type=Path)
    build = commands.add_parser('build', help='Write a new ZIP with previews and unsent drafts')
    build.add_argument('path', type=Path)
    build.add_argument('--out', required=True, type=Path)
    serve = commands.add_parser('serve', help='Run the browser workshop on this machine')
    serve.add_argument('--host', default='127.0.0.1')
    serve.add_argument('--port', type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        if args.command == 'init':
            write_new(args.path, (HERE / 'example.json').read_bytes())
            print(f'Created editable workspace: {args.path}')
        elif args.command in ('validate', 'build'):
            workspace = load_json(args.path.read_bytes())
            checked = validate(workspace)
            if args.command == 'build':
                data = build_zip(workspace)
                write_new(args.out, data)
                print(f'Created {args.out} ({len(data)} bytes); no messages sent or scheduled.')
            print(f'{len(checked["eligible"])} eligible unsent drafts; {len(checked["excluded"])} excluded.')
        else:
            with ThreadingHTTPServer((args.host, args.port), handler_class()) as server:
                print(f'Newsletter workshop: http://{args.host}:{server.server_port}/', flush=True)
                server.serve_forever()
    except (InputError, OSError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
