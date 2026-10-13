from __future__ import annotations

import copy
import unittest

from downselect import read_regular_json
from test_downselect import bind_evidence, ready_packet
from whitepaper import compile_whitepaper


class WhitepaperCompilerTests(unittest.TestCase):
    def test_selected_candidate_compiles_internal_source_packet_only(self) -> None:
        packet = bind_evidence(ready_packet())
        result = compile_whitepaper(packet)
        self.assertEqual(result["releaseState"], "INTERNAL_SOURCE_PACKET_ONLY")
        self.assertEqual(result["selectedCandidateId"], "alpha")
        self.assertIn("## Introduction — published weight 5%", result["markdown"])
        self.assertIn("## Army Benefits — published weight 25%", result["markdown"])
        self.assertIn("## Technical Approach — published weight 40%", result["markdown"])
        self.assertIn("Demonstrated metric", result["markdown"])
        self.assertIn("Transition path", result["markdown"])
        self.assertNotIn("woahwhattheheck/example", result["markdown"])
        self.assertFalse(result["officialTemplateApplied"])
        self.assertFalse(result["pageConformanceDetermined"])
        self.assertFalse(result["submissionAuthorized"])

    def test_hold_never_picks_candidate_for_prose(self) -> None:
        packet = ready_packet()
        packet["globalGates"]["ownershipControlEligible"] = {
            "state": "UNKNOWN",
            "evidenceRef": None,
        }
        result = compile_whitepaper(bind_evidence(packet))
        self.assertEqual(result["releaseState"], "BLOCKED_NO_INTERNAL_SELECTION")
        self.assertIsNone(result["selectedCandidateId"])
        self.assertIn("BLOCKED", result["markdown"])
        self.assertFalse(result["submissionAuthorized"])

    def test_current_real_packet_compiles_blocked(self) -> None:
        packet = read_regular_json("portfolio.current.json")
        result = compile_whitepaper(packet)
        self.assertEqual(result["releaseState"], "BLOCKED_NO_INTERNAL_SELECTION")
        self.assertIsNone(result["selectedCandidateId"])
        self.assertIn("source_generation:UNKNOWN", result["markdown"])
        self.assertFalse(result["submissionAuthorized"])

    def test_compiler_never_claims_template_or_page_conformance(self) -> None:
        result = compile_whitepaper(bind_evidence(ready_packet()))
        self.assertIn("Not the official ValidEval template", result["markdown"])
        self.assertIn("three-page conformance is not determined", result["markdown"])
        self.assertNotIn("submission-ready", result["markdown"].casefold())

    def test_output_is_deterministic_for_same_packet(self) -> None:
        packet = bind_evidence(ready_packet())
        first = compile_whitepaper(copy.deepcopy(packet))
        second = compile_whitepaper(copy.deepcopy(packet))
        self.assertEqual(first, second)
        self.assertEqual(len(first["receiptSha256"]), 64)


if __name__ == "__main__":
    unittest.main(verbosity=2)
