# SPDX-License-Identifier: Apache-2.0
"""Predecessor-discriminating contracts for final crop repair binding."""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from candidate_runtime import FinalCropBindingAgent
from crop_release import commit_input_repair, units
from spatial_tempo import SpatialTempo
from titan_runtime import TitanAgent


def action(market):
    return {
        "farmer": ["PASS"],
        "hands": [["PASS"]],
        "market": deepcopy(market),
    }


def buy_case():
    inherited = [
        ["SELL", "CARROT", 1],
        ["BUY_LAND"],
        ["SELL", "STRAWBERRY", 2],
    ]
    expected = action(inherited + [["BUY_PRODUCT", "WHEAT", 3]])
    obs = {"step": 455, "player": 0}
    post = {"step": 455, "player": 0}
    proposal = {
        "step": 455,
        "player": 0,
        "slot": len(inherited),
        "units": 3,
        "kind": "buy",
        "unit_binding": deepcopy(units(expected)),
        "inherited_market": deepcopy(inherited),
        "expected_market": deepcopy(expected["market"]),
        "shared_stock_upper": 100,
        "funding_through": 457,
        "spending_upper": 99,
    }
    intent = {
        "status": "awaiting_observed_deposit",
        "player": 0,
        "input_repair_remaining": 3,
        "wheat_reserve_required": 3,
    }
    return intent, proposal, obs, post, expected


class LateQueueOwnershipTests(unittest.TestCase):
    def bare_agent(self, *, repair):
        agent = object.__new__(FinalCropBindingAgent)
        agent.features = SimpleNamespace(
            early_capital=True,
            market_pressure=True,
        )
        agent.spatial = SimpleNamespace(_crop_repair=repair)
        agent.diagnostics = {"status": "completed"}
        agent._crop_repair_live = repair is not None
        return agent

    def test_live_crop_repair_blocks_capital_and_final_pressure(self):
        selected = action(
            [
                ["SELL", "CARROT", 1],
                ["BUY_LAND"],
                ["BUY_PRODUCT", "WHEAT", 3],
            ]
        )
        capital = action(
            [
                ["SELL", "CARROT", 1],
                ["BUY_LAND"],
                ["BUY_PRODUCT", "WHEAT", 3],
            ][::-1]
        )
        pressure = action([["SELL", "CARROT", 1]])
        agent = self.bare_agent(repair={"kind": "buy"})

        with patch.object(
            TitanAgent,
            "_early_capital_selected",
            return_value=capital,
        ) as early, patch.object(
            TitanAgent,
            "_market_pressure_selected",
            return_value=pressure,
        ) as market_pressure:
            returned = agent._early_capital_selected({}, {}, selected)

        self.assertIs(returned, selected)
        early.assert_not_called()
        market_pressure.assert_not_called()
        self.assertEqual(
            agent.diagnostics["early_capital"]["reason"],
            "crop_input_repair_owns_current_queue",
        )
        self.assertEqual(
            agent.diagnostics["market_pressure"]["reason"],
            "crop_input_repair_owns_current_queue",
        )

    def test_ordinary_action_retains_capital_then_final_pressure(self):
        selected = action([["BUY_LAND"], ["SELL", "CARROT", 1]])
        capital = action([["SELL", "CARROT", 1], ["BUY_LAND"]])
        pressured = action([["SELL", "CARROT", 1], ["BUY_LAND"]])
        agent = self.bare_agent(repair=None)

        with patch.object(
            TitanAgent,
            "_early_capital_selected",
            return_value=capital,
        ) as early, patch.object(
            TitanAgent,
            "_market_pressure_selected",
            return_value=pressured,
        ) as market_pressure:
            returned = agent._early_capital_selected({}, {}, selected)

        self.assertIs(returned, pressured)
        early.assert_called_once()
        market_pressure.assert_called_once()
        self.assertFalse(getattr(agent, "_final_pressure_boundary", False))


