from __future__ import annotations

import copy
import hashlib
import json
import random
import unittest
from datetime import datetime, timedelta, timezone

from .fixture import DEFECTS, EVALUATED_AT, build_acceptance_batch, build_case, build_policy
from .gate import AUTHORITY, GateInputError, digest, evaluate, verify


def _readdress(case):
    core = copy.deepcopy(case)
    core.pop("event_id", None)
    case["event_id"] = digest(core)
    return case

class AgenticGxpLineageGateTests(unittest.TestCase):
    def setUp(self):
        self.policy = build_policy()
        self.batch = build_acceptance_batch()

    def test_acceptance_fixture_is_120_with_96_ready_and_24_held(self):
        result = evaluate(self.policy, self.batch, evaluated_at=EVALUATED_AT)
        receipt = result["receipt"]
        self.assertEqual(120, receipt["input_case_count"])
        self.assertEqual(120, receipt["unique_event_count"])
        self.assertEqual(96, receipt["ready_case_count"])
        self.assertEqual(24, receipt["held_case_count"])
        self.assertEqual("HOLD", receipt["decision"])
        self.assertIn("CASES_HELD", receipt["holds"])
        self.assertEqual(AUTHORITY, receipt["authority"])
        self.assertFalse(receipt["source_authenticity_verified"])
        self.assertFalse(receipt["production_release_authorized"])
        self.assertFalse(receipt["qa_disposition_authorized"])
        self.assertFalse(receipt["regulatory_compliance_certified"])
        self.assertFalse(receipt["buyer_acceptance_inferred"])
        self.assertFalse(receipt["recognized_revenue_inferred"])
        self.assertTrue(verify(result, policy=self.policy, batch=self.batch))

    def test_fixture_has_exactly_three_of_each_synthetic_defect(self):
        result = evaluate(self.policy, self.batch, evaluated_at=EVALUATED_AT)
        counts = {defect: 0 for defect in DEFECTS}
        held = [row for row in result["manifest"]["rows"] if row["status"] == "HOLD"]
        self.assertEqual(24, len(held))
        for row in held:
            self.assertEqual(1, len(row["codes"]))
            code = row["codes"][0]
            self.assertIn(code, counts)
            counts[code] += 1
        self.assertEqual({defect: 3 for defect in DEFECTS}, counts)

    def test_ready_rows_bind_source_batch_execution_change_and_human_lineage(self):
        result = evaluate(self.policy, self.batch, evaluated_at=EVALUATED_AT)
        row = next(row for row in result["manifest"]["rows"] if row["status"] == AUTHORITY)
        self.assertEqual(2, len(row["source_lineage"]))
        self.assertRegex(row["lineage_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(row["query_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(row["artifact_sha256"], row["result_sha256"])
        self.assertTrue(row["change_control_reference"].startswith("CC-2026-"))
        self.assertTrue(row["human_reviewer_id"].startswith("reviewer-"))

    def test_input_order_changes_batch_hash_but_not_manifest(self):
        r1 = evaluate(self.policy, self.batch, evaluated_at=EVALUATED_AT)
        shuffled = copy.deepcopy(self.batch)
        random.Random(11).shuffle(shuffled["cases"])
        r2 = evaluate(self.policy, shuffled, evaluated_at=EVALUATED_AT)
        self.assertEqual(r1["manifest"], r2["manifest"])
        self.assertNotEqual(r1["receipt"]["batch_sha256"], r2["receipt"]["batch_sha256"])
        self.assertEqual(r1["receipt"]["manifest_sha256"], r2["receipt"]["manifest_sha256"])

    def test_exact_replay_is_collapsed(self):
        replay = copy.deepcopy(self.batch)
        replay["cases"].append(copy.deepcopy(replay["cases"][0]))
        result = evaluate(self.policy, replay, evaluated_at=EVALUATED_AT)
        self.assertEqual(121, result["receipt"]["input_case_count"])
        self.assertEqual(120, result["receipt"]["unique_event_count"])
        self.assertEqual(1, result["receipt"]["duplicate_event_count"])
        self.assertEqual(96, result["receipt"]["ready_case_count"])

    def test_same_case_id_changed_payload_is_quarantined_as_conflict(self):
        conflicting = copy.deepcopy(self.batch)
        changed = copy.deepcopy(conflicting["cases"][0])
        changed["artifact"]["sha256"] = digest({"changed": True})
        changed["execution"]["result_sha256"] = changed["artifact"]["sha256"]
        changed["human_approval"]["artifact_sha256"] = changed["artifact"]["sha256"]
        _readdress(changed)
        conflicting["cases"].append(changed)
        result = evaluate(self.policy, conflicting, evaluated_at=EVALUATED_AT)
        self.assertIn("CASE_ID_CONFLICT", result["receipt"]["holds"])
        self.assertEqual(1, result["receipt"]["conflicting_case_id_count"])
        self.assertEqual("case-000", result["manifest"]["conflicts"][0]["case_id"])
        self.assertFalse(any(row["case_id"] == "case-000" for row in result["manifest"]["rows"]))

    def test_incomplete_batch_capture_holds_even_if_cases_are_ready(self):
        batch = {"schema": self.batch["schema"], "capture_complete": False, "captured_at": self.batch["captured_at"], "cases": [build_case(1)]}
        result = evaluate(self.policy, batch, evaluated_at=EVALUATED_AT)
        self.assertIn("BATCH_CAPTURE_INCOMPLETE", result["receipt"]["holds"])
        self.assertEqual(1, result["receipt"]["ready_case_count"])
        self.assertEqual("HOLD", result["receipt"]["decision"])

    def test_stale_batch_and_case_hold(self):
        policy = build_policy()
        policy["max_evidence_age_seconds"] = 10
        batch = {"schema": self.batch["schema"], "capture_complete": True, "captured_at": self.batch["captured_at"], "cases": [build_case(1)]}
        result = evaluate(policy, batch, evaluated_at=EVALUATED_AT)
        self.assertIn("BATCH_CAPTURE_STALE", result["receipt"]["holds"])
        self.assertIn("EVIDENCE_STALE", result["manifest"]["rows"][0]["codes"])

    def test_artifact_type_not_approved_holds(self):
        case = build_case(1)
        case["artifact"]["artifact_type"] = "autonomous_batch_release"
        _readdress(case)
        result = evaluate(self.policy, self._one(case), evaluated_at=EVALUATED_AT)
        self.assertEqual(["ARTIFACT_TYPE_NOT_APPROVED"], result["manifest"]["rows"][0]["codes"])

    def test_actor_role_not_approved_holds(self):
        case = build_case(1)
        case["actor"]["role"] = "service_account"
        _readdress(case)
        result = evaluate(self.policy, self._one(case), evaluated_at=EVALUATED_AT)
        self.assertIn("ACTOR_ROLE_NOT_APPROVED", result["manifest"]["rows"][0]["codes"])

    def test_risk_class_not_approved_holds(self):
        case = build_case(1)
        case["intended_use"]["risk_class"] = "CRITICAL"
        _readdress(case)
        result = evaluate(self.policy, self._one(case), evaluated_at=EVALUATED_AT)
        self.assertIn("RISK_CLASS_NOT_APPROVED", result["manifest"]["rows"][0]["codes"])
        self.assertIn("HUMAN_APPROVER_ROLE_NOT_AUTHORIZED", result["manifest"]["rows"][0]["codes"])

    def test_four_eyes_violation_holds(self):
        case = build_case(2)
        case["human_approval"]["reviewer_id"] = case["actor"]["user_id"]
        _readdress(case)
        result = evaluate(self.policy, self._one(case), evaluated_at=EVALUATED_AT)
        self.assertEqual(["FOUR_EYES_VIOLATION"], result["manifest"]["rows"][0]["codes"])

    def test_human_rejection_holds(self):
        case = build_case(2)
        case["human_approval"]["decision"] = "REJECT"
        _readdress(case)
        result = evaluate(self.policy, self._one(case), evaluated_at=EVALUATED_AT)
        self.assertEqual(["HUMAN_APPROVAL_NOT_APPROVED"], result["manifest"]["rows"][0]["codes"])

    def test_result_artifact_hash_mismatch_holds(self):
        case = build_case(2)
        case["execution"]["result_sha256"] = digest({"different": "result"})
        _readdress(case)
        result = evaluate(self.policy, self._one(case), evaluated_at=EVALUATED_AT)
        self.assertEqual(["RESULT_ARTIFACT_HASH_MISMATCH"], result["manifest"]["rows"][0]["codes"])

    def _one(self, case, captured="2026-09-13T09:15:00Z"):
        return {
            "schema": self.batch["schema"],
            "capture_complete": True,
            "captured_at": captured,
            "cases": [case],
        }


if __name__ == "__main__":
    unittest.main()
