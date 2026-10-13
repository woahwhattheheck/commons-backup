from __future__ import annotations
import copy
import json
import unittest
from revenue.mcp_cross_client_conformance.acceptance import CLIENTS, TOOLS, acceptance_result, base_observation, make_acceptance, make_manifest
from revenue.mcp_cross_client_conformance.kernel import ConformanceError, assess_observation, canonical_bytes, evaluate, evaluate_text, loads_strict, verify_report

class StrictJsonTests(unittest.TestCase):
    def test_duplicate_key_rejected(self):
        with self.assertRaisesRegex(ConformanceError, "DUPLICATE_KEY"): loads_strict('{"a":1,"a":2}')
    def test_float_rejected(self):
        with self.assertRaisesRegex(ConformanceError, "FLOATS_NOT_ALLOWED"): loads_strict('{"a":1.5}')
    def test_nonfinite_rejected(self):
        with self.assertRaisesRegex(ConformanceError, "NONFINITE_NUMBER"): loads_strict('{"a":NaN}')
    def test_canonical_is_order_invariant(self):
        self.assertEqual(canonical_bytes({"b":2,"a":1}), canonical_bytes({"a":1,"b":2}))

class ManifestTests(unittest.TestCase):
    def test_zero_action_limit_is_mandatory(self):
        manifest=make_manifest(); manifest["production_action_limit"]=1
        with self.assertRaisesRegex(ConformanceError,"MUST_BE_ZERO"): evaluate(manifest,[])
    def test_duplicate_client_rejected(self):
        manifest=make_manifest(); manifest["clients"].append(manifest["clients"][0])
        with self.assertRaisesRegex(ConformanceError,"DUPLICATE_LIST_VALUE"): evaluate(manifest,[])
    def test_duplicate_resource_rejected(self):
        manifest=make_manifest(); manifest["resources"].append(copy.deepcopy(manifest["resources"][0]))
        with self.assertRaisesRegex(ConformanceError,"DUPLICATE_RESOURCE"): evaluate(manifest,[])

class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.manifest=make_manifest(); self.clean=base_observation(self.manifest,CLIENTS[0],"clean-x")
    def test_clean_passes(self):
        a=assess_observation(self.manifest,self.clean); self.assertEqual("PASS",a["disposition"]); self.assertEqual([],a["reasons"])
    def test_missing_tool_holds(self):
        o=copy.deepcopy(self.clean); o["listed_tools"]=TOOLS[:-1]; a=assess_observation(self.manifest,o); self.assertEqual("HOLD",a["disposition"]); self.assertTrue(any(r.startswith("MISSING_TOOLS") for r in a["reasons"]))
    def test_extra_tool_holds(self):
        o=copy.deepcopy(self.clean); o["listed_tools"]=TOOLS+["mutateCluster"]; a=assess_observation(self.manifest,o); self.assertEqual("HOLD",a["disposition"]); self.assertTrue(any(r.startswith("UNEXPECTED_TOOLS") for r in a["reasons"]))
    def test_unreachable_is_unverified_not_zero(self):
        o=copy.deepcopy(self.clean); o["listing_status"]="UNREACHABLE"; o["listed_tools"]=[]; o["resource_hashes"]={}; a=assess_observation(self.manifest,o); self.assertEqual("UNVERIFIED",a["disposition"]); self.assertIn("LISTING_UNREACHABLE",a["reasons"])
    def test_silent_downgrade_rejected(self):
        o=copy.deepcopy(self.clean); o["requested_protocol_version"]="2026-03-26"; o["negotiation_status"]="DOWNGRADED"; self.assertEqual("REJECT",assess_observation(self.manifest,o)["disposition"])
    def test_unsupported_protocol_acceptance_holds(self):
        o=copy.deepcopy(self.clean); o["requested_protocol_version"]="1900-01-01"; o["negotiated_protocol_version"]="1900-01-01"; a=assess_observation(self.manifest,o); self.assertEqual("HOLD",a["disposition"]); self.assertIn("UNSUPPORTED_PROTOCOL_ACCEPTED",a["reasons"])
    def test_resource_hash_drift_holds(self):
        o=copy.deepcopy(self.clean); o["resource_hashes"]["schema:vm.list"]="f"*64; a=assess_observation(self.manifest,o); self.assertEqual("HOLD",a["disposition"]); self.assertIn("RESOURCE_HASH_MISMATCH:schema:vm.list",a["reasons"])
    def test_unknown_resource_holds(self):
        o=copy.deepcopy(self.clean); o["resource_hashes"]["schema:unknown"]="f"*64; a=assess_observation(self.manifest,o); self.assertEqual("HOLD",a["disposition"]); self.assertTrue(any(r.startswith("UNEXPECTED_RESOURCES") for r in a["reasons"]))
    def test_wrong_server_build_holds(self):
        o=copy.deepcopy(self.clean); o["server_build"]="wrong"; a=assess_observation(self.manifest,o); self.assertEqual("HOLD",a["disposition"]); self.assertIn("SERVER_BUILD_MISMATCH",a["reasons"])
    def test_wrong_fixture_holds(self):
        o=copy.deepcopy(self.clean); o["fixture_sha256"]="f"*64; a=assess_observation(self.manifest,o); self.assertEqual("HOLD",a["disposition"]); self.assertIn("FIXTURE_MISMATCH",a["reasons"])
    def test_production_action_holds(self):
        o=copy.deepcopy(self.clean); o["production_action_count"]=1; a=assess_observation(self.manifest,o); self.assertEqual("HOLD",a["disposition"]); self.assertIn("PRODUCTION_ACTION_OBSERVED",a["reasons"])

