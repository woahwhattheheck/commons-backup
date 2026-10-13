"""Real SQLite, threaded HTTP and subprocess tests; no phone/provider calls."""
import concurrent.futures
import datetime as dt
import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
from desk import Conflict, Store, bundle, make_handler

TODAY = dt.date(2026, 9, 8)
CSV = '''order_ref,status,eta,delivered_on,returnable
1001,delivered,At the shop,2026-09-01,true
1002,shipped,Friday,,false
1003,delivered,Delivered,2026-07-01,true
1004,delivered,Final sale,2026-09-01,false
'''
POLICY = {'shop_name': 'Fixture Shop', 'shipping_text': 'Orders leave in two business days; carrier dates are estimates.', 'return_days': 30, 'staff_phone': ''}


class DeskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'desk.sqlite3'
        self.store = Store(self.db, today=lambda: TODAY)
        self.store.import_csv(CSV)
        self.store.update_policy(POLICY)

    def connect(self, call='call-a', ref='1001'):
        self.store.turn(call, 0)
        return self.store.turn(call, 1, digits=ref)

    def prepare(self, call='call-a'):
        self.connect(call)
        self.store.turn(call, 2, 'return')
        return self.store.turn(call, 3, 'damaged seam')

    def request(self, call='call-a'):
        self.prepare(call)
        return self.store.turn(call, 4, 'yes')

    def audit(self):
        with sqlite3.connect(self.db) as db:
            return db.execute('SELECT kind,details FROM audit ORDER BY id').fetchall()

    def test_status_uses_current_import_not_call_snapshot(self):
        self.connect(ref='1002')
        old = self.store.turn('call-a', 2, 'status')
        self.assertIn('is shipped', old['message'])
        self.store.import_csv('order_ref,status,eta,delivered_on,returnable\n1002,delivered,At front desk,2026-09-08,true\n')
        new = self.store.turn('call-a', 3, 'status')
        self.assertIn('is delivered', new['message'])
        self.assertIn('At front desk', new['message'])

    def test_shipping_uses_latest_saved_policy(self):
        self.connect()
        self.store.update_policy({**POLICY, 'shipping_text': 'Updated carrier guidance.'})
        self.assertIn('Updated carrier guidance.', self.store.turn('call-a', 2, digits='3')['message'])

    def test_return_requires_explicit_confirmation(self):
        before = self.prepare()
        self.assertEqual('confirm', before['state'])
        self.assertEqual([], self.store.snapshot()['returns'])
        result = self.store.turn('call-a', 4, digits='1')
        rows = self.store.snapshot()['returns']
        self.assertEqual(1, len(rows))
        self.assertEqual(result['return_id'], rows[0]['id'])
        self.assertEqual('damaged seam', rows[0]['reason'])
        self.assertEqual('requested', rows[0]['status'])
        self.assertIn('No refund', result['message'])

    def test_cancel_creates_no_return(self):
        self.prepare()
        self.assertEqual('menu', self.store.turn('call-a', 4, 'no')['state'])
        self.assertEqual([], self.store.snapshot()['returns'])

    def test_exact_turn_retries_survive_restart(self):
        expected = self.request()
        before = self.audit()
        reopened = Store(self.db, today=lambda: TODAY)
        self.assertEqual(expected, reopened.turn('call-a', 4, 'yes'))
        self.assertEqual(before, self.audit())
        self.assertEqual(1, len(reopened.snapshot()['returns']))

    def test_changed_retry_rejected_without_state_change(self):
        self.request()
        before = self.store.snapshot()
        with self.assertRaises(Conflict):
            self.store.turn('call-a', 4, 'no')
        self.assertEqual(before, self.store.snapshot())

    def test_out_of_order_initial_and_later_turns_are_atomic(self):
        with self.assertRaises(Conflict):
            self.store.turn('new', 2, 'yes')
        self.assertEqual([], self.store.snapshot()['calls'])
        self.connect()
        before = self.store.snapshot()
        with self.assertRaises(Conflict):
            self.store.turn('call-a', 8, 'status')
        self.assertEqual(before, self.store.snapshot())

    def test_concurrent_duplicate_confirmations_share_response(self):
        self.prepare()
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            responses = list(pool.map(lambda _: self.store.turn('call-a', 4, 'yes'), range(24)))
        self.assertTrue(all(r == responses[0] for r in responses))
        self.assertEqual(1, len(self.store.snapshot()['returns']))
        self.assertEqual(1, sum(kind == 'return_requested' for kind, _ in self.audit()))

    def test_concurrent_distinct_calls_create_one_order_return(self):
        calls = [f'parallel-{i}' for i in range(12)]
        for call in calls:
            self.prepare(call)
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            responses = list(pool.map(lambda c: self.store.turn(c, 4, 'yes'), calls))
        self.assertEqual(1, len({r['return_id'] for r in responses}))
        self.assertEqual(1, len(self.store.snapshot()['returns']))

    def test_existing_return_is_not_reopened_or_repeated(self):
        first = self.request()
        self.store.review('returns', first['return_id'], 'closed', 'Handled in merchant system.')
        self.connect('second')
        result = self.store.turn('second', 2, 'return')
        self.assertEqual(first['return_id'], result['return_id'])
        self.assertIn('already closed', result['message'])

    def test_policy_change_between_reason_and_confirmation_rechecks(self):
        self.prepare()
        self.store.update_policy({**POLICY, 'return_days': 1})
        result = self.store.turn('call-a', 4, 'yes')
        self.assertIn('handoff_id', result)
        self.assertEqual([], self.store.snapshot()['returns'])

    def test_order_change_before_confirmation_rechecks(self):
        self.prepare()
        self.store.import_csv(CSV.replace('At the shop,2026-09-01,true', 'Final sale,2026-09-01,false'))
        self.assertIn('handoff_id', self.store.turn('call-a', 4, 'yes'))
        self.assertEqual([], self.store.snapshot()['returns'])

    def test_no_assumed_return_policy_before_merchant_saves(self):
        store = Store(self.root / 'unconfigured.sqlite3', today=lambda: TODAY)
        store.import_csv(CSV)
        store.turn('call', 0)
        store.turn('call', 1, '1001')
        self.assertIn('handoff_id', store.turn('call', 2, 'return'))
        self.assertEqual([], store.snapshot()['returns'])

    def test_ineligible_orders_go_to_team_not_automatic_refund(self):
        for ref in ('1002', '1003', '1004'):
            with self.subTest(ref=ref):
                self.connect(ref, ref)
                result = self.store.turn(ref, 2, 'return')
                self.assertEqual('ended', result['state'])
                self.assertIn('handoff_id', result)
                self.assertNotIn('dial_phone', result)
        self.assertEqual([], self.store.snapshot()['returns'])

    def test_day_boundary_is_inclusive_and_future_delivery_rejected(self):
        self.store.update_policy({**POLICY, 'return_days': 7})
        self.assertIn('return_id', self.request())
        with self.assertRaises(ValueError):
            self.store.import_csv(CSV.replace('2026-09-01', '2026-09-09'))

    def test_real_dial_markup_and_failed_transfer_persistence(self):
        self.store.update_policy({**POLICY, 'staff_phone': '+12025550148'})
        self.connect()
        result = self.store.turn('call-a', 2, 'agent')
        xml = ET.fromstring(result['twiml'])
        self.assertEqual('+12025550148', xml.find('Dial/Number').text)
        self.assertEqual('/dial-result', xml.find('Dial').get('action'))
        failure = self.store.dial_result('call-a', 'no-answer')
        self.assertIsNotNone(ET.fromstring(failure['twiml']).find('Hangup'))
        self.assertEqual(failure, Store(self.db).dial_result('call-a', 'no-answer'))
        row = self.store.snapshot()['handoffs'][0]
        self.assertEqual('no-answer', row['dial_status'])
        self.assertEqual('open', row['operator_status'])
        with self.assertRaises(Conflict):
            self.store.dial_result('call-a', 'completed')

    def test_completed_provider_dial_does_not_resolve_human_queue(self):
        self.store.update_policy({**POLICY, 'staff_phone': '+12025550148'})
        self.store.turn('call-a', 0)
        self.store.turn('call-a', 1, digits='0')
        self.store.dial_result('call-a', 'completed')
        self.assertEqual('open', self.store.snapshot()['handoffs'][0]['operator_status'])

    def test_unknown_request_and_unknown_reference_escalate(self):
        self.connect()
        self.assertIn('handoff_id', self.store.turn('call-a', 2, 'change my payment card'))
        self.store.turn('other', 0)
        self.assertIn('handoff_id', self.store.turn('other', 1, 'order 1001 maybe'))

    def test_two_silences_have_one_visible_handoff(self):
        self.store.turn('silent', 0)
        self.assertEqual('order', self.store.turn('silent', 1)['state'])
        final = self.store.turn('silent', 2)
        self.assertIn('handoff_id', final)
        self.assertEqual(final, self.store.turn('silent', 2))
        with self.assertRaises(Conflict):
            self.store.turn('silent', 3)
        self.assertEqual(1, len(self.store.snapshot()['handoffs']))

    def test_spoken_digits_and_keypad_reason(self):
        self.store.turn('spoken', 0)
        self.assertEqual('1001', self.store.turn('spoken', 1, 'one zero zero one.')['order_ref'])
        self.store.turn('spoken', 2, digits='2')
        result = self.store.turn('spoken', 3, digits='2')
        self.assertIn('incorrect item', result['message'])

    def test_text_is_xml_escaped_not_executed(self):
        self.connect()
        self.store.turn('call-a', 2, 'return')
        reason = 'Loose <seam> & fabric </Say><Dial>not-a-number</Dial>'
        result = self.store.turn('call-a', 3, reason)
        root = ET.fromstring(result['twiml'])
        self.assertIn(reason, root.find('Gather/Say').text)
        self.assertIsNone(root.find('.//Dial'))

    def test_csv_bad_row_and_duplicate_references_rollback_everything(self):
        before, audit = self.store.snapshot(), self.audit()
        bads = [CSV.replace('1004,delivered', '1004,invalid'), CSV + '1001,processing,,,true\n', CSV.replace('true', 'yes'), CSV.replace('2026-09-01', '20260901'), CSV.replace('1001,delivered', '1001,processing'), CSV + '1006,processing\n']
        for bad in bads:
            with self.subTest(bad=bad[-60:]):
                with self.assertRaises(ValueError):
                    self.store.import_csv(bad)
                self.assertEqual(before, self.store.snapshot())
                self.assertEqual(audit, self.audit())

    def test_bom_import_and_unicode_policy_roundtrip(self):
        self.store.import_csv('\ufeff' + CSV)
        expected = self.store.update_policy({**POLICY, 'shop_name': 'Café & 工房', 'shipping_text': 'Stocké <ici> & expédié.'})
        self.assertEqual(expected, Store(self.db).snapshot()['policy'])
        self.assertIn('Café & 工房', ET.fromstring(self.store.turn('unicode', 0)['twiml']).find('Gather/Say').text)

    def test_invalid_json_field_types_leave_database_unchanged(self):
        before = self.store.snapshot()
        for policy in ({**POLICY, 'return_days': True}, {**POLICY, 'staff_phone': 'call me'}, {**POLICY, 'shop_name': []}, {**POLICY, 'shipping_text': '\x00'}):
            with self.assertRaises(ValueError):
                self.store.update_policy(policy)
        with self.assertRaises(ValueError):
            self.store.review([], 'none', [], 'note')
        with self.assertRaises(ValueError):
            self.store.turn('a', True)
        self.assertEqual(before, self.store.snapshot())

    def test_review_and_export_persist_actual_requests(self):
        rid = self.request()['return_id']
        self.store.review('returns', rid, 'reviewed', 'Inspected; label handled separately.')
        doc = json.loads(Store(self.db).export())
        self.assertEqual(1, doc['schema_version'])
        self.assertEqual('reviewed', doc['returns'][0]['status'])
        self.assertTrue(any(row['kind'] == 'operator_review' for row in doc['audit']))


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'http.sqlite3'
        self.store = Store(self.db, today=lambda: TODAY)
        self.store.import_csv(CSV)
        self.store.update_policy(POLICY)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.store))
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.addCleanup(self.stop)
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=3)

    def http(self, path, body=None, mime='application/json'):
        data = body if isinstance(body, bytes) or body is None else body.encode()
        req = urllib.request.Request(self.base + path, data=data, headers={'Content-Type': mime})
        try:
            with urllib.request.urlopen(req, timeout=3) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as response:
            return response.code, response.read(), response.headers

    def form(self, path, **form):
        return self.http(path, urllib.parse.urlencode(form), 'application/x-www-form-urlencoded')

    def test_http_phone_order_return_and_exact_retry(self):
        path = '/voice'
        bodies = []
        for digits in ('', '1001', '2', '1', '1'):
            status, body, headers = self.form(path, CallSid='CA-synthetic', Digits=digits)
            self.assertEqual(200, status, body)
            self.assertIn('application/xml', headers['Content-Type'])
            bodies.append((path, digits, body))
            root = ET.fromstring(body)
            path = root.find('Gather').get('action')
        old_path, digits, expected = bodies[-1]
        self.assertEqual(expected, self.form(old_path, CallSid='CA-synthetic', Digits=digits)[1])
        self.assertEqual(1, len(self.store.snapshot()['returns']))
        self.assertIn(b'No refund', expected)

    def test_http_staff_dial_callback_is_not_repeated(self):
        self.store.update_policy({**POLICY, 'staff_phone': '+12025550148'})
        self.form('/voice', CallSid='call-transfer')
        status, body, _ = self.form('/voice?turn=1', CallSid='call-transfer', SpeechResult='agent')
        self.assertEqual(200, status)
        self.assertIsNotNone(ET.fromstring(body).find('Dial/Number'))
        callback = self.form('/dial-result', CallSid='call-transfer', DialCallStatus='busy')
        self.assertEqual(200, callback[0])
        self.assertEqual(callback[1], self.form('/dial-result', CallSid='call-transfer', DialCallStatus='busy')[1])
        self.assertEqual('busy', self.store.snapshot()['handoffs'][0]['dial_status'])

    def test_http_import_policy_ui_state_and_export(self):
        for path in ('/', '/api/state', '/api/export', '/health'):
            status, body, headers = self.http(path)
            self.assertEqual(200, status, path)
            self.assertEqual(len(body), int(headers['Content-Length']))
        status, _, _ = self.http('/api/policy', json.dumps({**POLICY, 'return_days': 14}))
        self.assertEqual(200, status)
        self.assertEqual(14, self.store.snapshot()['policy']['return_days'])
        self.assertEqual(200, self.http('/api/import', CSV, 'text/csv')[0])
        doc = json.loads(self.http('/api/export')[1])
        self.assertEqual(4, len(doc['orders']))
        self.assertIn('attachment', self.http('/api/export')[2]['Content-Disposition'])

    def test_bad_http_json_utf8_form_and_turn_leave_state_unchanged(self):
        before = self.store.snapshot()
        cases = [('/api/policy', b'{', 'application/json'), ('/api/policy', b'\xff', 'application/json'), ('/api/policy', b'[]', 'application/json'), ('/api/review', b'{"kind":[],"status":[]}', 'application/json'), ('/voice', b'CallSid=a&CallSid=b', 'application/x-www-form-urlencoded'), ('/voice?turn=-1', b'CallSid=a', 'application/x-www-form-urlencoded'), ('/voice?turn=1&turn=2', b'CallSid=a', 'application/x-www-form-urlencoded')]
        for path, body, mime in cases:
            with self.subTest(path=path, body=body):
                self.assertEqual(400, self.http(path, body, mime)[0])
                self.assertEqual(before, self.store.snapshot())

    def test_http_conflicting_retries_return_409(self):
        body = json.dumps({'call_id': 'retry', 'turn': 0})
        first = self.http('/api/turn', body)
        self.assertEqual(200, first[0])
        self.assertEqual(first[1], self.http('/api/turn', body)[1])
        self.assertEqual(409, self.http('/api/turn', json.dumps({'call_id': 'retry', 'turn': 0, 'speech': 'different'}))[0])


