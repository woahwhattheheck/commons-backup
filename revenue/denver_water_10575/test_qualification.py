import copy, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
import qualification as q
A="a"*64; B="b"*64; C="c"*64; NOW="2026-09-13T11:20:00Z"
def proof(g,k="capability",subject="proposer",sha=C,ref=None,state="PROVEN"):
 return {"id":"ev-"+g,"claim_id":g,"subject":subject,"kind":k,"state":state,"observed_at":"2026-09-13T11:00:00Z","sha256":sha if state=="PROVEN" else None,"ref":ref or ("evidence:"+g if state=="PROVEN" else None)}
def req(g,route="BOTH",kind="capability",cure="NONE",shared=False,src="packet"):
 return {"id":g,"title":g,"route":route,"mandatory":True,"cure":cure,"requirement_source_id":src,"source_locator":"packet:section:"+g,"evidence_subject":"proposer","evidence_kind":kind,"allow_shared_source":shared}
def auth(reqs=None,files=None,deadline="2026-09-30T20:00:00Z",fresh="2026-09-30T19:00:00Z"):
 rs=sorted(copy.deepcopy(reqs or [req("runtime"),req("references","PRIME","past-performance","PARTNER_CURABLE"),req("integration","TEAMING","integration")]),key=lambda x:x["id"])
 fs=files or [{"id":"packet","class":"OFFICIAL_PACKET","url":"https://buyer.invalid/rfp.pdf","sha256":A}]
 return {"schema":q.AUTHORITY_SCHEMA,"opportunity_id":"denver-water-10575","solicitation_id":"10575","buyer":"Denver Water","state":"ACQUIRED","checked_at":"2026-09-13T10:00:00Z","fresh_until":fresh,"proposal_deadline":deadline,"deadline_source_id":"packet","official_files":copy.deepcopy(fs),"requirements":rs,"requirements_sha256":q._digest(rs)}
def payload(a):
 ss=[{"id":"notice","class":"OFFICIAL_NOTICE","state":"OBSERVED","url":"https://buyer.invalid/opps","captured_at":"2026-09-13T10:00:00Z","sha256":None,"label":"notice"}]
 for f in a["official_files"]: ss.append({"id":f["id"],"class":f["class"],"state":"ACQUIRED","url":f["url"],"captured_at":"2026-09-13T10:00:00Z","sha256":f["sha256"],"label":f["id"]})
 gs=[]
 for r in a["requirements"]:
  g=copy.deepcopy(r); g["evidence"]=proof(r["id"],r["evidence_kind"],r["evidence_subject"]); gs.append(g)
 return {"schema":q.PAYLOAD_SCHEMA,"opportunity":{"id":"denver-water-10575","solicitation_id":"10575","title":"Customer Experience AI Chatbot"},"sources":ss,"gates":gs}
