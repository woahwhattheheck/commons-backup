from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

try:
    from .acceptance import FIXTURE_TIME, build_clean_packet, run_acceptance
    from .gate import (
        AUTHORITY_FALSE,
        EvidenceError,
        _evaluate,
        _verify_receipt_at,
        canonical_json,
        load_json_strict,
        sha256_json,
    )
except ImportError:
    from acceptance import FIXTURE_TIME, build_clean_packet, run_acceptance
    from gate import (
        AUTHORITY_FALSE,
        EvidenceError,
        _evaluate,
        _verify_receipt_at,
        canonical_json,
        load_json_strict,
        sha256_json,
    )


class GateTests(unittest.TestCase):
    def clean(self):
        return build_clean_packet(7)

    def evaluate(self, packet):
        return _evaluate(packet, FIXTURE_TIME)

    def test_clean_ready_and_authority_false(self):
        receipt = self.evaluate(self.clean())
        self.assertEqual(receipt["decision"], "READY_FOR_PRIME_REVIEW")
        self.assertEqual(receipt["hold_reasons"], [])
        self.assertEqual(receipt["authority"], AUTHORITY_FALSE)

    def test_incomplete_snapshot_holds(self):
        packet = self.clean(); packet["complete"] = False
        self.assertIn("INCOMPLETE_SNAPSHOT", self.evaluate(packet)["hold_reasons"])

    def test_stale_snapshot_holds_against_external_trusted_time(self):
        receipt = _evaluate(self.clean(), FIXTURE_TIME + timedelta(hours=1))
        self.assertIn("STALE_SNAPSHOT", receipt["hold_reasons"])

    def test_future_snapshot_holds(self):
        packet = self.clean(); packet["captured_at"] = "2026-09-13T10:00:00Z"
        self.assertIn("FUTURE_SNAPSHOT", self.evaluate(packet)["hold_reasons"])

    def test_mandatory_requirement_must_be_covered(self):
        packet = self.clean()
        packet["test_cases"] = [x for x in packet["test_cases"] if x["test_id"] != "T-DEPLOY"]
        packet["test_runs"] = [x for x in packet["test_runs"] if x["test_id"] != "T-DEPLOY"]
        self.assertIn("MANDATORY_REQUIREMENT_UNCOVERED", self.evaluate(packet)["hold_reasons"])

    def test_failed_test_holds(self):
        packet = self.clean(); packet["test_runs"][0]["status"] = "FAIL"
        reasons = self.evaluate(packet)["hold_reasons"]
        self.assertIn("TEST_FAILURE", reasons)
        self.assertIn("MANDATORY_REQUIREMENT_UNCOVERED", reasons)

    def test_missing_run_holds(self):
        packet = self.clean(); packet["test_runs"].pop()
        self.assertIn("TEST_EXECUTION_CARDINALITY", self.evaluate(packet)["hold_reasons"])

    def test_unknown_requirement_reference_holds(self):
        packet = self.clean(); packet["test_cases"][0]["requirement_ids"] = ["REQ-NOT-THERE"]
        self.assertIn("UNKNOWN_REQUIREMENT_REFERENCE", self.evaluate(packet)["hold_reasons"])

    def test_all_core_validations_are_required_once(self):
        packet = self.clean(); packet["validation_results"].pop()
        self.assertIn("CORE_VALIDATION_CARDINALITY", self.evaluate(packet)["hold_reasons"])

    def test_failed_core_validation_holds(self):
        packet = self.clean(); packet["validation_results"][0]["status"] = "FAIL"
        self.assertIn("VALIDATION_FAILURE", self.evaluate(packet)["hold_reasons"])

    def test_unapproved_validation_rule_holds(self):
        packet = self.clean(); packet["validation_results"][0]["rule_id"] = "SELF_ASSERTED_OK"
        reasons = self.evaluate(packet)["hold_reasons"]
        self.assertIn("UNAPPROVED_VALIDATION_RULE", reasons)
        self.assertIn("CORE_VALIDATION_CARDINALITY", reasons)

    def test_role_collision_holds(self):
        packet = self.clean(); packet["workflow_events"][3]["actor_id"] = "actor-config"
        self.assertIn("ROLE_SEPARATION_VIOLATION", self.evaluate(packet)["hold_reasons"])

    def test_wrong_workflow_role_holds(self):
        packet = self.clean(); packet["workflow_events"][3]["role"] = "TESTER"
        self.assertIn("WORKFLOW_ROLE_MISMATCH", self.evaluate(packet)["hold_reasons"])

    def test_workflow_release_mismatch_holds(self):
        packet = self.clean(); packet["workflow_events"][1]["object_id"] = "OTHER-RELEASE"
        self.assertIn("WORKFLOW_RELEASE_MISMATCH", self.evaluate(packet)["hold_reasons"])

    def test_exact_duplicate_integration_event_collapses(self):
        packet = self.clean(); packet["integration_events"].append(copy.deepcopy(packet["integration_events"][0]))
        receipt = self.evaluate(packet)
        self.assertEqual(receipt["decision"], "READY_FOR_PRIME_REVIEW")
        self.assertEqual(receipt["counts"]["integration_events_unique"], 3)

    def test_changed_content_same_integration_id_holds(self):
        packet = self.clean(); changed = copy.deepcopy(packet["integration_events"][0]); changed["payload_sha256"] = "f" * 64
        packet["integration_events"].append(changed)
        self.assertIn("INTEGRATION_EVENT_ID_CONFLICT", self.evaluate(packet)["hold_reasons"])

    def test_invalid_no_effect_retry_holds(self):
        packet = self.clean(); packet["integration_events"][1]["retry_of"] = "INT-2"
        self.assertIn("INVALID_RETRY_LINK", self.evaluate(packet)["hold_reasons"])

    def test_integration_gap_holds(self):
        packet = self.clean(); packet["integration_events"][2]["sequence"] = 3
        self.assertIn("INTEGRATION_SEQUENCE_GAP", self.evaluate(packet)["hold_reasons"])

    def test_quarantined_integration_holds(self):
        packet = self.clean(); packet["integration_events"][2]["outcome"] = "QUARANTINED"
        self.assertIn("INTEGRATION_QUARANTINED", self.evaluate(packet)["hold_reasons"])

    def test_audit_chain_tamper_holds(self):
        packet = self.clean(); packet["audit_events"][2]["prev_hash"] = "0" * 64
        reasons = self.evaluate(packet)["hold_reasons"]
        self.assertIn("AUDIT_CHAIN_BROKEN", reasons)
        self.assertIn("AUDIT_HASH_MISMATCH", reasons)

    def test_audit_sequence_gap_holds(self):
        packet = self.clean(); packet["audit_events"][2]["sequence"] = 9
        # Shape validator sees duplicate-free sequence values; evaluator catches contiguity.
        self.assertIn("AUDIT_SEQUENCE_GAP", self.evaluate(packet)["hold_reasons"])

    def test_audit_time_regression_holds(self):
        packet = self.clean(); packet["audit_events"][2]["observed_at"] = "2026-09-13T09:28:59Z"
        self.assertIn("AUDIT_TIME_REGRESSION", self.evaluate(packet)["hold_reasons"])

    def test_stale_event_holds(self):
        packet = self.clean(); packet["test_runs"][0]["observed_at"] = "2026-09-12T08:00:00Z"
        self.assertIn("STALE_EVIDENCE", self.evaluate(packet)["hold_reasons"])

    def test_future_event_holds(self):
        packet = self.clean(); packet["test_runs"][0]["observed_at"] = "2026-09-13T09:35:00Z"
        reasons = self.evaluate(packet)["hold_reasons"]
        self.assertIn("EVIDENCE_AFTER_SNAPSHOT", reasons)

    def test_permutation_is_digest_stable(self):
        one = self.clean(); two = copy.deepcopy(one)
        for field in ("requirements", "test_cases", "test_runs", "validation_results", "workflow_events", "integration_events", "audit_events"):
            two[field] = list(reversed(two[field]))
        r1 = self.evaluate(one); r2 = self.evaluate(two)
        self.assertEqual(r1["snapshot_digest"], r2["snapshot_digest"])
        self.assertEqual(r1["receipt_digest"], r2["receipt_digest"])

    def test_receipt_tamper_fails(self):
        receipt = self.evaluate(self.clean())
        receipt["decision"] = "HOLD"
        self.assertFalse(_verify_receipt_at(receipt, FIXTURE_TIME + timedelta(seconds=1)))

    def test_receipt_lifetime_exact_boundary(self):
        receipt = self.evaluate(self.clean())
        self.assertTrue(_verify_receipt_at(receipt, FIXTURE_TIME + timedelta(seconds=1)))
        self.assertFalse(_verify_receipt_at(receipt, FIXTURE_TIME + timedelta(seconds=300)))

    def test_receipt_future_consumption_and_rollback_fail(self):
        receipt = self.evaluate(self.clean())
        self.assertFalse(_verify_receipt_at(receipt, FIXTURE_TIME - timedelta(seconds=1)))
        self.assertFalse(_verify_receipt_at(receipt, FIXTURE_TIME + timedelta(days=365)))

    def test_unknown_top_level_field_rejected(self):
        packet = self.clean(); packet["trust_me"] = True
        with self.assertRaises(EvidenceError):
            self.evaluate(packet)

    def test_bool_cannot_coerce_schema_version(self):
        packet = self.clean(); packet["schema_version"] = True
        with self.assertRaises(EvidenceError):
            self.evaluate(packet)

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "dup.json"
            path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
            with self.assertRaises(EvidenceError):
                load_json_strict(path)

    def test_nonfinite_json_number_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "nan.json"
            path.write_text('{"x":NaN}', encoding="utf-8")
            with self.assertRaises(EvidenceError):
                load_json_strict(path)

    def test_acceptance_corpus_exact_counts(self):
        manifest = run_acceptance()
        self.assertEqual(manifest["total_packets"], 80)
        self.assertEqual(manifest["ready"], 40)
        self.assertEqual(manifest["hold"], 40)
        self.assertEqual(set(manifest["hold_by_defect"].values()), {5})


if __name__ == "__main__":
    unittest.main()
