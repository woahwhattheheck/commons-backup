from __future__ import annotations

from copy import deepcopy
import unittest

from .acceptance import contract, source, target_for, run_acceptance, _h
from .engine import AUTHORITY, UATError, evaluate, verify_receipt


class LabInterfaceUATTests(unittest.TestCase):
    def setUp(self):
        self.contract = contract()
        self.source = source(1)
        self.target = target_for(self.source)

    def test_clean_bundle_passes(self):
        receipt = evaluate(self.contract, [self.source], [self.target])
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["authority"], AUTHORITY)
        self.assertEqual(receipt["reasons"], [])

    def test_exact_retries_are_idempotent_and_order_invariant(self):
        first = evaluate(self.contract, [self.source], [self.target])
        second = evaluate(
            self.contract,
            [deepcopy(self.source), deepcopy(self.source)],
            [deepcopy(self.target), deepcopy(self.target)],
        )
        self.assertEqual(first, second)

    def test_source_same_id_changed_payload_holds(self):
        changed = deepcopy(self.source)
        changed["result_value"] = "42"
        receipt = evaluate(self.contract, [self.source, changed], [self.target])
        self.assertIn("SOURCE_EVENT_IDENTITY_CONFLICT", receipt["reasons"])

    def test_target_same_id_changed_payload_holds(self):
        changed = deepcopy(self.target)
        changed["result_value"] = "42"
        receipt = evaluate(self.contract, [self.source], [self.target, changed])
        self.assertIn("TARGET_EVENT_IDENTITY_CONFLICT", receipt["reasons"])

    def test_source_conflict_receipt_is_arrival_order_invariant(self):
        changed = deepcopy(self.source)
        changed["result_value"] = "42"
        a = evaluate(self.contract, [self.source, changed], [self.target])
        b = evaluate(self.contract, [changed, self.source], [self.target])
        self.assertEqual(a, b)

    def test_target_conflict_receipt_is_arrival_order_invariant(self):
        changed = deepcopy(self.target)
        changed["status"] = "CORRECTED"
        a = evaluate(self.contract, [self.source], [self.target, changed])
        b = evaluate(self.contract, [self.source], [changed, self.target])
        self.assertEqual(a, b)

    def test_missing_target_holds(self):
        receipt = evaluate(self.contract, [self.source], [])
        self.assertIn("MISSING_TARGET_EVENT", receipt["reasons"])

    def test_unexpected_target_holds(self):
        other = source(99)
        receipt = evaluate(self.contract, [self.source], [self.target, target_for(other)])
        self.assertIn("UNEXPECTED_TARGET_EVENT", receipt["reasons"])

    def test_multiple_targets_for_source_holds(self):
        other = deepcopy(self.target)
        other["event_id"] = "tgt-other"
        receipt = evaluate(self.contract, [self.source], [self.target, other])
        self.assertIn("MULTIPLE_TARGETS_FOR_SOURCE", receipt["reasons"])

    def test_result_parity_drift_holds(self):
        target = deepcopy(self.target)
        target["result_value"] = "42"
        receipt = evaluate(self.contract, [self.source], [target])
        self.assertIn("SOURCE_TARGET_PARITY_MISMATCH", receipt["reasons"])
        self.assertIn("result_value", receipt["details"]["parity"][0])

    def test_site_parity_drift_holds(self):
        target = deepcopy(self.target)
        target["site"] = "site-other"
        self.assertIn(
            "SOURCE_TARGET_PARITY_MISMATCH",
            evaluate(self.contract, [self.source], [target])["reasons"],
        )

    def test_contract_version_parity_drift_holds(self):
        target = deepcopy(self.target)
        target["contract_version"] = "wrong-version"
        self.assertIn(
            "SOURCE_TARGET_PARITY_MISMATCH",
            evaluate(self.contract, [self.source], [target])["reasons"],
        )

    def test_source_system_mismatch_holds(self):
        src = deepcopy(self.source)
        src["source_system"] = "other-lims"
        receipt = evaluate(self.contract, [src], [self.target])
        self.assertIn("SOURCE_SYSTEM_MISMATCH", receipt["reasons"])

    def test_target_system_mismatch_is_parity_failure(self):
        target = deepcopy(self.target)
        target["target_system"] = "other-target"
        self.assertIn(
            "SOURCE_TARGET_PARITY_MISMATCH",
            evaluate(self.contract, [self.source], [target])["reasons"],
        )

    def test_unmapped_test_code_is_quarantined(self):
        src = deepcopy(self.source)
        src["test_code"] = "NOVEL"
        target = target_for(src)
        receipt = evaluate(self.contract, [src], [target])
        self.assertIn("SOURCE_QUARANTINED", receipt["reasons"])
        self.assertIn("UNMAPPED_TEST_CODE", receipt["details"]["quarantine"][0])

    def test_unmapped_unit_is_quarantined(self):
        src = deepcopy(self.source)
        src["unit"] = "unknown_unit"
        target = target_for(src)
        receipt = evaluate(self.contract, [src], [target])
        self.assertIn("SOURCE_QUARANTINED", receipt["reasons"])
        self.assertIn("UNMAPPED_UNIT", receipt["details"]["quarantine"][0])

    def test_status_outside_contract_is_quarantined(self):
        src = deepcopy(self.source)
        src["status"] = "PRELIMINARY"
        target = target_for(src)
        receipt = evaluate(self.contract, [src], [target])
        self.assertIn("STATUS_OUTSIDE_CONTRACT", receipt["details"]["quarantine"][0])

    def test_specimen_outside_contract_is_quarantined(self):
        src = deepcopy(self.source)
        src["specimen_type"] = "CSF"
        target = target_for(src)
        receipt = evaluate(self.contract, [src], [target])
        self.assertIn("SPECIMEN_OUTSIDE_CONTRACT", receipt["details"]["quarantine"][0])

    def test_out_of_order_correction_chain_passes(self):
        first = source(7)
        second = source(7, revision=2, supersedes=first["event_id"])
        receipt = evaluate(
            self.contract,
            [second, first],
            [target_for(second), target_for(first)],
        )
        self.assertEqual(receipt["status"], "PASS")

    def test_broken_correction_predecessor_holds(self):
        first = source(7)
        second = source(7, revision=2, supersedes="wrong-event")
        receipt = evaluate(
            self.contract,
            [first, second],
            [target_for(first), target_for(second)],
        )
        self.assertIn("BROKEN_CORRECTION_LINEAGE", receipt["reasons"])

    def test_noncontiguous_revision_holds(self):
        first = source(7)
        third = source(7, revision=3, supersedes=first["event_id"])
        receipt = evaluate(
            self.contract,
            [first, third],
            [target_for(first), target_for(third)],
        )
        self.assertIn("NONCONTIGUOUS_REVISION_LINEAGE", receipt["reasons"])

    def test_revision_one_cannot_supersede(self):
        src = deepcopy(self.source)
        src["supersedes_event_id"] = "old"
        with self.assertRaises(UATError):
            evaluate(self.contract, [src], [self.target])

    def test_revision_two_requires_predecessor(self):
        src = deepcopy(self.source)
        src["revision"] = 2
        with self.assertRaises(UATError):
            evaluate(self.contract, [src], [self.target])

    def test_inverted_reference_interval_rejected(self):
        src = deepcopy(self.source)
        src["reference_low"] = "200"
        src["reference_high"] = "100"
        with self.assertRaises(UATError):
            evaluate(self.contract, [src], [self.target])

    def test_unknown_source_field_rejected(self):
        src = deepcopy(self.source)
        src["patient_name"] = "must-not-appear"
        with self.assertRaises(UATError):
            evaluate(self.contract, [src], [self.target])

    def test_unknown_target_field_rejected(self):
        target = deepcopy(self.target)
        target["diagnosis"] = "must-not-appear"
        with self.assertRaises(UATError):
            evaluate(self.contract, [self.source], [target])

    def test_mapping_digest_must_bind_mapping_content(self):
        c = deepcopy(self.contract)
        c["code_map"]["GLU"] = "DIFFERENT"
        with self.assertRaises(UATError):
            evaluate(c, [self.source], [self.target])

    def test_mapping_digest_malformed_rejected(self):
        c = deepcopy(self.contract)
        c["mapping_sha256"] = "A" * 64
        with self.assertRaises(UATError):
            evaluate(c, [self.source], [self.target])

    def test_decimal_numeric_type_rejected(self):
        src = deepcopy(self.source)
        src["result_value"] = 13.7
        with self.assertRaises(UATError):
            evaluate(self.contract, [src], [self.target])

    def test_boolean_revision_rejected(self):
        src = deepcopy(self.source)
        src["revision"] = True
        with self.assertRaises(UATError):
            evaluate(self.contract, [src], [self.target])

    def test_tampered_receipt_rejected(self):
        receipt = evaluate(self.contract, [self.source], [self.target])
        receipt["status"] = "HOLD"
        self.assertFalse(verify_receipt(receipt, self.contract, [self.source], [self.target], require_pass=False))

    def test_receipt_wrong_evidence_rejected(self):
        receipt = evaluate(self.contract, [self.source], [self.target])
        changed = deepcopy(self.target)
        changed["result_value"] = "42"
        self.assertFalse(verify_receipt(receipt, self.contract, [self.source], [changed]))

    def test_hold_receipt_can_verify_only_when_pass_not_required(self):
        receipt = evaluate(self.contract, [self.source], [])
        self.assertTrue(verify_receipt(receipt, self.contract, [self.source], [], require_pass=False))
        self.assertFalse(verify_receipt(receipt, self.contract, [self.source], [], require_pass=True))

    def test_acceptance_matrix(self):
        result = run_acceptance()
        self.assertEqual(result["counts"], {"PASS": 160, "HOLD": 40})
        self.assertTrue(result["replay_idempotent"])
        self.assertTrue(result["receipt_verifies"])
        self.assertEqual(result["reason_counts"]["MISSING_TARGET_EVENT"], 8)
        self.assertEqual(result["reason_counts"]["SOURCE_EVENT_IDENTITY_CONFLICT"], 8)
        self.assertEqual(result["reason_counts"]["BROKEN_CORRECTION_LINEAGE"], 8)
        self.assertEqual(result["reason_counts"]["SOURCE_QUARANTINED"], 8)
        self.assertEqual(result["reason_counts"]["SOURCE_TARGET_PARITY_MISMATCH"], 8)


if __name__ == "__main__":
    unittest.main()
