"""Real compiler, MIME, archive, filesystem, CLI, and HTTP regression tests."""
import copy
import csv
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from email import policy
from email.parser import BytesParser
from pathlib import Path
from http.server import ThreadingHTTPServer

import newsletter_workflow as nw

ROOT = Path(__file__).resolve().parent


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.w = nw.load_json((ROOT / 'example.json').read_bytes())

    def test_starter_preferences(self):
        checked = nw.validate(self.w)
        self.assertEqual([s['email'] for s in checked['eligible']], ['alex@example.test', 'sam@example.test'])
        self.assertEqual([s['reason'] for s in checked['excluded']], ['unsubscribed', 'paused', 'topic_not_selected'])

    def test_real_archive_manifest_and_editable_source(self):
        with zipfile.ZipFile(io.BytesIO(nw.build_zip(self.w))) as archive:
            self.assertIsNone(archive.testzip())
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest['state'], 'PREPARED_NOT_SENT')
            self.assertEqual(manifest['eligible'], 2)
            self.assertEqual(set(archive.namelist()), set(manifest['files']) | {'manifest.json'})
            for name, record in manifest['files'].items():
                data = archive.read(name)
                self.assertEqual(len(data), record['bytes'])
                self.assertEqual(hashlib.sha256(data).hexdigest(), record['sha256'])
            self.assertEqual(json.loads(archive.read('workspace.json')), self.w)
            self.assertEqual(len([n for n in archive.namelist() if n.startswith('drafts/')]), 2)

    def test_repeat_build_is_byte_identical(self):
        self.assertEqual(nw.build_zip(self.w), nw.build_zip(copy.deepcopy(self.w)))

    def test_rebuild_retains_original_and_applies_unsubscribe(self):
        before = nw.build_files(self.w)
        self.w['subscribers'][0]['status'] = 'unsubscribed'
        after = nw.build_files(self.w)
        self.assertEqual(len([p for p in before if p.startswith('drafts/')]), 2)
        self.assertEqual(len([p for p in after if p.startswith('drafts/')]), 1)
        self.assertEqual(json.loads(after['manifest.json'])['eligible'], 1)
        plan = list(csv.DictReader(io.StringIO(after['delivery-plan.csv'].decode())))
        alex = next(row for row in plan if row['email'] == 'alex@example.test')
        self.assertEqual((alex['state'], alex['reason'], alex['draft_path']), ('EXCLUDED','unsubscribed',''))

    def test_mime_is_unicode_multipart_and_unsent(self):
        self.w['subscribers'][0]['name'] = 'Aléx Example'
        self.w['issue']['subject'] = 'An editable issue — café notes'
        files = nw.build_files(self.w)
        messages = [BytesParser(policy=policy.default).parsebytes(b) for p,b in files.items() if p.endswith('.eml')]
        self.assertEqual(len(messages), 2)
        for message in messages:
            self.assertEqual(str(message['Subject']), self.w['issue']['subject'])
            self.assertEqual(message['X-Unsent'], '1')
            self.assertEqual(message['X-Newsletter-State'], 'prepared-not-sent')
            self.assertEqual(message.get_content_type(), 'multipart/alternative')
            self.assertIn('repair notebook', message.get_body(preferencelist=('plain',)).get_content())
            self.assertIn('<!doctype html>', message.get_body(preferencelist=('html',)).get_content())
            self.assertIn('mailto:preferences@example.test', message['List-Unsubscribe'])
        self.assertTrue(any('Aléx' in str(m['To']) for m in messages))
        self.assertEqual(len({m['Message-ID'] for m in messages}), 2)

    def test_changed_quote_requires_matching_source_update(self):
        self.w['issue']['sections'][0]['quote'] = 'Keep the original beside the revision.'
        with self.assertRaisesRegex(nw.InputError, 'not an exact excerpt'):
            nw.build_zip(self.w)
        self.w['sources'][0]['text'] += ' Keep the original beside the revision.'
        self.assertIn(b'Keep the original beside the revision.', nw.build_files(self.w)['newsletter.txt'])

    def test_source_map_exact_quotes_and_hashes(self):
        sources = nw.validate(self.w)['sources']
        report = json.loads(nw.build_files(self.w)['source-map.json'])
        for section in report['sections']:
            source = sources[section['source_id']]
            self.assertIn(section['quote'], source['text'])
            self.assertEqual(section['source_text_sha256'], hashlib.sha256(source['text'].encode()).hexdigest())

    def test_html_escapes_editable_content(self):
        self.w['issue']['subject'] = '<script>alert(1)</script>'
        self.w['issue']['sections'][0]['commentary'] = '<img src=x onerror=alert(1)>'
        self.w['sources'][0]['url'] = 'https://example.test/"onclick="evil'
        rendered = nw.build_files(self.w)['preview.html'].decode()
        self.assertNotIn('<script>', rendered)
        self.assertNotIn('<img src=x', rendered)
        self.assertIn('&lt;script&gt;', rendered)
        self.assertIn('&quot;onclick=&quot;evil', rendered)

    def test_csv_formula_address_is_text_but_mime_preserves_address(self):
        self.w['subscribers'] = [{'email': '=danger@example.test', 'name': 'Example', 'status': 'subscribed', 'topics': ['workshops']}]
        files = nw.build_files(self.w)
        plan = list(csv.DictReader(io.StringIO(files['delivery-plan.csv'].decode())))
        self.assertEqual(plan[0]['email'], "'=danger@example.test")
        message = BytesParser(policy=policy.default).parsebytes(next(b for p,b in files.items() if p.endswith('.eml')))
        self.assertEqual(message['To'].addresses[0].addr_spec, '=danger@example.test')

    def test_duplicate_email_casefold_is_reported(self):
        self.w['subscribers'].append(dict(self.w['subscribers'][0], email='ALEX@example.test', status='unsubscribed'))
        with self.assertRaisesRegex(nw.InputError, 'Duplicate subscriber'):
            nw.build_zip(self.w)

    def test_zero_subscribers_still_exports_an_issue(self):
        self.w['subscribers'] = []
        files = nw.build_files(self.w)
        self.assertIn('preview.html', files)
        self.assertFalse(any(p.startswith('drafts/') for p in files))
        self.assertEqual(json.loads(files['manifest.json'])['eligible'], 0)

    def test_empty_topic_selection_excludes_subscriber(self):
        self.w['subscribers'][0]['topics'] = []
        self.assertEqual(len(nw.validate(self.w)['eligible']), 1)

    def test_duplicate_json_keys_and_nonfinite_values(self):
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', b'\xff'):
            with self.subTest(raw=raw), self.assertRaises(nw.InputError):
                nw.load_json(raw)
        self.w['extra'] = 1e400
        with self.assertRaisesRegex(nw.InputError, 'finite'):
            nw.build_zip(self.w)

    def test_json_exponent_overflow_is_rejected(self):
        raw = json.dumps(self.w)[:-1] + ', "extra": 1e400}'
        with self.assertRaises(nw.InputError):
            nw.build_zip(nw.load_json(raw))

    def test_wrong_container_shapes_raise_input_error(self):
        changes = [('sources',None),('subscribers',{}),('issue',[]),('publication',None),('schema_version',True)]
        for field,value in changes:
            with self.subTest(field=field), self.assertRaises(nw.InputError):
                nw.build_zip(dict(self.w, **{field:value}))
        for value in ([],{},None,True):
            bad = copy.deepcopy(self.w); bad['subscribers'][0]['status'] = value
            with self.subTest(status=value), self.assertRaises(nw.InputError): nw.build_zip(bad)
        for value in (None, [], 'bad'):
            bad = copy.deepcopy(self.w); bad['issue']['sections'][0] = value
            with self.subTest(section=value), self.assertRaises(nw.InputError): nw.build_zip(bad)

    def test_source_ids_and_unsafe_urls(self):
        for url in ('javascript:alert(1)', 'https://name:password@example.test/x', 'https://example.test:99999/', 'https://example.test/a b'):
            self.w['sources'][0]['url'] = url
            with self.subTest(url=url), self.assertRaises(nw.InputError): nw.build_zip(self.w)
        self.setUp(); self.w['sources'].append(self.w['sources'][0])
        with self.assertRaisesRegex(nw.InputError,'Duplicate source'): nw.build_zip(self.w)
        self.setUp(); self.w['issue']['sections'][0]['source_id']='missing'
        with self.assertRaisesRegex(nw.InputError,'unknown source'): nw.build_zip(self.w)

    def test_invalid_timezone_and_header_inputs(self):
        for value in ('2026-09-15T09:00:00','not-a-time',True):
            self.w['issue']['planned_at']=value
            with self.subTest(time=value), self.assertRaises(nw.InputError): nw.build_zip(self.w)
        self.setUp(); self.w['issue']['subject']='Hello\r\nBcc: other@example.test'
        with self.assertRaisesRegex(nw.InputError,'control'): nw.build_zip(self.w)
        self.setUp(); self.w['publication']['sender_email']='Display <a@example.test>'
        with self.assertRaises(nw.InputError): nw.build_zip(self.w)
        self.setUp(); self.w['issue']['subject']='\ud800'
        with self.assertRaisesRegex(nw.InputError,'Unicode'): nw.build_zip(self.w)

    def test_original_input_is_not_mutated(self):
        before=copy.deepcopy(self.w); nw.build_zip(self.w)
        self.assertEqual(self.w,before)

    def test_slug_never_becomes_archive_path(self):
        self.w['issue']['slug']='../../outside'
        with self.assertRaises(nw.InputError): nw.build_zip(self.w)

    def test_cli_init_validate_build_and_existing_file_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace=Path(tmp)/'work'/'mine.json'; output=Path(tmp)/'edition.zip'
            command=[sys.executable,str(ROOT/'newsletter_workflow.py')]
            for args in (['init',str(workspace)],['validate',str(workspace)],['build',str(workspace),'--out',str(output)]):
                result=subprocess.run(command+args,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
            original=output.read_bytes()
            retry=subprocess.run(command+['build',str(workspace),'--out',str(output)],capture_output=True,text=True)
            self.assertEqual(retry.returncode,2); self.assertEqual(output.read_bytes(),original)
            self.assertEqual(zipfile.ZipFile(output).testzip(),None)
            init_again=subprocess.run(command+['init',str(workspace)],capture_output=True,text=True)
            self.assertEqual(init_again.returncode,2)

    def test_cli_invalid_input_creates_no_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'bad.json'; output=Path(tmp)/'out.zip'
            path.write_text('{"schema_version":false}')
            result=subprocess.run([sys.executable,str(ROOT/'newsletter_workflow.py'),'build',str(path),'--out',str(output)],capture_output=True,text=True)
            self.assertEqual(result.returncode,2); self.assertFalse(output.exists())


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),nw.handler_class())
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=3)

    def test_real_http_starter_and_browser(self):
        with urllib.request.urlopen(self.base) as response:
            self.assertIn(b'Build a newsletter',response.read())
        with urllib.request.urlopen(self.base+'/example.json') as response:
            self.assertEqual(json.load(response)['schema_version'],1)

    def test_real_http_build_and_validate(self):
        raw=(ROOT/'example.json').read_bytes()
        for route in ('/validate','/build'):
            request=urllib.request.Request(self.base+route,data=raw,headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request) as response:
                body=response.read()
                if route=='/build':
                    self.assertIn('edition-01.zip',response.headers['Content-Disposition'])
                    self.assertIsNone(zipfile.ZipFile(io.BytesIO(body)).testzip())
                else:
                    self.assertEqual(json.loads(body),json.loads(raw))

    def test_real_http_rejects_duplicate_raw_json_and_wrong_shape(self):
        for raw in (b'{"schema_version":1,"schema_version":2}',b'[]',b'null'):
            request=urllib.request.Request(self.base+'/validate',data=raw)
            with self.subTest(raw=raw), self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request)
            self.assertEqual(caught.exception.code,400)
            self.assertIn('error',json.loads(caught.exception.read()))

    def test_real_http_unknown_path_and_empty_body(self):
        with self.assertRaises(urllib.error.HTTPError) as caught: urllib.request.urlopen(self.base+'/missing')
        self.assertEqual(caught.exception.code,404)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(urllib.request.Request(self.base+'/build',data=b''))
        self.assertEqual(caught.exception.code,400)


