"""Optional offline DOM tests against the real compiler, not browser HTTP E2E.

A transport adapter replaces fetch in an about:blank Chromium page. Export Blob
bytes are inspected before navigation, rather than claiming a native download.
No external requests are made. Playwright is only imported when run explicitly.
"""
import base64
import io
import json
import os
from pathlib import Path
import zipfile

import newsletter_workflow as nw

ROOT = Path(__file__).resolve().parent


def transport(route, options=None):
    """Exercise production parsing/compilation without browser networking."""
    try:
        if route == '/example.json':
            content = (ROOT / 'example.json').read_bytes()
        else:
            workspace = nw.load_json((options or {}).get('body', ''))
            if route == '/validate':
                nw.validate(workspace)
                content = nw._canonical(workspace)
            elif route == '/build':
                content = nw.build_zip(workspace)
            else:
                raise nw.InputError('Unknown offline test route')
        return {'status': 200, 'data': base64.b64encode(content).decode()}
    except nw.InputError as exc:
        content = json.dumps({'error': str(exc)}).encode()
        return {'status': 400, 'data': base64.b64encode(content).decode()}


def install_adapter(page):
    page.expose_function('__compiler', transport)
    page.evaluate('''() => {
        window.__exports = [];
        const blobs = new Map();
        const originalCreate = URL.createObjectURL.bind(URL);
        URL.createObjectURL = blob => {
            const url = originalCreate(blob); blobs.set(url, blob); return url;
        };
        window.fetch = async (route, options) => {
            const result = await window.__compiler(route, options || {});
            const bytes = Uint8Array.from(atob(result.data), c => c.charCodeAt(0));
            return new Response(bytes, {status: result.status});
        };
        window.__capture = () => document.addEventListener('click', event => {
            const link = event.target.closest('a[download]');
            if (link) {
                event.preventDefault();
                window.__exports.push({name:link.download, blob:blobs.get(link.href)});
            }
        }, true);
    }''')


def last_export(page):
    result = page.evaluate('''async () => {
        const item = window.__exports[window.__exports.length - 1];
        const bytes = new Uint8Array(await item.blob.arrayBuffer());
        let binary = ''; for (const byte of bytes) binary += String.fromCharCode(byte);
        return {name:item.name, data:btoa(binary)};
    }''')
    return result['name'], base64.b64decode(result['data'])


def run():
    from playwright.sync_api import sync_playwright, expect
    passed = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=os.environ.get('CHROMIUM_EXECUTABLE'))
        try:
            page = browser.new_page(viewport={'width': 1280, 'height': 1000})
            page.set_default_timeout(5000)
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            install_adapter(page)
            page.set_content((ROOT / 'workshop.html').read_text(), wait_until='domcontentloaded')
            page.evaluate('window.__capture()')
            expect(page.locator('#subject')).to_have_value('A repair notebook, an open bench, and a useful habit')
            expect(page.locator('.section')).to_have_count(3)
            expect(page.locator('#recipients li')).to_have_count(5)
            passed.append('starter populates real DOM sections and preferences')

            page.locator('#subject').fill('Offline browser edition')
            page.locator('#build').click()
            page.wait_for_function('window.__exports.length === 1')
            filename, payload = last_export(page)
            assert filename == 'edition-01.zip'
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                assert 'Offline browser edition' in archive.read('preview.html').decode()
                assert json.loads(archive.read('manifest.json'))['eligible'] == 2
            passed.append('form events produce real compiler ZIP Blob with two unsent drafts')

            page.locator('#advanced').evaluate('(element) => {element.open = true}')
            workspace = json.loads(page.locator('#raw').input_value())
            workspace['subscribers'][0]['status'] = 'unsubscribed'
            page.locator('#raw').fill(json.dumps(workspace))
            expect(page.locator('#subject')).to_be_disabled()
            page.locator('#apply').click()
            expect(page.locator('#status')).to_contain_text('JSON applied')
            expect(page.locator('#subject')).to_be_enabled()
            page.locator('#build').click()
            page.wait_for_function('window.__exports.length === 2')
            with zipfile.ZipFile(io.BytesIO(last_export(page)[1])) as archive:
                assert json.loads(archive.read('manifest.json'))['eligible'] == 1
            passed.append('full-JSON preference change excludes Alex in rebuilt Blob')

            invalid = json.dumps(workspace)[:-1] + ',"schema_version":1}'
            page.locator('#raw').fill(invalid)
            page.locator('#apply').click()
            expect(page.locator('#status')).to_contain_text('Duplicate JSON key')
            assert page.locator('#raw').input_value() == invalid
            page.locator('#save').click()
            page.wait_for_function('window.__exports.length === 3')
            assert last_export(page) == ('workspace.json', invalid.encode())
            passed.append('duplicate JSON receives real diagnostic and remains exportable unchanged')

            page.locator('#raw').fill(json.dumps(workspace))
            page.locator('#apply').click()
            expect(page.locator('#status')).to_contain_text('JSON applied')
            quote = page.get_by_role('textbox', name='Exact source excerpt', exact=True).first
            original = quote.input_value()
            quote.fill('Unsupported source excerpt.')
            page.locator('#build').click()
            expect(page.locator('#status')).to_contain_text('not an exact excerpt')
            assert page.evaluate('window.__exports.length') == 3
            quote.fill(original)
            passed.append('unsupported excerpt prevents a new export and shows compiler diagnostic')

            page.locator('#import').set_input_files({'name':'import.json','mimeType':'application/json','buffer':(ROOT/'example.json').read_bytes()})
            expect(page.locator('#status')).to_contain_text('Workspace imported')
            expect(page.locator('#subject')).to_have_value('A repair notebook, an open bench, and a useful habit')
            passed.append('native file-input event imports the actual starter through the validator')

            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            expect(page.locator('#build')).to_be_visible()
            passed.append('390px DOM layout has no horizontal overflow')
            assert not errors, errors
            passed.append('no application pageerror events')
        finally:
            browser.close()
    for item in passed:
        print('PASS:', item)
    print(f'{len(passed)} offline DOM/compiler checks passed; browser HTTP, native downloads and storage persistence not tested.')


if __name__ == '__main__':
    run()
