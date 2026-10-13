#!/usr/bin/env python3
"""Real SQLite, threaded HTTP, package and input-shape regression tests."""
import concurrent.futures
import copy
import hashlib
import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import studio


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'data.sqlite3'
        self.store = studio.Store(self.path)
        self.brief = json.loads((studio.HERE / 'example.json').read_text())

    def tearDown(self):
        self.temp.cleanup()

    def create(self, key='request-1'):
        return self.store.save(self.brief, request_id=key)


class StudioTests(Fixture):
    def test_create_restart_and_list(self):
        project = self.create()
        restarted = studio.Store(self.path)
        self.assertEqual(restarted.get(project['id']), project)
        self.assertEqual(restarted.list(), [project])

    def test_retry_create_same_project(self):
        first = self.create()
        self.assertEqual(self.create(), first)
        self.assertEqual(len(self.store.list()), 1)
        self.assertEqual(len(self.store.history(first['id'])), 1)

    def test_retry_with_different_brief_rejected(self):
        self.create()
        self.brief['name'] = 'Changed'
        with self.assertRaises(studio.Conflict):
            self.create()
        self.assertEqual(self.store.list()[0]['brief']['name'], 'Workshop Supply Planner')

    def test_concurrent_create_exactly_once(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            rows = list(pool.map(lambda _: self.create(), range(24)))
        self.assertEqual(len({row['id'] for row in rows}), 1)
        self.assertEqual(len(self.store.list()), 1)

    def test_revision_and_history_are_durable(self):
        first = self.create()
        self.brief['name'] = 'Changed'
        second = self.store.save(self.brief, project_id=first['id'], expected_revision=1)
        self.assertEqual(second['revision'], 2)
        history = studio.Store(self.path).history(first['id'])
        self.assertEqual([r['revision'] for r in history], [1, 2])
        self.assertEqual(history[0]['brief']['name'], 'Workshop Supply Planner')
        self.assertEqual(history[1]['brief']['name'], 'Changed')

    def test_concurrent_edits_do_not_lose_a_revision(self):
        first = self.create()
        def update(i):
            brief = {**self.brief, 'name': 'Edit '+str(i)}
            try:
                return self.store.save(brief, project_id=first['id'], expected_revision=1)
            except studio.Conflict:
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(update, range(16)))
        self.assertEqual(sum(row is not None for row in results), 1)
        self.assertEqual(len(self.store.history(first['id'])), 2)

    def test_boolean_revision_is_not_one(self):
        first = self.create()
        with self.assertRaises(studio.Conflict):
            self.store.save(self.brief, project_id=first['id'], expected_revision=True)

    def test_unknown_project(self):
        with self.assertRaises(KeyError):
            self.store.get('0'*32)
        with self.assertRaises(KeyError):
            self.store.history('0'*32)

    def test_invalid_shapes(self):
        for invalid in [None, [], 'text', 1, True]:
            with self.subTest(invalid=invalid), self.assertRaises(studio.InputError):
                studio.validate_brief(invalid)
        for key in ['name','creator','audience','problem','onboarding','pricing','support']:
            for value in [None, [], True, '', ' '*4]:
                with self.subTest(key=key, value=value), self.assertRaises(studio.InputError):
                    studio.validate_brief({**self.brief, key:value})

    def test_material_bounds(self):
        for value in [None, {}, [], [None], self.brief['materials']*17]:
            with self.subTest(value=value), self.assertRaises(studio.InputError):
                studio.validate_brief({**self.brief,'materials':value})
        for key in ['per_attendee','pack_size','buffer_percent']:
            for value in [True,None,[],{},'NaN','Infinity','-1','1000001','0.0000001']:
                brief = copy.deepcopy(self.brief)
                brief['materials'][0][key] = value
                with self.subTest(key=key,value=value), self.assertRaises(studio.InputError):
                    studio.validate_brief(brief)

    def test_decimal_normalization(self):
        self.brief['materials'][0].update(per_attendee='2.000000',pack_size='1e1',buffer_percent=10)
        row=studio.validate_brief(self.brief)['materials'][0]
        self.assertEqual((row['per_attendee'],row['pack_size'],row['buffer_percent']),('2','10','10'))

    def test_usage_bounds(self):
        for value in [None,True,1.5,0,10001,'20']:
            with self.subTest(value=value), self.assertRaises(studio.InputError):
                studio.validate_brief({**self.brief,'usage_target':value})

    def test_json_duplicate_and_nonfinite(self):
        for value in [b'{"name":"a","name":"b"}', b'{"value":NaN}',b'\xff',b'{']:
            with self.subTest(value=value), self.assertRaises(studio.InputError):
                studio.decode_json(value)

    def test_package_contains_real_application_and_history(self):
        first=self.create()
        archive=zipfile.ZipFile(io.BytesIO(studio.build_package(first,self.store.history(first['id']))))
        self.assertEqual(set(archive.namelist()), {'index.html','brief.json','revisions.json','START-HERE.md','launch-copy.txt','SHA256SUMS'})
        html=archive.read('index.html').decode()
        self.assertNotIn('__BRIEF_JSON__',html)
        self.assertIn('function calculate(plan)',html)
        self.assertEqual(json.loads(archive.read('brief.json')),first)
        self.assertEqual(len(json.loads(archive.read('revisions.json'))),1)
        for line in archive.read('SHA256SUMS').decode().splitlines():
            digest,name=line.split('  ',1)
            self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(),digest)

    def test_package_is_repeatable_and_project_specific(self):
        a=self.create('a');b=self.create('b')
        self.assertEqual(studio.build_package(a),studio.build_package(a))
        self.assertNotEqual(studio.build_package(a),studio.build_package(b))

    def test_markup_remains_text(self):
        self.brief['name']='Studio </script><b>draft</b> & café'
        project=self.create()
        html=studio.render_planner(project)
        payload=html.split('<script id="brief-data" type="application/json">')[1].split('</script>')[0]
        self.assertNotIn('<',payload)
        self.assertEqual(json.loads(payload)['name'],self.brief['name'])
        self.assertNotIn('innerHTML',html)


