"""Native app.py process and JavaScript render acceptance for results downloads.

Node.js enables the explicit DOM-fixture tests. They execute the real render()
function, not a browser engine; HTTP tests always launch the actual server CLI.
"""
from __future__ import annotations

import csv
import http.client
import io
import json
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parent
NODE = shutil.which("node")
DOM_SCRIPT = r"""
const fs = require('node:fs'), vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.textContent = ''; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(key, value) { this[key] = value; }
}
const ids = Object.create(null);
const document = {
  getElementById: id => ids[id] || (ids[id] = new Element('div')),
  createElement: tag => new Element(tag)
};
const context = {
  document, URLSearchParams, location: {search: '', href: 'https://lantern.invalid/'},
  history: {replaceState() {}}, localStorage: {getItem() {return null}, setItem() {}, removeItem() {}},
  fetch: async () => ({ok: true, json: async () => []}),
  setInterval: () => 0, confirm: () => false, fixture: input.state
};
const match = input.html.match(/<script>([\s\S]*?)<\/script>/);
if (!match) throw new Error('Native page script not found');
vm.runInNewContext(match[1] + '\nrender(fixture);', context, {timeout: 1000});
const links = [];
function walk(element) {
  if (element.tag === 'a') links.push({text: element.textContent,
    href: element.href, download: element.download});
  for (const child of element.children) walk(child);
}
walk(ids.stage);
process.stdout.write(JSON.stringify(links));
"""


class ResultsDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / 'native events.sqlite3'
        self.process = None
        self.host_keys = {}
        self.start_server()
        self.addCleanup(self.stop_server)

    def start_server(self):
        self.process = subprocess.Popen(
            [sys.executable, '-B', str(ROOT / 'app.py'), '--db', str(self.database),
             '--host', '127.0.0.1', '--port', '0'],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8')
        lines = queue.Queue()
        process = self.process
        reader = threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True)
        reader.start()
        try:
            line = lines.get(timeout=5)
            match = re.fullmatch(r'Lantern is serving on http://127\.0\.0\.1:(\d+)\n', line)
            if not match:
                raise AssertionError('Unexpected server startup: ' + repr(line))
            self.port = int(match.group(1))
        except BaseException:
            self.stop_server()
            raise
        finally:
            reader.join(timeout=1)

    def stop_server(self):
        if self.process is not None:
            process, self.process = self.process, None
            process.terminate()
            try:
                _, error = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                _, error = process.communicate(timeout=5)
            self.assertNotIn('Traceback', error)
            self.assertNotIn('ResourceWarning', error)

    def request(self, path, payload=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        try:
            body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
            connection.request('GET' if payload is None else 'POST', path, body=body,
                               headers={} if body is None else {'Content-Type': 'application/json'})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def api(self, path, payload=None, expected=200):
        status, _, body = self.request(path, payload)
        self.assertEqual(status, expected, body)
        return json.loads(body)

    def create(self, **changes):
        now = time.time()
        payload = {'title': 'Native results', 'room': 'Test room', 'opens': now-60,
                   'ends': now+3600, 'questions': [
                       {'prompt': 'Select A', 'choices': ['A', 'B'], 'correct': 0, 'points': 250}]}
        payload.update(changes)
        created = self.api('/api/events', payload, expected=201)
        self.host_keys[created['id']] = created['host_key']
        return created['id']

    def player(self, event, name, choice=None):
        member = self.api(f'/api/events/{event}/join', {'name': name})['id']
        if choice is not None:
            self.api(f'/api/events/{event}/answers', {'member_id': member, 'question': 0, 'choice': choice})
        return member

    def finish(self, event):
        return self.api(f'/api/events/{event}/finish', {'host_key': self.host_keys[event]})

    def download(self, event, format='json'):
        status, headers, body = self.request(f'/api/events/{event}/results.{format}')
        self.assertEqual(status, 200, body)
        mime = 'text/csv' if format == 'csv' else 'application/json'
        self.assertEqual(headers['Content-Type'], mime + '; charset=utf-8')
        self.assertEqual(headers['Content-Disposition'], f'attachment; filename="lantern-results.{format}"')
        self.assertEqual(int(headers['Content-Length']), len(body))
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        return body

    def render_links(self, state):
        status, _, page = self.request('/')
        self.assertEqual(status, 200)
        process = subprocess.run([NODE, '-e', DOM_SCRIPT],
            input=json.dumps({'html': page.decode('utf-8'), 'state': state}, ensure_ascii=False),
            capture_output=True, text=True, timeout=5)
        self.assertEqual(process.returncode, 0, process.stderr)
        return json.loads(process.stdout)

    def test_native_create_join_answer_finish_then_both_downloads(self):
        event = self.create()
        references = [self.player(event, 'First', 0), self.player(event, 'Second', 0),
                      self.player(event, 'No answer')]
        self.finish(event)
        data = self.download(event)
        document = json.loads(data)
        self.assertEqual(document['schema'], 'lantern.results.v1')
        self.assertEqual([r['rank'] for r in document['leaderboard']], [1, 1, 3])
        self.assertEqual([r['points'] for r in document['leaderboard']], [250, 250, 0])
        self.assertEqual(document['participants'], 3)
        for reference in references:
            self.assertNotIn(reference.encode(), data)
        self.assertNotIn(b'"correct"', data)
        rows = list(csv.DictReader(io.StringIO(self.download(event, 'csv').decode('utf-8-sig'))))
        self.assertEqual([r['rank'] for r in rows], ['1', '1', '3'])
        self.assertEqual([r['points'] for r in rows], ['250', '250', '0'])

    def test_open_event_is_json_409_from_the_real_main_entry_point(self):
        event = self.create()
        self.player(event, 'Player', 0)
        for format in ('csv', 'json'):
            status, headers, body = self.request(f'/api/events/{event}/results.{format}')
            self.assertEqual(status, 409, body)
            self.assertEqual(headers['Content-Type'], 'application/json; charset=utf-8')
            self.assertNotIn('Content-Disposition', headers)
            self.assertIn('only after the event finishes', json.loads(body)['error'])
        self.assertEqual(self.api(f'/api/events/{event}')['phase'], 'open')
        self.assertEqual(self.api('/health'), {'ok': True})

    def test_scheduled_event_is_json_409_without_mutation(self):
        now = time.time()
        event = self.create(opens=now+600, ends=now+3600)
        for format in ('json', 'csv'):
            status, headers, body = self.request(f'/api/events/{event}/results.{format}')
            self.assertEqual(status, 409, body)
            self.assertNotIn('Content-Disposition', headers)
        self.assertEqual(self.api(f'/api/events/{event}')['phase'], 'scheduled')

    def test_unknown_event_is_normal_json_404(self):
        for format in ('csv', 'json'):
            status, headers, body = self.request('/api/events/missing/results.' + format)
            self.assertEqual(status, 404, body)
            self.assertEqual(json.loads(body), {'error': 'Event not found'})
            self.assertNotIn('Content-Disposition', headers)

    def test_unsupported_formats_and_methods_remain_not_found(self):
        event = self.create()
        self.finish(event)
        for path, payload in ((f'/api/events/{event}/results.xml', None),
                              (f'/api/events/{event}/results.CSV', None),
                              (f'/api/events/{event}/results.json/extra', None),
                              (f'/api/events/{event}/results.json', {})):
            status, _, body = self.request(path, payload)
            self.assertEqual(status, 404, body)
        self.assertEqual(self.api(f'/api/events/{event}')['phase'], 'finished')

    def test_empty_finished_event_is_downloadable(self):
        event = self.create()
        self.finish(event)
        document = json.loads(self.download(event))
        self.assertEqual(document['participants'], 0)
        self.assertEqual(document['leaderboard'], [])
        rows = list(csv.reader(io.StringIO(self.download(event, 'csv').decode('utf-8-sig'))))
        self.assertEqual(len(rows), 1)
        self.assertIn('display_name', rows[0])

    def test_names_round_trip_and_cannot_change_download_filename(self):
        title, name = 'Round "café"\nOther title', 'Zoë, "雨"\nsecond line'
        event = self.create(title=title, room='=1+1')
        self.player(event, name, 0)
        self.finish(event)
        document = json.loads(self.download(event))
        self.assertEqual(document['event']['title'], title)
        self.assertEqual(document['leaderboard'][0]['name'], name)
        rows = list(csv.DictReader(io.StringIO(self.download(event, 'csv').decode('utf-8-sig'))))
        self.assertEqual(rows[0]['display_name'], name)
        self.assertEqual(rows[0]['room'], "'=1+1")

    def test_member_query_does_not_add_references_or_answers(self):
        event = self.create()
        reference = self.player(event, 'Player', 0)
        self.finish(event)
        expected = self.download(event)
        status, _, body = self.request(f'/api/events/{event}/results.json?member={reference}')
        self.assertEqual(status, 200)
        self.assertEqual(body, expected)
        self.assertNotIn(reference.encode(), body)

    def test_finished_downloads_survive_native_server_restart(self):
        event = self.create()
        reference = self.player(event, 'Persistent player', 0)
        self.finish(event)
        expected = {format: self.download(event, format) for format in ('csv', 'json')}
        self.stop_server()
        self.start_server()
        for format, data in expected.items():
            self.assertEqual(self.download(event, format), data)
        replay = self.api(f'/api/events/{event}/answers',
                          {'member_id': reference, 'question': 0, 'choice': 0})
        self.assertTrue(replay['replayed'])
        self.assertEqual(self.download(event), expected['json'])

    def test_downloads_do_not_mix_events(self):
        one, two = self.create(title='One'), self.create(title='Two')
        self.player(one, 'One participant', 0)
        self.player(two, 'Two participant', 1)
        self.finish(one)
        self.finish(two)
        self.assertNotIn(b'Two participant', self.download(one))
        self.assertNotIn(b'One participant', self.download(two))

    def test_existing_home_health_and_listing_do_not_become_attachments(self):
        event = self.create()
        for path in ('/', '/health', '/api/events', f'/api/events/{event}'):
            status, headers, body = self.request(path)
            self.assertEqual(status, 200, body)
            self.assertNotIn('Content-Disposition', headers)

    @unittest.skipUnless(NODE, 'Node.js required for explicit DOM-fixture acceptance')
    def test_actual_render_has_no_download_links_before_finish(self):
        now = time.time()
        for event in (self.create(), self.create(opens=now+600, ends=now+3600)):
            self.assertEqual(self.render_links(self.api(f'/api/events/{event}')), [])

    @unittest.skipUnless(NODE, 'Node.js required for explicit DOM-fixture acceptance')
    def test_actual_render_links_fetch_real_downloads_after_finish(self):
        event = self.create()
        reference = self.player(event, 'Rendered player', 0)
        self.finish(event)
        state = self.api(f'/api/events/{event}?member={reference}')
        links = self.render_links(state)
        self.assertEqual(len(links), 2)
        for link, format in zip(links, ('csv', 'json')):
            self.assertEqual(link, {'text': f'Download {format.upper()} results',
                'href': f'/api/events/{event}/results.{format}', 'download': f'lantern-results.{format}'})
            self.assertNotIn(reference, link['href'])
            status, _, body = self.request(link['href'])
            self.assertEqual(status, 200)
            self.assertEqual(body, self.download(event, format))

    @unittest.skipUnless(NODE, 'Node.js required for explicit DOM-fixture acceptance')
    def test_actual_render_offers_downloads_for_empty_finished_event(self):
        event = self.create()
        self.finish(event)
        self.assertEqual(len(self.render_links(self.api(f'/api/events/{event}'))), 2)

    @unittest.skipUnless(NODE, 'Node.js required for explicit DOM-fixture acceptance')
    def test_actual_render_encodes_the_event_reference_in_download_links(self):
        event = self.create()
        self.finish(event)
        state = self.api(f'/api/events/{event}')
        state['id'] = 'example /?&"'
        links = self.render_links(state)
        self.assertEqual([link['href'] for link in links],
            ['/api/events/example%20%2F%3F%26%22/results.'+format for format in ('csv', 'json')])


if __name__ == '__main__':
    unittest.main(verbosity=2)
