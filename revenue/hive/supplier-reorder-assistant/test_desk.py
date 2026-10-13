"""Real SQLite and HTTP coverage for the browser consumer of the landed engine."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

import desk

STOCK = 'sku,name,on_hand,on_order,allocated,unit\nFILTER-A,Filter cartridge,2,3,1,each\nBELT-B,Drive belt,0,0,0,each\n'
RULES = 'sku,reorder_at,target_stock,preferred_supplier\nFILTER-A,5,13,SAMPLE-SUPPLIER\nBELT-B,2,5,SAMPLE-SUPPLIER\n'
CATALOG = ('supplier_id,supplier_sku,sku,description,unit_cost,available_qty,lead_days,alternative_for_sku\n'
           'SAMPLE-SUPPLIER,F-A,FILTER-A,Sample filter,4.25,50,2,\n'
           'SAMPLE-SUPPLIER,B-B,BELT-B,Exact belt unavailable,8.50,0,3,\n'
           'SAMPLE-SUPPLIER,B-ALT,BELT-ALT,Fit requires human review,9.00,10,2,BELT-B\n')
RECEIPT_HEADER = ','.join(desk.RECEIPT_FIELDS) + '\n'


def make_request(operation='create-1'):
    return {'operation_id': operation, 'title': 'Fictional sample', 'inputs': {
        'stock': STOCK, 'rules': RULES, 'catalog': CATALOG,
        'as_of': '2026-09-08', 'currency': 'USD', 'pipeline_includes_draft': False}}


def receipt(receipt_id='R1', qty=4):
    return RECEIPT_HEADER + f'{receipt_id},2026-09-08,SAMPLE-SUPPLIER,F-A,FILTER-A,{qty}\n'


def receiving(operation='recv-1', revision=1, receipt_id='R1', qty=4):
    return {'operation_id': operation, 'expected_revision': revision, 'csv': receipt(receipt_id, qty)}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'saved.sqlite3'
        self.store = desk.Store(self.path)

    def created(self):
        return self.store.create(make_request())

    def test_imports_existing_product_engine(self):
        path = Path(desk.engine.__file__).resolve()
        self.assertEqual(path.name, 'reorder_assistant.py')
        self.assertEqual(path.parent, Path(desk.__file__).resolve().parent)

    def test_plan_uses_exact_engine(self):
        doc = self.created()
        po = doc['plan']['purchase_orders'][0]
        self.assertEqual((po['lines'][0]['quantity'], po['total']), (9, '38.25'))
        self.assertEqual(doc['plan']['summary']['orders_sent'], 0)
        self.assertEqual(doc['plan']['exceptions'][0]['unfilled_qty'], 5)
        self.assertEqual(doc['plan']['exceptions'][0]['action'], 'review_required_no_order_created')
        self.assertEqual(doc['plan']['exceptions'][0]['alternative_suggestions'][0]['supplier_sku'], 'B-ALT')

    def test_non_unicode_request_is_reported_without_save(self):
        req = make_request()
        req['title'] = '\ud800'
        with self.assertRaises(desk.DeskError):
            self.store.create(req)
        self.assertEqual(self.store.list(), [])
        with self.assertRaises(desk.DeskError):
            desk.csv_rows('\ud800', desk.INPUT_FIELDS['stock'], 'stock')

    def test_retains_submitted_source_and_digest(self):
        req = make_request()
        req['inputs']['stock'] = '\ufeff' + STOCK.replace('\n', '\r\n')
        doc = self.store.create(req)
        self.assertEqual(doc['inputs']['stock'], req['inputs']['stock'])
        self.assertEqual(doc['source_sha256']['stock'], desk.digest(req['inputs']['stock']))

    def test_restart_persists_plan(self):
        doc = self.created()
        self.assertEqual(desk.Store(self.path).get(doc['id']), doc)
        self.assertEqual(self.store.list()[0]['id'], doc['id'])

    def test_create_retry_returns_same_plan(self):
        doc = self.created()
        self.assertEqual(self.store.create(make_request()), doc)
        self.assertEqual(len(self.store.list()), 1)

    def test_operation_id_conflict(self):
        self.created()
        req = make_request()
        req['title'] = 'Different change'
        with self.assertRaises(desk.DeskError) as error:
            self.store.create(req)
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(len(self.store.list()), 1)

    def test_receive_and_restart(self):
        doc = self.created()
        applied = self.store.receive(doc['id'], receiving())
        self.assertEqual(applied['revision'], 2)
        self.assertIn('FILTER-A,Filter cartridge,6,3,1,each', applied['updated_stock'])
        self.assertEqual(desk.Store(self.path).get(doc['id']), applied)
        self.assertEqual(applied['inputs']['stock'], STOCK)
        self.assertEqual(applied['plan'], doc['plan'])
        self.assertEqual(applied['receipt_sources'][0]['csv'], receipt())

    def test_receiving_replays_cumulative_once(self):
        doc = self.created()
        self.store.receive(doc['id'], receiving())
        doc = desk.Store(self.path).receive(doc['id'], receiving('recv-2', 2, 'R2', 5))
        self.assertIn('FILTER-A,Filter cartridge,11,3,1,each', doc['updated_stock'])
        self.assertEqual(doc['receipt_log']['count'], 2)
        self.assertEqual(doc['revision'], 3)

    def test_over_receipt_across_sessions_is_atomic(self):
        doc = self.created()
        good = self.store.receive(doc['id'], receiving())
        with self.assertRaises(desk.DeskError):
            desk.Store(self.path).receive(doc['id'], receiving('recv-2', 2, 'R2', 6))
        self.assertEqual(self.store.get(doc['id']), good)
        self.assertEqual(self.store.history(doc['id']), [1, 2])

    def test_receipt_retry_same_operation_returns_original_success(self):
        doc = self.created()
        first = self.store.receive(doc['id'], receiving())
        self.store.receive(doc['id'], receiving('recv-2', 2, 'R2', 2))
        self.assertEqual(self.store.receive(doc['id'], receiving()), first)
        self.assertEqual(self.store.get(doc['id'])['revision'], 3)

    def test_same_receipt_new_operation_is_noop(self):
        doc = self.created()
        first = self.store.receive(doc['id'], receiving())
        self.assertEqual(self.store.receive(doc['id'], receiving('retry-2', 2)), first)
        self.assertEqual(self.store.history(doc['id']), [1, 2])

    def test_conflicting_receipt_id_is_atomic(self):
        doc = self.created()
        good = self.store.receive(doc['id'], receiving())
        with self.assertRaises(desk.DeskError) as error:
            self.store.receive(doc['id'], receiving('bad', 2, 'R1', 3))
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(self.store.get(doc['id']), good)

    def test_failed_batch_retains_all_old_rows(self):
        doc = self.created()
        request = receiving()
        request['csv'] += 'R2,2026-09-08,SAMPLE-SUPPLIER,B-ALT,BELT-B,1\n'
        with self.assertRaises(desk.DeskError):
            self.store.receive(doc['id'], request)
        self.assertEqual(self.store.get(doc['id']), doc)

    def test_stale_revision(self):
        doc = self.created()
        self.store.receive(doc['id'], receiving())
        with self.assertRaises(desk.DeskError) as error:
            self.store.receive(doc['id'], receiving('new', 1, 'R2', 1))
        self.assertEqual(error.exception.status, 409)

    def test_concurrent_save_only_one_revision_wins(self):
        doc = self.created()
        def receive(i):
            try:
                return self.store.receive(doc['id'], receiving(f'op-{i}', 1, f'R{i}', 1))['revision']
            except desk.DeskError as error:
                return error.status
        with ThreadPoolExecutor(2) as pool:
            result = list(pool.map(receive, [1, 2]))
        self.assertEqual(sorted(result), [2, 409])
        self.assertEqual(self.store.get(doc['id'])['receipt_log']['count'], 1)

    def test_pipeline_flag_is_consumed(self):
        req = make_request()
        req['inputs']['pipeline_includes_draft'] = True
        doc = self.store.create(req)
        doc = self.store.receive(doc['id'], receiving(qty=2))
        self.assertIn('FILTER-A,Filter cartridge,4,1,1,each', doc['updated_stock'])

    def test_history_keeps_original(self):
        doc = self.created()
        self.store.receive(doc['id'], receiving())
        self.assertEqual(self.store.get(doc['id'], 1), doc)
        self.assertEqual(self.store.history(doc['id']), [1, 2])

    def test_separate_plans_and_receipt_ids(self):
        first = self.created()
        second = self.store.create(make_request('second'))
        self.store.receive(first['id'], receiving())
        self.assertEqual(self.store.get(second['id']), second)
        self.store.receive(second['id'], receiving('second-receipt'))
        self.assertEqual(len(self.store.list()), 2)

    def test_bad_csv_width_and_headers(self):
        values = ['sku,sku\nx,x\n', STOCK+'x,y\n', STOCK+'x,y,1,1,1,each,extra\n', STOCK+'"unclosed\n']
        for value in values:
            with self.subTest(value=value), self.assertRaises(desk.DeskError):
                req = make_request(value[:10])
                req['inputs']['stock'] = value
                self.store.create(req)
        self.assertEqual(self.store.list(), [])

    def test_missing_and_invalid_inputs(self):
        for field, value in [('stock', None), ('rules', 1), ('catalog', ''), ('as_of', '2026-99-99'),
                             ('currency', '$'), ('pipeline_includes_draft', 'false')]:
            with self.subTest(field=field), self.assertRaises(desk.DeskError):
                req = make_request(field)
                req['inputs'][field] = value
                self.store.create(req)

    def test_nonfinite_numbers_not_saved(self):
        for value in ['NaN', 'Infinity', '-1', '1.5']:
            with self.subTest(value=value), self.assertRaises(desk.DeskError):
                req = make_request(value)
                req['inputs']['stock'] = STOCK.replace(',2,3,1,', f',{value},3,1,')
                self.store.create(req)

    def test_empty_and_duplicate_receipt_upload(self):
        doc = self.created()
        for value in [RECEIPT_HEADER, receipt()+receipt().split('\n')[1]+'\n']:
            with self.subTest(value=value), self.assertRaises(desk.DeskError):
                request = receiving(value[:10])
                request['csv'] = value
                self.store.receive(doc['id'], request)

    def test_utf8_size_limits(self):
        with self.assertRaises(desk.DeskError):
            desk.csv_rows('é' * (desk.MAX_CSV // 2 + 1), [], 'large')

    def test_missing_plan(self):
        with self.assertRaises(desk.DeskError) as error:
            self.store.get('absent')
        self.assertEqual(error.exception.status, 404)


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.store = desk.Store(Path(cls.temp.name) / 'db.sqlite3')
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), desk.handler(cls.store))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'
        cls.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def request(self, path, body=None, raw=None, content_type='application/json'):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        request = urllib.request.Request(self.url + path, data=data, headers={'Content-Type': content_type})
        try:
            response = self.opener.open(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read()

    def test_real_full_http_workflow(self):
        status, _, body = self.request('/api/runs', make_request('http-create'))
        self.assertEqual(status, 200)
        doc = json.loads(body)
        base = '/api/runs/' + doc['id']
        status, _, body = self.request(base + '/receipts', receiving('http-recv'))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['revision'], 2)
        status, headers, body = self.request(base + '/source/stock')
        self.assertEqual(status, 200)
        self.assertEqual(body, STOCK.encode())
        self.assertIn('attachment', headers['Content-Disposition'])
        self.assertEqual(headers['Cache-Control'], 'no-store')
        status, _, body = self.request(base + '/updated-stock.csv')
        self.assertIn(b'FILTER-A,Filter cartridge,6,3,1,each', body)
        self.assertEqual(self.request(base+'/history')[2], b'[1,2]')
        original = json.loads(self.request(base + '/history/1')[2])
        self.assertEqual(original['receipt_log']['count'], 0)
        exported = json.loads(self.request(base + '/export.json')[2])
        self.assertEqual(exported['receipt_log']['count'], 1)
        self.assertEqual(self.request(base + '/receipts', receiving('http-stale'))[0], 409)

    def test_serves_real_browser(self):
        status, headers, body = self.request('/')
        self.assertEqual(status, 200)
        self.assertTrue(headers['Content-Type'].startswith('text/html'))
        self.assertIn(b'Supplier reorder desk', body)
        self.assertIn(b"'/api/runs'", body)

    def test_invalid_json_reports_error(self):
        for raw in [b'{', b'NaN', b'[]', b'{"title":"x"}']:
            with self.subTest(raw=raw):
                self.assertEqual(self.request('/api/runs', raw=raw)[0], 400)

    def test_non_unicode_http_reports_json_error(self):
        req = make_request('http-unicode')
        req['title'] = '\ud800'
        status, headers, raw = self.request('/api/runs', req)
        self.assertEqual(status, 400)
        self.assertIn('Unicode', json.loads(raw)['error'])
        self.assertTrue(headers['Content-Type'].startswith('application/json'))

    def test_content_type_and_missing_route(self):
        self.assertEqual(self.request('/api/runs', raw=b'{}', content_type='text/plain')[0], 415)
        self.assertEqual(self.request('/api/not-a-route')[0], 404)
        self.assertEqual(self.request('/api/runs/missing')[0], 404)


if __name__ == '__main__':
    unittest.main()
