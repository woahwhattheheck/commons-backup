"""Real SQLite and loopback HTTP coverage for the catering storage sidecar."""
import concurrent.futures
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from event_store import Conflict, InputError, Store, ThreadingHTTPServer, canonical, make_handler, parse_json


SAMPLE = {'menu': [{'id': 'TRAY', 'price': '72.00', 'yield': 10}],
          'event': {'name': 'Synthetic lunch', 'guests': 40, 'notes': 'Caterer decides menu suitability'},
          'quote': {'total': '439.95', 'deposit': '109.99'}, 'confirmation': None}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'events.sqlite3'
        self.store = Store(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_save_reopen_exact_document_without_recalculation(self):
        record = self.store.save(SAMPLE, title='Lunch')
        self.assertEqual(record['document'], SAMPLE)
        self.assertEqual(record['revision'], 1)
        self.assertEqual(self.store.get(record['id']), record)
        self.assertEqual(record['sha256'], hashlib.sha256(canonical(SAMPLE).encode()).hexdigest())
        self.assertEqual(record['document']['quote']['total'], '439.95')

    def test_data_survives_new_store_instance(self):
        record = self.store.save(SAMPLE)
        reopened = Store(self.path)
        self.assertEqual(reopened.get(record['id']), record)

    def test_new_events_are_separate(self):
        first = self.store.save(SAMPLE, title='First')
        changed = copy.deepcopy(SAMPLE)
        changed['event']['name'] = 'Second'
        second = self.store.save(changed, title='Second')
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(self.store.get(first['id'])['document'], SAMPLE)
        self.assertEqual(len(self.store.list()), 2)
        self.assertNotIn('document', self.store.list()[0])

    def test_revision_history_retains_original(self):
        first = self.store.save(SAMPLE, title='Forty')
        changed = {'event': {'guests': 55}, 'quote': {'total': '616.35'}}
        second = self.store.save(changed, first['id'], 1, title='Fifty-five')
        self.assertEqual(second['revision'], 2)
        self.assertEqual(self.store.get(first['id'], 1), first)
        self.assertEqual(self.store.get(first['id']), second)
        self.assertEqual([row['revision'] for row in self.store.history(first['id'])], [2, 1])

    def test_stale_save_preserves_winner_and_history(self):
        first = self.store.save(SAMPLE)
        second = self.store.save({'new': 'contents'}, first['id'], 1)
        with self.assertRaises(Conflict):
            self.store.save({'stale': 'contents'}, first['id'], 1)
        self.assertEqual(self.store.get(first['id']), second)
        self.assertEqual(len(self.store.history(first['id'])), 2)

    def test_concurrent_save_has_one_winner(self):
        first = self.store.save(SAMPLE)
        barrier = threading.Barrier(2)
        def update(value):
            barrier.wait()
            try:
                return self.store.save({'value': value}, first['id'], 1)['revision']
            except Conflict:
                return 'conflict'
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(update, [1, 2]))
        self.assertCountEqual(results, [2, 'conflict'])
        self.assertEqual(len(self.store.history(first['id'])), 2)

    def test_same_new_operation_is_idempotent(self):
        first = self.store.save(SAMPLE, operation_id='save-new-1')
        second = self.store.save(SAMPLE, operation_id='save-new-1')
        self.assertEqual(first, second)
        self.assertEqual(len(self.store.list()), 1)
        self.assertEqual(len(self.store.history(first['id'])), 1)

    def test_retry_returns_original_revision_after_later_edit(self):
        first = self.store.save(SAMPLE, operation_id='new')
        updated = self.store.save({'updated': True}, first['id'], 1, operation_id='edit')
        third = self.store.save({'third': True}, first['id'], 2)
        retry = self.store.save({'updated': True}, first['id'], 1, operation_id='edit')
        self.assertEqual(retry, updated)
        self.assertEqual(self.store.get(first['id']), third)
        self.assertEqual(len(self.store.history(first['id'])), 3)

    def test_operation_cannot_describe_changed_contents(self):
        first = self.store.save(SAMPLE, operation_id='one')
        with self.assertRaises(Conflict):
            self.store.save({'different': True}, operation_id='one')
        self.assertEqual(self.store.get(first['id']), first)

    def test_concurrent_new_operation_does_not_duplicate(self):
        barrier = threading.Barrier(2)
        def save(_):
            barrier.wait()
            return self.store.save(SAMPLE, operation_id='same-new')
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(save, range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(self.store.list()), 1)

    def test_invalid_documents_and_revisions(self):
        for document in [None, [], True, {'n': float('nan')}, {'n': float('inf')}, {'large': 'x' * 1_000_000}]:
            with self.subTest(document_type=type(document).__name__), self.assertRaises(InputError):
                self.store.save(document)
        for revision in [True, 1.5, '1', -1]:
            with self.subTest(revision=revision), self.assertRaises(InputError):
                self.store.save(SAMPLE, expected_revision=revision)
        self.assertEqual(self.store.list(), [])

    def test_missing_event_and_revision(self):
        with self.assertRaises(KeyError):
            self.store.get('0' * 32)
        with self.assertRaises(KeyError):
            self.store.save(SAMPLE, '0' * 32, 0)
        first = self.store.save(SAMPLE)
        with self.assertRaises(KeyError):
            self.store.get(first['id'], 8)
        with self.assertRaises(Conflict):
            self.store.save(SAMPLE, expected_revision=2)

    def test_json_rejects_duplicate_and_nonfinite_values(self):
        for data in ['{"a":1,"a":2}', '{"a":{"b":1,"b":2}}', '{"n":NaN}', '{"n":Infinity}', '{bad']:
            with self.subTest(data=data), self.assertRaises(InputError):
                parse_json(data)

    def test_unknown_fields_unicode_and_explicit_receipts_roundtrip(self):
        document = {'customer': 'Événement 東京', 'unknown_future_field': [True, None, {'text': '🍽'}],
                    'received': '12.34', 'payment_source': 'synthetic manually supplied field'}
        saved = self.store.save(document)
        self.assertEqual(saved['document'], document)
        self.assertEqual(self.store.get(saved['id'])['document'], document)

    def test_restoring_old_revision_creates_new_revision(self):
        first = self.store.save(SAMPLE)
        self.store.save({'changed': True}, first['id'], 1)
        restored = self.store.save(self.store.get(first['id'], 1)['document'], first['id'], 2)
        self.assertEqual(restored['revision'], 3)
        self.assertEqual(restored['document'], SAMPLE)
        self.assertEqual(len(self.store.history(first['id'])), 3)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'assets'
        self.root.mkdir()
        (self.root / 'index.html').write_text('<h1>Existing catering UI</h1>')
        (self.root / 'catering.js').write_text('window.originalCalculator = true;')
        self.store = Store(Path(self.temp.name) / 'private' / 'events.sqlite3')
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.store, self.root))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, body=None, raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        return urlopen(Request(self.base + path, data=data, headers={'Content-Type': 'application/json'}), timeout=10)

    def test_serve_original_assets_and_status(self):
        with self.request('/') as response:
            self.assertEqual(response.read().decode(), '<h1>Existing catering UI</h1>')
        with self.request('/catering.js') as response:
            self.assertIn(b'originalCalculator', response.read())
        with self.request('/api/status') as response:
            self.assertEqual(json.load(response)['service'], 'hive-catering-event-store')
        with self.assertRaises(HTTPError) as error:
            self.request('/events.sqlite3')
        self.assertEqual(error.exception.code, 404)

    def test_full_real_http_event_flow(self):
        with self.request('/api/events', {'document': SAMPLE, 'title': 'Lunch', 'operation_id': 'http-new'}) as response:
            first = json.load(response)
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
        with self.request('/api/events', {'document': SAMPLE, 'title': 'Lunch', 'operation_id': 'http-new'}) as response:
            self.assertEqual(json.load(response), first)
        changed = copy.deepcopy(SAMPLE)
        changed['event']['guests'] = 55
        changed['quote']['total'] = '616.35'
        with self.request('/api/events', {'document': changed, 'id': first['id'], 'expected_revision': 1}) as response:
            second = json.load(response)
        with self.request('/api/events/' + first['id']) as response:
            self.assertEqual(json.load(response), second)
        with self.request('/api/events/' + first['id'] + '/revisions/1') as response:
            self.assertEqual(json.load(response), first)
        with self.request('/api/events/' + first['id'] + '/revisions') as response:
            self.assertEqual(len(json.load(response)), 2)
        with self.request('/api/events') as response:
            self.assertEqual(len(json.load(response)), 1)

    def test_conflict_and_malformed_requests(self):
        first = self.store.save(SAMPLE)
        cases = [({'document': SAMPLE, 'id': first['id'], 'expected_revision': 0}, 409),
                 ({'document': []}, 400), ({'document': SAMPLE, 'id': 'missing'}, 400),
                 ({'document': SAMPLE, 'id': '0' * 32}, 404)]
        for body, status in cases:
            with self.subTest(body=body), self.assertRaises(HTTPError) as error:
                self.request('/api/events', body)
            self.assertEqual(error.exception.code, status)
        for raw in [b'{"document":{},"document":{"changed":true}}', b'{"document":{"x":NaN}}', b'[]']:
            with self.subTest(raw=raw), self.assertRaises(HTTPError) as error:
                self.request('/api/events', raw=raw)
            self.assertEqual(error.exception.code, 400)
        self.assertEqual(self.store.get(first['id']), first)

    def test_read_routes_return_json_errors(self):
        for route, code in [('/api/unknown', 404), ('/api/events/bad', 400), ('/api/events/' + '0' * 32, 404)]:
            with self.subTest(route=route), self.assertRaises(HTTPError) as error:
                self.request(route)
            self.assertEqual(error.exception.code, code)
            self.assertIn('error', json.load(error.exception))


if __name__ == '__main__':
    unittest.main()
