"""Real SQLite, HTTP and concurrent-writer regression tests; no provider calls."""
import base64
import concurrent.futures
import hashlib
import http.client
import io
import json
import tempfile
import threading
import unittest
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from server import DEFAULT_BRAND, MAX_FILE, Desk, Problem, handler_for, sample_sources


class DeskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / 'desk.sqlite3'
        self.desk = Desk(self.db)
        self.ws = self.desk.create_workspace({'name': 'Fictional test studio'})
        self.wid = self.ws['id']

    def tearDown(self):
        self.temp.cleanup()

    def create(self, title='Brand package', priority=100):
        return self.desk.create_request({'workspace_id': self.wid, 'title': title, 'brief': 'Editable original source files.', 'priority': priority})['request_id']

    def req(self, rid):
        return next(r for r in self.desk.snapshot(self.wid)['requests'] if r['id'] == rid)

    def change(self, rid, action, **values):
        return self.desk.change_request(rid, {'version': self.req(rid)['version'], 'action': action, **values})

    def fail(self, code, function, *args):
        with self.assertRaises(Problem) as caught:
            function(*args)
        self.assertEqual(caught.exception.status, code)

    def upload(self, rid, name='design.txt', content=b'editable source'):
        return self.change(rid, 'asset', name=name, content_base64=base64.b64encode(content).decode())

    def test_workspace_and_requests_survive_reopen(self):
        rid = self.create()
        self.assertEqual(Desk(self.db).snapshot(self.wid), self.desk.snapshot(self.wid))
        self.assertEqual(self.req(rid)['status'], 'production')
        self.assertEqual(len(Desk(self.db).list_workspaces()), 1)

    def test_two_requests_have_exactly_one_active(self):
        first, second = self.create(), self.create('Second request')
        self.assertEqual(self.req(first)['status'], 'production')
        self.assertEqual(self.req(second)['status'], 'queued')

    def test_acceptance_flow_revision_then_next_production(self):
        first, second = self.create(), self.create('Social card')
        self.change(first, 'sample')
        self.assertEqual(self.req(first)['status'], 'review')
        self.change(first, 'revise', note='Use the revised headline.')
        self.assertEqual(self.req(second)['status'], 'queued')
        ws = self.desk.snapshot(self.wid)
        brand = {**ws['brand'], 'headline': 'A clearer headline for the next version.'}
        self.desk.update_brand(self.wid, {'version': ws['version'], 'brand': brand})
        self.change(first, 'sample')
        snapshot = self.change(first, 'approve')
        self.assertEqual(self.req(first)['status'], 'complete')
        self.assertEqual(self.req(second)['status'], 'production')
        self.assertEqual(len(snapshot['assets']), 8)
        kinds = [e['kind'] for e in self.req(first)['events']]
        self.assertEqual(kinds, ['submitted', 'sample', 'revise', 'sample', 'approve'])
        self.assertEqual(self.req(second)['events'][-1]['kind'], 'started')

    def test_queue_advances_by_priority_not_submission_order(self):
        first = self.create()
        later = self.create('Later', 100)
        urgent = self.create('Urgent', 30)
        self.change(later, 'priority', priority=20)
        self.change(first, 'sample')
        self.change(first, 'approve')
        self.assertEqual(self.req(later)['status'], 'production')
        self.assertEqual(self.req(urgent)['status'], 'queued')

    def test_workspaces_have_independent_queues(self):
        self.create()
        other = self.desk.create_workspace({'name': 'Other customer'})
        result = self.desk.create_request({'workspace_id': other['id'], 'title': 'Brand', 'brief': 'Different source'})
        self.assertEqual(result['workspace']['requests'][0]['status'], 'production')
        self.assertEqual(len(self.desk.snapshot(self.wid)['requests']), 1)

    def test_sample_exports_editable_sources_and_sha256_manifest(self):
        rid = self.create()
        self.change(rid, 'sample')
        with zipfile.ZipFile(io.BytesIO(self.desk.export(rid))) as archive:
            self.assertIn('current/landing.html', archive.namelist())
            self.assertIn('current/tokens.css', archive.namelist())
            self.assertIn('current/brand.md', archive.namelist())
            self.assertIn('current/START-HERE.txt', archive.namelist())
            self.assertIn(b'fictional', archive.read('current/landing.html'))
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(len(manifest), 4)
            for item in manifest:
                name = f"history/{item['revision']}/{item['id']}/{item['name']}"
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), item['sha256'])
            self.assertEqual(json.loads(archive.read('request.json'))['status'], 'review')

    def test_revision_export_keeps_both_original_and_latest(self):
        rid = self.create()
        self.upload(rid, 'source.txt', b'first original')
        self.change(rid, 'deliver', note='First source')
        self.change(rid, 'revise', note='Change source')
        self.upload(rid, 'source.txt', b'second revised')
        self.change(rid, 'deliver', note='Revision delivered')
        with zipfile.ZipFile(io.BytesIO(self.desk.export(rid))) as archive:
            self.assertEqual(archive.read('current/source.txt'), b'second revised')
            history = [archive.read(n) for n in archive.namelist() if n.startswith('history/')]
            self.assertEqual(history, [b'first original', b'second revised'])
            self.assertEqual(len(archive.namelist()), len(set(archive.namelist())))

    def test_cannot_approve_undelivered_request(self):
        rid = self.create()
        self.fail(409, self.change, rid, 'approve')
        self.assertEqual(self.req(rid)['version'], 1)

    def test_cannot_deliver_empty_sources(self):
        rid = self.create()
        with self.assertRaises(Problem):
            self.change(rid, 'deliver', note='No sources')
        self.assertEqual(self.req(rid)['status'], 'production')

    def test_revision_requires_new_sources_before_redelivery(self):
        rid = self.create()
        self.change(rid, 'sample')
        self.change(rid, 'revise', note='Please change headline')
        with self.assertRaises(Problem) as caught:
            self.change(rid, 'deliver', note='Unchanged sources')
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(self.req(rid)['status'], 'revision')

    def test_empty_revision_note_is_rejected_without_mutation(self):
        rid = self.create()
        self.change(rid, 'sample')
        before = self.req(rid)
        with self.assertRaises(Problem):
            self.change(rid, 'revise', note='  ')
        self.assertEqual(self.req(rid), before)

    def test_binary_unicode_source_is_preserved_exactly(self):
        rid = self.create()
        content = b'\x00\xff\x01editable\r\n'
        self.upload(rid, '招牌.src', content)
        asset = self.desk.snapshot(self.wid)['assets'][0]
        self.assertEqual(self.desk.asset(asset['id'])['content'], content)
        with zipfile.ZipFile(io.BytesIO(self.desk.export(rid))) as archive:
            self.assertEqual(archive.read('current/招牌.src'), content)

    def test_brand_library_bytes_survive_reopen(self):
        data = {'name': 'brand.css', 'content_base64': base64.b64encode(b':root { --color: blue; }').decode()}
        result = self.desk.add_brand_asset(self.wid, data)
        asset = Desk(self.db).asset(result['asset_id'])
        self.assertIsNone(asset['request_id'])
        self.assertEqual(asset['content'], b':root { --color: blue; }')

    def test_stale_request_version_does_not_duplicate_work(self):
        rid = self.create()
        payload = {'version': 1, 'action': 'sample'}
        self.desk.change_request(rid, payload)
        before = self.desk.snapshot(self.wid)
        self.fail(409, self.desk.change_request, rid, payload)
        self.assertEqual(self.desk.snapshot(self.wid), before)

    def test_stale_brand_version_does_not_overwrite(self):
        payload = {'version': 1, 'brand': {**DEFAULT_BRAND, 'name': 'First save'}}
        self.desk.update_brand(self.wid, payload)
        payload['brand']['name'] = 'Stale save'
        self.fail(409, self.desk.update_brand, self.wid, payload)
        self.assertEqual(self.desk.snapshot(self.wid)['brand']['name'], 'First save')

    def test_concurrent_first_requests_enforce_one_active(self):
        def create(index):
            return Desk(self.db).create_request({'workspace_id': self.wid, 'title': str(index), 'brief': 'Concurrent test'})
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(create, range(12)))
        requests = self.desk.snapshot(self.wid)['requests']
        self.assertEqual(len(requests), 12)
        self.assertEqual(sum(r['status'] == 'production' for r in requests), 1)
        self.assertEqual(sum(r['status'] == 'queued' for r in requests), 11)

    def test_concurrent_delivery_has_one_success_one_conflict(self):
        rid = self.create()
        barrier = threading.Barrier(2)
        def deliver(_):
            barrier.wait()
            try:
                Desk(self.db).change_request(rid, {'version': 1, 'action': 'sample'})
                return 200
            except Problem as exc:
                return exc.status
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(deliver, range(2)))
        self.assertEqual(sorted(results), [200, 409])
        self.assertEqual(len(self.desk.snapshot(self.wid)['assets']), 4)

    def test_invalid_filenames_leave_no_partial_assets(self):
        rid = self.create()
        for name in ('../source', 'folder/source', 'folder\\source', '.', '..', 'bad\nname', 'bad\x00name'):
            with self.subTest(name=name), self.assertRaises(Problem):
                self.upload(rid, name)
        self.assertEqual(self.desk.snapshot(self.wid)['assets'], [])
        self.assertEqual(self.req(rid)['version'], 1)

    def test_sample_failure_rolls_back_all_files_and_state(self):
        rid = self.create()
        original = self.desk.store_asset
        count = 0
        def fail_second(*args):
            nonlocal count
            count += 1
            if count == 2:
                raise Problem('Simulated interrupted write', 503)
            return original(*args)
        with patch.object(self.desk, 'store_asset', side_effect=fail_second):
            self.fail(503, self.change, rid, 'sample')
        self.assertEqual(self.desk.snapshot(self.wid)['assets'], [])
        self.assertEqual(self.req(rid)['version'], 1)

    def test_priority_types_are_not_silently_coerced(self):
        for value in (True, 1.2, '1', None, [], -1, 1_000_001):
            with self.subTest(value=value), self.assertRaises(Problem):
                self.create(priority=value)
        self.assertEqual(self.desk.snapshot(self.wid)['requests'], [])

    def test_shape_errors_and_unknown_ids_are_explicit(self):
        for value in (None, [], 'bad', 3):
            self.fail(400, self.desk.create_workspace, value)
        self.fail(404, self.desk.snapshot, '0' * 32)
        self.fail(404, self.desk.asset, '0' * 32)

    def test_completed_request_cannot_be_changed(self):
        rid = self.create()
        self.change(rid, 'sample')
        self.change(rid, 'approve')
        before = self.desk.snapshot(self.wid)
        for action in ('sample', 'approve', 'revise', 'priority', 'brief', 'deliver', 'asset'):
            with self.subTest(action=action), self.assertRaises(Problem):
                self.change(rid, action, note='No', brief='No', priority=1)
        self.assertEqual(self.desk.snapshot(self.wid), before)

    def test_source_input_is_escaped_in_original_sample(self):
        brand = {**DEFAULT_BRAND, 'headline': '<b>Literal title</b>'}
        source = sample_sources(brand)['landing.html']
        self.assertIn(b'&lt;b&gt;Literal title&lt;/b&gt;', source)
        self.assertNotIn(b'<b>Literal title</b>', source)

    def test_file_size_and_encoding_are_checked(self):
        for data in ({'name': 'x', 'content_base64': 'invalid?='}, {'name': 'x', 'content_base64': ''}, {'name': 'x', 'content_base64': []}):
            self.fail(400, self.desk.add_brand_asset, self.wid, data)
        data = {'name': 'x', 'content_base64': base64.b64encode(b'x' * (MAX_FILE + 1)).decode()}
        self.fail(400, self.desk.add_brand_asset, self.wid, data)

    def test_bad_color_and_brand_shape_do_not_change_saved_brand(self):
        before = self.desk.snapshot(self.wid)
        for brand in ({}, [], {**DEFAULT_BRAND, 'accent': 'green'}, {**DEFAULT_BRAND, 'body': None}):
            self.fail(400, self.desk.update_brand, self.wid, {'version': 1, 'brand': brand})
        self.assertEqual(self.desk.snapshot(self.wid), before)

    def test_brief_edits_are_recorded_without_advancing_queue(self):
        rid = self.create()
        second = self.create('Second')
        self.change(rid, 'brief', brief='Updated brief')
        self.assertEqual(self.req(rid)['brief'], 'Updated brief')
        self.assertEqual(self.req(rid)['events'][-1]['note'], 'Updated brief')
        self.assertEqual(self.req(second)['status'], 'queued')


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.desk = Desk(Path(self.temp.name) / 'desk.sqlite3')
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.desk))
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, method, path, data=None, raw=None, mime='application/json'):
        connection = http.client.HTTPConnection('127.0.0.1', self.http.server_port, timeout=5)
        body = json.dumps(data).encode() if raw is None and data is not None else raw
        headers = {'Content-Type': mime} if method == 'POST' else {}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_real_http_two_request_workflow_and_zip(self):
        code, _, body = self.request('POST', '/api/workspaces', {'name': 'HTTP sample'})
        self.assertEqual(code, 201)
        wid = json.loads(body)['id']
        ids = []
        for title in ('Brand landing package', 'Second design'):
            code, _, body = self.request('POST', '/api/requests', {'workspace_id': wid, 'title': title, 'brief': 'Original editable design'})
            self.assertEqual(code, 201)
            ids.append(json.loads(body)['request_id'])
        rid = ids[0]
        for action, version, extra in [('sample', 1, {}), ('revise', 2, {'note': 'Change heading'}), ('sample', 3, {}), ('approve', 4, {})]:
            code, _, body = self.request('POST', '/api/requests/' + rid, {'action': action, 'version': version, **extra})
            self.assertEqual(code, 200, body)
        rows = {r['id']: r for r in json.loads(body)['requests']}
        self.assertEqual(rows[ids[0]]['status'], 'complete')
        self.assertEqual(rows[ids[1]]['status'], 'production')
        code, headers, body = self.request('GET', '/api/requests/' + rid + '/export')
        self.assertEqual(code, 200)
        self.assertEqual(headers['Content-Type'], 'application/zip')
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            self.assertEqual(len(json.loads(archive.read('manifest.json'))), 8)

    def test_http_rejects_malformed_json_and_missing_routes(self):
        for raw in (b'{', b'null', b'[]', b'"string"', b'\xff'):
            self.assertEqual(self.request('POST', '/api/workspaces', raw=raw)[0], 400)
        self.assertEqual(self.request('POST', '/api/workspaces', {'name': 'x'}, mime='text/plain')[0], 415)
        self.assertEqual(self.request('GET', '/missing')[0], 404)
        self.assertEqual(self.request('GET', '/api/workspaces/' + '0' * 32)[0], 404)
        self.assertEqual(self.request('POST', '/api/workspaces', raw=b'')[0], 413)

    def test_http_homepage_and_binary_attachment(self):
        code, headers, body = self.request('GET', '/')
        self.assertEqual(code, 200)
        self.assertIn('text/html', headers['Content-Type'])
        self.assertIn(b'Fieldwork', body)
        ws = self.desk.create_workspace({'name': 'Files'})
        payload = {'name': '招牌.css', 'content_base64': base64.b64encode(b'original\x00\xff').decode()}
        code, _, response = self.request('POST', '/api/workspaces/' + ws['id'] + '/assets', payload)
        self.assertEqual(code, 200)
        aid = json.loads(response)['asset_id']
        code, headers, body = self.request('GET', '/api/assets/' + aid)
        self.assertEqual(code, 200)
        self.assertEqual(body, b'original\x00\xff')
        self.assertIn("filename*=UTF-8''", headers['Content-Disposition'])
        self.assertIn('%E6%8B%9B%E7%89%8C.css', headers['Content-Disposition'])
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')


if __name__ == '__main__':
    unittest.main(verbosity=2)
