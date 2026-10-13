# SPDX-License-Identifier: Apache-2.0
"""Contract tests grounded in official engine 28b6d8af / kaggriculture.py.

Relevant engine facts:
- market queue is q[:maxMarketOrdersPerTurn] (default 10)
- HIRE and BUY_LAND execute at their literal queue index
- hires_today is public farm state and resets at end of day
- town/shop absorption is an integer per-step tick
"""
from __future__ import annotations

from copy import deepcopy
import os
import unittest
from unittest.mock import patch

import e11_rival_sell as e11
import e20_hire_guard as e20
import rival_model as rival
import shop_arb


def plant(watered: bool = False):
    return {"kind": "PLANT", "crop": "WHEAT", "watered_today": watered}


def observation(*, step=10, money=3000, hires_today=0, own_tiles=None, rival_unlocked=None, prices=None):
    return {
        "step": step,
        "player": 0,
        "farms": [
            {
                "money": money,
                "unlocked_quadrants": ["NW"],
                "hires_today": hires_today,
                "tiles": own_tiles if own_tiles is not None else [[None]],
                "hands": [],
            },
            {
                "money": 3000,
                "unlocked_quadrants": rival_unlocked or ["NW", "NE"],
                "hires_today": 0,
                "tiles": [[None]],
                "hands": [],
            },
        ],
        "market": {"prices": prices or {"WHEAT": 10}, "inventory": {"WHEAT": 50}},
        "town": {"unlocked_shops": ["BAKERY"]},
    }


class RivalModelContractTests(unittest.TestCase):
    def test_full_queue_is_exact_identity_and_tenth_order_survives(self):
        obs = observation()
        action = {"farmer": ["PASS"], "hands": [], "market": [["SELL", "WHEAT", i + 1] for i in range(10)]}
        before = deepcopy(action)
        with patch.dict(os.environ, {"TITAN_RIVAL_MODEL": "1"}):
            out, report = rival.apply_rival_model(obs, action, None, {"maxMarketOrdersPerTurn": 10})
        self.assertIs(out, action)
        self.assertEqual(out, before)
        self.assertEqual(out["market"][9], ["SELL", "WHEAT", 10])
        self.assertFalse(report["changed"])
        self.assertEqual(report["reason"], "EARLY_EXPANDER_NO_FREE_MARKET_SLOT")

    def test_land_is_appended_without_reordering_inherited_cash_dependencies(self):
        obs = observation(money=1000)
        inherited = [["BUY_SEED", "WHEAT", 1], ["SELL", "WHEAT", 2]]
        action = {"farmer": ["PASS"], "hands": [], "market": deepcopy(inherited)}
        with patch.dict(os.environ, {"TITAN_RIVAL_MODEL": "1"}):
            out, report = rival.apply_rival_model(obs, action, None, {"maxMarketOrdersPerTurn": 10})
        self.assertEqual(action["market"], inherited)  # input immutability
        self.assertEqual(out["market"][:2], inherited)
        self.assertEqual(out["market"][2], ["BUY_LAND"])
        self.assertEqual(report["insertion_index"], 2)
        self.assertTrue(report["changed"])

    def test_existing_land_order_is_not_duplicated(self):
        action = {"market": [["BUY_LAND"], ["SELL", "WHEAT", 1]]}
        with patch.dict(os.environ, {"TITAN_RIVAL_MODEL": "1"}):
            out, report = rival.apply_rival_model(observation(), action, None, {})
        self.assertIs(out, action)
        self.assertEqual(report["reason"], "EARLY_EXPANDER_ALREADY_QUEUED")

    def test_dumper_classification_does_not_bypass_e11(self):
        obs = observation(step=200, rival_unlocked=["NW"], prices={"WHEAT": 10})
        action = {"market": [["SELL", "WHEAT", 4]]}
        with patch.dict(os.environ, {"TITAN_RIVAL_MODEL": "1"}):
            out, report = rival.apply_rival_model(obs, action, {"WHEAT": 40}, {})
        self.assertIs(out, action)
        self.assertEqual(out["market"], [["SELL", "WHEAT", 4]])
        self.assertEqual(report["archetype"], "AGGRESSIVE_MARKET_DUMPER")
        self.assertEqual(report["reason"], "DUMPER_OBSERVED_E11_OWNS_SELLS")

    def test_terminal_action_is_identity(self):
        action = {"market": [["SELL", "WHEAT", 1]]}
        with patch.dict(os.environ, {"TITAN_RIVAL_MODEL": "1"}):
            out, report = rival.apply_rival_model(observation(step=718), action, None, {"episodeSteps": 720})
        self.assertIs(out, action)
        self.assertEqual(report["reason"], "NO_EDIT_TERMINAL_STEP")


