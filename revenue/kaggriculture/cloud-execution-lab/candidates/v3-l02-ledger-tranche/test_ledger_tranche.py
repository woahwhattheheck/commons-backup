# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import unittest

import ledger_tranche as l02


OBS = {"step": 680, "day": 28, "hour": 8, "player": 0}
CFG = {"turnsPerDay": 24, "episodeSteps": 720, "maxMarketOrdersPerTurn": 10}


class ProductTrancheTests(unittest.TestCase):
    def test_outside_window_is_object_identity(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        returned, report = l02.apply_product_tranche(action, {"CARROT": 40},
                                                     {**OBS, "step": 671, "day": 27}, CFG)
        self.assertIs(returned, action)
        self.assertFalse(report["changed"])

    def test_carrot_enlarges_active_row_without_touching_inactive_tail(self):
        market = [["HIRE"], [], ["SELL", "CARROT", 4], ["BUY_SEED", "WHEAT", 1],
                  [], [], [], [], [], [], ["SELL", "MILK", 99], {"opaque": [1, 2]}]
        action = {"farmer": ["PASS"], "hands": [], "market": market}
        before = copy.deepcopy(action)
        returned, report = l02.apply_product_tranche(
            action, {"CARROT": 40, "MILK": 8}, OBS, CFG)
        self.assertTrue(report["changed"])
        self.assertEqual(returned["market"][2], ["SELL", "CARROT", 32])
        self.assertEqual(returned["market"][10:], before["market"][10:])
        self.assertEqual(action, before)
        self.assertNotIn("MILK", report["changed_items"])

    def test_append_uses_only_trailing_active_slack_and_is_idempotent(self):
        action = {"farmer": ["PASS"], "hands": [], "market": [["HIRE"]]}
        shed = {"MILK": 7}
        first, report = l02.apply_product_tranche(action, shed, OBS, CFG)
        second, second_report = l02.apply_product_tranche(first, shed, OBS, CFG)
        self.assertEqual(first["market"], [["HIRE"], ["SELL", "MILK", 7]])
        self.assertTrue(report["changed"])
        self.assertIs(second, first)
        self.assertFalse(second_report["changed"])

    def test_no_append_when_executable_prefix_is_full(self):
        action = {"market": [["HIRE"] for _ in range(10)]}
        returned, report = l02.apply_product_tranche(action, {"MILK": 7}, OBS, CFG)
        self.assertIs(returned, action)
        self.assertFalse(report["changed"])
        self.assertEqual(report["edits"][0]["reason"], "no_trailing_executable_slack")

    def test_duplicate_carrot_rows_raise_total_not_each_row(self):
        action = {"market": [["SELL", "CARROT", 3], ["SELL", "CARROT", 7]]}
        returned, _ = l02.apply_product_tranche(action, {"CARROT": 40}, OBS, CFG)
        self.assertEqual(returned["market"], [["SELL", "CARROT", 3],
                                              ["SELL", "CARROT", 29]])
        self.assertEqual(l02.executable_sales(returned["market"], {"CARROT": 40}, 10)["CARROT"], 32)

    def test_first_n_fill_ignores_inactive_sale(self):
        market = [["HIRE"] for _ in range(10)] + [["SELL", "CARROT", 99]]
        self.assertEqual(l02.executable_sales(market, {"CARROT": 40}, 10).get("CARROT", 0), 0)

    def test_malformed_target_order_fails_closed(self):
        action = {"market": [["SELL", "CARROT", "32"]]}
        before = copy.deepcopy(action)
        returned, report = l02.apply_product_tranche(action, {"CARROT": 40}, OBS, CFG)
        self.assertIs(returned, action)
        self.assertEqual(action, before)
        self.assertFalse(report["changed"])

    def test_later_malformed_target_does_not_partially_commit_predecessor(self):
        """Predecessor CARROT must not commit when a later tracked SELL is malformed."""
        action = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [
                ["SELL", "CARROT", 4],
                ["SELL", "MILK"],  # len-2 malformed active target
            ],
        }
        before = copy.deepcopy(action)
        shed = {"CARROT": 40, "MILK": 7}
        returned, report = l02.apply_product_tranche(action, shed, OBS, CFG)
        self.assertIs(returned, action)
        self.assertEqual(action, before)
        self.assertFalse(report["changed"])
        self.assertEqual(report["reason"], "malformed_active_sell")
        self.assertEqual(returned["market"][0], ["SELL", "CARROT", 4])


