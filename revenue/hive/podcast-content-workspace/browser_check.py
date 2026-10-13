#!/usr/bin/env python3
"""Optional real Chromium workflow smoke test. Requires Playwright + Chromium."""
import argparse
import hashlib
import json
import tempfile
import threading
import zipfile
from pathlib import Path

from app import Server, Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--document', type=Path, required=True)
    parser.add_argument('--media', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--browser', help='Optional existing Chromium executable path')
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright
    args.output.mkdir(parents=True, exist_ok=True)
    checks = []
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / 'workspace.sqlite')
        server = Server(('127.0.0.1', 0), store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True, executable_path=args.browser)
                context = browser.new_context(viewport={'width': 1440, 'height': 1050}, accept_downloads=True)
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('dialog', lambda dialog: dialog.accept('Studio browser test') if dialog.type == 'prompt' else dialog.accept())
                page.goto(f'http://127.0.0.1:{server.server_port}')
                page.locator('#newEpisode').click()
                page.locator('#workspace').wait_for(state='visible')
                page.locator('#importFile').set_input_files(str(args.document.resolve()))
                page.wait_for_function("document.querySelector('#status').textContent.startsWith('Transcript imported')")
                assert page.locator('.segment').count() == 6
                checks.append('create episode and import six source segments through browser')
                page.locator('#mediaFile').set_input_files(str(args.media.resolve()))
                page.locator('#uploadMedia').click()
                page.wait_for_function("document.querySelector('#status').textContent.startsWith('Recording saved')")
                page.wait_for_function("document.querySelector('#player').readyState >= 1")
                assert abs(page.locator('#player').evaluate('(player)=>player.duration') - json.loads(args.document.read_text())['duration']) < 0.05
                checks.append('original WAV upload and browser media decoding/duration')
                page.locator('.segment button').first.click()
                page.wait_for_function("!document.querySelector('#player').paused")
                page.locator('#player').evaluate('(player)=>player.pause()')
                checks.append('timestamp navigation starts real media playback')
                page.locator('#generate').click()
                page.wait_for_function("document.querySelector('#status').textContent.startsWith('Source-linked drafts')")
                assert page.locator('#draftTabs button').count() == 7
                assert 'source-media/' in page.locator('#draftText').input_value()
                checks.append('show notes/newsletter/five distinct post editors generated with source links')
                page.get_by_role('button', name='Newsletter', exact=True).click()
                page.locator('#draftText').fill('Original human-edited newsletter for browser regression.')
                page.locator('#saveDrafts').click()
                page.wait_for_function("document.querySelector('#status').textContent === 'Draft edits saved.'")
                page.reload()
                page.locator('.episode').first.click()
                page.get_by_role('button', name='Newsletter', exact=True).click()
                assert page.locator('#draftText').input_value() == 'Original human-edited newsletter for browser regression.'
                checks.append('draft editing and persistent reopen through browser')
                page.locator('#title').fill('Revised source title')
                page.locator('#saveDocument').click()
                page.wait_for_function("document.querySelector('#status').textContent === 'Source edits saved.'")
                assert 'STALE SOURCE' in page.locator('#draftNotice').text_content()
                assert page.locator('#draftText').input_value() == 'Original human-edited newsletter for browser regression.'
                checks.append('source edits mark drafts stale without replacing human edits')
                with page.expect_download() as download:
                    page.locator('#export').click()
                target = args.output / 'browser-export.zip'
                download.value.save_as(target)
                with zipfile.ZipFile(target) as packet:
                    assert packet.read('source-media/' + args.media.name) == args.media.read_bytes()
                    assert packet.read('newsletter.md').decode() == 'Original human-edited newsletter for browser regression.'
                    assert len([name for name in packet.namelist() if name.startswith('posts/')]) == 5
                    assert json.loads(packet.read('source-map.json'))['drafts_stale']
                checks.append('UI ZIP download preserves exact original media, five posts and saved edits')
                page.evaluate('window.scrollTo(0,0)')
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                page.screenshot(path=str(args.output / 'desktop.png'), full_page=True)
                page.set_viewport_size({'width': 390, 'height': 844})
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                page.screenshot(path=str(args.output / 'mobile.png'), full_page=True)
                checks.append('desktop1440 and mobile390 layouts have no horizontal overflow')
                page.locator('#deleteEpisode').click()
                page.wait_for_function("document.querySelector('#status').textContent.startsWith('Episode deleted')")
                assert not store.list()
                checks.append('browser deletion removes episode from persistent application store')
                assert not errors, errors
                checks.append('zero browser JavaScript exceptions')
                context.close(); browser.close()
        finally:
            server.shutdown(); server.server_close(); thread.join()
    result = {'passed': len(checks), 'checks': checks,
              'media_sha256': hashlib.sha256(args.media.read_bytes()).hexdigest()}
    (args.output / 'browser-results.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
