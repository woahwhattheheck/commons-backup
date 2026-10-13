from __future__ import annotations
import copy,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from revenue.procurement_award_price_intelligence.engine import Error,compile,load,verify
ROOT=Path(__file__).parent; EX=ROOT/'example.json'
def raw(x): return (json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
def base():
 v=json.loads(EX.read_bytes()); v['sources'][0].update(authority='BUYER_OFFICIAL',uri='https://buyer.example.gov/award/a'); return v
class T(unittest.TestCase):
 def test_example_holds(self): self.assertEqual('HOLD_NO_HISTORY',json.loads(compile(EX.read_bytes())[0])['status'])
 def test_ready(self): self.assertEqual('PRICE_EVIDENCE_READY',json.loads(compile(raw(base()))[0])['status'])
 def test_authority_false(self): self.assertTrue(all(x is False for x in json.loads(compile(raw(base()))[0])['authority'].values()))
 def test_range_separates_award_bid(self):
  v=base(); b=copy.deepcopy(v['observations'][0]); b.update(observation_id='b',claim_key='bid-b',price_kind='BID',amount_minor=17000); v['observations'].append(b); p=json.loads(compile(raw(v))[0]); self.assertEqual(['AWARD','BID'],[g['price_kind'] for g in p['comparable_groups']])
 def test_cross_currency_holds(self):
  v=base(); v['target']['currency']='GBP'; self.assertEqual('HOLD_INCOMPARABLE',json.loads(compile(raw(v))[0])['status'])
 def test_unit_holds(self):
  v=base(); v['target']['unit']='day'; self.assertEqual('HOLD_INCOMPARABLE',json.loads(compile(raw(v))[0])['status'])
 def test_term_holds(self):
  v=base(); v['target']['term_months']=24; self.assertEqual('HOLD_INCOMPARABLE',json.loads(compile(raw(v))[0])['status'])
 def test_basis_holds(self):
  v=base(); v['target'].update(basis='LUMP_SUM',unit=None); self.assertEqual('HOLD_INCOMPARABLE',json.loads(compile(raw(v))[0])['status'])
 def test_estimate_not_anchor(self):
  v=base(); v['observations'][0]['price_kind']='ESTIMATE'; self.assertEqual('HOLD_NO_HISTORY',json.loads(compile(raw(v))[0])['status'])
 def test_ceiling_not_anchor(self):
  v=base(); v['observations'][0]['price_kind']='CEILING'; self.assertEqual('HOLD_NO_HISTORY',json.loads(compile(raw(v))[0])['status'])
 def test_stale(self):
  v=base(); v['sources'][0]['observed_at']='2026-01-01T00:00:00Z'; self.assertEqual('HOLD_STALE',json.loads(compile(raw(v))[0])['status'])
 def test_conflict(self):
  v=base(); s=copy.deepcopy(v['sources'][0]); s.update(source_id='s2',sha256='b'*64,uri='https://buyer.example.gov/award/b'); v['sources'].append(s); o=copy.deepcopy(v['observations'][0]); o.update(observation_id='o2',amount_minor=19500,source_ids=['s2']); v['observations'].append(o); self.assertEqual('HOLD_SOURCE_CONFLICT',json.loads(compile(raw(v))[0])['status'])
 def test_same_claim_same_value_collapses_weight_and_preserves_sources(self):
  v=base(); first_source=v['sources'][0]['source_id']; s=copy.deepcopy(v['sources'][0]); s.update(source_id='s2',sha256='b'*64,uri='https://buyer.example.gov/award/b'); v['sources'].append(s); o=copy.deepcopy(v['observations'][0]); o.update(observation_id='o2',source_ids=['s2']); v['observations'].append(o); p=json.loads(compile(raw(v))[0]); self.assertEqual('PRICE_EVIDENCE_READY',p['status']); self.assertEqual(1,p['comparable_groups'][0]['count']); self.assertEqual(1,len(p['admissible_observations'])); self.assertEqual({first_source,'s2'},set(p['admissible_observations'][0]['source_ids'])); self.assertEqual({first_source,'s2'},{x['source_id'] for x in p['admissible_observations'][0]['sources']})
 def test_distinct_claim_same_value_counts_twice(self):
  v=base(); o=copy.deepcopy(v['observations'][0]); o.update(observation_id='o2',claim_key='different-claim',vendor='Other Vendor'); v['observations'].append(o); p=json.loads(compile(raw(v))[0]); self.assertEqual(2,p['comparable_groups'][0]['count'])
 def test_secondary_not_anchor(self):
  v=base(); v['sources'][0]['authority']='SECONDARY_INDEX'; self.assertEqual('HOLD_NO_HISTORY',json.loads(compile(raw(v))[0])['status'])
 def test_self_authored_not_anchor(self):
  v=base(); v['sources'][0]['authority']='SELF_AUTHORED'; self.assertEqual('HOLD_NO_HISTORY',json.loads(compile(raw(v))[0])['status'])
 def test_bool_money(self):
  v=base(); v['observations'][0]['amount_minor']=True; self.assertRaisesRegex(Error,'integer required',compile,raw(v))
 def test_float_json(self): self.assertRaisesRegex(Error,'non-integer',load,b'{"x":1.2}')
 def test_duplicate_key(self): self.assertRaisesRegex(Error,'duplicate JSON key',load,b'{"x":1,"x":2}')
 def test_bom(self): self.assertRaisesRegex(Error,'BOM',load,b'\xef\xbb\xbf{}')
 def test_future_source(self):
  v=base(); v['sources'][0]['observed_at']='2026-09-17T00:00:00Z'; self.assertRaisesRegex(Error,'future source',compile,raw(v))
 def test_rate_requires_unit(self):
  v=base(); v['observations'][0]['unit']=None; self.assertRaisesRegex(Error,'rate basis requires unit',compile,raw(v))
 def test_lump_forbids_unit(self):
  v=base(); v['observations'][0].update(basis='LUMP_SUM',unit='hour'); self.assertRaisesRegex(Error,'forbids unit',compile,raw(v))
 def test_unknown_source(self):
  v=base(); v['observations'][0]['source_ids']=['missing']; self.assertRaisesRegex(Error,'unknown source',compile,raw(v))
 def test_duplicate_source(self):
  v=base(); v['sources'].append(copy.deepcopy(v['sources'][0])); self.assertRaisesRegex(Error,'duplicate source',compile,raw(v))
 def test_duplicate_observation(self):
  v=base(); v['observations'].append(copy.deepcopy(v['observations'][0])); self.assertRaisesRegex(Error,'duplicate observation',compile,raw(v))
 def test_tamper_packet(self):
  v=raw(base()); p,m,r=compile(v); q=json.loads(p); q['authority']['quote_authorized']=True; self.assertRaisesRegex(Error,'packet mismatch',verify,v,raw(q),m,r)
 def test_tamper_memo(self):
  v=raw(base()); p,m,r=compile(v); self.assertRaisesRegex(Error,'memo mismatch',verify,v,p,m+b'x\n',r)
 def test_tamper_receipt(self):
  v=raw(base()); p,m,r=compile(v); q=json.loads(r); q['packet_sha256']='0'*64; self.assertRaisesRegex(Error,'receipt mismatch',verify,v,p,m,raw(q))
 def test_median_deterministic_lower(self):
  v=base(); o=copy.deepcopy(v['observations'][0]); o.update(observation_id='o2',claim_key='c2',amount_minor=19500); v['observations'].append(o); g=json.loads(compile(raw(v))[0])['comparable_groups'][0]; self.assertEqual(18500,g['median_minor'])
 def test_cli(self):
  v=base()
  with tempfile.TemporaryDirectory() as d:
   inp=Path(d)/'in.json'; inp.write_bytes(raw(v)); out=Path(d)/'out'; cmd=[sys.executable,'-m','revenue.procurement_award_price_intelligence.engine']; a=subprocess.run(cmd+['compile','--input',str(inp),'--out-dir',str(out)],cwd=ROOT.parents[1],capture_output=True,text=True); self.assertEqual(0,a.returncode,a.stderr); b=subprocess.run(cmd+['verify','--input',str(inp),'--packet',str(out/'packet.json'),'--memo',str(out/'memo.md'),'--receipt',str(out/'receipt.json')],cwd=ROOT.parents[1],capture_output=True,text=True); self.assertEqual(0,b.returncode,b.stderr); self.assertIn('"verified": true',b.stdout)
if __name__=='__main__': unittest.main()
