#!/usr/bin/env python3
"""Real SQLite, revision, ZIP and loopback HTTP exercises; no provider calls."""
import concurrent.futures
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
import press

DEMO = json.loads((Path(__file__).with_name('demo.json')).read_text(encoding='utf-8'))

class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'workspace.sqlite3'
        self.store = press.Store(self.db)
        self.view = self.store.create(copy.deepcopy(DEMO))
    def tearDown(self):
        self.tmp.cleanup()
    def save(self, doc=None):
        self.view = self.store.save(self.view['id'], self.view['revision'], doc or self.view['document'])
        return self.view
    def review_all(self):
        for iid in press.IDS:
            self.view = self.store.save(self.view['id'], self.view['revision'], None, review=iid)
        return self.view
    def test_four_distinct_topics_preserve_the_interview(self):
        d = self.view['document']
        self.assertEqual(d['original_interview'], DEMO['interview'])
        self.assertEqual(len(d['sources']), 4)
        self.assertEqual(len({i['body'] for i in d['issues']}), 4)
        self.assertEqual(d['issues'][0]['scheduled_utc'], '2026-10-06T14:00:00Z')
        self.assertEqual(d['issues'][3]['scheduled_utc'], '2026-10-27T14:00:00Z')
        for n, issue in enumerate(d['issues']):
            self.assertIn(issue['body'], d['sources'][n]['text'])
            self.assertEqual(issue['source_ids'], [f's{n+1}'])
    def test_real_database_reopen_retains_copy_and_revision(self):
        d = self.view['document']; d['issues'][0]['body'] = 'Edited text — café 東京.'
        self.save(d)
        reopened = press.Store(self.db).get(self.view['id'])
        self.assertEqual(reopened, self.view)
        self.assertEqual(reopened['revision'], 2)
    def test_stale_revision_does_not_overwrite(self):
        initial = copy.deepcopy(self.view)
        self.save()
        with self.assertRaises(press.Conflict):
            self.store.save(initial['id'], initial['revision'], initial['document'])
        self.assertEqual(self.store.get(initial['id']), self.view)
    def test_two_concurrent_writers_have_one_winner(self):
        barrier = threading.Barrier(2)
        def write(n):
            d = copy.deepcopy(self.view['document']); d['notes'] = str(n)
            barrier.wait()
            try:
                return self.store.save(self.view['id'], 1, d)['revision']
            except press.Conflict:
                return 'conflict'
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(write, [1, 2]))
        self.assertCountEqual(results, [2, 'conflict'])
        self.assertEqual(len(self.store.history(self.view['id'])), 2)
    def test_history_retains_original_and_edited_snapshots(self):
        first = copy.deepcopy(self.view)
        d = self.view['document']; d['notes'] = 'New research note'
        self.save(d)
        self.assertEqual(self.store.get(first['id'], 1), first)
        self.assertEqual([h['revision'] for h in self.store.history(first['id'])], [2, 1])
    def test_original_interview_cannot_be_replaced_by_save(self):
        d = self.view['document']; d['original_interview'] = 'A substituted transcript'
        with self.assertRaises(press.Invalid): self.save(d)
        self.assertEqual(self.store.get(self.view['id'])['revision'], 1)
    def test_forged_review_tokens_are_ignored(self):
        for i in self.view['document']['issues']:
            i['reviewed_hash'] = press.fingerprint(self.view['document'], i)
        self.save()
        self.assertEqual(len(self.view['review_needed']), 4)
    def test_reviewed_copy_edit_reopens_only_changed_issue(self):
        self.review_all()
        self.assertEqual(self.view['review_needed'], [])
        self.view['document']['issues'][1]['body'] += '\nEdited conclusion.'
        self.save()
        self.assertEqual(self.view['review_needed'], ['week2: source and copy review needed'])
    def test_working_source_change_invalidates_affected_review(self):
        self.review_all()
        self.view['document']['sources'][2]['text'] += '\nCorrected source.'
        self.save()
        self.assertEqual(self.view['review_needed'], ['week3: source and copy review needed'])
        self.assertEqual(self.view['document']['original_interview'], DEMO['interview'])
    def test_brand_change_invalidates_all_reviews(self):
        self.review_all()
        self.view['document']['brand']['footer'] = 'New footer.'
        self.save()
        self.assertEqual(len(self.view['review_needed']), 4)
    def test_date_change_invalidates_only_its_issue(self):
        self.review_all()
        self.view['document']['issues'][3]['scheduled_utc'] = '2026-10-28T14:30:00Z'
        self.save()
        self.assertEqual(self.view['review_needed'], ['week4: source and copy review needed'])
    def test_notes_change_retains_reviews(self):
        self.review_all()
        self.view['document']['notes'] += '\nInternal production note.'
        self.save()
        self.assertEqual(self.view['review_needed'], [])
    def test_unknown_or_duplicate_source_references_are_rejected(self):
        for refs in (['s99'], ['s1','s1'], [{}], [], 's1'):
            with self.subTest(refs=refs):
                d = copy.deepcopy(self.view['document']); d['issues'][0]['source_ids'] = refs
                with self.assertRaises(press.Invalid): self.save(d)
        self.assertEqual(self.store.get(self.view['id'])['revision'], 1)
    def test_invalid_intake_and_date_boundaries(self):
        for change in ({'interview':'Only one topic'}, {'start_date':'9999-12-30'},
                       {'start_date':None}, {'title':[]}, {'accent':'red; bad'}, {'client':True}):
            with self.subTest(change=change):
                with self.assertRaises(press.Invalid): self.store.create({**DEMO, **change})
    def test_invalid_document_shapes_and_nonfinite_values(self):
        docs = [None, [], {}, {**self.view['document'], 'issues': [None]*4},
                {**self.view['document'], 'extra': float('inf')}]
        for d in docs:
            with self.subTest(doc=d):
                with self.assertRaises(press.Invalid): self.store.save(self.view['id'], 1, d)
        for value in (True, 1.0, '1', None):
            with self.assertRaises(press.Invalid): self.store.save(self.view['id'], value, self.view['document'])
    def test_bad_schedule_and_multiline_subject_rejected(self):
        for key, value in [('scheduled_utc','2026-02-30T00:00:00Z'), ('scheduled_utc',3),
                           ('scheduled_utc','2026-10-06T14:00:00+01:00'), ('subject','Hello\r\nBcc: x')]:
            d = copy.deepcopy(self.view['document']); d['issues'][0][key] = value
            with self.assertRaises(press.Invalid): self.save(d)
    def test_ready_export_requires_reviews_and_unique_content(self):
        with self.assertRaises(press.Conflict): press.export_package(self.view, ready=True)
        self.review_all()
        self.view['document']['issues'][1]['subject'] = self.view['document']['issues'][0]['subject']
        self.save(); self.review_all()
        with self.assertRaises(press.Conflict): press.export_package(self.view, ready=True)
    def test_zip_contains_original_files_four_issues_and_truthful_status(self):
        self.review_all()
        data = press.export_package(self.view, ready=True)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            self.assertEqual(z.read('original-interview.txt').decode(), DEMO['interview'])
            manifest = json.loads(z.read('manifest.json'))
            self.assertEqual(manifest['status'], 'REVIEWED_HANDOFF')
            self.assertEqual(manifest['delivery_status'], 'NOT_SENT')
            self.assertEqual(len([n for n in z.namelist() if n.endswith('.html') and '/' not in n]), 4)
            for name, meta in manifest['files'].items():
                self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(), meta['sha256'])
                self.assertEqual(len(z.read(name)), meta['bytes'])
            self.assertEqual(z.read('editorial-calendar.ics').count(b'BEGIN:VEVENT'), 4)
            self.assertIn(b'STATUS:TENTATIVE', z.read('editorial-calendar.ics'))
            self.assertIn(b'NOT_SENT', z.read('schedule.csv'))
            self.assertIn(b'neither schedules nor sends', z.read('HANDOFF.txt'))
    def test_html_escapes_entered_copy_and_has_working_brand(self):
        d = self.view['document']; d['issues'][0]['body'] = '<script>alert(1)</script> & café'
        rendered = press.render(d, d['issues'][0], preview=True)
        self.assertNotIn('<script>', rendered)
        self.assertIn('&lt;script&gt;', rendered)
        self.assertIn(d['brand']['accent'], rendered)
        self.assertIn('NOT SENT', rendered)
    def test_client_projects_stay_separate_and_unknown_ids_fail(self):
        other = self.store.create({**DEMO, 'client':'Different client', 'interview':'A\nAlpha\n\nB\nBeta\n\nC\nGamma\n\nD\nDelta'})
        self.assertNotEqual(other['id'], self.view['id'])
        self.assertNotIn('Alpha', self.store.get(self.view['id'])['document']['original_interview'])
        with self.assertRaises(press.Missing): self.store.get('missing')
        with self.assertRaises(press.Missing): self.store.save('missing', 1, other['document'])
        with self.assertRaises(press.Missing): self.store.get(other['id'], 999)
        self.assertEqual(len(self.store.listing()), 2)

