import json
import tempfile
import unittest
from pathlib import Path

import assess_guidance as mod

ROOT = Path(__file__).parent
PACKET = ROOT / "fixtures" / "synthetic_guidance_packet.json"


class GuidanceUsabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guidance, cls.exercises = mod.load_packet(PACKET)
        cls.assessed = {g["guidance_id"]: mod.assess_guidance(g) for g in cls.guidance}

    def test_three_required_exercise_topics_exist(self):
        self.assertEqual({x["topic"] for x in self.exercises}, mod.TOPICS)

    def test_complete_current_pattern_is_usable(self):
        self.assertEqual(self.assessed["GUIDE-INPUT-01"].primary_state, "USABLE_GUIDANCE_EVIDENCED")
        self.assertEqual(self.assessed["GUIDE-AUTHZ-01"].primary_state, "USABLE_GUIDANCE_EVIDENCED")
        self.assertEqual(self.assessed["GUIDE-ERROR-01"].primary_state, "USABLE_GUIDANCE_EVIDENCED")

    def test_superseded_guidance_not_current_support(self):
        self.assertEqual(self.assessed["GUIDE-INPUT-OLD"].primary_state, "SUPERSEDED_NOT_CURRENT_SUPPORT")

    def test_partial_guidance_exposes_system_gaps(self):
        item = self.assessed["GUIDE-AUTHZ-PARTIAL"]
        self.assertEqual(item.primary_state, "PARTIAL_GUIDANCE_EVIDENCE")
        self.assertIn("owner role not supplied", item.gaps)
        self.assertIn("no decision/application triggers supplied", item.gaps)

    def test_unknown_status_remains_unknown(self):
        self.assertEqual(self.assessed["GUIDE-ERROR-UNKNOWN"].primary_state, "GUIDANCE_STATUS_UNKNOWN")

    def test_unknown_reference_fails_closed(self):
        payload = json.loads(PACKET.read_text())
        payload["exercises"][0]["guidance_refs"].append("DOES-NOT-EXIST")
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.json"
            p.write_text(json.dumps(payload))
            with self.assertRaisesRegex(mod.GuidanceError, "unknown guidance_refs"):
                mod.load_packet(p)

    def test_missing_required_topic_fails_closed(self):
        payload = json.loads(PACKET.read_text())
        payload["exercises"] = [x for x in payload["exercises"] if x["topic"] != "error_handling"]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.json"
            p.write_text(json.dumps(payload))
            with self.assertRaisesRegex(mod.GuidanceError, "coverage missing topics"):
                mod.load_packet(p)

    def test_sensitive_value_field_is_rejected(self):
        item = json.loads(json.dumps(self.guidance[0]))
        item["api_key"] = "fictional-but-out-of-scope"
        with self.assertRaisesRegex(mod.GuidanceError, "out of scope"):
            mod.validate_guidance(item)


if __name__ == "__main__":
    unittest.main()