class FinalizerOrderingTests(unittest.TestCase):
    class Spatial:
        def __init__(self, events):
            self.events_log = events
            self.events = []
            self.receipt_events = []
            self.sale_obligation = None
            self.crop_intent = {"status": "input_recovery_only"}
            self.crop_report = {}
            self._crop_repair = {"kind": "buy"}

        def observe_crop_receipts(self, *args):
            self.events_log.append("observe_crop_receipts")

        def guard_returned(self, obs, returned, **kwargs):
            self.events_log.append("guard_idle")
            return returned

        def guard_crop_returned(self, obs, returned, post):
            self.events_log.append(("guard_crop", deepcopy(returned["market"])))
            return returned

        def finish(self, *args):
            self.events_log.append("finish")

        def finish_crop(self, *args, **kwargs):
            self.events_log.append("finish_crop")

    class Harness(FinalCropBindingAgent):
        def _feed_stock_selected(self, obs, cfg, selected):
            self.order_events.append("feed")
            out = deepcopy(selected)
            out["market"].append(["SELL", "MILK", 1])
            return out

        def _early_capital_selected(self, obs, cfg, selected):
            self.order_events.append("capital_pressure")
            out = deepcopy(selected)
            out["market"].append(["SELL", "WOOL", 1])
            return out

    def make_harness(self):
        events = []
        agent = object.__new__(self.Harness)
        agent.order_events = events
        agent.spatial = self.Spatial(events)
        agent.history = None
        agent.quadrant = None
        agent._quadrant_admission = None
        agent.controller = SimpleNamespace(cur="MAIN")
        agent.features = SimpleNamespace(
            crop_release=True,
            terminal_history=False,
        )
        agent.diagnostics = {"status": "completed"}
        return agent, events

    def test_candidate_guards_exact_final_queue_before_receipt_commit(self):
        agent, events = self.make_harness()
        agent._crop_repair_live = True
        agent._crop_repair_still_bound = lambda *a, **k: True
        returned = agent._finish_production(
            {"step": 455, "player": 0},
            action([["BUY_PRODUCT", "WHEAT", 3]]),
            {},
        )
        self.assertIn("observe_crop_receipts", events)
        self.assertIn("guard_idle", events)
        self.assertTrue(any(isinstance(e, tuple) and e[0] == "guard_crop" for e in events))

    def test_current_predecessor_guards_before_late_market_mutators(self):
        agent, events = self.make_harness()
        TitanAgent._finish_production(
            agent,
            {"step": 455, "player": 0},
            action([["BUY_PRODUCT", "WHEAT", 3]]),
            {},
        )
        names = [event[0] if isinstance(event, tuple) else event for event in events]
        self.assertLess(names.index("guard_crop"), names.index("capital_pressure"))


class ReceiptBindingRegressionTests(unittest.TestCase):
    def test_current_order_can_execute_buy_but_poison_future_repair_state(self):
        intent, proposal, obs, post, expected = buy_case()
        owner = SpatialTempo.__new__(SpatialTempo)
        owner._crop_repair = proposal
        owner.crop_report = {}

        guarded_too_early = owner.guard_crop_returned(obs, expected, post)
        moved = deepcopy(guarded_too_early)
        repair = moved["market"].pop()
        moved["market"].insert(1, repair)
        predecessor = commit_input_repair(intent, proposal, obs, moved, post)

        self.assertIn(["BUY_PRODUCT", "WHEAT", 3], moved["market"][:10])
        self.assertTrue(predecessor["input_repair_unknown"])
        self.assertNotIn("input_repair_pending", predecessor)

        final_guarded = owner.guard_crop_returned(obs, expected, post)
        candidate = commit_input_repair(
            intent,
            proposal,
            obs,
            final_guarded,
            post,
        )
        self.assertNotIn("input_repair_unknown", candidate)
        self.assertEqual(
            candidate["input_repair_pending"]["expected_market"],
            expected["market"],
        )

    def test_withheld_sale_indices_are_equally_receipt_critical(self):
        inherited = [
            ["SELL", "WHEAT", 2],
            ["BUY_SEED", "WHEAT", 1],
            ["SELL", "WHEAT", 2],
            ["SELL", "STRAWBERRY", 1],
        ]
        expected = action(
            [
                [],
                ["BUY_SEED", "WHEAT", 1],
                [],
                ["SELL", "STRAWBERRY", 1],
            ]
        )
        obs = {"step": 457, "player": 0}
        post = {"step": 457, "player": 0}
        proposal = {
            "step": 457,
            "player": 0,
            "slot": len(inherited),
            "units": 3,
            "kind": "withhold",
            "unit_binding": deepcopy(units(expected)),
            "inherited_market": deepcopy(inherited),
            "expected_market": deepcopy(expected["market"]),
            "original_sale_slots": [0, 2],
            "sale_slots": [],
            "expected_sale_units": 0,
            "expected_shed_wheat": 3,
        }
        intent = {
            "player": 0,
            "input_repair_remaining": 3,
            "wheat_reserve_required": 3,
        }
        moved = deepcopy(expected)
        moved["market"] = [
            ["SELL", "STRAWBERRY", 1],
            [],
            ["BUY_SEED", "WHEAT", 1],
            [],
        ]

        predecessor = commit_input_repair(intent, proposal, obs, moved, post)
        candidate = commit_input_repair(intent, proposal, obs, expected, post)

        self.assertTrue(predecessor["input_repair_unknown"])
        self.assertIn("input_repair_pending", candidate)


