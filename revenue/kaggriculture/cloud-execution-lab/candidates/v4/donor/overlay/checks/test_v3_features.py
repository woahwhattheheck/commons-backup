# SPDX-License-Identifier: Apache-2.0
"""V3 lane contracts and wiring checks.  Standard library only:

    python -m unittest -v checks/test_v3_features.py

Contract cases carry the ARGUS semantic audit (candidates/v3-g01-argus-safe) into
the integrated tree with explicit `enabled` arguments instead of environment
flags.  Wiring cases check that the package keys parse, that every lane is the
exact identity when off, and that the runtime and both seller variants expose the
V3 seams.

Relevant engine facts (official 28b6d8af / kaggriculture.py):
- market queue is q[:maxMarketOrdersPerTurn] (default 10)
- HIRE and BUY_LAND execute at their literal queue index
- hires_today is public farm state and resets at end of day
- town/shop absorption is an integer per-step tick
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import e11_rival_sell as e11  # noqa: E402
import e20_hire_guard as e20  # noqa: E402
import rival_model as rival  # noqa: E402
import shop_arb  # noqa: E402
import scheduler  # noqa: E402
import frozen_selected  # noqa: E402
from titan_runtime import Features, TitanAgent  # noqa: E402


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


def every_four_steps(_item, step, _shops, _config):
    return 2 if step % 4 == 0 else 0


class RivalModelContractTests(unittest.TestCase):
    def test_full_queue_is_exact_identity_and_tenth_order_survives(self):
        obs = observation()
        action = {"farmer": ["PASS"], "hands": [], "market": [["SELL", "WHEAT", i + 1] for i in range(10)]}
        before = deepcopy(action)
        out, report = rival.apply_rival_model(obs, action, None, {"maxMarketOrdersPerTurn": 10}, enabled=True)
        self.assertIs(out, action)
        self.assertEqual(out, before)
        self.assertEqual(out["market"][9], ["SELL", "WHEAT", 10])
        self.assertFalse(report["changed"])
        self.assertEqual(report["reason"], "EARLY_EXPANDER_NO_FREE_MARKET_SLOT")

    def test_land_is_appended_without_reordering_inherited_cash_dependencies(self):
        obs = observation(money=1000)
        inherited = [["BUY_SEED", "WHEAT", 1], ["SELL", "WHEAT", 2]]
        action = {"farmer": ["PASS"], "hands": [], "market": deepcopy(inherited)}
        out, report = rival.apply_rival_model(obs, action, None, {"maxMarketOrdersPerTurn": 10}, enabled=True)
        self.assertEqual(action["market"], inherited)  # input immutability
        self.assertEqual(out["market"][:2], inherited)
        self.assertEqual(out["market"][2], ["BUY_LAND"])
        self.assertEqual(report["insertion_index"], 2)
        self.assertTrue(report["changed"])

    def test_existing_land_order_is_not_duplicated(self):
        action = {"market": [["BUY_LAND"], ["SELL", "WHEAT", 1]]}
        out, report = rival.apply_rival_model(observation(), action, None, {}, enabled=True)
        self.assertIs(out, action)
        self.assertEqual(report["reason"], "EARLY_EXPANDER_ALREADY_QUEUED")

    def test_dumper_classification_does_not_bypass_e11(self):
        obs = observation(step=200, rival_unlocked=["NW"], prices={"WHEAT": 10})
        action = {"market": [["SELL", "WHEAT", 4]]}
        out, report = rival.apply_rival_model(obs, action, {"WHEAT": 40}, {}, enabled=True)
        self.assertIs(out, action)
        self.assertEqual(out["market"], [["SELL", "WHEAT", 4]])
        self.assertEqual(report["archetype"], "AGGRESSIVE_MARKET_DUMPER")
        self.assertEqual(report["reason"], "DUMPER_OBSERVED_E11_OWNS_SELLS")

    def test_terminal_action_is_identity(self):
        action = {"market": [["SELL", "WHEAT", 1]]}
        out, report = rival.apply_rival_model(observation(step=718), action, None, {"episodeSteps": 720}, enabled=True)
        self.assertIs(out, action)
        self.assertEqual(report["reason"], "NO_EDIT_TERMINAL_STEP")


class E11ContractTests(unittest.TestCase):
    def test_non_tick_current_step_still_sees_real_future_absorption(self):
        obs = observation(step=5, prices={"WHEAT": 10})
        action = {"market": [["SELL", "WHEAT", 4], ["HIRE"]]}
        history = [(2, {"WHEAT": 40})]
        out, report = e11.apply_e11(
            obs, action, history,
            {"episodeSteps": 12, "rival_dump_lookback_steps": 8, "e11_min_future_absorption": 2},
            every_four_steps, enabled=True,
        )
        # Last executable step is 10; ticks at 8 only => exactly 2, not 0 * horizon.
        self.assertEqual(report["future_absorption"]["WHEAT"], 2)
        self.assertEqual(out["market"], [[], ["HIRE"]])
        self.assertEqual(action["market"][0], ["SELL", "WHEAT", 4])
        self.assertTrue(report["changed"])

    def test_tick_current_step_is_not_multiplied_by_horizon(self):
        obs = observation(step=4, prices={"WHEAT": 10})
        action = {"market": [["SELL", "WHEAT", 4]]}
        _out, report = e11.apply_e11(
            obs, action, [(1, {"WHEAT": 40})], {"episodeSteps": 12, "rival_dump_lookback_steps": 8},
            every_four_steps, enabled=True,
        )
        # Last executable step 10; ticks 4 and 8 => 4 units total.
        self.assertEqual(report["future_absorption"]["WHEAT"], 4)

    def test_fractional_absorption_fails_closed(self):
        obs = observation(step=4, prices={"WHEAT": 10})
        action = {"market": [["SELL", "WHEAT", 4]]}
        out, report = e11.apply_e11(obs, action, [(1, {"WHEAT": 40})], {"episodeSteps": 12}, lambda *_args: 1.5, enabled=True)
        self.assertIs(out, action)
        self.assertFalse(report["changed"])
        self.assertEqual(report["reason"], "NO_OP_NONINTEGER_OR_NEGATIVE_ABSORPTION")

    def test_future_history_entries_are_ignored(self):
        obs = observation(step=5, prices={"WHEAT": 10})
        action = {"market": [["SELL", "WHEAT", 4]]}
        out, report = e11.apply_e11(obs, action, [(6, {"WHEAT": 40})], {"episodeSteps": 12}, every_four_steps, enabled=True)
        self.assertIs(out, action)
        self.assertEqual(report["reason"], "NO_OP_FLAT_MARKET")

    def test_terminal_step_preserves_sale(self):
        action = {"market": [["SELL", "WHEAT", 4]]}
        out, report = e11.apply_e11(observation(step=718), action, [(710, {"WHEAT": 40})], {"episodeSteps": 720}, every_four_steps, enabled=True)
        self.assertIs(out, action)
        self.assertEqual(report["reason"], "NO_OP_TERMINAL_STEP")


class E20ContractTests(unittest.TestCase):
    def test_low_demand_multiple_hires_respect_remaining_allowance(self):
        obs = observation(hires_today=2, own_tiles=[[plant(True)]])
        action = {"market": [["HIRE"], ["BUY_SEED", "WHEAT", 1], ["HIRE"], ["HIRE"], ["SELL", "WHEAT", 1]]}
        original = deepcopy(action)
        out, report = e20.apply_hire_guard(obs, action, {"e20_max_hires_per_day": 3, "e20_min_unwatered_crops": 3}, enabled=True)
        self.assertEqual(action, original)
        self.assertEqual(out["market"], [["HIRE"], ["BUY_SEED", "WHEAT", 1], [], [], ["SELL", "WHEAT", 1]])
        self.assertEqual(report["dropped_indices"], [2, 3])
        self.assertTrue(report["changed"])

    def test_at_cap_drops_every_queued_hire_not_only_the_last(self):
        obs = observation(hires_today=3, own_tiles=[[plant(True)]])
        action = {"market": [["HIRE"], ["SELL", "WHEAT", 1], ["HIRE"]]}
        out, report = e20.apply_hire_guard(obs, action, {}, enabled=True)
        self.assertEqual(out["market"], [[], ["SELL", "WHEAT", 1], []])
        self.assertEqual(report["dropped_indices"], [0, 2])

    def test_real_unwatered_plant_demand_leaves_queue_untouched(self):
        obs = observation(hires_today=3, own_tiles=[[plant(False), plant(False), plant(False)]])
        action = {"market": [["HIRE"], ["HIRE"]]}
        out, report = e20.apply_hire_guard(obs, action, {}, enabled=True)
        self.assertIs(out, action)
        self.assertEqual(report["reason"], "DEMAND_JUSTIFIES_HIRES")

    def test_terminal_step_is_identity(self):
        action = {"market": [["HIRE"]]}
        out, report = e20.apply_hire_guard(observation(step=718), action, {}, enabled=True)
        self.assertIs(out, action)
        self.assertEqual(report["reason"], "NO_EDIT_TERMINAL_STEP")


class ShopAndFlagTests(unittest.TestCase):
    def test_shop_signal_never_changes_exact_absorption(self):
        self.assertEqual(shop_arb.priority_multiplier("WHEAT", ["BAKERY"], {"BAKERY": ["EGG", "WHEAT"]}, enabled=True), 1.5)
        exact = shop_arb.preserve_exact_absorption(3)
        self.assertEqual(exact, 3)
        self.assertIsInstance(exact, int)

    def test_shop_boundary_rejects_fractional_engine_counts(self):
        with self.assertRaises(TypeError):
            shop_arb.preserve_exact_absorption(1.5)  # type: ignore[arg-type]

    def test_all_lanes_off_are_object_identity(self):
        obs = observation()
        action = {"market": [["SELL", "WHEAT", 1], ["HIRE"]]}
        out1, rep1 = rival.apply_rival_model(obs, action, None, {})
        out2, rep2 = e11.apply_e11(obs, action, [(2, {"WHEAT": 40})], {}, every_four_steps)
        out3, rep3 = e20.apply_hire_guard(obs, action, {})
        mult = shop_arb.priority_multiplier("WHEAT", ["BAKERY"], {"BAKERY": ["WHEAT"]})
        self.assertIs(out1, action)
        self.assertIs(out2, action)
        self.assertIs(out3, action)
        self.assertEqual(mult, 1.0)
        for rep in (rep1, rep2, rep3):
            self.assertFalse(rep["enabled"])
            self.assertFalse(rep["changed"])


class PackageWiringTests(unittest.TestCase):
    def test_config_keys_parse_and_ship_off(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        features = Features(**data)
        for key in ("e11_rival_sell", "rival_model", "e20_hire_guard"):
            self.assertIn(key, data)
            self.assertIs(getattr(features, key), False)
        self.assertEqual(features.rival_dump_price_drop, 15.0)
        self.assertEqual(features.rival_dump_lookback_steps, 8)
        self.assertEqual(features.e11_min_future_absorption, 2)
        self.assertEqual(features.e20_max_hires_per_day, 3)
        self.assertEqual(features.e20_min_unwatered_crops, 3)
        self.assertEqual(features.g01_early_expander_step, 144)
        self.assertEqual(features.g01_land_cash_floor, 0.0)
        self.assertNotIn("shop_arb", data)

    def test_runtime_config_is_injected_only_when_a_key_is_on(self):
        self.assertFalse(TitanAgent(Features())._v3_active())
        agent = TitanAgent(Features(e20_hire_guard=True))
        self.assertTrue(agent._v3_active())
        cfg = agent._v3_config()
        self.assertEqual(cfg["e20_hire_guard"], True)
        self.assertEqual(cfg["e11_rival_sell"], False)
        self.assertEqual(cfg["rival_model"], False)
        self.assertEqual(cfg["params"]["e20_max_hires_per_day"], 3)
        self.assertEqual(cfg["params"]["g01_early_expander_step"], 144)

    def test_runtime_post_seam(self):
        action = {"farmer": ["PASS"], "hands": [], "market": [["HIRE"], ["SELL", "WHEAT", 1], ["HIRE"]]}
        agent = TitanAgent(Features())
        agent.diagnostics = {}
        self.assertIs(agent._v3_post(observation(), {}, action), action)
        agent = TitanAgent(Features(e20_hire_guard=True))
        agent.diagnostics = {}
        obs = observation(hires_today=3, own_tiles=[[plant(True)]])
        out = agent._v3_post(obs, {"titan_v3": agent._v3_config()}, action)
        self.assertEqual(out["market"], [[], ["SELL", "WHEAT", 1], []])
        self.assertTrue(agent.diagnostics["v3"]["e20_hire_guard"]["changed"])
        agent = TitanAgent(Features(rival_model=True))
        agent.diagnostics = {}
        out = agent._v3_post(observation(money=1000), {"maxMarketOrdersPerTurn": 10, "titan_v3": agent._v3_config()}, action)
        self.assertEqual(out["market"][-1], ["BUY_LAND"])
        self.assertEqual(out["market"][:3], action["market"])
        self.assertEqual(agent._v3_prev_prices, {"WHEAT": 10})

    def test_seller_pre_pending_seam_identity_off(self):
        for cls in (scheduler.SellScheduler, frozen_selected.FrozenSelected):
            seller = cls.__new__(cls)
            seller.diagnostics = {}
            out = {"farmer": ["PASS"], "hands": [], "market": [["SELL", "WHEAT", 4]]}
            self.assertIs(seller._v3_e11_before_pending(observation(), {"episodeSteps": 720}, out, 10), out)
            self.assertIs(seller._v3_e11_before_pending(observation(), {"titan_v3": {"e11_rival_sell": False}}, out, 10), out)
            self.assertNotIn("v3_e11", seller.diagnostics)

    def test_seller_pre_pending_seam_on_uses_exact_absorption(self):
        shop, products = next(iter(scheduler.m.SHOPS.items()))
        item = next(iter(products))
        obs = observation(step=5, prices={item: 10})
        obs["town"]["unlocked_shops"] = [shop]
        cfg = {"episodeSteps": 12, "townShopSellInterval": 4, "townCenterSellInterval": 24,
               "titan_v3": {"e11_rival_sell": True,
                            "params": {"rival_dump_price_drop": 15.0, "rival_dump_lookback_steps": 8,
                                       "e11_min_future_absorption": 1}}}
        seller = scheduler.SellScheduler.__new__(scheduler.SellScheduler)
        seller.diagnostics = {}
        seller._v3_price_history = [(2, {item: 40})]
        out = {"farmer": ["PASS"], "hands": [], "market": [["SELL", item, 4]]}
        result = seller._v3_e11_before_pending(obs, cfg, out, 5)
        report = seller.diagnostics["v3_e11"]
        self.assertTrue(report["enabled"])
        # step 8 is the only shop tick before the last executable step 10
        self.assertEqual(report["future_absorption"][item], scheduler.absorption(item, 8, [shop], cfg))
        self.assertTrue(report["changed"])
        self.assertEqual(result["market"], [[]])
        self.assertEqual(out["market"], [["SELL", item, 4]])
        self.assertEqual(seller._v3_price_history[-1], (5, {item: 10}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
