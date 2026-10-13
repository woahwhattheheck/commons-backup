from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from revenue.vancouver_civic_theatres_website import engine

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "company_unknown.json"


def packet() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def ready_packet() -> dict:
    value = packet()
    for name, gate in value["company_evidence"].items():
        if name in {"key_personnel_privacy", "subcontractor_disclosure", "agreement_amendments"}:
            gate.update(status="NOT_APPLICABLE", evidence_ref=None, notes="Owner-confirmed not applicable for this internal scenario")
        else:
            gate.update(status="READY", evidence_ref=f"owner://evidence/{name}", notes=None)
    value["owner_decision"] = "PRIME"
    return value


class PursuitCarrierTests(unittest.TestCase):
    def setUp(self):
        self.open_time = datetime(2026, 9, 16, 22, 30, tzinfo=timezone.utc)
        self.closed_time = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)

    def test_evidence_registry_digest_is_pinned(self):
        evidence = engine._load_evidence()
        self.assertEqual(engine._sha(evidence), engine.EVIDENCE_REGISTRY_SHA256)
        self.assertEqual(evidence["opportunity_id"], "PS20261832-ACCS-RFP")

    def test_official_buyer_event_facts(self):
        evidence = engine._load_evidence()
        official = next(s for s in evidence["sources"] if s["authority"] == "BUYER_PUBLIC_SUPPLIER_PORTAL")
        facts = official["facts"]
        self.assertEqual(facts["closes_at"], "2026-10-07T15:00:00-07:00")
        self.assertEqual(facts["currency"], "CAD")
        self.assertEqual(facts["contact_email"], "Wen.Shi@vancouver.ca")
        self.assertEqual(facts["service_line"]["pricing_basis"], "LUMP_SUM")
        self.assertIn("Confirmation of WCAG Level AA", facts["bid_prerequisites"])

    def test_public_fixture_holds_controlling_attachments_and_company_evidence(self):
        report = engine._compile_at(packet(), self.open_time)
        self.assertEqual(report["pursuit_posture"], "HOLD_CONTROLLING_ATTACHMENTS")
        self.assertEqual(report["source_readiness"], "HOLD_CONTROLLING_ATTACHMENTS")
        self.assertEqual(report["company_readiness"], "HOLD_COMPANY_EVIDENCE")
        self.assertEqual(len(report["source_blockers"]), 7)
        self.assertEqual(len(report["company_blockers"]), 13)

    def test_even_fully_ready_company_cannot_bypass_unretrieved_buyer_attachments(self):
        report = engine._compile_at(ready_packet(), self.open_time)
        self.assertEqual(report["company_readiness"], "COMPANY_EVIDENCE_COMPLETE")
        self.assertEqual(report["pursuit_posture"], "HOLD_CONTROLLING_ATTACHMENTS")
        self.assertFalse(report["commercial"]["buyer_facing_price_authorized"])

    def test_prime_owner_decision_is_not_submission_authority(self):
        report = engine._compile_at(ready_packet(), self.open_time)
        self.assertEqual(report["owner_decision"], "PRIME")
        self.assertTrue(report["authority"])
        self.assertFalse(any(report["authority"].values()))

    def test_all_external_authority_bits_are_false(self):
        report = engine._compile_at(packet(), self.open_time)
        self.assertEqual(set(report["authority"]), set(engine._ACTION_KEYS))
        self.assertFalse(any(report["authority"].values()))

    def test_close_time_fails_closed(self):
        report = engine._compile_at(ready_packet(), self.closed_time)
        self.assertEqual(report["deadline_state"], "CLOSED")
        self.assertEqual(report["pursuit_posture"], "CLOSED_NO_SUBMIT")
        self.assertFalse(any(report["authority"].values()))

    def test_naive_clock_rejected(self):
        with self.assertRaisesRegex(engine.ContractError, "timezone-aware"):
            engine._compile_at(packet(), datetime(2026, 9, 16, 22, 30))

    def test_candidate_cannot_self_author_source_gaps(self):
        value = packet()
        value["controlling_gaps"] = []
        with self.assertRaisesRegex(engine.ContractError, "unknown fields"):
            engine._compile_at(value, self.open_time)

    def test_candidate_cannot_self_author_opportunity_metadata(self):
        value = packet()
        value["opportunity"] = {"closes_at": "2099-01-01T00:00:00Z"}
        with self.assertRaisesRegex(engine.ContractError, "unknown fields"):
            engine._compile_at(value, self.open_time)

    def test_missing_company_gate_rejected(self):
        value = packet()
        del value["company_evidence"]["wcag_aa_capability"]
        with self.assertRaisesRegex(engine.ContractError, "schema mismatch"):
            engine._compile_at(value, self.open_time)

    def test_unknown_company_gate_rejected(self):
        value = packet()
        value["company_evidence"]["magic_certification"] = {"status": "READY", "evidence_ref": "x", "notes": None}
        with self.assertRaisesRegex(engine.ContractError, "schema mismatch"):
            engine._compile_at(value, self.open_time)

    def test_ready_gate_requires_evidence_reference(self):
        value = packet()
        value["company_evidence"]["wcag_aa_capability"]["status"] = "READY"
        with self.assertRaisesRegex(engine.ContractError, "READY requires evidence_ref"):
            engine._compile_at(value, self.open_time)

    def test_required_gate_cannot_be_not_applicable(self):
        value = packet()
        value["company_evidence"]["wcag_aa_capability"]["status"] = "NOT_APPLICABLE"
        value["company_evidence"]["wcag_aa_capability"]["notes"] = "no"
        with self.assertRaisesRegex(engine.ContractError, "NOT_APPLICABLE is invalid"):
            engine._compile_at(value, self.open_time)

    def test_conditional_gate_may_be_not_applicable(self):
        value = packet()
        value["company_evidence"]["subcontractor_disclosure"] = {
            "status": "NOT_APPLICABLE",
            "evidence_ref": None,
            "notes": "Owner states no subcontractors are proposed",
        }
        report = engine._compile_at(value, self.open_time)
        self.assertNotIn("subcontractor_disclosure", report["company_blockers"])

    def test_internal_estimate_is_explicitly_non_submitted(self):
        value = packet()
        value["commercial"] = {
            "status": "PROPOSED_INTERNAL_NOT_SUBMITTED",
            "internal_estimate_cad": 500000,
            "basis": "Internal scenario only; controlling Annex 4 not retained",
        }
        report = engine._compile_at(value, self.open_time)
        self.assertEqual(report["commercial"]["internal_estimate"]["internal_estimate_cad"], 500000.0)
        self.assertFalse(report["commercial"]["buyer_facing_price_authorized"])
        self.assertIn("Annex 4", report["commercial"]["note"])

    def test_no_estimate_cannot_smuggle_number(self):
        value = packet()
        value["commercial"]["internal_estimate_cad"] = 1
        with self.assertRaisesRegex(engine.ContractError, "NO_ESTIMATE"):
            engine._compile_at(value, self.open_time)

    def test_boolean_is_not_a_price(self):
        value = packet()
        value["commercial"] = {
            "status": "PROPOSED_INTERNAL_NOT_SUBMITTED",
            "internal_estimate_cad": True,
            "basis": "bad",
        }
        with self.assertRaisesRegex(engine.ContractError, "cannot be boolean"):
            engine._compile_at(value, self.open_time)

    def test_invalid_owner_decision_rejected(self):
        value = packet()
        value["owner_decision"] = "SEND"
        with self.assertRaisesRegex(engine.ContractError, "owner_decision"):
            engine._compile_at(value, self.open_time)

    def test_strict_json_rejects_duplicate_keys(self):
        with self.assertRaisesRegex(engine.ContractError, "duplicate JSON key"):
            engine.load_json_strict('{"a":1,"a":2}')

    def test_strict_json_rejects_nonfinite(self):
        with self.assertRaisesRegex(engine.ContractError, "non-finite"):
            engine.load_json_strict('{"a":NaN}')

    def test_registry_mutation_fails_digest(self):
        evidence = engine._load_evidence()
        altered = deepcopy(evidence)
        altered["sources"][0]["facts"]["closes_at"] = "2099-01-01T00:00:00Z"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "buyer_evidence.json"
            path.write_text(json.dumps(altered), encoding="utf-8")
            with patch.object(engine, "_EVIDENCE_PATH", path):
                with self.assertRaisesRegex(engine.ContractError, "digest mismatch"):
                    engine._load_evidence()

    def test_report_integrity_verifies(self):
        report = engine._compile_at(packet(), self.open_time)
        with patch.object(engine, "_now_utc", return_value=self.open_time):
            verdict = engine.verify_report(packet(), report)
        self.assertEqual(verdict["verdict"], "CURRENT_VERIFIED_INTERNAL_ONLY")
        self.assertTrue(verdict["historical_match"])
        self.assertFalse(verdict["external_submission_authorized"])

    def test_report_tamper_is_detected(self):
        report = engine._compile_at(packet(), self.open_time)
        report["opportunity"]["closes_at"] = "2099-01-01T00:00:00Z"
        with patch.object(engine, "_now_utc", return_value=self.open_time):
            verdict = engine.verify_report(packet(), report)
        self.assertEqual(verdict["verdict"], "TAMPERED_OR_NONCANONICAL")
        self.assertFalse(verdict["historical_match"])

    def test_verified_report_becomes_historical_after_deadline(self):
        report = engine._compile_at(packet(), self.open_time)
        with patch.object(engine, "_now_utc", return_value=self.closed_time):
            verdict = engine.verify_report(packet(), report)
        self.assertEqual(verdict["verdict"], "HISTORICAL_VERIFIED_DEADLINE_CLOSED")
        self.assertEqual(verdict["current_deadline_state"], "CLOSED")

    def test_markdown_is_explicitly_not_a_submission(self):
        text = engine.render_markdown(engine._compile_at(packet(), self.open_time))
        self.assertIn("NOT A SUBMISSION", text)
        self.assertIn("HOLD_CONTROLLING_ATTACHMENTS", text)
        self.assertIn("Every external-action authority bit is `false`", text)
        self.assertNotIn("$350", text)
        self.assertNotIn("$1,100,000", text)

    def test_response_spine_does_not_invent_migration_quantity_or_cms(self):
        report = engine._compile_at(packet(), self.open_time)
        text = json.dumps(report["response_spine"], sort_keys=True)
        self.assertNotIn("1,500", text)
        self.assertNotIn("WordPress", text)
        self.assertNotIn("Drupal", text)
        self.assertIn("migration quantities remain uncommitted", text)

    def test_required_components_keep_pricing_separate(self):
        report = engine._compile_at(packet(), self.open_time)
        parts = report["required_submission_components"]
        scope = next(p for p in parts if p.startswith("Annex 1"))
        financial = next(p for p in parts if p.startswith("Annex 4"))
        self.assertIn("no pricing", scope)
        self.assertIn("Financial Proposal", financial)

    def test_work_safe_bc_equivalent_rule_is_retained_from_buyer_event(self):
        report = engine._compile_at(packet(), self.open_time)
        matching = [p for p in report["required_submission_components"] if "WorkSafeBC" in p]
        self.assertEqual(len(matching), 1)
        self.assertIn("accepted equivalent", matching[0])


if __name__ == "__main__":
    unittest.main()
