"""Actual Chromium workflow checks. Requires Playwright and a Chromium binary.
Run: python test_browser.py --chromium /usr/bin/chromium --artifacts /tmp/catering-browser
No external service is contacted; a temporary loopback server serves the app.
"""
import argparse
import json
import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--chromium', default='/usr/bin/chromium')
    parser.add_argument('--artifacts', type=Path, default=Path('/tmp/catering-browser'))
    parser.add_argument('--in-memory', action='store_true', help='Exercise DOM without URL navigation; native storage is not tested.')
    args = parser.parse_args()
    args.artifacts.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parent
    passed = []
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(root))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f'http://127.0.0.1:{server.server_port}'
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.chromium, headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1440, 'height': 1100}, accept_downloads=True)
        errors, network = [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('request', lambda r: network.append(r.url) if r.url.startswith(('http:', 'https:')) and not r.url.startswith(base_url + '/') else None)
        if args.in_memory:
            html = (root / 'index.html').read_text().replace('<script src="catering.js"></script>', '<script>' + (root / 'catering.js').read_text() + '</script>')
            page.set_content(html)
        else:
            page.goto(base_url + '/index.html')
        expect(page.locator('#metric-total')).to_have_text('$785.10')
        expect(page.locator('#kitchen-lines')).to_contain_text('44 roll')
        passed.append('40-person browser quote and production sheet')
        page.screenshot(path=str(args.artifacts / 'desktop.png'), full_page=True)
        guests = page.locator('[data-field=headcount]')
        guests.fill('60'); guests.press('Tab')
        expect(page.locator('#metric-total')).to_have_text('$1096.40')
        expect(page.locator('#metric-deposit')).to_have_text('$328.92')
        expect(page.locator('#kitchen-lines')).to_contain_text('66 roll')
        passed.append('60-person browser recalculation')
        page.locator('#save').click()
        if args.in_memory:
            expect(page.locator('#error')).to_be_visible()
            passed.append('opaque-origin storage error is visible; native persistence NOT TESTED')
        else:
            guests.fill('25'); guests.press('Tab')
            page.locator('#restore').click()
            expect(guests).to_have_value('60')
            expect(page.locator('#metric-total')).to_have_text('$1096.40')
            passed.append('save/restore retains exact revision and amounts')
        with page.expect_download() as download:
            page.locator('#download').click()
        saved = args.artifacts / 'event.json'; download.value.save_as(saved)
        data = json.loads(saved.read_text())
        assert data['event']['headcount'] == '60'
        guests.fill('40'); guests.press('Tab')
        page.locator('#event-file').set_input_files(str(saved))
        expect(guests).to_have_value('60')
        passed.append('downloaded event reopens losslessly')
        with page.expect_download() as download:
            page.locator('#kitchen-csv').click()
        csv_path = args.artifacts / 'kitchen.csv'; download.value.save_as(csv_path)
        assert '66' in csv_path.read_text() and '60' in csv_path.read_text()
        passed.append('downloaded kitchen CSV uses current revision')
        guests.fill('0'); guests.press('Tab')
        expect(page.locator('#preview')).to_be_hidden()
        expect(page.locator('#error')).to_contain_text('Headcount')
        guests.fill('60'); guests.press('Tab')
        expect(page.locator('#preview')).to_be_visible()
        passed.append('invalid input hides stale quote and recovery is immediate')
        page.once('dialog', lambda d: d.accept('Example customer email reference'))
        page.locator('#confirm').click()
        expect(page.locator('#quote .revision')).to_contain_text('Confirmed manually')
        page.locator('[data-field=notes]').fill('Pack separately'); page.locator('[data-field=notes]').press('Tab')
        expect(page.locator('#quote .revision')).to_contain_text('Draft')
        passed.append('editing invalidates old confirmation')
        imported = dict(data, revision='12', confirmation=None)
        page.locator('#event-file').set_input_files({'name': 'string-revision.json', 'mimeType': 'application/json', 'buffer': json.dumps(imported).encode()})
        expect(page.locator('#quote .revision')).to_contain_text('Revision 12')
        page.once('dialog', lambda d: d.accept('Imported event confirmation'))
        page.locator('#confirm').click()
        expect(page.locator('#quote .revision')).to_contain_text('Confirmed manually')
        passed.append('imported numeric-text revision can be confirmed')
        page.locator('#menu-file').set_input_files({'name':'menu.csv','mimeType':'text/csv',
            'buffer':b'id,name,unit,serves,price,allergens,prep\nVEG,"Vegetable, platter",tray,10,30.00,Review supplier label,Keep labels attached\n'})
        expect(page.locator('#quote-lines')).to_contain_text('Vegetable, platter')
        expect(page.locator('#kitchen-lines')).to_contain_text('Keep labels attached')
        passed.append('real menu CSV import reaches quote and kitchen notes')
        before = page.locator('#metric-total').inner_text()
        page.locator('#menu-file').set_input_files({'name':'bad.csv','mimeType':'text/csv','buffer':b'id,name\nX,Bad'})
        expect(page.locator('#error')).to_contain_text('missing')
        assert page.locator('#metric-total').inner_text() == before
        passed.append('malformed menu import preserves previous workspace')
        page.locator('[data-field=received]').fill('50.00'); page.locator('[data-field=received]').press('Tab')
        expect(page.locator('#totals')).to_contain_text('Received (manual)')
        page.locator('[data-field=paymentLink]').fill('https://example.com/existing-payment'); page.locator('[data-field=paymentLink]').press('Tab')
        expect(page.locator('#payment a')).to_have_attribute('href', 'https://example.com/existing-payment')
        expect(page.locator('#payment')).to_contain_text("Check the provider's amount")
        passed.append('manual receipt and existing payment handoff render without contacting provider')
        page.locator('[data-field=name]').fill('<b>Plain text event</b>'); page.locator('[data-field=name]').press('Tab')
        expect(page.locator('#quote .event-name')).to_have_text('<b>Plain text event</b>')
        assert page.locator('#quote .event-name b').count() == 0
        passed.append('supplied text stays text, not markup')
        page.evaluate("window.print = () => { window.printCount = (window.printCount || 0) + 1; }")
        page.locator('#print-quote').click(); assert page.evaluate('document.body.dataset.print') == 'quote'
        page.emulate_media(media='print')
        expect(page.locator('#quote')).to_be_visible(); expect(page.locator('#kitchen')).to_be_hidden()
        page.screenshot(path=str(args.artifacts / 'quote-print.png'), full_page=True)
        page.emulate_media(media='screen'); page.locator('#print-kitchen').click()
        page.emulate_media(media='print')
        expect(page.locator('#quote')).to_be_hidden(); expect(page.locator('#kitchen')).to_be_visible()
        page.screenshot(path=str(args.artifacts / 'kitchen-print.png'), full_page=True)
        page.emulate_media(media='screen')
        passed.append('quote and kitchen print modes isolate the correct document')
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.screenshot(path=str(args.artifacts / 'mobile.png'), full_page=True)
        passed.append('390-pixel mobile layout has no page overflow')
        assert not errors, errors
        assert not network, network
        passed.append('zero JavaScript exceptions and zero external network requests')
        browser.close()
    server.shutdown()
    server.server_close()
    thread.join()
    result = {'mode': 'in-memory DOM' if args.in_memory else 'loopback HTTP', 'native_storage_tested': not args.in_memory, 'passed':len(passed),'checks':passed,'javascript_errors':errors,'external_network_requests':network}
    (args.artifacts / 'browser-results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
