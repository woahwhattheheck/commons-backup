from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = json.loads((HERE / "qualification_spec.json").read_text(encoding="utf-8"))

base_spec = importlib.util.spec_from_file_location("qualification", HERE / "qualification.py")
base = importlib.util.module_from_spec(base_spec)
assert base_spec.loader is not None
sys.modules["qualification"] = base
base_spec.loader.exec_module(base)

guard_spec = importlib.util.spec_from_file_location("alcorn_addendum_guard", HERE / "qualification_guarded.py")
guard = importlib.util.module_from_spec(guard_spec)
assert guard_spec.loader is not None
guard_spec.loader.exec_module(guard)

fixture_spec = importlib.util.spec_from_file_location("alcorn_base_fixtures", HERE / "test_qualification.py")
fixtures = importlib.util.module_from_spec(fixture_spec)
assert fixture_spec.loader is not None
fixture_spec.loader.exec_module(fixtures)


class AddendumGuardTests(unittest.TestCase):
    def test_current_evidence_records_addendum_and_stays_hold(self):
        evidence = base.load_json_strict(HERE / "current_evidence.json")
        result = guard.evaluate(SPEC, evidence)
        self.assertEqual(result["state"], "HOLD")
        finding = result["source_findings"][guard.ADDENDUM_ID]
        self.assertEqual(finding["sha256"], guard.ADDENDUM_SHA256)
        self.assertTrue(finding["vendor_proposal_structure_discretion"])
        self.assertTrue(finding["minimum_specifications_still_required"])
        self.assertFalse(finding["nvidia_oem_authority_granted"])
        self.assertFalse(finding["partner_credentials_inherited"])
        self.assertNotIn("amendments_review_evidence_id", result["blockers"])
        self.assertTrue(all(v is False for v in result["authority"].values()))

    def test_addendum_does_not_invent_a_new_teaming_permission_gate(self):
        evidence = fixtures.team_ready()
        predecessor = base.evaluate(SPEC, evidence)
        self.assertEqual(predecessor["state"], "TEAMING_READY")
        guarded = guard.evaluate(SPEC, evidence)
        self.assertEqual(guarded["state"], "TEAMING_READY")
        self.assertEqual(guarded["blockers"], predecessor["blockers"])
        self.assertFalse(guarded["source_findings"][guard.ADDENDUM_ID]["nvidia_oem_authority_granted"])

    def test_direct_prime_route_is_unchanged(self):
        evidence = fixtures.direct_ready()
        predecessor = base.evaluate(SPEC, evidence)
        result = guard.evaluate(SPEC, evidence)
        self.assertEqual(result["state"], "PRIME_READY")
        self.assertEqual(result["blockers"], predecessor["blockers"])
        self.assertTrue(result["source_findings"][guard.ADDENDUM_ID]["vendor_proposal_structure_discretion"])

    def test_addendum_digest_is_source_bound(self):
        spec = copy.deepcopy(SPEC)
        spec["buyer_addenda"][0]["sha256"] = "a" * 64
        with self.assertRaisesRegex(base.EvidenceError, "source binding mismatch for sha256"):
            guard.evaluate(spec, fixtures.team_ready())

    def test_addendum_message_id_is_source_bound(self):
        spec = copy.deepcopy(SPEC)
        spec["buyer_addenda"][0]["gmail_message_id"] = "invented-message"
        with self.assertRaisesRegex(base.EvidenceError, "source binding mismatch for gmail_message_id"):
            guard.evaluate(spec, fixtures.team_ready())

    def test_addendum_semantic_effect_cannot_be_rewritten_by_editing_spec(self):
        spec = copy.deepcopy(SPEC)
        spec["buyer_addenda"][0]["normalized_effect"] = "NVIDIA_AUTHORITY_GRANTED"
        with self.assertRaisesRegex(base.EvidenceError, "source binding mismatch for normalized_effect"):
            guard.evaluate(spec, fixtures.team_ready())

    def test_duplicate_bound_addendum_is_rejected(self):
        spec = copy.deepcopy(SPEC)
        spec["buyer_addenda"].append(copy.deepcopy(spec["buyer_addenda"][0]))
        with self.assertRaisesRegex(base.EvidenceError, "exactly one"):
            guard.evaluate(spec, fixtures.team_ready())

    def test_explicit_no_bid_stays_no_bid(self):
        evidence = fixtures.team_ready()
        evidence["explicit_disqualifier"] = {
            "fact": "buyer cancelled solicitation",
            "source": "buyer:addendum:cancel",
        }
        result = guard.evaluate(SPEC, evidence)
        self.assertEqual(result["state"], "NO_BID")
        self.assertEqual(result["reason"], "source_bound_explicit_disqualifier")


if __name__ == "__main__":
    unittest.main()
