#!/usr/bin/env python3
"""Fourfold: persistent, source-linked newsletter production. Standard library only."""
import argparse
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import hashlib
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit, parse_qs
import uuid
import zipfile

ROOT = Path(__file__).resolve().parent
STATES = ('draft', 'ready', 'scheduled_externally', 'sent_externally')


class Problem(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def text(value, name, maximum=20000, empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise Problem(f'{name}: supply {"text" if empty else "non-empty text"} up to {maximum} characters')
    if any((ord(c) < 32 and c not in '\n\r\t') or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise Problem(f'{name}: unsupported control character')
    return value.strip()


def brand_data(value):
    if not isinstance(value, dict):
        raise Problem('brand: supply an object')
    result = {k: text(value.get(k, ''), f'brand.{k}', 4000, empty=k != 'name')
              for k in ('name', 'voice', 'footer', 'cta_text', 'cta_url')}
    if result['cta_url']:
        try:
            url = urlsplit(result['cta_url'])
        except ValueError as exc:
            raise Problem('brand.cta_url: invalid HTTP(S) address') from exc
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
            raise Problem('brand.cta_url: use a complete HTTP(S) address without credentials')
    return result


def day(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise Problem('send_date: use YYYY-MM-DD')
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise Problem('send_date: invalid calendar date') from exc


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def make_pack(raw):
    if not isinstance(raw, dict):
        raise Problem('intake: supply a JSON object')
    segments = raw.get('segments')
    if not isinstance(segments, list) or not 4 <= len(segments) <= 80:
        raise Problem('segments: supply 4–80 interview sections for four distinct issues')
    source = []
    for index, item in enumerate(segments):
        if not isinstance(item, dict):
            raise Problem('each interview section must be an object')
        source.append({'id': f'S{index + 1:03}', 'heading': text(item.get('heading'), 'heading', 200),
                       'text': text(item.get('text'), 'interview text'),
                       'notes': text(item.get('notes', ''), 'research notes', empty=True)})
    first = day(raw.get('first_send'))
    issues = []
    for index in range(4):
        selected = source[len(source)*index//4:len(source)*(index+1)//4]
        try:
            scheduled = (first + timedelta(days=index*7)).isoformat()
        except OverflowError as exc:
            raise Problem('first_send: four weekly dates exceed the supported calendar') from exc
        issues.append({'id': f'issue-{index+1}', 'subject': selected[0]['heading'],
                       'preheader': ' / '.join(s['heading'] for s in selected)[:300],
                       'intro': f"This week: {selected[0]['heading']}.",
                       'body': '\n\n'.join(s['text'] for s in selected),
                       'closing': '', 'notes': '', 'source_ids': [s['id'] for s in selected],
                       'send_date': scheduled, 'status': 'draft', 'delivery_reference': ''})
    return {'id': uuid.uuid4().hex, 'version': 1, 'created_at': stamp(), 'updated_at': stamp(),
            'client': text(raw.get('client'), 'client', 200), 'brand': brand_data(raw.get('brand')),
            'source_title': text(raw.get('source_title'), 'source_title', 300),
            'source_credit': text(raw.get('source_credit', ''), 'source_credit', 300, empty=True),
            'segments': source, 'issues': issues}


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''CREATE TABLE IF NOT EXISTS packs(id TEXT PRIMARY KEY, version INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS revisions(pack_id TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(pack_id,version), FOREIGN KEY(pack_id) REFERENCES packs(id) ON DELETE CASCADE);''')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, key):
        with self.connection() as db:
            row = db.execute('SELECT payload FROM packs WHERE id=?', (key,)).fetchone()
            if not row:
                raise Problem('Newsletter pack not found', 404)
            return json.loads(row[0])

    def list(self):
        with self.connection() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT payload FROM packs ORDER BY rowid DESC')]

    @staticmethod
    def save(db, pack):
        payload = json.dumps(pack, ensure_ascii=False, allow_nan=False)
        db.execute('INSERT INTO packs VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,payload=excluded.payload',
                   (pack['id'], pack['version'], payload))
        db.execute('INSERT INTO revisions VALUES(?,?,?)', (pack['id'], pack['version'], payload))

    def create(self, raw):
        pack = make_pack(raw)
        with self.connection() as db:
            self.save(db, pack)
        return pack

    def history(self, key):
        self.get(key)
        with self.connection() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT payload FROM revisions WHERE pack_id=? ORDER BY version', (key,))]

    def update(self, key, raw):
        if not isinstance(raw, dict) or type(raw.get('version')) is not int:
            raise Problem('version: supply the integer revision you opened')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT payload FROM packs WHERE id=?', (key,)).fetchone()
            if not row:
                raise Problem('Newsletter pack not found', 404)
            pack = json.loads(row[0])
            if pack['version'] != raw['version']:
                raise Problem('A newer revision exists. Reopen it before saving your edits.', 409)
            if 'brand' in raw:
                pack['brand'] = brand_data(raw['brand'])
                for issue in pack['issues']:
                    issue['status'], issue['delivery_reference'] = 'draft', ''
            else:
                issue = next((i for i in pack['issues'] if i['id'] == raw.get('issue_id')), None)
                changes = raw.get('changes')
                if issue is None or not isinstance(changes, dict) or not changes:
                    raise Problem('Supply an existing issue_id and non-empty changes object')
                fields = {'subject': 300, 'preheader': 300, 'intro': 10000, 'body': 400000,
                          'closing': 10000, 'notes': 20000, 'delivery_reference': 2000}
                for field, value in changes.items():
                    if field in fields:
                        issue[field] = text(value, field, fields[field], empty=field not in ('subject', 'body'))
                    elif field == 'send_date':
                        issue[field] = day(value).isoformat()
                    elif field == 'status':
                        if not isinstance(value, str) or value not in STATES:
                            raise Problem('status: choose draft, ready, scheduled_externally, or sent_externally')
                        issue[field] = value
                    else:
                        raise Problem(f'Unknown issue field: {field}')
                editorial = {'subject', 'preheader', 'intro', 'body', 'closing', 'send_date'}
                if editorial.intersection(changes):
                    issue['status'], issue['delivery_reference'] = 'draft', ''
                if issue['status'].endswith('_externally') and not issue['delivery_reference']:
                    raise Problem('Add the existing provider job/message reference when recording external delivery')
            pack['version'] += 1
            pack['updated_at'] = stamp()
            self.save(db, pack)
        return pack

    def delete(self, key, version):
        if type(version) is not int:
            raise Problem('version: supply an integer')
        with self.connection() as db:
            result = db.execute('DELETE FROM packs WHERE id=? AND version=?', (key, version))
            if not result.rowcount:
                raise Problem('Pack missing or revision changed; reopen before deleting', 409)


def source_excerpt(pack, issue):
    return '\n\n'.join(s['text'] for s in pack['segments'] if s['id'] in issue['source_ids'])


def render(pack, issue):
    """Email-compatible escaped HTML, and plain text. No provider sends."""
    brand = pack['brand']
    paragraphs = [issue['intro'], issue['body'], issue['closing']]
    body = ''.join('<p>' + html.escape(p).replace('\n', '<br>') + '</p>'
                   for block in paragraphs for p in block.split('\n\n') if p)
    cta = ''
    if brand['cta_url'] and brand['cta_text']:
        cta = f'<p><a href="{html.escape(brand["cta_url"], quote=True)}">{html.escape(brand["cta_text"])}</a></p>'
    page = ('<!doctype html><html lang="en"><meta charset="utf-8"><title>' + html.escape(issue['subject']) +
            '</title><body style="font-family:Arial,sans-serif;max-width:640px;margin:32px auto;padding:20px;line-height:1.6">' +
            '<div style="display:none;max-height:0;overflow:hidden">' + html.escape(issue['preheader']) + '</div>' +
            '<p>' + html.escape(brand['name']) + '</p><h1>' + html.escape(issue['subject']) + '</h1>' + body + cta +
            '<hr><p>' + html.escape(brand['footer']).replace('\n', '<br>') + '</p></body></html>')
    plain = '\n\n'.join(p for p in [brand['name'], issue['subject'], *paragraphs,
                                   (brand['cta_text'] + ' ' + brand['cta_url']).strip(), brand['footer']] if p)
    return page, plain + '\n'


def calendar(pack):
    def escape(value):
        return value.replace('\\', '\\\\').replace('\r\n', '\n').replace('\r', '\n').replace('\n', '\\n').replace(';', '\\;').replace(',', '\\,')
    def fold(value):
        lines, line = [], ''
        for char in value:
            if len((line + char).encode('utf-8')) > 75:
                lines.append(line)
                line = ' '
            line += char
        return '\r\n'.join([*lines, line])
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Commons//Fourfold//EN', 'CALSCALE:GREGORIAN']
    created = datetime.fromisoformat(pack['created_at']).strftime('%Y%m%dT%H%M%SZ')
    for issue in pack['issues']:
        lines += ['BEGIN:VEVENT', f'UID:{pack["id"]}-{issue["id"]}@fourfold.local', f'DTSTAMP:{created}',
                  'DTSTART;VALUE=DATE:' + issue['send_date'].replace('-', ''),
                  f'SEQUENCE:{pack["version"]}', 'SUMMARY:' + escape('Newsletter handoff: ' + issue['subject']),
                  'DESCRIPTION:' + escape('Planning item only; no email is scheduled by Fourfold. State: ' + issue['status']),
                  'END:VEVENT']
    return '\r\n'.join(fold(line) for line in [*lines, 'END:VCALENDAR']) + '\r\n'


def bundle(pack):
    files = {'pack.json': json.dumps(pack, ensure_ascii=False, indent=2), 'calendar.ics': calendar(pack),
             'brand.json': json.dumps(pack['brand'], ensure_ascii=False, indent=2),
             'source-interview.json': json.dumps({'title': pack['source_title'], 'credit': pack['source_credit'],
                                                'segments': pack['segments']}, ensure_ascii=False, indent=2)}
    for issue in pack['issues']:
        page, plain = render(pack, issue)
        files[issue['id'] + '.html'], files[issue['id'] + '.txt'] = page, plain
    files['HANDOFF.txt'] = ('FOURFOLD — EDITABLE NEWSLETTER HANDOFF\nNo messages have been sent by this app.\n'
        'Import each HTML/text draft into the client\'s existing email platform. Configure its existing sender, audience, '
        'preference/unsubscribe merge fields and time zone there; preview/test there before scheduling.\n'
        'Calendar dates are planning dates, not provider jobs. External states are operator-entered references, '
        'not provider verification. Review editorial text against source-interview.json; unchanged excerpts '
        'are only as accurate as the supplied interview. All four issues and the complete revision are in pack.json.\n')
    encoded = {name: value.encode('utf-8') for name, value in files.items()}
    manifest = {'pack_id': pack['id'], 'version': pack['version'], 'email_sent_by_app': False,
                'files': {name: hashlib.sha256(data).hexdigest() for name, data in encoded.items()},
                'issues': [{'id': i['id'], 'source_ids': i['source_ids'],
                            'body_matches_supplied_excerpts': i['body'] == source_excerpt(pack, i)} for i in pack['issues']]}
    encoded['manifest.json'] = json.dumps(manifest, indent=2).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(encoded.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return output.getvalue()


def handler(store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, data, kind='application/json; charset=utf-8', attachment=None):
            payload = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            if attachment:
                self.send_header('Content-Disposition', f'attachment; filename="{attachment}"')
            self.end_headers()
            self.wfile.write(payload)

        def read_json(self):
            try:
                size = int(self.headers.get('Content-Length', '0'))
            except ValueError as exc:
                raise Problem('Invalid Content-Length') from exc
            if not 1 <= size <= 2_000_000:
                raise Problem('Supply a JSON body of 1–2,000,000 bytes', 413)
            try:
                return json.loads(self.rfile.read(size).decode('utf-8'))
            except (ValueError, UnicodeError) as exc:
                raise Problem('Malformed UTF-8 JSON') from exc

        def do_GET(self):
            self.route('GET')

        def do_POST(self):
            self.route('POST')

        def do_PATCH(self):
            self.route('PATCH')

        def do_DELETE(self):
            self.route('DELETE')

        def route(self, method):
            try:
                parsed = urlsplit(self.path)
                path = parsed.path
                if method == 'GET' and path in ('/', '/demo.json'):
                    target = ROOT / ('index.html' if path == '/' else 'demo.json')
                    return self.reply(200, target.read_bytes(), 'text/html; charset=utf-8' if path == '/' else 'application/json; charset=utf-8')
                if path == '/api/packs':
                    if method == 'GET':
                        return self.reply(200, store.list())
                    if method == 'POST':
                        return self.reply(201, store.create(self.read_json()))
                match = re.fullmatch(r'/api/packs/([a-f0-9]{32})(?:/(history|export|preview))?', path)
                if not match:
                    raise Problem('Not found', 404)
                key, action = match.groups()
                if method == 'GET':
                    pack = store.get(key)
                    if action in ('export', 'preview'):
                        query = parse_qs(parsed.query, keep_blank_values=True)
                        if 'version' in query:
                            versions = query['version']
                            if len(versions) != 1 or not re.fullmatch(r'[1-9][0-9]*', versions[0]):
                                raise Problem('version: supply one positive integer revision')
                            if versions[0] != str(pack['version']):
                                raise Problem('A newer revision exists. Reopen it before previewing or exporting.', 409)
                    if action == 'history':
                        return self.reply(200, store.history(key))
                    if action == 'export':
                        return self.reply(200, bundle(pack), 'application/zip', f'newsletter-{key}-v{pack["version"]}.zip')
                    if action == 'preview':
                        issue_id = parse_qs(parsed.query).get('issue', [''])[0]
                        issue = next((i for i in pack['issues'] if i['id'] == issue_id), None)
                        if issue is None:
                            raise Problem('Issue not found', 404)
                        return self.reply(200, render(pack, issue)[0].encode('utf-8'), 'text/html; charset=utf-8')
                    return self.reply(200, pack)
                if action is None and method == 'PATCH':
                    return self.reply(200, store.update(key, self.read_json()))
                if action is None and method == 'DELETE':
                    raw = self.read_json()
                    store.delete(key, raw.get('version') if isinstance(raw, dict) else None)
                    return self.reply(200, {'deleted': key})
                raise Problem('Method not supported for this route', 405)
            except Problem as exc:
                self.reply(exc.status, {'error': str(exc)})
            except sqlite3.Error:
                self.reply(503, {'error': 'Database operation unavailable; no successful save is being reported'})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='newsletter.sqlite3')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), handler(Store(args.db)))
    print(f'Fourfold ready at http://{args.host}:{server.server_port}; data: {args.db}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
