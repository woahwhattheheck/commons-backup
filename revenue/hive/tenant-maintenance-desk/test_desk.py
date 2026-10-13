"""Real SQLite and HTTP regressions. Run: python -m unittest -v test_desk.py"""
from __future__ import annotations
import base64
import concurrent.futures
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from desk import DeskError, Store
from server import MAX_BODY, make_server, strict_json

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aVqkAAAAASUVORK5CYII=')
START, END = '2026-10-01T14:00:00Z', '2026-10-01T15:00:00Z'


class DeskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'records.sqlite'
        self.store = Store(self.path)
        self.prop = self.call(type='property', name='Fictional Court', faq='Repairs use this desk.')['id']
        self.a = self.call(type='vendor', name='Repair A', trade='General')['id']
        self.b = self.call(type='vendor', name='Repair B', trade='Plumbing')['id']

    def call(self, **data):
        return self.store.command(data)

    def request(self, **extra):
        return self.call(**dict({'type': 'request', 'property_id': self.prop, 'unit': '2B',
                                 'description': 'Dripping tap', 'urgency': 'routine'}, **extra))

    def schedule(self, req, **extra):
        return self.call(**dict({'type': 'schedule', 'request_id': req['id'], 'version': req['version'],
                                 'vendor_id': self.a, 'start': START, 'end': END}, **extra))

    def current(self, req):
        return next(r for r in self.store.state()['requests'] if r['id'] == req['id'])

    def test_complete_replacement_and_closure_survive_restart(self):
        req = self.schedule(self.request())
        self.assertEqual(req['appointment']['vendor_name'], 'Repair A')
        result = self.call(type='vendor_availability', vendor_id=self.a, available=False)
        self.assertEqual(result['affected_requests'], [req['id']])
        req = self.current(req)
        self.assertEqual(req['status'], 'needs_reschedule')
        self.assertIsNone(req['appointment'])
        req = self.schedule(req, vendor_id=self.b)
        self.assertEqual(req['appointment']['vendor_name'], 'Repair B')
        req = self.call(type='close', request_id=req['id'], version=req['version'], closure='Washer replaced.')
        self.store = Store(self.path)
        saved = self.current(req)
        self.assertEqual(saved['closure'], 'Washer replaced.')
        self.assertEqual(saved['status'], 'closed')
        self.assertIsNone(saved['appointment'])
        self.assertEqual([a['state'] for a in saved['appointments']], ['cancelled', 'completed'])
        self.assertEqual(len(saved['events']), 5)

    def test_retry_returns_same_record_even_after_restart(self):
        data = {'type': 'request', 'property_id': self.prop, 'unit': '3A', 'description': 'Door sticks'}
        first = self.store.command(data, 'repeat')
        self.store = Store(self.path)
        self.assertEqual(first, self.store.command(data, 'repeat'))
        self.assertEqual(len(self.store.state()['requests']), 1)

    def test_changed_payload_cannot_reuse_operation(self):
        self.store.command({'type': 'vendor', 'name': 'A', 'trade': 'General'}, 'repeat')
        with self.assertRaises(DeskError) as caught:
            self.store.command({'type': 'vendor', 'name': 'B', 'trade': 'General'}, 'repeat')
        self.assertEqual(caught.exception.status, 409)

    def test_parallel_identical_retries_create_once(self):
        data = {'type': 'request', 'property_id': self.prop, 'unit': '3A', 'description': 'Door sticks'}
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: self.store.command(data, 'parallel'), range(6)))
        self.assertEqual(len({r['id'] for r in results}), 1)
        self.assertEqual(len(self.store.state()['requests']), 1)

    def test_overlapping_appointments_rejected(self):
        self.schedule(self.request())
        with self.assertRaises(DeskError) as caught:
            self.schedule(self.request(unit='4A'))
        self.assertEqual(caught.exception.status, 409)

    def test_adjacent_appointments_allowed(self):
        self.schedule(self.request())
        req = self.schedule(self.request(unit='4A'), start=END, end='2026-10-01T16:00:00Z')
        self.assertEqual(req['status'], 'scheduled')

    def test_parallel_booking_has_one_winner(self):
        requests = [self.request(unit='A'), self.request(unit='B')]
        barrier = threading.Barrier(2)
        def book(req):
            barrier.wait()
            try:
                self.schedule(req)
                return 'saved'
            except DeskError as exc:
                return exc.status
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(book, requests))
        self.assertCountEqual(results, ['saved', 409])
        self.assertEqual(sum(r['appointment'] is not None for r in self.store.state()['requests']), 1)

    def test_same_instant_different_offsets_conflicts(self):
        self.schedule(self.request())
        with self.assertRaises(DeskError):
            self.schedule(self.request(unit='4A'), start='2026-10-01T09:30:00-05:00', end='2026-10-01T10:30:00-05:00')

    def test_invalid_times_leave_no_appointment(self):
        req = self.request()
        for start, end in [('bad', END), ('2026-10-01T14:00:00', END), (END, START), (START, START), ([], END)]:
            with self.subTest(start=start, end=end), self.assertRaises(DeskError):
                self.schedule(req, start=start, end=end)
        self.assertEqual(self.current(req)['version'], 1)
        self.assertEqual(self.current(req)['appointments'], [])

    def test_stale_version_preserves_current_appointment(self):
        initial = self.request()
        saved = self.schedule(initial)
        with self.assertRaises(DeskError) as caught:
            self.schedule(initial, vendor_id=self.b)
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(self.current(initial), saved)

    def test_versions_require_integer_not_boolean(self):
        req = self.request()
        for version in [True, '1', 1.0, None, 0, []]:
            with self.subTest(version=version), self.assertRaises(DeskError):
                self.schedule(req, version=version)

    def test_failed_replacement_keeps_old_appointment(self):
        req = self.schedule(self.request())
        self.schedule(self.request(unit='3A'), vendor_id=self.b)
        with self.assertRaises(DeskError):
            self.schedule(req, vendor_id=self.b)
        self.assertEqual(self.current(req), req)

    def test_unavailability_updates_all_active_requests_only(self):
        a = self.schedule(self.request())
        b = self.schedule(self.request(unit='3A'), start=END, end='2026-10-01T16:00:00Z')
        closed = self.schedule(self.request(unit='4A'), start='2026-10-01T16:00:00Z', end='2026-10-01T17:00:00Z')
        closed = self.call(type='close', request_id=closed['id'], version=closed['version'], closure='Fixed.')
        self.call(type='vendor_availability', vendor_id=self.a, available=False)
        self.assertEqual(self.current(a)['status'], 'needs_reschedule')
        self.assertEqual(self.current(b)['status'], 'needs_reschedule')
        self.assertEqual(self.current(closed), closed)
        self.call(type='vendor_availability', vendor_id=self.a, available=True)
        self.assertIsNone(self.current(a)['appointment'])

    def test_unavailable_vendor_rejected_without_effect(self):
        self.call(type='vendor_availability', vendor_id=self.a, available=False)
        req = self.request()
        with self.assertRaises(DeskError):
            self.schedule(req)
        self.assertEqual(self.current(req), req)

    def test_availability_requires_boolean(self):
        for value in [0, 1, 'false', [], None]:
            with self.subTest(value=value), self.assertRaises(DeskError):
                self.call(type='vendor_availability', vendor_id=self.a, available=value)

    def test_photo_bytes_exact_after_restart(self):
        req = self.request(photos=[{'name': 'tap.png', 'base64': base64.b64encode(PNG).decode()}])
        self.store = Store(self.path)
        photo = self.store.photo(req['photos'][0]['id'])
        self.assertEqual(photo['data'], PNG)
        self.assertEqual(photo['mime'], 'image/png')

    def test_invalid_photo_rolls_back_entire_intake(self):
        good = {'name': 'tap.png', 'base64': base64.b64encode(PNG).decode()}
        for bad in [None, {'name': 'bad', 'base64': '%'}, {'name': 'html.png', 'base64': base64.b64encode(b'<html>').decode()}]:
            with self.subTest(bad=bad), self.assertRaises(DeskError):
                self.request(photos=[good, bad])
        with self.store.connection() as db:
            for table in ('requests', 'photos', 'events'):
                self.assertEqual(db.execute('SELECT count(*) FROM ' + table).fetchone()[0], 0)

    def test_photo_count_and_size_bounds(self):
        good = {'name': 'tap.png', 'base64': base64.b64encode(PNG).decode()}
        for photos in [[good] * 4, {}, [dict(good, base64='A' * (3 * 1024 * 1024))]]:
            with self.subTest(size=len(photos)), self.assertRaises(DeskError):
                self.request(photos=photos)
        self.assertEqual(self.store.state()['requests'], [])

    def test_malformed_shapes_produce_domain_errors(self):
        for data in [[], None, {'type': []}, {'type': 'property', 'name': 1}, {'type': 'request', 'urgency': []}]:
            with self.subTest(data=data), self.assertRaises(DeskError):
                self.store.command(data)

    def test_missing_property_rolls_back(self):
        with self.assertRaises(DeskError):
            self.request(property_id='missing')
        self.assertEqual(self.store.state()['requests'], [])

    def test_urgency_queue_and_faq_update(self):
        self.request(unit='A')
        urgent = self.request(unit='B', urgency='urgent')
        emergency = self.request(unit='C', urgency='emergency')
        self.assertEqual([r['id'] for r in self.store.state()['requests']][:2], [emergency['id'], urgent['id']])
        self.call(type='faq', property_id=self.prop, faq='Updated access instructions.')
        self.assertEqual(self.store.state()['properties'][0]['faq'], 'Updated access instructions.')

    def test_close_reopen_retains_history(self):
        req = self.request()
        req = self.call(type='close', request_id=req['id'], version=req['version'], closure='Resolved.')
        with self.assertRaises(DeskError):
            self.schedule(req)
        req = self.call(type='reopen', request_id=req['id'], version=req['version'], reason='Issue returned.')
        self.assertEqual(req['status'], 'new')
        self.assertEqual(req['closure'], '')
        self.assertIn('Closed: Resolved.', [e['message'] for e in req['events']])
        self.assertEqual(self.schedule(req)['status'], 'scheduled')

    def test_seed_repeat_safe(self):
        self.store.seed_demo()
        before = self.store.state()
        self.store.seed_demo()
        self.assertEqual(self.store.state(), before)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'test.sqlite')
        self.server = make_server(self.store, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.temp.cleanup()

    def request(self, method, path, data=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        conn.request(method, path, body=data, headers=headers or {})
        res = conn.getresponse()
        output = res.status, dict(res.getheaders()), res.read()
        conn.close()
        return output

    def post(self, command, op='http-operation'):
        return self.request('POST', '/api/command', json.dumps({'command': command, 'operation_id': op}), {'Content-Type': 'application/json'})

    def test_actual_http_create_read_and_retry(self):
        payload = {'type': 'property', 'name': 'HTTP Court', 'faq': 'Hello'}
        status, _, body = self.post(payload)
        self.assertEqual(status, 200)
        self.assertEqual(self.post(payload)[2], body)
        state = json.loads(self.request('GET', '/api/state')[2])
        self.assertEqual(state['properties'][0]['name'], 'HTTP Court')
        self.assertEqual(len(state['properties']), 1)

    def test_assets_headers_and_unknown_path(self):
        for path, token in [('/', b'Tenant desk'), ('/app.js', b'use strict')]:
            status, headers, body = self.request('GET', path)
            self.assertEqual(status, 200); self.assertIn(token, body)
            self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(self.request('GET', '/missing')[0], 404)
        self.assertEqual(self.request('GET', '/../../desk.py')[0], 404)

    def test_http_photo_original_and_export(self):
        prop = self.store.command({'type': 'property', 'name': 'Photo Court'})['id']
        req = self.store.command({'type': 'request', 'property_id': prop, 'unit': 'A', 'description': 'Photo test',
                                  'photos': [{'name': 'tap.png', 'base64': base64.b64encode(PNG).decode()}]})
        status, headers, body = self.request('GET', '/api/photo/' + req['photos'][0]['id'])
        self.assertEqual((status, body), (200, PNG))
        self.assertEqual(headers['Content-Type'], 'image/png')
        self.assertIn('attachment;', headers['Content-Disposition'])
        status, headers, body = self.request('GET', '/api/export')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['requests'][0]['id'], req['id'])

    def test_strict_json_and_http_errors(self):
        for raw in ['[]', '{"command":{}}', '{"x":1,"x":2}', '{"x":NaN}', '{"x":1e400}', 'bad']:
            with self.subTest(raw=raw):
                self.assertEqual(self.request('POST', '/api/command', raw, {'Content-Type': 'application/json'})[0], 400)
        self.assertEqual(self.request('POST', '/api/command', '{}', {'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(self.request('POST', '/api/missing', '{}', {'Content-Type': 'application/json'})[0], 404)
        self.assertEqual(self.request('POST', '/api/command', '{}', {'Content-Type': 'application/json', 'Content-Length': str(MAX_BODY + 1)})[0], 413)
        self.assertEqual(self.request('GET', '/api/photo/missing')[0], 404)

    def test_finite_json_and_duplicate_keys(self):
        self.assertEqual(strict_json('{"n":1.5,"i":2}'), {'n': 1.5, 'i': 2})
        for raw in ['{"n":1e400}', '{"n":-1e400}', '{"n":Infinity}', '{"a":{"x":1,"x":2}}']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                strict_json(raw)


if __name__ == '__main__':
    unittest.main()
