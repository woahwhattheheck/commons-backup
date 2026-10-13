import copy
import json
import unittest
from pathlib import Path

from revenue.washington_county_ar_2026_21_comms.acceptance_harness import HarnessError, evaluate_scenario
from revenue.washington_county_ar_2026_21_comms.qualification import PACKET_SHA256, REQUIRED_TECHNICAL, evaluate

ROOT = Path(__file__).parent


def blank_evidence():
    return json.loads((ROOT / "evidence_template.json").read_text())


def good_project(i):
    return {
        "jurisdiction": f"Synthetic Jurisdiction {i}",
        "start_date": "2024-01-01",
        "end_date": "2024-06-01",
        "scope": "government constituent communications",
        "channels": "phone/chat/email",
        "evidence_url": f"https://example.invalid/project/{i}",
        "completed": True,
    }


def complete_evidence():
    e = blank_evidence()
    e.update({
        "legal_entity": "Evidence-backed bidder",
        "authorized_signer": "Authorized Person",
        "prime_candidate": "Evidence-backed bidder",
        "partner_authorized": True,
        "boycott_certification_authorized": True,
        "insurance_letter": "artifact://insurance-letter",
        "proof_of_insurance": "artifact://insurance",
        "telephony_registration_plan": "artifact://telephony-plan",
        "supported_languages": ["English", "Spanish"],
        "language_fallback": "human escalation",
        "all_known_addenda_acknowledged": True,
        "vpat": {"document":"artifact://vpat", "wcag_2_1_aa": True},
        "implementation_lead": {"name":"Named Lead", "evidence":"artifact://lead-cv", "similar_government_deployment": True},
        "five_project_matrix": [good_project(i) for i in range(5)],
        "system_of_record_integrations": [{
            "client":"Synthetic public client", "system_of_record":"Synthetic CAMA",
            "production_date":"2025-01-01", "approach":"read-only adapter",
            "reference_or_evidence":"artifact://reference", "production":True
        }],
    })
    e["technical_support"] = {k: True for k in REQUIRED_TECHNICAL}
    e["pricing"].update({
        "year_one_implementation_cents": 1,
        "annual_subscription_cents": 1,
        "overage_rate": "evidence-backed",
        "additional_license_rate": "evidence-backed",
        "sms_rate": "evidence-backed",
        "year_one_total_cents": 2,
        "concurrent_session_cap": "evidence-backed"
    })
    return e


class QualificationTests(unittest.TestCase):
    def test_blank_is_hold(self):
        r = evaluate(blank_evidence())
        self.assertEqual(r["posture"], "HOLD_PRIME_OR_PARTNER")
        self.assertIn("E_FIVE_PROJECTS", r["reason_codes"])
        self.assertIn("E_PRODUCTION_SOR_INTEGRATION", r["reason_codes"])

    def test_complete_reaches_owner_review_not_submission(self):
        r = evaluate(complete_evidence())
        self.assertEqual(r["posture"], "READY_FOR_OWNER_SUBMISSION_REVIEW")
        self.assertFalse(r["submission_authorized_by_gate"])
        self.assertEqual(r["reason_codes"], [])

    def test_four_projects_fail(self):
        e = complete_evidence(); e["five_project_matrix"] = e["five_project_matrix"][:4]
        self.assertIn("E_FIVE_PROJECTS", evaluate(e)["reason_codes"])

    def test_project_must_be_completed(self):
        e = complete_evidence(); e["five_project_matrix"][0]["completed"] = False
        self.assertIn("E_FIVE_PROJECTS", evaluate(e)["reason_codes"])

    def test_integration_must_be_production(self):
        e = complete_evidence(); e["system_of_record_integrations"][0]["production"] = False
        self.assertIn("E_PRODUCTION_SOR_INTEGRATION", evaluate(e)["reason_codes"])

    def test_packet_transplant_rejected(self):
        e = complete_evidence(); e["packet_sha256"] = "0"*64
        self.assertIn("E_PACKET_DIGEST", evaluate(e)["reason_codes"])

    def test_missing_vpat(self):
        e = complete_evidence(); e["vpat"] = None
        self.assertIn("E_VPAT", evaluate(e)["reason_codes"])

    def test_missing_insurance_letter(self):
        e = complete_evidence(); e["insurance_letter"] = None
        self.assertIn("E_INSURANCE_LETTER", evaluate(e)["reason_codes"])

    def test_missing_authorized_signer(self):
        e = complete_evidence(); e["authorized_signer"] = None
        self.assertIn("E_AUTHORIZED_SIGNER", evaluate(e)["reason_codes"])

    def test_missing_addenda_ack(self):
        e = complete_evidence(); e["all_known_addenda_acknowledged"] = False
        self.assertIn("E_ADDENDA", evaluate(e)["reason_codes"])

    def test_bool_not_accepted_as_money(self):
        e = complete_evidence(); e["pricing"]["year_one_total_cents"] = True
        self.assertIn("E_PRICE_TYPE_YEAR_ONE_TOTAL_CENTS", evaluate(e)["reason_codes"])

    def test_missing_pricing(self):
        e = complete_evidence(); e["pricing"]["sms_rate"] = None
        self.assertIn("E_PRICING", evaluate(e)["reason_codes"])

    def test_missing_technical_support(self):
        e = complete_evidence(); e["technical_support"]["cama_read_integration"] = False
        r = evaluate(e)
        self.assertIn("E_TECHNICAL_SUPPORT", r["reason_codes"])
        self.assertIn("cama_read_integration", r["missing_technical"])

    def test_partner_not_authorized_stays_hold(self):
        e = complete_evidence(); e["partner_authorized"] = False
        self.assertEqual(evaluate(e)["posture"], "HOLD_PARTNER_CONFIRMATION")

    def test_submission_flag_is_warning_only(self):
        e = complete_evidence(); e["submission_authorized"] = True
        r = evaluate(e)
        self.assertFalse(r["submission_authorized_by_gate"])
        self.assertIn("W_SUBMISSION_AUTHORITY_IS_EXTERNAL_TO_THIS_GATE", r["warnings"])


