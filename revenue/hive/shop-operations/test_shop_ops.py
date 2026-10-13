"""File-backed transaction, HTTP and CLI tests; all merchant data is synthetic."""
from concurrent.futures import ThreadPoolExecutor
import copy
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


def product(sku='BAG-01', **changes):
    data = dict(sku=sku, version=0, title='Synthetic canvas bag',
                description='Fixture only: canvas bag with one pocket.',
                source_url='https://example.invalid/synthetic/bag', uncertainties='',
                price_minor=2400, currency='USD', listing_state='ready')
    return dict(data, **changes)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / 'shop.sqlite3'
        self.store = Store(self.db_path)
        self.seq = 0

    def command(self, action, data, key=None):
        self.seq += 1
        return self.store.execute(dict(action=action, data=data, key=key or f'cmd-{self.seq}'))

    def seed(self, qty=10):
        self.command('product', product())
        self.command('receive', dict(sku='BAG-01', quantity=qty, reference='fixture-delivery'))

    def reserve(self, qty=2, oid='order-1', kind='sale', key=None):
        return self.command('order', dict(id=oid, kind=kind, recipient_ref='fixture-recipient',
                            lines=[dict(sku='BAG-01', quantity=qty)]), key)

    def fulfill(self, oid='order-1'):
        return self.command('fulfill', dict(id=oid, shipment_ref='fixture-handoff'))

    def returned(self, qty=1, restock=True, rid='return-1', key=None):
        return self.command('return', dict(id=rid, order_id='order-1', sku='BAG-01',
                            quantity=qty, restock=restock, note='Synthetic inspection'), key)

    def assert_stock(self, hand, reserved):
        row = self.store.snapshot()['products'][0]
        self.assertEqual((row['on_hand'], row['reserved'], row['available']),
                         (hand, reserved, hand-reserved))

    def test_complete_listing_order_partial_return_and_sample_workflow(self):
        self.seed()
        self.reserve(4)
        self.assert_stock(10, 4)
        self.fulfill()
        self.assert_stock(6, 0)
        self.returned(2)
        self.returned(1, restock=False, rid='damaged-1')
        self.assert_stock(8, 0)
        self.reserve(1, 'sample-1', 'sample')
        self.fulfill('sample-1')
        self.assert_stock(7, 0)
        state = Store(self.db_path).snapshot()
        self.assertEqual(state['products'][0]['listing_state'], 'ready')
        self.assertEqual(state['orders'][1]['kind'], 'sample')
        self.assertEqual(sum(m['on_hand_delta'] for m in state['movements']), 7)
        self.assertEqual(sum(m['reserved_delta'] for m in state['movements']), 0)
        self.assertEqual(state['lines'][0]['price_minor'], 2400)

    def test_replay_after_restart_returns_exact_original_result(self):
        self.seed()
        request = dict(key='persistent-key', action='order', data=dict(id='o', kind='sale',
                       recipient_ref='fixture', lines=[dict(sku='BAG-01', quantity=4)]))
        result = self.store.execute(request)
        self.assertEqual(result, Store(self.db_path).execute(request))
        self.assert_stock(10, 4)
        self.assertEqual(len(self.store.snapshot()['orders']), 1)

    def test_key_reuse_for_different_request_conflicts(self):
        self.command('product', product(), 'same')
        before = self.store.snapshot()
        with self.assertRaisesRegex(DomainError, 'different input'):
            self.command('product', product('OTHER'), 'same')
        self.assertEqual(before, self.store.snapshot())

    def test_duplicate_receipt_reference_does_not_double_stock(self):
        self.seed()
        with self.assertRaises(DomainError):
            self.command('receive', dict(sku='BAG-01', quantity=10, reference='fixture-delivery'))
        self.assert_stock(10, 0)

    def test_bad_quantities_are_rejected_without_writes(self):
        self.seed()
        before = self.store.snapshot()
        for value in (True, False, 1.0, -1, 0, '2', None, 1_000_000_001):
            with self.subTest(value=value), self.assertRaises(DomainError):
                self.command('receive', dict(sku='BAG-01', quantity=value, reference='bad'))
        self.assertEqual(before, self.store.snapshot())

    def test_atomic_multiline_order_rolls_back_all_lines(self):
        self.seed()
        self.command('product', product('EMPTY'))
        before = self.store.snapshot()
        with self.assertRaises(DomainError):
            self.command('order', dict(id='atomic', recipient_ref='fixture', lines=[
                dict(sku='BAG-01', quantity=3), dict(sku='EMPTY', quantity=1)]))
        self.assertEqual(before, self.store.snapshot())

    def test_duplicate_order_lines_are_merged_once(self):
        self.seed()
        self.command('order', dict(id='o', recipient_ref='fixture', lines=[
            dict(sku='BAG-01', quantity=2), dict(sku='BAG-01', quantity=3)]))
        self.assert_stock(10, 5)
        self.assertEqual(len(self.store.snapshot()['lines']), 1)

    def test_cancel_releases_stock_and_repeat_has_no_effect(self):
        self.seed()
        self.reserve()
        self.command('cancel', dict(id='order-1'))
        self.command('cancel', dict(id='order-1'))
        self.assert_stock(10, 0)
        self.assertEqual(len(self.store.snapshot()['movements']), 3)
        with self.assertRaises(DomainError):
            self.fulfill()

    def test_fulfill_requires_reference_and_cannot_double_ship(self):
        self.seed()
        self.reserve()
        with self.assertRaises(DomainError):
            self.command('fulfill', dict(id='order-1'))
        self.assert_stock(10, 2)
        first = self.fulfill()
        self.assertEqual(first.get('shipment_ref'), 'fixture-handoff')
        second = self.fulfill()
        self.assertEqual(second['status'], 'fulfilled')
        self.assertEqual(second['shipment_ref'], 'fixture-handoff')
        self.assert_stock(8, 0)
        with self.assertRaises(DomainError):
            self.command('cancel', dict(id='order-1'))

    def test_fulfill_fresh_key_exact_reference_replays_without_movement(self):
        self.seed()
        self.reserve()
        self.fulfill()
        before = self.store.snapshot()
        again = self.command('fulfill', dict(id='order-1', shipment_ref='fixture-handoff'), key='fresh-exact')
        self.assertEqual(again['status'], 'fulfilled')
        self.assertEqual(again['shipment_ref'], 'fixture-handoff')
        self.assertEqual(before, self.store.snapshot())

    def test_fulfill_fresh_key_changed_reference_conflicts(self):
        self.seed()
        self.reserve()
        self.fulfill()
        before = self.store.snapshot()
        with self.assertRaisesRegex(DomainError, 'does not match'):
            self.command('fulfill', dict(id='order-1', shipment_ref='different-handoff'), key='fresh-changed')
        self.assertEqual(before, self.store.snapshot())

    def test_fulfill_fresh_key_blank_reference_rejected(self):
        self.seed()
        self.reserve()
        self.fulfill()
        before = self.store.snapshot()
        with self.assertRaises(DomainError):
            self.command('fulfill', dict(id='order-1'), key='fresh-blank')
        with self.assertRaises(DomainError):
            self.command('fulfill', dict(id='order-1', shipment_ref=''), key='fresh-blank2')
        with self.assertRaises(DomainError):
            self.command('fulfill', dict(id='order-1', shipment_ref='   '), key='fresh-blank3')
        self.assertEqual(before, self.store.snapshot())

    def test_return_requires_fulfilled_line_and_explicit_inspection(self):
        self.seed()
        self.reserve()
        with self.assertRaises(DomainError):
            self.returned()
        self.fulfill()
        for value in (None, 'true', 1, 0):
            with self.subTest(value=value), self.assertRaises(DomainError):
                self.returned(restock=value)
        self.assert_stock(8, 0)

    def test_return_quantity_accumulates_and_replay_is_exact(self):
        self.seed()
        self.reserve(3)
        self.fulfill()
        first = self.returned(2, key='return-key')
        self.assertEqual(first, self.returned(2, key='return-key'))
        with self.assertRaises(DomainError):
            self.returned(2, rid='too-many')
        self.returned(1, False, 'last-one')
        self.assert_stock(9, 0)
        self.assertEqual(len(self.store.snapshot()['returns']), 2)

    def test_duplicate_return_identifier_rolls_back(self):
        self.seed()
        self.reserve(3)
        self.fulfill()
        self.returned()
        before = self.store.snapshot()
        with self.assertRaises(DomainError):
            self.returned()
        self.assertEqual(before, self.store.snapshot())

    def test_catalog_import_is_atomic_and_versions_preserve_stock(self):
        self.seed()
        p = product(title='Updated', version=2)
        self.command('catalog', dict(products=[p, product('SECOND')]))
        self.assert_stock(10, 0)
        before = self.store.snapshot()
        with self.assertRaisesRegex(DomainError, 'Stale'):
            self.command('catalog', dict(products=[product('THIRD'), p]))
        self.assertEqual(before, self.store.snapshot())

    def test_duplicate_catalog_rows_rejected(self):
        with self.assertRaises(DomainError):
            self.command('catalog', dict(products=[product(), product()]))
        self.assertEqual(self.store.snapshot()['products'], [])

    def test_uncertain_attributes_remain_draft(self):
        self.command('product', product(uncertainties='Size unknown', listing_state='draft'))
        before = self.store.snapshot()
        for state in ('ready', 'listed'):
            with self.assertRaises(DomainError):
                self.command('product', product(version=1, listing_state=state, uncertainties='Size unknown'))
        self.assertEqual(before, self.store.snapshot())

    def test_source_and_currency_validation(self):
        for url in ('javascript:alert(1)', 'data:text/html,test', 'https://', 'https://u:p@example.invalid', 'http://['):
            with self.subTest(url=url), self.assertRaises(DomainError):
                self.command('product', product(source_url=url))
        with self.assertRaises(DomainError):
            self.command('product', product(currency='US'))
        self.assertEqual(self.store.snapshot()['products'], [])

    def test_price_snapshot_survives_catalog_edit(self):
        self.seed()
        self.reserve()
        version = self.store.snapshot()['products'][0]['version']
        self.command('product', product(version=version, price_minor=3000))
        self.assertEqual(self.store.snapshot()['lines'][0]['price_minor'], 2400)

    def test_malformed_json_shapes_and_nonfinite_values(self):
        for request in (None, [], {}, dict(key='x', action='product', data=[]),
                        dict(key='x', action='product', data={'ignored':float('nan')}),
                        dict(key='x', action='product', data={'ignored':'\ud800'})):
            with self.subTest(request=repr(request)), self.assertRaises(DomainError):
                self.store.execute(request)
        self.assertEqual(self.store.snapshot()['products'], [])

    def test_concurrent_stock_reservations_never_oversell(self):
        self.seed(5)
        barrier = threading.Barrier(12)
        def reserve(i):
            barrier.wait()
            try:
                return self.store.execute(dict(key=f'race-{i}', action='order', data=dict(
                    id=f'o-{i}', recipient_ref='fixture', lines=[dict(sku='BAG-01', quantity=1)])))
            except DomainError as exc:
                return exc.status
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(reserve, range(12)))
        self.assertEqual(sum(isinstance(r, dict) for r in results), 5)
        self.assertEqual(results.count(409), 7)
        self.assert_stock(5, 5)

    def test_concurrent_identical_delivery_counts_once(self):
        self.command('product', product())
        request = dict(key='one-delivery', action='receive', data=dict(sku='BAG-01', quantity=7, reference='delivery'))
        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(lambda _: self.store.execute(request), range(20)))
        self.assertTrue(all(r == results[0] for r in results))
        self.assert_stock(7, 0)
        self.assertEqual(len(self.store.snapshot()['movements']), 1)

    def test_concurrent_returns_cannot_exceed_fulfilled_stock(self):
        self.seed(5)
        self.reserve(3)
        self.fulfill()
        def attempt(i):
            try:
                return self.store.execute(dict(key=f'back-{i}', action='return', data=dict(
                    id=f'back-{i}', order_id='order-1', sku='BAG-01', quantity=1, restock=True)))
            except DomainError as exc:
                return exc.status
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(8)))
        self.assertEqual(sum(isinstance(r, dict) for r in results), 3)
        self.assert_stock(5, 0)

    def test_csv_protects_formula_text_and_keeps_raw_json(self):
        self.command('product', product(title='=SYNTHETIC()'))
        csv_row = list(csv.DictReader(io.StringIO(self.store.export_csv('products'))))[0]
        self.assertEqual(csv_row['title'], "'=SYNTHETIC()")
        self.assertEqual(self.store.snapshot()['products'][0]['title'], '=SYNTHETIC()')
        self.assertIn('id,kind,recipient_ref', self.store.export_csv('orders'))

    def test_database_integrity_and_no_mutation_of_request(self):
        request = dict(key='p', action='product', data=product())
        before = copy.deepcopy(request)
        self.store.execute(request)
        self.assertEqual(request, before)
        with self.store.connection() as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_cli_apply_export_and_failed_command(self):
        path = Path(self.tmp.name) / 'command.json'
        path.write_text(json.dumps(dict(key='cli', action='product', data=product())))
        script = str(Path(__file__).with_name('shop_ops.py'))
        base = [sys.executable, '-B', script, '--db', str(self.db_path)]
        applied = subprocess.run(base+['apply', str(path)], capture_output=True, text=True, timeout=10)
        self.assertEqual(applied.returncode, 0, applied.stderr)
        exported = subprocess.run(base+['export'], capture_output=True, text=True, timeout=10)
        self.assertEqual(json.loads(exported.stdout)['products'][0]['sku'], 'BAG-01')
        path.write_text('{}')
        failed = subprocess.run(base+['apply', str(path)], capture_output=True, text=True, timeout=10)
        self.assertEqual(failed.returncode, 2)
        self.assertNotIn('Traceback', failed.stderr)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name)/'web.sqlite3')
        self.server = server_for(self.store, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.tmp.cleanup()

    def request(self, path, data=None, raw=None):
        payload = raw if raw is not None else json.dumps(data).encode() if data is not None else None
        req = Request(self.url+path, data=payload, headers={'Content-Type':'application/json'})
        try:
            with urlopen(req, timeout=5) as response:
                return response.status, response.read(), response.headers
        except HTTPError as error:
            with error:
                return error.code, error.read(), error.headers

    def test_actual_http_create_replay_export_and_page(self):
        command = dict(key='web-product', action='product', data=product())
        status, body, headers = self.request('/api/command', command)
        self.assertEqual(status, 200)
        self.assertEqual(body, self.request('/api/command', command)[1])
        page = self.request('/')[1].decode()
        self.assertIn('Shop Operations Desk', page)
        self.assertIn('id="order-form"', page)
        self.assertEqual(json.loads(self.request('/api/state')[1])['products'][0]['sku'], 'BAG-01')
        self.assertIn(b'BAG-01', self.request('/export/products.csv')[1])
        self.assertEqual(headers['Cache-Control'], 'no-store')

    def test_actual_http_errors_are_json_and_do_not_mutate(self):
        for raw in (b'{bad', b'[]', b'{"key":"x","action":"product","data":{"bad":NaN}}', b'\xff'):
            status, body, _ = self.request('/api/command', raw=raw)
            self.assertEqual(status, 400)
            self.assertIn('error', json.loads(body))
        self.assertEqual(self.request('/no-such-route')[0], 404)
        self.assertEqual(self.request('/export/no-such-table.csv')[0], 404)
        self.assertEqual(self.store.snapshot()['products'], [])

    def test_actual_http_conflict_preserves_prior_operation(self):
        command = dict(key='web-product', action='product', data=product())
        self.request('/api/command', command)
        command['data']['title'] = 'Different'
        status, body, _ = self.request('/api/command', command)
        self.assertEqual(status, 409)
        self.assertIn('different input', json.loads(body)['error'])
        self.assertEqual(len(self.store.snapshot()['products']), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
