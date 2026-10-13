"""Real SQLite, HTTP and export regressions; no service mocks or sends."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date
import hashlib
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

import app

DEMO = json.loads((Path(__file__).parent / 'demo.json').read_text())


class NewsletterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'newsletter.sqlite3'
        self.store = app.Store(self.path)
        self.pack = self.store.create(deepcopy(DEMO))

    def tearDown(self):
        self.temp.cleanup()

    def update(self, changes, pack=None):
        pack = self.pack if pack is None else pack
        return self.store.update(pack['id'], {'version': pack['version'], 'issue_id': 'issue-1', 'changes': changes})

    def test_four_distinct_issues_keep_each_segment_once(self):
        issues = self.pack['issues']
        self.assertEqual(4, len({i['body'] for i in issues}))
        self.assertEqual([s['id'] for s in self.pack['segments']], [s for i in issues for s in i['source_ids']])
        self.assertTrue(all(i['body'] == app.source_excerpt(self.pack, i) for i in issues))
        self.assertEqual(['2026-10-06', '2026-10-13', '2026-10-20', '2026-10-27'], [i['send_date'] for i in issues])

    def test_non_multiple_of_four_has_no_dropped_sections(self):
        for count in (4, 5, 7, 13, 80):
            raw = deepcopy(DEMO)
            raw['segments'] = [deepcopy(DEMO['segments'][i % 8]) for i in range(count)]
            pack = app.make_pack(raw)
            self.assertEqual(count, sum(len(i['source_ids']) for i in pack['issues']))
            self.assertTrue(all(i['source_ids'] for i in pack['issues']))

    def test_source_research_notes_are_not_in_published_email(self):
        pack = deepcopy(self.pack)
        pack['segments'][0]['notes'] = 'Private research note not for publication'
        pack['issues'][0]['notes'] = 'Private production note not for publication'
        rendered = '\n'.join(app.render(pack, pack['issues'][0]))
        self.assertNotIn('not for publication', rendered)
        self.assertEqual(DEMO['segments'][0]['text'], pack['segments'][0]['text'])

    def test_restart_recovers_real_saved_edits_and_history(self):
        updated = self.update({'body': 'A new editable body.', 'notes': 'Rewrite requested.'})
        reopened = app.Store(self.path)
        self.assertEqual(updated, reopened.get(updated['id']))
        versions = reopened.history(updated['id'])
        self.assertEqual([1, 2], [v['version'] for v in versions])
        self.assertEqual(self.pack, versions[0])
        self.assertEqual('A new editable body.', versions[1]['issues'][0]['body'])

    def test_stale_save_preserves_newer_revision(self):
        updated = self.update({'subject': 'First writer'})
        with self.assertRaises(app.Problem) as cm:
            self.update({'subject': 'Stale writer'})
        self.assertEqual(409, cm.exception.status)
        self.assertEqual(updated, self.store.get(self.pack['id']))
        self.assertEqual(2, len(self.store.history(self.pack['id'])))

    def test_two_actual_writers_have_one_winner(self):
        barrier = threading.Barrier(2)
        def writer(name):
            barrier.wait()
            try:
                return self.update({'subject': name})['version']
            except app.Problem as exc:
                return exc.status
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(writer, ('First', 'Second')))
        self.assertEqual([2, 409], sorted(results))
        self.assertEqual(2, len(self.store.history(self.pack['id'])))

    def test_external_state_requires_reference_and_does_not_send(self):
        with self.assertRaises(app.Problem):
            self.update({'status': 'sent_externally'})
        updated = self.update({'status': 'scheduled_externally', 'delivery_reference': 'Existing provider job: demo-123'})
        self.assertEqual('scheduled_externally', updated['issues'][0]['status'])
        self.assertEqual(2, updated['version'])

    def test_edit_clears_old_delivery_state_and_keeps_history(self):
        scheduled = self.update({'status': 'scheduled_externally', 'delivery_reference': 'demo-123'})
        updated = self.update({'body': 'Revised body', 'status': 'sent_externally', 'delivery_reference': 'demo-456'}, scheduled)
        self.assertEqual('draft', updated['issues'][0]['status'])
        self.assertEqual('', updated['issues'][0]['delivery_reference'])
        self.assertEqual('demo-123', self.store.history(self.pack['id'])[1]['issues'][0]['delivery_reference'])

    def test_notes_only_edit_keeps_state(self):
        ready = self.update({'status': 'ready'})
        updated = self.update({'notes': 'Review comment'}, ready)
        self.assertEqual('ready', updated['issues'][0]['status'])

    def test_brand_update_applies_to_preview_and_resets_drafts(self):
        ready = self.update({'status': 'ready'})
        brand = deepcopy(ready['brand']); brand['name'] = 'Changed publication'
        updated = self.store.update(ready['id'], {'version': 2, 'brand': brand})
        self.assertTrue(all(i['status'] == 'draft' for i in updated['issues']))
        self.assertIn('Changed publication', app.render(updated, updated['issues'][0])[0])

    def test_validation_failure_rolls_back_all_edits(self):
        with self.assertRaises(app.Problem):
            self.update({'subject': 'Must not persist', 'send_date': '2026-02-30'})
        self.assertEqual(self.pack, self.store.get(self.pack['id']))
        self.assertEqual(1, len(self.store.history(self.pack['id'])))

    def test_bad_intake_shapes_and_calendar_edges(self):
        for raw in (None, [], {}, {**DEMO, 'segments': {}}, {**DEMO, 'segments': DEMO['segments'][:3]},
                    {**DEMO, 'first_send': '9999-12-31'}, {**DEMO, 'first_send': '20260203'},
                    {**DEMO, 'brand': []}):
            with self.subTest(raw=type(raw).__name__), self.assertRaises(app.Problem):
                app.make_pack(raw)

    def test_bad_update_shapes_are_controlled_errors(self):
        invalid = [None, [], {'version': True}, {'version': 1, 'issue_id': 'missing', 'changes': {'body': 'x'}},
                   {'version': 1, 'issue_id': 'issue-1', 'changes': {'status': []}},
                   {'version': 1, 'issue_id': 'issue-1', 'changes': {'source_ids': ['S002']}},
                   {'version': 1, 'issue_id': 'issue-1', 'changes': {'body': '\ud800'}}]
        for raw in invalid:
            with self.subTest(raw=repr(raw)), self.assertRaises(app.Problem):
                self.store.update(self.pack['id'], raw)
        self.assertEqual(self.pack, self.store.get(self.pack['id']))

    def test_html_escapes_editor_text_and_brand_fields(self):
        pack = deepcopy(self.pack)
        pack['brand']['name'] = '<b>Publication</b>'
        issue = pack['issues'][0]; issue['body'] = '<i>plain supplied text</i> & notes'
        page, plain = app.render(pack, issue)
        self.assertIn('&lt;b&gt;Publication&lt;/b&gt;', page)
        self.assertIn('&lt;i&gt;plain supplied text&lt;/i&gt; &amp; notes', page)
        self.assertIn('<i>plain supplied text</i>', plain)

    def test_brand_url_validation(self):
        for value in ('relative/path', 'https://[bad', 'https://user:password@example.test'):
            with self.subTest(value=value), self.assertRaises(app.Problem):
                app.brand_data({**DEMO['brand'], 'cta_url': value})
        brand = app.brand_data({**DEMO['brand'], 'cta_url': 'https://example.test/?a=1&b=2', 'cta_text': 'Read more'})
        pack = {**self.pack, 'brand': brand}
        self.assertIn('href="https://example.test/?a=1&amp;b=2"', app.render(pack, pack['issues'][0])[0])

    def test_zip_has_editable_files_hashes_and_no_send_claim(self):
        output = app.bundle(self.pack)
        self.assertEqual(output, app.bundle(self.pack))
        with zipfile.ZipFile(io.BytesIO(output)) as archive:
            self.assertEqual(14, len(archive.namelist()))
            manifest = json.loads(archive.read('manifest.json'))
            self.assertFalse(manifest['email_sent_by_app'])
            for name, expected in manifest['files'].items():
                self.assertEqual(expected, hashlib.sha256(archive.read(name)).hexdigest())
            self.assertEqual(self.pack, json.loads(archive.read('pack.json')))
            self.assertIn('No messages have been sent', archive.read('HANDOFF.txt').decode())

    def test_changed_body_export_does_not_assert_source_match(self):
        updated = self.update({'body': 'Editorial rewrite needing source review'})
        with zipfile.ZipFile(io.BytesIO(app.bundle(updated))) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertFalse(manifest['issues'][0]['body_matches_supplied_excerpts'])
            self.assertTrue(manifest['issues'][1]['body_matches_supplied_excerpts'])

    def test_calendar_folds_utf8_escapes_text_and_has_four_dates(self):
        pack = deepcopy(self.pack)
        pack['issues'][0]['subject'] = ('日本語é,;\\' * 20) + '\nSecond line'
        data = app.calendar(pack)
        self.assertEqual(4, data.count('BEGIN:VEVENT'))
        self.assertTrue(data.endswith('\r\n'))
        self.assertTrue(all(len(line.encode('utf-8')) <= 75 for line in data.split('\r\n')))
        unfolded = data.replace('\r\n ', '')
        self.assertIn('\\nSecond line', unfolded)
        self.assertIn('Planning item only; no email is scheduled by Fourfold'.replace(';', '\\;'), unfolded)
        self.assertIn('DTSTART;VALUE=DATE:20261027', unfolded)

    def test_deletion_cascades_history_but_stale_delete_is_rejected(self):
        self.update({'notes': 'New revision'})
        with self.assertRaises(app.Problem):
            self.store.delete(self.pack['id'], 1)
        self.store.delete(self.pack['id'], 2)
        self.assertEqual([], self.store.list())
        with sqlite3.connect(self.path) as db:
            self.assertEqual(0, db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0])

    def test_separate_clients_keep_separate_packs(self):
        other = self.store.create({**DEMO, 'client': 'Different fictional client'})
        self.update({'subject': 'Only first project'})
        self.assertEqual(other, self.store.get(other['id']))
        self.assertEqual(2, len(self.store.list()))

    def test_http_complete_workflow(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), app.handler(self.store))
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        base = f'http://127.0.0.1:{server.server_port}'
        def request(path, method='GET', raw=None):
            data = None if raw is None else json.dumps(raw).encode()
            req = Request(base + path, data=data, method=method, headers={'Content-Type': 'application/json'})
            with urlopen(req, timeout=5) as response:
                return response.status, response.read(), response.headers
        try:
            self.assertIn(b'Fourfold', request('/')[1])
            status, payload, _ = request('/api/packs', 'POST', DEMO)
            self.assertEqual(201, status); pack = json.loads(payload); path = '/api/packs/' + pack['id']
            status, payload, _ = request(path, 'PATCH', {'version': 1, 'issue_id': 'issue-1', 'changes': {'subject': 'HTTP saved subject'}})
            self.assertEqual(2, json.loads(payload)['version'])
            self.assertIn(b'HTTP saved subject', request(path + '/preview?issue=issue-1')[1])
            status, data, headers = request(path + '/export')
            self.assertEqual('application/zip', headers['Content-Type'])
            self.assertTrue(zipfile.is_zipfile(io.BytesIO(data)))
            self.assertEqual(2, len(json.loads(request(path + '/history')[1])))
            with self.assertRaises(HTTPError) as cm:
                request(path, 'PATCH', {'version': 1, 'issue_id': 'issue-1', 'changes': {'subject': 'Stale'}})
            self.assertEqual(409, cm.exception.code); cm.exception.close()
            self.assertEqual(200, request(path, 'DELETE', {'version': 2})[0])
        finally:
            server.shutdown(); server.server_close(); worker.join(5)

    def test_http_malformed_json_returns_structured_error(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), app.handler(self.store))
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        try:
            req = Request(f'http://127.0.0.1:{server.server_port}/api/packs', data=b'{broken', method='POST')
            with self.assertRaises(HTTPError) as cm:
                urlopen(req, timeout=5)
            self.assertEqual(400, cm.exception.code)
            self.assertIn('Malformed UTF-8 JSON', cm.exception.read().decode()); cm.exception.close()
        finally:
            server.shutdown(); server.server_close(); worker.join(5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
