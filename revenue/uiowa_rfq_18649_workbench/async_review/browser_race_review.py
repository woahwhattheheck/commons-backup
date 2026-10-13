#!/usr/bin/env python3
"""Independent, offline browser logic regression review of pinned workbench apps.

Exercises exact app.js bytes in Chromium using a test DOM and controlled File.text,
fetch and response.json delays. The compiler, production server, full HTML/CSS,
network stack and saved-draft import are NOT tested. No live service is contacted.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from playwright.async_api import async_playwright, Page

ROOT = Path(__file__).resolve().parent
SOURCES = {
    'baseline_main': ('original_app.js','f180d24e5bb05489774d8c0baa4f60d3fd978656','84ba4df57fc6c343a307873393d13a9a5ddc3261'),
    'trellis_16130': ('trellis_app.js','5d6c890a6366c3b4eb787b2c58d15e8f56a07f81','f91169044bc39b1ef7c99ada29d900932fbd15b6'),
    'keystone_16145': ('keystone_app.js','76801653c5839b7224b6a63b4ac0bf1b38f4dd94','3ff9f17c677f39a617a3537d8a61c8b1e15085e9'),
}
HTML='''<!doctype html><meta charset="utf-8"><title>Offline async review fixture</title>
<input id="candidateFile" type="file"><input id="authorityFile" type="file">
<input id="handoffFile" type="file">
<button id="inspectBtn">Inspect</button><button id="demoBtn">Demo</button>
<button id="resetBtn">Reset</button><button id="exportBtn">Export</button>
<button id="restoreBtn">Restore</button><button id="markdownBtn">Markdown</button>
<button id="importDraftBtn">Import draft</button><div id="error"></div>
<dl id="summary"></dl><input id="search"><select id="statusFilter"></select>
<div id="matrix"></div><pre id="detail"></pre><select id="disposition">
<option>UNREVIEWED</option><option>NEEDS_EVIDENCE</option><option>DISCUSS_WITH_PRIME</option>
<option>TECHNICAL_DRAFT_NOTE</option></select><textarea id="note"></textarea>
<div id="exportStatus"></div>'''
HARNESS='''
window.review = { requests: [], jobs: [], fileGates: [], bodyGates: [] };
window.review.defer = () => { let resolve, reject;
  const promise = new Promise((yes,no) => { resolve=yes; reject=no; });
  return {promise,resolve,reject}; };
window.fetch = () => { const gate=review.defer(); review.requests.push(gate); return gate.promise; };
review.files = (delayed=false, contents="{}") => {
  for (const id of ["candidateFile","authorityFile"]) {
    const gate = review.defer(); review.fileGates.push(gate);
    Object.defineProperty(document.getElementById(id),"files", {configurable:true,
      value:[{size:contents.length,text:()=>delayed ? gate.promise : Promise.resolve(contents)}]});
  }
};
review.start = () => { const index=review.jobs.length;
  review.jobs.push(inspectFiles()); return index; };
review.finish = (index, character="a", options={}) => {
  const report=syntheticReport(); report.receipt_sha256=character.repeat(64);
  if (options.invalidMode) report.mode="NOT_AN_INSPECTION";
  const payload=options.failed ? {error:"Synthetic current failure"} : {report};
  const gate=review.defer(); review.bodyGates[index]=gate;
  review.requests[index].resolve({ok:!options.failed,status:options.failed?400:200,
    json:()=> options.delayBody ? gate.promise : Promise.resolve(payload)});
  return payload;
};
review.snapshot = () => ({receipt:state.report?.receipt_sha256 || null,
  note:state.notes.get("ESS|software_development") || "", error:el.error.textContent,
  inspectDisabled:el.inspectBtn.disabled, exportDisabled:el.exportBtn.disabled,
  cellCount:state.cells.length, requests:review.requests.length,
  currentAuthority:state.report?.trust?.current_evidence_review_authority ?? null});
'''

async def settle(page: Page) -> None:
    await page.evaluate('() => new Promise(resolve => setTimeout(resolve,0))')

async def start(page: Page, *, delayed: bool=False, contents: str='{}') -> int:
    await page.evaluate('([delay,text]) => review.files(delay,text)',[delayed,contents])
    index = await page.evaluate('() => review.start()')
    await settle(page)
    return index

async def finish(page: Page, request: int=0, character: str='a', **options: Any) -> Any:
    return await page.evaluate('([i,c,o]) => review.finish(i,c,o)',[request,character,options])

async def job(page: Page, index: int=0) -> None:
    await page.evaluate('(i) => review.jobs[i]',index)

async def snapshot(page: Page) -> dict[str,Any]:
    return await page.evaluate('() => review.snapshot()')

async def expect(page: Page, **expected: Any) -> dict[str,Any]:
    observed=await snapshot(page)
    differences={key:{'expected':value,'observed':observed[key]} for key,value in expected.items() if observed[key]!=value}
    if differences: raise AssertionError(json.dumps(differences,ensure_ascii=False))
    return observed

async def scenario(page: Page, name: str) -> dict[str,Any]:
    if name=='current_success':
        await start(page); await finish(page); await job(page)
        return await expect(page,receipt='a'*64,cellCount=12,inspectDisabled=False,exportDisabled=False,currentAuthority=False,error='')
    if name=='current_failure':
        await start(page); await finish(page,failed=True); await job(page)
        return await expect(page,receipt=None,cellCount=0,inspectDisabled=False,exportDisabled=True,error='Synthetic current failure')
    if name=='invalid_file_does_not_submit':
        await start(page,contents='not json'); await job(page)
        observed=await expect(page,receipt=None,requests=0,inspectDisabled=False,exportDisabled=True)
        if 'not valid JSON' not in observed['error']: raise AssertionError('Missing parse diagnostic')
        return observed
    if name=='new_import_immediately_clears_notes':
        await page.click('#demoBtn'); await page.locator('[data-key="ESS|software_development"]').click()
        await page.fill('#note','Existing review'); await start(page,delayed=True)
        return await expect(page,receipt=None,note='',exportDisabled=True,cellCount=0)
    if name=='invalid_report_is_rejected':
        await start(page); await finish(page,invalidMode=True); await job(page)
        observed=await expect(page,receipt=None,inspectDisabled=False,exportDisabled=True)
        if not observed['error']: raise AssertionError('No invalid-report diagnostic')
        return observed
    if name=='reset_reenables_inspection_immediately':
        await start(page); await page.click('#resetBtn')
        return await expect(page,receipt=None,inspectDisabled=False,exportDisabled=True)
    if name=='reset_ignores_late_success':
        await start(page); await page.click('#resetBtn'); await finish(page); await job(page)
        return await expect(page,receipt=None,cellCount=0,exportDisabled=True,error='')
    if name=='reset_ignores_late_failure':
        await start(page); await page.click('#resetBtn'); await finish(page,failed=True); await job(page)
        return await expect(page,receipt=None,error='',exportDisabled=True)
    if name=='reset_ignores_late_transport_rejection':
        await start(page); await page.click('#resetBtn')
        await page.evaluate('() => review.requests[0].reject(new Error("Synthetic delayed transport failure"))'); await job(page)
        return await expect(page,receipt=None,error='',exportDisabled=True)
    if name=='reset_during_file_read_prevents_submission':
        await start(page,delayed=True); await page.click('#resetBtn')
        await page.evaluate('() => review.fileGates.forEach(gate => gate.resolve("{}"))'); await settle(page)
        # Do not await an original-app job still blocked on an unintended fetch.
        return await expect(page,receipt=None,requests=0,error='',exportDisabled=True)
    if name=='reset_during_body_read_ignores_result':
        await start(page); payload=await finish(page,delayBody=True); await settle(page)
        await page.click('#resetBtn')
        await page.evaluate('(payload) => review.bodyGates[0].resolve(payload)',payload); await job(page)
        return await expect(page,receipt=None,error='',exportDisabled=True)
    if name=='demo_notes_survive_old_response':
        await start(page); await page.click('#demoBtn')
        await page.locator('[data-key="ESS|software_development"]').click()
        await page.fill('#note','New review — preserve Δ\nsecond line')
        await finish(page); await job(page)
        return await expect(page,receipt='d'*64,note='New review — preserve Δ\nsecond line',error='',currentAuthority=False)
    if name=='old_finally_cannot_enable_new_pending_import':
        await start(page); await page.click('#resetBtn')
        # A function call permits this interleaving even where old UI never re-enables Inspect.
        await start(page); await finish(page,0,'a'); await job(page,0)
        return await expect(page,receipt=None,inspectDisabled=True,exportDisabled=True)
    if name=='newer_response_wins_over_older_response':
        await start(page); await page.click('#resetBtn'); await start(page)
        await finish(page,1,'b'); await job(page,1)
        await finish(page,0,'a'); await job(page,0)
        return await expect(page,receipt='b'*64,inspectDisabled=False,error='',currentAuthority=False)
    raise ValueError(f'Unknown scenario {name}')

CASES=[
    'current_success','current_failure','invalid_file_does_not_submit',
    'new_import_immediately_clears_notes','invalid_report_is_rejected',
    'reset_reenables_inspection_immediately','reset_ignores_late_success',
    'reset_ignores_late_failure','reset_ignores_late_transport_rejection',
    'reset_during_file_read_prevents_submission','reset_during_body_read_ignores_result',
    'demo_notes_survive_old_response','old_finally_cannot_enable_new_pending_import',
    'newer_response_wins_over_older_response',
]

def checked_source(path: Path, expected: str) -> str:
    data=path.read_bytes()
    actual=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    if actual!=expected: raise ValueError(f'Source mismatch for {path.name}: {actual} != {expected}')
    return data.decode('utf-8')

async def main(args: argparse.Namespace) -> int:
    sources=dict(SOURCES)
    if args.candidate_app:
        if not args.candidate_blob or not args.candidate_commit:
            raise ValueError('--candidate-app requires --candidate-blob and --candidate-commit')
        sources['candidate']=(str(args.candidate_app.resolve()),args.candidate_blob,args.candidate_commit)
    source_texts={name:checked_source(ROOT/file,blob) for name,(file,blob,_) in sources.items()}
    candidate_handoff = None
    if args.candidate_handoff:
        if not args.candidate_handoff_blob:
            raise ValueError('--candidate-handoff requires --candidate-handoff-blob')
        candidate_handoff=checked_source(args.candidate_handoff,args.candidate_handoff_blob)
    if 'WorkbenchHandoff.' in source_texts.get('candidate','') and candidate_handoff is None:
        raise ValueError('Candidate uses WorkbenchHandoff: supply its exact helper and blob')
    handoff=checked_source(ROOT/'handoff.js','0bf4745d46c06b1cb05fed49078f4aed9811f348')
    results: dict[str,Any]={'schema':'zz-kestrel-independent-browser-review/v1','generated_at':datetime.now(timezone.utc).isoformat(),
      'environment':{'python':platform.python_version(),'platform':platform.platform()},
      'scope':'Exact app.js browser logic with test DOM and synthetic controlled async I/O. Not parent compiler, full UI/layout, saved-draft parser, deployed server, hosted CI, or merge verification.',
      'sources':{name:{'file':file,'git_blob':blob,'commit':commit} for name,(file,blob,commit) in sources.items()},'results':[]}
    async with async_playwright() as playwright:
        browser=await playwright.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
        results['environment']['chromium']=browser.version
        for variant,source in source_texts.items():
            for name in CASES:
                page=await browser.new_page()
                page.set_default_timeout(5000)
                page_errors: list[str]=[]
                page.on('pageerror',lambda err:page_errors.append(str(err)))
                record={'variant':variant,'case':name}
                try:
                    await page.set_content(HTML)
                    # Real peer helper, not a validation stub. Keystone's saved-draft helper is
                    # not invoked by these inspection-only cases and is intentionally not loaded.
                    if variant=='trellis_16130': await page.add_script_tag(content=handoff)
                    if variant=='candidate' and candidate_handoff is not None:
                        await page.add_script_tag(content=candidate_handoff)
                    await page.add_script_tag(content=source)
                    await page.add_script_tag(content=HARNESS)
                    record['observed']=await scenario(page,name)
                    if page_errors: raise AssertionError(f'Unexpected page errors: {page_errors}')
                    record['pass']=True
                except Exception as exc:
                    record.update({'pass':False,'error':str(exc)})
                    try: record['observed']=await snapshot(page)
                    except Exception: pass
                finally:
                    await page.close()
                results['results'].append(record)
                print(f"{'PASS' if record['pass'] else 'FAIL'} {variant} {name}",flush=True)
        await browser.close()
    results['summary']={variant:{'passed':sum(row['pass'] for row in results['results'] if row['variant']==variant),'total':len(CASES)} for variant in sources}
    args.output.write_text(json.dumps(results,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(results['summary'],indent=2))
    # Baseline failures are retained as control evidence, not suppressed; any reviewed
    # PR failure gives this comparator a nonzero exit code.
    return int(any(not row['pass'] for row in results['results'] if row['variant']!='baseline_main'))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chromium',default='/usr/bin/chromium')
    parser.add_argument('--candidate-app',type=Path,help='Additional exact app.js to test')
    parser.add_argument('--candidate-blob',help='GitHub-readback Git blob SHA-1 for candidate app')
    parser.add_argument('--candidate-commit',help='Commit associated with candidate app readback')
    parser.add_argument('--candidate-handoff',type=Path,help='Actual WorkbenchHandoff helper when required')
    parser.add_argument('--candidate-handoff-blob',help='GitHub-readback Git blob SHA-1 for candidate helper')
    parser.add_argument('--output',type=Path,default=ROOT/'browser_review_results.json')
    raise SystemExit(asyncio.run(main(parser.parse_args())))
