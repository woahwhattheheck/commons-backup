#!/usr/bin/env python3
"""Source-bound, offline Chromium saved-draft byte and race regression checks.

Uses actual browser File objects; only selected read-completion timing is gated.
The DOM is a test fixture, not full production layout. No parent-compiler, HTTP,
hosted-CI, or main-merge claim is made. Original failures are negative controls.
"""
from __future__ import annotations
import argparse,asyncio,copy,hashlib,json,platform,re
from pathlib import Path
from datetime import datetime,timezone
from typing import Any
from playwright.async_api import async_playwright
import browser_race_review as shared

ROOT=Path(__file__).resolve().parent
BASE='c4c305db7944cb305625836d4767d6abcc37ae36'
SOURCE_PINS={'composed_app.js':'808a89401a7978c4897feb351aee231adcba8dd6',
 'composed_handoff.js':'114e6c0bf9041a5dd178ed5b646e6b2069848d7e',
 'handoff_import.js':'20703283260781e87ef88c7ca0af17b380541f74'}
INVALID={
 'invalid_leading_byte':b'\xff',
 'isolated_continuation':b'\x80',
 'truncated_multibyte':b'\xe2\x82',
 'invalid_continuation':b'\xc3(',
 'overlong_utf8':b'\xc0\xaf',
 'surrogate_utf8':b'\xed\xa0\x80',
 'outside_unicode_range':b'\xf4\x90\x80\x80',
}
VALID={
 'valid_ascii':'Saved source note',
 'valid_unicode':'café / 観察 / 🧪',
 'valid_replacement_character':'Real literal \ufffd is valid text',
 'valid_multiline':'First line\r\nsecond line\nthird line',
 'valid_empty_note':'',
 'valid_html_as_text':'<b>literal</b> & **not markup**',
 'valid_bom':'UTF-8 signature accepted',
 'valid_limit_4000':'x'*4000,
 'valid_astral_limit':'🧪'*2000,
 'valid_all_twelve_reordered':'Reordered saved record',
}
SCHEMA_CASES=['duplicate_json_key','wrong_receipt','wrong_status','authority_true',
 'missing_cell','duplicate_cell','wrong_synthetic','oversized_note','malformed_json',
 'array_root','oversized_file','deep_nesting']
RACE_CASES=['delayed_valid_edit','delayed_invalid_edit','delayed_reset',
 'delayed_same_receipt_replacement','delayed_other_receipt','newer_restore_wins',
 'read_failure','stale_read_failure']
CASES=list(VALID)+list(INVALID)+SCHEMA_CASES+RACE_CASES
# Explicit expected contracts, never chosen by observing what happens to pass.
CONTRACTS={
 'historical':{'bom':'accept','invalid_edit_diagnostic':'Notes changed'},
 'strict-shared':{'bom':'reject','invalid_edit_diagnostic':'UTF-8'},
}

SETUP=r'''
window.byteReview={networkCalls:0,gates:[],jobs:[]};
window.fetch=()=>{ byteReview.networkCalls++; throw new Error('Unexpected network call'); };
byteReview.edit=(note)=>{
  selectCell('ESS|software_development');
  el.note.value=note; el.note.dispatchEvent(new Event('input',{bubbles:true}));
};
byteReview.snapshot=()=>({
  receipt:state.report?.receipt_sha256||null,
  report:state.report?JSON.stringify(state.report):null,
  notes:[...state.notes].sort(([a],[b])=>a.localeCompare(b)),
  dispositions:[...state.dispositions].sort(([a],[b])=>a.localeCompare(b)),
  selected:state.selectedKey, search:el.search.value, filter:el.statusFilter.value,
  detail:el.detail.textContent, cellCount:state.cells.length,
  note:state.notes.get('ESS|software_development')||'',
  error:el.error.textContent, exportStatus:el.exportStatus.textContent,
  importDisabled:el.importDraftBtn.disabled, exportDisabled:el.exportBtn.disabled,
  networkCalls:byteReview.networkCalls
});
byteReview.draft=(note)=>{
  const d=WorkbenchHandoff.buildDraft(state.report);
  d.cell_notes.forEach((row,i)=>{
    row.analyst_note=i===0?note:`Saved cell ${i}`;
    row.disposition=i%2?'DISCUSS_WITH_PRIME':'TECHNICAL_DRAFT_NOTE';
  }); return d;
};
byteReview.installGate=()=>{
  for(const method of ['text','arrayBuffer']) {
    const original=File.prototype[method];
    File.prototype[method]=function(){
      if(!this.name.startsWith('delayed-')) return original.call(this);
      const file=this;
      return new Promise((resolve,reject)=>{
        byteReview.gates.push({method,release:()=>original.call(file).then(resolve,reject),
          reject:()=>reject(new Error('Synthetic file read failure'))});
      });
    };
  }
};
byteReview.start=()=>{const i=byteReview.jobs.length; byteReview.jobs.push(importDraft());return i;};
'''
KEEP=('receipt','report','notes','dispositions','selected','search','filter','detail','cellCount')

