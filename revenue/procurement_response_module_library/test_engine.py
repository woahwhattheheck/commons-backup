from __future__ import annotations
import copy,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from revenue.procurement_response_module_library.engine import Error,compile,load,verify
ROOT=Path(__file__).parent; CAT=ROOT/'catalog.json'; SOL=ROOT/'solicitation.json'
def raw(x): return (json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
class T(unittest.TestCase):
 def setUp(self): self.cb=CAT.read_bytes(); self.sb=SOL.read_bytes(); self.c=json.loads(self.cb); self.s=json.loads(self.sb)
 def test_ready_and_authority_false(self):
  o=compile(self.cb,self.sb); p=json.loads(o.packet); self.assertEqual('OWNER_REVIEW_READY',o.status); self.assertEqual(11,len(p['sections'])); self.assertTrue(all(x['status']=='SUPPORTED' for x in p['sections'])); self.assertTrue(all(v is False for v in p['authority'].values()))
 def test_citations(self):
  p=json.loads(compile(self.cb,self.sb).packet); self.assertTrue(all(c['citations'] for x in p['sections'] for c in x['module']['claims']))
 def test_partial_holds(self):
  c=copy.deepcopy(self.c); c['evidence'][0]['status']='PARTIAL'; o=compile(raw(c),self.sb); self.assertEqual('HOLD',o.status); self.assertIn('EVIDENCE_PARTIAL',' '.join(sum([x['reasons'] for x in json.loads(o.packet)['sections']],[])))
 def test_pending_owner_holds(self):
  c=copy.deepcopy(self.c); c['modules'][0]['owner_status']='PENDING'; self.assertEqual('HOLD',compile(raw(c),self.sb).status)
 def test_missing_family_holds(self):
  c=copy.deepcopy(self.c); fam=self.s['requirements'][0]['family']; c['modules']=[m for m in c['modules'] if m['family']!=fam]; self.assertEqual('HOLD',compile(raw(c),self.sb).status)
 def test_optional_missing_family_not_packet_hold(self):
  s=copy.deepcopy(self.s); s['requirements'].append({'section_id':'optional-x','family':'missing','required_tags':[],'required':False}); o=compile(self.cb,raw(s)); self.assertEqual('OWNER_REVIEW_READY',o.status); self.assertEqual('HOLD',next(x for x in json.loads(o.packet)['sections'] if x['section_id']=='optional-x')['status'])
 def test_tags_gate(self):
  s=copy.deepcopy(self.s); s['requirements'][0]['required_tags']=['federal','public_sector']; self.assertEqual('HOLD',compile(self.cb,raw(s)).status)
 def test_highest_revision(self):
  c=copy.deepcopy(self.c); m=copy.deepcopy(c['modules'][0]); m['revision']=2; m['source_sha256']='f'*64; c['modules'].append(m); p=json.loads(compile(raw(c),self.sb).packet); self.assertEqual(2,next(x for x in p['sections'] if x['family']==m['family'])['module']['revision'])
 def test_unknown_evidence(self):
  c=copy.deepcopy(self.c); c['modules'][0]['claims'][0]['evidence_ids']=['nope']; self.assertRaisesRegex(Error,'unknown evidence',compile,raw(c),self.sb)
 def test_duplicate_evidence(self):
  c=copy.deepcopy(self.c); c['evidence'].append(copy.deepcopy(c['evidence'][0])); self.assertRaisesRegex(Error,'duplicate evidence',compile,raw(c),self.sb)
 def test_duplicate_module_revision(self):
  c=copy.deepcopy(self.c); c['modules'].append(copy.deepcopy(c['modules'][0])); self.assertRaisesRegex(Error,'duplicate module',compile,raw(c),self.sb)
 def test_stale(self):
  c=copy.deepcopy(self.c); c['evidence_max_age_seconds']=1; self.assertRaisesRegex(Error,'stale evidence',compile,raw(c),self.sb)
 def test_future(self):
  c=copy.deepcopy(self.c); c['evidence'][0]['observed_at']='2026-09-17T00:00:00Z'; self.assertRaisesRegex(Error,'future evidence',compile,raw(c),self.sb)
 def test_expired(self):
  c=copy.deepcopy(self.c); c['modules'][0]['valid_until']='2026-09-15T00:00:00Z'; self.assertRaisesRegex(Error,'validity window',compile,raw(c),self.sb)
 def test_bool_revision(self):
  c=copy.deepcopy(self.c); c['modules'][0]['revision']=True; self.assertRaisesRegex(Error,'integer required',compile,raw(c),self.sb)
 def test_duplicate_json_key(self): self.assertRaisesRegex(Error,'duplicate JSON key',load,b'{"x":1,"x":2}')
 def test_bom(self): self.assertRaisesRegex(Error,'BOM',load,b'\xef\xbb\xbf{}')
 def test_float(self): self.assertRaisesRegex(Error,'non-integer',load,b'{"x":1.2}')
 def test_tamper_packet(self):
  o=compile(self.cb,self.sb); p=json.loads(o.packet); p['authority']['submission_authorized']=True; self.assertRaisesRegex(Error,'packet mismatch',verify,self.cb,self.sb,raw(p),o.markdown,o.receipt)
 def test_tamper_markdown(self):
  o=compile(self.cb,self.sb); self.assertRaisesRegex(Error,'markdown mismatch',verify,self.cb,self.sb,o.packet,o.markdown+b'x\n',o.receipt)
 def test_tamper_receipt(self):
  o=compile(self.cb,self.sb); r=json.loads(o.receipt); r['packet_sha256']='0'*64; self.assertRaisesRegex(Error,'receipt mismatch',verify,self.cb,self.sb,o.packet,o.markdown,raw(r))
 def test_cli(self):
  with tempfile.TemporaryDirectory() as d:
   base=[sys.executable,'-m','revenue.procurement_response_module_library.engine']; a=subprocess.run(base+['compile','--library',str(CAT),'--solicitation',str(SOL),'--out-dir',d],cwd=ROOT.parents[1],capture_output=True,text=True); self.assertEqual(0,a.returncode,a.stderr); b=subprocess.run(base+['verify','--library',str(CAT),'--solicitation',str(SOL),'--packet',d+'/packet.json','--markdown',d+'/packet.md','--receipt',d+'/receipt.json'],cwd=ROOT.parents[1],capture_output=True,text=True); self.assertEqual(0,b.returncode,b.stderr); self.assertIn('"verified": true',b.stdout)
if __name__=='__main__': unittest.main()
