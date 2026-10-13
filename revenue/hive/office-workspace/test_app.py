#!/usr/bin/env python3
"""Real temporary-SQLite and HTTP tests; no provider calls or mocked persistence."""
import concurrent.futures
import email
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

SPEC = importlib.util.spec_from_file_location("office_workspace_app", Path(__file__).with_name("app.py"))
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)
MEETING = "Authorized sample meeting\nACTION: Jordan | 2026-09-15 | Collect signed checklist\nACTION: Casey | - | Review onboarding notes"


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "office.db"
        self.store = app.Store(self.path)
        self.wid = self.store.create_workspace("Example client")['id']
        self.other = self.store.create_workspace("Separate client")['id']

    def tearDown(self):
        self.temp.cleanup()

    def meeting(self, body=MEETING, expected=0):
        return self.store.import_source(self.wid, "meeting-1", "Sample meeting", "meeting", body, expected)

    def document(self, body="The onboarding checklist lives in the welcome folder.", expected=0):
        return self.store.import_source(self.wid, "handbook", "Handbook", "document", body, expected)

    def problem(self, function, status=400):
        with self.assertRaises(app.Problem) as caught:
            function()
        self.assertEqual(caught.exception.status, status)

    def test_meeting_persists_and_retry_is_identical(self):
        first = self.meeting()
        task_ids = [r['id'] for r in self.store.snapshot(self.wid)['tasks']]
        second = self.meeting()
        self.assertEqual(first['source_id'], second['source_id'])
        self.assertEqual(second['version'], 1)
        self.assertTrue(second['repeated'])
        reopened = app.Store(self.path)
        self.assertEqual([r['id'] for r in reopened.snapshot(self.wid)['tasks']], task_ids)
        self.assertEqual(len(task_ids), 2)

    def test_concurrent_duplicate_import_creates_one_source(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.meeting(), range(12)))
        self.assertEqual(len({r['source_id'] for r in results}), 1)
        self.assertEqual(sum(not r['repeated'] for r in results), 1)
        self.assertEqual(len(self.store.snapshot(self.wid)['tasks']), 2)

    def test_concurrent_different_imports_do_not_overwrite(self):
        def save(body):
            try:
                return self.meeting(body)
            except app.Problem as error:
                return error.status
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(save, [MEETING, MEETING+'\nExtra context']))
        self.assertEqual(result.count(409), 1)
        self.assertEqual(self.store.snapshot(self.wid)['sources'][0]['version'], 1)

    def test_invalid_actions_rollback_everything(self):
        for line in ('ACTION: missing delimiters', 'ACTION: | - | task', 'ACTION: Jo | 2026-02-30 | task', 'ACTION: Jo | 20260915 | task', 'ACTION: Jo | - | '):
            with self.subTest(line=line):
                self.problem(lambda: self.meeting(MEETING+'\n'+line))
                self.assertEqual(self.store.snapshot(self.wid)['sources'], [])
                self.assertEqual(self.store.snapshot(self.wid)['tasks'], [])

    def test_unmarked_notes_are_not_tasks(self):
        self.meeting('Jordan may follow up tomorrow. An assumption is not an action.')
        self.assertEqual(self.store.snapshot(self.wid)['tasks'], [])

    def test_duplicate_action_lines_collapse(self):
        line = 'ACTION: Jordan | - | Review'
        self.meeting(line+'\n'+line)
        self.assertEqual(len(self.store.snapshot(self.wid)['tasks']), 1)

    def test_edit_preserves_done_and_supersedes_removed(self):
        first = self.meeting()
        task = next(r for r in self.store.snapshot(self.wid)['tasks'] if r['owner']=='Jordan')
        self.store.update_task(self.wid, task['id'], 1, 'done')
        self.meeting('New context\nACTION: Jordan | 2026-09-15 | Collect signed checklist', 1)
        tasks = self.store.snapshot(self.wid)['tasks']
        kept = next(r for r in tasks if r['id']==task['id'])
        self.assertEqual((kept['state'],kept['current'],kept['source_version']), ('done',1,2))
        removed = next(r for r in tasks if r['owner']=='Casey')
        self.assertEqual(removed['current'], 0)
        self.problem(lambda: self.store.update_task(self.wid,removed['id'],removed['revision'],'done'),409)
        self.assertEqual(self.store.source(self.wid,first['source_id'],1)['text'],MEETING)

    def test_stale_source_edit_cannot_revert_newer_version(self):
        self.document('Old policy')
        self.document('New policy',1)
        self.problem(lambda: self.document('Old policy',1),409)
        self.assertTrue(self.document('New policy',1)['repeated'])
        self.assertEqual(self.store.ask(self.wid,'policy')['citations'][0]['excerpt'],'New policy')

    def test_document_kind_does_not_extract_actions(self):
        self.document(MEETING)
        self.assertEqual(self.store.snapshot(self.wid)['tasks'],[])

    def test_current_exact_source_line_and_honest_gap(self):
        doc = self.document('Heading\nOnboarding requires a signed checklist.')
        answer = self.store.ask(self.wid,'onboarding checklist')
        self.assertEqual(answer['status'],'excerpts')
        cite = answer['citations'][0]
        self.assertEqual((cite['line'],cite['excerpt'],cite['version']),(2,'Onboarding requires a signed checklist.',1))
        self.assertIn(doc['source_id'],cite['url'])
        self.document('Heading\nOnboarding requires a reviewed checklist.',1)
        cite = self.store.ask(self.wid,'onboarding')['citations'][0]
        self.assertEqual(cite['version'],2)
        self.assertNotIn('signed',cite['excerpt'])
        self.assertEqual(self.store.ask(self.wid,'astronaut radiation')['status'],'no_answer')
        self.assertEqual(self.store.ask(self.wid,'what is the')['citations'],[])

    def test_client_isolation_for_sources_tasks_and_drafts(self):
        src = self.meeting()
        self.document()
        task = self.store.snapshot(self.wid)['tasks'][0]
        draft = self.store.save_draft(self.wid,'client@example.test','Review','Private example')
        self.assertEqual(self.store.snapshot(self.other)['tasks'],[])
        self.assertEqual(self.store.ask(self.other,'checklist')['status'],'no_answer')
        self.problem(lambda:self.store.source(self.other,src['source_id'],1),404)
        self.problem(lambda:self.store.update_task(self.other,task['id'],1,'done'),404)
        self.problem(lambda:self.store.save_draft(self.other,'x@example.test','No','No',draft['id'],1),404)
        self.problem(lambda:self.store.export(self.other,'draft',draft['id']),404)

    def test_task_and_draft_revision_conflicts(self):
        self.meeting()
        task = self.store.snapshot(self.wid)['tasks'][0]
        self.store.update_task(self.wid,task['id'],1,'done')
        self.problem(lambda:self.store.update_task(self.wid,task['id'],1,'open'),409)
        draft = self.store.save_draft(self.wid,'client@example.test','Review','Original')
        self.store.save_draft(self.wid,'client@example.test','Review','Edited',draft['id'],1)
        self.problem(lambda:self.store.save_draft(self.wid,'client@example.test','Review','Stale',draft['id'],1),409)
        self.assertEqual(self.store.snapshot(self.wid)['drafts'][0]['body'],'Edited')

    def test_draft_eml_is_unsent_and_edited(self):
        draft = self.store.save_draft(self.wid,'client@example.test','Résumé','Hello — please review.')
        raw,mime,name = self.store.export(self.wid,'draft',draft['id'])
        msg = email.message_from_bytes(raw)
        self.assertEqual(msg['X-Unsent'],'1')
        self.assertEqual(msg['To'],'client@example.test')
        self.assertEqual(mime,'message/rfc822')
        self.assertEqual(name,'draft.eml')
        self.assertIn('please review',msg.get_payload(decode=True).decode('utf-8'))

    def test_csv_only_current_tasks_and_formula_neutralization(self):
        self.meeting('ACTION: =SUM(1) | - | +sample\nACTION: Lee | - | Removed')
        self.meeting('ACTION: =SUM(1) | - | +sample',1)
        raw,mime,_ = self.store.export(self.wid,'tasks')
        self.assertIn("'=SUM(1)",raw.decode())
        self.assertIn("'+sample",raw.decode())
        self.assertNotIn('Removed',raw.decode())
        self.assertTrue(mime.startswith('text/csv'))

    def test_bad_input_is_rejected_before_writes(self):
        for invalid in (None,[],{},True,3):
            self.problem(lambda:self.store.create_workspace(invalid))
            self.problem(lambda:self.store.import_source(self.wid,'x','X','document',invalid))
        for invalid in (None,-1,True,1.5,[]):
            self.problem(lambda:self.store.import_source(self.wid,'x','X','document','text',invalid))
        self.problem(lambda:self.store.save_draft(self.wid,'x@example.test\nBcc: bad@example.test','Subject','body'))
        self.problem(lambda:self.store.save_draft(self.wid,'x@example.test','Subject\nOther: injected','body'))
        self.problem(lambda:self.store.source(self.wid,[],1))
        self.assertEqual(self.store.snapshot(self.wid)['drafts'],[])


    def test_keyed_draft_retry_survives_restart_and_later_edits(self):
        first = self.store.save_draft(self.wid, 'client@example.test', 'Review', 'Original', request_id='request-1')
        self.store.save_draft(self.wid, 'client@example.test', 'Review', 'Newer edit', first['id'], 1)
        reopened = app.Store(self.path)
        again = reopened.save_draft(self.wid, 'client@example.test', 'Review', 'Original', request_id='request-1')
        self.assertEqual((again['id'], again['revision'], again['repeated']), (first['id'], 2, True))
        self.assertEqual(len(reopened.snapshot(self.wid)['drafts']), 1)
        self.assertEqual(reopened.snapshot(self.wid)['drafts'][0]['body'], 'Newer edit')

    def test_concurrent_keyed_draft_creation_is_single(self):
        def create(_):
            return self.store.save_draft(self.wid, 'client@example.test', 'Review', 'Body', request_id='one-request')
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(create, range(16)))
        self.assertEqual(len({r['id'] for r in results}), 1)
        self.assertEqual(sum(not r['repeated'] for r in results), 1)
        self.assertEqual(len(self.store.snapshot(self.wid)['drafts']), 1)

    def test_reused_request_with_different_content_does_not_write(self):
        first = self.store.save_draft(self.wid, 'client@example.test', 'Review', 'Original', request_id='request')
        for recipient, subject, body in [('other@example.test', 'Review', 'Original'), ('client@example.test', 'Changed', 'Original'), ('client@example.test', 'Review', 'Changed')]:
            self.problem(lambda: self.store.save_draft(self.wid, recipient, subject, body, request_id='request'), 409)
        self.assertEqual([(r['id'], r['body'], r['revision']) for r in self.store.snapshot(self.wid)['drafts']], [(first['id'], 'Original', 1)])

    def test_request_ids_are_client_scoped_and_new_keys_are_independent(self):
        first = self.store.save_draft(self.wid, 'client@example.test', 'Review', 'Body', request_id='same')
        other = self.store.save_draft(self.other, 'other@example.test', 'Review', 'Other', request_id='same')
        second = self.store.save_draft(self.wid, 'client@example.test', 'Review', 'Body', request_id='second')
        self.assertEqual(len({first['id'], other['id'], second['id']}), 3)
        self.assertEqual(len(self.store.snapshot(self.wid)['drafts']), 2)
        self.assertEqual(len(self.store.snapshot(self.other)['drafts']), 1)

    def test_legacy_unkeyed_creation_and_keyed_edit_rejection(self):
        one = self.store.save_draft(self.wid, 'client@example.test', 'Review', 'Body')
        two = self.store.save_draft(self.wid, 'client@example.test', 'Review', 'Body')
        self.assertNotEqual(one['id'], two['id'])
        self.problem(lambda: self.store.save_draft(self.wid, 'client@example.test', 'Review', 'Changed', one['id'], 1, request_id='not-for-edit'))
        self.assertEqual({r['body'] for r in self.store.snapshot(self.wid)['drafts']}, {'Body'})

    def test_invalid_creation_keys_do_not_write(self):
        for value in ('', '  ', [], {}, True, 3, 'x'*201):
            with self.subTest(value=value):
                self.problem(lambda: self.store.save_draft(self.wid, 'client@example.test', 'Review', 'Body', request_id=value))
        self.assertEqual(self.store.snapshot(self.wid)['drafts'], [])

    def test_request_table_is_added_to_existing_database(self):
        old = self.store.save_draft(self.wid, 'client@example.test', 'Legacy', 'Keep me')
        with self.store.connection(True) as db:
            db.execute('DROP TABLE draft_requests')
        reopened = app.Store(self.path)
        created = reopened.save_draft(self.wid, 'client@example.test', 'New', 'New body', request_id='new')
        self.assertEqual({r['id'] for r in reopened.snapshot(self.wid)['drafts']}, {old['id'], created['id']})
        self.assertTrue(reopened.save_draft(self.wid, 'client@example.test', 'New', 'New body', request_id='new')['repeated'])


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = app.Store(Path(self.temp.name)/'http.db')
        self.server = app.make_server(self.store,0)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self,path,body=None,headers=None):
        payload = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base+path,data=payload,headers=headers or ({'Content-Type':'application/json'} if body is not None else {}))
        try:
            response = urllib.request.urlopen(req,timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status,response.headers,response.read()

    def test_browser_shell_and_full_workflow(self):
        status,headers,page = self.request('/')
        self.assertEqual(status,200)
        self.assertIn(b'id="draft-form"',page)
        status,_,raw = self.request('/api/workspaces',{'name':'HTTP client'})
        wid = json.loads(raw)['id']
        status,_,raw = self.request('/api/import',dict(workspace_id=wid,source_key='meeting',title='Meeting',kind='meeting',text=MEETING))
        self.assertEqual(status,200)
        status,_,raw = self.request('/api/import',dict(workspace_id=wid,source_key='manual',title='Manual',kind='document',text='Onboarding includes a signed checklist.'))
        self.assertEqual(status,200)
        status,_,raw = self.request('/api/ask',dict(workspace_id=wid,question='onboarding'))
        cite = json.loads(raw)['citations'][0]
        self.assertEqual(json.loads(self.request(cite['url'])[2])['text'],'Onboarding includes a signed checklist.')
        status,_,raw = self.request('/api/draft',dict(workspace_id=wid,recipient='client@example.test',subject='Review',body='Editable draft'))
        did=json.loads(raw)['id']
        status,headers,raw=self.request(f'/api/export?workspace_id={wid}&kind=draft&draft_id={did}')
        self.assertEqual(status,200)
        self.assertIn('attachment',headers['Content-Disposition'])
        self.assertIn(b'X-Unsent: 1',raw)
        self.assertEqual(headers['Cache-Control'],'no-store')

    def test_http_draft_creation_retries_and_payload_conflict(self):
        wid = self.store.create_workspace('Retry client')['id']
        payload = dict(workspace_id=wid, recipient='client@example.test', subject='Unsent', body='Original', request_id='http-request')
        status, _, original = self.request('/api/draft', payload)
        self.assertEqual(status, 200)
        first = json.loads(original)
        status, _, repeated = self.request('/api/draft', payload)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(repeated)['id'], first['id'])
        self.assertTrue(json.loads(repeated)['repeated'])
        self.assertEqual(self.request('/api/draft', dict(payload, body='Different'))[0], 409)
        self.assertEqual(len(self.store.snapshot(wid)['drafts']), 1)
        self.assertEqual(self.request('/api/send', payload)[0], 404)

    def test_bad_requests_and_unknown_routes(self):
        self.assertEqual(self.request('/api/workspaces',[])[0],400)
        self.assertEqual(self.request('/api/workspaces',{'name':'X'},{'Content-Type':'text/plain'})[0],415)
        self.assertEqual(self.request('/api/workspaces',{'name':'X'},{'Content-Type':'application/json','Origin':'https://elsewhere.example'})[0],403)
        self.assertEqual(self.request('/api/send',{})[0],404)
        self.assertEqual(self.request('/api/source?workspace_id=x&source_id=y&version=no')[0],400)
        self.assertEqual(self.request('/missing')[0],404)
        self.assertEqual(self.store.list_workspaces(),[])


if __name__=='__main__':
    unittest.main(verbosity=2)
