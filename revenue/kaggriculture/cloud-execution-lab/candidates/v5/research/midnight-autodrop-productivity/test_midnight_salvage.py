# SPDX-License-Identifier: Apache-2.0
import importlib.util
import copy
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "midnight_salvage.py"
spec = importlib.util.spec_from_file_location("midnight_salvage", MODULE_PATH)
ms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ms)


def observation(*, step=263, tile=None, shed=None, inventories=None, farmer=(0, 0), hands=None):
    if hands is None:
        hands = []
    if inventories is None:
        inventories = [{} for _ in range(1 + len(hands))]
    if shed is None:
        shed = {}
    grid = [[None for _ in range(3)] for _ in range(3)]
    if tile is not None:
        grid[farmer[1]][farmer[0]] = copy.deepcopy(tile)
    return {
        "step": step,
        "player": 0,
        "farms": [
            {"farmer": list(farmer), "hands": [list(p) for p in hands], "tiles": grid},
            {"farmer": [0, 0], "hands": [], "tiles": copy.deepcopy(grid)},
        ],
        "private": {
            "shed": copy.deepcopy(shed),
            "inventories": copy.deepcopy(inventories),
        },
    }


class MidnightSalvageTests(unittest.TestCase):
    def test_non_final_tick_is_identity(self):
        action = {"farmer": ["PASS"], "hands": [], "market": [["HIRE"]]}
        out, report = ms.apply(observation(step=262), action, {})
        self.assertIs(out, action)
        self.assertEqual(report["status"], "not_final_tick")

    def test_ongoing_crop_harvest_replaces_move_without_market_change(self):
        tile = {"kind": "PLANT", "crop": "STRAWBERRY", "planted_day": 0, "yield_units": 3}
        action = {"farmer": ["WEST"], "hands": [], "market": [["SELL", "EGG", 2]]}
        out, report = ms.apply(observation(tile=tile), action, {})
        self.assertEqual(out["farmer"], ["HARVEST"])
        self.assertEqual(out["market"], action["market"])
        self.assertEqual(report["certified_eod_total"], 3)

    def test_one_shot_crop_is_intentionally_out_of_scope(self):
        tile = {"kind": "PLANT", "crop": "WHEAT", "planted_day": 0, "yield_units": 6}
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        out, report = ms.apply(observation(tile=tile), action, {})
        self.assertIs(out, action)
        self.assertEqual(report["status"], "no_safe_opportunity")

    def test_urgent_feed_beats_ready_animal_harvest(self):
        tile = {
            "kind": "PASTURE", "animal": "COW", "fed_today": False,
            "cared_today": False, "consecutive_unfed": 1,
            "yield_units": 4, "fertilizer_available": True,
        }
        action = {"farmer": ["DROP"], "hands": [], "market": []}
        out, report = ms.apply(observation(tile=tile, inventories=[{"WHEAT": 2}]), action, {})
        self.assertEqual(out["farmer"], ["FEED"])
        self.assertEqual(report["consumed_inventory"], 1)
        self.assertEqual(report["replacements"][0]["reason"], "prevent_escape")

    def test_ready_animal_harvests_when_not_escape_urgent(self):
        tile = {
            "kind": "PASTURE", "animal": "COW", "fed_today": True,
            "cared_today": False, "consecutive_unfed": 0,
            "yield_units": 4, "fertilizer_available": True,
        }
        action = {"farmer": ["SOUTH"], "hands": [], "market": []}
        out, report = ms.apply(observation(tile=tile), action, {})
        self.assertEqual(out["farmer"], ["HARVEST"])
        self.assertEqual(report["added_inventory"], 4)

    def test_collects_fertilizer_before_eod_refresh_overwrites_readiness(self):
        tile = {
            "kind": "COOP", "animal": "GOOSE", "fed_today": False,
            "cared_today": False, "consecutive_unfed": 0,
            "yield_units": 0, "fertilizer_available": True,
        }
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        out, _ = ms.apply(observation(tile=tile), action, {})
        self.assertEqual(out["farmer"], ["COLLECT_FERTILIZER"])

    def test_care_requires_feed_already_satisfied(self):
        tile = {
            "kind": "COOP", "animal": "GOOSE", "fed_today": True,
            "cared_today": False, "consecutive_unfed": 0,
            "yield_units": 0, "fertilizer_available": False,
        }
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        out, _ = ms.apply(observation(tile=tile), action, {})
        self.assertEqual(out["farmer"], ["CARE"])

    def test_capacity_blocks_candidate_added_output(self):
        tile = {"kind": "PLANT", "crop": "STRAWBERRY", "planted_day": 0, "yield_units": 1}
        action = {"farmer": ["DROP"], "hands": [], "market": []}
        out, report = ms.apply(
            observation(tile=tile, shed={"EGG": 99}, inventories=[{"MILK": 1}]),
            action, {},
        )
        self.assertIs(out, action)
        self.assertEqual(report["status"], "no_safe_opportunity")

    def test_capacity_allows_exact_fit(self):
        tile = {"kind": "PLANT", "crop": "STRAWBERRY", "planted_day": 0, "yield_units": 1}
        action = {"farmer": ["DROP"], "hands": [], "market": []}
        out, report = ms.apply(
            observation(tile=tile, shed={"EGG": 98}, inventories=[{"MILK": 1}]),
            action, {},
        )
        self.assertEqual(out["farmer"], ["HARVEST"])
        self.assertEqual(report["certified_eod_total"], 100)

    def test_preexisting_overflow_refuses_even_feed_rewrite(self):
        tile = {
            "kind": "COOP", "animal": "GOOSE", "fed_today": False,
            "cared_today": False, "consecutive_unfed": 1,
            "yield_units": 0, "fertilizer_available": False,
        }
        action = {"farmer": ["DROP"], "hands": [], "market": []}
        out, report = ms.apply(
            observation(tile=tile, shed={"EGG": 100}, inventories=[{"WHEAT": 1}]),
            action, {},
        )
        self.assertIs(out, action)
        self.assertEqual(report["status"], "preexisting_overflow_risk")

    def test_existing_other_harvest_is_reserved_in_capacity_certificate(self):
        target = {
            "kind": "COOP", "animal": "GOOSE", "fed_today": True,
            "cared_today": False, "consecutive_unfed": 0,
            "yield_units": 0, "fertilizer_available": True,
        }
        x = observation(tile=target, shed={"EGG": 98}, hands=[(1, 0)], inventories=[{}, {}])
        x["farms"][0]["tiles"][0][1] = {
            "kind": "PASTURE", "animal": "COW", "fed_today": True,
            "cared_today": True, "consecutive_unfed": 0,
            "yield_units": 2, "fertilizer_available": False,
        }
        action = {"farmer": ["PASS"], "hands": [["HARVEST"]], "market": []}
        out, report = ms.apply(x, action, {})
        self.assertIs(out, action)
        self.assertEqual(report["status"], "no_safe_opportunity")
        self.assertEqual(report["existing_output_upper_bound"], 2)

    def test_market_buy_inflow_is_reserved_in_capacity_certificate(self):
        tile = {
            "kind": "COOP", "animal": "GOOSE", "fed_today": True,
            "cared_today": False, "consecutive_unfed": 0,
            "yield_units": 0, "fertilizer_available": False,
        }
        action = {"farmer": ["PASS"], "hands": [], "market": [["BUY_PRODUCT", "WHEAT", 2]]}
        out, report = ms.apply(observation(tile=tile, shed={"EGG": 99}), action, {})
        self.assertIs(out, action)
        self.assertEqual(report["status"], "preexisting_overflow_risk")
        self.assertEqual(report["market_inflow_upper_bound"], 2)

    def test_market_cap_limits_buy_inflow_bound(self):
        tile = {
            "kind": "COOP", "animal": "GOOSE", "fed_today": True,
            "cared_today": False, "consecutive_unfed": 0,
            "yield_units": 0, "fertilizer_available": False,
        }
        action = {
            "farmer": ["PASS"], "hands": [],
            "market": [["SELL", "EGG", 1], ["BUY_PRODUCT", "WHEAT", 99]],
        }
        out, report = ms.apply(observation(tile=tile), action, {"maxMarketOrdersPerTurn": 1})
        self.assertEqual(out["farmer"], ["CARE"])
        self.assertEqual(report["market_inflow_upper_bound"], 0)

    def test_exact_public_identity_rejects_aliases(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        for bad in (True, "263", 263.0, -1):
            x = observation()
            x["step"] = bad
            out, report = ms.apply(x, action, {})
            self.assertIs(out, action)
            self.assertEqual(report["status"], "invalid_identity_or_config")
        for bad in (True, "0", 0.0, -1, 2):
            x = observation()
            x["player"] = bad
            out, report = ms.apply(x, action, {})
            self.assertIs(out, action)
            self.assertEqual(report["status"], "invalid_identity_or_config")

    def test_stacked_tile_only_first_unit_salvages(self):
        tile = {"kind": "PLANT", "crop": "STRAWBERRY", "planted_day": 0, "yield_units": 2}
        x = observation(tile=tile, hands=[(0, 0)], inventories=[{}, {}])
        action = {"farmer": ["PASS"], "hands": [["PASS"]], "market": []}
        out, report = ms.apply(x, action, {})
        self.assertEqual(out["farmer"], ["HARVEST"])
        self.assertEqual(out["hands"][0], ["PASS"])
        self.assertEqual(len(report["replacements"]), 1)


if __name__ == "__main__":
    unittest.main()
