# SPDX-License-Identifier: Apache-2.0
"""Finite workspace numbers through the real SQLite and HTTP persistence paths."""
import hashlib
import importlib.util
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('prospect_store_finite', HERE / 'server.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FiniteStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'workspace.sqlite3'
        self.store = MODULE.Store(self.path)

    def operation_count(self):
        with self.store.connect() as db:
            return db.execute('SELECT COUNT(*) FROM operations').fetchone()[0]

    def assert_rejected_without_write(self, payload, operation='invalid'):
        before = self.store.read()
        count = self.operation_count()
        with self.assertRaisesRegex(ValueError, 'not a finite JSON number'):
            self.store.write(payload, before['revision'], operation)
        self.assertEqual(self.store.read(), before)
        self.assertEqual(self.operation_count(), count)

    def test_positive_exponent_overflow(self):
        self.assert_rejected_without_write('{"value": 1e999}')

    def test_negative_exponent_overflow(self):
        self.assert_rejected_without_write('{"value": -1e999}')

    def test_decimal_uppercase_exponent_overflow(self):
        self.assert_rejected_without_write('{"value": 9.99E+999}')

    def test_overflow_at_binary_float_boundary(self):
        self.assert_rejected_without_write('{"value": 1.7976931348623159e308}')

    def test_overflow_in_nested_account_data(self):
        self.assert_rejected_without_write(
            '{"accounts": [{"values": [0, {"value": 1e999}]}]}'
        )

    def test_nonfinite_symbols_still_rejected(self):
        for token in ('NaN', 'Infinity', '-Infinity'):
            with self.subTest(token=token):
                self.assert_rejected_without_write('{"value": ' + token + '}')

    def test_finite_extremes_preserve_exact_bytes_and_retry(self):
        payload = (
            '{\n "high": 1.7976931348623157e308, "low": -1.7976931348623157e308,\n'
            ' "small": 5e-324, "zero": -0.0, "underflow": 1e-999, "text": "café"\n}\n'
        )
        first = self.store.write(payload, 0, 'finite')
        restored = MODULE.Store(self.path).read()
        self.assertEqual(restored['payload'], payload)
        self.assertEqual(restored['sha256'], hashlib.sha256(payload.encode('utf-8')).hexdigest())
        self.assertEqual(first['revision'], 1)
        self.assertEqual(self.store.write(payload, 0, 'finite')['status'], 'already_applied')
        self.assertEqual(self.operation_count(), 1)

    def test_arbitrary_precision_integer_behavior_unchanged(self):
        # Existing integer semantics are intentionally separate from float parsing.
        payload = '{"value": ' + '9' * 400 + '}'
        self.store.write(payload, 0, 'integer')
        self.assertEqual(self.store.read()['payload'], payload)

    def test_number_looking_strings_are_not_numbers(self):
        payload = '{"notes": ["1e999", "-Infinity", "NaN", "9.99E+999"]}'
        self.store.write(payload, 0, 'strings')
        self.assertEqual(self.store.read()['payload'], payload)

    def test_invalid_update_preserves_snapshot_and_old_retry(self):
        payload = '{ "version": 1, "accounts": [] }\n'
        self.store.write(payload, 0, 'initial')
        self.assert_rejected_without_write('{"value": 1e999}')
        self.assertEqual(self.store.write(payload, 0, 'initial')['status'], 'already_applied')
        self.assertEqual(self.store.read()['payload'], payload)

    def test_rejected_payload_does_not_consume_operation_id(self):
        self.assert_rejected_without_write('{"value": 1e999}', 'correctable')
        result = self.store.write('{"value": 1.25}', 0, 'correctable')
        self.assertEqual(result['status'], 'saved')
        self.assertEqual(result['revision'], 1)
        self.assertEqual(self.operation_count(), 1)

    def test_delete_and_old_save_retry_after_rejection(self):
        self.store.write('{}', 0, 'initial')
        self.assert_rejected_without_write('{"value": -1e999}')
        deleted = self.store.write(None, 1, 'delete')
        self.assertEqual((deleted['revision'], deleted['present']), (2, False))
        self.assertEqual(self.store.write('{}', 0, 'initial')['status'], 'already_applied')
        self.assertEqual(self.store.write(None, 1, 'delete')['status'], 'already_applied')
        self.assertEqual(self.store.read(), {
            'revision': 2, 'payload': None, 'sha256': None, 'present': False,
        })

    def test_concurrent_invalid_writers_and_identical_valid_retries(self):
        def save(index):
            try:
                if index % 2:
                    return self.store.write('{"value": 1e999}', 0, f'invalid-{index}')['status']
                return self.store.write('{"value": 1.25}', 0, 'valid')['status']
            except ValueError as error:
                return 'nonfinite' if 'not a finite JSON number' in str(error) else 'other-error'
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(save, range(8)))
        self.assertEqual(results.count('nonfinite'), 4, results)
        self.assertEqual(results.count('saved'), 1, results)
        self.assertEqual(results.count('already_applied'), 3, results)
        self.assertEqual(self.operation_count(), 1)
        self.assertEqual(self.store.read()['payload'], '{"value": 1.25}')


class FiniteHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.store = MODULE.Store(root / 'workspace.sqlite3')
        self.server = MODULE.Server(('127.0.0.1', 0), self.store, root)
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True,
        )
        self.thread.start()
        self.addCleanup(self.close)
        self.url = f'http://127.0.0.1:{self.server.server_port}/api/state'

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.assertFalse(self.thread.is_alive())

    def request(self, data=None):
        request = Request(
            self.url, data=None if data is None else json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
        )
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def test_http_overflow_returns_400_and_leaves_empty_state(self):
        for index, token in enumerate(('1e999', '-1e999', '1.7976931348623159e308')):
            with self.subTest(token=token):
                status, body = self.request({
                    'payload': '{"value": ' + token + '}', 'expected_revision': 0,
                    'operation_id': f'invalid-{index}',
                })
                self.assertEqual(status, 400, body)
                self.assertIn('not a finite JSON number', body['error'])
                status, body = self.request()
                self.assertEqual(status, 200)
                self.assertEqual(body['revision'], 0)
                self.assertFalse(body['present'])

    def test_http_corrected_update_retry_and_old_retry_preserve_bytes(self):
        original = '{ "version": 1, "nextId": 1, "accounts": [], "imports": [], "segments": [] }\n'
        first = {'payload': original, 'expected_revision': 0, 'operation_id': 'first'}
        self.assertEqual(self.request(first)[0], 200)
        invalid = {'payload': '{"value": 1e999}', 'expected_revision': 1, 'operation_id': 'second'}
        status, body = self.request(invalid)
        self.assertEqual(status, 400, body)
        self.assertEqual(self.request()[1]['payload'], original)
        corrected = dict(invalid, payload='{ "value": 1.25 }\n')
        self.assertEqual(self.request(corrected)[1]['status'], 'saved')
        self.assertEqual(self.request(corrected)[1]['status'], 'already_applied')
        self.assertEqual(self.request(first)[1]['status'], 'already_applied')
        state = self.request()[1]
        self.assertEqual(state['revision'], 2)
        self.assertEqual(state['payload'], corrected['payload'])
        self.assertEqual(state['sha256'], hashlib.sha256(corrected['payload'].encode()).hexdigest())


if __name__ == '__main__':
    unittest.main()
