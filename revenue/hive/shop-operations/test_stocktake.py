"""Physical stock reconciliation against real SQLite, threads, HTTP and CLI."""
from concurrent.futures import ThreadPoolExecutor
import csv
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from shop_ops import DomainError, Store, server_for
from test_shop_ops import product


class StocktakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'counts.sqlite3'
        self.store = Store(self.path)
        self.seq = 0
        self.command('product', product())
        self.command('receive', dict(sku='BAG-01', quantity=10, reference='fixture-delivery'))

    def command(self, action, data, key=None):
        self.seq += 1
        return self.store.execute(dict(key=key or f'count-op-{self.seq}', action=action, data=data))

    def count(self, quantity=8, **changes):
        p = self.store.snapshot()['products'][0]
        return dict(dict(sku=p['sku'], version=p['version'], quantity=quantity,
                         reference=f'count-{self.seq}', note='Synthetic shelf count'), **changes)

    def reserve(self, quantity=3, oid='fixture-order'):
        return self.command('order', dict(id=oid, recipient_ref='fixture',
                            lines=[dict(sku='BAG-01', quantity=quantity)]))

    def test_decrease_count_preserves_reservations_and_original_records(self):
        self.reserve()
        before = self.store.snapshot()
        result = self.command('stocktake', self.count(8))
        state = self.store.snapshot()
        self.assertEqual((result['prior_on_hand'], result['on_hand'], result['delta']), (10, 8, -2))
        self.assertEqual((result['reserved'], result['available']), (3, 5))
        for table in ('orders', 'lines', 'receipts', 'returns', 'return_lines'):
            self.assertEqual(before[table], state[table])
        self.assertEqual(state['stocktakes'][0]['version_before'], 3)
        self.assertEqual(state['stocktakes'][0]['note'], 'Synthetic shelf count')
        self.assertEqual(state['movements'][-1]['reason'], 'stocktake')
        self.assertEqual(sum(m['on_hand_delta'] for m in state['movements']), 8)
        self.assertEqual(sum(m['reserved_delta'] for m in state['movements']), 3)

    def test_increase_and_zero_delta_counts_remain_auditable(self):
        first = self.command('stocktake', self.count(14, reference='more'))
        second = self.command('stocktake', self.count(14, reference='same'))
        state = self.store.snapshot()
        self.assertEqual((first['delta'], second['delta']), (4, 0))
        self.assertEqual(second['version'], first['version']+1)
        self.assertEqual(len(state['stocktakes']), 2)
        self.assertEqual(state['movements'][-1]['on_hand_delta'], 0)
        self.assertEqual(sum(m['on_hand_delta'] for m in state['movements']), 14)

    def test_empty_shelf_count_is_valid_without_reservations(self):
        result = self.command('stocktake', self.count(0))
        self.assertEqual((result['on_hand'], result['available'], result['delta']), (0, 0, -10))
        with self.assertRaises(DomainError):
            self.reserve(1)

    def test_below_reserved_conflict_changes_nothing(self):
        self.reserve(7)
        before = self.store.snapshot()
        with self.assertRaisesRegex(DomainError, 'below 7 reserved') as ctx:
            self.command('stocktake', self.count(6))
        self.assertEqual(ctx.exception.status, 409)
        self.assertEqual(before, self.store.snapshot())
        # Resolve the actual allocation explicitly, then capture a fresh version.
        self.command('cancel', dict(id='fixture-order'))
        result = self.command('stocktake', self.count(6))
        self.assertEqual((result['on_hand'], result['reserved']), (6, 0))

    def test_exactly_reserved_count_keeps_zero_available(self):
        self.reserve(4)
        result = self.command('stocktake', self.count(4))
        self.assertEqual(result['available'], 0)
        self.command('fulfill', dict(id='fixture-order', shipment_ref='fixture-handoff'))
        p = self.store.snapshot()['products'][0]
        self.assertEqual((p['on_hand'], p['reserved']), (0, 0))

    def test_stale_count_never_overwrites_a_new_receipt(self):
        observation = self.count()
        self.command('receive', dict(sku='BAG-01', quantity=5, reference='new-fixture-delivery'))
        before = self.store.snapshot()
        with self.assertRaisesRegex(DomainError, 'Stale stock count'):
            self.command('stocktake', observation)
        self.assertEqual(before, self.store.snapshot())
        self.assertEqual(before['products'][0]['on_hand'], 15)

    def test_metadata_edit_invalidates_old_count_version(self):
        observation = self.count()
        self.command('product', product(version=2, title='Changed synthetic title'))
        with self.assertRaisesRegex(DomainError, 'Stale stock count'):
            self.command('stocktake', observation)
        self.assertEqual(self.store.snapshot()['stocktakes'], [])

    def test_exact_retry_survives_restart_and_later_fulfillment(self):
        observation = self.count(8)
        request = dict(key='durable-count', action='stocktake', data=observation)
        first = self.store.execute(request)
        self.reserve(2)
        self.command('fulfill', dict(id='fixture-order', shipment_ref='fixture-handoff'))
        reopened = Store(self.path)
        self.assertEqual(reopened.execute(request), first)
        state = reopened.snapshot()
        self.assertEqual(state['products'][0]['on_hand'], 6)
        self.assertEqual(len(state['stocktakes']), 1)

    def test_new_key_cannot_reuse_same_count_reference(self):
        self.command('stocktake', self.count(8, reference='count-once'))
        before = self.store.snapshot()
        with self.assertRaises(DomainError):
            self.command('stocktake', self.count(9, reference='count-once'))
        self.assertEqual(before, self.store.snapshot())

    def test_invalid_fields_and_unknown_sku_do_not_write(self):
        before = self.store.snapshot()
        bad = ([dict(quantity=v) for v in (True, 1.0, -1, None, '2', 1_000_000_001)] +
               [dict(version=v) for v in (False, 0, '2', None, 2.0)] +
               [dict(reference=''), dict(note=None), dict(sku='MISSING')])
        for changes in bad:
            with self.subTest(changes=changes), self.assertRaises(DomainError):
                self.command('stocktake', self.count(**changes))
        self.assertEqual(before, self.store.snapshot())

    def seed_second(self):
        self.command('product', product('OTHER'))
        self.command('receive', dict(sku='OTHER', quantity=5, reference='fixture-other-delivery'))
        return dict(sku='OTHER', version=2, quantity=3, reference='batch-count')

    def test_multisku_batch_commits_and_replays_as_one_operation(self):
        other = self.seed_second()
        counts = [self.count(8, reference='batch-count'), other]
        request = dict(key='count-batch', action='stocktake_batch', data={'counts':counts})
        result = self.store.execute(request)
        self.assertEqual(Store(self.path).execute(request), result)
        self.assertEqual([p['on_hand'] for p in self.store.snapshot()['products']], [8, 3])
        self.assertEqual(len(self.store.snapshot()['stocktakes']), 2)
        self.assertEqual([r['delta'] for r in result['counts']], [-2, -2])

    def test_later_batch_failure_rolls_back_earlier_count_and_audit(self):
        other = self.seed_second()
        before = self.store.snapshot()
        other['version'] = 1
        with self.assertRaises(DomainError):
            self.command('stocktake_batch', {'counts':[self.count(8), other]}, key='retry-batch')
        self.assertEqual(before, self.store.snapshot())
        other['version'] = 2
        # Failed operations do not claim a durable key; correction can proceed.
        self.command('stocktake_batch', {'counts':[self.count(8), other]}, key='retry-batch')
        self.assertEqual(len(self.store.snapshot()['stocktakes']), 2)

    def test_bad_batches_and_normalized_duplicate_skus_are_atomic(self):
        c = self.count()
        before = self.store.snapshot()
        for counts in (None, [], {}, [c, None], [c, dict(c, sku=' BAG-01 ')]):
            with self.subTest(counts=counts), self.assertRaises(DomainError):
                self.command('stocktake_batch', {'counts':counts})
        self.assertEqual(before, self.store.snapshot())

    def test_concurrent_same_version_counts_have_one_winner(self):
        observation = self.count(8)
        barrier = threading.Barrier(10)
        def count(i):
            barrier.wait()
            try:
                return self.store.execute(dict(key=f'race-count-{i}', action='stocktake',
                    data=dict(observation, reference=f'race-count-{i}')))
            except DomainError as error:
                return error.status
        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(count, range(10)))
        self.assertEqual(sum(isinstance(r, dict) for r in results), 1)
        self.assertEqual(results.count(409), 9)
        self.assertEqual(len(self.store.snapshot()['stocktakes']), 1)
        self.assertEqual(self.store.snapshot()['products'][0]['on_hand'], 8)

    def test_concurrent_identical_count_retries_return_one_original_result(self):
        request = dict(key='retry-count', action='stocktake', data=self.count(8))
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _:self.store.execute(request), range(24)))
        self.assertTrue(all(r == results[0] for r in results))
        self.assertEqual(len(self.store.snapshot()['stocktakes']), 1)
        self.assertEqual(len(self.store.snapshot()['movements']), 2)

    def test_count_order_race_never_erases_a_committed_allocation(self):
        observation = self.count(0)
        barrier = threading.Barrier(2)
        def send(request):
            barrier.wait()
            try:
                return self.store.execute(request)
            except DomainError as error:
                return error.status
        requests = [dict(key='race-zero',action='stocktake',data=observation),
                    dict(key='race-order',action='order',data=dict(id='race-order',recipient_ref='fixture',
                         lines=[dict(sku='BAG-01',quantity=1)]))]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(send, requests))
        self.assertEqual(sum(isinstance(r, dict) for r in results), 1)
        self.assertEqual(results.count(409), 1)
        state = self.store.snapshot()
        p = state['products'][0]
        self.assertIn((p['on_hand'],p['reserved']), ((0,0),(10,1)))
        self.assertEqual(sum(m['on_hand_delta'] for m in state['movements']),p['on_hand'])
        self.assertEqual(sum(m['reserved_delta'] for m in state['movements']),p['reserved'])

    def test_additive_schema_upgrade_preserves_existing_data_and_retry_history(self):
        # Remove only the newly added empty table to recreate the exact v1 table set.
        request = dict(key='legacy-reserve',action='order',data=dict(id='legacy',recipient_ref='fixture',
                       lines=[dict(sku='BAG-01',quantity=2)]))
        original_result = self.store.execute(request)
        before = self.store.snapshot()
        with self.store.connection() as db:
            db.execute('DROP TABLE stocktakes')
        reopened = Store(self.path)
        self.assertEqual(reopened.snapshot(),before)
        self.assertEqual(reopened.execute(request),original_result)
        self.command('stocktake',self.count(8))
        with self.store.connection() as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_audit_csv_keeps_headers_and_protects_text_without_altering_json(self):
        self.assertIn('reference,sku,quantity,prior_on_hand,version_before,note,created_at',
                      self.store.export_csv('stocktakes'))
        self.command('stocktake',self.count(8,reference='=FIXTURE()',note='@fixture'))
        row = list(csv.DictReader(io.StringIO(self.store.export_csv('stocktakes'))))[0]
        self.assertEqual(row['reference'],"'=FIXTURE()")
        self.assertEqual(row['note'],"'@fixture")
        self.assertEqual(self.store.snapshot()['stocktakes'][0]['reference'],'=FIXTURE()')

    def test_real_http_count_batch_and_export(self):
        other = self.seed_second()
        server = server_for(self.store,port=0)
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        url=f'http://127.0.0.1:{server.server_port}'
        try:
            request = dict(key='http-count',action='stocktake_batch',data={'counts':[self.count(8),other]})
            with urlopen(Request(url+'/api/command',data=json.dumps(request).encode(),
                         headers={'Content-Type':'application/json'}),timeout=5) as response:
                result=json.load(response)
            self.assertEqual(len(result['counts']),2)
            with urlopen(url+'/export/stocktakes.csv',timeout=5) as response:
                rows=list(csv.DictReader(io.StringIO(response.read().decode())))
            self.assertEqual(len(rows),2)
            request['key']='http-stale'
            try:
                urlopen(Request(url+'/api/command',data=json.dumps(request).encode()),timeout=5)
                self.fail('Stale HTTP request unexpectedly succeeded')
            except HTTPError as error:
                with error:
                    self.assertEqual(error.code,409)
                    self.assertIn('Stale stock count',json.load(error)['error'])
        finally:
            server.shutdown();server.server_close();thread.join(5)

    def test_real_cli_count_and_snapshot_survive_reopen(self):
        command=Path(self.tmp.name)/'count.json'
        command.write_text(json.dumps(dict(key='cli-count',action='stocktake',data=self.count(8))))
        base=[sys.executable,'-B',str(Path(__file__).with_name('shop_ops.py')),'--db',str(self.path)]
        applied=subprocess.run(base+['apply',str(command)],capture_output=True,text=True,timeout=10)
        self.assertEqual(applied.returncode,0,applied.stderr)
        self.assertEqual(json.loads(applied.stdout)['on_hand'],8)
        exported=subprocess.run(base+['export'],capture_output=True,text=True,timeout=10)
        self.assertEqual(exported.returncode,0,exported.stderr)
        self.assertEqual(json.loads(exported.stdout)['stocktakes'][0]['quantity'],8)


if __name__ == '__main__':
    unittest.main(verbosity=2)
