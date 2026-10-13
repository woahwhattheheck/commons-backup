"""Real formatter, filesystem/CLI, SQLite and HTTP-adapter regression tests."""
from __future__ import annotations

import copy
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

from placement_calendar import CalendarError, build_calendar

NOW = '2026-09-08T11:30:00Z'
UPDATED = '2026-09-08T10:00:00Z'


def placement(**changes):
    row = dict(id='booking-01', issue_date='2026-09-15', summary='Sample publisher: sample offer',
               revision=1, updated_at=UPDATED, description='Fictional planning fixture only.')
    row.update(changes)
    return row


def export(rows=None, **changes):
    options = dict(generated_at=NOW, namespace='fixture-workspace')
    options.update(changes)
    return build_calendar([placement()] if rows is None else rows, **options)


def unfold(data):
    """Independent byte-level unfolding, not the production helper."""
    return re.sub(rb'\r\n[ \t]', b'', data).decode('utf-8').split('\r\n')


def events(data):
    result, current = [], None
    for line in unfold(data):
        if line == 'BEGIN:VEVENT':
            if current is not None:
                raise AssertionError('nested event')
            current = {}
        elif line == 'END:VEVENT':
            if current is None:
                raise AssertionError('unmatched end')
            result.append(current)
            current = None
        elif current is not None:
            key, value = line.split(':', 1)
            if key in current:
                raise AssertionError('duplicate property')
            current[key] = value
    if current is not None:
        raise AssertionError('unterminated event')
    return result


def unescape(text):
    return re.sub(r'\\([\\,;nN])', lambda m: '\n' if m[1] in 'nN' else m[1], text)