class E11ContractTests(unittest.TestCase):
    @staticmethod
    def every_four_steps(_item, step, _shops, _config):
        return 2 if step % 4 == 0 else 0

    def test_non_tick_current_step_still_sees_real_future_absorption(self):
        obs = observation(step=5, prices={"WHEAT": 10})
        action = {"market": [["SELL", "WHEAT", 4], ["HIRE"]]}
        history = [(2, {"WHEAT": 40})]
        with patch.dict(os.environ, {"TITAN_E11_RIVAL_SELL": "1"}):
            out, report = e11.apply_e11(
                obs,
                action,
                history,
                {"episodeSteps": 12, "rival_dump_lookback_steps": 8, "e11_min_future_absorption": 2},
                self.every_four_steps,
            )
        # Last executable step is 10; ticks at 8 only => exactly 2, not 0 * horizon.
        self.assertEqual(report["future_absorption"]["WHEAT"], 2)
        self.assertEqual(out["market"], [[], ["HIRE"]])
        self.assertEqual(action["market"][0], ["SELL", "WHEAT", 4])
        self.assertTrue(report["changed"])

    def test_tick_current_step_is_not_multiplied_by_horizon(self):
        obs = observation(step=4, prices={"WHEAT": 10})
        action = {"market": [["SELL", "WHEAT", 4]]}
        with patch.dict(os.environ, {"TITAN_E11_RIVAL_SELL": "1"}):
            _out, report = e11.apply_e11(
                obs,
                action,
                [(1, {"WHEAT": 40})],
                {"episodeSteps": 12, "rival_dump_lookback_steps": 8},
                self.every_four_steps,
            )
        # Last executable step 10; ticks 4 and 8 => 4 units total.
        self.assertEqual(report["future_absorption"]["WHEAT"], 4)

    def test_fractional_absorption_fails_closed(self):
        obs = observation(step=4, prices={"WHEAT": 10})
        action = {"market": [["SELL", "WHEAT", 4]]}
        with patch.dict(os.environ, {"TITAN_E11_RIVAL_SELL": "1"}):
            out, report = e11.apply_e11(
                obs,
                action,
                [(1, {"WHEAT": 40})],
                {"episodeSteps": 12},
                lambda *_args: 1.5,
            )
        self.assertIs(out, action)
        self.assertFalse(report["changed"])
        self.assertEqual(report["reason"], "NO_OP_NONINTEGER_OR_NEGATIVE_ABSORPTION")

    def test_future_history_entries_are_ignored(self):
        obs = observation(step=5, prices={"WHEAT": 10})
        action = {"market": [["SELL", "WHEAT", 4]]}
        with patch.dict(os.environ, {"TITAN_E11_RIVAL_SELL": "1"}):
            out, report = e11.apply_e11(
                obs,
                action,
                [(6, {"WHEAT": 40})],
                {"episodeSteps": 12},
                self.every_four_steps,
            )
        self.assertIs(out, action)
        self.assertEqual(report["reason"], "NO_OP_FLAT_MARKET")

    def test_terminal_step_preserves_sale(self):
        action = {"market": [["SELL", "WHEAT", 4]]}
        with patch.dict(os.environ, {"TITAN_E11_RIVAL_SELL": "1"}):
            out, report = e11.apply_e11(
                observation(step=718), action, [(710, {"WHEAT": 40})], {"episodeSteps": 720}, self.every_four_steps
            )
        self.assertIs(out, action)
        self.assertEqual(report["reason"], "NO_OP_TERMINAL_STEP")


