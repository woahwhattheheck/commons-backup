"""Optional actual Chromium acceptance workflow: pip install playwright; playwright install chromium."""
import argparse
import base64
import re
import json
import shutil
import tempfile
import threading
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from server import Desk, Problem, ROOT, handler_for


def exercise(browser, base, width, output, offline_desk=None):
    context = browser.new_context(viewport={'width': width, 'height': 960}, accept_downloads=True)
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    if offline_desk is None:
        page.goto(base)
    else:
        # No navigation or network-policy changes: a test-only in-process adapter.
        # Real HTTP behavior is exercised independently by test_desk.HTTPTests.
        def transport(path, data):
            try:
                if path == '/api/workspaces':
                    result = offline_desk.list_workspaces() if data is None else offline_desk.create_workspace(data)
                elif path == '/api/requests':
                    result = offline_desk.create_request(data)
                elif re.fullmatch(r'/api/workspaces/[a-f0-9]{32}', path):
                    result = offline_desk.snapshot(path.split('/')[3])
                elif path.endswith('/brand'):
                    result = offline_desk.update_brand(path.split('/')[3], data)
                elif path.endswith('/assets'):
                    result = offline_desk.add_brand_asset(path.split('/')[3], data)
                elif path.startswith('/api/assets/'):
                    return {'status': 200, 'bytes': base64.b64encode(offline_desk.asset(path.split('/')[3])['content']).decode(), 'mime': 'application/octet-stream'}
                elif path.endswith('/export'):
                    return {'status': 200, 'bytes': base64.b64encode(offline_desk.export(path.split('/')[3])).decode(), 'mime': 'application/zip'}
                elif path.startswith('/api/requests/'):
                    result = offline_desk.change_request(path.split('/')[3], data)
                else:
                    raise Problem('Unknown offline test route', 404)
                return {'status': 200, 'json': result}
            except Problem as exc:
                return {'status': exc.status, 'json': {'error': str(exc)}}
        page.expose_function('offlineDeskTransport', transport)
        page.evaluate("""() => {
            window.fetch = async (path, opts={}) => {
                const r = await window.offlineDeskTransport(String(path), opts.body ? JSON.parse(opts.body) : null);
                const body = r.bytes ? Uint8Array.from(atob(r.bytes), c=>c.charCodeAt(0)) : JSON.stringify(r.json);
                return new Response(body, {status:r.status, headers:{'Content-Type':r.mime||'application/json'}});
            };
        }""")
        page.set_content((ROOT / 'index.html').read_text())
        page.evaluate("""() => document.addEventListener('click', async e => {
            const link=e.target.closest('a[href^="/api/"]'); if(!link)return;
            e.preventDefault(); const response=await fetch(link.getAttribute('href'));
            const blob=await response.blob(); const a=document.createElement('a');
            a.href=URL.createObjectURL(blob);a.download=link.download||'editable-delivery.zip';
            document.body.append(a);a.click();a.remove();
        })""")
    page.locator('#workspace-name').fill(f'Fictional sample {width}')
    page.get_by_role('button', name='Create workspace').click()
    expect(page.locator('#desk')).to_be_visible()
    for title in ('Brand and landing package', 'Second design request'):
        page.locator('#request-title').fill(title)
        page.locator('#request-brief').fill('An original editable brand and landing page, with preserved revisions.')
        page.get_by_role('button', name='Submit request').click()
        expect(page.locator('article').filter(has=page.get_by_role('heading', name=title, exact=True))).to_be_visible()
    first = page.locator('article').filter(has=page.get_by_role('heading', name='Brand and landing package', exact=True))
    second = page.locator('article').filter(has=page.get_by_role('heading', name='Second design request', exact=True))
    expect(first).to_have_attribute('data-status', 'production')
    expect(second).to_have_attribute('data-status', 'queued')
    first.get_by_role('button', name='Build editable brand + landing sample', exact=True).click()
    expect(first).to_have_attribute('data-status', 'review')
    with page.expect_download() as download_info:
        first.get_by_role('link', name='Download editable ZIP').click()
    first_zip = output / f'first-delivery-{width}.zip'
    download_info.value.save_as(first_zip)
    with zipfile.ZipFile(first_zip) as archive:
        assert 'current/landing.html' in archive.namelist()
        assert len(json.loads(archive.read('manifest.json'))) == 4
    first.get_by_role('button', name='Preview landing page').click()
    expect(page.locator('#preview-dialog')).to_be_visible()
    expect(page.frame_locator('#preview').get_by_role('heading', level=1)).to_have_text('Clear ideas. Thoughtful design. Room to grow.')
    page.screenshot(path=str(output / f'preview-{width}.png'), full_page=True)
    page.get_by_role('button', name='Close preview').click()
    first.get_by_role('textbox', name='Revision request', exact=True).fill('Please use the revised headline.')
    first.get_by_role('button', name='Request revision', exact=True).click()
    expect(first).to_have_attribute('data-status', 'revision')
    expect(second).to_have_attribute('data-status', 'queued')
    page.locator('#brand-headline').fill('A clearer idea for your next chapter.')
    page.get_by_role('button', name='Save brand direction').click()
    expect(page.locator('#notice')).to_contain_text('Brand direction saved')
    first.get_by_role('button', name='Build editable brand + landing sample', exact=True).click()
    expect(first).to_have_attribute('data-status', 'review')
    with page.expect_download() as download_info:
        first.get_by_role('link', name='Download editable ZIP').click()
    revised_zip = output / f'revised-delivery-{width}.zip'
    download_info.value.save_as(revised_zip)
    with zipfile.ZipFile(revised_zip) as archive:
        assert b'A clearer idea for your next chapter.' in archive.read('current/landing.html')
        assert len(json.loads(archive.read('manifest.json'))) == 8
    first.get_by_role('button', name='Accept & advance queue').click()
    expect(first).to_have_attribute('data-status', 'complete')
    expect(second).to_have_attribute('data-status', 'production')
    if offline_desk is None:
        page.reload()
    else:
        page.get_by_role('button', name='Refresh', exact=True).click()
    expect(first).to_have_attribute('data-status', 'complete')
    expect(second).to_have_attribute('data-status', 'production')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Horizontal overflow'
    page.screenshot(path=str(output / f'queue-{width}.png'), full_page=True)
    assert not errors, errors
    context.close()
    return {'mode': 'offline-in-process-SQLite' if offline_desk else 'HTTP', 'width': width, 'workflow': 'PASS', 'revisions': 2, 'source_files_preserved': 8, 'page_errors': errors, 'horizontal_overflow': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=None)
    parser.add_argument('--offline', action='store_true', help='Test-only in-process transport; no browser network navigation')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        output = Path(args.output or folder)
        output.mkdir(parents=True, exist_ok=True)
        desk = Desk(Path(folder) / 'desk.sqlite3')
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(desk))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True, executable_path=shutil.which('chromium') or None, args=['--no-sandbox'])
                results = [exercise(browser, f'http://127.0.0.1:{server.server_port}', width, output, desk if args.offline else None) for width in (1440, 390)]
                browser.close()
            (output / 'browser-results.json').write_text(json.dumps(results, indent=2))
            print(json.dumps(results, indent=2))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    main()
