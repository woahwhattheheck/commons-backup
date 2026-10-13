import copy
import unittest

from policy_assessment import (
    CONTRACT,
    GovernanceError,
    assess_governance,
    loads_strict,
    verify_result,
)

AS_OF = "2026-09-13T10:30:00Z"
EVIDENCE_TIME = "2026-09-13T10:00:00Z"

GEN = {
    "system_id": "gen-draft",
    "name": "Internal drafting assistant",
    "ai_kind": "GENERATIVE",
    "lifecycle": "PILOT",
    "automation_level": "ASSISTIVE",
    "data_classes": ["INTERNAL", "PUBLIC_RECORD"],
    "impact_areas": ["ADMINISTRATIVE"],
    "external_vendor": True,
    "internet_connected": True,
    "can_change_operational_state": False,
    "public_facing_output": False,
    "owner_role": "Communications",
}
OPS = {
    "system_id": "ops-control",
    "name": "Wastewater process optimization",
    "ai_kind": "OPERATIONAL",
    "lifecycle": "PRODUCTION",
    "automation_level": "RECOMMENDATION",
    "data_classes": ["CRITICAL_INFRASTRUCTURE", "SECURITY_SENSITIVE"],
    "impact_areas": ["WASTEWATER_PROCESS", "SAFETY", "INFRASTRUCTURE"],
    "external_vendor": False,
    "internet_connected": False,
    "can_change_operational_state": True,
    "public_facing_output": False,
    "owner_role": "Operations Engineering",
}
LOW = {
    "system_id": "low-internal",
    "name": "Local brainstorming helper",
    "ai_kind": "GENERATIVE",
    "lifecycle": "DISCOVERY",
    "automation_level": "ASSISTIVE",
    "data_classes": ["INTERNAL"],
    "impact_areas": ["ADMINISTRATIVE"],
    "external_vendor": False,
    "internet_connected": False,
    "can_change_operational_state": False,
    "public_facing_output": False,
    "owner_role": "Innovation",
}
ALL_CONTROLS = {
    "named_owner": True,
    "approved_use_case": True,
    "data_classification": True,
    "records_retention": True,
    "records_export": True,
    "vendor_terms_review": True,
    "security_review": True,
    "incident_response": True,
    "logging_monitoring": True,
    "human_oversight": True,
    "output_validation": True,
    "change_management": True,
    "ot_safety_review": True,
    "fail_safe_or_rollback": True,
    "staff_training": True,
    "data_residency_known": True,
}


def root(inventory=None):
    return {
        "contract": CONTRACT,
        "inventory": copy.deepcopy([GEN, OPS] if inventory is None else inventory),
        "control_evidence": [],
    }


def inventory_sha(payload):
    probe = assess_governance(copy.deepcopy(payload), trusted_as_of=AS_OF)
    return probe["inventory_sha256"]


def evidence(sid, inv_sha, *, evidence_id=None, controls=None, captured_at=EVIDENCE_TIME):
    return {
        "system_id": sid,
        "evidence_id": evidence_id or f"evidence-{sid}",
        "captured_at": captured_at,
        "inventory_evidence_sha256": inv_sha,
        "controls": copy.deepcopy(ALL_CONTROLS if controls is None else controls),
    }


def complete_payload(inventory=None):
    p = root(inventory)
    inv = inventory_sha(p)
    p["control_evidence"] = [evidence(item["system_id"], inv) for item in p["inventory"]]
    return p