class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = press.Store(Path(cls.tmp.name)/'http.sqlite3')
        cls.server = ThreadingHTTPServer(('127.0.0.1',0),press.handler(cls.store))
        cls.thread = threading.Thread(target=cls.server.serve_forever,daemon=True); cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(); cls.tmp.cleanup()
    def request(self, path, method='GET', value=None, raw=None):
        data = raw if raw is not None else (json.dumps(value).encode() if value is not None else None)
        req = urllib.request.Request(self.base+path, method=method, data=data,
            headers={'Content-Type':'application/json'} if data else {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r: return r.status,r.read(),r.headers
        except urllib.error.HTTPError as e: return e.code,e.read(),e.headers
    def test_real_http_create_save_preview_history_export(self):
        code, body, _ = self.request('/api/demo','POST',{})
        self.assertEqual(code,201); v=json.loads(body); pid=v['id']
        v['document']['issues'][0]['body']='Real HTTP edited copy.'
        code, body, _ = self.request('/api/projects/'+pid,'PUT',{'expected_revision':1,'document':v['document']})
        self.assertEqual(code,200); self.assertEqual(json.loads(body)['revision'],2)
        code, body, _ = self.request('/preview/'+pid+'/week1'); self.assertEqual(code,200); self.assertIn(b'Real HTTP edited',body)
        code, body, _ = self.request('/api/projects/'+pid+'/history'); self.assertEqual(len(json.loads(body)),2)
        code, body, headers = self.request('/export/'+pid); self.assertEqual(code,200); self.assertEqual(headers['Content-Type'],'application/zip')
        with zipfile.ZipFile(io.BytesIO(body)) as z: self.assertIn(b'Real HTTP edited',z.read('week1.txt'))
        self.assertEqual(self.request('/export/'+pid+'?ready=1')[0],409)
        self.assertEqual(self.request('/api/projects/'+pid+'?revision=1')[0],200)
    def test_http_invalid_json_shape_and_unknown_routes(self):
        for raw in (b'{',b'[]',b'null',b'NaN',b'\xff'):
            self.assertEqual(self.request('/api/projects','POST',raw=raw)[0],400)
        self.assertEqual(self.request('/missing')[0],404)
        self.assertEqual(self.request('/api/projects/missing')[0],404)
        self.assertEqual(self.request('/api/projects/missing?revision=abc')[0],400)
    def test_http_review_and_stale_save_contract(self):
        _,body,_=self.request('/api/projects','POST',DEMO); v=json.loads(body)
        path='/api/projects/'+v['id']
        for iid in press.IDS:
            code,body,_=self.request(path+'/review/'+iid,'POST',{'expected_revision':v['revision']})
            self.assertEqual(code,200); v=json.loads(body)
        self.assertEqual(v['review_needed'],[])
        self.assertEqual(self.request('/export/'+v['id']+'?ready=1')[0],200)
        self.assertEqual(self.request(path,'PUT',{'expected_revision':1,'document':v['document']})[0],409)
    def test_http_serves_editor_and_list_and_preview_not_found(self):
        code,body,_=self.request('/'); self.assertEqual(code,200); self.assertIn(b'Pressroom',body)
        self.assertEqual(self.request('/api/projects')[0],200)
        _,body,_=self.request('/api/demo','POST',{}); v=json.loads(body)
        self.assertEqual(self.request('/preview/'+v['id']+'/no-issue')[0],404)

if __name__=='__main__':
    unittest.main(verbosity=2)
