'use strict';
const assert = require('node:assert/strict');
const test = require('node:test');
const path = require('node:path');
const fs = require('node:fs');
const DEFAULT = path.resolve(__dirname, '..');
const ROOT = path.resolve(process.env.WORKBENCH_SOURCE || DEFAULT);
const H = require(path.join(ROOT,'handoff.js'));
const I = require(path.join(ROOT,'handoff_import.js'));
const KEY='ESS|software';
function fixture() {
 const report={mode:'UNTRUSTED_INSPECTION',receipt_sha256:'a'.repeat(64),aggregate_state:'HOLD_TRUSTED_AUTHORITY_REQUIRED',trust:{current_evidence_review_authority:false,authority_root_supplied_out_of_band:false},assessment_matrix:[]};
 for(const group of ['ESS','RIS','IAM'])for(const dimension of ['software','security','deployment','ai_readiness'])report.assessment_matrix.push({group,dimension,status:'UNTRUSTED_EVIDENCE_CONSISTENT',source_ids:[],source_record_sha256s:[],reason_codes:[]});
 return {report,draft:H.buildDraft(report)};
}
const scalarError=/Unicode scalar|unpaired surrogate/;
function withNote(note,index=0){const {report,draft}=fixture();draft.cell_notes[index].analyst_note=note;return {report,draft};}

test('every isolated UTF-16 surrogate is rejected by both shared schema entrances',()=>{
 let count=0;
 for(let code=0xD800;code<=0xDFFF;code++){
  const note='prefix '+String.fromCharCode(code)+' suffix';
  const {report,draft}=withNote(note);
  assert.throws(()=>H.buildDraft(report,new Map([[KEY,note]])),scalarError,`build U+${code.toString(16)}`);
  assert.throws(()=>H.validateDraft(draft,report),scalarError,`restore U+${code.toString(16)}`);
  count++;
 }
 assert.equal(count,2048);
});
test('ASCII JSON escape syntax does not launder an invalid note into the importer',()=>{
 for(const note of ['\ud800','\udfff','x\ud800y','\ud800\ud800','\udc00\ud800','\ud83e\uddea\ud800']){
  const {report,draft}=withNote(note);const raw=JSON.stringify(draft);
  assert.equal(new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(Buffer.from(raw,'utf8')),raw);
  assert.throws(()=>I.parseDraft(raw,report),scalarError);
 }
});
test('Markdown export refuses invalid notes rather than silently repairing them',()=>{
 for(const note of ['\ud800','\udfff']){
  const {report,draft}=withNote(note);assert.throws(()=>H.renderMarkdown(report,draft),scalarError);
 }
});
test('rejecting the last of 12 notes does not mutate the draft or report',()=>{
 const {report,draft}=withNote('last \ud800',11);
 const beforeDraft=JSON.stringify(draft),beforeReport=JSON.stringify(report);
 assert.throws(()=>H.validateDraft(draft,report),scalarError);
 assert.throws(()=>I.parseDraft(beforeDraft,report),scalarError);
 assert.equal(JSON.stringify(draft),beforeDraft);assert.equal(JSON.stringify(report),beforeReport);
});
test('valid surrogate pairs include both range endpoints and neighboring scalars',async()=>{
 for(const code of [0,1,0x7f,0x80,0x7ff,0x800,0xd7ff,0xe000,0xfffd,0xffff,0x10000,0x1f9ea,0x10ffff]){
  const note='note '+String.fromCodePoint(code)+' tail';const {report,draft}=withNote(note);
  assert.equal(I.parseDraft(JSON.stringify(draft),report).notes.get(KEY),note);
  const md=H.renderMarkdown(report,draft);assert.equal(await new Blob([md]).text(),md);
 }
});
test('valid text is never normalized or stripped to make the validator pass',async()=>{
 for(const note of ['café','cafe\u0301','literal \ufffd','観察','👩‍💻','🧑🏽‍🔬','line\nnext','line\r\nnext','\ufeff inside','\u2028\u2029']){
  const {report,draft}=withNote(note);
  assert.equal(H.validateDraft(draft,report)[0].analyst_note,note);
  assert.equal(I.parseDraft(JSON.stringify(draft),report).notes.get(KEY),note);
  const md=H.renderMarkdown(report,draft);assert.equal(await new Blob([md]).text(),md);
 }
});
test('2000 astral symbols retain the existing 4000-code-unit note boundary',()=>{
 const {report}=fixture();const valid='🧪'.repeat(2000);
 const draft=H.buildDraft(report,new Map([[KEY,valid]]));assert.equal(draft.cell_notes[0].analyst_note,valid);
 assert.throws(()=>H.buildDraft(report,new Map([[KEY,valid+'🧪']])),/4000/);
});
test('invalid trailing surrogate is rejected inside, not only beyond, the length cap',()=>{
 const {report}=fixture();assert.throws(()=>H.buildDraft(report,new Map([[KEY,'x'.repeat(3999)+'\ud800']])),scalarError);
});
test('seeded scalar sequences survive all shared-module paths and UTF-8 conversion',async()=>{
 let seed=0x4242cafe;
 function next(){seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed;}
 for(let i=0;i<512;i++){
  let note='';for(let j=0;j<24;j++){let code=next()%0x110000;if(code>=0xd800&&code<=0xdfff)code=0xe000+(code-0xd800);note+=String.fromCodePoint(code);}
  const {report}=fixture();const draft=H.buildDraft(report,new Map([[KEY,note]]));
  assert.equal(I.parseDraft(JSON.stringify(draft),report).notes.get(KEY),note);
  const md=H.renderMarkdown(report,draft);assert.equal(await new Blob([md]).text(),md);
 }
});
test('row order, dispositions and all seven false authority flags remain unchanged',()=>{
 const {report,draft}=fixture();draft.cell_notes.forEach((c,i)=>{c.analyst_note=`Cell ${i} 🧪`;c.disposition='NEEDS_EVIDENCE';});draft.cell_notes.reverse();
 const restored=I.parseDraft(JSON.stringify(draft),report);assert.equal(restored.notes.size,12);
 const rebuilt=H.buildDraft(report,restored.notes,restored.dispositions);
 assert.equal(rebuilt.cell_notes[0].analyst_note,'Cell 0 🧪');assert.equal(Object.keys(rebuilt.authority).length,7);assert.ok(Object.values(rebuilt.authority).every(x=>x===false));
});
test('missing, non-string, oversized and duplicate fields remain validation errors',()=>{
 for(const bad of [null,17,[],{},'x'.repeat(4001)]){const {report,draft}=withNote(bad);assert.throws(()=>I.parseDraft(JSON.stringify(draft),report));}
 const {report,draft}=fixture();const raw=JSON.stringify(draft).replace('"analyst_note":""','"analyst_note":"","analyst_note":"again"');assert.throws(()=>I.parseDraft(raw,report),/duplicate/);
});
test('valid explicit U+FFFD stays distinguishable from rejected escaped surrogates',()=>{
 const {report,draft}=withNote('\ufffd');assert.equal(H.validateDraft(draft,report)[0].analyst_note,'\ufffd');
 draft.cell_notes[0].analyst_note='\ud800';assert.throws(()=>H.validateDraft(draft,report),scalarError);
});
