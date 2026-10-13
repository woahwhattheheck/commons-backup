#!/usr/bin/env python3
"""Optional browser rehearsal; not a runtime dependency of the stdlib verifier."""
import argparse
import json
from pathlib import Path
import shutil
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread


def run(bundle: Path, executable: str, screenshots: Path | None = None) -> dict:
    from playwright.sync_api import sync_playwright
    expected = [
        ('Where is the RIS evidence gap introduced?', 'L9', 'RIS — evidence gap example'),
        ('Which source is an interview without a retained example?', 'E-006', 'no retained example'),
        ('Which IAM result covers one representative consumer?', 'E-007', 'One representative'),
        ('What is the corresponding limited recommendation?', 'L25', 'R-002'),
    ]
    results = []
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=str(bundle.resolve())))
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    origin = f'http://127.0.0.1:{server.server_port}'
    try:
      with sync_playwright() as tool:
          browser = tool.chromium.launch(executable_path=executable, headless=True,
                                         args=['--no-sandbox','--disable-background-networking'])
          context = browser.new_context(viewport={'width':1365,'height':900})
          context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(origin + '/') else route.abort())
          page = context.new_page()
          for label, anchor, content in expected:
              page.goto(origin + '/review.html')
              if screenshots and not results:
                  screenshots.mkdir(parents=True,exist_ok=True)
                  page.screenshot(path=str(screenshots/'review-guide.png'), full_page=True)
              page.get_by_role('link',name=label,exact=True).click()
              target = page.locator(':target')
              if target.count() != 1 or target.get_attribute('id') != anchor or content not in target.inner_text():
                  raise RuntimeError(f'wrong destination for {label}')
              before = page.url
              page.reload()
              if page.url != before or page.locator(':target').get_attribute('id') != anchor:
                  raise RuntimeError(f'destination lost after reload: {label}')
              results.append({'question':label,'anchor':anchor,'click':'PASS','reload':'PASS'})
              if screenshots and anchor == 'E-006':
                  page.screenshot(path=str(screenshots/'evidence-destination.png'), full_page=True)
          version=browser.version
          browser.close()
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
    return {'browser':'Chromium','version':version,'network':'loopback only; external requests blocked','results':results,'passed':len(results)}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle',type=Path)
    parser.add_argument('--browser',default=shutil.which('chromium') or shutil.which('google-chrome'))
    parser.add_argument('--screenshots',type=Path)
    args=parser.parse_args()
    if not args.browser: parser.error('supply --browser with an installed Chromium executable')
    print(json.dumps(run(args.bundle,args.browser,args.screenshots),ensure_ascii=False,indent=2))