class Trusted(unittest.TestCase):
 def setUp(self):
  self.a=auth(); self.p=payload(self.a); self.patch=mock.patch.object(q,"TRUSTED_AUTHORITY_SHA256",q._digest(self.a)); self.patch.start()
 def tearDown(self): self.patch.stop()
 def ev(self,p=None,a=None,now=NOW): return q._evaluate_at(p or self.p,a or self.a,now)
 def gate(self,p,g): return next(x for x in p["gates"] if x["id"]==g)
 def test_prime_ready(self): self.assertEqual(self.ev()["disposition"],"PRIME_READY")
 def test_partner_gap_teams(self):
  p=copy.deepcopy(self.p); e=self.gate(p,"references")["evidence"]; e.update(proof("references","past-performance",state="FAILED")); self.assertEqual(self.ev(p)["disposition"],"TEAMING_READY")
 def test_omitted_gate_holds(self):
  p=copy.deepcopy(self.p); p["gates"]=[g for g in p["gates"] if g["id"]!="references"]; self.assertEqual(self.ev(p)["reasons"],["REQUIREMENT_MANIFEST_MISMATCH"])
 def test_one_easy_gate_holds(self):
  p=copy.deepcopy(self.p); p["gates"]=[self.gate(p,"runtime")]; self.assertEqual(self.ev(p)["disposition"],"HOLD")
 def test_descriptor_drift_holds(self):
  for f,v in [("mandatory",False),("route","TEAMING"),("cure","OWNER_CURABLE"),("source_locator","packet:other")]:
   p=copy.deepcopy(self.p); self.gate(p,"references")[f]=v; self.assertEqual(self.ev(p)["reasons"],["REQUIREMENT_MANIFEST_MISMATCH"])
 def test_file_digest_drift_holds(self):
  p=copy.deepcopy(self.p); next(x for x in p["sources"] if x["id"]=="packet")["sha256"]=B; self.assertEqual(self.ev(p)["reasons"],["CONTROLLING_FILE_SET_MISMATCH"])
 def test_missing_addendum_holds(self):
  fs=self.a["official_files"]+[{"id":"add","class":"OFFICIAL_ADDENDUM","url":"https://buyer.invalid/add.pdf","sha256":B}]; a=auth(files=fs); p=payload(a); p["sources"]=[x for x in p["sources"] if x["id"]!="add"]
  with mock.patch.object(q,"TRUSTED_AUTHORITY_SHA256",q._digest(a)): self.assertEqual(q._evaluate_at(p,a,NOW)["reasons"],["CONTROLLING_FILE_SET_MISMATCH"])
 def test_claim_binding_holds(self):
  p=copy.deepcopy(self.p); e=self.gate(p,"references")["evidence"]; e["claim_id"]="runtime"; e["kind"]="capability"; self.assertIn("EVIDENCE_CLAIM_BINDING_MISMATCH",self.ev(p)["reasons"][0])
 def test_cross_gate_proof_reuse_holds(self):
  p=copy.deepcopy(self.p); a=self.gate(p,"runtime")["evidence"]; r=self.gate(p,"references")["evidence"]; r["sha256"],r["ref"]=a["sha256"],a["ref"]; self.assertEqual(self.ev(p)["reasons"],["EVIDENCE_SOURCE_REUSE_NOT_AUTHORIZED"])
 def test_shared_proof_requires_manifest_permission(self):
  rs=[req("a",kind="controls",shared=True),req("b",kind="controls",shared=True)]; a=auth(rs); p=payload(a); p["gates"][1]["evidence"]["sha256"]=p["gates"][0]["evidence"]["sha256"]; p["gates"][1]["evidence"]["ref"]=p["gates"][0]["evidence"]["ref"]
  with mock.patch.object(q,"TRUSTED_AUTHORITY_SHA256",q._digest(a)): self.assertEqual(q._evaluate_at(p,a,NOW)["disposition"],"PRIME_READY")
 def test_future_source_and_evidence_rejected(self):
  p=copy.deepcopy(self.p); p["sources"][0]["captured_at"]="2026-09-13T12:00:00Z"
  with self.assertRaises(q.QualificationError): self.ev(p)
  p=copy.deepcopy(self.p); p["gates"][0]["evidence"]["observed_at"]="2026-09-13T12:00:00Z"
  with self.assertRaises(q.QualificationError): self.ev(p)
 def test_deadline_and_freshness_owned_by_authority(self):
  self.assertEqual(self.ev(now="2026-10-01T00:00:00Z")["reasons"],["TRUSTED_PROPOSAL_DEADLINE_EXPIRED"])
  a=auth(deadline="2026-10-30T00:00:00Z",fresh="2026-09-13T11:19:59Z"); p=payload(a)
  with mock.patch.object(q,"TRUSTED_AUTHORITY_SHA256",q._digest(a)): self.assertEqual(q._evaluate_at(p,a,NOW)["reasons"],["TRUSTED_AUTHORITY_STALE"])
 def test_payload_cannot_inject_deadline(self):
  p=copy.deepcopy(self.p); p["opportunity"]["proposal_deadline"]="2099-01-01T00:00:00Z"
  with self.assertRaises(q.QualificationError): self.ev(p)
 def test_historical_ready_loses_current_authority(self):
  r=q._compile_at(self.p,self.a,"2026-09-29T12:00:00Z"); self.assertEqual(r["disposition"],"PRIME_READY")
  with mock.patch.object(q,"_now_string",return_value="2026-10-01T00:00:00Z"):
   v=q.verify_current(self.p,self.a,r); self.assertEqual(v["current_disposition"],"NO_BID"); self.assertFalse(v["current_commercial_authority"])
 def test_tamper_rejected(self):
  r=q._compile_at(self.p,self.a,NOW); r["disposition"]="TEAMING_READY"
  with mock.patch.object(q,"_now_string",return_value=NOW), self.assertRaises(q.QualificationError): q.verify_current(self.p,self.a,r)
 def test_order_invariant(self):
  r=self.ev(); p=copy.deepcopy(self.p); p["sources"].reverse(); p["gates"].reverse(); self.assertEqual(r,self.ev(p))
