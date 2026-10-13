#!/usr/bin/env python3
"""Optional in-memory Chromium DOM check with a real SQLite Store bridge.

No browser network/navigation or native-download coverage is claimed. The product's
HTTP routes are covered separately by test_app.py. All records here are synthetic.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import time
from playwright.sync_api import sync_playwright, expect
from app import Store, DeskError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chromium', default='/usr/bin/chromium')
    parser.add_argument('--output', type=Path, default=Path('browser-results'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    checks = []
    def record(name, condition=True):
        assert condition, name
        checks.append(name)
        print("PASS",name,flush=True)
    html = (Path(__file__).parent / 'index.html').read_text().replace('<script src="desk.js" defer></script>', '')
    script = (Path(__file__).parent / 'desk.js').read_text()
    with tempfile.TemporaryDirectory() as td:
        store = Store(Path(td) / 'events.sqlite3')
        def bridge(path, payload):
            parts = path.split('?')[0].strip('/').split('/')[2:]
            write = payload is not None
            try:
                if not parts:
                    result = store.save_event(payload) if write else store.list_events()
                elif len(parts) == 1:
                    result = store.save_event(payload, parts[0]) if write else store.detail(parts[0])
                elif len(parts) == 2 and parts[1] == 'exhibitors':
                    result = store.save_exhibitor(parts[0], payload)
                elif len(parts) == 3 and parts[1] == 'exhibitors':
                    result = store.save_exhibitor(parts[0], payload, parts[2]) if write else store.detail(parts[0], parts[2])
                elif len(parts) == 4 and parts[3] == 'assets':
                    result = store.add_asset(parts[0], parts[2], payload)
                elif len(parts) == 4 and parts[3] == 'changes':
                    result = store.request_change(parts[0], parts[2], payload)
                elif len(parts) == 5 and parts[3] == 'changes':
                    result = store.resolve_change(parts[0], parts[2], parts[4], payload)
                else:
                    raise AssertionError('Unexpected DOM test route: ' + path)
                return {'ok':True, 'result':result}
            except DeskError as exc:
                return {'ok':False, 'result':{'error':str(exc)}}
        def load_dom(page, search=''):
            page.set_content(html)
            page.add_script_tag(content='''window.fetch=async(path, options)=> {
                const r=await window.storeBridge(path, options && options.body !== undefined ? JSON.parse(options.body) : null);
                return {ok:r.ok,json:async()=>r.result};
            };''')
            # Only the query source is supplied for the portal test; app logic stays unchanged.
            page.add_script_tag(content=script.replace('new URLSearchParams(location.search)', 'new URLSearchParams(' + json.dumps(search) + ')'))
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=args.chromium, headless=True, args=['--no-sandbox'])
            context = browser.new_context(viewport={'width':1440, 'height':1100}, timezone_id='America/Indiana/Indianapolis', accept_downloads=True)
            context.set_default_timeout(5000)
            context.expose_function('storeBridge', bridge)
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda exc: errors.append(str(exc)))
            load_dom(page)
            form = page.locator('form').first
            form.get_by_label('Event name', exact=True).fill('SAMPLE — Makers Showcase')
            form.get_by_label('Venue', exact=True).fill('Example Hall · synthetic event')
            form.get_by_label('Event begins').fill('2026-10-15T09:00')
            form.get_by_label('Materials due').fill('2026-10-01T17:00')
            form.get_by_label('Current exhibitor instructions').fill('Synthetic demonstration. Bring a labelled crate and use the east loading entrance.')
            form.get_by_role('button', name='Create event', exact=True).click()
            expect(page.locator('#notice')).to_contain_text('Event information saved')
            record('browser event creation saves explicit time zone', store.list_events()[0]['starts_at'] == '2026-10-15T13:00:00+00:00')
            eid = store.list_events()[0]['id']
            form = page.locator('form').filter(has=page.get_by_role('button', name='Add exhibitor', exact=True))
            for name, value in [('Company','Sample Ceramics'), ('Contact name','Example Coordinator'), ('Email for reminder drafts','sample@example.invalid'), ('Booth code','A01'), ('Booth width','3'), ('Booth depth','3'), ('Requested power','500'), ('Equipment, access','One table; step-free loading requested.')]:
                form.get_by_label(name).fill(value)
            form.get_by_role('button',name='Add exhibitor',exact=True).click()
            expect(page.locator('#notice')).to_contain_text('Exhibitor requirements saved')
            xid = store.detail(eid)['exhibitors'][0]['id']
            record('browser intake persists booth requirements', store.detail(eid)['exhibitors'][0]['power_w'] == 500)
            data = b'Original synthetic booth asset\x00\xff\n'
            page.get_by_label('File · up to').set_input_files({'name':'original booth.bin','mimeType':'application/octet-stream','buffer':data})
            page.get_by_role('button',name='Upload original file').click()
            expect(page.locator('#notice')).to_contain_text('Original asset stored')
            asset = store.detail(eid)['exhibitors'][0]['assets'][0]
            record('browser file upload preserves exact hash', asset['sha256'] == hashlib.sha256(data).hexdigest())
            href = page.get_by_role('link',name='original booth.bin',exact=True).get_attribute('href')
            record('original asset link targets scoped original bytes', href == f'/api/events/{eid}/exhibitors/{xid}/assets/{asset["id"]}' and store.asset(eid,xid,asset['id'])['data'] == data)
            link = page.get_by_role('link',name='Open exhibitor portal').get_attribute('href')
            portal = context.new_page()
            portal.on('pageerror',lambda exc:errors.append(str(exc)))
            load_dom(portal, link)
            expect(portal.locator('#sidebar')).to_be_hidden()
            record('portal opens scoped exhibitor and current deadline', portal.get_by_role('heading',name='Sample Ceramics',exact=True).count() == 1)
            portal.get_by_label('Booth width').fill('4')
            portal.get_by_label('What changed and why?').fill('Display wall is wider; need four metres.')
            portal.get_by_role('button',name='Request requirement change').click()
            expect(portal.locator('#notice')).to_contain_text('Change recorded')
            record('portal request leaves current requirements intact',store.detail(eid)['exhibitors'][0]['width_m']=='3')
            page.get_by_role('button',name='Refresh current information').click()
            expect(page.get_by_role('button',name='Apply requested change')).to_be_visible()
            page.get_by_label('Resolution note').fill('Organizer checked the layout; use the revised four-metre footprint.')
            page.get_by_role('button',name='Apply requested change').click()
            expect(page.locator('#notice')).to_contain_text('Requested requirements applied')
            record('organizer resolves and applies portal change',store.detail(eid)['exhibitors'][0]['width_m']=='4')
            portal.get_by_role('button',name='Refresh current information').click()
            expect(portal.get_by_label('Booth width')).to_have_value('4')
            record('portal refresh shows changed requirements')
            page.get_by_text('Edit event and deadline',exact=True).click()
            form = page.locator('form').filter(has=page.get_by_role('button',name='Save event information'))
            form.get_by_label('Materials due').fill('2026-10-04T12:00')
            form.get_by_role('button',name='Save event information').click()
            expect(page.locator('#notice')).to_contain_text('Event information saved')
            portal.get_by_role('button',name='Refresh current information').click()
            expect(portal.get_by_text('Materials due:',exact=False)).to_contain_text('Oct 4, 2026')
            record('portal shows revised deadline after refresh')
            links = {'Download reminder draft':f'/exhibitors/{xid}/reminder.eml', 'Calendar file':'/deadlines.ics', 'Floor-plan CSV':'/floor-plan.csv', 'Complete event packet':'/packet.zip'}
            for label, suffix in links.items():
                record(label + ' uses saved event scope', page.get_by_role('link',name=label,exact=True).get_attribute('href') == f'/api/events/{eid}' + suffix)
            fresh = context.new_page()
            fresh.on('pageerror', lambda exc:errors.append(str(exc)))
            load_dom(fresh)
            page.close()
            page = fresh
            page.get_by_role('button',name='Sample Ceramics').click()
            expect(page.get_by_label('Booth width',exact=False).first).to_have_value('4')
            record('fresh DOM reconstructs stored revisions and original file',page.get_by_role('link',name='original booth.bin',exact=True).count()==1)
            page.screenshot(path=str(args.output/'desktop.png'),full_page=True)
            record('desktop no horizontal overflow',page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(args.output/'mobile.png'),full_page=True)
            record('390px mobile no horizontal overflow',page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            portal.set_viewport_size({'width':390,'height':844})
            portal.screenshot(path=str(args.output/'portal-mobile.png'),full_page=True)
            record('390px portal no horizontal overflow',portal.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            record('no JavaScript exceptions',not errors)
            context.close()
            browser.close()
    result = {'passed':len(checks),'checks':checks,'elapsed_seconds':round(time.monotonic()-started,3),'transport':'in-memory Chromium DOM with direct real Store bridge; no browser HTTP or native downloads','synthetic_data_only':True}
    (args.output/'browser-results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
