from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from engine import EvidenceError, compile_receipt, digest, loads_strict, read_stable_json, verify_receipt


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def base_request():
    src_hash = h("controlling-rfp-bytes")
    return {
        "schema": "affordable-housing-compliance-demo-request/v1",
        "buyer_ref": "CITY-DEMO-001",
        "opportunity_ref": "RFP-DEMO-001",
        "generated_at": "2026-09-13T15:00:00Z",
        "data_classification": "SYNTHETIC",
        "sources": [
            {"source_id": "RFP", "uri": "https://example.gov/rfp", "sha256": src_hash, "authority": "CONTROLLING", "retrieved_at": "2026-09-13T14:59:00Z"}
        ],
        "requirements": [
            {"requirement_id": "REQ-AI", "source_id": "RFP", "source_sha256": src_hash, "category": "AI_DEMO", "statement_sha256": h("AI demo requirement")},
            {"requirement_id": "REQ-MIG", "source_id": "RFP", "source_sha256": src_hash, "category": "MIGRATION", "statement_sha256": h("migration requirement")},
        ],
        "gold_findings": [
            {"case_id": "CASE-001", "finding_code": "INCOME_LIMIT_EXCEPTION", "requirement_id": "REQ-AI"},
            {"case_id": "CASE-002", "finding_code": "RECERT_DUE", "requirement_id": "REQ-AI"},
        ],
        "candidate_findings": [
            {"case_id": "CASE-001", "finding_code": "INCOME_LIMIT_EXCEPTION", "evidence_sha256": h("ev1")},
            {"case_id": "CASE-002", "finding_code": "RECERT_DUE", "evidence_sha256": h("ev2")},
        ],
        "migration_source": [
            {"record_id": "UNIT-001", "record_sha256": h("row1")},
            {"record_id": "UNIT-002", "record_sha256": h("row2")},
        ],
        "migration_target": [
            {"record_id": "UNIT-001", "record_sha256": h("row1")},
            {"record_id": "UNIT-002", "record_sha256": h("row2")},
        ],
        "access_policy": [
            {"role": "CITY_REVIEWER", "action": "READ_FILE", "allowed": True},
            {"role": "PROPERTY_MANAGER", "action": "ADOPT_RULE", "allowed": False},
        ],
        "audit_events": [
            {"event_id": "AE-001", "role": "CITY_REVIEWER", "action": "READ_FILE", "resource_id": "CASE-001", "observed_allowed": True},
            {"event_id": "AE-002", "role": "PROPERTY_MANAGER", "action": "ADOPT_RULE", "resource_id": "RULE-001", "observed_allowed": False},
        ],
        "effects": [
            {"event_id": "FX-001", "idempotency_key": "ALERT-CASE-001", "effect_id": "WORK-001", "status": "COMMITTED"},
            {"event_id": "FX-002", "idempotency_key": "ALERT-CASE-001", "effect_id": "WORK-001", "status": "REPLAY"},
        ],
        "threshold_policy": {
            "approved": False,
            "approval_ref": None,
            "approval_sha256": None,
            "min_precision_bps": 10_000,
            "min_recall_bps": 10_000,
            "max_migration_missing": 0,
            "max_migration_extra": 0,
            "max_migration_changed": 0,
            "max_access_violations": 0,
            "max_duplicate_effects": 0,
        },
    }


