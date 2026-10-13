from __future__ import annotations
import copy, hashlib, inspect, json, os, tempfile, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from revenue.multi_framework_evidence_freshness.golden import GOLDEN_CORPUS_SHA256, build_golden_input, golden_corpus_sha256
from revenue.multi_framework_evidence_freshness.gate import GateError, _compile_packet_at, _verify_integrity, _verify_packet_at, compile_packet, load_strict_json, render_markdown
AS_OF=datetime(2026,9,13,14,0,0,tzinfo=timezone.utc)
class FreshnessGateTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls): cls.raw=build_golden_input()
 def _one(self,eid):
  raw=copy.deepcopy(self.raw); raw["evidence"]=[copy.deepcopy(next(r for r in raw["evidence"] if r["evidence_id"]==eid))]; return raw
 def test_golden_hash(self): self.assertEqual(golden_corpus_sha256(),GOLDEN_CORPUS_SHA256)
 def test_golden_counts(self):
  p=_compile_packet_at(self.raw,AS_OF); self.assertEqual(p["counts"],{"REUSABLE":240,"STALE":50,"SCOPE_MISMATCH":40,"MISSING_OWNER":35,"INCOMPLETE":35})
  for row in p["results"]:
   self.assertIn("source_ref",row["source_trace"]); self.assertEqual(set(row["source_trace"]["fields"]),{"owner","collection_time","assessment_period_coverage","framework_control_mapping","checksum","freshness_rule"})
 def test_compile_public_has_no_clock_override(self):
  self.assertEqual(list(inspect.signature(compile_packet).parameters),["raw"])
 def test_future_coverage_incomplete(self):
  raw=self._one("REUSE-000"); raw["evidence"][0]["coverage_end"]="2026-09-14T00:00:00Z"
  p=_compile_packet_at(raw,AS_OF); self.assertEqual(p["results"][0]["state"],"INCOMPLETE"); self.assertIn("FUTURE_COVERAGE",p["results"][0]["reasons"])
 def test_coverage_after_collection_incomplete(self):
  raw=self._one("REUSE-000"); raw["evidence"][0]["coverage_end"]="2026-09-01T12:00:01Z"
  p=_compile_packet_at(raw,AS_OF); self.assertEqual(p["results"][0]["state"],"INCOMPLETE")
 def test_future_collection_incomplete(self):
  raw=self._one("REUSE-000"); raw["evidence"][0]["collected_at"]="2026-09-13T14:00:01Z"
  result=_compile_packet_at(raw,AS_OF)["results"][0]; self.assertEqual(result["state"],"INCOMPLETE"); self.assertIn("FUTURE_COLLECTION",result["reasons"])
 def test_current_verifier_rejects_future_packet(self):
  future=AS_OF+timedelta(days=1); packet=_compile_packet_at(self._one("REUSE-000"),future)
  with self.assertRaisesRegex(GateError,"future_evaluation"): _verify_packet_at(packet,AS_OF)
 def test_current_verifier_rejects_fresh_to_stale(self):
  raw=self._one("REUSE-000"); raw["freshness_policy"]["max_age_days"]=1
  packet=_compile_packet_at(raw,datetime(2026,9,1,12,0,0,tzinfo=timezone.utc)); self.assertTrue(_verify_integrity(packet))
  with self.assertRaisesRegex(GateError,"not_current"): _verify_packet_at(packet,datetime(2026,9,3,12,0,1,tzinfo=timezone.utc))
 def test_integrity_replay_still_deterministic(self): self.assertTrue(_verify_integrity(_compile_packet_at(self.raw,AS_OF)))
 def test_input_order_invariance(self):
  altered=copy.deepcopy(self.raw); altered["evidence"]=list(reversed(altered["evidence"])); altered["assessment"]["scope"]=list(reversed(altered["assessment"]["scope"]))
  self.assertEqual(_compile_packet_at(self.raw,AS_OF),_compile_packet_at(altered,AS_OF))
 def test_stale_boundary(self):
  raw=self._one("REUSE-000"); raw["freshness_policy"]["max_age_days"]=30; raw["evidence"][0]["collected_at"]="2026-08-14T14:00:00Z"; self.assertEqual(_compile_packet_at(raw,AS_OF)["results"][0]["state"],"REUSABLE"); raw["evidence"][0]["collected_at"]="2026-08-14T13:59:59Z"; self.assertEqual(_compile_packet_at(raw,AS_OF)["results"][0]["state"],"STALE")
 def test_missing_owner_precedence(self):
  raw=self._one("REUSE-000"); raw["evidence"][0]["owner_ref"]=""; self.assertEqual(_compile_packet_at(raw,AS_OF)["results"][0]["state"],"MISSING_OWNER")
 def test_scope_mismatch(self):
  raw=self._one("REUSE-000"); raw["evidence"][0]["mappings"]=[{"framework":"SOC2","control":"OUTSIDE"}]; self.assertEqual(_compile_packet_at(raw,AS_OF)["results"][0]["state"],"SCOPE_MISMATCH")
 def test_duplicate_id_rejected(self):
  raw=self._one("REUSE-000"); raw["evidence"].append(copy.deepcopy(raw["evidence"][0]));
  with self.assertRaises(GateError): _compile_packet_at(raw,AS_OF)
 def test_bool_max_age_rejected(self):
  raw=self._one("REUSE-000"); raw["freshness_policy"]["max_age_days"]=True
  with self.assertRaises(GateError): _compile_packet_at(raw,AS_OF)
 def test_receipt_tamper(self):
  packet=_compile_packet_at(self.raw,AS_OF); packet["counts"]["REUSABLE"]-=1
  with self.assertRaises(GateError): _verify_integrity(packet)
 def test_markdown_commitment(self):
  p=_compile_packet_at(self.raw,AS_OF); md=render_markdown(p); self.assertEqual(hashlib.sha256(md.encode()).hexdigest(),p["markdown_sha256"]); self.assertNotEqual(hashlib.sha256((md+"tamper").encode()).hexdigest(),p["markdown_sha256"])
 def test_authority_false(self): self.assertTrue(all(v is False for v in _compile_packet_at(self.raw,AS_OF)["authority"].values()))
 def test_duplicate_json_key_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/"x.json"; p.write_text('{"a":1,"a":2}')
   with self.assertRaises(GateError): load_strict_json(p)
 def test_symlink_input_rejected(self):
  if not hasattr(os,"symlink"): self.skipTest("no symlink")
  with tempfile.TemporaryDirectory() as td:
   real=Path(td)/"real.json"; link=Path(td)/"link.json"; real.write_text('{}'); os.symlink(real,link)
   with self.assertRaises((GateError,OSError)): load_strict_json(link)
 def test_fifo_input_rejected_without_read(self):
  if not hasattr(os,"mkfifo"): self.skipTest("no fifo")
  with tempfile.TemporaryDirectory() as td:
   fifo=Path(td)/"x"; os.mkfifo(fifo)
   with self.assertRaises(GateError): load_strict_json(fifo)
 def test_oversize_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/"x"; p.write_bytes(b"x"*33)
   with self.assertRaisesRegex(GateError,"input_too_large"): load_strict_json(p,max_bytes=32)
 def test_nonfinite_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/"x"; p.write_text('{"x":NaN}')
   with self.assertRaises(GateError): load_strict_json(p)
 def test_missing_checksum_is_incomplete(self):
  raw=self._one("REUSE-000"); raw["evidence"][0]["checksum_sha256"]=""; self.assertEqual(_compile_packet_at(raw,AS_OF)["results"][0]["state"],"INCOMPLETE")
 def test_missing_mapping_is_incomplete(self):
  raw=self._one("REUSE-000"); raw["evidence"][0]["mappings"]=[]; self.assertEqual(_compile_packet_at(raw,AS_OF)["results"][0]["state"],"INCOMPLETE")
 def test_wrong_freshness_rule_is_incomplete(self):
  raw=self._one("REUSE-000"); raw["evidence"][0]["freshness_rule_id"]="freshness-v2"; p=_compile_packet_at(raw,AS_OF); self.assertEqual(p["results"][0]["state"],"INCOMPLETE"); self.assertIn("FRESHNESS_RULE_MISMATCH",p["results"][0]["reasons"])
 def test_period_coverage_mismatch(self):
  raw=self._one("REUSE-000"); raw["evidence"][0]["coverage_start"]="2026-02-01T00:00:00Z"; self.assertEqual(_compile_packet_at(raw,AS_OF)["results"][0]["state"],"SCOPE_MISMATCH")
 def test_unknown_key_rejected(self):
  raw=self._one("REUSE-000"); raw["evidence"][0]["surprise"]=1
  with self.assertRaises(GateError): _compile_packet_at(raw,AS_OF)
 def test_secret_shaped_ref_rejected(self):
  raw=self._one("REUSE-000"); raw["evidence"][0]["source_ref"]="token=abc"
  with self.assertRaises(GateError): _compile_packet_at(raw,AS_OF)
 def test_three_run_hash_stability(self):
  packets=[_compile_packet_at(copy.deepcopy(self.raw),AS_OF) for _ in range(3)]; self.assertEqual(len({p["receipt_sha256"] for p in packets}),1); self.assertEqual(len({hashlib.sha256(json.dumps(p,sort_keys=True,separators=(",",":")).encode()).hexdigest() for p in packets}),1)
 def test_zero_reusable_without_required_semantics(self):
  p=_compile_packet_at(self.raw,AS_OF); rows={r["evidence_id"]:r for r in p["input"]["evidence"]}; scope={(x["framework"],x["control"]) for x in p["input"]["assessment"]["scope"]}
  for result in p["results"]:
   if result["state"]!="REUSABLE": continue
   row=rows[result["evidence_id"]]; self.assertTrue(row["owner_ref"] and row["checksum_sha256"] and row["source_ref"] and row["mappings"]); self.assertEqual(row["freshness_rule_id"],p["input"]["freshness_policy"]["rule_id"]); self.assertLessEqual(row["coverage_start"],p["input"]["assessment"]["period_start"]); self.assertGreaterEqual(row["coverage_end"],p["input"]["assessment"]["period_end"]); self.assertLessEqual(row["coverage_end"],row["collected_at"]); self.assertTrue({(m["framework"],m["control"]) for m in row["mappings"]}.issubset(scope))
 def test_output_create_exclusive_and_symlink_parent(self):
  from revenue.multi_framework_evidence_freshness.cli import _write_new
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); out=root/"packet"; _write_new(out,b"abc"); self.assertEqual(out.read_bytes(),b"abc")
   with self.assertRaises(OSError): _write_new(out,b"def")
   real=root/"real"; real.mkdir(); link=root/"link"; os.symlink(real,link)
   with self.assertRaises((OSError,GateError)): _write_new(link/"x",b"x")
 def test_cli_preflights_both_outputs_before_publication(self):
  from revenue.multi_framework_evidence_freshness.cli import main
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); src=root/"input.json"; pkt=root/"packet.json"; md=root/"review.md"; src.write_text(json.dumps(self.raw)); md.write_text("occupied")
   self.assertEqual(main(["compile",str(src),str(pkt),str(md)]),2); self.assertFalse(pkt.exists()); self.assertEqual(md.read_text(),"occupied")
 def test_cli_preflight_rejects_dangling_symlink(self):
  if not hasattr(os,"symlink"): self.skipTest("no symlink")
  from revenue.multi_framework_evidence_freshness.cli import main
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); src=root/"input.json"; pkt=root/"packet.json"; md=root/"review.md"; src.write_text(json.dumps(self.raw)); os.symlink(root/"missing",md)
   self.assertEqual(main(["compile",str(src),str(pkt),str(md)]),2); self.assertFalse(pkt.exists())
 def test_cli_current_compile_verify(self):
  from revenue.multi_framework_evidence_freshness.cli import main
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); src=root/"input.json"; pkt=root/"packet.json"; md=root/"review.md"; src.write_text(json.dumps(self.raw))
   self.assertEqual(main(["compile",str(src),str(pkt),str(md)]),0); self.assertTrue(pkt.exists() and md.exists()); self.assertEqual(main(["verify",str(pkt)]),0)

if __name__=="__main__": unittest.main()