class E20ContractTests(unittest.TestCase):
    def test_low_demand_multiple_hires_respect_remaining_allowance(self):
        obs = observation(hires_today=2, own_tiles=[[plant(True)]])
        action = {
            "market": [["HIRE"], ["BUY_SEED", "WHEAT", 1], ["HIRE"], ["HIRE"], ["SELL", "WHEAT", 1]]
        }
        original = deepcopy(action)
        with patch.dict(os.environ, {"TITAN_E20_HIRE_GUARD": "1"}):
            out, report = e20.apply_hire_guard(
                obs, action, {"e20_max_hires_per_day": 3, "e20_min_unwatered_crops": 3}
            )
        self.assertEqual(action, original)
        self.assertEqual(out["market"], [["HIRE"], ["BUY_SEED", "WHEAT", 1], [], [], ["SELL", "WHEAT", 1]])
        self.assertEqual(report["dropped_indices"], [2, 3])
        self.assertTrue(report["changed"])

    def test_at_cap_drops_every_queued_hire_not_only_the_last(self):
        obs = observation(hires_today=3, own_tiles=[[plant(True)]])
        action = {"market": [["HIRE"], ["SELL", "WHEAT", 1], ["HIRE"]]}
        with patch.dict(os.environ, {"TITAN_E20_HIRE_GUARD": "1"}):
            out, report = e20.apply_hire_guard(obs, action, {})
        self.assertEqual(out["market"], [[], ["SELL", "WHEAT", 1], []])
        self.assertEqual(report["dropped_indices"], [0, 2])

    def test_real_unwatered_plant_demand_leaves_queue_untouched(self):
        obs = observation(hires_today=3, own_tiles=[[plant(False), plant(False), plant(False)]])
        action = {"market": [["HIRE"], ["HIRE"]]}
        with patch.dict(os.environ, {"TITAN_E20_HIRE_GUARD": "1"}):
            out, report = e20.apply_hire_guard(obs, action, {})
        self.assertIs(out, action)
        self.assertEqual(report["reason"], "DEMAND_JUSTIFIES_HIRES")

    def test_terminal_step_is_identity(self):
        action = {"market": [["HIRE"]]}
        with patch.dict(os.environ, {"TITAN_E20_HIRE_GUARD": "1"}):
            out, report = e20.apply_hire_guard(observation(step=718), action, {})
        self.assertIs(out, action)
        self.assertEqual(report["reason"], "NO_EDIT_TERMINAL_STEP")


class ShopAndFlagTests(unittest.TestCase):
    def test_shop_signal_never_changes_exact_absorption(self):
        with patch.dict(os.environ, {"TITAN_SHOP_ARB": "1"}):
            self.assertEqual(shop_arb.priority_multiplier("WHEAT", ["BAKERY"], {"BAKERY": ["EGG", "WHEAT"]}), 1.5)
            exact = shop_arb.preserve_exact_absorption(3)
        self.assertEqual(exact, 3)
        self.assertIsInstance(exact, int)

    def test_shop_boundary_rejects_fractional_engine_counts(self):
        with self.assertRaises(TypeError):
            shop_arb.preserve_exact_absorption(1.5)  # type: ignore[arg-type]

    def test_all_flags_off_are_object_identity(self):
        obs = observation()
        action = {"market": [["SELL", "WHEAT", 1], ["HIRE"]]}
        with patch.dict(
            os.environ,
            {
                "TITAN_RIVAL_MODEL": "0",
                "TITAN_E11_RIVAL_SELL": "0",
                "TITAN_E20_HIRE_GUARD": "0",
                "TITAN_SHOP_ARB": "0",
            },
        ):
            out1, _ = rival.apply_rival_model(obs, action, None, {})
            out2, _ = e11.apply_e11(obs, action, [], {}, self.every_four_steps if hasattr(self, "every_four_steps") else None)
            out3, _ = e20.apply_hire_guard(obs, action, {})
            mult = shop_arb.priority_multiplier("WHEAT", ["BAKERY"], {"BAKERY": ["WHEAT"]})
        self.assertIs(out1, action)
        self.assertIs(out2, action)
        self.assertIs(out3, action)
        self.assertEqual(mult, 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
