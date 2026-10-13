"""Embedded DOM -> Python bridge -> real HTTP/SQLite. No native navigation claim."""
import hashlib, json, os, shutil, sys, tempfile, threading
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent
OUTPUT=Path(os.environ.get('CREATOR_DESK_TEST_OUTPUT') or tempfile.mkdtemp(prefix='creator-desk-ui-'))
OUTPUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0,str(ROOT))
from app import make_server
from toolkit import Store

TMP=tempfile.TemporaryDirectory()
store=Store(Path(TMP.name)/'browser.sqlite3')
server=make_server(store,port=0)
thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True)
thread.start()
base=f'http://127.0.0.1:{server.server_port}'
checks=[]; network=[]; errors=[]

def http_bridge(path,method='GET',body=None):
 assert path.startswith('/') and not path.startswith('//')
 request=Request(base+path,data=None if body is None else body.encode(),headers={'Content-Type':'application/json'},method=method)
 try: response=urlopen(request,timeout=8)
 except HTTPError as e: response=e
 with response:
  network.append({'method':method,'path':path.split('?')[0],'status':response.status})
  return {'ok':200<=response.status<300,'status':response.status,'text':response.read().decode()}

shim='''<script>
window.__memoryStorage = new Map();
Object.defineProperty(window, 'localStorage', {value:{getItem:k=>window.__memoryStorage.get(k)||null,setItem:(k,v)=>window.__memoryStorage.set(k,v)}, configurable:true});
window.fetch=async (path,options={})=>{const r=await window.httpBridge(path,options.method||'GET',options.body||null);return {ok:r.ok,status:r.status,json:async()=>JSON.parse(r.text)};};
</script>'''
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'),headless=True,args=['--no-sandbox'])
  context=browser.new_context(viewport={'width':1360,'height':980})
  page=context.new_page();page.on('pageerror', lambda e: errors.append(str(e)))
  page.expose_function('httpBridge',http_bridge)
  html=ROOT.joinpath('index.html').read_text()
  page.set_content(html.replace('<script>',shim+'<script>',1),wait_until='load')
  page.get_by_role('button',name='Creator workspace',exact=True).click()
  page.get_by_role('button',name='Add fictional demo resource',exact=True).click()
  page.wait_for_function("document.getElementById('counts').textContent.includes('1 resources')")
  checks.append('embedded UI creates fictional resource through real HTTP/SQLite')
  page.get_by_role('button',name='Resource library',exact=True).click()
  page.get_by_role('button',name='Get resource',exact=True).first.click()
  page.locator('#member-name').fill('Fictional Reader');page.locator('#member-email').fill('browser@example.invalid')
  page.locator('#request-optin').check()
  page.locator('#request-form').get_by_role('button',name='Get resource',exact=True).click()
  page.wait_for_function("!document.getElementById('member-content').hidden")
  member=page.locator('#member-reference').input_value()
  assert store.member(member)['opted_in'] and len(store.dashboard()['outbox'])==2
  checks.append('resource form schedules only affirmative opt-in')
  href=page.get_by_role('link',name='Download planning-note.txt').get_attribute('href')
  with urlopen(base+href) as response: payload=response.read()
  assert payload==b'Fictional demonstration resource.\nChoose one useful goal and write your next action.\n'
  checks.append('rendered download link resolves to original bytes over real HTTP')
  page.get_by_role('button',name='Creator workspace',exact=True).click()
  page.wait_for_function("document.getElementById('outbox').textContent.includes('due now')")
  href=page.get_by_role('link',name='Download .eml draft').get_attribute('href')
  with urlopen(base+href) as response: draft=response.read()
  assert b'X-Unsent: 1' in draft
  checks.append('due draft UI link returns an actual unsent EML')
  page.get_by_role('button',name='My deliveries',exact=True).click()
  page.locator('#member-reference').fill(member)
  page.get_by_role('button',name='Reconnect',exact=True).click()
  page.wait_for_function("!document.getElementById('member-content').hidden")
  assert page.locator('#member-reference').input_value()==member
  checks.append('explicit member-reference reconnect reads real persisted record')
  page.locator('#inquiry-body').fill('Please share a shorter planning note.')
  page.get_by_role('button',name='Save request for creator',exact=True).click()
  page.wait_for_function("document.getElementById('status').textContent.includes('Request saved')")
  assert len(store.dashboard()['inquiries'])==1
  checks.append('member inquiry form creates actual inbox row')
  page.get_by_role('button',name='Stop follow-up emails',exact=True).click()
  page.wait_for_function("document.getElementById('preference-state').textContent.includes('stopped')")
  assert all(o['state']=='cancelled' for o in store.dashboard()['outbox'])
  checks.append('opt-out form cancels both queued messages')
  page.get_by_role('button',name='Resource library',exact=True).click()
  page.get_by_role('button',name='Get resource',exact=True).first.click()
  page.locator('#request-optin').check()
  page.locator('#request-form').get_by_role('button',name='Get resource',exact=True).click()
  page.wait_for_function("document.getElementById('status').textContent.includes('existing delivery')")
  assert store.dashboard()['counts']['requests']==1 and not store.member(member)['opted_in']
  checks.append('repeat UI request neither duplicates nor re-enrolls')
  page.get_by_role('button',name='Creator workspace',exact=True).click()
  page.wait_for_function("document.getElementById('outbox').textContent.includes('cancelled')")
  assert page.get_by_role('link',name='Download .eml draft').count()==0
  page.get_by_role('button',name='Mark resolved',exact=True).click()
  page.wait_for_function("document.getElementById('inquiries').textContent.includes('closed')")
  checks.append('cancelled drafts have no export links; inquiry resolves')
  page.get_by_role('button',name='Edit title / sequence',exact=True).click()
  page.locator('#resource-title').fill('Revised planning note');page.locator('#sequence').fill('[]')
  page.get_by_role('button',name='Save resource',exact=True).click()
  page.wait_for_function("document.getElementById('resource-list').textContent.includes('Revised planning note')")
  assert store.catalog()[0]['revision']==2 and len(store.dashboard()['outbox'])==2
  checks.append('metadata update keeps queued snapshots')
  page.get_by_role('button',name='Resource library',exact=True).click()
  page.screenshot(path=str(OUTPUT/'creator-desktop.png'),full_page=True)
  for width in [390,320]:
   page.set_viewport_size({'width':width,'height':844})
   for label in ['Resource library','My deliveries','Creator workspace']:
    page.get_by_role('button',name=label,exact=True).click();page.wait_for_timeout(150)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'),(width,label,page.evaluate('document.documentElement.scrollWidth'))
   checks.append(f'{width}px all three tabs without horizontal overflow')
  page.set_viewport_size({'width':390,'height':844});page.get_by_role('button',name='Resource library',exact=True).click()
  page.screenshot(path=str(OUTPUT/'creator-mobile.png'),full_page=True)
  assert not errors,errors
  checks.append('no uncaught browser errors')
  browser.close()
 result={'transport':'embedded DOM -> declared Python bridge -> real HTTP/SQLite','native_navigation':'ERR_BLOCKED_BY_ADMINISTRATOR','storage':'declared in-memory browser adapter; native localStorage not exercised','checks_passed':len(checks),'checks':checks,'http_requests':len(network),'errors':errors,'download_sha256':hashlib.sha256(payload).hexdigest()}
 (OUTPUT/'browser-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
finally:
 server.shutdown();server.server_close();thread.join(2);TMP.cleanup()
