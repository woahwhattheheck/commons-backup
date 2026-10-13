"""Real temporary SQLite/HTTP tests; no real chats or external provider calls."""
import base64
import concurrent.futures
from contextlib import closing
import hashlib
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import app

# Small, valid synthetic PNG; never a customer's screenshot.
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII=')
IMAGE = {'name': 'fictional.png', 'data_base64': base64.b64encode(PNG).decode()}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dbpath = Path(self.temp.name) / 'desk.sqlite3'
        self.store = app.Store(self.dbpath)
        self.item = self.store.create({'title': 'Fictional weekend', 'transcript': 'Other: Easy walk or long hike?',
                                      'context': 'Prefer a low-key meeting', 'reply': 'I prefer an easy walk',
                                      'question': 'Which trail do you like'})

    def test_create_and_reopen(self):
        other = app.Store(self.dbpath)
        self.assertEqual(other.get(self.item['id']), self.item)
        self.assertEqual(len(other.list()), 1)

    def test_edit_corrected_transcript_and_draft_survive_reopen(self):
        got = self.store.update(self.item['id'], {'transcript': 'Corrected words', 'draft': 'My own reply'}, 1)
        self.assertEqual(got['revision'], 2)
        self.assertEqual(app.Store(self.dbpath).get(got['id'])['draft'], 'My own reply')
        self.assertEqual(got['transcript'], 'Corrected words')

    def test_stale_edit_preserves_first_writer(self):
        self.store.update(self.item['id'], {'draft': 'First writer'}, 1)
        with self.assertRaises(app.Conflict):
            self.store.update(self.item['id'], {'draft': 'Second writer'}, 1)
        self.assertEqual(self.store.get(self.item['id'])['draft'], 'First writer')

    def test_boolean_and_float_revisions_are_not_integer_revisions(self):
        for revision in [True, False, 1.0, '1', None, float('inf')]:
            with self.subTest(revision=revision), self.assertRaises(app.Conflict):
                self.store.update(self.item['id'], {'draft': 'No'}, revision)

    def test_concurrent_updates_only_one_wins(self):
        def write(n):
            try:
                self.store.update(self.item['id'], {'draft': str(n)}, 1)
                return True
            except app.Conflict:
                return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            outcomes = list(pool.map(write, range(4)))
        self.assertEqual(sum(outcomes), 1)
        self.assertEqual(self.store.get(self.item['id'])['revision'], 2)

    def test_original_screenshot_bytes_and_digest(self):
        record = self.store.add_image(self.item['id'], IMAGE, 1)
        stored = self.store.image(record['id'], record['images'][0]['id'])
        self.assertEqual(stored['data'], PNG)
        self.assertEqual(stored['sha256'], hashlib.sha256(PNG).hexdigest())
        self.assertEqual(record['revision'], 2)

    def test_screenshot_lookup_stays_in_selected_conversation(self):
        record = self.store.add_image(self.item['id'], IMAGE, 1)
        other = self.store.create({})
        with self.assertRaises(app.Missing):
            self.store.image(other['id'], record['images'][0]['id'])

    def test_delete_image_preserves_copied_transcript(self):
        record = self.store.add_image(self.item['id'], IMAGE, 1)
        got = self.store.delete_image(record['id'], record['images'][0]['id'], 2)
        self.assertEqual(got['images'], [])
        self.assertEqual(got['transcript'], self.item['transcript'])
        self.assertEqual(got['revision'], 3)

    def test_stale_delete_does_not_remove_screenshot(self):
        record = self.store.add_image(self.item['id'], IMAGE, 1)
        with self.assertRaises(app.Conflict):
            self.store.delete_image(record['id'], record['images'][0]['id'], 1)
        self.assertEqual(len(self.store.get(record['id'])['images']), 1)

    def test_delete_conversation_cascades_and_preserves_other(self):
        record = self.store.add_image(self.item['id'], IMAGE, 1)
        other = self.store.create({'title': 'Unrelated'})
        self.store.delete(record['id'], 2)
        with self.assertRaises(app.Missing):
            self.store.get(record['id'])
        with closing(sqlite3.connect(self.dbpath)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM images').fetchone()[0], 0)
        self.assertEqual(self.store.get(other['id'])['title'], 'Unrelated')

    def test_stale_conversation_delete_is_non_destructive(self):
        self.store.update(self.item['id'], {'draft': 'Keep'}, 1)
        with self.assertRaises(app.Conflict):
            self.store.delete(self.item['id'], 1)
        self.assertEqual(self.store.get(self.item['id'])['draft'], 'Keep')

    def test_export_original_bytes_and_all_text(self):
        record = self.store.add_image(self.item['id'], IMAGE, 1)
        self.store.update(record['id'], {'draft': 'A chosen response'}, 2)
        export = self.store.export()
        self.assertEqual(export['format'], 'conversation-desk-export-v1')
        self.assertEqual(base64.b64decode(export['images'][0]['data_base64']), PNG)
        self.assertEqual(export['conversations'][0]['draft'], 'A chosen response')
        self.assertEqual(export['images'][0]['conversation_id'], record['id'])
        json.dumps(export, allow_nan=False)

    def test_erase_removes_every_conversation_and_image_after_reopen(self):
        self.store.add_image(self.item['id'], IMAGE, 1)
        self.store.create({'title': 'Another', 'draft': 'Remove this too'})
        self.store.erase()
        reopened = app.Store(self.dbpath)
        self.assertEqual(reopened.list(), [])
        self.assertEqual(reopened.export()['images'], [])

    def test_invalid_fields_leave_database_unchanged(self):
        for value in [None, [], {'title': ' '}, {'draft': False}, {'intent': 'unknown'},
                      {'transcript': 'x' * 30001}, {'draft': '\x00'}, {'context': '\ud800'}]:
            with self.subTest(value=repr(value)[:60]), self.assertRaises(app.DeskError):
                self.store.update(self.item['id'], value, 1)
        self.assertEqual(self.store.get(self.item['id']), self.item)

    def test_bad_image_bytes_are_not_saved(self):
        for value in [{}, {'data_base64': '@@@'}, {'data_base64': 'YQ=='},
                      {**IMAGE, 'name': ''}, {**IMAGE, 'name': '\ud800'}]:
            with self.subTest(value=repr(value)[:80]), self.assertRaises(app.DeskError):
                self.store.add_image(self.item['id'], value, 1)
        self.assertEqual(self.store.get(self.item['id'])['revision'], 1)
        self.assertEqual(self.store.export()['images'], [])

    def test_size_boundary_rejects_before_storage(self):
        with patch.object(app, 'MAX_IMAGE', len(PNG) - 1), self.assertRaises(app.DeskError):
            self.store.add_image(self.item['id'], IMAGE, 1)


class DraftTests(unittest.TestCase):
    def test_three_options_use_user_words(self):
        result = app.suggestions({'intent': 'respond', 'reply': 'Saturday works for me', 'question': 'Coffee at noon'})
        self.assertEqual(result['engine'], 'local-templates-v1')
        self.assertEqual([s['tone'] for s in result['suggestions']], ['Warm', 'Direct', 'Light'])
        self.assertEqual(len({s['text'] for s in result['suggestions']}), 3)
        for option in result['suggestions']:
            self.assertIn('Saturday works for me.', option['text'])
            self.assertIn('Coffee at noon?', option['text'])

    def test_all_five_intents_have_distinct_options(self):
        for intent in app.INTENTS:
            with self.subTest(intent=intent):
                values = {'intent': intent, 'reply': 'My chosen point', 'question': 'My chosen question'}
                result = app.suggestions(values)['suggestions']
                self.assertEqual(len({s['text'] for s in result}), 3)
                self.assertTrue(all('My chosen point.' in s['text'] for s in result))

    def test_no_facts_inferred_from_other_person_or_notes(self):
        values = {'transcript': 'You love skiing in Oslo', 'context': 'secret-cobalt-note',
                  'reply': 'I prefer walking', 'intent': 'respond'}
        result = json.dumps(app.suggestions(values))
        for text in ['Oslo', 'skiing', 'secret-cobalt-note']:
            self.assertNotIn(text, result)

    def test_missing_reply_or_question_remains_explicit(self):
        for value in [{}, {'intent': 'invite'}, {'intent': 'follow_up', 'reply': 'Interesting'}]:
            with self.subTest(value=value), self.assertRaises(app.DeskError):
                app.suggestions(value)
        self.assertEqual(len(app.suggestions({'intent': 'follow_up', 'question': 'Which one?'})['suggestions']), 3)

    def test_boundary_and_close_use_gentle_not_flirtatious_tone(self):
        for intent in ['boundary', 'close']:
            result = app.suggestions({'intent': intent, 'reply': 'I do not want to continue'})
            self.assertEqual(result['suggestions'][2]['tone'], 'Gentle')
            self.assertTrue(all('I do not want to continue.' in s['text'] for s in result['suggestions']))

    def test_unicode_and_multiline_words_preserved(self):
        result = app.suggestions({'reply': 'Café sounds good!\nSunday works for me.', 'question': 'At 10?'})
        self.assertIn('Café sounds good!\nSunday works for me.', result['suggestions'][1]['text'])

    def test_missing_ocr_has_manual_route(self):
        with patch('app.shutil.which', return_value=None), self.assertRaisesRegex(app.DeskError, 'manually'):
            app.transcribe(PNG)

    def test_ocr_failure_is_a_user_diagnostic(self):
        # Failure-path doubles only; the executed real OCR check is a separate synthetic-image smoke.
        with patch('app.shutil.which', return_value='/usr/bin/tesseract'), patch('app.subprocess.run') as run:
            run.return_value.returncode = 1
            with self.assertRaisesRegex(app.DeskError, 'manually'):
                app.transcribe(PNG)
            self.assertNotIn('shell', run.call_args.kwargs)


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.store = app.Store(Path(cls.temp.name) / 'http.sqlite3')
        cls.httpd = app.server(cls.store, port=0)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.httpd.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); cls.thread.join(); cls.httpd.server_close(); cls.temp.cleanup()

    def request(self, path, method='GET', body=None, raw=None, content_type='application/json'):
        data = raw if raw is not None else None if body is None else json.dumps(body).encode()
        request = Request(self.base + path, data=data, method=method, headers={'Content-Type': content_type})
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.read(), response.headers

    def test_complete_real_http_workflow(self):
        code, body, _ = self.request('/api/conversations', 'POST', {'title': 'HTTP fictional', 'reply': 'I prefer an easy walk'})
        self.assertEqual(code, 201); item = json.loads(body); root = '/api/conversations/' + item['id']
        code, body, _ = self.request(root + '/images', 'POST', {**IMAGE, 'expected_revision': 1})
        self.assertEqual(code, 201); image = json.loads(body)['images'][0]
        code, body, _ = self.request(root + '/images/' + image['id'])
        self.assertEqual((code, body), (200, PNG))
        code, body, _ = self.request(root, 'POST', {'expected_revision': 2, 'transcript': 'Corrected screenshot text'})
        self.assertEqual(code, 200); self.assertEqual(json.loads(body)['revision'], 3)
        code, body, _ = self.request(root + '/suggest', 'POST', {'expected_revision': 3})
        self.assertEqual(code, 200); draft = json.loads(body)['suggestions'][1]['text'] + ' My edit.'
        code, _, _ = self.request(root, 'POST', {'expected_revision': 3, 'draft': draft})
        self.assertEqual(code, 200)
        code, body, _ = self.request(root)
        self.assertEqual(json.loads(body)['draft'], draft)
        self.assertEqual(self.request(root, 'DELETE', {'expected_revision': 4})[0], 200)
        self.assertEqual(self.request(root)[0], 404)
        self.assertEqual(self.request(root + '/images/' + image['id'])[0], 404)

    def test_invalid_json_and_non_object_diagnostics(self):
        for raw in [b'{', b'[]', b'null', b'NaN', b'"string"', b'\xff']:
            with self.subTest(raw=raw):
                code, body, _ = self.request('/api/conversations', 'POST', raw=raw)
                self.assertEqual(code, 400)
                self.assertIn('error', json.loads(body))

    def test_wrong_media_type_is_rejected(self):
        self.assertEqual(self.request('/api/conversations', 'POST', raw=b'{}', content_type='text/plain')[0], 400)

    def test_unknown_route_and_missing_record(self):
        for path in ['/absent', '/api/conversations/missing', '/app.py']:
            self.assertEqual(self.request(path)[0], 404)

    def test_export_download_and_privacy_headers(self):
        code, body, headers = self.request('/api/export')
        self.assertEqual(code, 200)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertIn('attachment', headers['Content-Disposition'])
        self.assertEqual(json.loads(body)['format'], 'conversation-desk-export-v1')

    def test_static_assets_are_real_and_csp_compatible(self):
        code, body, headers = self.request('/')
        self.assertEqual(code, 200)
        self.assertIn(b'<meta name="viewport"', body)
        self.assertIn(b'<script src="desk.js" defer>', body)
        self.assertIn("script-src 'self'", headers['Content-Security-Policy'])
        self.assertEqual(self.request('/desk.js')[0], 200)

    def test_state_reports_ocr_capability(self):
        code, body, _ = self.request('/api/state')
        self.assertEqual(code, 200)
        self.assertIsInstance(json.loads(body)['ocr_available'], bool)

    def test_stale_generation_and_update_return_conflict(self):
        _, body, _ = self.request('/api/conversations', 'POST', {'reply': 'Hello'})
        root = '/api/conversations/' + json.loads(body)['id']
        self.assertEqual(self.request(root, 'POST', {'expected_revision': 1, 'draft': 'Saved'})[0], 200)
        self.assertEqual(self.request(root + '/suggest', 'POST', {'expected_revision': 1})[0], 409)
        self.assertEqual(self.request(root, 'POST', {'expected_revision': 1, 'draft': 'Lost'})[0], 409)

    def test_erase_requires_deliberate_confirmation(self):
        self.assertEqual(self.request('/api/erase', 'POST', {'confirmation': 'no'})[0], 400)
        self.assertEqual(self.request('/api/erase', 'POST', {'confirmation': 'ERASE'})[0], 200)
        self.assertEqual(self.store.export()['conversations'], [])
        self.assertEqual(self.store.export()['images'], [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
