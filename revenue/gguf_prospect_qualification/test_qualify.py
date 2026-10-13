import json
import unittest
from pathlib import Path

from qualify import compile_packet, qualify, validate_packet

HERE = Path(__file__).resolve().parent


def candidate(name="Acme"):
    return {
        "organization": name,
        "commercial_entity": True,
        "public_business_channel": True,
        "gap_is_current": True,
        "budget_signal": "strong",
        "known_prior_contact": False,
        "known_do_not_resend": False,
        "evidence": {
            "gguf_control": {"verified": True, "url": "https://example.com/gguf"},
            "evaluation_harness": {"verified": True, "url": "https://example.com/eval"},
            "quantization_gap": {"verified": True, "url": "https://example.com/gap"},
        },
    }


class QualificationTests(unittest.TestCase):
    def test_ready_never_grants_send_authority(self):
        d = qualify(candidate())
        self.assertEqual(d.state, "RESEARCH_READY_SEND_AUTHORITY_PENDING")
        self.assertGreaterEqual(d.score, 75)
        self.assertFalse(d.send_authority)

    def test_dnr_is_hard_block(self):
        c = candidate()
        c["known_do_not_resend"] = True
        d = qualify(c)
        self.assertEqual(d.state, "DNR")
        self.assertEqual(d.score, 0)
        self.assertFalse(d.send_authority)

    def test_prior_contact_is_hard_block(self):
        c = candidate()
        c["known_prior_contact"] = True
        d = qualify(c)
        self.assertEqual(d.state, "HOLD_PRIOR_CONTACT")

    def test_missing_control_is_not_qualified(self):
        c = candidate()
        c["evidence"]["gguf_control"]["verified"] = False
        d = qualify(c)
        self.assertEqual(d.state, "RESEARCH_INCOMPLETE")
        self.assertIn("missing_verified_gguf_control", d.reasons)

    def test_verified_evidence_requires_https(self):
        c = candidate()
        c["evidence"]["gguf_control"]["url"] = "http://example.com"
        packet = {"schema_version": 1, "candidates": [c]}
        with self.assertRaises(ValueError):
            validate_packet(packet)

    def test_duplicate_organizations_rejected(self):
        packet = {"schema_version": 1, "candidates": [candidate(), candidate()]}
        with self.assertRaises(ValueError):
            validate_packet(packet)

    def test_repository_packet_compiles(self):
        packet = json.loads((HERE / "prospects.json").read_text())
        result = compile_packet(packet)
        self.assertFalse(result["send_authority"])
        by_name = {d["organization"]: d for d in result["decisions"]}
        self.assertTrue(by_name["CloudSurf Software LLC"]["state"].startswith("RESEARCH_READY"))
        self.assertEqual(by_name["XHToken / SparkLLM"]["state"], "RESEARCH_INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
