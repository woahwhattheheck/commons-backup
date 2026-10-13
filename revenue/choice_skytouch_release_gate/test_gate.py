from __future__ import annotations

from copy import deepcopy
import unittest

from .acceptance import make_bundle, run_acceptance
from .gate import (
    ReleaseEvidenceError,
    evaluate,
    load_strict_json,
    plan_effect_replay,
    snapshot_sha256,
    verify_receipt,
)


class ReleaseEvidenceGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = make_bundle(7)

    def test_valid_bundle_passes_and_has_no_external_authority(self) -> None:
        result = evaluate(self.bundle)
        self.assertEqual("PASS", result.receipt["status"])
        self.assertFalse(result.receipt["external_effect_authorized"])
        self.assertFalse(result.receipt["buyer_acceptance_claimed"])
        self.assertTrue(verify_receipt(result.receipt))
        self.assertEqual(2, len(result.receipt["effect_intents"]))

    def test_change_and_invariant_order_do_not_change_receipt(self) -> None:
        first = evaluate(self.bundle)
        other = deepcopy(self.bundle)
        other["changes"].reverse()
        other["invariants"].reverse()
        second = evaluate(other)
        self.assertEqual(first.receipt_sha256, second.receipt_sha256)

    def test_stale_base_holds(self) -> None:
        bundle = deepcopy(self.bundle)
        bundle["base_snapshot_sha256"] = "1" * 64
        receipt = evaluate(bundle).receipt
        self.assertEqual("HOLD", receipt["status"])
        self.assertIn("STALE_BASE", {row["code"] for row in receipt["failures"]})
        self.assertEqual([], receipt["effect_intents"])

    def test_property_id_drift_holds(self) -> None:
        bundle = deepcopy(self.bundle)
        bundle["candidate"]["property_id"] = "SYNTH-OTHER"
        codes = {row["code"] for row in evaluate(bundle).receipt["failures"]}
        self.assertIn("PROPERTY_ID_DRIFT", codes)

    def test_nonadvancing_revision_holds(self) -> None:
        bundle = deepcopy(self.bundle)
        bundle["candidate"]["revision"] = bundle["baseline"]["revision"]
        codes = {row["code"] for row in evaluate(bundle).receipt["failures"]}
        self.assertIn("NONADVANCING_REVISION", codes)

    def test_undeclared_mutation_holds(self) -> None:
        bundle = deepcopy(self.bundle)
        bundle["candidate"]["config"]["rates.default.currency"] = "EUR"
        codes = {row["code"] for row in evaluate(bundle).receipt["failures"]}
        self.assertIn("UNDECLARED_MUTATION", codes)

    def test_declared_noop_holds(self) -> None:
        bundle = deepcopy(self.bundle)
        bundle["candidate"]["config"]["integration.crm.retry_limit"] = 3
        codes = {row["code"] for row in evaluate(bundle).receipt["failures"]}
        self.assertIn("DECLARED_CHANGE_NOT_APPLIED", codes)

    def test_before_mismatch_holds(self) -> None:
        bundle = deepcopy(self.bundle)
        bundle["changes"][0]["before"] = 999
        codes = {row["code"] for row in evaluate(bundle).receipt["failures"]}
        self.assertIn("DECLARED_BEFORE_MISMATCH", codes)

    def test_after_mismatch_holds(self) -> None:
        bundle = deepcopy(self.bundle)
        bundle["changes"][0]["after"] = 999
        codes = {row["code"] for row in evaluate(bundle).receipt["failures"]}
        self.assertIn("DECLARED_AFTER_MISMATCH", codes)

    def test_failed_invariant_holds(self) -> None:
        bundle = deepcopy(self.bundle)
        bundle["candidate"]["config"]["inventory.overbooking_limit"] = 9
        bundle["changes"].append(
            {"path": "inventory.overbooking_limit", "before": 2, "after": 9, "effect_kind": "refresh"}
        )
        codes = {row["code"] for row in evaluate(bundle).receipt["failures"]}
        self.assertIn("INVARIANT_FAILED", codes)

    def test_missing_invariant_path_holds(self) -> None:
        bundle = deepcopy(self.bundle)
        bundle["invariants"].append({"name": "missing", "path": "missing.path", "expected": "x"})
        codes = {row["code"] for row in evaluate(bundle).receipt["failures"]}
        self.assertIn("INVARIANT_FAILED", codes)

    def test_duplicate_declared_path_rejected(self) -> None:
        bundle = deepcopy(self.bundle)
        bundle["changes"].append(deepcopy(bundle["changes"][0]))
        with self.assertRaisesRegex(ReleaseEvidenceError, "DUPLICATE_DECLARED_PATH"):
            evaluate(bundle)

    def test_duplicate_invariant_rejected(self) -> None:
        bundle = deepcopy(self.bundle)
        bundle["invariants"].append(deepcopy(bundle["invariants"][0]))
        with self.assertRaisesRegex(ReleaseEvidenceError, "DUPLICATE_INVARIANT"):
            evaluate(bundle)

    def test_unknown_top_level_field_rejected(self) -> None:
        bundle = deepcopy(self.bundle)
        bundle["surprise"] = True
        with self.assertRaisesRegex(ReleaseEvidenceError, "SCHEMA_KEYS"):
            evaluate(bundle)

    def test_nested_config_value_rejected(self) -> None:
        bundle = deepcopy(self.bundle)
        bundle["baseline"]["config"]["nested.bad"] = {"x": 1}
        with self.assertRaisesRegex(ReleaseEvidenceError, "NON_SCALAR_CONFIG_VALUE"):
            evaluate(bundle)

    def test_invalid_config_path_rejected(self) -> None:
        bundle = deepcopy(self.bundle)
        bundle["candidate"]["config"]["../escape"] = 1
        with self.assertRaisesRegex(ReleaseEvidenceError, "INVALID_CONFIG_PATH"):
            evaluate(bundle)

    def test_duplicate_json_key_rejected_before_materialization(self) -> None:
        with self.assertRaisesRegex(ReleaseEvidenceError, "DUPLICATE_JSON_KEY"):
            load_strict_json('{"schema":"x","schema":"y"}')

    def test_nonfinite_json_rejected(self) -> None:
        with self.assertRaisesRegex(ReleaseEvidenceError, "NONFINITE_JSON_NUMBER"):
            load_strict_json('{"x":NaN}')

    def test_non_object_receipt_is_invalid(self) -> None:
        self.assertFalse(verify_receipt(["not", "a", "receipt"]))

    def test_receipt_tamper_is_detected(self) -> None:
        receipt = deepcopy(evaluate(self.bundle).receipt)
        receipt["candidate_revision"] += 1
        self.assertFalse(verify_receipt(receipt))

    def test_first_effect_plan_emits_each_logical_effect_once(self) -> None:
        receipt = evaluate(self.bundle).receipt
        plan = plan_effect_replay(receipt)
        self.assertEqual(2, len(plan["new_effect_intents"]))
        self.assertEqual([], plan["collapsed_effect_ids"])
        self.assertFalse(plan["external_effects_performed"])

    def test_second_effect_plan_collapses_every_effect(self) -> None:
        receipt = evaluate(self.bundle).receipt
        first = plan_effect_replay(receipt)
        second = plan_effect_replay(receipt, first["effect_state"])
        self.assertEqual([], second["new_effect_intents"])
        self.assertEqual(2, len(second["collapsed_effect_ids"]))

    def test_effect_replay_conflict_fails_closed(self) -> None:
        receipt = evaluate(self.bundle).receipt
        first = plan_effect_replay(receipt)
        state = deepcopy(first["effect_state"])
        key = next(iter(state["effects"]))
        state["effects"][key] = "f" * 64
        with self.assertRaisesRegex(ReleaseEvidenceError, "EFFECT_REPLAY_CONFLICT"):
            plan_effect_replay(receipt, state)

    def test_same_release_id_plan_drift_conflicts_with_prior_effect_state(self) -> None:
        first_receipt = evaluate(self.bundle).receipt
        first_plan = plan_effect_replay(first_receipt)

        drifted = deepcopy(self.bundle)
        drifted["baseline"]["config"]["integration.crm.retry_limit"] = 4
        drifted["changes"][0]["before"] = 4
        drifted["base_snapshot_sha256"] = snapshot_sha256(drifted["baseline"])
        second_receipt = evaluate(drifted).receipt
        self.assertEqual("PASS", second_receipt["status"])

        with self.assertRaisesRegex(ReleaseEvidenceError, "EFFECT_REPLAY_CONFLICT"):
            plan_effect_replay(second_receipt, first_plan["effect_state"])

    def test_hold_receipt_cannot_be_planned(self) -> None:
        bundle = deepcopy(self.bundle)
        bundle["base_snapshot_sha256"] = "0" * 64
        receipt = evaluate(bundle).receipt
        with self.assertRaisesRegex(ReleaseEvidenceError, "RECEIPT_NOT_PASS"):
            plan_effect_replay(receipt)

    def test_invalid_receipt_cannot_be_planned(self) -> None:
        receipt = deepcopy(evaluate(self.bundle).receipt)
        receipt["status"] = "HOLD"
        with self.assertRaisesRegex(ReleaseEvidenceError, "INVALID_RECEIPT"):
            plan_effect_replay(receipt)

    def test_acceptance_fixture_proves_twenty_releases_and_replay(self) -> None:
        summary = run_acceptance()
        self.assertEqual(20, summary["passing_releases"])
        self.assertEqual(40, summary["declared_changes"])
        self.assertEqual(40, summary["first_pass_new_effect_intents"])
        self.assertEqual(40, summary["second_pass_collapsed_effect_intents"])
        self.assertEqual(0, summary["second_pass_new_effect_intents"])
        self.assertTrue(summary["all_receipts_verified"])
        self.assertFalse(summary["external_effects_performed"])
        self.assertEqual(
            {
                "failed_invariant": "INVARIANT_FAILED",
                "nonadvancing_revision": "NONADVANCING_REVISION",
                "property_drift": "PROPERTY_ID_DRIFT",
                "stale_base": "STALE_BASE",
                "undeclared_mutation": "UNDECLARED_MUTATION",
            },
            summary["hostile_classes"],
        )


if __name__ == "__main__":
    unittest.main()
