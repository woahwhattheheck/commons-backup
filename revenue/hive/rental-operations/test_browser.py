"""Chromium UI exercise. Falls back only to a documented real-HTTP test bridge.

Run with an installed Playwright package and Chromium. The bridge changes the
fetch transport, not UI actions, business code or database results. Native
origin/CSP/network behavior is not established when bridge mode is reported.
"""
from __future__ import annotations

import json
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from fleet import Store
from server import make_server

ROOT = Path(__file__).resolve().parent


def main():
    checks = []
    mode = 'native_http'
    navigation_error = None
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / 'browser.sqlite'
        store = Store(path)
        server = make_server(store, 0)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
                context = browser.new_context(viewport={'width':1440,'height':1100}, timezone_id='America/Chicago', accept_downloads=True)
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                try:
                    page.goto(f'http://127.0.0.1:{server.server_port}/', timeout=10000)
                except Exception as exc:
                    if 'ERR_BLOCKED_BY_ADMINISTRATOR' not in str(exc):
                        raise
                    mode = 'embedded_dom_real_http_bridge'
                    navigation_error = 'ERR_BLOCKED_BY_ADMINISTRATOR'
                    def bridge(payload):
                        route, options = payload['path'], payload.get('options') or {}
                        # The fixture can call only this test server, never a remote host.
                        if not route.startswith('/api/') or route.startswith('//'):
                            raise ValueError('Unexpected fixture route')
                        request = urllib.request.Request(f'http://127.0.0.1:{server.server_port}' + route,
                                  data=options.get('body', '').encode() if options.get('method') == 'POST' else None,
                                  headers=options.get('headers') or {}, method=options.get('method','GET'))
                        try:
                            response = urllib.request.urlopen(request, timeout=5)
                        except urllib.error.HTTPError as response:
                            return {'status':response.code, 'body':response.read().decode()}
                        with response:
                            return {'status':response.status, 'body':response.read().decode()}
                    page.close()
                    page = context.new_page()
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.expose_function('fleetlineHTTP', bridge)
                    page.set_content(ROOT.joinpath('index.html').read_text().replace('<script defer src="app.js"></script>',''))
                    page.evaluate('''() => { window.fetch = async (path, options) => {
                        const r = await window.fleetlineHTTP({path, options});
                        return {ok:r.status>=200 && r.status<300,status:r.status,json:async()=>JSON.parse(r.body)};
                    }; }''')
                    page.add_script_tag(content=ROOT.joinpath('app.js').read_text())
                expect(page.locator('#assets')).to_contain_text('Add your first asset')
                checks.append('empty workspace rendered')
                page.locator('#asset-name').fill('Example compact lift')
                page.locator('#asset-rate').fill('75.25')
                page.locator('#asset-notes').fill('Synthetic training asset')
                page.locator('#asset-form button[type=submit]').click()
                expect(page.locator('#assets')).to_contain_text('Example compact lift')
                checks.append('asset create through UI and real HTTP')
                page.locator('#reservation-start').fill('2026-09-10T09:00')
                page.locator('#reservation-end').fill('2026-09-11T09:00')
                page.locator('#reservation-customer').fill('Example & Company <sample>')
                page.locator('#reservation-contact').fill('example@example.invalid')
                page.locator('#check-availability').click()
                expect(page.locator('#availability')).to_contain_text('available · $75.25')
                checks.append('availability and exact USD quote rendered')
                page.locator('#reservation-form button[type=submit]').click()
                expect(page.locator('#schedule')).to_contain_text('Example & Company <sample>')
                expect(page.locator('#schedule')).to_contain_text('$75.25')
                assert page.locator('#schedule sample').count() == 0
                checks.append('booking save and literal imported text')
                page.locator('#reservation-start').fill('2026-09-10T09:00')
                page.locator('#reservation-end').fill('2026-09-11T09:00')
                page.locator('#reservation-customer').fill('Conflicting example')
                page.locator('#reservation-form button[type=submit]').click()
                expect(page.locator('#feedback')).to_contain_text('overlaps a booking')
                assert len(store.state()['reservations']) == 1
                checks.append('overlap rejected in UI without a new record')
                page.locator('#reservation-kind').select_option('maintenance')
                page.locator('#reservation-start').fill('2026-09-11T09:00')
                page.locator('#reservation-end').fill('2026-09-12T09:00')
                page.locator('#reservation-customer').fill('Scheduled service')
                page.locator('#reservation-form button[type=submit]').click()
                expect(page.locator('#schedule')).to_contain_text('Maintenance hold')
                checks.append('adjacent maintenance hold saved')
                page.locator('#reservation-start').fill('2026-09-11T09:00')
                page.locator('#reservation-end').fill('2026-09-12T09:00')
                page.locator('#check-availability').click()
                expect(page.locator('#availability')).to_contain_text('unavailable')
                checks.append('maintenance removes availability in browser')
                page.get_by_role('button', name='Handover', exact=True).click()
                page.locator('#check-form button[value=complete]').click()
                expect(page.locator('#check-dialog .dialog-error')).to_contain_text('Complete all checklist items')
                checks.append('incomplete handover stays visible and reserved')
                for checkbox in page.locator('#check-items input').all(): checkbox.check()
                page.locator('#check-notes').fill('Condition and accessories recorded')
                page.locator('#check-form button[value=complete]').click()
                expect(page.locator('#schedule')).to_contain_text('Handed over')
                page.get_by_role('button', name='Return', exact=True).click()
                for checkbox in page.locator('#check-items input').all(): checkbox.check()
                page.locator('#check-notes').fill('Returned; no follow-up')
                page.locator('#check-form button[value=complete]').click()
                expect(page.locator('#schedule')).to_contain_text('Returned')
                checks.append('complete handover and return persist')
                page.get_by_role('button', name='Message draft', exact=True).click()
                expect(page.locator('#message-dialog')).to_be_visible()
                assert 'No payment is recorded' in page.locator('#message-body').input_value()
                assert 'returned' in page.locator('#message-body').input_value()
                page.locator('#message-close').click()
                checks.append('current unsent customer message draft')
                page.get_by_role('button', name='Edit rate & details', exact=True).click()
                page.locator('#asset-rate').fill('100.00')
                page.locator('#asset-form button[type=submit]').click()
                expect(page.locator('#assets')).to_contain_text('$100.00')
                expect(page.locator('#schedule')).to_contain_text('$75.25')
                checks.append('new asset rate does not rewrite prior quote')
                page.locator('#schedule-date').fill('2026-09-11')
                expect(page.locator('#schedule')).to_contain_text('Scheduled service')
                page.locator('#schedule-clear').click()
                checks.append('date-filtered availability schedule')
                with page.expect_download() as info:
                    page.locator('#export-workspace').click()
                exported = json.loads(Path(info.value.path()).read_text())
                assert exported['format'] == 'fleetline-export-v1'
                assert len(exported['tables']['reservations']) == 2
                assert len(exported['tables']['audit']) == 6
                checks.append('browser JSON download contains complete audit and records')
                page.screenshot(path=str(ROOT/'browser-desktop.png'), full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(ROOT/'browser-mobile.png'), full_page=True)
                checks.append('390px layout without body overflow')
                page.emulate_media(media='print')
                expect(page.locator('#reservation-form')).to_be_hidden()
                expect(page.locator('#schedule')).to_be_visible()
                checks.append('print view retains schedule and hides editor controls')
                page.emulate_media(media='screen')
                port = server.server_port
                server.shutdown(); server.server_close(); thread.join()
                store = Store(path)
                server = make_server(store, port)
                thread = threading.Thread(target=server.serve_forever); thread.start()
                page.locator('#refresh').click()
                expect(page.locator('#feedback')).to_contain_text('Schedule refreshed')
                expect(page.locator('#schedule')).to_contain_text('Returned')
                checks.append('HTTP server restart retains customer workflow')
                assert not errors, errors
                checks.append('no uncaught page errors')
                context.close(); browser.close()
        finally:
            server.shutdown(); server.server_close(); thread.join()
    result = {'mode':mode,'navigation_error':navigation_error,'passed':len(checks),'checks':checks,
              'limitations':[] if mode == 'native_http' else ['Native local-page navigation was blocked; fetch used a test bridge to the actual HTTP server. Native origin/CSP/network loading is not established by these DOM checks.']}
    ROOT.joinpath('browser-results.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
