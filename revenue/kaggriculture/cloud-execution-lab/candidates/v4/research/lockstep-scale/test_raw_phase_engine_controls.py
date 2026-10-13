from __future__ import annotations

import unittest

import raw_phase_contract
import raw_phase_engine_controls as controls


class EngineControlShapeTests(unittest.TestCase):
    def test_all_constructed_cases_satisfy_certificate(self):
        namespace = {"certify_adjacent_buy_phase": raw_phase_contract.certify_adjacent_buy_phase}
        rows = controls.validate_specs(namespace)
        self.assertEqual(len(rows), 3)
        self.assertEqual({row["direction"] for row in rows}, {"advance_one_slot", "delay_one_slot"})

    def test_only_wheat_buy_is_varied(self):
        for spec in controls.case_specs():
            before = spec["before_rows"]
            after = spec["after_rows"]
            flattened = [row for row in before + after if row and row[0] == "BUY_PRODUCT"]
            self.assertTrue(flattened)
            self.assertTrue(all(row == ["BUY_PRODUCT", "WHEAT", 10] for row in flattened))

    def test_control_has_no_rival_market_order(self):
        spec = next(row for row in controls.case_specs() if row["name"] == "no-rival-row-phase-control")
        self.assertEqual(spec["rival_rows"], [[], []])
        self.assertEqual(spec["expected_relation"], "delta_own_zero")


if __name__ == "__main__":
    unittest.main()