class EvidenceTests(unittest.TestCase):
    def test_measure_only_without_approved_thresholds(self):
        r = compile_receipt(base_request())
        self.assertEqual(r["decision"], "MEASURE_ONLY")
        self.assertEqual(r["metrics"]["finding_precision_bps"], 10000)
        self.assertFalse(r["authority"]["buyer_acceptance_proven"])

    def test_approved_thresholds_pass_only_to_prime_review(self):
        req = base_request()
        req["threshold_policy"].update({"approved": True, "approval_ref": "PRIME-APPROVAL-1", "approval_sha256": h("approval")})
        r = compile_receipt(req)
        self.assertEqual(r["decision"], "READY_FOR_PRIME_REVIEW")
        self.assertFalse(r["authority"]["housing_compliance_determined"])
        self.assertFalse(r["authority"]["proposal_submission_authorized"])

    def test_threshold_failure(self):
        req = base_request()
        req["candidate_findings"].pop()
        req["threshold_policy"].update({"approved": True, "approval_ref": "P", "approval_sha256": h("p")})
        r = compile_receipt(req)
        self.assertEqual(r["decision"], "HOLD_THRESHOLDS")
        self.assertIn("FINDING_RECALL", r["threshold_failures"])

    def test_discovery_source_forces_hold(self):
        req = base_request()
        req["sources"][0]["authority"] = "DISCOVERY"
        r = compile_receipt(req)
        self.assertEqual(r["decision"], "HOLD_SOURCE_AUTHORITY")
        self.assertEqual(r["evidence"]["requirement_source_holds"], ["REQ-AI", "REQ-MIG"])

    def test_migration_missing_extra_changed(self):
        req = base_request()
        req["migration_target"] = [
            {"record_id": "UNIT-001", "record_sha256": h("changed")},
            {"record_id": "UNIT-003", "record_sha256": h("row3")},
        ]
        r = compile_receipt(req)
        self.assertEqual(r["decision"], "HOLD_EVIDENCE")
        self.assertEqual(r["evidence"]["migration_missing_ids"], ["UNIT-002"])
        self.assertEqual(r["evidence"]["migration_extra_ids"], ["UNIT-003"])
        self.assertEqual(r["evidence"]["migration_changed_ids"], ["UNIT-001"])

    def test_access_policy_mismatch_holds(self):
        req = base_request()
        req["audit_events"][1]["observed_allowed"] = True
        r = compile_receipt(req)
        self.assertEqual(r["decision"], "HOLD_EVIDENCE")
        self.assertEqual(r["metrics"]["access_violation_count"], 1)

    def test_unknown_access_policy_holds(self):
        req = base_request()
        req["audit_events"].append({"event_id": "AE-003", "role": "VENDOR", "action": "DELETE", "resource_id": "CASE-X", "observed_allowed": False})
        r = compile_receipt(req)
        self.assertEqual(r["evidence"]["access_violations"][-1]["reason"], "NO_APPROVED_POLICY")

    def test_duplicate_logical_effect_holds(self):
        req = base_request()
        req["effects"][1]["effect_id"] = "WORK-002"
        r = compile_receipt(req)
        self.assertEqual(r["decision"], "HOLD_EVIDENCE")
        self.assertEqual(r["evidence"]["duplicate_effect_keys"], ["ALERT-CASE-001"])

    def test_false_positive_precision(self):
        req = base_request()
        req["candidate_findings"].append({"case_id": "CASE-999", "finding_code": "BOGUS", "evidence_sha256": h("bogus")})
        r = compile_receipt(req)
        self.assertEqual(r["metrics"]["finding_true_positive"], 2)
        self.assertEqual(r["metrics"]["finding_false_positive"], 1)
        self.assertEqual(r["metrics"]["finding_precision_bps"], 6666)

    def test_source_hash_binding(self):
        req = base_request()
        req["requirements"][0]["source_sha256"] = h("other")
        with self.assertRaises(EvidenceError):
            compile_receipt(req)

    def test_gold_must_bind_requirement(self):
        req = base_request()
        req["gold_findings"][0]["requirement_id"] = "MISSING"
        with self.assertRaises(EvidenceError):
            compile_receipt(req)

    def test_empty_gold_set_rejected(self):
        req = base_request()
        req["gold_findings"] = []
        req["candidate_findings"] = []
        req["threshold_policy"].update({"approved": True, "approval_ref": "P", "approval_sha256": h("p")})
        with self.assertRaises(EvidenceError):
            compile_receipt(req)

    def test_duplicate_candidate_rejected(self):
        req = base_request()
        req["candidate_findings"].append(copy.deepcopy(req["candidate_findings"][0]))
        with self.assertRaises(EvidenceError):
            compile_receipt(req)

    def test_duplicate_audit_event_rejected(self):
        req = base_request()
        req["audit_events"].append(copy.deepcopy(req["audit_events"][0]))
        with self.assertRaises(EvidenceError):
            compile_receipt(req)

    def test_bool_is_not_integer_threshold(self):
        req = base_request()
        req["threshold_policy"]["max_access_violations"] = False
        with self.assertRaises(EvidenceError):
            compile_receipt(req)

    def test_unapproved_threshold_cannot_imply_approval(self):
        req = base_request()
        req["threshold_policy"]["approval_ref"] = "fake"
        with self.assertRaises(EvidenceError):
            compile_receipt(req)

    def test_forbidden_pii_field_rejected(self):
        req = base_request()
        req["candidate_findings"][0]["email"] = "tenant@example.com"
        with self.assertRaises(EvidenceError):
            compile_receipt(req)

    def test_unknown_request_key_rejected(self):
        req = base_request()
        req["prime_qualified"] = True
        with self.assertRaises(EvidenceError):
            compile_receipt(req)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(EvidenceError):
            loads_strict(b'{"schema":"x","schema":"y"}')

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(EvidenceError):
            loads_strict(b'{"x":NaN}')

    def test_deterministic_receipt(self):
        a = compile_receipt(base_request())
        b = compile_receipt(copy.deepcopy(base_request()))
        self.assertEqual(a, b)
        self.assertEqual(a["receipt_sha256"], b["receipt_sha256"])

    def test_receipt_tamper_rejected(self):
        req = base_request()
        receipt = compile_receipt(req)
        receipt["decision"] = "READY_FOR_PRIME_REVIEW"
        with self.assertRaises(EvidenceError):
            verify_receipt(req, receipt)

    def test_symlink_input_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            real = p / "real.json"
            real.write_text(json.dumps(base_request()), encoding="utf-8")
            link = p / "link.json"
            try:
                link.symlink_to(real)
            except (OSError, NotImplementedError):
                self.skipTest("symlink unsupported")
            with self.assertRaises(EvidenceError):
                read_stable_json(link)

    def test_stable_file_read(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "request.json"
            p.write_text(json.dumps(base_request()), encoding="utf-8")
            loaded = read_stable_json(p)
            self.assertEqual(digest(loaded), digest(base_request()))

    def test_authority_ceiling_is_all_false(self):
        req = base_request()
        req["threshold_policy"].update({"approved": True, "approval_ref": "P", "approval_sha256": h("p")})
        receipt = compile_receipt(req)
        self.assertTrue(all(value is False for value in receipt["authority"].values()))


if __name__ == "__main__":
    unittest.main()
