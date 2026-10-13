from __future__ import annotations

import unittest
from support import *


class EfficiencyNinetyTests(unittest.TestCase):
    def test_exactly_ninety_percent_fails_strictly_greater_gate(self):
        scenario = load_fixture("scenario_good.json")
        scenario["scenario_id"] = "exact-ninety"
        scenario["traders"] = [
            {"trader_id":"high-buyer","side":"BUY","private_value":11,"quantity":1,"action_step":1,"strategy":"TRUTHFUL","shade":0},
            {"trader_id":"seller-a","side":"SELL","private_value":2,"quantity":1,"action_step":2,"strategy":"TRUTHFUL","shade":0},
            {"trader_id":"low-buyer","side":"BUY","private_value":3,"quantity":1,"action_step":3,"strategy":"SHADED","shade":2},
            {"trader_id":"seller-b","side":"SELL","private_value":2,"quantity":1,"action_step":4,"strategy":"TRUTHFUL","shade":0},
        ]
        scenario["news"] = []
        result = compile_result(scenario)
        self.assertEqual(result["status"], STATUS_HOLD)
        for row in result["mechanisms"]:
            self.assertEqual(row["efficient_surplus"], 10)
            self.assertEqual(row["realized_surplus"], 9)
            self.assertEqual(row["allocative_efficiency"]["basis_points"], 9000)
            self.assertFalse(row["strictly_above_90_percent"])
