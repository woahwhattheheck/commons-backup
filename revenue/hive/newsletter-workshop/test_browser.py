"""Optional real Chromium exercise. Requires Playwright and its Chromium browser.

Run: python test_browser.py
"""
import io
import json
import os
import tempfile
import threading
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
import newsletter_workflow as nw


def run():
    server = ThreadingHTTPServer(('127.0.0.1', 0), nw.handler_class())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assertions = []
    try:
        with tempfile.TemporaryDirectory() as tmp, sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, executable_path=os.environ.get('CHROMIUM_EXECUTABLE'))
            page = browser.new_page(viewport={'width': 1280, 'height': 1000}, accept_downloads=True)
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            expect(page.locator('#subject')).to_have_value('A repair notebook, an open bench, and a useful habit')
            expect(page.locator('.section')).to_have_count(3)
            expect(page.locator('#recipients li')).to_have_count(5)
            assertions.append('starter renders three editable sections and five preference records')
            page.locator('#subject').fill('My edited workshop issue')
            with page.expect_download() as downloaded:
                page.locator('#build').click()
            data = Path(downloaded.value.path()).read_bytes()
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                assert 'My edited workshop issue' in archive.read('preview.html').decode()
                assert json.loads(archive.read('manifest.json'))['eligible'] == 2
            assertions.append('form edits reach real compiler ZIP with two unsent MIME drafts')
            page.reload()
            expect(page.locator('#subject')).to_have_value('My edited workshop issue')
            assertions.append('applied edits survive browser reload')
            page.locator('#advanced').evaluate('(element) => {element.open=true}')
            workspace = json.loads(page.locator('#raw').input_value())
            workspace['subscribers'][0]['status'] = 'unsubscribed'
            page.locator('#raw').fill(json.dumps(workspace))
            expect(page.locator('#subject')).to_be_disabled()
            page.locator('#apply').click()
            expect(page.locator('#status')).to_contain_text('JSON applied')
            expect(page.locator('#subject')).to_be_enabled()
            with page.expect_download() as downloaded:
                page.locator('#build').click()
            with zipfile.ZipFile(downloaded.value.path()) as archive:
                assert json.loads(archive.read('manifest.json'))['eligible'] == 1
            assertions.append('preference edit removes recipient on actual rebuild')
            invalid = json.dumps(workspace)[:-1] + ',"schema_version":1}'
            page.locator('#raw').fill(invalid)
            page.locator('#apply').click()
            expect(page.locator('#status')).to_contain_text('Duplicate JSON key')
            assert page.locator('#raw').input_value() == invalid
            with page.expect_download() as downloaded:
                page.locator('#save').click()
            assert Path(downloaded.value.path()).read_text() == invalid
            assertions.append('duplicate JSON reaches central validator; invalid edits remain downloadable')
            page.locator('#raw').fill(json.dumps(workspace))
            page.locator('#apply').click()
            expect(page.locator('#status')).to_contain_text('JSON applied')
            quote = page.get_by_role('textbox', name='Exact source excerpt', exact=True).first
            original = quote.input_value()
            quote.fill('A claim that is not in the source.')
            page.locator('#build').click()
            expect(page.locator('#status')).to_contain_text('not an exact excerpt')
            quote.fill(original)
            assertions.append('source-mismatched quote reports actionable compiler error')
            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            expect(page.locator('#build')).to_be_visible()
            assertions.append('390px mobile layout has no horizontal overflow')
            assert not errors, errors
            assertions.append('no browser runtime errors')
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    for item in assertions:
        print('PASS:', item)
    print(f'{len(assertions)} real Chromium workflow checks passed')


if __name__ == '__main__':
    run()
