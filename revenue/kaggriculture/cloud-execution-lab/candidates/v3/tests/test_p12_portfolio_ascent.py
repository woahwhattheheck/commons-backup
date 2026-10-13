# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE.parent / "overlay" / "p12_portfolio_ascent.py"
SPEC = importlib.util.spec_from_file_location("p12_portfolio_ascent", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)
PortfolioAscent = MODULE.PortfolioAscent
augment_action = MODULE.augment_action
sale_prefix_dominates = MODULE.sale_prefix_dominates


NOW = 100


def evaluation(item, *, gain=1.0, quantity=4, reference=None, plan=None, forced=False):
    return {
        "item": item,
        "quantity": quantity,
        "reference": reference if reference is not None else [(NOW, 0), (NOW + 1, quantity)],
        "plan": plan if plan is not None else [(NOW, 1), (NOW + 1, quantity - 1)],
        "worst_relative_gain": gain,
        "forced_feasibility": forced,
    }


class FakeDelegate:
    def __init__(self, action, diagnostics):
        self.action = action
        self.diagnostics = diagnostics
        self.calls = 0

    def act(self, obs, configuration=None):
        self.calls += 1
        return self.action


class PrefixDominanceTests(unittest.TestCase):
    def test_equal_total_earlier_sale_dominates(self):
        self.assertTrue(
            sale_prefix_dominates(
                [(NOW, 2), (NOW + 1, 2)],
                [(NOW, 0), (NOW + 1, 4)],
            )
        )

    def test_delayed_sale_does_not_dominate(self):
        self.assertFalse(
            sale_prefix_dominates(
                [(NOW, 1), (NOW + 1, 3)],
                [(NOW, 2), (NOW + 1, 2)],
            )
        )

    def test_malformed_plan_fails_closed(self):
        self.assertFalse(sale_prefix_dominates([(NOW, True)], [(NOW, 0)]))
        self.assertFalse(sale_prefix_dominates("not-a-plan", [(NOW, 0)]))


class AugmentActionTests(unittest.TestCase):
    def test_composes_two_independent_positive_products(self):
        action = {"farmer": ["PASS"], "hands": [], "market": [["SELL", "CARROT", 1]]}
        diagnostics = {
            "chosen": {"item": "CARROT"},
            "evaluations": [
                evaluation("CARROT", gain=9.0, plan=[(NOW, 1), (NOW + 1, 3)]),
                evaluation("MILK", gain=7.0, plan=[(NOW, 2), (NOW + 1, 2)]),
                evaluation("EGG", gain=3.0, plan=[(NOW, 1), (NOW + 1, 3)]),
            ],
        }
        out, additions = augment_action(action, diagnostics, step=NOW, max_market_orders=10)
        self.assertEqual(
            out["market"],
            [["SELL", "CARROT", 1], ["SELL", "MILK", 2], ["SELL", "EGG", 1]],
        )
        self.assertEqual([row["item"] for row in additions], ["MILK", "EGG"])

    def test_raw_order_cap_admits_only_highest_gain(self):
        action = {"market": [["SELL", "CARROT", 1], []]}
        diagnostics = {
            "chosen": {"item": "CARROT"},
            "evaluations": [
                evaluation("MILK", gain=2.0, plan=[(NOW, 1), (NOW + 1, 3)]),
                evaluation("EGG", gain=8.0, plan=[(NOW, 1), (NOW + 1, 3)]),
            ],
        }
        out, additions = augment_action(action, diagnostics, step=NOW, max_market_orders=3)
        self.assertEqual(out["market"][-1], ["SELL", "EGG", 1])
        self.assertEqual([row["item"] for row in additions], ["EGG"])

    def test_equal_gain_preserves_evaluation_order(self):
        action = {"market": [["SELL", "CARROT", 1]]}
        diagnostics = {
            "chosen": {"item": "CARROT"},
            "evaluations": [
                evaluation("MILK", gain=5.0, plan=[(NOW, 1), (NOW + 1, 3)]),
                evaluation("EGG", gain=5.0, plan=[(NOW, 1), (NOW + 1, 3)]),
            ],
        }
        out, additions = augment_action(action, diagnostics, step=NOW, max_market_orders=2)
        self.assertEqual(out["market"][-1], ["SELL", "MILK", 1])
        self.assertEqual(additions[0]["evaluation_ordinal"], 0)

    def test_delayed_positive_plan_is_not_composed(self):
        action = {"market": [["SELL", "CARROT", 1]]}
        diagnostics = {
            "chosen": {"item": "CARROT"},
            "evaluations": [
                evaluation(
                    "MILK",
                    gain=99.0,
                    reference=[(NOW, 2), (NOW + 1, 2)],
                    plan=[(NOW, 1), (NOW + 1, 3)],
                )
            ],
        }
        out, additions = augment_action(action, diagnostics, step=NOW, max_market_orders=10)
        self.assertEqual(out, action)
        self.assertEqual(additions, [])

    def test_zero_negative_nonfinite_and_forced_negative_are_rejected(self):
        action = {"market": []}
        diagnostics = {
            "evaluations": [
                evaluation("MILK", gain=0.0),
                evaluation("EGG", gain=-1.0, forced=True),
                evaluation("WOOL", gain=float("nan")),
                evaluation("HONEY", gain=float("inf")),
            ]
        }
        out, additions = augment_action(action, diagnostics, step=NOW, max_market_orders=10)
        self.assertEqual(out, action)
        self.assertEqual(additions, [])

    def test_post_unit_quantity_is_hard_bound(self):
        action = {"market": [["SELL", "MILK", 1]]}
        diagnostics = {
            "evaluations": [
                evaluation("MILK", gain=4.0, quantity=2, plan=[(NOW, 3)])
            ]
        }
        out, additions = augment_action(action, diagnostics, step=NOW, max_market_orders=10)
        self.assertEqual(out, action)
        self.assertEqual(additions, [])

    def test_existing_rows_are_counted_before_append(self):
        action = {"market": [["SELL", "MILK", 1], ["SELL", "MILK", 1]]}
        diagnostics = {
            "evaluations": [
                evaluation("MILK", gain=4.0, quantity=4, plan=[(NOW, 3), (NOW + 1, 1)])
            ]
        }
        out, additions = augment_action(action, diagnostics, step=NOW, max_market_orders=10)
        self.assertEqual(out["market"][-1], ["SELL", "MILK", 1])
        self.assertEqual(additions[0]["quantity"], 1)

    def test_future_only_improvement_does_not_create_hidden_state_action(self):
        action = {"market": []}
        diagnostics = {
            "evaluations": [
                evaluation(
                    "MILK",
                    gain=4.0,
                    reference=[(NOW, 0), (NOW + 1, 4)],
                    plan=[(NOW, 0), (NOW + 1, 4)],
                )
            ]
        }
        out, additions = augment_action(action, diagnostics, step=NOW, max_market_orders=10)
        self.assertEqual(out, action)
        self.assertEqual(additions, [])

    def test_malformed_matching_sell_row_fails_that_item_closed(self):
        action = {"market": [["SELL", "MILK", "bad"]]}
        diagnostics = {"evaluations": [evaluation("MILK", gain=4.0)]}
        out, additions = augment_action(action, diagnostics, step=NOW, max_market_orders=10)
        self.assertEqual(out, action)
        self.assertEqual(additions, [])

    def test_input_action_and_diagnostics_are_not_mutated(self):
        action = {"market": [["SELL", "CARROT", 1]]}
        diagnostics = {
            "chosen": {"item": "CARROT"},
            "evaluations": [evaluation("MILK", gain=4.0)],
        }
        action_before = copy.deepcopy(action)
        diagnostics_before = copy.deepcopy(diagnostics)
        augment_action(action, diagnostics, step=NOW, max_market_orders=10)
        self.assertEqual(action, action_before)
        self.assertEqual(diagnostics, diagnostics_before)

    def test_malformed_boundary_is_identity(self):
        action = {"market": []}
        diagnostics = {"evaluations": [evaluation("MILK", gain=4.0)]}
        for bad_step, bad_cap in ((True, 10), (NOW, True), (NOW, "10")):
            out, additions = augment_action(
                action,
                diagnostics,
                step=bad_step,
                max_market_orders=bad_cap,
            )
            self.assertEqual(out, action)
            self.assertEqual(additions, [])


