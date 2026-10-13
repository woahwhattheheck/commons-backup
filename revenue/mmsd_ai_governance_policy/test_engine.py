import copy
import unittest

from revenue.mmsd_ai_governance_policy.engine import (
    GovernanceError,
    compile_report,
    strict_json_loads,
    verify_report,
)

H = "1" * 64
V = "2" * 64


def system(**kw):
    row = dict(
        system_id="sys-1", system_kind="GENERATIVE", deployment="INTERNAL", data_class="PUBLIC",
        external_processing="NO", provider_training="NO", physical_influence="NONE", human_override="YES",
        monitoring="YES", validation_evidence_sha256=V, public_records_status="APPLIES", retention_status="DEFINED",
        vendor_change_notice="YES", incident_plan="YES", manual_fallback="YES", evidence_sha256=H,
    )
    row.update(kw)
    return row


def packet(*rows):
    return {"schema":"commons-ai-governance-inventory/v1","inventory_id":"inv","inventory_generation":1,"systems":list(rows)}


class GovernanceTests(unittest.TestCase):
    def test_baseline_is_relative_not_inventory_ready(self):
        r=compile_report(packet(system()))
        self.assertEqual(r["state"],"SUPPLIED_ROWS_ANALYZED")
        self.assertEqual(r["inventory_scope"],"CALLER_SUPPLIED_ROWS_ONLY")
        self.assertEqual(r["inventory_completeness"],"NOT_ASSERTED_BY_ENGINE")
        self.assertEqual(r["systems"][0]["review_state"],"SUPPLIED_ROW_ANALYZED")

    def test_report_schema_bumped_for_scope_semantics(self):
        self.assertEqual(compile_report(packet(system()))["schema"], "commons-ai-governance-report/v2")

    def test_deterministic(self):
        p=packet(system(system_id="b"),system(system_id="a")); self.assertEqual(compile_report(p),compile_report(copy.deepcopy(p)))
    def test_order_invariant(self):
        a=system(system_id="a"); b=system(system_id="b"); self.assertEqual(compile_report(packet(a,b))["receipt_sha256"],compile_report(packet(b,a))["receipt_sha256"])
    def test_exact_replay_collapses(self):
        r=compile_report(packet(system(),system())); self.assertEqual(r["systems"][0]["occurrences"],2)
    def test_changed_same_id_conflicts(self):
        r=compile_report(packet(system(),system(data_class="INTERNAL"))); self.assertEqual(r["state"],"HOLD_CONFLICT")
    def test_conflict_order_invariant(self):
        a=system(); b=system(data_class="INTERNAL"); self.assertEqual(compile_report(packet(a,b)),compile_report(packet(b,a)))
    def test_public_records_unknown_holds(self):
        r=compile_report(packet(system(public_records_status="UNKNOWN"))); self.assertIn("PUBLIC_RECORDS_STATUS_UNKNOWN",r["systems"][0]["holds"])
    def test_retention_unknown_holds(self):
        r=compile_report(packet(system(retention_status="UNKNOWN"))); self.assertIn("RETENTION_NOT_DEFINED",r["systems"][0]["holds"])
    def test_retention_undefined_holds(self):
        r=compile_report(packet(system(retention_status="UNDEFINED"))); self.assertIn("RETENTION_NOT_DEFINED",r["systems"][0]["holds"])
    def test_confidential_external_risk(self):
        r=compile_report(packet(system(data_class="CONFIDENTIAL",external_processing="YES"))); self.assertGreaterEqual(r["systems"][0]["information_risk"],3)
    def test_restricted_training_is_max(self):
        r=compile_report(packet(system(data_class="RESTRICTED",external_processing="YES",provider_training="YES"))); self.assertEqual(r["systems"][0]["information_risk"],4)
    def test_unknown_data_max(self):
        r=compile_report(packet(system(data_class="UNKNOWN"))); self.assertEqual(r["systems"][0]["information_risk"],4)
    def test_operational_recommendation_high(self):
        r=compile_report(packet(system(system_kind="OPERATIONAL_AI",deployment="OPERATIONAL_OT",physical_influence="RECOMMENDATION"))); self.assertEqual(r["systems"][0]["operational_risk"],3)
    def test_operational_automatic_max(self):
        r=compile_report(packet(system(system_kind="OPERATIONAL_AI",deployment="OPERATIONAL_OT",physical_influence="AUTOMATIC"))); self.assertEqual(r["systems"][0]["operational_risk"],4)
    def test_operational_missing_override_holds(self):
        r=compile_report(packet(system(system_kind="OPERATIONAL_AI",deployment="OPERATIONAL_OT",physical_influence="RECOMMENDATION",human_override="NO"))); self.assertIn("HUMAN_OVERRIDE_NOT_EVIDENCED",r["systems"][0]["holds"])
    def test_operational_missing_fallback_holds(self):
        r=compile_report(packet(system(system_kind="OPERATIONAL_AI",deployment="OPERATIONAL_OT",physical_influence="RECOMMENDATION",manual_fallback="UNKNOWN"))); self.assertIn("MANUAL_FALLBACK_NOT_EVIDENCED",r["systems"][0]["holds"])
    def test_high_missing_monitoring_holds(self):
        r=compile_report(packet(system(data_class="CONFIDENTIAL",monitoring="NO"))); self.assertIn("MONITORING_NOT_EVIDENCED",r["systems"][0]["holds"])
    def test_high_missing_incident_plan_holds(self):
        r=compile_report(packet(system(data_class="CONFIDENTIAL",incident_plan="NO"))); self.assertIn("INCIDENT_PLAN_NOT_EVIDENCED",r["systems"][0]["holds"])
    def test_high_missing_validation_holds(self):
        r=compile_report(packet(system(data_class="CONFIDENTIAL",validation_evidence_sha256=None))); self.assertIn("VALIDATION_EVIDENCE_MISSING",r["systems"][0]["holds"])
    def test_embedded_vendor_change_holds(self):
        r=compile_report(packet(system(deployment="PROCURED_EMBEDDED",data_class="CONFIDENTIAL",vendor_change_notice="UNKNOWN"))); self.assertIn("VENDOR_CHANGE_NOTICE_NOT_EVIDENCED",r["systems"][0]["holds"])
    def test_unknown_provider_training_holds(self):
        r=compile_report(packet(system(external_processing="YES",provider_training="UNKNOWN"))); self.assertIn("PROVIDER_TRAINING_STATUS_UNKNOWN",r["systems"][0]["holds"])
    def test_unknown_physical_influence_holds(self):
        r=compile_report(packet(system(physical_influence="UNKNOWN"))); self.assertIn("PHYSICAL_INFLUENCE_UNKNOWN",r["systems"][0]["holds"])
    def test_high_controls_include_safety(self):
        r=compile_report(packet(system(system_kind="OPERATIONAL_AI",deployment="OPERATIONAL_OT",physical_influence="AUTOMATIC"))); self.assertIn("OPERATIONAL_SAFETY_REVIEW",r["systems"][0]["required_controls"])
    def test_genai_not_physical(self):
        r=compile_report(packet(system())); self.assertEqual(r["systems"][0]["operational_risk"],1)
    def test_agentic_nonphysical_still_elevated(self):
        r=compile_report(packet(system(system_kind="AGENTIC"))); self.assertEqual(r["systems"][0]["operational_risk"],2)
    def test_no_external_authority(self):
        r=compile_report(packet(system())); self.assertFalse(r["external_action_authorized"]); self.assertFalse(r["operational_release_authorized"])
    def test_no_legal_authority(self):
        self.assertFalse(compile_report(packet(system()))["legal_conclusion_authorized"])
    def test_no_vendor_approval_authority(self):
        self.assertFalse(compile_report(packet(system()))["vendor_approval_authorized"])
    def test_verify_roundtrip(self):
        p=packet(system()); r=compile_report(p); self.assertTrue(verify_report(p,r))
    def test_verify_tamper_fails(self):
        p=packet(system()); r=compile_report(p); r["state"]="HOLD"; self.assertFalse(verify_report(p,r))
    def test_verify_reseal_semantic_tamper_fails(self):
        from revenue.mmsd_ai_governance_policy.engine import canonical_bytes, sha256
        p=packet(system()); r=compile_report(p); r["systems"][0]["overall_risk"]=4; r["receipt_sha256"]=sha256(canonical_bytes({k:v for k,v in r.items() if k!="receipt_sha256"})); self.assertFalse(verify_report(p,r))
    def test_packet_extra_key_rejected(self):
        p=packet(system()); p["x"]=1
        with self.assertRaises(GovernanceError): compile_report(p)
    def test_system_missing_key_rejected(self):
        s=system(); del s["monitoring"]
        with self.assertRaises(GovernanceError): compile_report(packet(s))
    def test_system_extra_key_rejected(self):
        s=system(); s["owner_asserted_ready"]=True
        with self.assertRaises(GovernanceError): compile_report(packet(s))
    def test_bool_generation_rejected(self):
        p=packet(system()); p["inventory_generation"]=True
        with self.assertRaises(GovernanceError): compile_report(p)
    def test_bad_digest_rejected(self):
        with self.assertRaises(GovernanceError): compile_report(packet(system(evidence_sha256="bad")))
    def test_uppercase_digest_rejected(self):
        with self.assertRaises(GovernanceError): compile_report(packet(system(evidence_sha256="A"*64)))
    def test_bad_enum_rejected(self):
        with self.assertRaises(GovernanceError): compile_report(packet(system(system_kind="genai")))
    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(GovernanceError): strict_json_loads('{"a":1,"a":2}')
    def test_nonfinite_json_rejected(self):
        with self.assertRaises(GovernanceError): strict_json_loads('{"a":NaN}')
    def test_float_rejected(self):
        p=packet(system()); p["inventory_generation"]=1.0
        with self.assertRaises(GovernanceError): compile_report(p)
    def test_unsupported_nested_type_rejected(self):
        p=packet(system()); p["systems"][0]["evidence_sha256"]=bytearray(b"x")
        with self.assertRaises(GovernanceError): compile_report(p)

    def test_empty_inventory_is_not_positive_ready(self):
        r=compile_report(packet())
        self.assertEqual(r["state"],"NO_SYSTEMS_SUPPLIED")
        self.assertEqual(r["inventory_completeness"],"NOT_ASSERTED_BY_ENGINE")

    def test_omitting_hold_row_cannot_mint_whole_inventory_ready(self):
        high=system(system_id="critical", physical_influence="UNKNOWN")
        safe=system(system_id="safe")
        full=compile_report(packet(high, safe))
        subset=compile_report(packet(safe))
        self.assertEqual(full["state"], "HOLD_SUPPLIED_ROWS")
        self.assertEqual(subset["state"], "SUPPLIED_ROWS_ANALYZED")
        self.assertNotIn("READY", subset["state"])
        self.assertEqual(subset["inventory_scope"], "CALLER_SUPPLIED_ROWS_ONLY")
        self.assertEqual(subset["inventory_completeness"], "NOT_ASSERTED_BY_ENGINE")
        self.assertNotEqual(full["normalized_input_sha256"], subset["normalized_input_sha256"])

    def test_no_report_level_ready_vocabulary(self):
        r=compile_report(packet(system()))
        self.assertNotIn("READY", r["state"])
        self.assertNotIn("READY", r["systems"][0]["review_state"])

    def test_generation_label_is_bound_but_not_completeness_authority(self):
        p1=packet(system()); p2=copy.deepcopy(p1); p2["inventory_generation"]=2
        r1=compile_report(p1); r2=compile_report(p2)
        self.assertNotEqual(r1["normalized_input_sha256"], r2["normalized_input_sha256"])
        self.assertEqual(r1["inventory_completeness"], "NOT_ASSERTED_BY_ENGINE")
        self.assertEqual(r2["inventory_completeness"], "NOT_ASSERTED_BY_ENGINE")

    def test_bound_inventory(self):
        p=packet(); p["systems"]=[system(system_id=f"s{i}") for i in range(5001)]
        with self.assertRaises(GovernanceError): compile_report(p)
    def test_system_id_ascii_guard(self):
        with self.assertRaises(GovernanceError): compile_report(packet(system(system_id="bad\n")))
    def test_information_and_ops_axes_are_independent(self):
        r=compile_report(packet(system(data_class="RESTRICTED",physical_influence="NONE")))["systems"][0]
        self.assertEqual(r["information_risk"],3); self.assertEqual(r["operational_risk"],1)


if __name__ == "__main__": unittest.main()