class StaleProposalOwnershipTests(unittest.TestCase):
    def test_deadline_fallback_retires_stale_proposal_and_retains_late_transforms(self):
        intent, proposal, obs, post, expected = buy_case()
        fallback = action(proposal["inherited_market"])
        events = []

        class Spatial:
            def __init__(self):
                self.events_log = events
                self.events = []
                self.receipt_events = []
                self.sale_obligation = None
                self.crop_intent = intent
                self.crop_report = {}
                self._crop_repair = deepcopy(proposal)

            def observe_crop_receipts(self, *args):
                self.events_log.append("observe_crop_receipts")

            def guard_returned(self, obs, returned, **kwargs):
                self.events_log.append("guard_idle")
                return returned

            def guard_crop_returned(self, obs, returned, post):
                self.events_log.append(("guard_crop", getattr(self, "_crop_repair", None) is not None))
                p = self._crop_repair
                if p is None:
                    return returned
                from crop_release import units
                bound = (
                    int(obs["step"]) == p["step"]
                    and int(obs["player"]) == p["player"]
                    and units(returned) == p["unit_binding"]
                    and post is not None
                    and int(post["step"]) == p["step"]
                    and int(post["player"]) == p["player"]
                    and returned.get("market", []) == p["expected_market"]
                )
                if not bound and p["kind"] == "buy":
                    self.crop_report = {"changed": False, "reason": "final_unit_guard_canceled_unbound_repair"}
                return returned

            def finish(self, *args):
                self.events_log.append("finish")

            def finish_crop(self, *args, **kwargs):
                self.events_log.append("finish_crop")

        class Harness(FinalCropBindingAgent):
            def _feed_stock_selected(self, obs, cfg, selected):
                self.order_events.append("feed")
                out = deepcopy(selected)
                out["market"].append(["SELL", "MILK", 1])
                return out

            def _early_capital_selected(self, obs, cfg, selected):
                return FinalCropBindingAgent._early_capital_selected(self, obs, cfg, selected)

        agent = object.__new__(Harness)
        agent.order_events = events
        agent.spatial = Spatial()
        agent.history = None
        agent.quadrant = None
        agent._quadrant_admission = None
        agent.controller = SimpleNamespace(cur="MAIN")
        agent.features = SimpleNamespace(
            crop_release=True,
            terminal_history=False,
            early_capital=True,
            market_pressure=True,
            operating_stock=False,
        )
        agent.diagnostics = {"status": "deadline_fallback"}

        returned = agent._finish_production(obs, fallback, {})

        self.assertNotIn(["BUY_PRODUCT", "WHEAT", 3], returned["market"])
        self.assertIn("feed", events)
        self.assertFalse(getattr(agent, "_crop_repair_live", True))
        self.assertEqual(
            agent.spatial.crop_report.get("reason"),
            "final_unit_guard_canceled_unbound_repair",
        )

    def test_post_guard_returned_unit_mismatch_retires_and_allows_transforms(self):
        intent, proposal, obs, post, expected = buy_case()
        selected = deepcopy(expected)
        events = []

        class Spatial:
            def __init__(self):
                self.events_log = events
                self.events = []
                self.receipt_events = []
                self.sale_obligation = None
                self.crop_intent = intent
                self.crop_report = {}
                self._crop_repair = deepcopy(proposal)

            def observe_crop_receipts(self, *args):
                self.events_log.append("observe_crop_receipts")

            def guard_returned(self, obs, returned, **kwargs):
                self.events_log.append("guard_idle")
                out = deepcopy(returned)
                out["farmer"] = ["MOVE", "N"]
                return out

            def guard_crop_returned(self, obs, returned, post):
                self.events_log.append(("guard_crop", getattr(self, "_crop_repair", None) is not None))
                p = self._crop_repair
                if p is None:
                    return returned
                from crop_release import units
                bound = (
                    int(obs["step"]) == p["step"]
                    and int(obs["player"]) == p["player"]
                    and units(returned) == p["unit_binding"]
                    and post is not None
                    and int(post["step"]) == p["step"]
                    and int(post["player"]) == p["player"]
                    and returned.get("market", []) == p["expected_market"]
                )
                if not bound and p["kind"] == "buy":
                    market = returned.get("market", [])
                    if p["slot"] == len(market) - 1 and market and market[p["slot"]] == ["BUY_PRODUCT", "WHEAT", p["units"]]:
                        returned = deepcopy(returned)
                        returned["market"].pop()
                    self.crop_report = {"changed": False, "reason": "final_unit_guard_canceled_unbound_repair"}
                return returned

            def finish(self, *args):
                self.events_log.append("finish")

            def finish_crop(self, *args, **kwargs):
                self.events_log.append("finish_crop")

        class Harness(FinalCropBindingAgent):
            def _feed_stock_selected(self, obs, cfg, selected):
                self.order_events.append("feed")
                out = deepcopy(selected)
                out["market"].append(["SELL", "MILK", 1])
                return out

            def _early_capital_selected(self, obs, cfg, selected):
                return FinalCropBindingAgent._early_capital_selected(self, obs, cfg, selected)

            def _selected_snapshot(self, obs, returned=None):
                return {"step": obs["step"], "player": obs["player"]}

        agent = object.__new__(Harness)
        agent.order_events = events
        agent.spatial = Spatial()
        agent.history = object()
        agent.quadrant = None
        agent._quadrant_admission = None
        agent.controller = SimpleNamespace(cur="MAIN")
        agent.features = SimpleNamespace(
            crop_release=True,
            terminal_history=False,
            early_capital=True,
            market_pressure=True,
            operating_stock=False,
        )
        agent.diagnostics = {"status": "completed"}

        returned = agent._finish_production(obs, selected, {})

        self.assertNotIn(["BUY_PRODUCT", "WHEAT", 3], returned.get("market", []))
        self.assertIn("feed", events)
        self.assertFalse(getattr(agent, "_crop_repair_live", True))
        self.assertEqual(
            agent.spatial.crop_report.get("reason"),
            "final_unit_guard_canceled_unbound_repair",
        )


