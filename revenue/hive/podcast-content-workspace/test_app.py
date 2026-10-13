"""Real SQLite, HTTP and export regression tests; no external accounts or sends."""
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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app import Conflict, Invalid, Missing, Server, Store, generate, timestamp, validate_document


def document():
    return {'title': 'Original sample', 'duration': 120, 'description': 'An original test fixture.',
            'synthetic_demo': True,
            'segments': [{'id': f's{i}', 'start': i * 10, 'end': i * 10 + 8,
                          'speaker': 'Synthetic narrator', 'text': f'Distinct original passage {i}.',
                          'verified': False} for i in range(6)],
            'chapters': [{'start': 0, 'title': 'Start'}, {'start': 30, 'title': 'Next'}]}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'workspace.sqlite'
        self.store = Store(self.path)
        self.episode = self.store.create(document())

    def test_reopen_persists_source(self):
        self.assertEqual(Store(self.path).get(self.episode['id']), self.episode)

    def test_canonical_input_does_not_mutate_caller(self):
        source = document(); original = copy.deepcopy(source)
        result = validate_document(source)
        result['segments'][0]['text'] = 'changed'
        self.assertEqual(source, original)

    def test_unicode_source_survives(self):
        doc = document(); doc['title'] = '日本語 / العربية / Café'
        doc['segments'][0]['text'] = '日本語の原稿 · نص أصلي · Café'
        episode = self.store.create(doc)
        self.assertEqual(episode['document']['segments'][0]['text'], doc['segments'][0]['text'])

    def test_malformed_timestamps_rejected(self):
        for value in (None, [], {}, '10', True, float('nan'), float('inf'), -1, 10**1000):
            with self.subTest(value=repr(value)[:60]):
                doc = document(); doc['segments'][0]['start'] = value
                with self.assertRaises(Invalid): self.store.create(doc)

    def test_invalid_shapes_rejected(self):
        for key, value in [('segments', {}), ('chapters', None), ('title', []), ('synthetic_demo', 1), ('duration', 0)]:
            with self.subTest(key=key):
                doc = document(); doc[key] = value
                with self.assertRaises(Invalid): self.store.create(doc)

    def test_nonchronological_overlap_and_duplicates_rejected(self):
        for edit in ('overlap', 'duplicate', 'reversed', 'outside', 'chapter'):
            doc = document()
            if edit == 'overlap': doc['segments'][1]['start'] = 1
            if edit == 'duplicate': doc['segments'][1]['id'] = 's0'
            if edit == 'reversed': doc['segments'][0]['end'] = 0
            if edit == 'outside': doc['segments'][-1]['end'] = 121
            if edit == 'chapter': doc['chapters'][1]['start'] = 0
            with self.subTest(edit=edit), self.assertRaises(Invalid): self.store.create(doc)

    def test_segment_ids_and_review_flags(self):
        for key, value in [('id', '../bad'), ('verified', 'yes'), ('speaker', {}), ('text', '')]:
            doc = document(); doc['segments'][0][key] = value
            with self.subTest(key=key), self.assertRaises(Invalid): self.store.create(doc)

    def test_five_distinct_post_source_groups(self):
        generated = generate(self.episode['document'])
        self.assertEqual(len(set(generated['posts'])), 5)
        sources = sum(generated['source_map'].values(), [])
        self.assertEqual(sources, [s['id'] for s in self.episode['document']['segments']])
        self.assertTrue(all(generated['source_map'].values()))
        for s in self.episode['document']['segments']:
            self.assertIn(s['text'].replace('.', '\\.'), generated['show_notes'])

    def test_less_than_five_segments_not_disguised_as_five_posts(self):
        doc = document(); doc['segments'] = doc['segments'][:4]
        with self.assertRaises(Invalid): generate(doc)

    def test_imported_markup_is_text_not_links(self):
        doc = document(); doc['segments'][0]['text'] = '<script>alert(1)</script> [click](javascript:bad)'
        generated = generate(doc)['show_notes']
        self.assertNotIn('<script>', generated)
        self.assertNotIn('[click](', generated)
        self.assertIn('&lt;script&gt;', generated)

    def test_existing_drafts_need_explicit_replace(self):
        e = self.store.make_drafts(self.episode['id'], 1)
        drafts = e['drafts']; drafts['newsletter'] = 'My edited newsletter'
        e = self.store.save_drafts(e['id'], e['revision'], drafts)
        with self.assertRaises(Conflict): self.store.make_drafts(e['id'], e['revision'])
        self.assertEqual(self.store.get(e['id'])['drafts']['newsletter'], 'My edited newsletter')
        e = self.store.make_drafts(e['id'], e['revision'], replace=True)
        self.assertNotEqual(e['drafts']['newsletter'], 'My edited newsletter')

    def test_source_change_preserves_and_marks_drafts_stale(self):
        e = self.store.make_drafts(self.episode['id'], 1)
        drafts = copy.deepcopy(e['drafts'])
        doc = e['document']; doc['segments'][0]['text'] = 'Corrected quotation'
        e = self.store.save_document(e['id'], e['revision'], doc)
        self.assertTrue(e['drafts_stale']); self.assertEqual(e['drafts'], drafts)

    def test_replacing_media_also_marks_drafts_stale(self):
        e = self.store.make_drafts(self.episode['id'], 1)
        e = self.store.upload(e['id'], e['revision'], 'audio.wav', b'original')
        self.assertTrue(e['drafts_stale'])
        self.assertEqual(e['media']['sha256'], hashlib.sha256(b'original').hexdigest())

    def test_stale_export_with_shortened_transcript_preserves_edits(self):
        e = self.store.make_drafts(self.episode['id'], 1)
        drafts = copy.deepcopy(e['drafts']); drafts['newsletter'] = 'Preserve this working copy'
        e = self.store.save_drafts(e['id'], e['revision'], drafts)
        doc = e['document']; doc['segments'] = doc['segments'][:2]
        self.store.save_document(e['id'], e['revision'], doc)
        with zipfile.ZipFile(io.BytesIO(self.store.export(e['id']))) as packet:
            self.assertEqual(packet.read('newsletter.md').decode(), 'Preserve this working copy')
            self.assertIn('stale', packet.read('README.txt').decode())
            self.assertTrue(json.loads(packet.read('source-map.json'))['drafts_stale'])

    def test_media_roundtrip_and_export_packet(self):
        media = bytes(range(256)) * 8
        e = self.store.upload(self.episode['id'], 1, 'original.wav', media)
        e = self.store.make_drafts(e['id'], e['revision'])
        with zipfile.ZipFile(io.BytesIO(self.store.export(e['id']))) as packet:
            self.assertEqual(packet.read('source-media/original.wav'), media)
            self.assertEqual(len([p for p in packet.namelist() if p.startswith('posts/')]), 5)
            for name in ('transcript.json', 'transcript.vtt', 'transcript.srt', 'chapters.csv', 'source-map.json', 'show-notes.md', 'newsletter.md'):
                self.assertIn(name, packet.namelist())
            manifest = json.loads(packet.read('source-map.json'))
            self.assertFalse(manifest['drafts_stale'])
            self.assertEqual(manifest['media']['sha256'], hashlib.sha256(media).hexdigest())
            self.assertTrue(packet.read('transcript.vtt').startswith(b'WEBVTT\n\n'))

    def test_media_names_cannot_escape_export_folder(self):
        for name in ('../evil.wav', 'x/y.wav', 'x\\y.wav', 'x\r.wav', 'x.html', ''):
            with self.subTest(name=name), self.assertRaises(Invalid):
                self.store.upload(self.episode['id'], 1, name, b'abc')

    def test_invalid_media_empty_or_over_limit(self):
        with self.assertRaises(Invalid): self.store.upload(self.episode['id'], 1, 'x.wav', b'')

    def test_stale_revision_does_not_overwrite(self):
        doc = document(); doc['title'] = 'First writer'
        self.store.save_document(self.episode['id'], 1, doc)
        doc['title'] = 'Stale writer'
        with self.assertRaises(Conflict): self.store.save_document(self.episode['id'], 1, doc)
        self.assertEqual(self.store.get(self.episode['id'])['document']['title'], 'First writer')

    def test_real_concurrent_writers_only_one_wins(self):
        barrier = threading.Barrier(2)
        def write(name):
            doc = document(); doc['title'] = name
            barrier.wait()
            try:
                self.store.save_document(self.episode['id'], 1, doc)
                return 'saved'
            except Conflict:
                return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(write, ['Writer A', 'Writer B']))
        self.assertEqual(sorted(results), ['conflict', 'saved'])
        self.assertEqual(self.store.get(self.episode['id'])['revision'], 2)

    def test_invalid_revision_and_draft_shapes(self):
        for rev in (None, True, 0, '1', []):
            with self.subTest(rev=rev), self.assertRaises(Invalid): self.store.save_document(self.episode['id'], rev, document())
        with self.assertRaises(Invalid): self.store.save_drafts(self.episode['id'], 1, {'posts': []})

    def test_delete_removes_application_record_and_media(self):
        e = self.store.upload(self.episode['id'], 1, 'x.wav', b'abc')
        with self.assertRaises(Conflict): self.store.delete(e['id'], 1)
        self.store.delete(e['id'], e['revision'])
        with self.assertRaises(Missing): self.store.get(e['id'])
        with self.assertRaises(Missing): self.store.media(e['id'])
        self.assertEqual(self.store.list(), [])

    def test_csv_formula_titles_display_escaped(self):
        doc = document(); doc['chapters'][0]['title'] = '=1+1'
        e = self.store.create(doc); self.store.make_drafts(e['id'], 1)
        with zipfile.ZipFile(io.BytesIO(self.store.export(e['id']))) as packet:
            self.assertIn("'=1+1", packet.read('chapters.csv').decode())
            self.assertEqual(json.loads(packet.read('transcript.json'))['chapters'][0]['title'], '=1+1')

    def test_caption_millisecond_carry(self):
        self.assertEqual(timestamp(59.9999), '00:01:00.000')
        self.assertEqual(timestamp(3600.125, ','), '01:00:00,125')


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'db.sqlite')
        self.server = Server(('127.0.0.1', 0), self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.tmp.cleanup()

    def request(self, path, method='GET', data=None, headers=None):
        if isinstance(data, dict):
            data = json.dumps(data).encode()
            headers = {'Content-Type': 'application/json', **(headers or {})}
        req = urllib.request.Request(self.base + path, data=data, headers=headers or {}, method=method)
        try: response = urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as exc: response = exc
        with response:
            return response.status, dict(response.headers), response.read()

    def create(self):
        status, _, data = self.request('/api/episodes', 'POST', document())
        self.assertEqual(status, 201)
        return json.loads(data)

    def test_complete_http_create_edit_generate_export_delete(self):
        e = self.create(); route = f"/api/episodes/{e['id']}"
        doc = e['document']; doc['title'] = 'HTTP working episode'
        status, _, data = self.request(route, 'PUT', {'revision': 1, 'document': doc})
        self.assertEqual(status, 200); e = json.loads(data)
        status, _, data = self.request(route + '/generate', 'POST', {'revision': e['revision']})
        self.assertEqual(status, 200); e = json.loads(data)
        e['drafts']['newsletter'] = 'Human-edited delivery'
        status, _, data = self.request(route + '/drafts', 'PUT', {'revision': e['revision'], 'drafts': e['drafts']})
        self.assertEqual(status, 200); e = json.loads(data)
        status, headers, data = self.request(route + '/export')
        self.assertEqual(status, 200); self.assertEqual(headers['Content-Type'], 'application/zip')
        with zipfile.ZipFile(io.BytesIO(data)) as packet:
            self.assertEqual(packet.read('newsletter.md').decode(), 'Human-edited delivery')
        self.assertEqual(self.request(route, 'DELETE', {'revision': e['revision']})[0], 200)
        self.assertEqual(self.request(route)[0], 404)

    def test_http_media_ranges_suffix_head_and_original(self):
        e = self.create(); route = f"/api/episodes/{e['id']}/media"
        payload = b'0123456789'
        self.assertEqual(self.request(route + '?filename=sample.wav', 'POST', payload, {'If-Match': '1'})[0], 200)
        self.assertEqual(self.request(route)[2], payload)
        status, headers, data = self.request(route, headers={'Range': 'bytes=2-5'})
        self.assertEqual((status, data), (206, b'2345'))
        self.assertEqual(headers['Content-Range'], 'bytes 2-5/10')
        self.assertEqual(self.request(route, headers={'Range': 'bytes=-3'})[2], b'789')
        self.assertEqual(self.request(route, headers={'Range': 'bytes=7-'})[2], b'789')
        status, headers, data = self.request(route, 'HEAD')
        self.assertEqual((status, data, headers['Content-Length']), (200, b'', '10'))
        for value in ('bytes=20-', 'bytes=-0', 'bytes=5-2', 'bytes=-', 'bytes=1-2,4-5'):
            self.assertEqual(self.request(route, headers={'Range': value})[0], 416)

    def test_http_bad_json_types_and_overflow(self):
        for data in (b'[]', b'{broken', b'{"title":NaN}', b'null', b'{"title":"x","duration":1e999,"segments":[]}'):
            with self.subTest(data=data): self.assertEqual(self.request('/api/episodes', 'POST', data)[0], 400)

    def test_http_conflict_preserves_record(self):
        e = self.create(); route = f"/api/episodes/{e['id']}"
        self.assertEqual(self.request(route, 'PUT', {'revision': 1, 'document': document()})[0], 200)
        self.assertEqual(self.request(route, 'PUT', {'revision': 1, 'document': document()})[0], 409)

    def test_http_missing_routes_do_not_leak_files(self):
        self.assertEqual(self.request('/../app.py')[0], 404)
        self.assertEqual(self.request('/app.py')[0], 404)
        self.assertEqual(self.request('/api/episodes/' + 'a' * 32)[0], 404)

    def test_http_missing_media_revision_and_bad_replace_type(self):
        e = self.create(); route = f"/api/episodes/{e['id']}"
        self.assertEqual(self.request(route + '/media?filename=a.wav', 'POST', b'a')[0], 400)
        self.assertEqual(self.request(route + '/generate', 'POST', {'revision': 1, 'replace': 'yes'})[0], 400)

    def test_index_and_head_are_served(self):
        status, headers, data = self.request('/')
        self.assertEqual(status, 200)
        self.assertIn(b'Podcast Content Desk', data)
        self.assertIn(b'aria-live', data)
        status, head_headers, body = self.request('/', 'HEAD')
        self.assertEqual(status, 200); self.assertEqual(body, b'')
        self.assertEqual(headers['Content-Length'], head_headers['Content-Length'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
