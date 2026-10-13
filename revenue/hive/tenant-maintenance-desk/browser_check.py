"""Actual Chromium workflow checks, separate from the dependency-free unit suite.

Requires Playwright and Chromium; does not substitute HTTP-only checks or mocks.
Set CHROMIUM_PATH to use a system browser and SHOT_DIR to retain screenshots.
BROWSER_HTTP_BRIDGE=1 exercises the DOM offline with fetch responses from the
real loopback HTTP server. It does not validate direct browser network transport.
No browser security settings are changed.
"""
from __future__ import annotations
import base64
import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from desk import Store
from server import make_server

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aVqkAAAAASUVORK5CYII=')


class BrowserChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        launch = {'headless': True}
        if os.environ.get('CHROMIUM_PATH'):
            launch['executable_path'] = os.environ['CHROMIUM_PATH']
        cls.browser = cls.playwright.chromium.launch(**launch)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'browser.sqlite')
        self.server = make_server(self.store, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.context = self.browser.new_context(viewport={'width': self.width, 'height': 1000}, timezone_id='America/Chicago')
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.bridged = os.environ.get('BROWSER_HTTP_BRIDGE') == '1'
        if self.bridged:
            self.page.expose_function('__desk_http', self.bridge_http)

    def bridge_http(self, path, method='GET', body=None):
        # Real application HTTP, not fabricated fixtures or substituted business logic.
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        conn.request(method, path, body=body.encode('utf-8') if isinstance(body, str) else body,
                     headers={'Content-Type': 'application/json'})
        response = conn.getresponse()
        result = {'status': response.status, 'headers': dict(response.getheaders()),
                  'body': base64.b64encode(response.read()).decode()}
        conn.close()
        return result

    def open_page(self, fragment=''):
        if not self.bridged:
            self.page.goto(self.url + '/' + fragment)
            return
        self.page.goto('about:blank')
        html = (Path(__file__).parent / 'index.html').read_text()
        html = html.replace('<script src="/app.js" defer></script>', '')
        self.page.set_content(html)
        self.page.evaluate("""() => {
          window.fetch = async (path, options={}) => {
            const result = await window.__desk_http(path, options.method || 'GET', options.body || null);
            const bytes = Uint8Array.from(atob(result.body), c => c.charCodeAt(0));
            return new Response(bytes, {status: result.status, headers: result.headers});
          };
          if (!crypto.randomUUID) crypto.randomUUID = () => {
            const b = crypto.getRandomValues(new Uint8Array(16));
            b[6] = (b[6] & 15) | 64; b[8] = (b[8] & 63) | 128;
            return Array.from(b, v => v.toString(16).padStart(2, '0')).join('');
          };
        }""")
        if fragment:
            self.page.evaluate('(value) => { location.hash = value; }', fragment)
        self.page.add_script_tag(path=str(Path(__file__).parent / 'app.js'))

    def reload_page(self):
        if self.bridged:
            self.open_page('#' + self.page.url.split('#', 1)[1] if '#' in self.page.url else '')
        else:
            self.page.reload()

    def tearDown(self):
        self.context.close()
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.temp.cleanup()
        self.assertEqual(self.errors, [], 'No unhandled browser JavaScript errors')

    width = 1280

    def screenshot(self, name):
        if os.environ.get('SHOT_DIR'):
            path = Path(os.environ['SHOT_DIR']); path.mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(path / f'{name}-{self.width}.png'), full_page=True)

    def no_horizontal_overflow(self):
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))

    def workflow(self):
        page = self.page
        self.open_page()
        page.get_by_role('button', name='Properties & vendors', exact=True).click()
        page.get_by_label('Property name', exact=True).fill('DEMO · Maple Court')
        page.get_by_label('Property FAQ / contact instructions', exact=True).fill('Fictional property. Repairs are scheduled through this desk.')
        page.get_by_role('button', name='Add property', exact=True).click()
        expect(page.locator('#message')).to_have_text('Property added.')
        for name, trade in [('DEMO · Northstar Repairs', 'General'), ('DEMO · Harbor Plumbing', 'Plumbing')]:
            page.get_by_label('Vendor name', exact=True).fill(name)
            page.get_by_label('Trade / specialty', exact=True).fill(trade)
            page.get_by_role('button', name='Add vendor', exact=True).click()
            expect(page.locator('#vendor-list')).to_contain_text(name)
        page.get_by_role('button', name='Maintenance queue', exact=True).click()
        page.get_by_role('button', name='+ New request', exact=True).click()
        page.locator('#intake-property').select_option(label='DEMO · Maple Court')
        page.get_by_label('Unit / location', exact=True).fill('DEMO 2B')
        page.get_by_label('Priority', exact=True).select_option('urgent')
        page.get_by_label('What is happening?', exact=True).fill('Kitchen tap keeps dripping after closing.')
        page.get_by_label('Photos (optional)', exact=True).set_input_files({'name': 'tap.png', 'mimeType': 'image/png', 'buffer': PNG})
        page.get_by_role('button', name='Create request', exact=True).click()
        expect(page.locator('#detail')).to_contain_text('Kitchen tap keeps dripping after closing.')
        expect(page.locator('#open-count')).to_have_text('1')
        photo_link = page.locator('#detail').get_by_role('link', name='tap.png', exact=True)
        if self.bridged:
            # Browser link rendering + real HTTP bytes; direct download transport is not claimed.
            response = self.bridge_http(photo_link.get_attribute('href'))
            self.assertEqual(base64.b64decode(response['body']), PNG)
        else:
            with page.expect_download() as download:
                photo_link.click()
            self.assertEqual(Path(download.value.path()).read_bytes(), PNG)
        page.get_by_label('Available vendor', exact=True).select_option(label='DEMO · Northstar Repairs · General')
        page.get_by_label('Start (your browser’s local time)', exact=True).fill('2026-10-01T09:00')
        page.get_by_label('End (your browser’s local time)', exact=True).fill('2026-10-01T10:00')
        page.get_by_role('button', name='Save appointment', exact=True).click()
        expect(page.locator('#detail .appointment')).to_contain_text('DEMO · Northstar Repairs')
        expect(page.locator('#scheduled-count')).to_have_text('1')
        self.no_horizontal_overflow(); self.screenshot('queue-scheduled')
        page.get_by_role('button', name='Properties & vendors', exact=True).click()
        northstar = page.locator('.vendor').filter(has_text='DEMO · Northstar Repairs')
        northstar.get_by_role('button', name='Mark unavailable', exact=True).click()
        expect(northstar.get_by_role('button', name='Mark available', exact=True)).to_be_visible()
        page.get_by_role('button', name='Tenant status', exact=True).click()
        expect(page.locator('#tenant-detail')).to_contain_text('A replacement appointment is needed.')
        expect(page.locator('#tenant-detail .appointment')).to_have_count(0)
        self.screenshot('tenant-replacement-needed')
        page.get_by_role('button', name='Maintenance queue', exact=True).click()
        expect(page.locator('#reschedule-count')).to_have_text('1')
        page.get_by_label('Available vendor', exact=True).select_option(label='DEMO · Harbor Plumbing · Plumbing')
        page.get_by_label('Start (your browser’s local time)', exact=True).fill('2026-10-01T11:00')
        page.get_by_label('End (your browser’s local time)', exact=True).fill('2026-10-01T12:00')
        page.get_by_role('button', name='Save appointment', exact=True).click()
        expect(page.locator('#detail .appointment')).to_contain_text('DEMO · Harbor Plumbing')
        page.get_by_role('button', name='Open tenant status', exact=True).click()
        expect(page.locator('#tenant-detail .appointment')).to_contain_text('DEMO · Harbor Plumbing')
        self.assertIn('view=tenant', page.url)
        self.reload_page()
        expect(page.locator('#tenant-detail .appointment')).to_contain_text('DEMO · Harbor Plumbing')
        expect(page.locator('#tenant-faq')).to_contain_text('Fictional property.')
        page.get_by_role('button', name='Maintenance queue', exact=True).click()
        page.get_by_label('What was resolved?', exact=True).fill('Tap washer replaced. No dripping after repair.')
        page.get_by_role('button', name='Close request', exact=True).click()
        expect(page.locator('#detail')).to_contain_text('Tap washer replaced. No dripping after repair.')
        page.get_by_role('button', name='Open tenant status', exact=True).click()
        expect(page.locator('#tenant-detail .badge').first).to_have_text('Closed')
        expect(page.locator('#tenant-detail .appointment')).to_have_count(0)
        self.no_horizontal_overflow(); self.screenshot('tenant-closed')
        self.reload_page()
        expect(page.locator('#tenant-detail')).to_contain_text('Tap washer replaced. No dripping after repair.')
        saved = self.store.state()['requests'][0]
        self.assertEqual(saved['status'], 'closed')
        self.assertEqual(len(saved['appointments']), 2)
        self.assertEqual(saved['appointments'][1]['start'], '2026-10-01T16:00:00.000000+00:00')
        self.assertEqual(len(saved['events']), 5)

    def test_full_customer_workflow(self):
        self.workflow()

    def test_render_text_not_markup(self):
        prop = self.store.command({'type': 'property', 'name': 'Text-only court', 'faq': '<b>Keep literal FAQ text</b>'})['id']
        payload = '<img src=x onerror="window.injected=true">'
        request = self.store.command({'type': 'request', 'property_id': prop, 'unit': 'A', 'description': payload})
        self.open_page('#view=tenant&request=' + request['id'])
        expect(self.page.locator('#tenant-detail')).to_contain_text(payload)
        self.assertIsNone(self.page.evaluate('window.injected'))
        self.assertEqual(self.page.locator('#tenant-detail img').count(), 0)
        expect(self.page.locator('#tenant-faq')).to_have_text('<b>Keep literal FAQ text</b>')


class MobileWorkflow(BrowserChecks):
    width = 390

    def test_full_customer_workflow(self):
        self.workflow()


if __name__ == '__main__':
    unittest.main()
