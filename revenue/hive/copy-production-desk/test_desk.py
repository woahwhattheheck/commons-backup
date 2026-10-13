import concurrent.futures
import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path
from server import Desk, DeskError, load_example, make_server


class DeskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'desk.sqlite3'
        self.desk = Desk(self.path)
        self.client = self.write('client/create', name='Test customer', voice='Plain language',
                                 claims=[{'id': 'c1', 'text': 'An actual offer', 'source': 'owned-offer.md'}])['id']

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, op, **data):
        return self.desk.write(op, {'operation_id': uuid.uuid4().hex, **data})

    def request(self, client=None, priority=0):
        return self.write('request/create', client_id=client or self.client, title='Copy request',
                          kind='Landing page', brief='Only supported claims', priority=priority)['id']

    def item(self, identifier):
        return next(r for r in self.desk.snapshot()['requests'] if r['id'] == identifier)

    def action(self, identifier, action, **extra):
        return self.write('request/action', id=identifier, version=self.item(identifier)['version'], action=action, **extra)

    def save(self, identifier, **extra):
        return self.write('draft/save', **{'id': identifier, 'version': self.item(identifier)['version'],
            'files': {'landing.md': '# Real copy'}, 'source_ids': ['c1'], 'note': 'First draft', **extra})

    def active(self):
        identifier = self.request()
        self.action(identifier, 'start')
        return identifier

    def review(self):
        identifier = self.active()
        self.save(identifier)
        return identifier

    def test_real_persistence_after_reopen(self):
        identifier = self.review()
        reopened = Desk(self.path)
        self.assertEqual(reopened.snapshot()['requests'][0]['drafts'][0]['files']['landing.md'], '# Real copy')
        self.assertEqual(self.item(identifier)['status'], 'review')

    def test_one_active_including_review_and_revision(self):
        first = self.review()
        second = self.request()
        for stage in ('review', 'revision'):
            if stage == 'revision':
                self.action(first, 'revise', feedback='Clarify the offer')
            with self.assertRaises(DeskError) as caught:
                self.action(second, 'start')
            self.assertEqual(caught.exception.status, 409)
            self.assertEqual(self.item(second)['status'], 'queued')

    def test_different_customers_can_work_concurrently(self):
        self.active()
        other = self.write('client/create', name='Other', voice='Direct', claims=[{'id': 'x','text':'Fact','source':'source'}])['id']
        request = self.request(other)
        self.action(request, 'start')
        self.assertEqual(self.item(request)['status'], 'active')

    def test_concurrent_starts_one_winner_real_sqlite(self):
        identifiers = [self.request(), self.request()]
        barrier = threading.Barrier(2)
        def start(identifier):
            barrier.wait()
            try:
                self.action(identifier, 'start')
                return 200
            except DeskError as exc:
                return exc.status
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            self.assertEqual(sorted(pool.map(start, identifiers)), [200, 409])

    def test_delivery_promotes_highest_priority_then_oldest(self):
        first = self.review()
        self.request(priority=1)
        next_id = self.request(priority=80)
        self.request(priority=80)
        result = self.action(first, 'deliver')
        self.assertEqual(result['next_id'], next_id)
        self.assertEqual(self.item(next_id)['status'], 'active')
        self.assertEqual(self.item(first)['status'], 'delivered')
        self.assertEqual(result['delivery'], 'LOCAL_FILES_ONLY_NOT_SENT')

    def test_priority_change_changes_next_job(self):
        first = self.review()
        second = self.request(priority=5)
        third = self.request(priority=10)
        self.action(second, 'priority', priority=99)
        self.action(first, 'deliver')
        self.assertEqual(self.item(second)['status'], 'active')
        self.assertEqual(self.item(third)['status'], 'queued')

    def test_delivery_without_next(self):
        identifier = self.review()
        self.assertIsNone(self.action(identifier, 'deliver')['next_id'])

    def test_stale_edit_does_not_overwrite(self):
        identifier = self.active()
        version = self.item(identifier)['version']
        self.save(identifier)
        with self.assertRaises(DeskError):
            self.save(identifier, version=version, files={'landing.md': 'Stale'})
        self.assertEqual(len(self.item(identifier)['drafts']), 1)

    def test_immutable_revision_history_and_feedback(self):
        identifier = self.review()
        self.action(identifier, 'revise', feedback='Make the heading clearer')
        self.save(identifier, files={'landing.md': '# Clearer copy'}, note='Responded to feedback')
        item = self.item(identifier)
        self.assertEqual(item['feedback'], 'Make the heading clearer')
        self.assertEqual([d['number'] for d in item['drafts']], [1, 2])
        self.assertEqual(item['drafts'][0]['files']['landing.md'], '# Real copy')
        self.assertEqual(item['drafts'][1]['files']['landing.md'], '# Clearer copy')

    def test_brand_change_preserves_snapshot_and_requires_updated_draft(self):
        identifier = self.review()
        self.write('client/update', id=self.client, version=1, name='Changed', voice='Warm',
                   claims=[{'id':'c1','text':'Updated offer','source':'new-source.md'}])
        with self.assertRaises(DeskError):
            self.action(identifier, 'deliver')
        self.assertEqual(self.item(identifier)['drafts'][0]['brand_snapshot']['voice'], 'Plain language')
        self.save(identifier, note='Updated for new offer')
        self.action(identifier, 'deliver')
        self.assertEqual(self.item(identifier)['status'], 'delivered')

    def test_stale_brand_edit_rejected(self):
        data = dict(id=self.client, version=1, name='Changed', voice='Warm', claims=[{'id':'a','text':'A','source':'S'}])
        self.write('client/update', **data)
        with self.assertRaises(DeskError):
            self.write('client/update', **data)

    def test_replay_write_after_lost_ack_no_duplicate(self):
        data = {'operation_id':'lost-ack','client_id':self.client,'title':'Unique','kind':'Email','brief':'Brief'}
        one = self.desk.write('request/create', data)
        two = Desk(self.path).write('request/create', data)
        self.assertEqual(one, two)
        self.assertEqual(len(self.desk.snapshot()['requests']), 1)

    def test_replay_delivery_does_not_promote_extra_job(self):
        first = self.review()
        second, third = self.request(), self.request()
        data = {'operation_id':'delivery-once','id':first,'version':self.item(first)['version'],'action':'deliver'}
        self.assertEqual(self.desk.write('request/action',data), self.desk.write('request/action',data))
        self.assertEqual(self.item(second)['status'], 'active')
        self.assertEqual(self.item(third)['status'], 'queued')

    def test_same_operation_different_payload_conflicts(self):
        data = {'operation_id':'unique-key','client_id':self.client,'title':'One','kind':'Email','brief':'Brief'}
        self.desk.write('request/create', data)
        with self.assertRaises(DeskError) as caught:
            self.desk.write('request/create', {**data,'title':'Two'})
        self.assertEqual(caught.exception.status, 409)

    def test_concurrent_identical_retries_one_record(self):
        data = {'operation_id':'concurrent-key','client_id':self.client,'title':'One','kind':'Email','brief':'Brief'}
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            results = list(pool.map(lambda _: self.desk.write('request/create',data), range(8)))
        self.assertEqual(len({r['id'] for r in results}), 1)
        self.assertEqual(len(self.desk.snapshot()['requests']), 1)

    def test_cancel_releases_production_slot(self):
        first = self.active()
        self.action(first, 'cancel')
        second = self.request()
        self.action(second, 'start')
        self.assertEqual(self.item(second)['status'], 'active')

    def test_cannot_save_or_deliver_queued_request(self):
        identifier = self.request()
        for call in (lambda:self.save(identifier), lambda:self.action(identifier,'deliver')):
            with self.assertRaises(DeskError):
                call()

    def test_delivered_files_cannot_be_silently_changed(self):
        identifier = self.review()
        self.action(identifier, 'deliver')
        with self.assertRaises(DeskError):
            self.save(identifier)

    def test_unknown_source_and_malformed_sources_rejected(self):
        identifier = self.active()
        for sources in ([], ['unknown'], [[]], {}, 'c1', [True]):
            with self.subTest(sources=sources), self.assertRaises(DeskError):
                self.save(identifier, source_ids=sources)
        self.assertEqual(self.item(identifier)['drafts'], [])

    def test_document_name_and_content_validation(self):
        identifier = self.active()
        for files in ({'../x.md':'x'}, {'nested/a.md':'x'}, {'x.md':''}, {'x.md':[]}, {'x.html':'x'}, [], {}, {'x.md':float('inf')}):
            with self.subTest(files=files), self.assertRaises(DeskError):
                self.save(identifier, files=files)

    def test_invalid_priorities_are_not_coerced(self):
        for priority in (True, 0.5, '5', -1, 101, float('inf')):
            with self.subTest(priority=priority), self.assertRaises(DeskError):
                self.request(priority=priority)

    def test_brand_shapes_and_duplicate_claims_rejected(self):
        claim = {'id':'x','text':'Fact','source':'Source'}
        for claims in ({}, [], [None], [claim,claim], [{'id':[],'text':'Fact','source':'Source'}]):
            with self.subTest(claims=claims), self.assertRaises(DeskError):
                self.write('client/create', name='C', voice='V', claims=claims)

    def test_missing_customer_not_found(self):
        with self.assertRaises(DeskError) as caught:
            self.request('does-not-exist')
        self.assertEqual(caught.exception.status, 404)

    def test_export_current_history_and_source_snapshot(self):
        identifier = self.review()
        self.save(identifier, files={'landing.md':'Second','email-01.txt':'Hello'}, note='Expanded')
        with zipfile.ZipFile(io.BytesIO(self.desk.export(identifier))) as archive:
            self.assertEqual(archive.read('current/landing.md'), b'Second')
            self.assertEqual(archive.read('revisions/1/landing.md'), b'# Real copy')
            metadata = json.loads(archive.read('request.json'))
            self.assertEqual(metadata['drafts'][0]['sources'], ['c1'])
            self.assertIn(b'nothing was emailed', archive.read('DELIVERY.txt'))

    def test_export_without_draft_does_not_claim_delivery(self):
        with self.assertRaises(DeskError):
            self.desk.export(self.request())

    def test_demo_contains_six_finished_documents_and_reloads_once(self):
        identifier = load_example(self.desk)
        self.assertEqual(load_example(Desk(self.path)), identifier)
        item = self.item(identifier)
        self.assertEqual(len(item['drafts'][0]['files']), 6)
        self.assertEqual(len([r for r in self.desk.snapshot()['requests'] if r['client_id']==item['client_id']]), 2)
        self.assertEqual(item['status'], 'review')

    def test_http_real_server_and_bad_requests(self):
        server = make_server(self.desk, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with urllib.request.urlopen(base) as response:
                self.assertIn(b'Hive Copy Desk', response.read())
            with urllib.request.urlopen(base+'/api/state') as response:
                self.assertEqual(json.load(response)['clients'][0]['id'], self.client)
            body = json.dumps({'operation_id':'http-1','client_id':self.client,'title':'HTTP request','kind':'Email','brief':'HTTP brief'}).encode()
            request = urllib.request.Request(base+'/api/request/create',data=body,headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request) as response:
                identifier = json.load(response)['id']
            self.action(identifier,'start')
            self.save(identifier)
            with urllib.request.urlopen(base+'/api/export/'+identifier) as response:
                self.assertEqual(response.headers['Content-Type'],'application/zip')
                with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
                    self.assertIn('current/landing.md',archive.namelist())
            for data, content_type, status in ((b'[]','application/json',400),(b'{','application/json',400),
                    (b'{}','text/plain',415),(b'{"operation_id":"nonfinite","n":1e400}','application/json',400)):
                request = urllib.request.Request(base+'/api/request/create',data=data,headers={'Content-Type':content_type})
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(request)
                self.assertEqual(caught.exception.code,status)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
