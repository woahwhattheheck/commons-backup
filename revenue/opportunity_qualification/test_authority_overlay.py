import copy
import unittest

from engine import HOLD, compile_qualification
from test_engine import AS_OF, PACKET, TRUSTED_COMPLETENESS, TRUSTED_COMPLETENESS_SHA256


class AuthorityOverlayTests(unittest.TestCase):
    def compile(self, packet):
        return compile_qualification(
            copy.deepcopy(packet),
            trusted_as_of=AS_OF,
            trusted_completeness=copy.deepcopy(TRUSTED_COMPLETENESS),
            trusted_completeness_sha256=TRUSTED_COMPLETENESS_SHA256,
        )

    def test_secondary_expired_deadline_cannot_force_no_bid(self):
        packet = copy.deepcopy(PACKET)
        packet["sources"].append(
            {
                "source_id": "deadline-mirror",
                "scope": "BUYER",
                "source_class": "SECONDARY",
                "url": "https://mirror.example.com/rfp/2026-001/deadline",
                "captured_at": "2026-09-13T09:00:00Z",
                "sha256": "a" * 64,
                "label": "Unverified mirror deadline",
            }
        )
        packet["opportunity"]["proposal_deadline"] = "2026-09-12T17:00:00Z"
        packet["opportunity"]["proposal_deadline_source_id"] = "deadline-mirror"
        receipt = self.compile(packet)
        self.assertEqual(receipt["disposition"], HOLD)
        self.assertIn("PROPOSAL_DEADLINE_NOT_OFFICIALLY_EVIDENCED", receipt["reasons"])

    def test_secondary_teaming_prohibition_cannot_close_team_route(self):
        packet = copy.deepcopy(PACKET)
        packet["sources"].append(
            {
                "source_id": "teaming-mirror",
                "scope": "BUYER",
                "source_class": "SECONDARY",
                "url": "https://mirror.example.com/rfp/2026-001/teaming",
                "captured_at": "2026-09-13T09:00:00Z",
                "sha256": "b" * 64,
                "label": "Unverified teaming summary",
            }
        )
        packet["opportunity"]["teaming"] = "PROHIBITED"
        packet["opportunity"]["teaming_source_id"] = "teaming-mirror"
        gate = packet["requirements"][1]
        gate["prime_state"] = "FAIL"
        gate["prime_evidence_ids"] = ["prime-registration"]
        receipt = self.compile(packet)
        self.assertEqual(receipt["disposition"], HOLD)
        self.assertTrue(receipt["team"]["possible"])
        self.assertIn("TEAMING_NOT_OFFICIALLY_EVIDENCED", receipt["team"]["reasons"])


if __name__ == "__main__":
    unittest.main()
