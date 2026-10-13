from __future__ import annotations

from copy import deepcopy
import unittest

from .acceptance import _t, fixture, policy, run_acceptance
from .gate import AUTHORITY, EvidenceError, compute_lineage_digest, evaluate, verify_receipt


class GateTests(unittest.TestCase):
    def ready(self):
        return evaluate(fixture(), policy(), evaluated_at=_t(30))

    def test_clean_fixture_ready(self):
        receipt = self.ready()
        self.assertEqual(receipt["status"], "READY")
        self.assertEqual(receipt["authority"], AUTHORITY)
        self.assertEqual(receipt["reasons"], [])

    def test_order_invariant_and_exact_duplicate_collapses(self):
        base = fixture()
        receipt = evaluate(base, policy(), evaluated_at=_t(30))
        replay = list(reversed(base)) + [deepcopy(base[0]), deepcopy(base[1])]
        self.assertEqual(receipt, evaluate(replay, policy(), evaluated_at=_t(30)))

    def test_changed_payload_same_event_id_holds(self):
        events = fixture()
        changed = deepcopy(events[2])
        changed["body"]["dataset_version"] = "other"
        events.append(changed)
        receipt = evaluate(events, policy(), evaluated_at=_t(30))
        self.assertEqual(receipt["status"], "HOLD")
        self.assertIn("EVENT_IDENTITY_CONFLICT", receipt["reasons"])

    def test_conflicting_identity_receipt_is_arrival_order_invariant(self):
        events = fixture()
        changed = deepcopy(events[2])
        changed["body"]["dataset_version"] = "other"
        forward = events + [changed]
        reverse = list(reversed(forward))
        self.assertEqual(evaluate(forward, policy(), evaluated_at=_t(30)), evaluate(reverse, policy(), evaluated_at=_t(30)))

    def test_model_must_match_change_control(self):
        events = fixture(); events[1]["body"]["model_version"] = "model-8"
        self.assertIn("MODEL_OUTSIDE_CHANGE_CONTROL", evaluate(events, policy(), evaluated_at=_t(30))["reasons"])

    def test_tools_must_match_change_control(self):
        events = fixture(); events[1]["body"]["tools"] = {"oee-query": "2.2"}
        self.assertIn("TOOLS_OUTSIDE_CHANGE_CONTROL", evaluate(events, policy(), evaluated_at=_t(30))["reasons"])

    def test_prompt_policy_must_match_change_control(self):
        events = fixture(); events[1]["body"]["prompt_policy_version"] = "prompt-policy-5"
        self.assertIn("PROMPT_POLICY_OUTSIDE_CHANGE_CONTROL", evaluate(events, policy(), evaluated_at=_t(30))["reasons"])

    def test_risk_must_be_in_change_control_and_policy(self):
        events = fixture(); events[1]["body"]["intended_use_risk"] = "HIGH"
        reasons = evaluate(events, policy(), evaluated_at=_t(30))["reasons"]
        self.assertIn("RISK_OUTSIDE_CHANGE_CONTROL", reasons)
        self.assertIn("RISK_OUTSIDE_POLICY", reasons)

    def test_execution_role_must_be_allowed(self):
        events = fixture(); events[1]["body"]["actor_role"] = "service-account"
        self.assertIn("EXECUTION_ROLE_NOT_ALLOWED", evaluate(events, policy(), evaluated_at=_t(30))["reasons"])

    def test_approver_role_must_be_allowed(self):
        events = fixture(); events[0]["body"]["approver_role"] = "manufacturing-analyst"
        self.assertIn("APPROVER_ROLE_NOT_ALLOWED", evaluate(events, policy(), evaluated_at=_t(30))["reasons"])

    def test_approval_binds_lineage_digest(self):
        events = fixture(); events[0]["body"]["lineage_digest"] = "0" * 64
        self.assertIn("APPROVAL_DIGEST_MISMATCH", evaluate(events, policy(), evaluated_at=_t(30))["reasons"])

    def test_source_reference_must_match(self):
        events = fixture(); events[1]["body"]["source_event_id"] = "src-999"
        self.assertIn("SOURCE_LINEAGE_MISMATCH", evaluate(events, policy(), evaluated_at=_t(30))["reasons"])

    def test_change_reference_must_match(self):
        events = fixture(); events[1]["body"]["change_event_id"] = "chg-999"
        self.assertIn("CHANGE_LINEAGE_MISMATCH", evaluate(events, policy(), evaluated_at=_t(30))["reasons"])

    def test_approval_reference_must_match(self):
        events = fixture(); events[0]["body"]["execution_event_id"] = "exe-999"
        self.assertIn("APPROVAL_LINEAGE_MISMATCH", evaluate(events, policy(), evaluated_at=_t(30))["reasons"])

    def test_policy_cannot_self_extend_historical_receipt(self):
        receipt = self.ready()
        self.assertTrue(verify_receipt(receipt, fixture(), policy(), evaluated_at=_t(31)))
        self.assertFalse(verify_receipt(receipt, fixture(), policy(), evaluated_at=_t(121)))

    def test_change_control_expiry_holds(self):
        self.assertIn("CHANGE_CONTROL_NOT_CURRENT", evaluate(fixture(), policy(), evaluated_at=_t(181))["reasons"])

    def test_source_staleness_holds(self):
        self.assertIn("SOURCE_STALE", evaluate(fixture(), policy(), evaluated_at=_t(361))["reasons"])

    def test_future_event_holds(self):
        events = fixture(); events[2]["occurred_at"] = _t(31)
        self.assertIn("FUTURE_EVENT", evaluate(events, policy(), evaluated_at=_t(30))["reasons"])

    def test_missing_kind_holds(self):
        events = [e for e in fixture() if e["kind"] != "HUMAN_APPROVAL"]
        self.assertIn("HUMAN_APPROVAL_COUNT", evaluate(events, policy(), evaluated_at=_t(30))["reasons"])

    def test_multiple_kind_holds(self):
        events = fixture(); extra = deepcopy(events[2]); extra["event_id"] = "src-extra"; events.append(extra)
        self.assertIn("SOURCE_COUNT", evaluate(events, policy(), evaluated_at=_t(30))["reasons"])

    def test_cross_artifact_bundle_holds(self):
        events = fixture(); events[1]["artifact_id"] = "artifact-other"
        self.assertIn("ARTIFACT_IDENTITY_CONFLICT", evaluate(events, policy(), evaluated_at=_t(30))["reasons"])

    def test_tampered_receipt_rejected(self):
        receipt = self.ready(); receipt["status"] = "HOLD"
        self.assertFalse(verify_receipt(receipt, fixture(), policy(), evaluated_at=_t(31), require_ready=False))

    def test_rehashed_forged_receipt_rejected_by_re_evaluation(self):
        receipt = self.ready(); events = fixture(); events[1]["body"]["model_version"] = "model-8"
        self.assertFalse(verify_receipt(receipt, events, policy(), evaluated_at=_t(31)))

    def test_boolean_integer_policy_rejected(self):
        p = policy(); p["max_source_age_s"] = True
        with self.assertRaises(EvidenceError): evaluate(fixture(), p, evaluated_at=_t(30))

    def test_noncanonical_hash_rejected(self):
        events = fixture(); events[2]["body"]["source_snapshot_hash"] = "A" * 64
        with self.assertRaises(EvidenceError): evaluate(events, policy(), evaluated_at=_t(30))

    def test_unknown_event_fields_rejected(self):
        events = fixture(); events[0]["surprise"] = True
        with self.assertRaises(EvidenceError): evaluate(events, policy(), evaluated_at=_t(30))

    def test_lineage_digest_is_content_bound(self):
        events = fixture(); source, change, execution = events[2], events[3], events[1]
        before = compute_lineage_digest(source, change, execution)
        execution = deepcopy(execution); execution["body"]["result_hash"] = "f" * 64
        self.assertNotEqual(before, compute_lineage_digest(source, change, execution))

    def test_acceptance_fixture(self):
        result = run_acceptance()
        self.assertEqual(result["counts"], {"READY": 80, "HOLD": 20})
        self.assertTrue(result["clean_order_invariant"])
        self.assertTrue(result["clean_verifies"])
        self.assertEqual(result["reason_counts"]["MODEL_OUTSIDE_CHANGE_CONTROL"], 5)
        self.assertEqual(result["reason_counts"]["APPROVAL_DIGEST_MISMATCH"], 20)
        self.assertEqual(result["reason_counts"]["EVENT_IDENTITY_CONFLICT"], 5)
        self.assertEqual(result["reason_counts"]["RISK_OUTSIDE_POLICY"], 5)


if __name__ == "__main__":
    unittest.main()
