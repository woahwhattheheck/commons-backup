from __future__ import annotations

import unittest
from support import *


class CompilerGateTests(unittest.TestCase):
    def test_good_fixture_clears_strict_gate_in_both_mechanisms(self):
        result = compile_result(load_fixture("scenario_good.json"))
        self.assertEqual(result["status"], STATUS_READY)
        self.assertEqual(result["blockers"], [])
        self.assertEqual(len(result["mechanisms"]), 2)
        for row in result["mechanisms"]:
            self.assertTrue(row["strictly_above_90_percent"])
            self.assertEqual(row["allocative_efficiency"]["basis_points"], 10000)
            self.assertGreater(row["realized_surplus"], 0)
            self.assertEqual(len(row["provenance"]["final_state_sha256"]), 64)
        self.assertFalse(result["panel"]["external_llm_panel_executed"])
        self.assertFalse(result["authority"]["sbir_eligibility_proven"])

    def test_adversarial_fixture_fails_gate(self):
        result = compile_result(load_fixture("scenario_bad.json"))
        self.assertEqual(result["status"], STATUS_HOLD)
        self.assertEqual(result["mechanisms"][0]["realized_surplus"], 0)
        self.assertTrue(any(x.startswith("EFFICIENCY_GATE:") for x in result["blockers"]))