def demand(condition:bool,message:str)->None:
    if not condition: raise AssertionError(message)

def unchanged(before:dict,after:dict)->None:
    changed=[key for key in KEEP if before[key]!=after[key]]
    demand(not changed,'Existing review changed: '+', '.join(changed))

def json_bytes(value:Any)->bytes:
    return json.dumps(value,ensure_ascii=False,separators=(',',':')).encode('utf-8')

async def upload(page,raw:bytes,name:str='saved.json')->None:
    await page.set_input_files('#handoffFile',{'name':name,'mimeType':'application/json','buffer':raw})

async def snapshot(page)->dict:
    return await page.evaluate('() => byteReview.snapshot()')

async def restore(page)->None:
    await page.evaluate('() => importDraft()')

async def pending(page,raw:bytes,name:str)->int:
    await upload(page,raw,name)
    index=await page.evaluate('() => byteReview.start()')
    await page.wait_for_function('(n) => byteReview.gates.length>n',arg=index)
    return index

async def release(page,index:int,reject:bool=False)->None:
    await page.evaluate('([i,bad]) => bad ? byteReview.gates[i].reject() : byteReview.gates[i].release()',[index,reject])
    await page.evaluate('(i) => byteReview.jobs[i]',index)

async def click_control(page,selector:str)->None:
    # New presentation wraps import controls in a collapsed native disclosure.
    # Open actual summaries; never force-click hidden controls or mutate app state.
    target=page.locator(selector)
    for _ in range(8):
        closed=target.locator('xpath=ancestor::details[not(@open)]')
        if not await closed.count():
            await target.click()
            return
        await closed.first.locator(':scope > summary').first.click()
    raise AssertionError('Too many closed disclosure ancestors')