class LedgerTests(unittest.TestCase):
    def test_reconciliation_uses_active_physical_fills_and_trims_future(self):
        planned = {"CARROT": [(681, 8), (690, 20)], "MILK": [(690, 2)]}
        pending = {"CARROT": 28, "MILK": 2}
        market = [["SELL", "CARROT", 32], ["SELL", "MILK", 5]]
        new_planned, new_pending, report = l02.reconciled_ledger(
            planned, pending, {"CARROT": 40, "MILK": 5}, market, 680, 10,
            ["CARROT", "MILK"])
        self.assertEqual(new_pending, {"CARROT": 8, "MILK": 0})
        self.assertEqual(new_planned, {"CARROT": [(681, 8)]})
        self.assertEqual(report["active_fills"], {"CARROT": 32, "MILK": 5})

    def test_apply_and_reconcile_is_transactional_on_bad_plan(self):
        class Consumer:
            planned = {"CARROT": [("tomorrow", 8)]}
            pending = {"CARROT": 36}
        consumer = Consumer()
        action = {"market": [["SELL", "CARROT", 4]]}
        old_planned = copy.deepcopy(consumer.planned)
        old_pending = copy.deepcopy(consumer.pending)
        returned, report = l02.apply_and_reconcile(
            consumer, action, {"CARROT": 40}, OBS, CFG)
        self.assertIs(returned, action)
        self.assertEqual(report["reason"], "ledger_reconciliation_failed")
        self.assertEqual(consumer.planned, old_planned)
        self.assertEqual(consumer.pending, old_pending)


class InstallTests(unittest.TestCase):
    def test_consumer_edit_occurs_before_checkpoint_state_is_read(self):
        class Consumer:
            def __init__(self):
                self.planned = {"CARROT": [(690, 28)]}
                self.pending = {"CARROT": 28}
                self.capture_post_units = False
                self.selected_post_units = None
                self.selected_post_units_binding = None
                self.diagnostics = {}
            def transform(self, obs, cfg, selected):
                self.selected_post_units = ({}, {"shed": {"CARROT": 40}})
                self.selected_post_units_binding = (
                    obs["step"], obs["player"], selected.get("farmer"), selected.get("hands", []))
                return copy.deepcopy(selected)

        class Agent:
            def __init__(self):
                self.consumer = None
                self.diagnostics = {}
                self.feed_seen = None
            def _initialize(self):
                self.consumer = Consumer()
            def _feed_stock_selected(self, obs, cfg, selected):
                self.feed_seen = copy.deepcopy(selected)
                return selected

        agent = Agent()
        l02.install(agent)
        agent._initialize()
        selected = {"farmer": ["PASS"], "hands": [],
                    "market": [["SELL", "CARROT", 4]]}
        returned = agent.consumer.transform(OBS, CFG, selected)
        self.assertEqual(returned["market"], [["SELL", "CARROT", 32]])
        self.assertEqual(agent.consumer.pending["CARROT"], 8)
        self.assertEqual(agent.consumer.planned["CARROT"], [(690, 8)])
        checkpoint = {"planned": copy.deepcopy(agent.consumer.planned),
                      "pending": copy.deepcopy(agent.consumer.pending)}
        self.assertEqual(checkpoint["pending"]["CARROT"], 8)

    def test_wheat_is_proposed_before_existing_feed_guard(self):
        class Consumer:
            selected_post_units = ({}, {"shed": {"WHEAT": 80}})
            selected_post_units_binding = (680, 0, ["PASS"], [])
        class Features:
            operating_stock = True
        class Agent:
            def __init__(self):
                self.consumer = Consumer()
                self.features = Features()
                self.diagnostics = {}
                self.feed_input = None
            def _initialize(self):
                pass
            def _feed_stock_selected(self, obs, cfg, selected):
                self.feed_input = copy.deepcopy(selected)
                out = copy.deepcopy(selected)
                # Simulate the canonical feed reserve retaining 60 of 80 units.
                for order in out["market"]:
                    if order and order[:2] == ["SELL", "WHEAT"]:
                        order[2] = min(order[2], 20)
                return out
        agent = Agent()
        l02.install(agent)
        selected = {"farmer": ["PASS"], "hands": [], "market": []}
        returned = agent._feed_stock_selected(OBS, CFG, selected)
        self.assertEqual(agent.feed_input["market"], [["SELL", "WHEAT", 57]])
        self.assertEqual(returned["market"], [["SELL", "WHEAT", 20]])
        self.assertEqual(agent.diagnostics["l02_wheat_tranche"]["after_feed_guard"], 20)

    def test_wheat_fails_closed_when_feed_guard_is_disabled(self):
        class Consumer:
            selected_post_units = ({}, {"shed": {"WHEAT": 80}})
            selected_post_units_binding = (680, 0, ["PASS"], [])
        class Features:
            operating_stock = False
        class Agent:
            def __init__(self):
                self.consumer = Consumer()
                self.features = Features()
                self.diagnostics = {}
            def _initialize(self):
                pass
            def _feed_stock_selected(self, obs, cfg, selected):
                return selected
        agent = Agent()
        l02.install(agent)
        selected = {"farmer": ["PASS"], "hands": [], "market": []}
        returned = agent._feed_stock_selected(OBS, CFG, selected)
        self.assertIs(returned, selected)
        self.assertEqual(agent.diagnostics["l02_wheat_tranche"]["reason"],
                         "feed_guard_disabled")

    def test_install_is_idempotent(self):
        class Agent:
            def _initialize(self): pass
            def _feed_stock_selected(self, obs, cfg, selected): return selected
        agent = Agent()
        self.assertIs(l02.install(agent), agent)
        initialize = agent._initialize
        self.assertIs(l02.install(agent), agent)
        self.assertIs(agent._initialize, initialize)


if __name__ == "__main__":
    unittest.main()
