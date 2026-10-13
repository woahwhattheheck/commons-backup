from __future__ import annotations

import unittest
from support import *


class EfficiencyZeroTests(unittest.TestCase):
    def test_zero_feasible_surplus_is_hold_not_fake_100(self):
        scenario = load_fixture("scenario_good.json")
        scenario["scenario_id"] = "zero-surplus"
        scenario["traders"] = [
            {"trader_id":"buyer","side":"BUY","private_value":50,"quantity":1,"action_step":1,"strategy":"TRUTHFUL","shade":0},
            {"trader_id":"seller","side":"SELL","private_value":70,"quantity":1,"action_step":2,"strategy":"TRUTHFUL","shade":0},
        ]
        scenario["news"] = []
        result = compile_result(scenario)
        self.assertEqual(result["status"], STATUS_HOLD)
        self.assertIn("NO_POSITIVE_FEASIBLE_SURPLUS", result["blockers"])
        for row in result["mechanisms"]:
            self.assertIsNone(row["allocative_efficiency"]["basis_points"])
            self.assertFalse(row["strictly_above_90_percent"])
