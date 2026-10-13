# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from server import Conflict, MAX_BYTES, Server, Store

PAYLOAD = '{\n  "version": 1, "companies": [{"name": "Synthetic example", "domain": "example.test"}]\n}\n'


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'state.sqlite3'
        self.store = Store(self.path)

    def test_empty_store(self):
        self.assertEqual(self.store.read(), {'revision': 0, 'payload': None, 'sha256': None, 'present': False})

    def test_exact_bytes_survive_reopen(self):
        result = self.store.write(PAYLOAD, 0, 'save-1')
        self.assertEqual(result['revision'], 1)
        reopened = Store(self.path).read()
        self.assertEqual(reopened['payload'], PAYLOAD)
        self.assertEqual(reopened['sha256'], hashlib.sha256(PAYLOAD.encode()).hexdigest())

    def test_same_operation_retry_is_idempotent(self):
        self.store.write(PAYLOAD, 0, 'save-1')
        self.assertEqual(self.store.write(PAYLOAD, 0, 'save-1')['status'], 'already_applied')
        self.assertEqual(self.store.read()['revision'], 1)

    def test_operation_id_cannot_refer_to_different_bytes(self):
        self.store.write(PAYLOAD, 0, 'save-1')
        for payload, revision in [('{}', 0), (PAYLOAD, 1)]:
            with self.assertRaises(Conflict):
                self.store.write(payload, revision, 'save-1')
        self.assertEqual(self.store.read()['payload'], PAYLOAD)

    def test_stale_save_and_delete_preserve_newer_data(self):
        self.store.write(PAYLOAD, 0, 'save-1')
        for payload in ('{}', None):
            with self.assertRaises(Conflict):
                self.store.write(payload, 0, 'stale')
        self.assertEqual(self.store.read()['payload'], PAYLOAD)

    def test_delete_clears_payload_and_retains_monotonic_revision(self):
        self.store.write(PAYLOAD, 0, 'save-1')
        result = self.store.write(None, 1, 'delete-1')
        self.assertEqual((result['revision'], result['present']), (2, False))
        self.assertIsNone(self.store.read()['payload'])
        self.assertEqual(self.store.write(None, 1, 'delete-1')['status'], 'already_applied')
        self.store.write('{}', 2, 'save-2')
        self.assertEqual(self.store.read()['revision'], 3)

    def test_old_retry_cannot_overwrite_later_save(self):
        self.store.write(PAYLOAD, 0, 'save-1')
        self.store.write('{}', 1, 'save-2')
        self.assertEqual(self.store.write(PAYLOAD, 0, 'save-1')['revision'], 1)
        self.assertEqual(self.store.read()['payload'], '{}')

    def test_invalid_payload_revision_or_operation_has_no_write(self):
        cases = [('[]', 0, 'a'), ('null', 0, 'b'), ('{"a":NaN}', 0, 'c'),
                 ('bad', 0, 'd'), ({}, 0, 'e'), ('{}', True, 'f'), ('{}', -1, 'g'),
                 ('{}', 0, ''), ('{}', 0, 'a b')]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.store.write(*args)
        self.assertEqual(self.store.read()['revision'], 0)

    def test_size_bound(self):
        with self.assertRaises(ValueError):
            self.store.write(json.dumps({'large': 'x' * MAX_BYTES}), 0, 'too-large')
        self.assertEqual(self.store.read()['revision'], 0)

    def test_two_concurrent_writers_only_one_advances_revision(self):
        def save(i):
            try:
                return self.store.write(json.dumps({'writer': i}), 0, f'save-{i}')['status']
            except Conflict:
                return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(save, (1, 2)))
        self.assertEqual(sorted(results), ['conflict', 'saved'])
        self.assertEqual(self.store.read()['revision'], 1)

    def test_concurrent_identical_retry(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.store.write(PAYLOAD, 0, 'save-1')['status'], (1, 2)))
        self.assertEqual(sorted(results), ['already_applied', 'saved'])


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        assets = root / 'assets'; assets.mkdir()
        self.original = '<!doctype html><html><body><h1>Consumer fixture</h1><script src="model.js"></script></body></html>'
        (assets / 'index.html').write_text(self.original)
        (assets / 'model.js').write_text('/* Exact consumer fixture */')
        self.store = Store(root / 'state.sqlite3')
        self.server = Server(('127.0.0.1', 0), self.store, assets)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.close)
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)

    def request(self, path, data=None):
        req = Request(self.url + path, data=None if data is None else json.dumps(data).encode(),
                      headers={'Content-Type': 'application/json'})
        with urlopen(req, timeout=5) as response:
            return response.read(), response.headers

    def test_real_http_save_reload_retry_delete(self):
        self.assertFalse(json.loads(self.request('/api/state')[0])['present'])
        body = {'payload': PAYLOAD, 'expected_revision': 0, 'operation_id': 'save-1'}
        self.assertEqual(json.loads(self.request('/api/state', body)[0])['status'], 'saved')
        self.assertEqual(json.loads(self.request('/api/state', body)[0])['status'], 'already_applied')
        self.assertEqual(json.loads(self.request('/api/state')[0])['payload'], PAYLOAD)
        self.request('/api/state', {'payload': None, 'expected_revision': 1, 'operation_id': 'delete-1'})
        self.assertFalse(json.loads(self.request('/api/state')[0])['present'])

    def test_http_conflict_is_409_without_data_loss(self):
        self.store.write(PAYLOAD, 0, 'save-1')
        with self.assertRaises(HTTPError) as caught:
            self.request('/api/state', {'payload': '{}', 'expected_revision': 0, 'operation_id': 'save-2'})
        self.assertEqual(caught.exception.code, 409)
        self.assertEqual(self.store.read()['payload'], PAYLOAD)

    def test_invalid_request_is_400(self):
        with self.assertRaises(HTTPError) as caught:
            self.request('/api/state', {'payload': []})
        self.assertEqual(caught.exception.code, 400)

    def test_serves_existing_assets_with_only_additive_panel(self):
        html, headers = self.request('/')
        addition = '<iframe src="/persistence.html" title="Private SQLite backups" style="width:100%;height:360px;border:0;display:block"></iframe>'
        self.assertEqual(html.decode(), self.original.replace('</body>', addition + '</body>'))
        self.assertEqual(self.request('/model.js')[0], b'/* Exact consumer fixture */')
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertIn(b'Save to SQLite', self.request('/persistence.html')[0])
        self.assertIn(b'expected_revision', self.request('/persistence.js')[0])


if __name__ == '__main__':
    unittest.main()