class GovernanceAssessmentTests(unittest.TestCase):
    def test_complete_portfolio(self):
        result = assess_governance(complete_payload(), trusted_as_of=AS_OF)
        self.assertEqual(result["state"], "ASSESSMENT_COMPLETE")
        self.assertEqual(result["portfolio_summary"]["system_count"], 2)
        self.assertEqual(result["portfolio_summary"]["systems_with_control_gaps"], 0)
        self.assertTrue(verify_result(result))
        self.assertTrue(all(v is False for v in result["authority"].values()))

    def test_deterministic(self):
        p = complete_payload()
        self.assertEqual(
            assess_governance(copy.deepcopy(p), trusted_as_of=AS_OF),
            assess_governance(copy.deepcopy(p), trusted_as_of=AS_OF),
        )

    def test_inventory_order_does_not_change_digest(self):
        self.assertEqual(inventory_sha(root([GEN, OPS])), inventory_sha(root([OPS, GEN])))

    def test_evidence_order_does_not_change_result(self):
        p = complete_payload()
        q = copy.deepcopy(p)
        q["control_evidence"].reverse()
        self.assertEqual(
            assess_governance(p, trusted_as_of=AS_OF),
            assess_governance(q, trusted_as_of=AS_OF),
        )

    def test_low_tier(self):
        result = assess_governance(complete_payload([LOW]), trusted_as_of=AS_OF)
        self.assertEqual(result["systems"][0]["inherent_risk_tier"], "T1_LOW")

    def test_vendor_public_record_is_moderate(self):
        result = assess_governance(complete_payload([GEN]), trusted_as_of=AS_OF)
        self.assertEqual(result["systems"][0]["inherent_risk_tier"], "T2_MODERATE")
        required = result["systems"][0]["required_controls"]
        self.assertIn("vendor_terms_review", required)
        self.assertIn("data_residency_known", required)
        self.assertIn("records_export", required)
        self.assertIn("security_review", required)

    def test_operational_actuation_is_critical(self):
        result = assess_governance(complete_payload([OPS]), trusted_as_of=AS_OF)
        self.assertEqual(result["systems"][0]["inherent_risk_tier"], "T4_CRITICAL")
        self.assertIn("ot_safety_review", result["systems"][0]["required_controls"])
        self.assertIn("fail_safe_or_rollback", result["systems"][0]["required_controls"])

    def test_sensitive_genai_is_high(self):
        x = copy.deepcopy(GEN)
        x["system_id"] = "sensitive-gen"
        x["data_classes"] = ["PERSONAL"]
        x["external_vendor"] = False
        x["internet_connected"] = False
        result = assess_governance(complete_payload([x]), trusted_as_of=AS_OF)
        self.assertEqual(result["systems"][0]["inherent_risk_tier"], "T3_HIGH")

    def test_missing_evidence_is_gap_not_approval(self):
        result = assess_governance(root([GEN]), trusted_as_of=AS_OF)
        self.assertEqual(result["state"], "CONTROL_GAPS_PRESENT")
        self.assertEqual(result["portfolio_summary"]["systems_without_control_evidence"], 1)
        self.assertGreater(len(result["systems"][0]["missing_controls"]), 0)

    def test_false_required_control_is_gap(self):
        p = complete_payload([OPS])
        p["control_evidence"][0]["controls"]["ot_safety_review"] = False
        result = assess_governance(p, trusted_as_of=AS_OF)
        self.assertEqual(result["state"], "CONTROL_GAPS_PRESENT")
        self.assertIn("ot_safety_review", result["systems"][0]["missing_controls"])

    def test_irrelevant_false_control_does_not_create_gap(self):
        p = complete_payload([LOW])
        p["control_evidence"][0]["controls"]["ot_safety_review"] = False
        self.assertEqual(assess_governance(p, trusted_as_of=AS_OF)["state"], "ASSESSMENT_COMPLETE")

    def test_future_evidence_rejected(self):
        p = complete_payload([LOW])
        p["control_evidence"][0]["captured_at"] = "2026-09-14T10:00:00Z"
        with self.assertRaisesRegex(GovernanceError, "future evidence"):
            assess_governance(p, trusted_as_of=AS_OF)

    def test_caller_cannot_smuggle_as_of(self):
        p = complete_payload([LOW])
        p["as_of"] = AS_OF
        with self.assertRaisesRegex(GovernanceError, "schema mismatch"):
            assess_governance(p, trusted_as_of=AS_OF)

    def test_inventory_digest_binding(self):
        p = complete_payload([LOW])
        p["inventory"][0]["name"] = "Changed after evidence"
        with self.assertRaisesRegex(GovernanceError, "inventory digest mismatch"):
            assess_governance(p, trusted_as_of=AS_OF)

    def test_unknown_top_level_field_rejected(self):
        p = complete_payload([LOW])
        p["approved"] = True
        with self.assertRaises(GovernanceError):
            assess_governance(p, trusted_as_of=AS_OF)

    def test_unknown_system_field_rejected(self):
        p = complete_payload([LOW])
        p["inventory"][0]["legal_basis"] = "yes"
        with self.assertRaises(GovernanceError):
            assess_governance(p, trusted_as_of=AS_OF)

    def test_unknown_control_field_rejected(self):
        p = complete_payload([LOW])
        p["control_evidence"][0]["controls"]["auto_approve"] = True
        with self.assertRaises(GovernanceError):
            assess_governance(p, trusted_as_of=AS_OF)

    def test_duplicate_system_rejected(self):
        with self.assertRaisesRegex(GovernanceError, "duplicate system_id"):
            assess_governance(root([LOW, LOW]), trusted_as_of=AS_OF)

    def test_duplicate_evidence_id_rejected(self):
        p = complete_payload([GEN, OPS])
        p["control_evidence"][1]["evidence_id"] = p["control_evidence"][0]["evidence_id"]
        with self.assertRaisesRegex(GovernanceError, "duplicate evidence_id"):
            assess_governance(p, trusted_as_of=AS_OF)

    def test_multiple_evidence_rows_per_system_rejected(self):
        p = complete_payload([LOW])
        duplicate = copy.deepcopy(p["control_evidence"][0])
        duplicate["evidence_id"] = "another-evidence"
        p["control_evidence"].append(duplicate)
        with self.assertRaisesRegex(GovernanceError, "multiple control evidence"):
            assess_governance(p, trusted_as_of=AS_OF)

    def test_unknown_system_evidence_rejected(self):
        p = complete_payload([LOW])
        p["control_evidence"][0]["system_id"] = "not-in-inventory"
        with self.assertRaisesRegex(GovernanceError, "unknown system"):
            assess_governance(p, trusted_as_of=AS_OF)

    def test_bool_not_integer(self):
        p = complete_payload([LOW])
        p["inventory"][0]["external_vendor"] = 1
        with self.assertRaises(GovernanceError):
            assess_governance(p, trusted_as_of=AS_OF)

    def test_float_rejected(self):
        p = complete_payload([LOW])
        p["inventory"][0]["risk_score"] = 1.0
        with self.assertRaises(GovernanceError):
            assess_governance(p, trusted_as_of=AS_OF)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(GovernanceError, "duplicate JSON key"):
            loads_strict('{"a":1,"a":2}')

    def test_nan_json_rejected(self):
        with self.assertRaises(GovernanceError):
            loads_strict('{"a":NaN}')

    def test_secret_api_key_rejected_in_name(self):
        p = root([LOW])
        p["inventory"][0]["name"] = "api_key=supersecretmaterial"
        with self.assertRaisesRegex(GovernanceError, "secret-shaped"):
            assess_governance(p, trusted_as_of=AS_OF)

    def test_bearer_token_rejected_in_owner(self):
        p = root([LOW])
        p["inventory"][0]["owner_role"] = "Bearer abcdefghijklmnop"
        with self.assertRaisesRegex(GovernanceError, "secret-shaped"):
            assess_governance(p, trusted_as_of=AS_OF)

    def test_duplicate_data_class_rejected(self):
        p = root([LOW])
        p["inventory"][0]["data_classes"] = ["INTERNAL", "INTERNAL"]
        with self.assertRaisesRegex(GovernanceError, "duplicate"):
            assess_governance(p, trusted_as_of=AS_OF)

    def test_empty_impact_area_rejected(self):
        p = root([LOW])
        p["inventory"][0]["impact_areas"] = []
        with self.assertRaises(GovernanceError):
            assess_governance(p, trusted_as_of=AS_OF)

    def test_noncanonical_timestamp_rejected(self):
        p = complete_payload([LOW])
        p["control_evidence"][0]["captured_at"] = "2026-09-13T10:00:00.000Z"
        with self.assertRaisesRegex(GovernanceError, "second-precision"):
            assess_governance(p, trusted_as_of=AS_OF)

    def test_result_tamper_fails_verification(self):
        r = assess_governance(complete_payload([LOW]), trusted_as_of=AS_OF)
        r["state"] = "CONTROL_GAPS_PRESENT"
        self.assertFalse(verify_result(r))

    def test_result_extra_field_rejected(self):
        r = assess_governance(complete_payload([LOW]), trusted_as_of=AS_OF)
        r["policy_adopted"] = True
        with self.assertRaises(GovernanceError):
            verify_result(r)

    def test_bad_result_digest_rejected(self):
        r = assess_governance(complete_payload([LOW]), trusted_as_of=AS_OF)
        r["result_sha256"] = "A" * 64
        with self.assertRaises(GovernanceError):
            verify_result(r)

    def test_public_facing_recommendation_is_high(self):
        x = copy.deepcopy(LOW)
        x["system_id"] = "public-reco"
        x["public_facing_output"] = True
        x["automation_level"] = "RECOMMENDATION"
        result = assess_governance(complete_payload([x]), trusted_as_of=AS_OF)
        self.assertEqual(result["systems"][0]["inherent_risk_tier"], "T3_HIGH")

    def test_public_facing_assistive_is_moderate(self):
        x = copy.deepcopy(LOW)
        x["system_id"] = "public-assist"
        x["public_facing_output"] = True
        result = assess_governance(complete_payload([x]), trusted_as_of=AS_OF)
        self.assertEqual(result["systems"][0]["inherent_risk_tier"], "T2_MODERATE")

    def test_internet_connected_requires_security_review(self):
        x = copy.deepcopy(LOW)
        x["system_id"] = "net-helper"
        x["internet_connected"] = True
        result = assess_governance(complete_payload([x]), trusted_as_of=AS_OF)
        self.assertIn("security_review", result["systems"][0]["required_controls"])

    def test_operational_requires_change_and_rollback_controls(self):
        x = copy.deepcopy(LOW)
        x["system_id"] = "ops-observer"
        x["ai_kind"] = "OPERATIONAL"
        x["impact_areas"] = ["ADMINISTRATIVE"]
        result = assess_governance(complete_payload([x]), trusted_as_of=AS_OF)
        required = result["systems"][0]["required_controls"]
        self.assertIn("change_management", required)
        self.assertIn("fail_safe_or_rollback", required)

    def test_no_policy_authority_even_when_complete(self):
        result = assess_governance(complete_payload([OPS]), trusted_as_of=AS_OF)
        self.assertEqual(result["state"], "ASSESSMENT_COMPLETE")
        self.assertFalse(result["authority"]["policy_adoption"])
        self.assertFalse(result["authority"]["production_change"])
        self.assertFalse(result["authority"]["legal_conclusion"])


if __name__ == "__main__":
    unittest.main()
