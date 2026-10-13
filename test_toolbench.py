"""Exercise the real evidence instruments. Test sequences are not actor workflows."""
import base64
import hashlib
import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from host.toolbench import Bench, BenchError, ROOT, load_example, server


class BenchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'bench.sqlite3'
        self.bench = Bench(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def op(self, op, **args):
        return self.bench.apply({'op': op, 'args': args})

    def job(self, identifier='job'):
        self.op('add_job', job_id=identifier, title='Synthetic job')

    def source(self, identifier='source', value='Original evidence'):
        self.op('add_source', source_id=identifier, name=identifier+'.txt',
                source_ref='synthetic test object', text=value)

    def linked(self):
        self.job()
        self.source('a')
        self.source('b', 'Other evidence')
        for source in ['a', 'b']:
            self.op('link', job_id='job', source_id=source, reason='Chosen by the test driver')

    def exported(self):
        data = self.bench.export('job')
        archive = zipfile.ZipFile(io.BytesIO(data))
        return archive, json.loads(archive.read('manifest.json'))

    def test_empty_state_and_unassigned_import(self):
        self.assertEqual(self.bench.snapshot()['revision'], 0)
        self.job(); self.source()
        state = self.bench.snapshot()
        self.assertEqual(state['revision'], 2)
        self.assertEqual(state['links'], [])
        self.assertEqual(state['selections'], [])
        self.assertNotIn('data', state['sources'][0])

    def test_exact_text_and_binary_bytes(self):
        self.source(value='Résumé\r\nπ\n')
        self.assertEqual(self.bench.source('source')['text'], 'Résumé\r\nπ\n')
        data = bytes(range(256))
        self.op('add_source', source_id='binary', name='evidence.bin', source_ref='synthetic',
                data_base64=base64.b64encode(data).decode())
        actual = self.bench.source('binary')
        self.assertEqual(base64.b64decode(actual['data_base64']), data)
        self.assertEqual(actual['sha256'], hashlib.sha256(data).hexdigest())
        self.assertIsNone(actual['text'])

    def test_sources_immutable_and_failed_write_atomic(self):
        self.source()
        before = self.bench.snapshot()
        with self.assertRaises(BenchError):
            self.source(value='replacement')
        self.assertEqual(before, self.bench.snapshot())
        self.assertEqual(self.bench.source('source')['text'], 'Original evidence')
        self.assertEqual(len(self.bench.history()), 1)

    def test_missing_reference_creates_no_partial_event(self):
        self.job()
        with self.assertRaises(BenchError) as error:
            self.op('link', job_id='job', source_id='missing', reason='not available')
        self.assertEqual(error.exception.code, 'NOT_FOUND')
        self.assertEqual(self.bench.snapshot()['revision'], 1)
        self.assertEqual(self.bench.snapshot()['links'], [])

    def test_same_request_retry_survives_stale_revision(self):
        request = {'op':'add_job', 'args':{'job_id':'job','title':'Title'},
                   'request_id':'stable-id', 'expected_revision':0}
        first = self.bench.apply(request)
        self.source()
        retry = self.bench.apply(request)
        self.assertTrue(first['applied'])
        self.assertFalse(retry['applied'])
        self.assertTrue(retry['replayed'])
        self.assertEqual((retry['revision'], retry['current_revision']), (1, 2))
        self.assertEqual(len(self.bench.snapshot()['jobs']), 1)

    def test_reused_request_id_different_payload_refused(self):
        request = {'op':'add_job', 'args':{'job_id':'job','title':'Title'},'request_id':'same'}
        self.bench.apply(request)
        request['args']['title'] = 'Changed'
        with self.assertRaises(BenchError) as error:
            self.bench.apply(request)
        self.assertEqual(error.exception.code, 'REQUEST_CONFLICT')
        self.assertEqual(self.bench.snapshot()['jobs'][0]['title'], 'Title')

    def test_stale_selection_cannot_erase_new_selection(self):
        self.linked()
        revision = self.bench.snapshot()['revision']
        self.op('select', job_id='job', source_ids=['a'])
        with self.assertRaises(BenchError) as error:
            self.bench.apply({'op':'select', 'args':{'job_id':'job','source_ids':['b']},
                              'expected_revision':revision})
        self.assertEqual(error.exception.code, 'STATE_CONFLICT')
        self.assertEqual(self.bench.snapshot()['selections'][0]['source_id'], 'a')

    def test_selection_is_explicit_order_not_source_sort_order(self):
        self.linked()
        self.op('select', job_id='job', source_ids=['b','a'])
        archive, manifest = self.exported()
        with archive:
            self.assertEqual([s['id'] for s in manifest['selected']], ['b','a'])

    def test_unlinked_or_duplicate_selection_preserves_previous(self):
        self.linked(); self.source('unlinked')
        self.op('select', job_id='job', source_ids=['a'])
        original = self.bench.snapshot()
        for invalid in [['b','unlinked'],['a','a'],['missing'],None,'a']:
            with self.subTest(invalid=invalid), self.assertRaises(BenchError):
                self.op('select', job_id='job', source_ids=invalid)
            self.assertEqual(original, self.bench.snapshot())

    def test_unlink_preserves_source_and_past_reason(self):
        self.linked()
        self.op('select', job_id='job', source_ids=['a','b'])
        self.op('unlink', job_id='job', source_id='a')
        state = self.bench.snapshot()
        self.assertEqual([s['source_id'] for s in state['selections']], ['b'])
        self.assertEqual(self.bench.source('a')['text'], 'Original evidence')
        self.assertTrue(any(e['operation']['op']=='link' and e['operation']['args']['source_id']=='a'
                            for e in self.bench.history()))

    def test_association_correction_retains_history(self):
        self.linked()
        self.op('link', job_id='job', source_id='a', reason='Revised interpretation')
        self.assertEqual(self.bench.snapshot()['links'][0]['reason'], 'Revised interpretation')
        self.assertEqual(sum(e['operation']['op']=='link' and e['operation']['args']['source_id']=='a'
                             for e in self.bench.history()), 2)

    def test_version_comparison_and_original_retained(self):
        self.source('v1','Inspection only.\n')
        self.op('add_source', source_id='v2', name='v2.txt', source_ref='synthetic revised approval',
                text='Inspection and seal replacement.\n', revision_of='v1')
        result = self.bench.compare('v1','v2')
        self.assertFalse(result['same_bytes'])
        self.assertIn('-Inspection only.', result['text_diff'])
        self.assertIn('+Inspection and seal replacement.', result['text_diff'])
        self.assertTrue(self.bench.compare('v1','v1')['same_bytes'])
        self.assertEqual(self.bench.source('v2')['revision_of'], 'v1')

    def test_binary_comparison_does_not_invent_text(self):
        self.source('a')
        self.op('add_source', source_id='b', name='b.bin', source_ref='synthetic', data_base64='/w==')
        self.assertIsNone(self.bench.compare('a','b')['text_diff'])

    def test_question_resolution_preserves_question_and_prior_events(self):
        self.job()
        self.op('annotate', note_id='n', job_id='job', text='Where is the photograph?')
        self.op('resolve_note', note_id='n', resolution='Not supplied; requested separately.')
        note = self.bench.snapshot()['notes'][0]
        self.assertEqual(note['text'], 'Where is the photograph?')
        self.assertEqual(note['resolution'], 'Not supplied; requested separately.')
        self.assertEqual([e['operation']['op'] for e in self.bench.history()],
                         ['add_job','annotate','resolve_note'])

    def test_export_exact_bytes_deterministic_and_excludes_unselected_content(self):
        self.linked()
        self.source('unselected-secret','SYNTHETIC-UNSELECTED-CONTENT-DO-NOT-EXPORT')
        self.op('select', job_id='job', source_ids=['a'])
        self.op('annotate', note_id='n', job_id='job', text='Closing photo remains missing.')
        data = self.bench.export('job')
        self.assertEqual(data, self.bench.export('job'))
        archive, manifest = self.exported()
        with archive:
            self.assertEqual(len(manifest['selected']),1)
            source = manifest['selected'][0]
            raw = archive.read(source['archive_path'])
            self.assertEqual(raw, b'Original evidence')
            self.assertEqual(hashlib.sha256(raw).hexdigest(),source['sha256'])
            self.assertEqual(manifest['notes'][0]['text'], 'Closing photo remains missing.')
            self.assertEqual([r['source_id'] for r in manifest['linked_not_selected']],['b'])
            self.assertNotIn(b'SYNTHETIC-UNSELECTED-CONTENT-DO-NOT-EXPORT',data)

    def test_empty_selection_is_not_filled_automatically(self):
        self.linked()
        archive, manifest = self.exported()
        with archive:
            self.assertEqual(manifest['selected'], [])
            self.assertEqual(set(archive.namelist()), {'manifest.json','READ-ME.txt'})
            self.assertIn('no completeness', manifest['coverage'])

    def test_archive_paths_independent_of_untrusted_source_name_and_id(self):
        self.job()
        self.op('add_source', source_id='../../escape', name='../../evil.html',
                source_ref='<script>untrusted reference</script>',text='<script>do_not_run()</script>')
        self.op('link', job_id='job', source_id='../../escape', reason='explicit choice')
        self.op('select', job_id='job', source_ids=['../../escape'])
        archive, manifest = self.exported()
        with archive:
            self.assertFalse(any('..' in n or n.startswith('/') for n in archive.namelist()))
            self.assertEqual(manifest['selected'][0]['name'],'../../evil.html')
            self.assertEqual(archive.read(manifest['selected'][0]['archive_path']), b'<script>do_not_run()</script>')

    def test_reopen_retains_workspace_for_another_client(self):
        self.linked()
        self.op('select', job_id='job', source_ids=['b'])
        second = Bench(self.path)
        self.assertEqual(second.snapshot(),self.bench.snapshot())
        second.apply({'op':'annotate','args':{'note_id':'second','job_id':'job','text':'Different next question'}})
        self.assertEqual(self.bench.snapshot()['notes'][0]['text'],'Different next question')

    def test_concurrent_distinct_operations_preserve_both(self):
        self.job()
        def add(i):
            return Bench(self.path).apply({'op':'annotate','args':{'note_id':str(i), 'job_id':'job', 'text':'Note '+str(i)}})
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(add,range(12)))
        self.assertEqual(len(self.bench.snapshot()['notes']),12)
        self.assertEqual(len({r['revision'] for r in results}),12)
        self.assertEqual(self.bench.snapshot()['revision'],13)

    def test_concurrent_same_request_has_one_effect(self):
        request={'op':'add_job','args':{'job_id':'one','title':'One'},'request_id':'same-request'}
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _: Bench(self.path).apply(request),range(8)))
        self.assertEqual(sum(r['applied'] for r in results),1)
        self.assertEqual(self.bench.snapshot()['revision'],1)

    def test_optional_actor_label_is_not_required_for_participation(self):
        self.bench.apply({'op':'add_job','args':{'job_id':'j','title':'J'},'actor':''})
        self.assertEqual(self.bench.history()[0]['operation']['actor'],'anonymous')

    def test_invalid_inputs_never_change_state(self):
        cases=[[], {'op':'missing'}, {'op':'add_job','args':[]},
               {'op':'add_job','args':{'job_id':'','title':'x'}},
               {'op':'add_job','args':{'job_id':'j','title':'J'},'expected_revision':True},
               {'op':'add_source','args':{'source_id':'s','name':'s','source_ref':'s','text':'x','data_base64':'eA=='}},
               {'op':'add_source','args':{'source_id':'s','name':'s','source_ref':'s','data_base64':'%%%'}},
               {'op':'add_source','args':{'source_id':'s','name':'s','source_ref':'s','text':'x','revision_of':'missing'}},
               {'op':'add_job','args':{'job_id':'j','title':'J','description':float('nan')}}]
        for request in cases:
            with self.subTest(request=request), self.assertRaises(BenchError):
                self.bench.apply(request)
            self.assertEqual(self.bench.snapshot()['revision'],0)

    def test_example_is_inert_and_repeat_loading_idempotent(self):
        path=ROOT/'toolbench/example.json'
        load_example(self.bench,path)
        state=self.bench.snapshot()
        self.assertEqual(len(state['jobs']),2)
        self.assertEqual(len(state['sources']),6)
        self.assertEqual(state['links'],[])
        self.assertEqual(state['selections'],[])
        load_example(self.bench,path)
        self.assertEqual(state,self.bench.snapshot())
        self.assertEqual(self.bench.source('camera-b')['name'],'J-101-photo.png')
        self.assertTrue(base64.b64decode(self.bench.source('camera-b')['data_base64']).startswith(b'\x89PNG'))

    def test_checkpoint_zip_contents_and_reopen_matches_snapshot(self):
        self.linked()
        self.op('select', job_id='job', source_ids=['b', 'a'])
        self.op('annotate', note_id='n', job_id='job', text='Checkpoint must carry unselected evidence too.')
        before = self.bench.snapshot()
        data = self.bench.checkpoint()
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(set(archive.namelist()), {'workspace.sqlite3', 'manifest.json'})
            manifest = json.loads(archive.read('manifest.json'))
            db_bytes = archive.read('workspace.sqlite3')
        self.assertEqual(manifest['format'], 'commons-toolbench-checkpoint-v1')
        self.assertEqual(manifest['kind'], 'FULL_WORKSPACE_BACKUP')
        self.assertEqual(manifest['revision'], before['revision'])
        self.assertEqual(manifest['sha256'], hashlib.sha256(db_bytes).hexdigest())
        self.assertIn('Committed workspace only', manifest['coverage'])
        self.assertIn('no drafts', manifest['coverage'])
        self.assertIn('does not execute history', manifest['coverage'])
        extracted = Path(self.temp.name) / 'workspace.sqlite3'
        extracted.write_bytes(db_bytes)
        reopened = Bench(extracted)
        self.assertEqual(reopened.snapshot(), before)
        self.assertEqual(reopened.source('a')['text'], 'Original evidence')
        self.assertEqual([s['source_id'] for s in reopened.snapshot()['selections']], ['b', 'a'])

    def test_checkpoint_includes_mutations_and_does_not_bump_revision(self):
        self.job()
        self.source()
        first = self.bench.checkpoint()
        with zipfile.ZipFile(io.BytesIO(first)) as archive:
            first_manifest = json.loads(archive.read('manifest.json'))
        self.op('annotate', note_id='n', job_id='job', text='After first checkpoint')
        before = self.bench.snapshot()
        revision = before['revision']
        second = self.bench.checkpoint()
        self.assertEqual(self.bench.snapshot()['revision'], revision)
        self.assertEqual(len(self.bench.history()), revision)
        with zipfile.ZipFile(io.BytesIO(second)) as archive:
            second_manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(second_manifest['kind'], 'FULL_WORKSPACE_BACKUP')
            extracted = Path(self.temp.name) / 'after.sqlite3'
            extracted.write_bytes(archive.read('workspace.sqlite3'))
        self.assertGreater(second_manifest['revision'], first_manifest['revision'])
        restored = Bench(extracted)
        self.assertEqual(restored.snapshot()['notes'][0]['text'], 'After first checkpoint')
        self.assertEqual(restored.snapshot(), before)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.bench=Bench(Path(self.temp.name)/'http.sqlite3')
        self.http=server(self.bench,port=0)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True)
        self.thread.start()
        self.url=f'http://127.0.0.1:{self.http.server_port}'

    def tearDown(self):
        self.http.shutdown(); self.http.server_close(); self.thread.join(timeout=3)
        self.temp.cleanup()

    def get(self,path):
        with urllib.request.urlopen(self.url+path,timeout=5) as response:
            return response.headers,response.read()

    def post(self,body):
        request=urllib.request.Request(self.url+'/api/op',data=json.dumps(body).encode(),
                                       headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=5) as response:
            return json.load(response)

    def test_human_surface_and_tool_contract_share_actual_state(self):
        headers,body=self.get('/')
        self.assertIn('text/html',headers['Content-Type'])
        self.assertIn(b'Working handover',body)
        self.assertIn(b'Download workspace checkpoint',body)
        self.assertIsNone(headers.get('Set-Cookie'))
        _,body=self.get('/api/operations')
        contract=json.loads(body)
        self.assertIn('add_source',contract['operations'])
        self.assertIn('/api/checkpoint', contract['read'])
        self.post({'op':'add_job','args':{'job_id':'j','title':'From HTTP client 1'}})
        _,body=self.get('/api/state')
        state=json.loads(body)
        self.assertEqual(state['jobs'][0]['title'],'From HTTP client 1')
        self.post({'op':'annotate','args':{'note_id':'n','job_id':'j','text':'HTTP client 2 continues'},
                   'expected_revision':state['revision']})
        self.assertEqual(self.bench.snapshot()['notes'][0]['text'],'HTTP client 2 continues')
        headers,data=self.get('/api/export?job=j')
        self.assertEqual(headers['Content-Type'],'application/zip')
        self.assertIn('toolbench-handover.zip', headers.get('Content-Disposition',''))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(json.loads(archive.read('manifest.json'))['notes'][0]['text'],'HTTP client 2 continues')

    def test_http_checkpoint_download(self):
        self.post({'op':'add_job','args':{'job_id':'j','title':'Checkpoint job'}})
        self.post({'op':'add_source','args':{'source_id':'s','name':'s.txt','source_ref':'synthetic','text':'carry me'}})
        revision = self.bench.snapshot()['revision']
        headers, data = self.get('/api/checkpoint')
        self.assertEqual(headers['Content-Type'], 'application/zip')
        self.assertIn('toolbench-checkpoint.zip', headers.get('Content-Disposition', ''))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(set(archive.namelist()), {'workspace.sqlite3', 'manifest.json'})
            manifest = json.loads(archive.read('manifest.json'))
            db_bytes = archive.read('workspace.sqlite3')
        self.assertEqual(manifest['format'], 'commons-toolbench-checkpoint-v1')
        self.assertEqual(manifest['kind'], 'FULL_WORKSPACE_BACKUP')
        self.assertEqual(manifest['revision'], revision)
        self.assertEqual(manifest['sha256'], hashlib.sha256(db_bytes).hexdigest())
        self.assertEqual(self.bench.snapshot()['revision'], revision)
        extracted = Path(self.temp.name) / 'from-http.sqlite3'
        extracted.write_bytes(db_bytes)
        self.assertEqual(Bench(extracted).snapshot(), self.bench.snapshot())

    def test_invalid_json_and_unknown_route_report_errors(self):
        for raw in [b'not json',b'{"op":"add_job","args":{"job_id":"j","title":"J","description":NaN}}']:
            req=urllib.request.Request(self.url+'/api/op',data=raw,headers={'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(req,timeout=5)
            with error.exception as response:
                self.assertEqual(response.code,400)
                self.assertEqual(json.load(response)['error'],'INVALID_INPUT')
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.get('/not-a-file')
        error.exception.close()
        self.assertEqual(self.bench.snapshot()['revision'],0)

    def test_http_conflict_reports_no_silent_overwrite(self):
        self.post({'op':'add_job','args':{'job_id':'j','title':'J'}})
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post({'op':'annotate','args':{'note_id':'n','job_id':'j','text':'stale'},'expected_revision':0})
        with error.exception as response:
            self.assertEqual(response.code,409)
            self.assertEqual(json.load(response)['error'],'STATE_CONFLICT')
        self.assertEqual(self.bench.snapshot()['notes'],[])


if __name__=='__main__':
    unittest.main()