class CalendarTests(unittest.TestCase):
    def test_complete_utf8_crlf_bytes(self):
        data = export()
        self.assertIsInstance(data, bytes)
        self.assertTrue(data.startswith(b'BEGIN:VCALENDAR\r\nVERSION:2.0\r\n'))
        self.assertTrue(data.endswith(b'END:VCALENDAR\r\n'))
        self.assertNotIn(b'\n', data.replace(b'\r\n', b''))
        self.assertNotIn(b'\r', data.replace(b'\r\n', b''))
        self.assertEqual(len(events(data)), 1)

    def test_utf8_folding_counts_octets(self):
        title = '日本語 🦉 café ' * 80
        data = export([placement(summary=title)])
        self.assertTrue(any(line.startswith(b' ') for line in data.split(b'\r\n')))
        for line in data.split(b'\r\n'):
            self.assertLessEqual(len(line), 75)
            line.decode('utf-8')
        self.assertEqual(unescape(events(data)[0]['SUMMARY']), title)

    def test_ascii_folding_exact_boundaries(self):
        for size in (65, 66, 67, 74, 75, 76, 140, 141, 142, 150, 1000):
            with self.subTest(size=size):
                data = export([placement(summary='A' * size)])
                self.assertEqual(events(data)[0]['SUMMARY'], 'A' * size)
                self.assertTrue(all(len(line) <= 75 for line in data.split(b'\r\n')))

    def test_text_escaping_and_newline_normalization(self):
        text = 'One, two; C:\\plans\r\nNext\rLast\nTab\tend'
        record = events(export([placement(summary=text, description=text)]))[0]
        expected = text.replace('\r\n', '\n').replace('\r', '\n')
        self.assertEqual(unescape(record['SUMMARY']), expected)
        self.assertTrue(unescape(record['DESCRIPTION']).endswith(expected))

    def test_embedded_property_text_stays_in_summary(self):
        title = 'Draft\r\nSTATUS:CONFIRMED\r\nBEGIN:VEVENT'
        data = export([placement(summary=title)])
        self.assertEqual(len(events(data)), 1)
        self.assertEqual(events(data)[0]['STATUS'], 'TENTATIVE')
        self.assertEqual(unescape(events(data)[0]['SUMMARY']), title.replace('\r\n', '\n'))

    def test_local_plan_is_not_scheduling_transaction(self):
        lines = unfold(export())
        record = events(export())[0]
        self.assertEqual(record['STATUS'], 'TENTATIVE')
        self.assertEqual(record['TRANSP'], 'TRANSPARENT')
        self.assertFalse(any(line.startswith(('METHOD:', 'ORGANIZER:', 'ATTENDEE:')) for line in lines))
        self.assertIn('No publisher confirmation', unescape(record['DESCRIPTION']))

    def test_stable_uid_across_reschedule_and_revisions(self):
        first = events(export())[0]
        second = events(export([placement(issue_date='2026-09-22', summary='Revised', revision=2)]))[0]
        self.assertEqual(first['UID'], second['UID'])
        self.assertNotEqual(first['DTSTART;VALUE=DATE'], second['DTSTART;VALUE=DATE'])
        self.assertEqual(second['SEQUENCE'], '2')

    def test_workspace_namespace_separates_identical_ids(self):
        first = events(export(namespace='workspace-a'))[0]
        second = events(export(namespace='workspace-b'))[0]
        self.assertNotEqual(first['UID'], second['UID'])

    def test_uid_framing_is_unambiguous(self):
        a = events(export([placement(id='b:c')], namespace='a'))[0]['UID']
        b = events(export([placement(id='c')], namespace='a:b'))[0]['UID']
        self.assertNotEqual(a, b)
        self.assertRegex(a, r'^[a-f0-9]{64}@hive\.local$')

    def test_cancelled_event_is_retained(self):
        before = events(export())[0]
        after = events(export([placement(cancelled=True, revision=2,
                                         updated_at='2026-09-08T11:00:00Z')]))[0]
        self.assertEqual(after['UID'], before['UID'])
        self.assertEqual(after['STATUS'], 'CANCELLED')
        self.assertEqual(after['SEQUENCE'], '2')
        self.assertEqual(after['LAST-MODIFIED'], '20260908T110000Z')

    def test_all_day_date_not_shifted_by_timezone(self):
        row = events(export([placement(issue_date='2028-02-29',
                         updated_at='2026-09-08T23:30:00-07:00')]))[0]
        self.assertEqual(row['DTSTART;VALUE=DATE'], '20280229')
        self.assertEqual(row['DURATION'], 'P1D')
        self.assertNotIn('DTEND', row)
        self.assertEqual(row['LAST-MODIFIED'], '20260909T063000Z')

    def test_supported_years_are_zero_padded(self):
        for year in ('0001', '0099', '0999', '9999'):
            with self.subTest(year=year):
                row = events(export([placement(issue_date=year + '-01-02',
                                               updated_at=year + '-01-02T03:04:05Z')]))[0]
                self.assertEqual(row['DTSTART;VALUE=DATE'], year + '0102')
                self.assertEqual(row['DTSTAMP'], year + '0102T030405Z')

    def test_snapshot_dtstamp_is_source_revision_not_export_time(self):
        a = events(export())[0]
        b = events(export(generated_at='2026-10-01T10:00:00Z'))[0]
        self.assertEqual(a, b)
        self.assertEqual(a['DTSTAMP'], a['LAST-MODIFIED'])
        self.assertIn('X-HIVE-GENERATED-AT:20260908T113000Z', unfold(export()))

    def test_datetime_objects_accepted(self):
        data = export([placement(updated_at=datetime(2026, 9, 8, tzinfo=timezone.utc))],
                      generated_at=datetime(2026, 9, 8, 11, 30, tzinfo=timezone.utc))
        self.assertEqual(events(data)[0]['DTSTAMP'], '20260908T000000Z')

    def test_deterministic_order_and_generators(self):
        rows = [placement(id='later', issue_date='2026-09-30'), placement(id='first')]
        self.assertEqual(export(rows), export(iter(reversed(rows))))
        self.assertEqual(events(export(rows))[0]['DTSTART;VALUE=DATE'], '20260915')

    def test_inputs_not_mutated(self):
        rows = [placement(), placement(id='second', cancelled=True)]
        saved = copy.deepcopy(rows)
        export(rows)
        self.assertEqual(rows, saved)

    def test_empty_calendar_reports_no_placements(self):
        with self.assertRaisesRegex(CalendarError, 'no placements'):
            export([])

    def test_invalid_record_containers(self):
        for value in ({}, '', b'', 1, None):
            with self.subTest(value=value), self.assertRaises(CalendarError):
                build_calendar(value, namespace='fixture', generated_at=NOW)
        for value in (None, [], 1, 'row'):
            with self.subTest(row=value), self.assertRaises(CalendarError):
                export([value])

    def test_invalid_dates(self):
        for value in ('2026-02-29', '2026-9-01', '2026-13-01', '0000-01-01',
                      '2026-09-01T00:00:00', '２０２６-09-01', '', None, [], 1):
            with self.subTest(value=value), self.assertRaises(CalendarError):
                export([placement(issue_date=value)])

    def test_invalid_revisions(self):
        for value in (True, False, -1, 2147483648, '1', 1.2, None, [], {}):
            with self.subTest(value=value), self.assertRaises(CalendarError):
                export([placement(revision=value)])
        for value in (0, 2147483647):
            self.assertEqual(events(export([placement(revision=value)]))[0]['SEQUENCE'], str(value))

    def test_invalid_cancelled_flag(self):
        for value in ('false', 0, 1, None, [], {}):
            with self.subTest(value=value), self.assertRaises(CalendarError):
                export([placement(cancelled=value)])

    def test_invalid_text_unicode_and_controls(self):
        for field in ('id', 'summary', 'description'):
            for value in (None, [], {}, 2, '\x00bad', '\x7fbad', '\ud800'):
                with self.subTest(field=field, value=repr(value)), self.assertRaises(CalendarError):
                    export([placement(**{field: value})])
        for value in ('', ' ', None, [], '\ud800'):
            with self.subTest(namespace=repr(value)), self.assertRaises(CalendarError):
                export(namespace=value)

    def test_invalid_or_naive_timestamps(self):
        values = (None, [], {}, True, '2026-09-08', '2026-09-08T12:00:00',
                  'not a date', datetime(2026, 9, 8), '0001-01-01T00:00:00+01:00',
                  '9999-12-31T23:59:59-01:00')
        for value in values:
            with self.subTest(value=repr(value)), self.assertRaises(CalendarError):
                export([placement(updated_at=value)])
            with self.subTest(generated=repr(value)), self.assertRaises(CalendarError):
                export(generated_at=value)

    def test_duplicate_ids_fail_instead_of_duplicate_events(self):
        with self.assertRaisesRegex(CalendarError, 'duplicate record id'):
            export([placement(), placement(revision=2)])

    def test_valid_url_is_uri_not_escaped_text(self):
        url = 'https://example.invalid/brief;a,b?labels=a,b&state=draft#creative'
        self.assertEqual(events(export([placement(url=url)]))[0]['URL'], url)
        self.assertNotIn('URL', events(export())[0])

    def test_invalid_url_shapes(self):
        for value in ('file:///tmp/a', 'javascript:alert(1)', 'https://', 'https://user:pw@example.invalid/',
                      'https://example.invalid/a\nb', 'https://example.invalid:99999/',
                      'https://例.example/', 'https://example.invalid\\x', None, [], 1):
            with self.subTest(value=value), self.assertRaises(CalendarError):
                export([placement(url=value)])


