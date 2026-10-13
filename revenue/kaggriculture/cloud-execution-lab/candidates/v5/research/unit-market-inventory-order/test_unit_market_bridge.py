from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "unit_market_bridge", HERE / "unit_market_bridge.py"
)
bridge = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(bridge)


def fixture(
    final_action,
    *,
    shed=None,
    inv=None,
    market=None,
    hands=False,
    pos=(4, 4),
    config=None,
):
    selected = {
        "farmer": ["PASS"] if hands else final_action,
        "hands": [final_action] if hands else [],
        "market": market if market is not None else [["SELL", "MILK", 4]],
    }
    farm = {"farmer": [4, 4], "hands": [list(pos)] if hands else []}
    if not hands:
        farm["farmer"] = list(pos)
    private = {
        "shed": shed if shed is not None else {"MILK": 1},
        "inventories": (
            [{}, inv if inv is not None else {"MILK": 3}]
            if hands
            else [inv if inv is not None else {"MILK": 3}]
        ),
    }
    return selected, farm, private, {} if config is None else config


class UnitMarketBridgeTests(unittest.TestCase):
    def test_pass_places_exact_sell_shortfall_without_mutating_parent(self):
        selected, farm, private, config = fixture(["PASS"])
        original = copy.deepcopy(selected)
        out, report = bridge.transform(selected, farm, private, config)
        self.assertEqual(out["farmer"], ["PLACE", "MILK", 3])
        self.assertEqual(report["reason"], "place_sale_shortfall")
        self.assertEqual(selected, original)

    def test_pass_bridge_clips_to_current_shed_room(self):
        selected, farm, private, config = fixture(
            ["PASS"], shed={"MILK": 1, "EGG": 98}, inv={"MILK": 3}
        )
        out, report = bridge.transform(selected, farm, private, config)
        self.assertEqual(out["farmer"], ["PLACE", "MILK", 1])
        self.assertEqual(report["quantity"], 1)

    def test_pickup_that_would_starve_sale_becomes_pass(self):
        selected, farm, private, config = fixture(
            ["PICKUP", "MILK", 3], shed={"MILK": 4}, inv={}
        )
        out, report = bridge.transform(selected, farm, private, config)
        self.assertEqual(out["farmer"], ["PASS"])
        self.assertEqual(report["reason"], "reserve_sale_stock")

    def test_pickup_is_capped_to_excess_and_preserves_trailing_metadata(self):
        selected, farm, private, config = fixture(
            ["PICKUP", "MILK", 3, "tag"], shed={"MILK": 6}, inv={}
        )
        out, report = bridge.transform(selected, farm, private, config)
        self.assertEqual(out["farmer"], ["PICKUP", "MILK", 2, "tag"])
        self.assertEqual(report["replacement_pickup"], 2)

    def test_pickup_already_preserving_sale_is_identity(self):
        selected, farm, private, config = fixture(
            ["PICKUP", "MILK", 3], shed={"MILK": 7}, inv={}
        )
        out, report = bridge.transform(selected, farm, private, config)
        self.assertIs(out, selected)
        self.assertEqual(report["classification"], "NO_OP")

    def test_operating_stock_is_excluded(self):
        selected, farm, private, config = fixture(
            ["PICKUP", "WHEAT", 3],
            shed={"WHEAT": 4},
            inv={},
            market=[["SELL", "WHEAT", 4]],
        )
        out, report = bridge.transform(selected, farm, private, config)
        self.assertIs(out, selected)
        self.assertEqual(report["reason"], "no_sale_only_sell")

    def test_earlier_shed_mutation_blocks(self):
        selected = {
            "farmer": ["DROP"],
            "hands": [["PASS"]],
            "market": [["SELL", "MILK", 4]],
        }
        farm = {"farmer": [4, 4], "hands": [[4, 4]]}
        private = {
            "shed": {"MILK": 1},
            "inventories": [{"EGG": 1}, {"MILK": 3}],
        }
        out, report = bridge.transform(selected, farm, private, {})
        self.assertIs(out, selected)
        self.assertEqual(report["reason"], "earlier_shed_mutation")

    def test_market_cap_ignores_suffix_sell(self):
        market = [["SELL", "MILK", 1], ["SELL", "MILK", 50]]
        selected, farm, private, config = fixture(
            ["PASS"],
            shed={"MILK": 1},
            inv={"MILK": 3},
            market=market,
            config={"maxMarketOrdersPerTurn": 1},
        )
        out, report = bridge.transform(selected, farm, private, config)
        self.assertIs(out, selected)
        self.assertEqual(report["reason"], "ambiguous_or_no_pass_bridge")

    def test_sell_trailing_metadata_is_engine_valid(self):
        selected, farm, private, config = fixture(
            ["PASS"], market=[["SELL", "MILK", "4", "meta"]]
        )
        out, _ = bridge.transform(selected, farm, private, config)
        self.assertEqual(out["farmer"], ["PLACE", "MILK", 3])

    def test_nonlist_market_is_identity(self):
        selected, farm, private, config = fixture(["PASS"])
        selected["market"] = {"bad": "shape"}
        out, report = bridge.transform(selected, farm, private, config)
        self.assertIs(out, selected)
        self.assertEqual(report["reason"], "no_sale_only_sell")

    def test_nonfinite_sell_quantity_fails_closed(self):
        selected, farm, private, config = fixture(
            ["PASS"], market=[["SELL", "MILK", float("inf")]]
        )
        out, report = bridge.transform(selected, farm, private, config)
        self.assertIs(out, selected)
        self.assertEqual(report["reason"], "malformed_sell_quantity")

    def test_ambiguous_two_item_shortfall_does_not_choose(self):
        market = [["SELL", "MILK", 2], ["SELL", "WOOL", 2]]
        selected, farm, private, config = fixture(
            ["PASS"],
            shed={"MILK": 0, "WOOL": 0},
            inv={"MILK": 2, "WOOL": 2},
            market=market,
        )
        out, report = bridge.transform(selected, farm, private, config)
        self.assertIs(out, selected)
        self.assertEqual(report["reason"], "ambiguous_or_no_pass_bridge")

    def test_final_hand_is_supported(self):
        selected, farm, private, config = fixture(["PASS"], hands=True)
        out, report = bridge.transform(selected, farm, private, config)
        self.assertEqual(out["hands"][-1], ["PLACE", "MILK", 3])
        self.assertEqual(report["worker_index"], 1)

    def test_not_shed_adjacent_is_identity(self):
        selected, farm, private, config = fixture(["PASS"], pos=(0, 0))
        out, report = bridge.transform(selected, farm, private, config)
        self.assertIs(out, selected)
        self.assertEqual(report["reason"], "final_worker_not_shed_adjacent")

    def test_falsey_non_mapping_configurations_fail_closed(self):
        selected, farm, private, _ = fixture(["PASS"])
        for malformed in (False, 0, "", [], ()):
            with self.subTest(malformed=malformed):
                out, report = bridge.transform(selected, farm, private, malformed)
                self.assertIs(out, selected)
                self.assertEqual(report["classification"], "NO_OP")
                self.assertEqual(report["reason"], "malformed_config")


if __name__ == "__main__":
    unittest.main()