class PackageTests(unittest.TestCase):
    def test_cli_import_policy_export_and_no_overwrite(self):
        here = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            csv_path = root / 'orders.csv'
            csv_path.write_text(CSV)
            policy = root / 'policy.json'
            policy.write_text(json.dumps(POLICY))
            output = root / 'export.json'
            command = [sys.executable, str(here / 'desk.py'), '--db', str(root / 'desk.sqlite3')]
            for args in (['import', str(csv_path)], ['policy', str(policy)], ['export', str(output)]):
                result = subprocess.run(command + args, capture_output=True, text=True, timeout=10)
                self.assertEqual(0, result.returncode, result.stderr)
            original = output.read_bytes()
            self.assertEqual(4, len(json.loads(original)['orders']))
            result = subprocess.run(command + ['export', str(output)], capture_output=True, timeout=10)
            self.assertEqual(2, result.returncode)
            self.assertEqual(original, output.read_bytes())

    def test_source_bundle_runs_after_extraction_and_contains_no_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            destination = root / 'desk.zip'
            bundle(destination)
            original = destination.read_bytes()
            with self.assertRaises(FileExistsError):
                bundle(destination)
            self.assertEqual(original, destination.read_bytes())
            with zipfile.ZipFile(destination) as archive:
                self.assertEqual({'voice-support-desk/' + p for p in ['desk.py', 'index.html', 'README.md', 'test_desk.py', 'orders.example.csv']}, set(archive.namelist()))
                archive.extractall(root / 'extracted')
            extracted = root / 'extracted' / 'voice-support-desk'
            command = [sys.executable, str(extracted / 'desk.py'), '--db', str(root / 'extracted.sqlite3'), 'import', str(extracted / 'orders.example.csv')]
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(4, len(Store(root / 'extracted.sqlite3').snapshot()['orders']))


if __name__ == '__main__':
    unittest.main()