class IntegrationTests(unittest.TestCase):
    def test_sqlite_reopen_reschedule_cancel_preserves_uid(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'placements.sqlite3'
            with sqlite3.connect(path) as con:
                con.execute('CREATE TABLE placements(id TEXT PRIMARY KEY, payload TEXT)')
                con.execute('INSERT INTO placements VALUES (?, ?)', ('booking-01', json.dumps(placement())))
            def read():
                with sqlite3.connect(path) as con:
                    return export([json.loads(row[0]) for row in con.execute('SELECT payload FROM placements')])
            first = events(read())[0]
            with sqlite3.connect(path) as con:
                row = placement(issue_date='2026-09-22', revision=2)
                con.execute('UPDATE placements SET payload=?', (json.dumps(row),))
            second = events(read())[0]
            with sqlite3.connect(path) as con:
                row.update(cancelled=True, revision=3, updated_at='2026-09-09T08:00:00Z')
                con.execute('UPDATE placements SET payload=?', (json.dumps(row),))
            third = events(read())[0]
            self.assertEqual(first['UID'], second['UID'])
            self.assertEqual(second['UID'], third['UID'])
            self.assertEqual(third['SEQUENCE'], '3')
            self.assertEqual(third['STATUS'], 'CANCELLED')
            self.assertEqual(third['DTSTART;VALUE=DATE'], '20260922')

    def test_http_adapter_serves_exact_bytes(self):
        # Independent test adapter, not QUOIN's product server or a vendor client.
        expected = export([placement(summary='日本語 🦉 sample')])
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                data = export([placement(summary='日本語 🦉 sample')])
                self.send_response(200)
                self.send_header('Content-Type', 'text/calendar; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def log_message(self, *_args):
                pass
        with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urlopen(f'http://127.0.0.1:{server.server_port}/calendar.ics', timeout=3) as response:
                    self.assertEqual(response.headers['Content-Type'], 'text/calendar; charset=utf-8')
                    self.assertEqual(response.read(), expected)
            finally:
                server.shutdown()
                thread.join(3)

    def run_cli(self, root, content):
        source, target = Path(root) / 'input.json', Path(root) / 'calendar.ics'
        source.write_text(content, encoding='utf-8')
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('placement_calendar.py')),
                                 str(source), str(target)], capture_output=True, timeout=5)
        return result, target

    def test_cli_success_matches_library(self):
        with tempfile.TemporaryDirectory() as root:
            payload = dict(namespace='fixture-workspace', generated_at=NOW, records=[placement()])
            result, target = self.run_cli(root, json.dumps(payload))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.read_bytes(), export())

    def test_cli_bad_input_keeps_existing_calendar(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / 'calendar.ics'
            original = export()
            target.write_bytes(original)
            for content in ('{', '[]', '{"namespace":"a","namespace":"b"}',
                            json.dumps(dict(namespace='n', generated_at=NOW, records=[]))):
                with self.subTest(content=content):
                    result, actual = self.run_cli(root, content)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn(b'calendar export:', result.stderr)
                    self.assertEqual(actual.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
