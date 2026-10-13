#!/usr/bin/env python3
"""Real Chromium, actual saved files and downloads; synthetic UI report, no HTTP/compiler.

Executes unchanged published HTML/app/importer plus the selected shared handoff.js.
All network requests are explicitly aborted. No browser navigation/transport or
visual/layout acceptance is implied by set_content-based UI execution.
"""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from playwright.sync_api import expect, sync_playwright

HERE=Path(__file__).resolve().parent
DEFAULT=HERE.parent
ROOT=Path(os.environ.get('WORKBENCH_SOURCE', DEFAULT)).resolve()

class ScalarNoteBrowserTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.p=sync_playwright().start()
  exe=os.environ.get('CHROMIUM_EXECUTABLE') or shutil.which('chromium')
  options={'headless':True,'args':['--no-sandbox']}
  if exe:options['executable_path']=exe
  try:cls.browser=cls.p.chromium.launch(**options)
  except Exception:cls.p.stop();raise
  print(f'CHROMIUM={cls.browser.version}; SOURCE={ROOT}',flush=True)
 @classmethod
 def tearDownClass(cls):
  cls.browser.close();cls.p.stop()
 def setUp(self):
  self.ctx=self.browser.new_context(accept_downloads=True)
  self.addCleanup(self.ctx.close)
  self.ctx.route('**/*',lambda route:route.abort())
  self.page=self.ctx.new_page();self.page.set_default_timeout(3000)
  self.errors=[];self.page.on('pageerror',lambda error:self.errors.append(str(error)))
  html=(ROOT/'index.html').read_text(encoding='utf-8')
  html=html.replace('<link rel="stylesheet" href="/style.css">','')
  html=re.sub(r'<script src="/(?:handoff|handoff_import|app)\.js" defer></script>','',html)
  self.page.set_content(html,wait_until='load')
  for name in ['handoff.js','handoff_import.js','app.js']:
   self.page.add_script_tag(content=(ROOT/name).read_text(encoding='utf-8'))
  self.page.evaluate("()=>{window.fetch=()=>{throw new Error('Unexpected network dispatch in saved-review test')};}")
  self.page.locator('#demoBtn').click()
  self.page.locator('.cell').first.click()
  self.page.locator('#note').fill('Current notes must survive.')
  self.page.locator('#disposition').select_option('DISCUSS_WITH_PRIME')
 def tearDown(self):self.assertEqual(self.errors,[],'uncaught UI script error')
 def download(self,selector):
  with self.page.expect_download() as pending:self.page.locator(selector).click()
  with tempfile.TemporaryDirectory() as d:
   target=Path(d)/pending.value.suggested_filename
   pending.value.save_as(target)
   return target.read_text(encoding='utf-8',errors='strict')
 def draft(self):return json.loads(self.download('#exportBtn'))
 def upload(self,draft,name='review.json'):
  # ASCII escape serialization is deliberate: even a lone surrogate here is
  # syntactically valid JSON in valid UTF-8 bytes, not the separate File.text bug.
  raw=json.dumps(draft,ensure_ascii=True).encode('ascii')
  self.page.locator('#handoffFile').set_input_files({'name':name,'mimeType':'application/json','buffer':raw})
 def restore(self,draft):
  self.upload(draft);self.page.locator('#importDraftBtn').click()
  expect(self.page.locator('#importDraftBtn')).to_be_enabled()
 def assert_rejected(self,note,index=0):
  before=self.draft();bad=copy.deepcopy(before);bad['cell_notes'][index]['analyst_note']=note
  self.restore(bad)
  message=self.page.locator('#error').inner_text()
  self.assertRegex(message,r'Unicode scalar|unpaired surrogate')
  self.assertEqual(self.draft(),before)
  expect(self.page.locator('#note')).to_have_value('Current notes must survive.')
  expect(self.page.locator('#disposition')).to_have_value('DISCUSS_WITH_PRIME')
 def test_ascii_escaped_high_surrogate_is_rejected_without_note_loss(self):
  self.assert_rejected('Before \ud800 after')
 def test_ascii_escaped_low_surrogate_is_rejected_without_note_loss(self):
  self.assert_rejected('Before \udfff after')
 def test_invalid_last_cell_preserves_all_twelve_notes_atomically(self):
  baseline=self.draft()
  options=('UNREVIEWED','NEEDS_EVIDENCE','DISCUSS_WITH_PRIME','TECHNICAL_DRAFT_NOTE')
  for index,row in enumerate(baseline['cell_notes']):
   row['analyst_note']=f'Retained original note {index} café 🧪'
   row['disposition']=options[index % len(options)]
  self.restore(baseline)
  expect(self.page.locator('#error')).to_be_empty()
  self.page.locator('.cell').nth(4).click()
  before=self.draft()
  incoming=copy.deepcopy(before)
  # Every preceding row differs. A validate-as-you-apply implementation would
  # visibly corrupt earlier notes before the final invalid row is encountered.
  for index,row in enumerate(incoming['cell_notes'][:-1]):
   row['analyst_note']=f'Incoming replacement {index} must not be applied'
   row['disposition']=options[(index + 1) % len(options)]
   self.assertNotEqual(row['analyst_note'],before['cell_notes'][index]['analyst_note'])
   self.assertNotEqual(row['disposition'],before['cell_notes'][index]['disposition'])
  incoming['cell_notes'][-1]['analyst_note']='Invalid final note \ud800'
  self.restore(incoming)
  self.assertRegex(self.page.locator('#error').inner_text(),r'Unicode scalar|unpaired surrogate')
  self.assertEqual(self.draft(),before,'Rejected final row must preserve the entire original review')
  expect(self.page.locator('#note')).to_have_value(before['cell_notes'][4]['analyst_note'])
  expect(self.page.locator('#disposition')).to_have_value(before['cell_notes'][4]['disposition'])
 def test_valid_twelve_cell_restoration_and_actual_downloads(self):
  before=self.draft();good=copy.deepcopy(before)
  for i,row in enumerate(good['cell_notes']):
   row['analyst_note']=f'Cell {i} café 🧪 cafe\u0301 literal \ufffd'
   row['disposition']='NEEDS_EVIDENCE'
  self.restore(good)
  expect(self.page.locator('#error')).to_be_empty()
  self.assertEqual(self.draft(),good)
  md=self.download('#markdownBtn')
  for row in good['cell_notes']:self.assertIn(row['analyst_note'],md)
  self.assertIn('DRAFT — NON-AUTHORITATIVE',md)
  self.assertTrue(all(v is False for v in good['authority'].values()))
 def test_unicode_plane_endpoints_survive_real_download(self):
  good=self.draft();note='Endpoints '+chr(0x10000)+' '+chr(0x10ffff)+' '+chr(0xd7ff)+' '+chr(0xe000)
  good['cell_notes'][0]['analyst_note']=note;self.restore(good)
  self.assertEqual(self.draft(),good);self.assertIn(note,self.download('#markdownBtn'))
 def test_genuine_replacement_character_and_decomposed_text_are_preserved(self):
  good=self.draft();note='literal \ufffd decomposed cafe\u0301 emoji 👩‍💻'
  good['cell_notes'][0]['analyst_note']=note;self.restore(good)
  self.assertEqual(self.draft()['cell_notes'][0]['analyst_note'],note)
  self.assertIn(note,self.download('#markdownBtn'))
 def open_intake(self):
  panel=self.page.locator('#importPanel')
  if panel.count() and not panel.evaluate('(node)=>node.open'):
   panel.locator('summary').first.click()
 def delayed(self,draft):
  self.page.evaluate("""()=>{const old=File.prototype.arrayBuffer;File.prototype.arrayBuffer=function(){
   if(this.name!=='delayed.json')return old.call(this);
   return new Promise(resolve=>{window.__release=()=>old.call(this).then(resolve)});
  }}""")
  self.upload(draft,'delayed.json');self.page.locator('#importDraftBtn').click()
  self.page.wait_for_function("typeof window.__release==='function'")
 def release(self):self.page.evaluate("async()=>{await window.__release();await new Promise(r=>setTimeout(r,0))}")
 def test_delayed_bad_draft_does_not_replace_intervening_edit(self):
  bad=self.draft();bad['cell_notes'][0]['analyst_note']='\ud800';self.delayed(bad)
  self.page.locator('#note').fill('New work during read.');before=self.draft();self.release()
  self.assertEqual(self.draft(),before)
 def test_delayed_bad_draft_does_not_repopulate_cleared_workbench(self):
  bad=self.draft();bad['cell_notes'][0]['analyst_note']='\ud800';self.delayed(bad)
  self.open_intake();self.page.locator('#resetBtn').click();self.release()
  expect(self.page.locator('#exportBtn')).to_be_disabled()
  expect(self.page.locator('#matrix')).to_have_attribute('data-rendered-cells','0')
  expect(self.page.locator('#error')).to_be_empty()
 def test_delayed_bad_draft_cannot_cross_same_receipt_new_generation(self):
  bad=self.draft();bad['cell_notes'][0]['analyst_note']='\ud800';self.delayed(bad)
  self.open_intake();self.page.locator('#demoBtn').click();self.page.locator('.cell').first.click()
  self.page.locator('#note').fill('New generation with the same synthetic receipt.')
  before=self.draft();self.release();self.assertEqual(self.draft(),before)
  expect(self.page.locator('#error')).to_be_empty()

if __name__=='__main__':unittest.main(verbosity=2)
