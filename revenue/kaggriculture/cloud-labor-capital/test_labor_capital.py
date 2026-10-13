import copy
import dataclasses
import unittest
from labor_capital import (NO_ORDER, Projection, View, _configuration, alternatives,
                           choose_projection, hire_cost)


def result(cash=100, *, final=False, farm=None, market=None):
    return Projection(cash, 10, farm or {"plant": {"fed": False}}, market or {"MILK": 10000},
                      1, 5, 0, 0, ((4, 4),), 718 if final else 23, final)


class ContractTests(unittest.TestCase):
    def test_exact_daily_fibonacci(self):
        self.assertEqual([hire_cost(i) for i in range(10)], [1,1,2,3,5,8,13,21,34,55])

    def test_multiplier_and_zero(self):
        self.assertEqual(hire_cost(5, 3), 24)
        self.assertEqual(hire_cost(100, 0), 0)

    def test_invalid_fibonacci_arguments(self):
        for args in [(-1, 1), (True, 1), (2, -1), (2, 1.5)]:
            with self.assertRaises(ValueError):
                hire_cost(*args)

    def test_seed_is_not_a_runtime_input(self):
        cfg = _configuration({"seed": 9800101, "farmHandCostMult": 2})
        self.assertNotIn("seed", cfg)
        self.assertEqual(cfg.farmHandCostMult, 2)

    def test_view_copy_protocol(self):
        self.assertEqual(copy.deepcopy(View(nested=View(n=1))), {"nested": {"n": 1}})
        self.assertFalse(hasattr(View(), "missing"))

    def test_no_hires_no_candidates(self):
        self.assertEqual(alternatives({"market": [["SELL", "MILK", 2]]}, 10), [])

    def test_preserves_lockstep_positions_and_input(self):
        action = {"farmer": ["WATER"], "hands": [["CARE"]],
                  "market": [["HIRE"], ["SELL", "MILK", 3], ["HIRE"]]}
        before = copy.deepcopy(action)
        options = alternatives(action, 10)
        self.assertEqual(len(options), 2)
        self.assertEqual(options[0][1]["market"], [["HIRE"], ["SELL", "MILK", 3], NO_ORDER])
        self.assertEqual(options[1][1]["market"], [NO_ORDER, ["SELL", "MILK", 3], NO_ORDER])
        self.assertEqual(action, before)
        options[0][1]["hands"][0][0] = "PASS"
        self.assertEqual(action, before)

    def test_hires_past_real_order_limit_do_not_matter(self):
        self.assertEqual(alternatives({"market": [["SELL", "MILK", 1], ["HIRE"]]}, 1), [])

    def test_timed_hires_preserve_other_order_relative_order(self):
        action = {"market": [["HIRE"], ["BUY_SEED", "CARROT", 1], ["SELL", "MILK", 1], ["HIRE"]]}
        name, candidate = alternatives(action, 4, "timed")[-1]
        self.assertEqual(name, "fund_nonhire_orders_first")
        self.assertEqual(candidate["market"], [["BUY_SEED", "CARROT", 1], ["SELL", "MILK", 1], ["HIRE"], ["HIRE"]])

    def test_strict_value_gain_keeps_baseline_on_tie(self):
        self.assertIsNone(choose_projection(result(), [("same", result())]))
        self.assertEqual(choose_projection(result(), [("save", result(101))]), "save")

    def test_cannot_spend_future_production_as_zero(self):
        lost_asset = result(200, farm={"plant": None})
        self.assertIsNone(choose_projection(result(), [("bad", lost_asset)]))

    def test_inputs_and_displaced_stock_are_part_of_state(self):
        control = result(farm={"farm": {}, "private": {"seeds": {"WHEAT": 2}}})
        candidate = result(200, farm={"farm": {}, "private": {"seeds": {"WHEAT": 0}}})
        self.assertIsNone(choose_projection(control, [("bad", candidate)]))

    def test_market_state_must_match_before_final_boundary(self):
        self.assertIsNone(choose_projection(result(), [("shift", result(101, market={"MILK": 10001}))]))

    def test_final_cash_is_only_terminal_objective(self):
        self.assertEqual(choose_projection(result(final=True), [
            ("cash", result(101, final=True, farm={"stock": 0}, market={"MILK": 9999}))]), "cash")

    def test_mismatched_horizon_is_not_compared(self):
        self.assertIsNone(choose_projection(result(), [("later", result(1000, final=True))]))

    def test_nonfinite_cash_not_selected(self):
        self.assertIsNone(choose_projection(result(), [("bad", result(float("nan")))]))
        self.assertIsNone(choose_projection(result(), [("bad", result(float("inf")))]))

    def test_pick_best_valid_alternative_not_most_workers_removed(self):
        self.assertEqual(choose_projection(result(), [("one", result(105)), ("two", result(102))]), "one")

    def test_modes_are_explicit(self):
        with self.assertRaises(ValueError):
            alternatives({}, 10, "unknown")


if __name__ == "__main__":
    unittest.main()