class HTTPTests(Fixture):
    def setUp(self):
        super().setUp()
        self.server=studio.make_server(self.store,port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        super().tearDown()

    def request(self,path,method='GET',payload=None,raw=None,kind='application/json'):
        body=raw if raw is not None else None if payload is None else json.dumps(payload).encode()
        request=urllib.request.Request(self.base+path,data=body,method=method,headers={'Content-Type':kind})
        try:
            response=urllib.request.urlopen(request,timeout=5)
        except urllib.error.HTTPError as error:
            response=error
        with response:
            return response.status,response.headers,response.read()

    def test_http_full_workflow(self):
        status,_,body=self.request('/api/projects','POST',{'brief':self.brief,'request_id':'http-1'})
        self.assertEqual(status,201)
        project=json.loads(body);path='/api/projects/'+project['id']
        self.brief['name']='Updated via HTTP'
        status,_,body=self.request(path,'PUT',{'brief':self.brief,'expected_revision':1})
        self.assertEqual((status,json.loads(body)['revision']),(200,2))
        self.assertEqual(self.request(path,'PUT',{'brief':self.brief,'expected_revision':1})[0],409)
        status,_,body=self.request(path+'/history')
        self.assertEqual((status,len(json.loads(body)['revisions'])),(200,2))
        status,headers,body=self.request(path+'/export.zip')
        self.assertEqual((status,headers['Content-Type']),(200,'application/zip'))
        self.assertIn('index.html',zipfile.ZipFile(io.BytesIO(body)).namelist())
        self.assertEqual(self.request(path+'/preview')[0],200)

    def test_http_input_statuses(self):
        self.assertEqual(self.request('/api/projects','POST',raw=b'[]')[0],400)
        self.assertEqual(self.request('/api/projects','POST',raw=b'{')[0],400)
        self.assertEqual(self.request('/api/projects','POST',raw=b'{}',kind='text/plain')[0],415)
        self.assertEqual(self.request('/api/projects','POST',raw=b'x'*(studio.MAX_BODY+1))[0],413)
        self.assertEqual(self.request('/api/projects/'+'0'*32)[0],404)
        self.assertEqual(self.request('/does-not-exist')[0],404)

    def test_http_static_and_example(self):
        status,headers,body=self.request('/')
        self.assertEqual(status,200)
        self.assertIn('Creator App Studio',body.decode())
        self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
        self.assertEqual(json.loads(self.request('/api/example')[2]),self.brief)


if __name__=='__main__':
    unittest.main(verbosity=2)
