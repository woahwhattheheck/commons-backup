#!/usr/bin/env python3
"""Editable newsletter email exports. No network calls, sending or scheduling."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from email.message import EmailMessage
from email.policy import SMTP
import hashlib
import html
import io
import json
import os
from pathlib import Path
import tempfile
from typing import Any
import zipfile

MAX_ISSUES = 52
MAX_BODY = 1_000_000


class HandoffError(ValueError):
    """An input cannot be represented faithfully in an email handoff."""


def _text(value: Any, label: str, limit: int, *, empty: bool = False,
          single_line: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise HandoffError(f'{label} must be text with {0 if empty else 1}–{limit} characters.')
    if any((ord(c) < 32 and c not in '\n\r\t') or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise HandoffError(f'{label} contains unsupported control characters or Unicode surrogates.')
    if single_line and any(c in value for c in '\n\r'):
        raise HandoffError(f'{label} must be a single line.')
    return value


def _json(value: Any) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                           allow_nan=False) + '\n').encode('utf-8')
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise HandoffError('Metadata must be finite, UTF-8-compatible JSON.') from exc


def _schedule(value: Any) -> str:
    if value in (None, ''):
        return ''
    value = _text(value, 'scheduled_at', 64, single_line=True)
    try:
        when = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if when.tzinfo is None or when.utcoffset() is None:
            raise ValueError('Timezone required')
        return when.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    except (ValueError, OverflowError) as exc:
        raise HandoffError('scheduled_at must be an ISO timestamp with an explicit timezone.') from exc


def _issue(value: Any, index: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HandoffError(f'Issue {index} must be an object.')
    references = value.get('source_refs', [])
    if not isinstance(references, list) or len(references) > 5000:
        raise HandoffError('source_refs must be a list of at most 5000 passage references.')
    return {
        'id': _text(value.get('id'), 'Issue id', 200, single_line=True),
        'subject': _text(value.get('subject'), 'Subject', 200, single_line=True),
        'body': _text(value.get('body'), 'Body', MAX_BODY),
        'preheader': _text(value.get('preheader', ''), 'Preheader', 500, empty=True, single_line=True),
        'scheduled_at': _schedule(value.get('scheduled_at')),
        'source_refs': [_text(ref, 'Source reference', 2000, single_line=True) for ref in references],
    }


def render_issue_html(issue: dict[str, Any], *, publication: str) -> str:
    """Render literal editorial text, not executable HTML or interpreted Markdown."""
    issue = _issue(issue, 1)
    publication = _text(publication, 'Publication', 200, single_line=True)
    escape = html.escape
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>' + escape(issue['subject']) + '</title></head>'
            '<body style="margin:0;background:#f3f6f4;color:#19372e;font:17px/1.65 Arial,sans-serif">'
            '<div style="display:none;max-height:0;overflow:hidden">' + escape(issue['preheader']) + '</div>'
            '<main style="max-width:640px;overflow-wrap:anywhere;margin:24px auto;padding:32px;background:white;border-top:6px solid #23715a">'
            '<header style="font-size:13px;letter-spacing:1px">' + escape(publication) + '</header>'
            '<h1 style="font-size:30px;line-height:1.2">' + escape(issue['subject']) + '</h1>'
            '<div style="white-space:pre-wrap;overflow-wrap:anywhere">' + escape(issue['body']) + '</div>'
            '<footer style="font-size:12px;border-top:1px solid #ddd;margin-top:24px;padding-top:12px">'
            'Unsent editorial preview. Configure the client’s sender and preference footer in their existing email platform before delivery.'
            '</footer></main></body></html>\n')


def _email(issue: dict[str, Any], rendered: str) -> bytes:
    mail = EmailMessage(policy=SMTP)
    mail['Subject'] = issue['subject']
    mail['X-Unsent'] = '1'
    # Deliberately omit From, To, Date and Message-ID: this is an editable draft.
    mail.set_content(issue['body'])
    mail.add_alternative(rendered, subtype='html')
    digest = hashlib.sha256(_json(issue) + rendered.encode('utf-8')).hexdigest()
    # RFC 2046 section 5.1.1 caps boundaries at 70 characters. Each candidate
    # below is 63 ASCII characters; collision retries never lengthen it.
    for attempt in range(1000):
        boundary = f'newsletter-handoff-{digest[:40]}-{attempt:03d}'
        if boundary not in issue['body'] and boundary not in rendered:
            mail.set_boundary(boundary)
            return mail.as_bytes()
    raise HandoffError('Unable to choose a MIME boundary absent from the draft content.')


def _csv_cell(value: str) -> str:
    if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
        return "'" + value
    return value


def build_email_bundle(issues: list[dict[str, Any]], *, publication: str,
                       source_metadata: dict[str, Any] | None = None) -> bytes:
    """Return a deterministic ZIP of text, HTML, unsent .eml, CSV and JSON.

    Each issue supplies id, subject, body; preheader, scheduled_at and source_refs
    are optional. scheduled_at is intended delivery time, never a provider receipt.
    Source metadata is copied as JSON; no metadata claim is independently verified.
    """
    publication = _text(publication, 'Publication', 200, single_line=True)
    if not isinstance(issues, list) or not 1 <= len(issues) <= MAX_ISSUES:
        raise HandoffError(f'issues must be a list of 1–{MAX_ISSUES} issues.')
    if source_metadata is not None and not isinstance(source_metadata, dict):
        raise HandoffError('source_metadata must be an object or None.')
    source_bytes = _json(source_metadata if source_metadata is not None else {})
    if len(source_bytes) > 1_000_000:
        raise HandoffError('source_metadata exceeds one million encoded bytes.')
    clean = [_issue(issue, i) for i, issue in enumerate(issues, 1)]
    identifiers = [issue['id'] for issue in clean]
    if len(set(identifiers)) != len(identifiers):
        raise HandoffError('Issue ids must be unique.')
    files: dict[str, bytes] = {'source-metadata.json': source_bytes}
    manifest: dict[str, Any] = {'schema_version': 1, 'publication': publication,
                              'delivery_state': 'UNSENT_EXPORT', 'scheduling_state': 'NOT_SCHEDULED',
                              'source_metadata_file': 'source-metadata.json', 'issues': []}
    csv_buffer = io.StringIO(newline='')
    writer = csv.writer(csv_buffer)
    writer.writerow(['issue_id', 'subject', 'intended_send_at_utc', 'text_file', 'html_file', 'eml_file', 'delivery_state'])
    for index, issue in enumerate(clean, 1):
        stem = f'issues/{index:02d}'  # Never derive archive paths from caller filenames/ids.
        rendered = render_issue_html(issue, publication=publication)
        payloads = {stem + '.txt': issue['body'].encode('utf-8'),
                    stem + '.html': rendered.encode('utf-8'), stem + '.eml': _email(issue, rendered)}
        files.update(payloads)
        entry = dict(issue, files={ext: stem + '.' + ext for ext in ('txt', 'html', 'eml')},
                     sha256={name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()})
        # Body remains in the editable .txt, avoiding a duplicate large manifest copy.
        del entry['body']
        manifest['issues'].append(entry)
        writer.writerow([_csv_cell(issue['id']), _csv_cell(issue['subject']), issue['scheduled_at'],
                         stem + '.txt', stem + '.html', stem + '.eml', 'UNSENT_EXPORT'])
    files['campaign-import.csv'] = csv_buffer.getvalue().encode('utf-8-sig')
    files['manifest.json'] = _json(manifest)
    files['README.txt'] = (
        'NEWSLETTER EMAIL HANDOFF — UNSENT\n\n'
        'Each numbered issue has original editable UTF-8 text, escaped HTML preview, and a multipart .eml draft.\n'
        'The text file preserves exact input bytes after UTF-8 encoding. Email serialization normalizes line endings and adds a final newline.\n'
        'X-Unsent is a draft hint, not a universal mail-client control. No sender, recipient, Date or Message-ID is invented.\n'
        'The CSV is a neutral handoff, not a guaranteed provider import schema. Map columns using the client’s existing platform.\n'
        'Intended-send timestamps are normalized to UTC. No campaign is scheduled; no email is sent.\n'
        'Configure the actual sender, recipients, preferences/unsubscribe footer and delivery in the chosen platform.\n'
        'Review quotes, rights, source references and source-metadata.json before use. Supplied metadata is not independent verification.\n'
        'CSV leading formula characters are prefixed with an apostrophe; original subjects and ids remain in manifest.json.\n'
    ).encode('utf-8')
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return output.getvalue()


def _load_packet(raw: str) -> dict[str, Any]:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise HandoffError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    try:
        packet = json.loads(raw, object_pairs_hook=pairs)
        _json(packet)  # Reject NaN, infinity (including 1e400) and invalid Unicode.
    except (ValueError, RecursionError) as exc:
        raise HandoffError('Invalid input JSON: ' + str(exc)[:160]) from exc
    if not isinstance(packet, dict):
        raise HandoffError('Input packet must be an object.')
    return packet


def write_packet(packet: dict[str, Any], output: Path) -> None:
    """Validate first, then atomically replace only the requested output file."""
    data = build_email_bundle(packet.get('issues'), publication=packet.get('publication'),
                              source_metadata=packet.get('source_metadata'))
    output = Path(output)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix='.email-handoff-', delete=False) as stream:
            temporary = stream.name
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packet', type=Path, help='JSON containing publication, issues, optional source_metadata')
    parser.add_argument('--output', type=Path, required=True, help='ZIP output; atomically replaces this path')
    args = parser.parse_args()
    try:
        packet = _load_packet(args.packet.read_text(encoding='utf-8'))
        write_packet(packet, args.output)
    except (HandoffError, OSError, UnicodeError) as exc:
        parser.exit(2, f'email-handoff: {exc}\n')
    print(f'Created {args.output} (UNSENT_EXPORT; NOT_SCHEDULED)')


if __name__ == '__main__':
    main()