async def run_case(page,name:str,contract:str='historical')->dict:
    before=await snapshot(page)
    value=VALID.get(name,'SAVED_SENTINEL')
    draft=await page.evaluate('(note) => byteReview.draft(note)',value)
    raw=json_bytes(draft)
    if name in VALID:
        if name=='valid_bom':
            raw=b'\xef\xbb\xbf'+raw
            if CONTRACTS[contract]['bom']=='reject':
                await upload(page,raw);await restore(page);after=await snapshot(page)
                unchanged(before,after)
                demand('JSON' in after['error'],'Declared BOM rejection did not diagnose invalid JSON')
                demand(not after['importDisabled'],'Restore button stuck after BOM rejection')
                return after
        if name=='valid_all_twelve_reordered':
            draft['cell_notes'].reverse();raw=json_bytes(draft)
        await upload(page,raw);await restore(page)
        after=await snapshot(page)
        demand(not after['error'],'Valid draft rejected: '+after['error'])
        demand(after['note']==value,'Valid note changed')
        expected={f"{r['group']}|{r['dimension']}":r['analyst_note'] for r in draft['cell_notes']}
        demand(dict(after['notes'])==expected,'Not all twelve notes restored exactly')
        demand(after['report']==before['report'],'Compiler report changed on valid restore')
        exported=await page.evaluate('() => WorkbenchHandoff.buildDraft(state.report,state.notes,state.dispositions)')
        demand(all(v is False for v in exported['authority'].values()),'Authority flag changed')
        return after
    if name in INVALID:
        raw=raw.replace(b'SAVED_SENTINEL',INVALID[name])
    elif name in SCHEMA_CASES:
        if name=='duplicate_json_key': raw=raw.replace(b'"schema":',b'"schema":"duplicate","schema":',1)
        elif name=='wrong_receipt': draft['report_receipt_sha256']='f'*64
        elif name=='wrong_status': draft['cell_notes'][0]['compiler_status']='HOLD_DIFFERENT'
        elif name=='authority_true': draft['authority']['prime_approved']=True
        elif name=='missing_cell': draft['cell_notes'].pop()
        elif name=='duplicate_cell': draft['cell_notes'][-1]=copy.deepcopy(draft['cell_notes'][0])
        elif name=='wrong_synthetic': draft['synthetic_demo']=False
        elif name=='oversized_note': draft['cell_notes'][0]['analyst_note']='x'*4001
        elif name=='malformed_json': raw=b'{not-json'
        elif name=='array_root': raw=b'[]'
        elif name=='oversized_file': raw=b' '*(1024*1024+1)
        elif name=='deep_nesting': raw=b'['*66+b'0'+b']'*66
        if name not in ('duplicate_json_key','malformed_json','array_root','oversized_file','deep_nesting'):
            raw=json_bytes(draft)
    else:
        await page.evaluate('() => byteReview.installGate()')
        if name=='delayed_invalid_edit': raw=raw.replace(b'SAVED_SENTINEL',b'\xff')
        first=await pending(page,raw,'delayed-first.json')
        if name in ('read_failure','stale_read_failure'):
            if name=='stale_read_failure':
                await click_control(page,'#resetBtn');before=await snapshot(page)
            await release(page,first,reject=True);after=await snapshot(page)
            unchanged(before,after)
            demand(bool(after['error'])==(name=='read_failure'),'Wrong stale/read error behavior')
            return after
        if name in ('delayed_valid_edit','delayed_invalid_edit'):
            await page.evaluate('() => byteReview.edit("Newer edit must survive")')
            before=await snapshot(page);await release(page,first);after=await snapshot(page)
            unchanged(before,after)
            expected=CONTRACTS[contract]['invalid_edit_diagnostic'] if name=='delayed_invalid_edit' else 'Notes changed'
            demand(expected in after['error'],'Declared diagnostic precedence changed: '+after['error'])
            return after
        if name=='delayed_reset': await click_control(page,'#resetBtn')
        elif name=='delayed_same_receipt_replacement':
            await click_control(page,'#demoBtn');await page.evaluate('() => byteReview.edit("New same-receipt generation")')
        elif name=='delayed_other_receipt':
            await page.evaluate('() => {const r=syntheticReport();r.receipt_sha256="e".repeat(64);installReport(r);byteReview.edit("Other receipt");}')
        elif name=='newer_restore_wins':
            newer=await page.evaluate('() => byteReview.draft("Second restore wins")')
            second=await pending(page,json_bytes(newer),'delayed-second.json')
            await release(page,second)
            demand((await snapshot(page))['note']=='Second restore wins','Second restore never completed')
        before=await snapshot(page);await release(page,first);after=await snapshot(page)
        unchanged(before,after);demand(not after['error'],'Stale completion surfaced an error')
        return after
    await upload(page,raw);await restore(page);after=await snapshot(page)
    unchanged(before,after)
    demand(bool(after['error']),'Rejected-input diagnostic missing')
    demand(not after['importDisabled'],'Restore button stuck disabled')
    if name in INVALID: demand('UTF-8' in after['error'],'UTF-8 diagnosis missing')
    return after

