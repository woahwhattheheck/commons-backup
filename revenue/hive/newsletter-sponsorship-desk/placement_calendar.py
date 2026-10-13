#!/usr/bin/env python3
"""Deterministic iCalendar export for a local sponsorship planning workspace.

This module formats supplied records. It does not send invitations, synchronize
calendars, reserve publisher inventory, or infer publisher acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


class CalendarError(ValueError):
    """Input cannot be represented by the placement calendar contract."""


def _text(value: object, field: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise CalendarError(f'{field} must be {"text" if empty else "nonempty text"}')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError:
        raise CalendarError(f'{field} must be valid Unicode') from None
    if any(ord(c) < 32 and c not in '\r\n\t' for c in value) or '\x7f' in value:
        raise CalendarError(f'{field} contains unsupported control characters')
    return value


def _utc(value: object, field: str) -> datetime:
    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError()
        return value.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        raise CalendarError(f'{field} must be a valid timezone-aware datetime') from None


def _stamp(value: datetime) -> str:
    return f'{value.year:04d}{value.month:02d}{value.day:02d}T{value.hour:02d}{value.minute:02d}{value.second:02d}Z'


def _escape(value: str) -> str:
    return (value.replace('\r\n', '\n').replace('\r', '\n').replace('\\', '\\\\')
            .replace('\n', '\\n').replace(';', '\\;').replace(',', '\\,'))


def _fold(line: str) -> list[str]:
    """Fold at 75 UTF-8 octets, counting the continuation space."""
    parts, current, size = [], '', 0
    for char in line:
        width = len(char.encode('utf-8'))
        if size + width > 75:
            parts.append(current)
            current, size = ' ', 1
        current += char
        size += width
    return parts + [current]


def _record(record: object, namespace: str) -> dict:
    if not isinstance(record, Mapping):
        raise CalendarError('each record must be an object')
    ident = _text(record.get('id'), 'id')
    issue_date = record.get('issue_date')
    try:
        if not isinstance(issue_date, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', issue_date):
            raise ValueError()
        date.fromisoformat(issue_date)
    except ValueError:
        raise CalendarError('issue_date must be a valid YYYY-MM-DD date') from None
    revision = record.get('revision')
    if type(revision) is not int or not 0 <= revision <= 2147483647:
        raise CalendarError('revision must be an integer from 0 to 2147483647')
    cancelled = record.get('cancelled', False)
    if type(cancelled) is not bool:
        raise CalendarError('cancelled must be a boolean')
    link = _text(record.get('url', ''), 'url', empty=True)
    if link:
        try:
            parsed = urlsplit(link)
            if (not link.isascii() or any(c.isspace() for c in link) or
                    parsed.scheme not in ('http', 'https') or not parsed.hostname or
                    parsed.username is not None or parsed.password is not None or '\\' in link):
                raise ValueError()
            _ = parsed.port
        except ValueError:
            raise CalendarError('url must be an ASCII HTTP(S) URI without credentials or whitespace') from None
    # JSON framing avoids delimiter ambiguities; the workspace namespace must
    # stay stable across exports, but differ between independent workspaces.
    key = json.dumps([namespace, ident], ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return {'id': ident, 'uid': hashlib.sha256(key).hexdigest() + '@hive.local',
            'issue_date': issue_date, 'revision': revision, 'cancelled': cancelled,
            'summary': _text(record.get('summary'), 'summary'),
            'description': _text(record.get('description', ''), 'description', empty=True),
            'updated_at': _utc(record.get('updated_at'), 'updated_at'), 'url': link}


def build_calendar(records: Iterable[Mapping], *, generated_at: datetime | str,
                   namespace: str) -> bytes:
    """Return a complete UTF-8 CRLF calendar; never mutate input or write files.

    Required per-record fields: id, issue_date, summary, revision, updated_at.
    Optional: description, url, cancelled (boolean; default False).
    Include cancelled records with incremented revisions as tombstones. Normal
    records remain TENTATIVE: a local plan is not publisher confirmation.
    An empty iterable raises CalendarError instead of inventing a placeholder.
    """
    namespace = _text(namespace, 'namespace')
    stamp = _utc(generated_at, 'generated_at')
    if isinstance(records, (str, bytes, Mapping)) or not isinstance(records, Iterable):
        raise CalendarError('records must be an iterable of record objects')
    normalized, seen = [], set()
    for source in records:
        record = _record(source, namespace)
        if record['id'] in seen:
            raise CalendarError(f"duplicate record id: {record['id']!r}")
        seen.add(record['id'])
        normalized.append(record)
    if not normalized:
        raise CalendarError('no placements to export')
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0',
             'PRODID:-//Commons Hive//Placement Calendar//EN', 'CALSCALE:GREGORIAN',
             'X-HIVE-GENERATED-AT:' + _stamp(stamp)]
    for record in sorted(normalized, key=lambda r: (r['issue_date'], r['uid'])):
        description = ('Local sponsorship plan only. No publisher confirmation, invitation or payment is implied.'
                       + ('\n' + record['description'] if record['description'] else ''))
        lines.extend(['BEGIN:VEVENT', 'UID:' + record['uid'],
                      'DTSTAMP:' + _stamp(record['updated_at']),
                      'LAST-MODIFIED:' + _stamp(record['updated_at']),
                      'SEQUENCE:' + str(record['revision']),
                      'DTSTART;VALUE=DATE:' + record['issue_date'].replace('-', ''),
                      'DURATION:P1D', 'SUMMARY:' + _escape(record['summary']),
                      'DESCRIPTION:' + _escape(description), 'TRANSP:TRANSPARENT',
                      'STATUS:' + ('CANCELLED' if record['cancelled'] else 'TENTATIVE')])
        if record['url']:
            # URL is URI-valued, not TEXT-valued: do not backslash-escape commas.
            lines.append('URL:' + record['url'])
        lines.append('END:VEVENT')
    lines.append('END:VCALENDAR')
    return ('\r\n'.join(part for line in lines for part in _fold(line)) + '\r\n').encode('utf-8')


def _unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise CalendarError(f'duplicate JSON field: {key}')
        result[key] = value
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='JSON object: namespace, generated_at, records')
    parser.add_argument('output', type=Path, help='Destination .ics file')
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.input.read_text(encoding='utf-8'), object_pairs_hook=_unique_object)
        if not isinstance(payload, dict):
            raise CalendarError('input must be a JSON object')
        content = build_calendar(payload.get('records'), generated_at=payload.get('generated_at'),
                                 namespace=payload.get('namespace'))
        # Complete validation precedes opening the output; a malformed input
        # cannot truncate an earlier successful calendar.
        args.output.write_bytes(content)
    except (CalendarError, OSError, ValueError, UnicodeError) as exc:
        parser.exit(2, f'calendar export: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