class WrapperTests(unittest.TestCase):
    def test_wrapper_preserves_incumbent_choice_and_reports_addition(self):
        action = {"market": [["SELL", "CARROT", 1]]}
        diagnostics = {
            "chosen": {"item": "CARROT"},
            "evaluations": [evaluation("MILK", gain=4.0)],
        }
        delegate = FakeDelegate(action, diagnostics)
        wrapper = PortfolioAscent(delegate)
        out = wrapper.act({"step": NOW}, {"maxMarketOrdersPerTurn": 10})
        self.assertEqual(delegate.calls, 1)
        self.assertEqual(out["market"][-1], ["SELL", "MILK", 1])
        self.assertEqual(wrapper.diagnostics["chosen"], diagnostics["chosen"])
        self.assertEqual(wrapper.diagnostics["portfolio_additions"][0]["item"], "MILK")

    def test_wrapper_does_not_mutate_delegate_objects(self):
        action = {"market": [["SELL", "CARROT", 1]]}
        diagnostics = {
            "chosen": {"item": "CARROT"},
            "evaluations": [evaluation("MILK", gain=4.0)],
        }
        action_before = copy.deepcopy(action)
        diagnostics_before = copy.deepcopy(diagnostics)
        wrapper = PortfolioAscent(FakeDelegate(action, diagnostics))
        wrapper.act({"step": NOW}, {})
        self.assertEqual(action, action_before)
        self.assertEqual(diagnostics, diagnostics_before)

    def test_malformed_configuration_fails_closed(self):
        action = {"market": [["SELL", "CARROT", 1]]}
        diagnostics = {"evaluations": [evaluation("MILK", gain=4.0)]}
        wrapper = PortfolioAscent(FakeDelegate(action, diagnostics))
        out = wrapper.act({"step": NOW}, {"maxMarketOrdersPerTurn": "10"})
        self.assertEqual(out, action)
        self.assertEqual(wrapper.diagnostics["portfolio_additions"], [])


if __name__ == "__main__":
    unittest.main()