class Root(unittest.TestCase):
 def test_current_root_is_pinned(self):
  here=Path(__file__).parent; a=q.load_json_bytes((here/"trusted_authority.json").read_bytes()); self.assertEqual(q._digest(a),q.TRUSTED_AUTHORITY_SHA256)
 def test_self_minted_authority_rejected(self):
  a=auth(); p=payload(a)
  with self.assertRaisesRegex(q.QualificationError,"root mismatch"): q._evaluate_at(p,a,NOW)
 def test_inner_manifest_hash_corruption_rejected(self):
  a=auth(); a["requirements_sha256"]=B
  with mock.patch.object(q,"TRUSTED_AUTHORITY_SHA256",q._digest(a)), self.assertRaisesRegex(q.QualificationError,"manifest digest"): q._evaluate_at(payload(auth()),a,NOW)
 def test_not_acquired_cannot_smuggle_material(self):
  here=Path(__file__).parent; a=q.load_json_bytes((here/"trusted_authority.json").read_bytes()); a["official_files"]=[{"id":"x","class":"OFFICIAL_PACKET","url":"https://x.invalid/x","sha256":A}]
  with mock.patch.object(q,"TRUSTED_AUTHORITY_SHA256",q._digest(a)), self.assertRaisesRegex(q.QualificationError,"must not carry readiness"): q._evaluate_at(json.loads((here/"current_qualification.json").read_text()),a,NOW)
class Current(unittest.TestCase):
 def setUp(self):
  self.h=Path(__file__).parent; self.p=q.load_json_bytes((self.h/"current_qualification.json").read_bytes()); self.a=q.load_json_bytes((self.h/"trusted_authority.json").read_bytes())
 def test_fixture_holds(self): self.assertEqual(q._evaluate_at(self.p,self.a,NOW)["reasons"],["CONTROLLING_PACKET_NOT_ACQUIRED"])
 def test_duplicate_json_and_nan_rejected(self):
  with self.assertRaises(q.QualificationError): q.load_json_bytes(b'{"x":1,"x":2}')
  with self.assertRaises(q.QualificationError): q.load_json_bytes(b'{"x":NaN}')
 def test_strict_keys_and_bool(self):
  p=copy.deepcopy(self.p); p["gates"][0]["surprise"]=1
  with self.assertRaises(q.QualificationError): q._evaluate_at(p,self.a,NOW)
  p=copy.deepcopy(self.p); p["gates"][0]["mandatory"]=1
  with self.assertRaises(q.QualificationError): q._evaluate_at(p,self.a,NOW)
 def test_nonproven_cannot_carry_proof(self):
  p=copy.deepcopy(self.p); e=p["gates"][0]["evidence"]; e["sha256"]=A
  with self.assertRaises(q.QualificationError): q._evaluate_at(p,self.a,NOW)
 def test_cli_no_clock_override_and_exclusive_output(self):
  tool=self.h/"qualification.py"; helptext=subprocess.run([sys.executable,str(tool),"compile","--help"],capture_output=True,text=True).stdout; self.assertNotIn("current-time",helptext)
  with tempfile.TemporaryDirectory() as td:
   out=Path(td)/"r.json"; cmd=[sys.executable,str(tool),"compile","--input",str(self.h/"current_qualification.json"),"--authority",str(self.h/"trusted_authority.json"),"--output",str(out)]; subprocess.run(cmd,check=True); subprocess.run([sys.executable,str(tool),"verify","--input",str(self.h/"current_qualification.json"),"--authority",str(self.h/"trusted_authority.json"),"--receipt",str(out)],check=True); self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
 @unittest.skipUnless(hasattr(os,"symlink"),"symlink unsupported")
 def test_symlink_output_refused(self):
  tool=self.h/"qualification.py"
  with tempfile.TemporaryDirectory() as td:
   target=Path(td)/"t"; target.write_text("sentinel"); out=Path(td)/"r"; os.symlink(target,out); cmd=[sys.executable,str(tool),"compile","--input",str(self.h/"current_qualification.json"),"--authority",str(self.h/"trusted_authority.json"),"--output",str(out)]; self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0); self.assertEqual(target.read_text(),"sentinel")
if __name__=="__main__": unittest.main()
