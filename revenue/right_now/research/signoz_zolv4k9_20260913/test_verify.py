from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from verify import verify

ROOT = Path(__file__).parent
EVIDENCE = json.loads((ROOT / "evidence.json").read_text(encoding="utf-8"))
PATCH = json.loads((ROOT / "candidate_patch.json").read_text(encoding="utf-8"))


class ResearchCarrierTests(unittest.TestCase):
    def test_exact_packet_passes(self):
        receipt = verify(copy.deepcopy(EVIDENCE), copy.deepcopy(PATCH))
        self.assertEqual(receipt["status"], "PASS")
        self.assertFalse(receipt["transport_authorized"])

    def test_evidence_tamper_breaks_digest(self):
        evidence = copy.deepcopy(EVIDENCE)
        evidence["evidence"][0]["finding"] += " tamper"
        with self.assertRaisesRegex(ValueError, "evidence digest mismatch"):
            verify(evidence, copy.deepcopy(PATCH))

    def test_transport_cannot_be_enabled(self):
        patch = copy.deepcopy(PATCH)
        patch["recommended_state"]["transport_authorized"] = True
        with self.assertRaisesRegex(ValueError, "may not authorize transport"):
            verify(copy.deepcopy(EVIDENCE), patch)

    def test_internal_incident_cannot_be_claimed(self):
        evidence = copy.deepcopy(EVIDENCE)
        evidence["evidence"][0]["internal_incident_asserted"] = True
        with self.assertRaisesRegex(ValueError, "must not claim a SigNoz internal incident"):
            verify(evidence, copy.deepcopy(PATCH))

    def test_non_first_party_source_rejected(self):
        evidence = copy.deepcopy(EVIDENCE)
        evidence["evidence"][1]["source_url"] = "https://example.com/about"
        with self.assertRaisesRegex(ValueError, "non-first-party host"):
            verify(evidence, copy.deepcopy(PATCH))

    def test_missing_evidence_class_rejected(self):
        evidence = copy.deepcopy(EVIDENCE)
        evidence["evidence"] = evidence["evidence"][:2]
        with self.assertRaisesRegex(ValueError, "exactly three evidence classes"):
            verify(evidence, copy.deepcopy(PATCH))

    def test_ready_to_draft_cannot_be_promoted(self):
        patch = copy.deepcopy(PATCH)
        patch["recommended_state"]["ready_to_draft"] = True
        with self.assertRaisesRegex(ValueError, "may not auto-draft"):
            verify(copy.deepcopy(EVIDENCE), patch)

    def test_route_must_remain_unused(self):
        evidence = copy.deepcopy(EVIDENCE)
        route = next(r for r in evidence["evidence"] if r["kind"] == "first_party_route")
        route["route_used"] = True
        with self.assertRaisesRegex(ValueError, "must not use route"):
            verify(evidence, copy.deepcopy(PATCH))


if __name__ == "__main__":
    unittest.main()
