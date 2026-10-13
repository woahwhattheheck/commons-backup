"""Optional real-Chromium acceptance check. Runtime app does not need Playwright."""
import argparse
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
import zipfile

from playwright.sync_api import sync_playwright
import app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chromium', default='/usr/bin/chromium')
    parser.add_argument('--out', default='browser-evidence')
    parser.add_argument('--offline-dom', action='store_true', help='Only render a real-store snapshot; no browser network assertions')
    args = parser.parse_args()
    output = Path(args.out); output.mkdir(parents=True, exist_ok=True)
    if args.offline_dom:
        return offline_dom(args, output)
    with tempfile.TemporaryDirectory() as tmp:
        store = app.Store(Path(tmp) / 'desk.sqlite3')
        server = ThreadingHTTPServer(('127.0.0.1', 0), app.handler(store))
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        base = f'http://127.0.0.1:{server.server_port}'
        checks, errors = [], []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=args.chromium, headless=True, args=['--no-sandbox'])
                context = browser.new_context(viewport={'width': 1440, 'height': 1100}, accept_downloads=True)
                page = context.new_page(); page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base); page.get_by_role('button', name='Load fictional example').click()
                page.wait_for_function("document.querySelectorAll('#segments .section-editor').length === 8")
                page.get_by_role('button', name='Create four-issue pack').click()
                page.locator('#workspace').wait_for(state='visible')
                assert page.locator('#issueTabs button').count() == 4
                checks.append('demo intake produces four issue tabs through real HTTP')
                page.locator('#body').fill('Edited body for the real-browser acceptance workflow.')
                page.get_by_role('button', name='Save revision', exact=True).click()
                page.wait_for_function("document.querySelector('#revision').textContent === 'REVISION 2'")
                assert 'edited' in page.locator('#sourceBadge').inner_text()
                checks.append('body edit saves and source match label changes')
                page.get_by_text('Handoff status', exact=True).click()
                page.select_option('#state', 'ready')
                page.get_by_role('button', name='Record state', exact=True).click()
                page.wait_for_function("document.querySelector('#revision').textContent === 'REVISION 3'")
                checks.append('ready state records without provider action')
                second = context.new_page(); second.goto(base)
                second.locator('#packs button').first.click(); second.locator('#workspace').wait_for(state='visible')
                second.locator('#subject').fill('Unsaved stale-window subject')
                page.locator('#subject').fill('Saved from first browser window')
                page.get_by_role('button', name='Save revision', exact=True).click()
                page.wait_for_function("document.querySelector('#revision').textContent === 'REVISION 4'")
                second.get_by_role('button', name='Save revision', exact=True).click()
                second.wait_for_function("document.querySelector('#alert').textContent.includes('newer revision')")
                assert second.locator('#subject').input_value() == 'Unsaved stale-window subject'
                assert store.list()[0]['issues'][0]['subject'] == 'Saved from first browser window'
                checks.append('stale second window keeps unsaved draft and cannot overwrite saved revision')
                second.close()
                page.get_by_role('button', name='Preview saved email', exact=True).click()
                page.frame_locator('#preview').get_by_role('heading', name='Saved from first browser window').wait_for()
                assert 'Edited body' in page.frame_locator('#preview').locator('body').inner_text()
                checks.append('saved email iframe renders real edited body')
                with page.expect_download() as download_info:
                    page.get_by_role('link', name='Export editable month', exact=True).click()
                download = download_info.value
                download.save_as(output / 'browser-month.zip')
                with zipfile.ZipFile(io.BytesIO((output / 'browser-month.zip').read_bytes())) as archive:
                    manifest = json.loads(archive.read('manifest.json'))
                    assert manifest['version'] == 4 and manifest['email_sent_by_app'] is False
                    assert 'Edited body' in archive.read('issue-1.txt').decode()
                checks.append('browser download contains current editable revision and no-send manifest')
                page.reload(); page.locator('#packs button').first.click()
                page.wait_for_function("document.querySelector('#revision').textContent === 'REVISION 4'")
                assert page.locator('#body').input_value().startswith('Edited body')
                checks.append('browser reload recovers SQLite state')
                page.screenshot(path=str(output / 'desktop.png'), full_page=True)
                page.set_viewport_size({'width': 390, 'height': 844})
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                page.locator('#issueTabs button').nth(3).click()
                assert 'Week 4' in page.locator('#issueTitle').inner_text()
                page.screenshot(path=str(output / 'mobile.png'), full_page=True)
                checks.append('390px layout has no horizontal overflow and week navigation works')
                assert not errors, errors
                browser.close()
        finally:
            server.shutdown(); server.server_close(); worker.join(5)
    result = {'passed': len(checks), 'checks': checks, 'javascript_errors': errors,
              'server': 'real temporary SQLite and loopback HTTP; no service mocks', 'provider_actions': 0}
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))



def offline_dom(args, output):
    """Render without navigation; suitable when managed browser policy blocks URLs."""
    with tempfile.TemporaryDirectory() as tmp:
        store = app.Store(Path(tmp) / 'desk.sqlite3')
        pack = store.create(json.loads((app.ROOT / 'demo.json').read_text()))
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=args.chromium, headless=True, args=['--no-sandbox'])
            page = browser.new_page(viewport={'width': 1440, 'height': 1100})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.set_content((app.ROOT / 'index.html').read_text())
            page.evaluate("p => { current=p; selected=0; showPack(); notice('Offline DOM rendering; real HTTP is tested separately.'); }", pack)
            assert page.locator('#issueTabs button').count() == 4
            assert page.locator('#body').input_value() == pack['issues'][0]['body']
            page.get_by_text('Sources and research notes', exact=True).click()
            assert page.locator('#sources .source').count() == 2
            page.screenshot(path=str(output / 'desktop.png'), full_page=True)
            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.locator('#issueTabs button').nth(3).click()
            assert page.locator('#body').input_value() == pack['issues'][3]['body']
            page.screenshot(path=str(output / 'mobile.png'), full_page=True)
            assert not errors, errors
            browser.close()
    result = {'passed': 4, 'mode': 'offline DOM from a real SQLite pack snapshot',
              'checks': ['four issue tabs and body rendering', 'source notes rendering',
                         '390px layout has no horizontal overflow', 'week-four navigation renders its distinct body'],
              'browser_http_workflow': 'not executed in this mode', 'javascript_errors': errors}
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