class ExerciseTests(unittest.TestCase):
    def test_all_worked_solutions_validate_and_build(self):
        import exercises
        starter=nw.load_json((ROOT/'example.json').read_bytes())
        for number,answer in enumerate(exercises.solutions(starter),1):
            with self.subTest(exercise=number):
                exercises.check(number,answer)
                with zipfile.ZipFile(io.BytesIO(nw.build_zip(answer))) as archive:
                    self.assertIsNone(archive.testzip())
                    self.assertEqual(json.loads(archive.read('manifest.json'))['eligible'],2 if number==1 else 1)
        self.assertEqual(len(answer['issue']['sections']),4)

    def test_incomplete_exercises_are_not_marked_complete(self):
        import exercises
        starter=nw.load_json((ROOT/'example.json').read_bytes())
        answers=exercises.solutions(starter)
        for number,before in enumerate([starter,answers[0],answers[1]],1):
            with self.subTest(exercise=number),self.assertRaises(nw.InputError): exercises.check(number,before)

    def test_prepare_real_files_and_preserve_existing(self):
        import exercises
        with tempfile.TemporaryDirectory() as tmp:
            destination=Path(tmp)/'practice'
            exercises.prepare(destination)
            files={p.name:p.read_bytes() for p in destination.iterdir()}
            self.assertEqual(len(files),6)
            with self.assertRaises(FileExistsError): exercises.prepare(destination)
            self.assertEqual(files,{p.name:p.read_bytes() for p in destination.iterdir()})
            for number in range(1,4): exercises.check(number,nw.load_json(files[f'solution-{number}.json']))

    def test_exercise_cli_checks_real_file(self):
        import exercises
        with tempfile.TemporaryDirectory() as tmp:
            destination=Path(tmp)/'practice';exercises.prepare(destination)
            result=subprocess.run([sys.executable,str(ROOT/'exercises.py'),'check','3',str(destination/'solution-3.json')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('1 eligible unsent drafts',result.stdout)


if __name__=='__main__':
    unittest.main()