class HarnessTests(unittest.TestCase):
    def scenario(self):
        return json.loads((ROOT / "fixtures" / "synthetic_case.json").read_text())

    def test_fixture_passes(self):
        r = evaluate_scenario(self.scenario())
        self.assertEqual(r["status"], "PASS")
        self.assertEqual(r["cross_channel_case_ids"], ["case-001"])
        self.assertEqual(r["property_lookup_count"], 2)

    def test_account_field_requires_identity(self):
        s = self.scenario(); s["events"][4]["identity_confirmed"] = False
        r = evaluate_scenario(s)
        self.assertEqual(r["status"], "HOLD")
        self.assertTrue(any(x.startswith("IDENTITY_REQUIRED") for x in r["failure_codes"]))

    def test_mutation_action_rejected(self):
        s = self.scenario(); s["events"][0]["action"] = "update_property"
        r = evaluate_scenario(s)
        self.assertTrue(any(x.startswith("ACTION_NOT_READ_ONLY") for x in r["failure_codes"]))

    def test_knowledge_drift_rejected(self):
        s = self.scenario(); s["events"][0]["knowledge_version"] = "other"
        self.assertTrue(any(x.startswith("KNOWLEDGE_DRIFT") for x in evaluate_scenario(s)["failure_codes"]))

    def test_duplicate_event_rejected(self):
        s = self.scenario(); s["events"][1]["event_id"] = s["events"][0]["event_id"]
        self.assertTrue(any(x.startswith("DUPLICATE_EVENT") for x in evaluate_scenario(s)["failure_codes"]))

    def test_case_constituent_drift_rejected(self):
        s = self.scenario(); s["events"][1]["constituent_id"] = "other"
        self.assertTrue(any(x.startswith("CASE_CONSTITUENT_DRIFT") for x in evaluate_scenario(s)["failure_codes"]))

    def test_unknown_field_rejected(self):
        s = self.scenario(); s["events"][0]["secret"] = "x"
        with self.assertRaises(HarnessError): evaluate_scenario(s)

    def test_bool_alias_rejected(self):
        s = self.scenario(); s["events"][0]["identity_confirmed"] = 1
        with self.assertRaises(HarnessError): evaluate_scenario(s)

    def test_unknown_property_field_hold(self):
        s = self.scenario(); s["events"][1]["field"] = "ssn"
        self.assertTrue(any(x.startswith("FIELD_NOT_ALLOWLISTED") for x in evaluate_scenario(s)["failure_codes"]))

if __name__ == "__main__":
    unittest.main()
