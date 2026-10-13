import hashlib,json,subprocess,sys,tempfile,unittest
from pathlib import Path
import launch_ops
P={"sku":"TEST-001","name":"Test Product","description":"Operator supplied.","price_cents":2500,"currency":"USD","stock":4,"reorder_at":2,"shipping_terms":"Ships after staff confirmation.","return_days":21,"support_contact":"support@example.invalid","attributes":{"material":"canvas","size":"medium"},"benefits":["Benefit one.","Benefit two."],"creative_constraints":["Do not claim waterproofing."],"channels":["web","marketplace"]}
class T(unittest.TestCase):
 def setUp(self): self.t=tempfile.TemporaryDirectory(); self.addCleanup(self.t.cleanup); self.root=Path(self.t.name); self.out=self.root/"pack"
 def b(self,p=None): return launch_ops.build(p or P,self.out)
 def state(self): return json.loads((self.out/"state.json").read_text())
 def test_source_fields_preserved(self):
  self.b(); ls=json.loads((self.out/"listings.json").read_text())["listings"]
  for c in P["channels"]:
   for k in ("sku","name","description","price_cents","currency","shipping_terms","return_days","attributes","benefits"): self.assertEqual(P[k],ls[c][k])
 def test_unsent_inventory_consistent(self):
  self.b(); h=json.loads((self.out/"inventory_handoff.json").read_text()); self.assertEqual(4,h["source_available"]); self.assertTrue(all(v=={"available":4,"publication":"NOT_SENT"} for v in h["channels"].values()))
 def test_claim_restraint(self):
  self.b(); b=(self.out/"creative_brief.md").read_text(); self.assertIn("Do not claim waterproofing.",b); self.assertIn("Do not invent performance, health, safety",b); self.assertNotIn("clinically",b.lower())
 def test_missing_and_duplicate_channel_rejected(self):
  p=dict(P); p.pop("shipping_terms")
  with self.assertRaises(launch_ops.LaunchError): self.b(p)
  p=dict(P); p["channels"]=["web","web"]
  with self.assertRaises(launch_ops.LaunchError): self.b(p)
 def test_manifest_hashes(self):
  m=self.b()
  for n,h in m["files"].items(): self.assertEqual(h,hashlib.sha256((self.out/n).read_bytes()).hexdigest())
 def test_order_and_reorder(self):
  self.b(); r=launch_ops.order(self.out/"state.json","O1",2); self.assertEqual(2,self.state()["available"]); self.assertTrue(r["inventory"]["reorder_needed"]); self.assertTrue(all(v["available"]==2 for v in self.state()["channels"].values()))
 def test_order_retry_idempotent_and_conflict(self):
  self.b(); launch_ops.order(self.out/"state.json","O1",1); self.assertTrue(launch_ops.order(self.out/"state.json","O1",1)["idempotent"]); self.assertEqual(3,self.state()["available"])
  with self.assertRaises(launch_ops.LaunchError): launch_ops.order(self.out/"state.json","O1",2)
 def test_oversell_no_change(self):
  self.b(); before=(self.out/"state.json").read_bytes()
  with self.assertRaises(launch_ops.LaunchError): launch_ops.order(self.out/"state.json","O1",5)
  self.assertEqual(before,(self.out/"state.json").read_bytes())
 def test_restock_return_idempotent(self):
  self.b(); launch_ops.order(self.out/"state.json","O1",2); self.assertFalse(launch_ops.ret(self.out/"state.json","O1","R1","restock")["idempotent"]); self.assertTrue(launch_ops.ret(self.out/"state.json","O1","R1","restock")["idempotent"]); self.assertEqual(4,self.state()["available"]); self.assertEqual(2,len(self.state()["events"]))
 def test_hold_and_second_return(self):
  self.b(); launch_ops.order(self.out/"state.json","O1",1); launch_ops.ret(self.out/"state.json","O1","R1","hold"); self.assertEqual(3,self.state()["available"])
  with self.assertRaises(launch_ops.LaunchError): launch_ops.ret(self.out/"state.json","O1","R2","restock")
 def test_unknown_order_return_rejected(self):
  self.b()
  with self.assertRaises(launch_ops.LaunchError): launch_ops.ret(self.out/"state.json","NO","R1","restock")
 def test_cli_round_trip(self):
  f=self.root/"p.json"; f.write_text(json.dumps(P)); s=Path(launch_ops.__file__).resolve()
  for cmd in ([sys.executable,str(s),"build",str(f),"--out",str(self.out)],[sys.executable,str(s),"order","--state",str(self.out/"state.json"),"--order-id","C1","--quantity","1"],[sys.executable,str(s),"return","--state",str(self.out/"state.json"),"--order-id","C1","--return-id","CR1","--disposition","restock"]): self.assertEqual(0,subprocess.run(cmd,capture_output=True).returncode)
  self.assertEqual(4,self.state()["available"])
 def test_rebuild_after_state_preserves_bytes(self):
  """Regression: second build into existing managed workspace must fail closed and leave state untouched."""
  self.b()
  launch_ops.order(self.out/"state.json","O1",2)
  before = (self.out/"state.json").read_bytes()
  with self.assertRaises(launch_ops.LaunchError) as cm:
    launch_ops.build(P, self.out)
  self.assertIn("managed launch workspace", str(cm.exception))
  self.assertEqual(before, (self.out/"state.json").read_bytes())
  self.assertEqual(2, self.state()["available"])
 def test_fresh_empty_dir_build_succeeds(self):
  empty = self.root / "empty"
  empty.mkdir()
  launch_ops.build(P, empty)
  self.assertTrue((empty / "state.json").is_file())
  self.assertEqual(4, json.loads((empty / "state.json").read_text())["available"])
 def test_nan_attribute_rejected(self):
  p = dict(P)
  p["attributes"] = dict(P["attributes"])
  p["attributes"]["bad"] = float("nan")
  with self.assertRaises(launch_ops.LaunchError) as cm:
    self.b(p)
  self.assertIn("non-finite", str(cm.exception).lower())
if __name__=="__main__": unittest.main()
