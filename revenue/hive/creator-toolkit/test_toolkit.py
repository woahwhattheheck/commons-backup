"""Real filesystem, SQLite, threaded-concurrency and live-HTTP coverage."""
import base64
import concurrent.futures
import hashlib
import json
import tempfile
import threading
import unittest
import uuid
from email import policy
from email.parser import BytesParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app import OPERATOR_ACTIONS, make_server
from operator_auth import OperatorAuth
from toolkit import CONSENT_TEXT, DeskError, MAX_FILE_BYTES, Store

BINARY = bytes(range(256)) + b'\x00\xff\r\nOriginal bytes\n'
SEQUENCE = [{"delay_minutes": 0, "subject": "First step", "body": "An optional first step."},
            {"delay_minutes": 1440, "subject": "Tomorrow", "body": "An optional second step."}]


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'desk.sqlite3'
        self.now = 1000
        self.store = Store(self.path, lambda: self.now)

    def change(self, action, payload, op=None):
        return self.store.mutate(action, op or uuid.uuid4().hex, payload)

    def resource(self, **kwargs):
        value = dict(title="A real resource", description="Shared note", kind="file", filename="original.bin",
                     data_base64=base64.b64encode(BINARY).decode(), sequence=SEQUENCE)
        value.update(kwargs)
        return self.change('resource.create', value)

    def request(self, resource, address='person@example.invalid', opt_in=False, op=None):
        return self.change('request', dict(resource_id=resource['id'], email=address, name='Reader', opt_in=opt_in), op)

    def pref(self, member_id, value):
        member = self.store.member(member_id)
        return self.change('preferences', dict(member_id=member_id, expected_revision=member['revision'], opted_in=value))

    def assertDeskError(self, code, fn):
        with self.assertRaises(DeskError) as exc:
            fn()
        self.assertEqual(exc.exception.status, code)

    def test_empty_workspace(self):
        self.assertEqual(self.store.catalog(), [])
        self.assertEqual(self.store.dashboard()['counts'], {'members': 0, 'requests': 0})

    def test_original_binary_and_hash_survive_reopen(self):
        resource = self.resource()
        request = self.request(resource)
        reopened = Store(self.path)
        result = reopened.delivery(request['request_id'])
        self.assertEqual(result['data'], BINARY)
        self.assertEqual(result['sha256'], hashlib.sha256(BINARY).hexdigest())
        self.assertEqual(reopened.member(request['member_id'])['requests'][0]['id'], request['request_id'])

    def test_link_delivered_exactly(self):
        r = self.resource(kind='link', target='https://example.invalid/book?a=1&b=2')
        q = self.request(r)
        self.assertEqual(self.store.delivery(q['request_id'])['target'], 'https://example.invalid/book?a=1&b=2')

    def test_bad_links(self):
        for target in ['javascript:alert(1)', '//example.invalid', 'https://u:p@example.invalid', 'https://x.invalid:bad', 'https://x.invalid/\nnext']:
            with self.subTest(target=target):
                self.assertDeskError(400, lambda: self.resource(kind='link', target=target))
        self.assertEqual(self.store.catalog(), [])

    def test_retry_and_operation_conflict(self):
        payload = dict(title='Link', kind='link', target='https://example.invalid')
        first = self.change('resource.create', payload, 'stable-create')
        self.assertEqual(first, self.change('resource.create', payload, 'stable-create'))
        self.assertDeskError(409, lambda: self.change('resource.create', dict(payload, title='Different'), 'stable-create'))
        self.assertEqual(len(self.store.catalog()), 1)

    def test_bad_shapes_and_file_names_are_atomic(self):
        for kwargs in [dict(filename='../file'), dict(filename='line\nname'), dict(data_base64='??'), dict(kind=[]), dict(title=False), dict(sequence={}), dict(sequence=[None]), dict(sequence=[dict(delay_minutes=True, subject='Hi', body='Hi')])]:
            with self.subTest(kwargs=kwargs):
                self.assertDeskError(400, lambda: self.resource(**kwargs))
        self.assertEqual(self.store.catalog(), [])

    def test_size_boundary_and_empty_file(self):
        self.assertDeskError(400, lambda: self.resource(data_base64='A' * ((((MAX_FILE_BYTES+2)//3)*4)+1)))
        empty = self.resource(data_base64='')
        self.assertEqual(empty['sha256'], hashlib.sha256(b'').hexdigest())

    def test_header_and_delay_validation(self):
        for seq in [[dict(delay_minutes=-1, subject='Hi', body='Hi')], [dict(delay_minutes=0, subject='Hi\nInjected: x', body='Hi')], [dict(delay_minutes=0, subject='Hi', body=None)]]:
            with self.subTest(seq=seq):
                self.assertDeskError(400, lambda: self.resource(sequence=seq))

    def test_default_request_has_no_marketing(self):
        q = self.request(self.resource(), address='  Reader@Example.Invalid  ')
        member = self.store.member(q['member_id'])
        self.assertFalse(member['opted_in'])
        self.assertEqual(member['email'], 'reader@example.invalid')
        self.assertEqual(member['consents'], [])
        self.assertEqual(self.store.dashboard()['outbox'], [])

    def test_affirmative_optin_records_wording_and_schedule(self):
        q = self.request(self.resource(), opt_in=True)
        member = self.store.member(q['member_id'])
        self.assertTrue(member['opted_in'])
        self.assertEqual(member['consents'][0]['wording'], CONSENT_TEXT)
        outbox = self.store.dashboard()['outbox']
        self.assertEqual([o['due_at'] for o in outbox], [1000, 87400])
        self.assertEqual([o['due'] for o in outbox], [True, False])

    def test_repeat_request_coalesces_without_reenrollment(self):
        r = self.resource()
        a = self.request(r, opt_in=True)
        self.pref(a['member_id'], False)
        b = self.request(r, opt_in=True)
        self.assertEqual(a['request_id'], b['request_id'])
        self.assertTrue(b['reused'])
        self.assertFalse(self.store.member(a['member_id'])['opted_in'])
        self.assertEqual(len(self.store.dashboard()['outbox']), 2)
        self.assertTrue(all(o['state'] == 'cancelled' for o in self.store.dashboard()['outbox']))

    def test_old_operation_replay_does_not_reapply_consent(self):
        r = self.resource()
        a = self.request(r, opt_in=True, op='old-request')
        self.pref(a['member_id'], False)
        b = self.request(r, opt_in=True, op='old-request')
        self.assertEqual(a, b)
        self.assertFalse(self.store.member(a['member_id'])['opted_in'])

    def test_unchecked_new_request_neither_enrolls_nor_cancels_existing(self):
        a = self.request(self.resource(), opt_in=True)
        b = self.request(self.resource(title='Another'), opt_in=False)
        self.assertEqual(a['member_id'], b['member_id'])
        self.assertTrue(self.store.member(b['member_id'])['opted_in'])
        self.assertEqual(len(self.store.dashboard()['outbox']), 2)

    def test_stop_cancels_all_queued_sequences_and_resume_does_not_revive(self):
        a = self.request(self.resource(), opt_in=True)
        self.request(self.resource(title='Other'), opt_in=True)
        self.pref(a['member_id'], False)
        self.pref(a['member_id'], True)
        rows = self.store.dashboard()['outbox']
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(o['state'] == 'cancelled' for o in rows))
        self.request(self.resource(title='Fresh opt-in'), opt_in=True)
        self.assertEqual(sum(o['state'] == 'queued' for o in self.store.dashboard()['outbox']), 2)

    def test_preferences_stale_revision_is_conflict(self):
        q = self.request(self.resource(), opt_in=True)
        old = self.store.member(q['member_id'])
        self.pref(old['id'], False)
        self.assertDeskError(409, lambda: self.change('preferences', dict(member_id=old['id'], expected_revision=old['revision'], opted_in=True)))
        self.assertFalse(self.store.member(old['id'])['opted_in'])

    def test_resource_updates_keep_file_and_queued_sequence_snapshots(self):
        r = self.resource()
        q = self.request(r, opt_in=True)
        payload = dict(id=r['id'], expected_revision=r['revision'], title='Renamed', description='New description', sequence=[], active=True)
        updated = self.change('resource.update', payload)
        self.assertEqual(updated['revision'], 2)
        self.assertEqual(self.store.delivery(q['request_id'])['data'], BINARY)
        self.assertEqual([o['subject'] for o in self.store.dashboard()['outbox']], ['First step', 'Tomorrow'])
        self.assertDeskError(409, lambda: self.change('resource.update', payload))

    def test_archival_preserves_existing_delivery_and_rejects_new_request(self):
        r = self.resource()
        q = self.request(r)
        self.change('resource.update', dict(id=r['id'], expected_revision=1, title=r['title'], description=r['description'], sequence=[], active=False))
        self.assertEqual(self.store.catalog(), [])
        self.assertEqual(self.store.delivery(q['request_id'])['data'], BINARY)
        self.assertEqual(self.request(r)['request_id'], q['request_id'])
        self.assertDeskError(409, lambda: self.request(r, address='other@example.invalid'))
        self.assertEqual(self.store.dashboard()['counts']['members'], 1)

    def test_concurrent_resource_requests_create_one_delivery(self):
        r = self.resource()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.request(r, opt_in=True), range(16)))
        self.assertEqual(len({x['request_id'] for x in results}), 1)
        self.assertEqual(self.store.dashboard()['counts'], {'members': 1, 'requests': 1})
        self.assertEqual(len(self.store.dashboard()['outbox']), 2)

    def test_concurrent_same_operation_applies_once(self):
        payload = dict(title='Link', kind='link', target='https://example.invalid')
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.change('resource.create', payload, 'one'), range(12)))
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(len(self.store.catalog()), 1)

    def test_draft_due_check_and_headers(self):
        self.request(self.resource(), opt_in=True)
        first, second = self.store.dashboard()['outbox']
        msg = BytesParser(policy=policy.default).parsebytes(self.store.email_draft(first['id']))
        self.assertEqual(msg['To'], 'person@example.invalid')
        self.assertEqual(msg['X-Unsent'], '1')
        self.assertEqual(msg['X-Creator-Desk-Reference'], first['id'])
        self.assertIn('unsubscribe', msg.get_body().get_content())
        self.assertIsNone(msg['From'])
        self.assertDeskError(409, lambda: self.store.email_draft(second['id']))
        self.now = 87400
        self.assertTrue(self.store.email_draft(second['id']))

    def test_cancelled_draft_cannot_be_reexported_or_recorded(self):
        q = self.request(self.resource(), opt_in=True)
        first = self.store.dashboard()['outbox'][0]
        self.assertTrue(self.store.email_draft(first['id']))
        self.pref(q['member_id'], False)
        self.assertDeskError(409, lambda: self.store.email_draft(first['id']))
        self.assertDeskError(409, lambda: self.change('outbox.record', dict(id=first['id'], receipt='synthetic-receipt')))

    def test_record_reference_is_retry_safe_not_actual_send(self):
        self.request(self.resource(), opt_in=True)
        first, second = self.store.dashboard()['outbox']
        payload = dict(id=first['id'], receipt='synthetic-test-provider-reference')
        result = self.change('outbox.record', payload, 'record-once')
        self.assertEqual(result['state'], 'recorded')
        self.assertEqual(self.change('outbox.record', payload, 'record-once'), result)
        self.assertDeskError(409, lambda: self.change('outbox.record', payload))
        self.assertDeskError(409, lambda: self.change('outbox.record', dict(id=second['id'], receipt='not-due')))
        self.assertDeskError(409, lambda: self.store.email_draft(first['id']))

    def test_member_inquiry_is_idempotent_and_resolvable(self):
        q = self.request(self.resource())
        payload = dict(member_id=q['member_id'], body='Please make a shorter version.')
        a = self.change('inquiry', payload, 'ask-once')
        self.assertEqual(a, self.change('inquiry', payload, 'ask-once'))
        self.assertEqual(len(self.store.dashboard()['inquiries']), 1)
        self.assertEqual(self.change('inquiry.close', {'id': a['id']})['state'], 'closed')

    def test_invalid_payload_does_not_write(self):
        for payload in [None, [], {'x': float('nan')}, {'x': '\ud800'}]:
            self.assertDeskError(400, lambda: self.change('resource.create', payload))
        for key in [None, [], 1, {}, '\ud800']:
            self.assertDeskError(400, lambda: self.store.member(key))
        self.assertDeskError(404, lambda: self.store.member('absent'))
        self.assertEqual(self.store.dashboard()['counts']['members'], 0)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'http.sqlite3'
        self.store = Store(self.path, lambda: 1000)
        self.operator_key = OperatorAuth.initialize(self.path)
        self.auth = OperatorAuth(self.path)
        self.server = make_server(self.store, port=0, operator_auth=self.auth)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.tmp.cleanup()

    def call(self, path, value=None, method=None, operator=False, authorization=None):
        headers = {'Content-Type': 'application/json'}
        if authorization is not None:
            headers['Authorization'] = authorization
        elif operator:
            headers['Authorization'] = 'Bearer ' + self.operator_key
        request = Request(self.base + path, data=None if value is None else json.dumps(value).encode(), headers=headers, method=method)
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, response.headers, response.read()
        except HTTPError as exc:
            return exc.code, exc.headers, exc.read()

    def change(self, action, payload, op=None, operator=None):
        if operator is None:
            operator = action in OPERATOR_ACTIONS
        status, _, body = self.call('/api/change', dict(action=action, payload=payload, operation_id=op or uuid.uuid4().hex), operator=operator)
        self.assertEqual(status, 200, body)
        return json.loads(body)

    def resource(self, **kwargs):
        return self.change('resource.create', dict(title='Download', kind='file', filename='résumé.bin', data_base64=base64.b64encode(BINARY).decode(), sequence=SEQUENCE, **kwargs))

    def request(self, resource, op=None):
        return self.change('request', dict(resource_id=resource['id'], email='wire@example.invalid', opt_in=True), op)

    def test_full_http_workflow_download_stop_and_reconnect(self):
        status, _, body = self.call('/')
        self.assertEqual(status, 200)
        self.assertIn(b'Creator Desk', body)
        self.assertIn(b'/operator-auth.js', body)
        r = self.resource()
        q = self.request(r, 'wire-once')
        self.assertEqual(q, self.request(r, 'wire-once'))
        status, headers, content = self.call('/download?id=' + q['request_id'])
        self.assertEqual(status, 200)
        self.assertEqual(content, BINARY)
        self.assertEqual(headers['X-Content-SHA256'], hashlib.sha256(content).hexdigest())
        self.assertIn('r%C3%A9sum%C3%A9.bin', headers['Content-Disposition'])
        status, _, body = self.call('/api/member?id=' + q['member_id'])
        member = json.loads(body)
        self.assertEqual(status, 200)
        first = self.store.dashboard()['outbox'][0]
        self.assertEqual(self.call('/draft.eml?id=' + first['id'], operator=True)[0], 200)
        self.change('preferences', dict(member_id=member['id'], expected_revision=member['revision'], opted_in=False))
        self.assertEqual(self.call('/draft.eml?id=' + first['id'], operator=True)[0], 409)
        self.assertFalse(json.loads(self.call('/api/member?id=' + member['id'])[2])['opted_in'])
        self.assertEqual(self.call('/download?id=' + q['request_id'])[2], BINARY)

    def test_live_http_concurrent_request_coalescing(self):
        r = self.resource()
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: self.request(r), range(10)))
        self.assertEqual(len({q['request_id'] for q in results}), 1)
        dashboard = json.loads(self.call('/api/dashboard', operator=True)[2])
        self.assertEqual(dashboard['counts']['requests'], 1)
        self.assertEqual(len(dashboard['outbox']), 2)

    def test_operator_boundary_rejects_missing_wrong_and_hostile_keys(self):
        r = self.resource()
        q = self.request(r)
        inquiry = self.change('inquiry', dict(member_id=q['member_id'], body='A question'))
        first = self.store.dashboard()['outbox'][0]
        for authorization in (None, 'Bearer wrong', 'Basic anything', 'Bearer ' + 'x' * 300, 'Bearer ÿ'):
            with self.subTest(authorization=repr(authorization)):
                self.assertEqual(self.call('/api/operator', authorization=authorization)[0], 403)
                self.assertEqual(self.call('/api/dashboard', authorization=authorization)[0], 403)
                self.assertEqual(self.call('/workspace.sqlite3', authorization=authorization)[0], 403)
                self.assertEqual(self.call('/draft.eml?id=' + first['id'], authorization=authorization)[0], 403)
                status = self.call('/api/change', dict(action='inquiry.close', operation_id=uuid.uuid4().hex,
                                                       payload={'id': inquiry['id']}), authorization=authorization)[0]
                self.assertEqual(status, 403)
        status, _, body = self.call('/api/operator', operator=True)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {'operator': True})
        self.assertEqual(self.store.dashboard()['inquiries'][0]['state'], 'open')

    def test_public_member_mutations_do_not_require_operator_key(self):
        r = self.resource()
        request = self.change('request', dict(resource_id=r['id'], email='public@example.invalid', opt_in=True), operator=False)
        member = json.loads(self.call('/api/member?id=' + request['member_id'])[2])
        self.change('preferences', dict(member_id=member['id'], expected_revision=member['revision'], opted_in=False), operator=False)
        inquiry = self.change('inquiry', dict(member_id=member['id'], body='Public member request'), operator=False)
        self.assertEqual(inquiry['state'], 'open')
        self.assertFalse(json.loads(self.call('/api/member?id=' + member['id'])[2])['opted_in'])

    def test_authorized_backup_keeps_plaintext_operator_key_out_of_snapshot(self):
        self.resource()
        status, headers, body = self.call('/workspace.sqlite3', operator=True)
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'application/octet-stream')
        self.assertNotIn(self.operator_key.encode(), body)
        self.assertEqual(headers['X-Content-SHA256'], hashlib.sha256(body).hexdigest())

    def test_bad_json_missing_ids_and_content_type(self):
        self.assertEqual(self.call('/api/member')[0], 400)
        self.assertEqual(self.call('/api/member?id=absent')[0], 404)
        self.assertEqual(self.call('/does-not-exist')[0], 404)
        self.assertEqual(self.call('/api/change', [1])[0], 400)
        for data, ctype, expected in [(b'{', 'application/json', 400), (b'{}', 'text/plain', 415)]:
            req = Request(self.base + '/api/change', data=data, headers={'Content-Type': ctype})
            with self.assertRaises(HTTPError) as exc:
                urlopen(req, timeout=5)
            self.assertEqual(exc.exception.code, expected)

    def test_head_and_no_store(self):
        status, headers, content = self.call('/', method='HEAD')
        self.assertEqual(status, 200)
        self.assertEqual(content, b'')
        self.assertGreater(int(headers['Content-Length']), 0)
        self.assertEqual(headers['Cache-Control'], 'no-store')

    def test_link_is_not_a_file_and_inquiry_routes(self):
        r = self.change('resource.create', dict(title='Link', kind='link', target='https://example.invalid/guide'))
        q = self.request(r)
        self.assertEqual(self.call('/download?id=' + q['request_id'])[0], 400)
        self.assertEqual(json.loads(self.call('/api/delivery?id=' + q['request_id'])[2])['target'], r['target'])
        inquiry = self.change('inquiry', dict(member_id=q['member_id'], body='A question'))
        self.change('inquiry.close', dict(id=inquiry['id']))
        self.assertEqual(json.loads(self.call('/api/dashboard', operator=True)[2])['inquiries'][0]['state'], 'closed')


if __name__ == '__main__':
    unittest.main(verbosity=2)
