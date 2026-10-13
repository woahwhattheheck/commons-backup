"""Compose the real catering calculator with real SQLite/HTTP and backup.

This is not a browser-navigation test. It exercises the canonical JavaScript
calculation/load/export functions in Node and the actual Python event service.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from event_backup import backup_events
from event_store import Store, ThreadingHTTPServer, make_handler

CALCULATOR = Path(os.environ.get('CATERING_JS', Path(__file__).with_name('catering.js'))).resolve()
NODE_SCRIPT = '''
const fs = require('node:fs');
const C = require(process.argv[1]);
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const document = input === null ? C.sample() : C.load(JSON.stringify(input));
process.stdout.write(JSON.stringify({document, quote:C.quote(document), kitchen:C.kitchenCSV(document)}));
'''


def calculate(document=None):
    if not CALCULATOR.is_file():
        raise RuntimeError('Run beside the canonical catering.js or set CATERING_JS to its exact source')
    if not shutil.which('node'):
        raise RuntimeError('Node.js is required for the real calculator integration tests')
    result = subprocess.run(['node', '-e', NODE_SCRIPT, str(CALCULATOR)],
                            input=json.dumps(document), capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class StorageContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = self.root / 'events.sqlite3'
        self.start(self.database)
        self.sample = calculate()['document']

    def start(self, database):
        self.store = Store(database)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.store))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def tearDown(self):
        self.stop()
        self.temp.cleanup()

    def request(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = Request(self.base + path, data=data, headers={'Content-Type': 'application/json'})
        with urlopen(request, timeout=10) as response:
            return json.load(response)

    def save(self, document, record=None, operation_id=None):
        return self.request('/api/events', {
            'document': document, 'id': record['id'] if record else None,
            'expected_revision': record['revision'] if record else 0,
            'title': document['event']['name'], 'operation_id': operation_id,
        })

    def test_canonical_quote_and_kitchen_survive_save_and_restart(self):
        before = calculate(self.sample)
        saved = self.save(before['document'], operation_id='first-save')
        self.stop()
        self.start(self.database)
        loaded = self.request('/api/events/' + saved['id'])
        self.assertEqual(loaded, saved)
        self.assertEqual(calculate(loaded['document']), before)
        self.assertEqual(before['quote']['totals']['total'], 78510)
        self.assertEqual(before['quote']['totals']['deposit'], 23553)
        self.assertEqual([line['units'] for line in before['quote']['lines']], [5, 5, 44])

    def test_headcount_updates_quote_kitchen_and_preserves_old_revision(self):
        initial = calculate(self.sample)
        first = self.save(initial['document'])
        changed = copy.deepcopy(initial['document'])
        changed['event']['headcount'] = '60'
        changed['revision'] += 1
        second = self.save(changed, first)
        reopened = calculate(self.request('/api/events/' + first['id'])['document'])
        self.assertEqual(reopened['quote']['totals']['total'], 109640)
        self.assertEqual(reopened['quote']['totals']['deposit'], 32892)
        self.assertEqual([line['units'] for line in reopened['quote']['lines']], [7, 7, 66])
        self.assertNotEqual(reopened['kitchen'], initial['kitchen'])
        self.assertEqual(second['revision'], 2)
        prior = self.request('/api/events/' + first['id'] + '/revisions/1')
        self.assertEqual(calculate(prior['document']), initial)

    def test_stale_document_cannot_replace_saved_quote(self):
        first = self.save(self.sample)
        winner = copy.deepcopy(self.sample)
        winner['event']['headcount'] = '60'
        winner['revision'] = 2
        second = self.save(winner, first)
        stale = copy.deepcopy(self.sample)
        stale['event']['headcount'] = '55'
        stale['revision'] = 2
        with self.assertRaises(HTTPError) as error:
            self.save(stale, first)
        self.assertEqual(error.exception.code, 409)
        self.assertEqual(stale['event']['headcount'], '55')
        current = self.request('/api/events/' + first['id'])
        self.assertEqual(current, second)
        self.assertEqual(calculate(current['document'])['quote']['totals']['total'], 109640)

    def test_quote_confirmation_revision_is_not_storage_revision(self):
        document = copy.deepcopy(self.sample)
        document['revision'] = 7
        document['confirmation'] = {'revision': 7, 'reference': 'Synthetic acceptance reference'}
        document['event']['received'] = '123.45'
        first = self.save(document)
        second = self.save(document, first)
        self.assertEqual(second['revision'], 2)
        self.assertEqual(second['document']['revision'], 7)
        self.assertTrue(calculate(second['document'])['quote']['confirmed'])
        self.assertEqual(calculate(second['document'])['quote']['totals']['received'], 12345)
        document['revision'] = 8
        document['event']['headcount'] = '60'
        third = self.save(document, second)
        self.assertFalse(calculate(third['document'])['quote']['confirmed'])
        self.assertEqual(third['document']['confirmation']['revision'], 7)

    def test_retry_after_backup_returns_original_without_losing_later_quote(self):
        first = self.save(self.sample, operation_id='stable-creation')
        changed = copy.deepcopy(self.sample)
        changed['event']['headcount'] = '60'
        changed['revision'] = 2
        second = self.save(changed, first, operation_id='later-save')
        target = self.root / 'copied.sqlite3'
        receipt = backup_events(self.database, target)
        self.assertEqual(receipt['counts']['operations'], 2)
        self.stop()
        self.start(target)
        retried = self.save(self.sample, operation_id='stable-creation')
        self.assertEqual(retried, first)
        current = self.request('/api/events/' + first['id'])
        self.assertEqual(current, second)
        self.assertEqual(calculate(current['document']), calculate(changed))
        self.assertEqual(len(self.request('/api/events')), 1)
        self.assertEqual(len(self.request('/api/events/' + first['id'] + '/revisions')), 2)

    def test_separate_events_preserve_overrides_notes_and_future_fields(self):
        first = self.save(self.sample)
        second_doc = copy.deepcopy(self.sample)
        second_doc['event']['name'] = 'Separate synthetic lunch'
        second_doc['event']['customer'] = 'Synthetic customer B'
        second_doc['event']['dietary'] = 'Customer request only; caterer decides suitability.'
        second_doc['event']['lines'][0]['guests'] = '12'
        second_doc['event']['lines'][0]['price'] = '43.21'
        second_doc['future_metadata'] = {'customer_reference': 'B', 'text': 'Événement 東京'}
        expected = calculate(second_doc)
        second = self.save(second_doc)
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(calculate(self.request('/api/events/' + second['id'])['document']), expected)
        self.assertEqual(self.request('/api/events/' + first['id'])['document'], self.sample)
        self.assertEqual(len(self.request('/api/events')), 2)


if __name__ == '__main__':
    if CALCULATOR.is_file():
        data = CALCULATOR.read_bytes()
        print('Canonical calculator SHA256:', hashlib.sha256(data).hexdigest(), flush=True)
    unittest.main()