async def main(args)->int:
    if args.candidate:
        app=args.candidate.resolve()
        helper=args.handoff.resolve() if args.handoff else app.with_name('handoff.js')
        importer=args.importer.resolve() if args.importer else app.with_name('handoff_import.js')
        label='candidate'
    else:
        for name,sha in SOURCE_PINS.items():shared.checked_source(ROOT/name,sha)
        app=ROOT/('composed_app.js' if args.variant=='original' else 'fixed_app.js')
        helper=ROOT/'composed_handoff.js';importer=ROOT/'handoff_import.js'
        label=args.variant
    inputs={name:path.read_bytes() for name,path in [('app',app),('handoff',helper),('importer',importer)]}
    git_blob=lambda data:hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    data=inputs['app'];blob=git_blob(data)
    html=shared.HTML if not args.html else re.sub(r'<script\b[^>]*>[\s\S]*?</script\s*>','',args.html.read_text(encoding='utf-8'),flags=re.I)

    result={'schema':'zz-kestrel-saved-draft-byte-review/v1','generated_at':datetime.now(timezone.utc).isoformat(),
      'variant':label,'contract_profile':args.contract,'expected_contract':CONTRACTS[args.contract],
      'candidate_commit_as_supplied':args.candidate_commit if args.candidate else None,
      'historical_fixture_base_commit':BASE if not args.candidate else None,'app_git_blob':blob,
      'app_publication':'TEST_INPUT_ONLY_NOT_A_LIVE_UI_INTEGRATION_CLAIM',
      'source_pins':{name:git_blob(value) for name,value in inputs.items()},
      'runner_git_blob':git_blob(Path(__file__).read_bytes()),
      'dom_sha256':hashlib.sha256(html.encode('utf-8')).hexdigest(),
      'html_git_blob':git_blob(args.html.read_bytes()) if args.html else None,
      'optimized_python':not __debug__,'environment':{'python':platform.python_version(),'platform':platform.platform()},
      'scope':'Actual Chromium File bytes + exact app/helpers + fixture DOM; not production layout, parent compiler, HTTP, hosted CI or merge.','results':[]}
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
        result['environment']['chromium']=browser.version
        for name in CASES:
            page=await browser.new_page();page.set_default_timeout(5000)
            await page.route('**/*',lambda route:route.abort())
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            record={'case':name}
            try:
                await page.set_content(html)
                for file in ('handoff','importer'):
                    await page.add_script_tag(content=inputs[file].decode('utf-8'))
                await page.add_script_tag(content=data.decode())
                await page.add_script_tag(content=SETUP)
                await page.evaluate('''() => {
                    installReport(syntheticReport());
                    for (let i=0;i<state.cells.length;i++) {
                        selectCell(keyFor(state.cells[i]));el.note.value=`Existing note ${i}`;
                        el.note.dispatchEvent(new Event('input',{bubbles:true}));
                        el.disposition.value='NEEDS_EVIDENCE';
                        el.disposition.dispatchEvent(new Event('change',{bubbles:true}));
                    }
                    selectCell('ESS|software_development');el.search.value='ESS';renderMatrix();
                }''')
                observed=await asyncio.wait_for(run_case(page,name,args.contract),timeout=10)
                demand(observed['networkCalls']==0,'Unexpected network call')
                demand(not errors,'Page error: '+str(errors))
                record.update({'pass':True,'observed':observed})
            except Exception as exc:
                record.update({'pass':False,'error':str(exc)})
                try:record['observed']=await snapshot(page)
                except Exception:pass
            finally:await page.close()
            result['results'].append(record)
            print(('PASS' if record['pass'] else 'FAIL')+' '+label+' '+name,flush=True)
        await browser.close()
    result['summary']={'passed':sum(r['pass'] for r in result['results']),'total':len(CASES),
      'failed_cases':[r['case'] for r in result['results'] if not r['pass']]}
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result['summary'],indent=2),flush=True)
    return int(bool(result['summary']['failed_cases']))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--variant',choices=['original','fixed'],help='Run the pinned historical before/after fixture.')
    source.add_argument('--candidate',type=Path,help='Run a supplied composed app; hashes are recorded, not assumed.')
    parser.add_argument('--handoff',type=Path,help='Candidate helper; defaults to handoff.js beside candidate.')
    parser.add_argument('--importer',type=Path,help='Candidate strict parser; defaults to handoff_import.js beside candidate.')
    parser.add_argument('--html',type=Path,help='Optional native DOM; scripts removed, all browser network requests aborted.')
    parser.add_argument('--contract',choices=CONTRACTS,default='historical',
                        help='Explicit BOM/diagnostic expectations; does not alter the app or preservation checks.')
    parser.add_argument('--candidate-commit',help='Optional claimed source commit; actual input blob identities are always recorded.')
    parser.add_argument('--chromium',default='/usr/bin/chromium')
    parser.add_argument('--output',type=Path,required=True)
    raise SystemExit(asyncio.run(main(parser.parse_args())))
