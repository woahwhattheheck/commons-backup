from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import math
import unittest

from .fixture import base_bundle, exact_replay, h, hostile_fixture
from .gate import ProvenanceInputError, _assess_at, authority_is_non_effecting, verify_receipt

NOW = datetime(2026, 9, 13, 9, 0, tzinfo=timezone.utc)


class GateTests(unittest.TestCase):
    def test_clean_bundle_ready(self):
        r = _assess_at(base_bundle(3), NOW)
        self.assertEqual(r["outcome"], "QA_REVIEW_READY_EVIDENCE_ONLY")
        self.assertEqual(r["stats"]["evidence_complete_events"], 3)
        self.assertTrue(authority_is_non_effecting(r))

    def test_private_clock_is_deterministic(self):
        b = base_bundle(3)
        self.assertEqual(_assess_at(b, NOW), _assess_at(deepcopy(b), NOW))

    def test_unknown_top_level_field_rejected(self):
        b = base_bundle(1); b["extra"] = True
        with self.assertRaisesRegex(ProvenanceInputError, "schema"):
            _assess_at(b, NOW)

    def test_secret_shaped_field_rejected(self):
        b = base_bundle(1); b["events"][0]["api_token"] = "abc"
        with self.assertRaises(ProvenanceInputError):
            _assess_at(b, NOW)

    def test_component_duplicate_rejected(self):
        b = base_bundle(1); b["components"].append(deepcopy(b["components"][0]))
        with self.assertRaisesRegex(ProvenanceInputError, "duplicated"):
            _assess_at(b, NOW)

    def test_component_conflict_rejected(self):
        b = base_bundle(1); c = deepcopy(b["components"][0]); c["sha256"] = h("other"); b["components"].append(c)
        with self.assertRaisesRegex(ProvenanceInputError, "conflicting"):
            _assess_at(b, NOW)

    def test_undeclared_component_rejected(self):
        b = base_bundle(1); b["events"][0]["tool_ref"]["component_id"] = "missing"
        with self.assertRaisesRegex(ProvenanceInputError, "not declared"):
            _assess_at(b, NOW)

    def test_component_digest_mismatch_rejected(self):
        b = base_bundle(1); b["events"][0]["tool_ref"]["sha256"] = h("wrong")
        with self.assertRaisesRegex(ProvenanceInputError, "digest"):
            _assess_at(b, NOW)

    def test_source_duplicate_rejected(self):
        b = base_bundle(1); b["source_snapshots"].append(deepcopy(b["source_snapshots"][0]))
        with self.assertRaisesRegex(ProvenanceInputError, "duplicated"):
            _assess_at(b, NOW)

    def test_source_digest_mismatch_holds(self):
        b = base_bundle(1); b["events"][0]["source_sha256"] = h("wrong")
        r = _assess_at(b, NOW)
        self.assertIn("SOURCE_DIGEST_MISMATCH", r["hold_codes"])

    def test_source_after_generation_holds(self):
        b = base_bundle(1); b["source_snapshots"][0]["captured_at"] = "2026-09-13T08:30:00Z"; b["events"][0]["generated_at"] = "2026-09-13T08:00:00Z"
        r = _assess_at(b, NOW); self.assertIn("SOURCE_AFTER_GENERATION", r["hold_codes"])

    def test_stale_source_holds(self):
        b = base_bundle(1); b["source_snapshots"][0]["captured_at"] = "2026-07-01T00:00:00Z"
        self.assertIn("SOURCE_STALE", _assess_at(b, NOW)["hold_codes"])

    def test_future_source_holds(self):
        b = base_bundle(1); b["source_snapshots"][0]["captured_at"] = "2026-09-13T09:06:00Z"; b["events"][0]["generated_at"] = "2026-09-13T09:07:00Z"; b["events"][0]["approval"]["approved_at"] = "2026-09-13T09:08:00Z"
        self.assertIn("SOURCE_FROM_FUTURE", _assess_at(b, NOW)["hold_codes"])

    def test_generation_future_holds(self):
        b = base_bundle(1); b["events"][0]["generated_at"] = "2026-09-13T09:06:00Z"; b["events"][0]["approval"]["approved_at"] = "2026-09-13T09:07:00Z"
        self.assertIn("GENERATION_FROM_FUTURE", _assess_at(b, NOW)["hold_codes"])

    def test_nonhuman_approval_holds(self):
        b = base_bundle(1); b["events"][0]["approval"]["reviewer_type"] = "agent"
        self.assertIn("HUMAN_APPROVAL_REQUIRED", _assess_at(b, NOW)["hold_codes"])

    def test_pending_approval_holds(self):
        b = base_bundle(1); b["events"][0]["approval"]["decision"] = "PENDING"
        self.assertIn("APPROVAL_NOT_GRANTED", _assess_at(b, NOW)["hold_codes"])

    def test_approval_wrong_artifact_holds(self):
        b = base_bundle(1); b["events"][0]["approval"]["artifact_sha256"] = h("wrong")
        self.assertIn("APPROVAL_ARTIFACT_MISMATCH", _assess_at(b, NOW)["hold_codes"])

    def test_approval_before_generation_holds(self):
        b = base_bundle(1); b["events"][0]["approval"]["approved_at"] = "2026-09-12T12:30:00Z"
        self.assertIn("APPROVAL_BEFORE_GENERATION", _assess_at(b, NOW)["hold_codes"])

    def test_exact_replay_collapses(self):
        r = _assess_at(exact_replay(base_bundle(2)), NOW)
        self.assertEqual(r["stats"]["input_events"], 3)
        self.assertEqual(r["stats"]["unique_events"], 2)
        self.assertEqual(r["stats"]["exact_replays_collapsed"], 1)
        self.assertEqual(r["outcome"], "QA_REVIEW_READY_EVIDENCE_ONLY")

    def test_changed_same_id_holds(self):
        b = base_bundle(2); other = deepcopy(b["events"][0]); other["query_sha256"] = h("changed"); b["events"].append(other)
        r = _assess_at(b, NOW); self.assertIn("EVENT_ID_CONFLICT", r["hold_codes"])

    def test_actor_email_rejected(self):
        b = base_bundle(1); b["events"][0]["actor_ref"] = "person@example.com"
        with self.assertRaises(ProvenanceInputError): _assess_at(b, NOW)

    def test_boolean_schema_version_rejected(self):
        b = base_bundle(1); b["schema_version"] = True
        with self.assertRaises(ProvenanceInputError): _assess_at(b, NOW)

    def test_nonfinite_json_rejected(self):
        b = base_bundle(1); b["events"][0]["intended_use"] = float("nan")
        with self.assertRaises(ProvenanceInputError): _assess_at(b, NOW)

    def test_receipt_verifies_exact_bundle(self):
        b = base_bundle(2); r = _assess_at(b, NOW)
        self.assertTrue(verify_receipt(b, r))

    def test_receipt_tamper_fails(self):
        b = base_bundle(2); r = _assess_at(b, NOW); r["outcome"] = "HOLD"
        self.assertFalse(verify_receipt(b, r))

    def test_bundle_tamper_fails_receipt(self):
        b = base_bundle(2); r = _assess_at(b, NOW); changed = deepcopy(b); changed["events"][0]["intended_use"] = "different reviewed use"
        self.assertFalse(verify_receipt(changed, r))

    def test_hostile_fixture_exact_matrix(self):
        r = _assess_at(hostile_fixture(), NOW)
        self.assertEqual(r["stats"]["unique_events"], 100)
        self.assertEqual(r["stats"]["evidence_complete_events"], 80)
        self.assertEqual(r["stats"]["hold_events"], 20)
        self.assertEqual(r["hold_codes"], ["APPROVAL_ARTIFACT_MISMATCH", "APPROVAL_NOT_GRANTED", "HUMAN_APPROVAL_REQUIRED", "SOURCE_STALE"])

    def test_hostile_fixture_receipt_stable(self):
        a = _assess_at(hostile_fixture(), NOW); b = _assess_at(hostile_fixture(), NOW)
        self.assertEqual(a["receipt_sha256"], b["receipt_sha256"])

    def test_all_authority_flags_false_even_ready(self):
        r = _assess_at(base_bundle(1), NOW)
        self.assertTrue(all(v is False for v in r["authority"].values()))

    def test_canonical_timestamp_required(self):
        b = base_bundle(1); b["events"][0]["generated_at"] = "2026-09-12T13:00:00+00:00"
        with self.assertRaisesRegex(ProvenanceInputError, "canonical UTC"):
            _assess_at(b, NOW)


if __name__ == "__main__":
    unittest.main()
