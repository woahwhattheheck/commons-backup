#!/usr/bin/env python3
"""Optional Chromium end-to-end acceptance; requires Playwright and a browser.

Runs a real local server and never replaces a blocked browser navigation with a
mock. A browser-policy failure exits nonzero and must not be counted as a pass.
"""
import argparse
import csv
import io
import json
import tempfile
import threading
import zipfile
from pathlib import Path

import studio


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chromium', help='Use an existing Chromium executable')
    parser.add_argument('--output', type=Path, default=Path('browser-results'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory() as tmp:
        server = studio.make_server(studio.Store(Path(tmp)/'studio.sqlite3'), port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        checks=[]
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True, executable_path=args.chromium)
                context = browser.new_context(accept_downloads=True,viewport={'width':1280,'height':1000})
                page = context.new_page()
                failures=[]
                page.on('pageerror',lambda error:failures.append(str(error)))
                base='http://127.0.0.1:'+str(server.server_port)
                page.goto(base,wait_until='networkidle')
                page.locator('#name').fill('Community Craft Supply Planner')
                page.get_by_role('button',name='Save brief revision').click()
                page.locator('#status').filter(has_text='Saved revision 1').wait_for()
                preview=page.locator('#preview').get_attribute('href')
                checks.append('studio creates and saves editable brief')
                page.reload(wait_until='networkidle')
                options=page.locator('#projects option').all_text_contents()
                assert any('Community Craft Supply Planner' in value for value in options)
                checks.append('studio reload reads persisted project')
                planner=context.new_page()
                planner.on('pageerror',lambda error:failures.append(str(error)))
                planner.goto(base+preview,wait_until='networkidle')
                assert planner.title()=='Community Craft Supply Planner'
                planner.locator('#calculate').click()
                cells=planner.locator('#results tbody tr').first.locator('td').all_text_contents()
                assert cells==['Card sheets','26.4 sheets','3','30 sheets'],cells
                checks.append('12 attendees × 2 sheets + 10% reserve = 26.4; 3 packs = 30')
                planner.locator('#plan-name').fill('Saturday workshop')
                planner.locator('#attendees').fill('20')
                planner.locator('#save').click()
                assert 'Saved in this browser' in planner.locator('#status').inner_text()
                planner.reload(wait_until='networkidle')
                saved=planner.locator('#saved option').nth(1).get_attribute('value')
                planner.locator('#saved').select_option(saved)
                planner.locator('#load').click()
                assert planner.locator('#plan-name').input_value()=='Saturday workshop'
                assert planner.locator('#attendees').input_value()=='20'
                checks.append('save, browser reload and reopen preserves edited plan')
                with planner.expect_download() as d:
                    planner.locator('#csv').click()
                csv_bytes=Path(d.value.path()).read_bytes()
                rows=list(csv.reader(io.StringIO(csv_bytes.decode())))
                assert rows[1][0]=='Saturday workshop' and rows[1][-3:]==['44','5','50'],rows
                checks.append('real CSV download contains updated arithmetic and editable inputs')
                with planner.expect_download() as d:
                    planner.locator('#backup').click()
                backup=Path(d.value.path()).read_bytes()
                restored=context.new_page()
                restored.goto(base+preview,wait_until='networkidle')
                restored.locator('#restore').set_input_files({'name':'plans.json','mimeType':'application/json','buffer':backup})
                restored.locator('#status').filter(has_text='Restored 1 plans without duplicates').wait_for()
                assert restored.locator('#saved option').count()==2
                checks.append('real JSON backup import is retry-safe')
                api_path=preview.rsplit('/',1)[0]
                response=context.request.get(base+api_path+'/export.zip')
                assert response.ok
                archive=zipfile.ZipFile(io.BytesIO(response.body()))
                exported=Path(tmp)/'exported'
                archive.extractall(exported)
                # No network host or alternate policy controls are changed.
                standalone=context.new_page()
                standalone.goto((exported/'index.html').as_uri(),wait_until='load')
                standalone.locator('#calculate').click()
                assert '26.4 sheets' in standalone.locator('#results').inner_text()
                checks.append('exported standalone app calculates without the studio server')
                # Exact arithmetic cases exercise the real implementation in the browser.
                edge=planner.evaluate('''() => CreatorPlanner.calculate({name:'exact',attendees:3,materials:[{name:'fraction',unit:'u',per_attendee:'0.1',pack_size:'0.3',buffer_percent:'0'}]})''')
                assert edge[0]['packs']=='1' and edge[0]['purchase']=='0.3',edge
                checks.append('decimal pack boundary does not round 0.3 into two packs')
                planner.screenshot(path=str(args.output/'planner.png'),full_page=True)
                page.screenshot(path=str(args.output/'studio.png'),full_page=True)
                assert not failures,failures
                checks.append('no uncaught browser script errors')
                browser.close()
            report={'status':'PASS','checks':checks,'count':len(checks)}
            (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(report,indent=2))
        except Exception as exc:
            report={'status':'FAILED','checks_completed':checks,'error':str(exc)}
            (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(report,indent=2))
            raise
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=='__main__':
    main()
