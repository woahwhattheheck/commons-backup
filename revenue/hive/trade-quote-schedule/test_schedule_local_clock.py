"""Local-wall-clock input regressions using actual files, CLI and HTTP requests."""
import csv
from datetime import time
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

import trade_quote as app


class LocalClockTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.schedule = self.root / 'schedule.csv'
        self.first = self.quote('Q-CLOCK')
        self.second = self.quote('Q-NEXT')

    def quote(self, quote_id):
        target = self.root / (quote_id + '.json')
        target.write_text(json.dumps({
            'schema': app.SCHEMA, 'status': 'DRAFT_NOT_SENT',
            'quote_id': quote_id, 'request_id': 'REQ-' + quote_id,
            'customer': 'Synthetic clock fixture', 'service': 'interior_painting',
            'acceptance_token': 'fixture-token', 'valid_until': '2026-09-22',
            'schedule_duration_hours': '1', 'total': '10.00', 'currency': 'USD',
        }), encoding='utf-8')
        return target

    def accept(self, start, quote=None, schedule=None):
        return app.accept_quote(quote or self.first, 'fixture-token', '2026-09-15',
                                start, schedule or self.schedule)

    def rows(self):
        with self.schedule.open(newline='', encoding='utf-8') as handle:
            return list(csv.DictReader(handle))

    def cli(self, start):
        return subprocess.run(
            [sys.executable, str(Path(app.__file__).resolve()), 'accept',
             '--quote', str(self.first), '--token', 'fixture-token',
             '--date', '2026-09-15', '--start', start,
             '--schedule', str(self.schedule)],
            capture_output=True, text=True, timeout=10,
        )

    def start_server(self):
        server = app.ThreadingHTTPServer(('127.0.0.1', 0),
                 app.make_handler(app.ServeConfig(self.root, self.schedule)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def cleanup():
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
        self.addCleanup(cleanup)
        return f'http://127.0.0.1:{server.server_port}/accept'

    def post(self, url, start, quote='Q-CLOCK'):
        data = urlencode({'quote': quote, 'token': 'fixture-token',
                          'date': '2026-09-15', 'start': start}).encode()
        try:
            with urlopen(url, data, timeout=5) as response:
                return response.status, response.read().decode()
        except HTTPError as exc:
            return exc.code, exc.read().decode()

    def test_supported_naive_formats_remain_compatible(self):
        for value in ('09', '09:00', '0900', '09:00:00', '09:00:00.000000', 'T09:00'):
            with self.subTest(value=value):
                parsed = app._clock(value, 'start_time')
                self.assertEqual(time(9, 0), parsed)
                self.assertIsNone(parsed.tzinfo)
        self.assertEqual(time(0, 0), app._clock('00:00', 'start_time'))
        self.assertEqual(time(23, 59), app._clock('23:59', 'start_time'))

    def test_offset_bearing_clocks_are_not_silently_truncated(self):
        for value in ('09:00+01:00', '09:00-05:00', '09:00+00:00', '09:00Z',
                      '09:00+00:30', '0900+0100', '09:00+01:00:30'):
            with self.subTest(value=value):
                with self.assertRaisesRegex(app.QuoteError, 'local'):
                    app._clock(value, 'start_time')

    def test_non_string_clock_inputs_use_the_existing_error_contract(self):
        for value in (None, False, 9, 9.5, [], {}, b'09:00'):
            with self.subTest(value=value):
                with self.assertRaisesRegex(app.QuoteError, 'start_time.*HH:MM'):
                    app._clock(value, 'start_time')

    def test_invalid_formats_and_subminute_values_still_fail(self):
        for value in ('', 'later', '25:00', '09:60', '09:00:01', '09:00:00.000001'):
            with self.subTest(value=value):
                with self.assertRaisesRegex(app.QuoteError, 'start_time'):
                    app._clock(value, 'start_time')

    def test_offset_rejection_precedes_all_schedule_files(self):
        nested = self.root / 'not-created' / 'schedule.csv'
        with self.assertRaisesRegex(app.QuoteError, 'local'):
            self.accept('09:00+01:00', schedule=nested)
        self.assertFalse(nested.parent.exists())

    def test_offset_input_preserves_existing_schedule_and_receipt(self):
        self.accept('09:00')
        before = self.schedule.read_bytes()
        receipt = (self.root / 'Q-CLOCK-acceptance.json').read_bytes()
        with self.assertRaisesRegex(app.QuoteError, 'local'):
            self.accept('11:00+01:00', self.second)
        self.assertEqual(before, self.schedule.read_bytes())
        self.assertEqual(receipt, (self.root / 'Q-CLOCK-acceptance.json').read_bytes())
        self.assertFalse((self.root / 'Q-NEXT-acceptance.json').exists())

    def test_offset_in_existing_csv_is_diagnosed_without_rewriting_it(self):
        self.accept('09:00')
        rows = self.rows()
        rows[0]['start_time'] = '09:00+01:00'
        with self.schedule.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=app.SCHEDULE_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        before = self.schedule.read_bytes()
        with self.assertRaisesRegex(app.QuoteError, 'schedule.start_time.*local'):
            self.accept('11:00', self.second)
        self.assertEqual(before, self.schedule.read_bytes())
        self.assertFalse((self.root / 'Q-NEXT-acceptance.json').exists())

    def test_cli_offset_is_a_diagnostic_not_a_booking(self):
        result = self.cli('09:00+01:00')
        self.assertEqual(2, result.returncode, (result.stdout, result.stderr))
        self.assertIn('local', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertFalse(self.schedule.exists())

    def test_cli_local_clock_is_stored_and_retried(self):
        first = self.cli('09:00')
        self.assertEqual(0, first.returncode, first.stderr)
        second = self.cli('0900')
        self.assertEqual(0, second.returncode, second.stderr)
        self.assertEqual(json.loads(first.stdout), json.loads(second.stdout))
        self.assertEqual(['09:00'], [row['start_time'] for row in self.rows()])

    def test_http_offset_returns_400_before_creating_schedule(self):
        result = self.post(self.start_server(), '09:00+01:00')
        self.assertEqual(400, result[0], result)
        self.assertIn('local', result[1])
        self.assertFalse(self.schedule.exists())

    def test_http_offset_after_local_booking_does_not_disconnect_or_mutate(self):
        self.accept('09:00')
        before = self.schedule.read_bytes()
        result = self.post(self.start_server(), '11:00+01:00', 'Q-NEXT')
        self.assertEqual(400, result[0], result)
        self.assertIn('local', result[1])
        self.assertEqual(before, self.schedule.read_bytes())

    def test_http_local_booking_and_retry_remain_successful(self):
        url = self.start_server()
        self.assertEqual(200, self.post(url, '09:00')[0])
        self.assertEqual(200, self.post(url, '09:00:00')[0])
        self.assertEqual(['09:00'], [row['start_time'] for row in self.rows()])


if __name__ == '__main__':
    unittest.main()
