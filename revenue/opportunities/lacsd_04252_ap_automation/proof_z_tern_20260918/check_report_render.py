from pathlib import Path
import json,hashlib
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parent
report=root/'lacsd-proof/synthetic-demonstration-v3/index.html'
raw=report.read_text(encoding='utf-8')
results=[]
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
 for width,height,label in [(1440,1000,'desktop'),(390,844,'mobile')]:
  page=browser.new_page(viewport={'width':width,'height':height})
  requests=[]; errors=[]
  page.on('request', lambda r: requests.append(r.url))
  page.on('pageerror', lambda e: errors.append(str(e)))
  # Render the exact bytes directly. This makes no assertion about browser-specific
  # file:// support or remote deployment.
  page.set_content(raw,wait_until='load')
  page.screenshot(path=str(root/'lacsd-proof'/f'report_{label}.png'),full_page=True)
  metrics=page.evaluate('''() => ({documentWidth:document.documentElement.scrollWidth, viewportWidth:innerWidth, rows:document.querySelectorAll('tbody tr').length, scriptCount:document.scripts.length, formCount:document.forms.length, resourceCount:document.querySelectorAll('img,iframe,link[rel=stylesheet]').length})''')
  result={'view':label,'render_method':'set_content of exact HTML bytes, not file URL navigation','requests':requests,'errors':errors,**metrics}
  if requests or errors or metrics['rows']!=11 or metrics['documentWidth']>width or metrics['scriptCount'] or metrics['formCount']:
   raise RuntimeError(result)
  results.append(result);page.close()
 browser.close()
(root/'lacsd-proof/render_receipt.json').write_text(json.dumps({'html_sha256':hashlib.sha256(report.read_bytes()).hexdigest(),'results':results},indent=2)+'\n')
print(json.dumps(results,indent=2))
