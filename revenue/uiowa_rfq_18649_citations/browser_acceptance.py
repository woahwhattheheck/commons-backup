#!/usr/bin/env python3
"""Optional real-Chromium acceptance; no live providers or paid services."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = 'uiowa_rfq_18649_citations'

from .export import write_new_bundle
from .resolver import Resolver
from .sample import make_sample


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main(argv=None):
    from playwright.sync_api import sync_playwright
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chromium', default='/usr/bin/chromium')
    parser.add_argument('--screenshots', type=Path)
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix='uiowa-browser-') as temp:
        root = Path(temp)
        sources = root / 'inputs'
        sources.mkdir()
        packet, report = make_sample(sources)
        output = root / 'bundle'
        write_new_bundle(Resolver(packet, report, sources), output)
        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(output)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = 'http://127.0.0.1:' + str(server.server_port)
        try:
            return inspect_browser(args, output, origin)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


def inspect_browser(args, output, origin):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(executable_path=args.chromium, headless=True,
                                           args=['--no-sandbox'])
        tab = browser.new_page(viewport={'width': 1280, 'height': 900})
        errors, network = [], []
        tab.on('pageerror', lambda error: errors.append(str(error)))
        tab.on('request', lambda request: network.append(request.url)
               if request.url.startswith(('http:', 'https:')) and not request.url.startswith(origin + '/') else None)
        tab.goto(origin + '/index.html')
        require(tab.locator('tbody tr').count() == 12, 'Expected twelve compiler cells')
        tab.keyboard.press('Tab')
        require(tab.locator(':focus').inner_text() == 'Summary', 'First focus must be Summary')
        tab.keyboard.press('Enter')
        require(tab.url.endswith('#summary'), 'Keyboard summary link did not navigate')
        tab.locator('#citation-F-ESS-C1').get_by_role('link', name='Open exact segment').click()
        require(tab.url.endswith('#text-0004'), 'Did not navigate to exact extracted segment')
        require('Change ENR-17' in tab.locator(':target').inner_text(), 'Wrong source text')
        require('lines 6-7' in tab.locator(':target').inner_text(), 'Wrong source locator')
        tab.get_by_role('link', name='Citation appendix').click()
        require(tab.url.endswith('index.html#appendix'), 'Return link did not navigate')
        require('SOURCE_VERSION_NOT_IN_COMPILER_REPORT' in
                tab.locator('#citation-F-IAM-OLD-C1').inner_text(), 'Historical warning missing')
        require(tab.locator('#citation-F-MISSING-C1 a').count() == 1,
                'Missing source must have only a back-to-finding link')
        tab.goto(origin + '/index.html')
        if args.screenshots:
            args.screenshots.mkdir(parents=True, exist_ok=True)
            tab.screenshot(path=str(args.screenshots / 'desktop.png'))
        tab.set_viewport_size({'width': 390, 'height': 844})
        overflow = tab.evaluate('document.documentElement.scrollWidth > innerWidth')
        if args.screenshots:
            tab.screenshot(path=str(args.screenshots / 'mobile.png'))
        require(not overflow, 'Report overflows the mobile page width')
        require(not errors, 'Browser errors: ' + repr(errors))
        require(not network, 'Unexpected external requests: ' + repr(network))
        version = browser.version
        browser.close()
    print(json.dumps({'result': 'PASS', 'browser': version, 'compiler_cells': 12,
                      'exact_source_navigation': True, 'keyboard_navigation': True,
                      'historical_warning': True, 'missing_source_no_false_link': True,
                      'mobile_body_overflow': False, 'external_requests': 0, 'page_errors': 0, 'delivery': 'loopback HTTP'}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
