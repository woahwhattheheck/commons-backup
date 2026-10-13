import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import handoff  # noqa: E402


def load_example(name):
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


class HandoffValidationTests(unittest.TestCase):
    def test_planned_release_is_reviewable_without_recorded_gaps(self):
        packet = load_example("planned_release.json")
        findings = handoff.validate(packet)
        self.assertFalse([f for f in findings if f.level == "ERROR"])
        self.assertEqual(
            handoff.assessment_state(findings),
            "REVIEWABLE_NO_RECORDED_GAPS",
        )
        self.assertTrue(any(f.code == "SYNTHETIC_PACKET" for f in findings))

    def test_urgent_maintenance_keeps_documentation_followup_visible(self):
        packet = load_example("urgent_maintenance.json")
        findings = handoff.validate(packet)
        self.assertFalse([f for f in findings if f.level == "ERROR"])
        self.assertEqual(
            handoff.assessment_state(findings),
            "REVIEWABLE_WITH_FOLLOWUP",
        )
        self.assertTrue(
            any(f.code == "DOCUMENTATION_FOLLOWUP_OPEN" for f in findings)
        )
        self.assertTrue(any(f.code == "NON_BLOCKING_OPEN_ITEM" for f in findings))

    def test_broken_evidence_reference_is_an_error(self):
        packet = load_example("planned_release.json")
        broken = copy.deepcopy(packet)
        broken["requirements"][0]["acceptance_evidence"] = ["EVID-NOT-THERE"]
        findings = handoff.validate(broken)
        self.assertTrue(
            any(f.code == "BROKEN_EVIDENCE_REFERENCE" for f in findings)
        )
        self.assertEqual(handoff.assessment_state(findings), "UNRELIABLE_PACKET")

    def test_requirement_without_support_link_is_a_gap_not_inferred_ready(self):
        packet = load_example("planned_release.json")
        broken = copy.deepcopy(packet)
        broken["requirements"][0]["support_readiness"] = []
        findings = handoff.validate(broken)
        self.assertTrue(
            any(f.code == "REQUIREMENT_HANDOFF_MISSING" for f in findings)
        )
        self.assertEqual(
            handoff.assessment_state(findings),
            "REVIEWABLE_WITH_FOLLOWUP",
        )

    def test_renderer_preserves_traceability_and_nonapproval_boundary(self):
        packet = load_example("planned_release.json")
        findings = handoff.validate(packet)
        report = handoff.render(packet, findings)
        self.assertIn("Requirement traceability", report)
        self.assertIn("REQ-01", report)
        self.assertIn("EVID-01", report)
        self.assertIn("SUP-01", report)
        self.assertIn("not release approval", report)

    def test_duplicate_evidence_id_is_an_error(self):
        packet = load_example("planned_release.json")
        broken = copy.deepcopy(packet)
        broken["acceptance_evidence"].append(
            copy.deepcopy(broken["acceptance_evidence"][0])
        )
        findings = handoff.validate(broken)
        self.assertTrue(any(f.code == "DUPLICATE_ID" for f in findings))


if __name__ == "__main__":
    unittest.main()
