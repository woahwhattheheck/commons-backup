"""Real file, process and HTTP regressions for local acceptance persistence."""
import concurrent.futures
import csv
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

import trade_quote as app


PROCESS_WORKER = r'''
import sys, time
from pathlib import Path
import trade_quote as app
role, root, quote, start = sys.argv[1:]
root = Path(root)
read = app._read_schedule
def delayed(path):
    rows = read(path)
    (root / (role + '-read')).write_text('read', encoding='utf-8')
    if role == 'first':
        deadline = time.monotonic() + 6
        while not (root / 'release').exists():
            if time.monotonic() > deadline:
                raise RuntimeError('test release timed out')
            time.sleep(.01)
    return rows
app._read_schedule = delayed
(root / (role + '-ready')).write_text('ready', encoding='utf-8')
sys.argv = [app.__file__, 'accept', '--quote', quote, '--token', 'fixture-token',
            '--date', '2026-09-15', '--start', start,
            '--schedule', str(root / 'schedule.csv')]
raise SystemExit(app.main())
'''


class SchedulePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.schedule = self.root / 'schedule.csv'
        self.first = self.quote('Q-FIRST')
        self.second = self.quote('Q-SECOND')

    def quote(self, quote_id):
        path = self.root / f'{quote_id}.json'
        path.write_text(json.dumps({
            'schema': app.SCHEMA, 'status': 'DRAFT_NOT_SENT',
            'quote_id': quote_id, 'request_id': 'REQ-' + quote_id,
            'customer': 'Synthetic customer', 'service': 'interior_painting',
            'acceptance_token': 'fixture-token', 'valid_until': '2026-09-22',
            'schedule_duration_hours': '1', 'total': '10.00', 'currency': 'USD',
        }), encoding='utf-8')
        return path

    def accept(self, quote=None, start='09:00', schedule=None):
        return app.accept_quote(quote or self.first, 'fixture-token',
                                '2026-09-15', start, schedule or self.schedule)

    def rows(self):
        with self.schedule.open(newline='', encoding='utf-8') as handle:
            return list(csv.DictReader(handle))

    def threaded_race(self, second_start):
        first_read = threading.Event()
        second_read = threading.Event()
        release = threading.Event()
        counter_lock = threading.Lock()
        count = 0
        original = app._read_schedule

        def delayed(path):
            nonlocal count
            rows = original(path)  # Actual on-disk read; only interleaving is controlled.
            with counter_lock:
                count += 1
                position = count
            if position == 1:
                first_read.set()
                if not release.wait(5):
                    raise RuntimeError('test release timed out')
            else:
                second_read.set()
            return rows

        def attempt(quote, start):
            try:
                return self.accept(quote, start)
            except app.QuoteError as exc:
                return str(exc)

        with patch.object(app, '_read_schedule', side_effect=delayed):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                a = pool.submit(attempt, self.first, '09:00')
                try:
                    self.assertTrue(first_read.wait(3))
                    b = pool.submit(attempt, self.second, second_start)
                    # Before the repair, B finishes while A holds a stale empty snapshot.
                    # With serialization, B cannot read until A releases the transaction.
                    if second_read.wait(.25):
                        b.result(timeout=3)
                finally:
                    release.set()
                return a.result(timeout=3), b.result(timeout=3)

    def process_race(self, second_start):
        workers = []
        try:
            for role, quote, start in [('first', self.first, '09:00'),
                                       ('second', self.second, second_start)]:
                proc = subprocess.Popen(
                    [sys.executable, '-c', PROCESS_WORKER, role, str(self.root), str(quote), start],
                    cwd=Path(app.__file__).parent, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True,
                )
                workers.append(proc)
                ready = self.root / f'{role}-ready'
                ready_deadline = time.monotonic() + 3
                while not ready.exists() and time.monotonic() < ready_deadline:
                    time.sleep(.01)
                self.assertTrue(ready.exists(), 'worker imported the current app')
                marker = self.root / f'{role}-read'
                deadline = time.monotonic() + (3 if role == 'first' else .3)
                while not marker.exists() and time.monotonic() < deadline:
                    if proc.poll() is not None:
                        self.fail(f'worker exited before reading: {proc.communicate()}')
                    time.sleep(.01)
                if role == 'first':
                    self.assertTrue(marker.exists(), 'first process reached the actual read')
                elif marker.exists():
                    proc.wait(timeout=3)
            (self.root / 'release').write_text('go', encoding='utf-8')
            results = []
            for proc in workers:
                stdout, stderr = proc.communicate(timeout=8)
                results.append((proc.returncode, stdout, stderr))
            return results
        finally:
            (self.root / 'release').touch()
            for proc in workers:
                if proc.poll() is None:
                    proc.kill()
                proc.communicate(timeout=3)

    def test_threaded_distinct_bookings_preserve_both_rows(self):
        results = self.threaded_race('11:00')
        self.assertTrue(all(isinstance(result, dict) for result in results), results)
        self.assertEqual({'Q-FIRST', 'Q-SECOND'}, {row['quote_id'] for row in self.rows()})

    def test_threaded_overlapping_bookings_accept_only_one(self):
        results = self.threaded_race('09:30')
        self.assertEqual(1, sum(isinstance(result, dict) for result in results), results)
        self.assertTrue(any('collision' in result for result in results if isinstance(result, str)))
        self.assertEqual(1, len(self.rows()))
        self.assertEqual(1, len(list(self.root.glob('*-acceptance.json'))))

    def test_separate_cli_processes_preserve_both_rows(self):
        results = self.process_race('11:00')
        self.assertEqual([0, 0], [result[0] for result in results], results)
        self.assertEqual({'Q-FIRST', 'Q-SECOND'}, {row['quote_id'] for row in self.rows()})

    def test_separate_cli_processes_recheck_overlap(self):
        results = self.process_race('09:30')
        self.assertEqual([0, 2], [result[0] for result in results], results)
        self.assertIn('collision', results[1][2])
        self.assertEqual(1, len(self.rows()))

    def test_exact_retry_returns_same_receipt_without_rewriting_schedule(self):
        first = self.accept()
        before = self.schedule.read_bytes()
        stamp = self.schedule.stat().st_mtime_ns
        second = self.accept()
        self.assertEqual(first, second)
        self.assertEqual(before, self.schedule.read_bytes())
        self.assertEqual(stamp, self.schedule.stat().st_mtime_ns)
        self.assertEqual(1, len(self.rows()))

    def test_retry_repairs_missing_receipt_from_committed_schedule(self):
        expected = self.accept()
        receipt = self.root / 'Q-FIRST-acceptance.json'
        receipt.unlink()
        actual = self.accept()
        self.assertEqual(expected, actual)
        self.assertEqual(expected, json.loads(receipt.read_text(encoding='utf-8')))
        self.assertEqual(1, len(self.rows()))

    def test_same_quote_cannot_be_booked_again_in_a_different_slot(self):
        self.accept()
        before = self.schedule.read_bytes()
        with self.assertRaisesRegex(app.QuoteError, 'collision'):
            self.accept(start='11:00')
        self.assertEqual(before, self.schedule.read_bytes())

    def test_failed_schedule_replace_preserves_previous_file_and_cleans_staging(self):
        self.accept()
        before = self.schedule.read_bytes()
        replace = os.replace
        def failure(source, destination):
            if Path(destination) == self.schedule:
                raise OSError('synthetic replacement failure')
            return replace(source, destination)
        with patch('os.replace', side_effect=failure):
            with self.assertRaisesRegex(app.QuoteError, 'replacement failure'):
                self.accept(self.second, '11:00')
        self.assertEqual(before, self.schedule.read_bytes())
        self.assertFalse((self.root / 'Q-SECOND-acceptance.json').exists())
        self.assertFalse(list(self.root.glob('*.tmp')))
        self.accept(self.second, '11:00')  # The failed operation released its lock.
        self.assertEqual(2, len(self.rows()))

    def test_failed_receipt_replace_is_recoverable_without_duplicate_booking(self):
        receipt = self.root / 'Q-FIRST-acceptance.json'
        replace = os.replace
        def failure(source, destination):
            if Path(destination) == receipt:
                raise OSError('synthetic receipt failure')
            return replace(source, destination)
        with patch('os.replace', side_effect=failure):
            with self.assertRaisesRegex(app.QuoteError, 'receipt failure'):
                self.accept()
        self.assertEqual(1, len(self.rows()))
        self.assertFalse(receipt.exists())
        self.assertFalse(list(self.root.glob('*.tmp')))
        result = self.accept()
        self.assertEqual(result, json.loads(receipt.read_text(encoding='utf-8')))
        self.assertEqual(1, len(self.rows()))

    def test_validation_failure_releases_transaction_for_next_booking(self):
        self.accept()
        with self.assertRaisesRegex(app.QuoteError, 'collision'):
            self.accept(self.second, '09:30')
        self.accept(self.second, '10:00')
        self.assertEqual(2, len(self.rows()))

    def test_atomic_rewrite_preserves_existing_mode_and_adjacent_artifact(self):
        self.accept()
        self.schedule.chmod(0o640)
        original_mode = stat.S_IMODE(self.schedule.stat().st_mode)
        unrelated = self.root / 'schedule.csv.tmp'
        unrelated.write_bytes(b'other writer artifact')
        self.accept(self.second, '10:00')
        self.assertEqual(original_mode, stat.S_IMODE(self.schedule.stat().st_mode))
        self.assertEqual(b'other writer artifact', unrelated.read_bytes())

    def test_real_threaded_http_double_submit_is_successful_and_idempotent(self):
        server = app.ThreadingHTTPServer(('127.0.0.1', 0),
                                        app.make_handler(app.ServeConfig(self.root, self.schedule)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def request():
            body = urlencode({'quote': 'Q-FIRST', 'token': 'fixture-token',
                              'date': '2026-09-15', 'start': '09:00'}).encode()
            try:
                with urlopen(f'http://127.0.0.1:{server.server_port}/accept', body, timeout=5) as response:
                    return response.status, response.read().decode()
            except HTTPError as exc:
                return exc.code, exc.read().decode()
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: request(), range(2)))
            self.assertEqual([200, 200], [result[0] for result in results], results)
            self.assertEqual(1, len(self.rows()))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
