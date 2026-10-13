#!/usr/bin/env python3
"""Optional Chromium UI check. Declares its HTTP-binding test transport explicitly.

Requires Playwright, Chromium, Pillow and local English Tesseract. The application
itself requires only Python; text/manual-transcription mode does not need OCR.
This harness does not establish native browser networking, clipboard or downloads.
"""
import argparse
import base64
import io
import json
import shutil
import tempfile
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

import app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    args = parser.parse_args()
    artifacts = args.artifacts or Path(tempfile.mkdtemp(prefix='conversation-browser-'))
    artifacts.mkdir(parents=True, exist_ok=True)
    if not shutil.which('tesseract'):
        raise SystemExit('This optional screenshot check requires Tesseract with English data.')
    checks = []
    def check(condition, description):
        if not condition:
            raise AssertionError(description)
        checks.append(description)

    image = Image.new('RGB', (1200, 160), 'white')
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype('DejaVuSans.ttf', 46)
    except OSError:
        font = ImageFont.load_default(size=46)
    draw.text((30, 40), 'Alex: Easy walk or longer hike?', fill='black', font=font)
    buffer = io.BytesIO(); image.save(buffer, format='PNG'); png = buffer.getvalue()

    with tempfile.TemporaryDirectory() as tmp:
        store = app.Store(Path(tmp) / 'smoke.sqlite3')
        httpd = app.server(store, port=0)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True); thread.start()
        base = f'http://127.0.0.1:{httpd.server_port}'
        def request(path, method='GET', body=None):
            payload = None if body is None else body.encode('utf-8')
            req = Request(base + path, data=payload, method=method, headers={'Content-Type': 'application/json'})
            try:
                response = urlopen(req, timeout=25)
            except HTTPError as exc:
                response = exc
            with response:
                return {'status': response.status, 'body': response.read().decode('utf-8')}
        try:
            with sync_playwright() as playwright:
                options = {'headless': True}
                if shutil.which('chromium'):
                    options['executable_path'] = shutil.which('chromium')
                browser = playwright.chromium.launch(**options)
                page = browser.new_page(viewport={'width': 1440, 'height': 1100})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('dialog', lambda dialog: dialog.accept('ERASE') if dialog.type == 'prompt' else dialog.accept())
                # Offline DOM with the actual JS and a binding to the actual local HTTP
                # server. Browser network transport is deliberately not under test.
                page.expose_function('__deskRequest', request)
                html = (app.HERE / 'index.html').read_text().replace('<script src="desk.js" defer></script>', '')
                page.set_content(html)
                page.evaluate("""() => { window.fetch = async (path, options = {}) => {
                    const result = await window.__deskRequest(String(path), options.method || 'GET', options.body ?? null);
                    return new Response(result.body, {status: result.status, headers: {'Content-Type':'application/json'}});
                }; }""")
                page.add_script_tag(content=(app.HERE / 'desk.js').read_text())
                page.wait_for_function("document.getElementById('status').textContent.startsWith('Workspace ready')")
                page.click('#sample')
                page.wait_for_function("document.getElementById('status').textContent.startsWith('Fictional example')")
                check(len(store.list()) == 1, 'fictional sample saved through real HTTP')
                cid = store.list()[0]['id']
                page.click('#generate'); page.wait_for_selector('.candidate')
                check(page.locator('.candidate').count() == 3, 'three rendered tone options')
                page.get_by_role('button', name='Use direct draft').click()
                chosen = page.input_value('#draft') + ' I can bring water.'
                page.fill('#draft', chosen); page.click('#save')
                page.wait_for_function("document.getElementById('status').textContent === 'Conversation and draft saved.'")
                check(app.Store(store.path).get(cid)['draft'] == chosen, 'edited draft survives SQLite reopen')
                # Hold one real save in the browser to check the in-flight editing boundary.
                page.evaluate(r"""() => {
                    const original = window.fetch;
                    window.fetch = (path, options = {}) => {
                        if (options.method === 'POST' && /^\/api\/conversations\/[^/]+$/.test(String(path))) {
                            return new Promise(resolve => {
                                window.__continueSave = () => { window.fetch = original; resolve(original(path, options)); };
                            });
                        }
                        return original(path, options);
                    };
                }""")
                page.fill('#draft', chosen + ' Low-key is best for me.'); page.click('#save')
                check(not page.locator('#draft').is_editable() and page.locator('#intent').is_disabled(), 'in-flight save holds editable controls')
                page.evaluate('window.__continueSave()')
                page.wait_for_function("document.getElementById('status').textContent === 'Conversation and draft saved.' && !document.getElementById('draft').readOnly")
                check(store.get(cid)['draft'].endswith('Low-key is best for me.'), 'held save persists the captured draft')
                check(page.locator('#draft').is_editable(), 'editing resumes after save completion')
                page.evaluate("Object.defineProperty(navigator, 'clipboard', {configurable:true, value:{writeText:async () => {throw new Error('Synthetic clipboard denial');}}})")
                page.click('#copy')
                page.wait_for_function("document.getElementById('status').textContent.startsWith('Clipboard is unavailable')")
                check(page.evaluate("document.activeElement.id === 'draft'"), 'clipboard-denial fallback focuses the real draft')
                check(page.evaluate("document.getElementById('draft').selectionStart === 0 && document.getElementById('draft').selectionEnd === document.getElementById('draft').value.length"), 'clipboard-denial fallback selects the complete draft')
                page.locator('summary').click()
                page.set_input_files('#image-file', {'name': 'fictional-question.png', 'mimeType': 'image/png', 'buffer': png})
                page.click('#upload')
                page.wait_for_function("document.getElementById('status').textContent.startsWith('Original screenshot saved')")
                record = store.get(cid); iid = record['images'][0]['id']
                check(store.image(cid, iid)['data'] == png, 'original uploaded screenshot bytes preserved')
                # Thumbnail is fixture-rendered because about:blank has no native
                # relative-image transport. This is not a thumbnail-network test.
                page.locator('.image-card img').evaluate('(img, src) => img.src = src', 'data:image/png;base64,' + base64.b64encode(png).decode())
                page.get_by_role('button', name='Transcribe locally').click()
                page.wait_for_selector('#ocr-editor', state='visible', timeout=25000)
                extracted = page.input_value('#ocr-text')
                check('Easy walk' in extracted and 'hike' in extracted, 'one real local Tesseract transcription')
                corrected = 'Alex: Easy walk or a longer hike this weekend?'
                page.fill('#ocr-text', corrected); page.click('#apply-ocr'); page.click('#save')
                page.wait_for_function("document.getElementById('status').textContent === 'Conversation and draft saved.'")
                check(corrected in store.get(cid)['transcript'], 'user-corrected OCR saved, not auto-replaced')
                page.click('#reload')
                page.wait_for_function("document.getElementById('status').textContent === 'Saved version reloaded.'")
                check(corrected in page.input_value('#transcript'), 'saved transcript reloads into browser editor')
                # Stale write keeps the unsaved browser text visible for recovery.
                record = store.get(cid)
                store.update(cid, {'draft': 'Other tab saved this.'}, record['revision'])
                page.fill('#draft', 'My unsaved edit'); page.click('#save')
                page.wait_for_function("document.getElementById('status').textContent.includes('This conversation changed')")
                check(page.input_value('#draft') == 'My unsaved edit', 'conflict preserves unsaved browser text')
                check(store.get(cid)['draft'] == 'Other tab saved this.', 'conflict preserves saved competing revision')
                page.click('#reload')
                page.wait_for_function("document.getElementById('status').textContent === 'Saved version reloaded.'")
                page.select_option('#intent', 'boundary')
                page.fill('#reply', 'I prefer to keep chatting here for now.'); page.fill('#question', '')
                page.click('#generate'); page.wait_for_selector('.candidate')
                check(page.locator('.candidate h3').all_text_contents() == ['Warm', 'Direct', 'Gentle'], 'boundary intent changes framing to gentle')
                page.locator('.image-card img').evaluate('(img, src) => img.src = src', 'data:image/png;base64,' + base64.b64encode(png).decode())
                page.screenshot(path=str(artifacts / 'desktop.png'), full_page=True)
                page.set_viewport_size({'width': 390, 'height': 844})
                check(page.evaluate('document.documentElement.scrollWidth <= innerWidth'), '390px layout has no horizontal overflow')
                page.screenshot(path=str(artifacts / 'mobile.png'), full_page=True)
                export = json.loads(request('/api/export')['body'])
                check(export['conversations'][0]['id'] == cid and len(export['images']) == 1, 'real HTTP export contains saved text and image')
                page.click('#delete')
                page.wait_for_function("document.getElementById('status').textContent.startsWith('Conversation and its screenshots deleted')")
                check(store.list() == [] and store.export()['images'] == [], 'delete removes conversation and screenshot')
                check(all(not page.input_value('#' + key) for key in ['title', 'transcript', 'context', 'reply', 'question', 'draft']), 'delete clears private editor fields')
                page.click('#sample')
                page.wait_for_function("document.getElementById('status').textContent.startsWith('Fictional example')")
                page.click('#erase')
                page.wait_for_function("document.getElementById('status').textContent.startsWith('All saved conversation text')")
                check(store.list() == [], 'whole-workspace erase through browser control')
                check(not errors, 'no JavaScript page errors')
                browser.close()
                report = {'mode': 'offline Chromium DOM + bound real local HTTP; fixture thumbnail',
                          'checks_passed': len(checks), 'checks': checks, 'ocr_text': extracted,
                          'native_browser_network': 'not tested here',
                          'native_clipboard_and_download_completion': 'not tested', 'page_errors': errors}
                (artifacts / 'browser-report.json').write_text(json.dumps(report, indent=2) + '\n')
                print(json.dumps(report, indent=2))
        finally:
            httpd.shutdown(); thread.join(); httpd.server_close()


if __name__ == '__main__':
    main()
