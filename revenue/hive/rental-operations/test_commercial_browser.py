"""Focused browser regression for Fleetline commercial quote terms."""
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


def main():
    with tempfile.TemporaryDirectory() as temporary:
        store = Store(Path(temporary) / 'fleet.sqlite')
        server = make_server(store, 0)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path='/usr/bin/chromium', headless=True,
                                                     args=['--no-sandbox'])
                context = browser.new_context(viewport={'width': 1200, 'height': 900},
                                              timezone_id='America/Chicago', accept_downloads=True)
                page = context.new_page()
                mode = 'native_http'
                try:
                    page.goto(f'http://127.0.0.1:{server.server_port}/', timeout=10000)
                except Exception as exc:
                    if 'ERR_BLOCKED_BY_ADMINISTRATOR' not in str(exc):
                        raise
                    mode = 'embedded_dom_real_http_bridge'
                    def bridge(payload):
                        route, options = payload['path'], payload.get('options') or {}
                        if not route.startswith('/api/') or route.startswith('//'):
                            raise ValueError('Unexpected fixture route')
                        request = urllib.request.Request(
                            f'http://127.0.0.1:{server.server_port}' + route,
                            data=options.get('body', '').encode() if options.get('method') == 'POST' else None,
                            headers=options.get('headers') or {}, method=options.get('method', 'GET'))
                        try:
                            response = urllib.request.urlopen(request, timeout=5)
                        except urllib.error.HTTPError as response:
                            return {'status': response.code, 'body': response.read().decode()}
                        with response:
                            return {'status': response.status, 'body': response.read().decode()}
                    page.close()
                    page = context.new_page()
                    page.expose_function('fleetlineHTTP', bridge)
                    root = Path(__file__).resolve().parent
                    page.set_content(root.joinpath('index.html').read_text().replace(
                        '<script defer src="app.js"></script>', ''))
                    page.evaluate("""() => { window.fetch = async (path, options) => {
                        const r = await window.fleetlineHTTP({path, options});
                        return {ok:r.status>=200 && r.status<300,status:r.status,json:async()=>JSON.parse(r.body)};
                    }; }""")
                    page.add_script_tag(content=root.joinpath('app.js').read_text())
                expect(page.locator('#assets')).to_contain_text('Add your first asset')

                page.locator('#asset-name').fill('Example compact lift')
                page.locator('#asset-rate').fill('75.25')
                page.locator('#asset-booking-fee').fill('10.00')
                page.locator('#asset-security-deposit').fill('200.00')
                page.locator('#asset-form button[type=submit]').click()
                expect(page.locator('#assets')).to_contain_text('Booking fee $10.00')
                expect(page.locator('#assets')).to_contain_text('refundable deposit $200.00')

                page.locator('#reservation-start').fill('2026-09-10T09:00')
                page.locator('#reservation-end').fill('2026-09-11T09:00')
                page.locator('#reservation-customer').fill('Example customer')
                page.locator('#reservation-contact').fill('example@example.invalid')
                page.locator('#check-availability').click()
                expect(page.locator('#availability')).to_contain_text('$285.25 due')
                expect(page.locator('#availability')).to_contain_text('rental $75.25 + fee $10.00 + refundable deposit $200.00')

                page.locator('#reservation-form button[type=submit]').click()
                expect(page.locator('#schedule')).to_contain_text('$285.25 due')
                expect(page.locator('#schedule')).to_contain_text('pricing snapshot')

                page.get_by_role('button', name='Edit rate & details', exact=True).click()
                page.locator('#asset-rate').fill('90.00')
                page.locator('#asset-booking-fee').fill('20.00')
                page.locator('#asset-security-deposit').fill('300.00')
                page.locator('#asset-form button[type=submit]').click()
                expect(page.locator('#assets')).to_contain_text('Booking fee $20.00')
                expect(page.locator('#schedule')).to_contain_text('$285.25 due')

                page.get_by_role('button', name='Message draft', exact=True).click()
                message = page.locator('#message-body').input_value()
                assert 'Rental subtotal: USD 75.25' in message
                assert 'Booking fee: USD 10.00' in message
                assert 'Refundable security deposit: USD 200.00' in message
                assert 'Amount due before taxes/delivery: USD 285.25' in message
                assert 'No payment is recorded' in message
                page.locator('#message-close').click()

                with page.expect_download() as info:
                    page.locator('#export-workspace').click()
                exported = json.loads(Path(info.value.path()).read_text())
                assert exported['format'] == 'fleetline-export-v1'
                reservation = exported['tables']['reservations'][0]
                assert reservation['total_cents'] == 7525
                assert reservation['booking_fee_cents'] == 1000
                assert reservation['security_deposit_cents'] == 20000
                assert reservation['amount_due_cents'] == 28525

                assert not page.locator('body').evaluate('(body) => body.scrollWidth > document.documentElement.clientWidth')
                context.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    print(json.dumps({'passed': 12, 'mode': mode, 'scope': 'commercial quote terms'}))


if __name__ == '__main__':
    main()