class EvaluationTests(unittest.TestCase):
    def test_acceptance_fixture_passes(self):
        r=acceptance_result(); self.assertTrue(r["verified"]); self.assertEqual("PASS",r["report"]["overall"]); self.assertEqual(5,r["report"]["client_count"]); self.assertEqual(16,r["report"]["unique_observation_count"]); self.assertEqual([],r["report"]["global_reasons"])
    def test_order_invariant_report(self):
        m,o=make_acceptance(); self.assertEqual(evaluate(m,o),evaluate(m,list(reversed(o))))
    def test_exact_duplicate_collapses(self):
        m,o=make_acceptance(); o.append(copy.deepcopy(o[0])); r=evaluate(m,o); self.assertEqual("PASS",r["overall"]); self.assertEqual(1,r["duplicate_collapses"])
    def test_same_id_changed_payload_rejected(self):
        m,o=make_acceptance(); changed=copy.deepcopy(o[0]); changed["listed_tools"]=changed["listed_tools"][:-1]; o.append(changed)
        with self.assertRaisesRegex(ConformanceError,"OBSERVATION_ID_CONFLICT"): evaluate(m,o)
    def test_missing_client_clean_run_holds(self):
        m,o=make_acceptance(); o=[x for x in o if x["client_id"]!=CLIENTS[-1]]; r=evaluate(m,o); self.assertEqual("HOLD",r["overall"]); self.assertTrue(any(x.startswith(f"CLEAN_RUN_COUNT:{CLIENTS[-1]}") for x in r["global_reasons"]))
    def test_clean_replay_drift_holds(self):
        m,o=make_acceptance(); t=next(x for x in o if x["client_id"]==CLIENTS[1] and x["run_id"]=="clean-2"); t["requested_protocol_version"]="2026-03-26"; t["negotiated_protocol_version"]="2026-03-26"; r=evaluate(m,o); self.assertEqual("HOLD",r["overall"]); self.assertIn(f"CLEAN_REPLAY_DRIFT:{CLIENTS[1]}",r["global_reasons"])
    def test_missing_hostile_case_holds(self):
        m,o=make_acceptance(); o=[x for x in o if x["case"]!="corrupt_binary"]; r=evaluate(m,o); self.assertEqual("HOLD",r["overall"]); self.assertIn("MISSING_HOSTILE_CASE:corrupt_binary",r["global_reasons"])
    def test_hostile_wrong_disposition_holds(self):
        m,o=make_acceptance(); t=next(x for x in o if x["case"]=="omitted_tool"); t["listed_tools"]=list(TOOLS); r=evaluate(m,o); self.assertEqual("HOLD",r["overall"]); self.assertTrue(any(x.startswith("HOSTILE_DISPOSITION:omitted_tool") for x in r["global_reasons"]))
    def _assert_hostile_binding_failure(self, case, field, value, reason):
        m,o=make_acceptance(); t=next(x for x in o if x["case"]==case); t[field]=value
        assessment=assess_observation(m,t)
        self.assertEqual(m["hostile_expectations"][case],assessment["disposition"])
        self.assertIn(reason,assessment["reasons"])
        r=evaluate(m,o)
        self.assertEqual("HOLD",r["overall"])
        self.assertIn(f"EVIDENCE_BINDING_FAILURE:{t['observation_id']}:{reason}",r["global_reasons"])
    def test_reject_hostile_wrong_server_build_cannot_pass_aggregate(self):
        self._assert_hostile_binding_failure("unsupported_protocol","server_build","wrong-build","SERVER_BUILD_MISMATCH")
    def test_hold_hostile_wrong_fixture_cannot_pass_aggregate(self):
        self._assert_hostile_binding_failure("omitted_tool","fixture_sha256","f"*64,"FIXTURE_MISMATCH")
    def test_unverified_hostile_unknown_client_cannot_pass_aggregate(self):
        self._assert_hostile_binding_failure("unreachable_listing","client_id","unknown-client","UNKNOWN_CLIENT")
    def test_production_action_boundary_fails_report(self):
        m,o=make_acceptance(); o[0]["production_action_count"]=1; r=evaluate(m,o); self.assertEqual("HOLD",r["overall"]); self.assertIn("PRODUCTION_ACTION_BOUNDARY_VIOLATED",r["global_reasons"])
    def test_receipt_tamper_detected(self):
        r=acceptance_result()["report"]; self.assertTrue(verify_report(r)); r=copy.deepcopy(r); r["server_build"]="tampered"; self.assertFalse(verify_report(r))
    def test_text_evaluation_matches_object(self):
        m,o=make_acceptance(); rt=evaluate_text(json.dumps(m,sort_keys=True,separators=(",",":")),json.dumps(o,sort_keys=True,separators=(",",":"))); self.assertEqual(evaluate(m,o),rt)

if __name__=="__main__": unittest.main()
