"""Optional end-to-end checks: python browser_smoke.py (requires Playwright/Chromium)."""
import json
import tempfile
import shutil
import os
from pathlib import Path
from playwright.sync_api import sync_playwright
from workflow import Server, Store
from test_workflow import running


def main():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(str(Path(tmp) / 'browser.sqlite3'))
        with running(Server(('127.0.0.1', 0), store)) as url, sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=shutil.which('chromium'), args=['--no-sandbox'])
            artifacts = Path(os.environ.get('BROWSER_ARTIFACT_DIR', 'browser-artifacts'))
            artifacts.mkdir(parents=True, exist_ok=True)
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            problems = []
            page.on('pageerror', lambda error: problems.append(str(error)))
            page.goto(url)
            page.wait_for_function("document.querySelector('#intake [name=id]').value.startsWith('clean-')")
            for field, value in {'id': 'browser:cleaning:001', 'name': 'Browser Example', 'email': 'browser@example.com', 'address': 'Example service address', 'notes': 'Synthetic browser workflow'}.items():
                page.locator(f'#intake [name={field}]').fill(value)
            page.get_by_role('button', name='Create customer & job').click()
            page.get_by_text('Customer and job recorded. Notification is queued.', exact=True).wait_for()
            page.get_by_role('button', name='Create customer & job').click()
            page.get_by_text('Existing job returned. No duplicate was created.', exact=True).wait_for()
            assert len(store.snapshot()['jobs']) == 1
            page.get_by_role('button', name='Deliver next notification').click()
            page.get_by_text('Delivery: delivered', exact=True).wait_for()
            page.locator('.tasks input').nth(0).check()
            page.wait_for_function("document.querySelector('.badge').textContent==='in progress'")
            page.reload()
            page.locator('.tasks input').nth(0).wait_for()
            assert page.locator('.tasks input').nth(0).is_checked()
            config = store.settings()['mapping']
            config['name'] = 'customer_name'
            page.locator('#config [name=mapping]').fill(json.dumps(config))
            page.get_by_role('button', name='Save settings').click()
            page.get_by_text('Settings saved. Pending deliveries use the current receiver.', exact=True).wait_for()
            page.locator('#intake [name=id]').fill('browser:cleaning:002')
            page.locator('#intake [name=name]').fill('<b>Literal customer name</b>')
            page.locator('#intake [name=email]').fill('second@example.com')
            page.locator('#intake [name=address]').fill('Another example service address')
            page.get_by_role('button', name='Create customer & job').click()
            page.get_by_text('Customer and job recorded. Notification is queued.', exact=True).wait_for()
            page.get_by_role('heading', name='<b>Literal customer name</b> new', exact=True).wait_for()
            assert page.locator('#jobs h3 b').count() == 0
            with page.expect_download() as download:
                page.get_by_role('button', name='Export workspace JSON').click()
            exported = json.loads(Path(download.value.path()).read_text())
            assert len(exported['customers']) == 2 and len(exported['jobs']) == 2
            source = {'id': 'browser:import:003', 'payload': {'customer_name': 'Imported Example', 'email': 'imported@example.com', 'address': 'Imported example service address', 'service': 'Move-out cleaning'}}
            page.locator('#import').set_input_files({'name': 'intake.json', 'mimeType': 'application/json', 'buffer': json.dumps(source).encode()})
            page.get_by_text('Imported customer and job.', exact=True).wait_for()
            assert len(store.snapshot()['jobs']) == 3
            page.screenshot(path=str(artifacts / 'desktop.png'), full_page=True)
            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(artifacts / 'mobile.png'), full_page=True)
            assert not problems, problems
            print(json.dumps({'browser': 'Chromium', 'checks': ['form-create', 'duplicate-submit', 'notification', 'task-persistence', 'field-mapping', 'text-rendering', 'export', 'file-import', 'mobile-layout'], 'jobs': 3, 'page_errors': problems}))
            browser.close()


if __name__ == '__main__':
    main()
