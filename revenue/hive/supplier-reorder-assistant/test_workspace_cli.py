"""Real CLI processes and browser-store interoperability; synthetic data only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import csv
import hashlib
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen

from desk import MAX_CSV, Store, handler
from workspace_cli import main

ROOT = Path(__file__).resolve().parent
STOCK = 'sku,name,on_hand,on_order,allocated,unit\r\nA,Synthetic item,2,3,0,ea\r\n'
RULES = 'sku,reorder_at,target_stock,preferred_supplier\r\nA,5,14,SUP\r\n'
CATALOG = ('supplier_id,supplier_sku,sku,description,unit_cost,available_qty,lead_days,alternative_for_sku\r\n'
           'SUP,S-A,A,Synthetic item,4.25,20,1,\r\n')
HEADER = 'receipt_id,received_at,supplier_id,supplier_sku,sku,quantity\r\n'


def receipt(identity='R1', quantity=4, sku='A'):
    return HEADER + f'{identity},2026-09-08T10:00:00Z,SUP,S-A,{sku},{quantity}\r\n'


def stock_count(doc):
    row = next(csv.DictReader(io.StringIO(doc['updated_stock'])))
    return int(row['on_hand']), int(row['on_order'])


@contextmanager
def browser_api(path):
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler(Store(path)))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()


class WorkspaceCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'shared.sqlite3'
        for name, content in [('stock', STOCK), ('rules', RULES), ('catalog', CATALOG)]:
            (self.root / f'{name}.csv').write_bytes(content.encode())
        self.first = self.root / 'first.csv'
        self.first.write_bytes(receipt().encode())
        self.second = self.root / 'second.csv'
        self.second.write_bytes(receipt('R2', 5).encode())

    def cli(self, *args, code=0):
        run = subprocess.run([sys.executable, '-B', str(ROOT / 'workspace_cli.py'),
                              '--db', str(self.db), *map(str, args)], capture_output=True, timeout=20)
        self.assertEqual(run.returncode, code, run.stderr.decode(errors='replace'))
        if code:
            self.assertEqual(run.stdout, b'')
            self.assertNotIn(b'Traceback', run.stderr)
        else:
            self.assertEqual(run.stderr, b'')
        return run

    def create_args(self, operation='create-synthetic'):
        return ['create', '--operation-id', operation, '--title', 'Synthetic plan',
                '--stock', self.root / 'stock.csv', '--rules', self.root / 'rules.csv',
                '--catalog', self.root / 'catalog.csv', '--as-of', '2026-09-08']

    def create(self):
        return json.loads(self.cli(*self.create_args()).stdout)

    def receive_args(self, doc, path=None, operation='receive-R1', revision=None):
        return ['receive', doc['id'], '--receipts', path or self.first,
                '--expected-revision', doc['revision'] if revision is None else revision,
                '--operation-id', operation]

    def test_create_reopens_in_browser_store_with_exact_source_hashes(self):
        doc = self.create()
        self.assertEqual(Store(self.db).get(doc['id']), doc)
        self.assertEqual(doc['plan']['purchase_orders'][0]['lines'][0]['quantity'], 9)
        self.assertEqual(stock_count(doc), (2, 3))
        self.assertEqual(doc['source_sha256']['stock'], hashlib.sha256(STOCK.encode()).hexdigest())

    def test_create_operation_retry_returns_same_run_across_processes(self):
        first = self.create()
        self.assertEqual(self.create(), first)
        self.assertEqual(len(Store(self.db).list()), 1)

    def test_create_operation_reuse_with_changed_input_is_conflict(self):
        before = self.create()
        (self.root / 'stock.csv').write_text(STOCK.replace('Synthetic item', 'Changed item'))
        failed = self.cli(*self.create_args(), code=2)
        self.assertEqual(json.loads(failed.stderr)['status'], 409)
        self.assertEqual(Store(self.db).get(before['id']), before)

    def test_receive_retry_keeps_one_application_and_same_response(self):
        doc = self.create()
        args = self.receive_args(doc)
        first = json.loads(self.cli(*args).stdout)
        self.assertEqual(stock_count(first), (6, 3))
        self.assertEqual(json.loads(self.cli(*args).stdout), first)
        self.assertEqual(Store(self.db).history(doc['id']), [1, 2])

    def test_browser_receipt_then_cli_receipt_share_cumulative_cap(self):
        doc = self.create()
        browser = Store(self.db).receive(doc['id'], {'operation_id': 'browser-R1',
                                  'expected_revision': 1, 'csv': receipt()})
        final = json.loads(self.cli(*self.receive_args(browser, self.second, 'cli-R2')).stdout)
        self.assertEqual(stock_count(final), (11, 3))
        self.assertEqual(final['receipt_log']['count'], 2)
        self.assertEqual(Store(self.db).get(doc['id']), final)

    def test_cli_receipt_is_visible_through_real_http_api(self):
        doc = self.create()
        with browser_api(self.db) as url:
            received = json.loads(self.cli(*self.receive_args(doc)).stdout)
            with urlopen(f'{url}/api/runs/{doc["id"]}', timeout=5) as response:
                self.assertEqual(json.load(response), received)
            payload = json.dumps({'operation_id': 'http-R2', 'expected_revision': 2,
                                  'csv': receipt('R2', 5)}).encode()
            request = Request(f'{url}/api/runs/{doc["id"]}/receipts', data=payload,
                              headers={'Content-Type': 'application/json'})
            with urlopen(request, timeout=5) as response:
                last = json.load(response)
            self.assertEqual(stock_count(last), (11, 3))
            self.assertEqual(json.loads(self.cli('show', doc['id']).stdout), last)

    def test_new_operation_with_duplicate_receipt_does_not_add_revision(self):
        doc = self.create()
        first = json.loads(self.cli(*self.receive_args(doc)).stdout)
        again = json.loads(self.cli(*self.receive_args(first, operation='new-op-same-receipt')).stdout)
        self.assertEqual(again, first)
        self.assertEqual(Store(self.db).history(doc['id']), [1, 2])

    def test_conflicting_receipt_id_is_rejected_without_mutation(self):
        doc = self.create()
        first = json.loads(self.cli(*self.receive_args(doc)).stdout)
        self.second.write_text(receipt('R1', 5))
        fail = self.cli(*self.receive_args(first, self.second, 'changed-R1'), code=2)
        self.assertEqual(json.loads(fail.stderr)['status'], 409)
        self.assertEqual(Store(self.db).get(doc['id']), first)

    def test_stale_revision_requires_explicit_reread(self):
        doc = self.create()
        first = json.loads(self.cli(*self.receive_args(doc)).stdout)
        fail = self.cli(*self.receive_args(doc, self.second, 'stale-R2'), code=2)
        self.assertEqual(json.loads(fail.stderr)['status'], 409)
        self.assertEqual(Store(self.db).get(doc['id']), first)

    def test_cumulative_overreceipt_preserves_saved_state(self):
        doc = self.create()
        first = json.loads(self.cli(*self.receive_args(doc)).stdout)
        self.second.write_text(receipt('R2', 6))
        self.cli(*self.receive_args(first, self.second, 'over-R2'), code=2)
        self.assertEqual(Store(self.db).get(doc['id']), first)

    def test_invalid_second_row_rolls_back_whole_batch(self):
        doc = self.create()
        self.first.write_text(receipt() + receipt('BAD', 1, 'MISSING').splitlines()[1] + '\n')
        self.cli(*self.receive_args(doc), code=2)
        self.assertEqual(Store(self.db).get(doc['id']), doc)

    def test_parallel_same_operation_returns_one_identical_result(self):
        doc = self.create()
        args = self.receive_args(doc)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.cli(*args).stdout, range(16)))
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(stock_count(json.loads(results[0])), (6, 3))
        self.assertEqual(Store(self.db).history(doc['id']), [1, 2])

    def test_parallel_distinct_operations_respect_revision_then_compose(self):
        doc = self.create()
        commands = [self.receive_args(doc), self.receive_args(doc, self.second, 'R2')]
        def invoke(args):
            return subprocess.run([sys.executable, '-B', str(ROOT / 'workspace_cli.py'),
                                   '--db', str(self.db), *map(str, args)], capture_output=True, timeout=20)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(invoke, commands))
        self.assertEqual(sorted(r.returncode for r in results), [0, 2])
        failed_index = next(i for i, r in enumerate(results) if r.returncode == 2)
        self.assertEqual(json.loads(results[failed_index].stderr)['status'], 409)
        current = Store(self.db).get(doc['id'])
        args = commands[failed_index]
        args[args.index('--expected-revision') + 1] = current['revision']
        final = json.loads(self.cli(*args).stdout)
        self.assertEqual(stock_count(final), (11, 3))
        self.assertEqual(Store(self.db).history(doc['id']), [1, 2, 3])

    def test_list_history_and_historical_stock_are_shared_snapshots(self):
        doc = self.create()
        self.cli(*self.receive_args(doc))
        self.assertEqual(json.loads(self.cli('list').stdout)[0]['id'], doc['id'])
        self.assertEqual(json.loads(self.cli('history', doc['id']).stdout), [1, 2])
        old = json.loads(self.cli('show', doc['id'], '--revision', 1).stdout)
        self.assertEqual(old, doc)
        self.assertEqual(self.cli('show', doc['id'], '--revision', 1, '--format', 'stock').stdout,
                         doc['updated_stock'].encode())
        log = json.loads(self.cli('show', doc['id'], '--format', 'receipt-log').stdout)
        self.assertEqual(log['count'], 1)

    def test_source_export_preserves_bom_crlf_and_no_added_newline(self):
        raw = b'\xef\xbb\xbf' + STOCK.rstrip('\r\n').encode()
        (self.root / 'stock.csv').write_bytes(raw)
        doc = self.create()
        self.assertEqual(self.cli('source', doc['id'], 'stock').stdout, raw)
        self.assertEqual(self.cli('source', doc['id'], 'stock', '--revision', 1).stdout, raw)

    def test_missing_workspace_does_not_create_database_for_reads_or_receive(self):
        for args in [('list',), ('show', 'none'), ('history', 'none'),
                     ('source', 'none', 'stock'), tuple(self.receive_args({'id': 'none', 'revision': 1}))]:
            with self.subTest(args=args):
                fail = self.cli(*args, code=2)
                self.assertEqual(json.loads(fail.stderr)['status'], 404)
                self.assertFalse(self.db.exists())

    def test_missing_input_and_invalid_utf8_do_not_open_new_database(self):
        (self.root / 'stock.csv').unlink()
        self.cli(*self.create_args(), code=2)
        self.assertFalse(self.db.exists())
        (self.root / 'stock.csv').write_bytes(b'\xff')
        fail = self.cli(*self.create_args(), code=2)
        self.assertEqual(json.loads(fail.stderr)['status'], 400)
        self.assertFalse(self.db.exists())

    def test_oversized_input_is_bounded_before_database_open(self):
        (self.root / 'stock.csv').write_bytes(b'x' * (MAX_CSV + 1))
        self.cli(*self.create_args(), code=2)
        self.assertFalse(self.db.exists())

    def test_bad_revision_is_argument_error_before_mutation(self):
        doc = self.create()
        for value in ['0', '-1', '1.5', 'true']:
            with self.subTest(value=value):
                self.cli(*self.receive_args(doc, revision=value), code=2)
        self.assertEqual(Store(self.db).get(doc['id']), doc)

    def test_store_error_json_and_unknown_historical_revision(self):
        doc = self.create()
        for args in [('show', 'missing'), ('show', doc['id'], '--revision', 99)]:
            fail = self.cli(*args, code=2)
            self.assertEqual(json.loads(fail.stderr)['status'], 404)

    def test_operation_retry_returns_original_response_after_later_receipt(self):
        doc = self.create()
        first = json.loads(self.cli(*self.receive_args(doc)).stdout)
        final = json.loads(self.cli(*self.receive_args(first, self.second, 'R2')).stdout)
        self.assertEqual(json.loads(self.cli(*self.receive_args(doc)).stdout), first)
        self.assertEqual(json.loads(self.cli('show', doc['id']).stdout), final)

    def test_output_failure_reports_possible_commit_and_replay_is_safe(self):
        class FailedOutput(io.StringIO):
            def write(self, value):
                raise OSError('synthetic full output sink')
        args = ['--db', str(self.db), *map(str, self.create_args())]
        error = io.StringIO()
        self.assertEqual(main(args, stdout=FailedOutput(), stderr=error), 3)
        self.assertIn('may already have committed', error.getvalue())
        current = Store(self.db).list()
        self.assertEqual(len(current), 1)
        self.assertEqual(self.create()['id'], current[0]['id'])


if __name__ == '__main__':
    unittest.main()