class ValidLiveOwnershipStillBlocksTests(unittest.TestCase):
    def test_still_bound_repair_suppresses_capital_and_pressure(self):
        intent, proposal, obs, post, expected = buy_case()
        events = []

        class Spatial:
            def __init__(self):
                self.events_log = events
                self.events = []
                self.receipt_events = []
                self.sale_obligation = None
                self.crop_intent = intent
                self.crop_report = {}
                self._crop_repair = deepcopy(proposal)

            def observe_crop_receipts(self, *args):
                self.events_log.append("observe_crop_receipts")

            def guard_returned(self, obs, returned, **kwargs):
                self.events_log.append("guard_idle")
                return returned

            def guard_crop_returned(self, obs, returned, post):
                self.events_log.append(("guard_crop", deepcopy(returned["market"])))
                return returned

            def finish(self, *args):
                self.events_log.append("finish")

            def finish_crop(self, *args, **kwargs):
                self.events_log.append("finish_crop")

        class Harness(FinalCropBindingAgent):
            def _feed_stock_selected(self, obs, cfg, selected):
                self.order_events.append("feed")
                return selected

            def _early_capital_selected(self, obs, cfg, selected):
                return FinalCropBindingAgent._early_capital_selected(self, obs, cfg, selected)

            def _selected_snapshot(self, obs, returned=None):
                return post

        agent = object.__new__(Harness)
        agent.order_events = events
        agent.spatial = Spatial()
        agent.history = object()
        agent.quadrant = None
        agent._quadrant_admission = None
        agent.controller = SimpleNamespace(cur="MAIN")
        agent.features = SimpleNamespace(
            crop_release=True,
            terminal_history=False,
            early_capital=True,
            market_pressure=True,
            operating_stock=False,
        )
        agent.diagnostics = {"status": "completed"}

        returned = agent._finish_production(obs, expected, {})

        self.assertEqual(returned["market"], expected["market"])
        self.assertTrue(getattr(agent, "_crop_repair_live", False))
        self.assertNotIn("feed", events)
        self.assertEqual(
            agent.diagnostics.get("early_capital", {}).get("reason"),
            "crop_input_repair_owns_current_queue",
        )


if __name__ == "__main__":
    unittest.main()
