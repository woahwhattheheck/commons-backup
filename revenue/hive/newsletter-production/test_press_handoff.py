#!/usr/bin/env python3
"""Actual WREN component consumption and saved-revision HTTP contracts."""
import copy
from email.parser import BytesParser
from email.policy import default
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import email_handoff
import press
import test_press

class HandoffConsumerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = press.Store(Path(self.temp.name) / 'consumer.sqlite3')
        self.view = self.store.create(copy.deepcopy(test_press.DEMO))
    def tearDown(self):
        self.temp.cleanup()
    def test_real_component_is_called_and_its_bytes_are_preserved(self):
        with patch.object(press, 'build_email_bundle', wraps=email_handoff.build_email_bundle, create=True) as call:
            blob = press.export_package(self.view)
            self.assertEqual(call.call_count, 1)
            args, kwargs = call.call_args
            expected = email_handoff.build_email_bundle(*args, **kwargs)
        with zipfile.ZipFile(io.BytesIO(expected)) as peer, zipfile.ZipFile(io.BytesIO(blob)) as outer:
            for name in peer.namelist():
                self.assertEqual(outer.read('email-handoff/' + name), peer.read(name))
    def test_mime_drafts_preserve_copy_footer_subject_and_no_delivery_headers(self):
        self.view['document']['issues'][0]['body'] = 'Editable café 東京.\nSecond line.'
        self.view['document']['brand']['footer'] = 'Fictional footer — not sent.'
        self.view = self.store.save(self.view['id'], 1, self.view['document'])
        with zipfile.ZipFile(io.BytesIO(press.export_package(self.view))) as z:
            self.assertEqual(len(z.namelist()), 30)
            for n, issue in enumerate(self.view['document']['issues'], 1):
                body = issue['body'] + '\n\n' + self.view['document']['brand']['footer']
                self.assertEqual(z.read(f'email-handoff/issues/{n:02d}.txt'), body.encode())
                mail = BytesParser(policy=default).parsebytes(z.read(f'email-handoff/issues/{n:02d}.eml'))
                self.assertEqual(str(mail['Subject']), issue['subject'])
                self.assertEqual(mail['X-Unsent'], '1')
                self.assertTrue(mail.is_multipart())
                for header in ('From','To','Bcc','Date','Message-ID'):
                    self.assertIsNone(mail[header])
                self.assertEqual(mail.get_body(preferencelist=('plain',)).get_content().replace('\r\n','\n'), body + '\n')
    def test_saved_source_and_revision_metadata_follow_the_actual_workspace(self):
        v = self.view
        with zipfile.ZipFile(io.BytesIO(press.export_package(v))) as z:
            meta = json.loads(z.read('email-handoff/source-metadata.json'))
            self.assertEqual(meta['project_id'], v['id'])
            self.assertEqual(meta['source_revision'], v['revision'])
            self.assertEqual(meta['original_interview_sha256'], hashlib.sha256(v['document']['original_interview'].encode()).hexdigest())
            self.assertEqual(meta['review_needed'], v['review_needed'])
            manifest = json.loads(z.read('email-handoff/manifest.json'))
            self.assertEqual(manifest['delivery_state'], 'UNSENT_EXPORT')
            self.assertEqual(manifest['scheduling_state'], 'NOT_SCHEDULED')
            for a, b in zip(manifest['issues'], v['document']['issues']):
                self.assertEqual(a['source_refs'], b['source_ids'])
                self.assertEqual(a['scheduled_at'], b['scheduled_utc'])
            self.assertEqual(z.read('original-interview.txt'), v['document']['original_interview'].encode())
        doc = copy.deepcopy(v['document']); del doc['sources'][0]['reference']
        updated = self.store.save(v['id'], v['revision'], doc)
        with zipfile.ZipFile(io.BytesIO(press.export_package(updated))) as z:
            self.assertEqual(json.loads(z.read('email-handoff/source-metadata.json'))['working_sources'][0]['reference'], '')
    def test_outer_manifest_covers_every_added_component_file(self):
        with zipfile.ZipFile(io.BytesIO(press.export_package(self.view))) as z:
            manifest = json.loads(z.read('manifest.json'))
            self.assertEqual(set(manifest['files']), set(z.namelist()) - {'manifest.json'})
            for name, meta in manifest['files'].items():
                self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(), meta['sha256'])
    def test_component_rejection_has_no_storage_side_effect_or_partial_return(self):
        before = self.store.get(self.view['id'])
        self.view['document']['brand']['name'] = 'Unsupported\npublication'
        with self.assertRaises(press.Invalid):
            press.export_package(self.view)
        self.assertEqual(self.store.get(before['id']), before)
    def test_export_keeps_peer_source_unchanged(self):
        source = Path(email_handoff.__file__)
        before = source.read_bytes()
        press.export_package(self.view)
        self.assertEqual(source.read_bytes(), before)

class RevisionHTTPTests(unittest.TestCase):
    setUpClass = classmethod(test_press.HttpTests.setUpClass.__func__)
    tearDownClass = classmethod(test_press.HttpTests.tearDownClass.__func__)
    request = test_press.HttpTests.request
    def test_preview_resolves_selected_history_not_latest_copy(self):
        old = self.store.create(copy.deepcopy(test_press.DEMO))
        doc = copy.deepcopy(old['document']); doc['issues'][0]['body'] = 'Newer revision copy.'
        newer = self.store.save(old['id'], 1, doc)
        code, body, _ = self.request('/preview/' + old['id'] + '/week1?revision=1')
        self.assertEqual(code, 200)
        self.assertEqual(body.decode(), press.render(old['document'], old['document']['issues'][0], True))
        code, body, _ = self.request('/preview/' + old['id'] + '/week1?revision=2')
        self.assertEqual(body.decode(), press.render(newer['document'], newer['document']['issues'][0], True))
        self.assertEqual(self.request('/preview/' + old['id'] + '/week1?revision=999')[0], 404)
    def test_export_rejects_stale_revision_and_current_http_zip_has_mime(self):
        v = self.store.create(copy.deepcopy(test_press.DEMO))
        new = self.store.save(v['id'], 1, v['document'])
        self.assertEqual(self.request('/export/' + v['id'] + '?revision=1')[0], 409)
        code, body, _ = self.request('/export/' + v['id'] + '?revision=2')
        self.assertEqual(code, 200)
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            self.assertEqual(len([n for n in z.namelist() if n.endswith('.eml')]), 4)
            self.assertEqual(json.loads(z.read('manifest.json'))['revision'], new['revision'])
    def test_invalid_revision_queries_rejected_consistently(self):
        v = self.store.create(copy.deepcopy(test_press.DEMO))
        for route in ('/api/projects/' + v['id'], '/preview/' + v['id'] + '/week1', '/export/' + v['id']):
            for query in ('revision=', 'revision=0', 'revision=-1', 'revision=abc', 'revision=9999999999', 'revision=1&revision=2'):
                with self.subTest(route=route, query=query):
                    self.assertEqual(self.request(route + '?' + query)[0], 400)
    def test_editor_links_pin_export_and_preview_revision(self):
        code, body, _ = self.request('/')
        self.assertEqual(code, 200)
        self.assertIn(b'/export/${view.id}?revision=${view.revision}', body)
        self.assertIn(b'?ready=1&revision=${current.revision}', body)
        self.assertIn(b'/preview/${current.id}/${i.id}?revision=${current.revision}', body)

if __name__ == '__main__':
    unittest.main(verbosity=2)
