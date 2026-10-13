# SPDX-License-Identifier: Apache-2.0
"""Focused checks for V4 ``r04_b10_public_supply_order``.

Run in a materialised candidate package:

    python -B -m unittest -v checks/test_v4_b10_public_supply_order.py
"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_b10_public_supply_order as b10  # noqa: E402
import r04_full_router as r04  # noqa: E402
from titan_runtime import Features, TitanAgent  # noqa: E402

CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10,
          "shedCapacity": 100, "maxMarketOrdersPerTurn": 10,
          "farmHandCostMult": 1}


def obs(step: int, inventory=None, *, shops=None, player: int = 0):
    values = {item: 10_000 for item in b10.PRODUCTS}
    if inventory:
        values.update(inventory)
    return {
        "step": step,
        "player": player,
        "market": {"inventory": values},
        "town": {"unlocked_shops": list(shops or [])},
    }


def action(*rows):
    return {"farmer": ["PASS"], "hands": [], "market": [list(row) for row in rows]}


def full_observation(step=0):
    tiles = [["LOCKED"] * 10 for _ in range(10)]
    for y in range(3, 7):
        for x in range(3, 7):
            tiles[y][x] = {"kind": "SOIL"}
    farm = {"tiles": tiles, "farmer": [4, 4], "hands": [], "money": 3000,
            "unlocked_quadrants": ["NW"], "hires_today": 0}
    prices = {item: 10 for item in r04.PRODUCTS}
    inventory = {item: 10_000 for item in r04.PRODUCTS}
    return {"step": step, "day": step // 24, "hour": step % 24, "player": 0,
            "farms": [farm, copy.deepcopy(farm)],
            "private": {"inventories": [{}], "shed": {}},
            "market": {"prices": prices, "inventory": inventory},
            "town": {"unlocked_shops": ["BAKERY", "YARN_STORE"]}}


class RivalSupplyOrderTests(unittest.TestCase):
    def tearDown(self):
        if hasattr(r04, "B10_PUBLIC_SUPPLY_ORDER"):
            r04.B10_PUBLIC_SUPPLY_ORDER = False
        b10.ORDER.players.clear()

    def test_key_ships_off_and_features_accept_it(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        self.assertIs(data["r04_b10_public_supply_order"], False)
        self.assertIs(data["r04_place_delivery"], False)
        features = Features(**data)
        self.assertIs(features.r04_b10_public_supply_order, False)
        self.assertIs(features.r04_place_delivery, False)

    def test_supply_lower_bound_exact_without_own_sell_or_town(self):
        previous = {item: 100 for item in b10.PRODUCTS}
        current = dict(previous)
        current["WOOL"] = 104
        zero = {item: 0 for item in b10.PRODUCTS}
        lower = b10._rival_supply_lower_bound(previous, current, zero, zero)
        self.assertEqual(lower["WOOL"], 4)

    def test_requested_own_sell_upper_cannot_fabricate_rival_supply(self):
        previous = {item: 100 for item in b10.PRODUCTS}
        current = dict(previous)
        current["MILK"] = 103
        town = {item: 0 for item in b10.PRODUCTS}
        own = {item: 0 for item in b10.PRODUCTS}
        own["MILK"] = 3
        lower = b10._rival_supply_lower_bound(previous, current, town, own)
        self.assertEqual(lower["MILK"], 0)

    def test_own_buy_only_hides_rival_supply(self):
        previous = {item: 100 for item in b10.PRODUCTS}
        current = dict(previous)
        current["EGG"] = 103
        zero = {item: 0 for item in b10.PRODUCTS}
        lower = b10._rival_supply_lower_bound(previous, current, zero, zero)
        self.assertEqual(lower["EGG"], 3)

    def test_nonbuyable_supply_feasibility_and_buyable_non_authorization(self):
        previous = {item: 10_000 for item in b10.PRODUCTS}
        zero = {item: 0 for item in b10.PRODUCTS}

        control = dict(previous)
        control["CARROT"] += 100
        lower = b10._validated_supply_lower_bound(previous, control, zero, zero, 100)
        self.assertEqual(lower["CARROT"], 100)

        rival_over = dict(previous)
        rival_over["CARROT"] += 101
        with self.assertRaises(ValueError):
            b10._validated_supply_lower_bound(previous, rival_over, zero, zero, 100)

        impossible = dict(previous)
        impossible["CARROT"] += 201
        own = dict(zero)
        own["CARROT"] = 201
        with self.assertRaises(ValueError):
            b10._validated_supply_lower_bound(previous, impossible, zero, own, 100)

        fertilizer = dict(previous)
        fertilizer["FERTILIZER"] += 101
        lower = b10._validated_supply_lower_bound(previous, fertilizer, zero, zero, 100)
        self.assertEqual(lower["FERTILIZER"], 101)

    def test_lockstep_price_room_handles_final_pair_overshoot(self):
        zero = {item: 0 for item in b10.PRODUCTS}

        # Sellers may enter WOOL on different raw market-row indices. Starting
        # two below the floor, one single SELL can advance to 10058 and a later
        # dual quote can then commit two units at the same final >$1 quote.
        staggered_previous = {item: 10_000 for item in b10.PRODUCTS}
        staggered_previous["WOOL"] = 10_057
        staggered_control = dict(staggered_previous)
        staggered_control["WOOL"] = 10_060
        lower = b10._validated_supply_lower_bound(
            staggered_previous, staggered_control, zero, zero, 100
        )
        self.assertEqual(lower["WOOL"], 3)

        staggered_poison = dict(staggered_previous)
        staggered_poison["WOOL"] = 10_061
        with self.assertRaises(ValueError):
            b10._validated_supply_lower_bound(
                staggered_previous, staggered_poison, zero, zero, 100
            )

        previous = {item: 10_000 for item in b10.PRODUCTS}
        previous["WOOL"] = 10_058

        control = dict(previous)
        control["WOOL"] = 10_060
        lower = b10._validated_supply_lower_bound(previous, control, zero, zero, 100)
        self.assertEqual(lower["WOOL"], 2)

        poison = dict(previous)
        poison["WOOL"] = 10_061
        with self.assertRaises(ValueError):
            b10._validated_supply_lower_bound(previous, poison, zero, zero, 100)

        floor = dict(previous)
        floor["WOOL"] = 10_059
        above_floor = dict(floor)
        above_floor["WOOL"] = 10_060
        with self.assertRaises(ValueError):
            b10._validated_supply_lower_bound(floor, above_floor, zero, zero, 100)

    def test_tuple_own_sell_is_engine_noop_not_supply_upper_bound(self):
        parent = {"farmer": ["PASS"], "hands": [],
                  "market": [("SELL", "WOOL", 99), ["SELL", "MILK", 2]]}
        upper = b10._own_sell_upper(parent)
        self.assertEqual(upper["WOOL"], 0)
        self.assertEqual(upper["MILK"], 2)

    def test_town_consumption_handles_multi_and_single_product_shops(self):
        row = b10._town_consumption(obs(4, shops=["BAKERY", "YARN_STORE"]))
        self.assertEqual(row["WHEAT"], 1)
        self.assertEqual(row["EGG"], 1)
        self.assertEqual(row["WOOL"], 2)
        self.assertEqual(row["FERTILIZER"], 0)

    def test_town_center_consumption_is_added_at_step_24(self):
        row = b10._town_consumption(obs(24, shops=[]))
        for item in b10.CENTER_PRODUCTS:
            self.assertEqual(row[item], 1)
        self.assertEqual(row["FERTILIZER"], 0)

    def test_positive_supply_moves_product_earlier_inside_leading_sell_block(self):
        parent = action(("SELL", "MILK", 2), ("SELL", "WOOL", 3),
                        ("SELL", "CARROT", 1), ("PASS",))
        evidence = {item: 0 for item in b10.PRODUCTS}
        evidence["CARROT"] = 4
        evidence["WOOL"] = 2
        result, detail = b10._reorder_leading_sells(parent, evidence)
        self.assertIsNot(result, parent)
        self.assertEqual([row[1] for row in result["market"][:3]],
                         ["CARROT", "WOOL", "MILK"])
        self.assertEqual(result["market"][3], ["PASS"])
        self.assertEqual(detail["before"], ["MILK", "WOOL", "CARROT"])
        self.assertEqual(detail["after"], ["CARROT", "WOOL", "MILK"])

    def test_equal_supply_preserves_native_relative_order(self):
        parent = action(("SELL", "MILK", 2), ("SELL", "WOOL", 3),
                        ("SELL", "CARROT", 1))
        evidence = {item: 0 for item in b10.PRODUCTS}
        evidence["MILK"] = evidence["WOOL"] = 2
        result, detail = b10._reorder_leading_sells(parent, evidence)
        self.assertIs(result, parent)
        self.assertIsNone(detail)

    def test_wheat_and_fertilizer_rows_stay_at_exact_indices(self):
        parent = action(("SELL", "MILK", 2), ("SELL", "WHEAT", 5),
                        ("SELL", "FERTILIZER", 4), ("SELL", "CARROT", 1),
                        ("SELL", "WOOL", 1))
        evidence = {item: 0 for item in b10.PRODUCTS}
        evidence["FERTILIZER"] = 999
        evidence["WOOL"] = 9
        evidence["CARROT"] = 3
        result, _ = b10._reorder_leading_sells(parent, evidence)
        self.assertEqual(result["market"][1], ["SELL", "WHEAT", 5])
        self.assertEqual(result["market"][2], ["SELL", "FERTILIZER", 4])
        self.assertEqual([result["market"][i][1] for i in (0, 3, 4)],
                         ["WOOL", "CARROT", "MILK"])

        only_buyable = {item: 0 for item in b10.PRODUCTS}
        only_buyable["FERTILIZER"] = 999
        same, detail = b10._reorder_leading_sells(parent, only_buyable)
        self.assertIs(same, parent)
        self.assertIsNone(detail)

    def test_later_cash_spend_vetoes_reorder(self):
        parent = action(("SELL", "MILK", 2), ("SELL", "WOOL", 3), ("HIRE",))
        evidence = {item: 0 for item in b10.PRODUCTS}
        evidence["WOOL"] = 9
        result, detail = b10._reorder_leading_sells(parent, evidence)
        self.assertIs(result, parent)
        self.assertIsNone(detail)

    def test_nonleading_sell_is_not_moved(self):
        parent = action(("SELL", "MILK", 2), ("SELL", "WOOL", 3),
                        ("PASS",), ("SELL", "CARROT", 9))
        evidence = {item: 0 for item in b10.PRODUCTS}
        evidence["WOOL"] = 2
        evidence["CARROT"] = 99
        result, _ = b10._reorder_leading_sells(parent, evidence)
        self.assertEqual(result["market"][3], ["SELL", "CARROT", 9])

    def test_disabled_helper_is_exact_parent_identity(self):
        parent = action(("SELL", "MILK", 1), ("SELL", "WOOL", 1))
        self.assertIs(b10.apply_public_supply_order(obs(1), parent, enabled=False), parent)

    def test_disabled_tracker_is_exact_parent_identity(self):
        tracker = b10.RivalSupplyOrder(enabled=False)
        tracker.apply(obs(1), action())
        parent = action(("SELL", "MILK", 1), ("SELL", "WOOL", 1))
        result = tracker.apply(obs(2, {"WOOL": 10_003}), parent)
        self.assertIs(result, parent)
        self.assertEqual(tracker.telemetry["confirmed_supply_transitions"], 1)
        self.assertEqual(tracker.telemetry["reorders"], 0)

    def test_gap_or_rewind_does_not_use_stale_supply_evidence(self):
        tracker = b10.RivalSupplyOrder(enabled=True)
        tracker.apply(obs(1), action())
        parent = action(("SELL", "MILK", 1), ("SELL", "WOOL", 1))
        result = tracker.apply(obs(3, {"WOOL": 10_050}), parent)
        self.assertIs(result, parent)
        self.assertEqual(tracker.telemetry["reorders"], 0)

    def test_unknown_shop_fails_closed_and_drops_state(self):
        tracker = b10.RivalSupplyOrder(enabled=True)
        parent = action(("SELL", "MILK", 1), ("SELL", "WOOL", 1))
        result = tracker.apply(obs(4, shops=["UNKNOWN"]), parent)
        self.assertIs(result, parent)
        self.assertEqual(tracker.players, {})

    def test_valid_previous_signal_plus_unknown_current_shop_never_mutates(self):
        tracker = b10.RivalSupplyOrder(enabled=True)
        tracker.apply(obs(1), action())
        parent = action(("SELL", "MILK", 1), ("SELL", "WOOL", 1))
        current = obs(2, {"WOOL": 10_003}, shops=["UNKNOWN"])
        result = tracker.apply(current, parent)
        self.assertIs(result, parent)
        self.assertEqual(tracker.players, {})
        self.assertEqual(tracker.telemetry["reorders"], 0)

    def test_custom_market_params_disable_mutation(self):
        tracker = b10.RivalSupplyOrder(enabled=True)
        tracker.apply(obs(1), action())
        parent = action(("SELL", "MILK", 1), ("SELL", "WOOL", 1))
        current = obs(2, {"WOOL": 10_003})
        result = tracker.apply(current, parent,
                               {"marketParams": {"WOOL": {"base": 999}}})
        self.assertIs(result, parent)
        self.assertEqual(tracker.players, {})

    def test_falsey_malformed_market_params_fail_closed_and_clear_latch(self):
        parent = action(("SELL", "MILK", 1), ("SELL", "WOOL", 1))
        for market_params in ([], "", 0, False):
            with self.subTest(marketParams=market_params):
                tracker = b10.RivalSupplyOrder(enabled=True)
                tracker.apply(obs(1), action())
                self.assertIn(0, tracker.players)
                result = tracker.apply(obs(2, {"WOOL": 10_003}), parent,
                                       {"marketParams": market_params})
                self.assertIs(result, parent)
                self.assertEqual(tracker.players, {})
                self.assertEqual(tracker.telemetry["reorders"], 0)

    def test_empty_market_params_mapping_preserves_standard_path(self):
        tracker = b10.RivalSupplyOrder(enabled=True)
        tracker.apply(obs(1), action())
        parent = action(("SELL", "MILK", 1), ("SELL", "WOOL", 1))
        result = tracker.apply(obs(2, {"WOOL": 10_003}), parent,
                               {"marketParams": {}})
        self.assertEqual(result["market"][:2],
                         [["SELL", "WOOL", 1], ["SELL", "MILK", 1]])

    def test_bool_sell_quantity_is_malformed_not_one(self):
        with self.assertRaises(ValueError):
            b10._own_sell_upper(action(("SELL", "WOOL", True)))

    def test_no_positive_evidence_keeps_exact_parent(self):
        parent = action(("SELL", "MILK", 1), ("SELL", "WOOL", 1))
        evidence = {item: -5 for item in b10.PRODUCTS}
        result, detail = b10._reorder_leading_sells(parent, evidence)
        self.assertIs(result, parent)
        self.assertIsNone(detail)

    def test_nonstandard_or_ambiguous_market_cap_fails_closed_and_clears_latch(self):
        parent = action(("SELL", "MILK", 1), ("SELL", "WOOL", 1))
        for cap in (1, 3, 0, -1, True, 10.0, "10", 11):
            with self.subTest(cap=cap):
                tracker = b10.RivalSupplyOrder(enabled=True)
                tracker.apply(obs(1), action())
                self.assertIn(0, tracker.players)
                result = tracker.apply(obs(2, {"WOOL": 10_003}), parent,
                                       {"maxMarketOrdersPerTurn": cap})
                self.assertIs(result, parent)
                self.assertEqual(tracker.players, {})
                self.assertEqual(tracker.telemetry["reorders"], 0)

    def test_shed_capacity_is_positive_json_int_and_runtime_bound(self):
        parent = action(("SELL", "MILK", 1), ("SELL", "WOOL", 1))
        for bad_capacity in (0, -1, True, 100.0, "100"):
            with self.subTest(shedCapacity=bad_capacity):
                tracker = b10.RivalSupplyOrder(enabled=True)
                tracker.apply(obs(1), action(), dict(CONFIG))
                bad = dict(CONFIG)
                bad["shedCapacity"] = bad_capacity
                self.assertIs(tracker.apply(obs(2, {"WOOL": 10_003}), parent, bad), parent)
                self.assertEqual(tracker.players, {})

        tracker = b10.RivalSupplyOrder(enabled=True)
        wider = dict(CONFIG)
        wider["shedCapacity"] = 101
        tracker.apply(obs(1), action(), wider)
        result = tracker.apply(obs(2, {"WOOL": 10_003}), parent, wider)
        self.assertEqual(result["market"][:2],
                         [["SELL", "WOOL", 1], ["SELL", "MILK", 1]])

    def test_invalid_player_never_seeds_or_uses_tracker_state(self):
        tracker = b10.RivalSupplyOrder(enabled=True)
        parent = action(("SELL", "MILK", 1), ("SELL", "WOOL", 1))
        self.assertIs(tracker.apply(obs(1, player=2), parent), parent)
        self.assertIs(tracker.apply(obs(2, {"WOOL": 10_003}, player=2), parent), parent)
        self.assertEqual(tracker.players, {})
        self.assertEqual(tracker.telemetry["reorders"], 0)

    def test_install_and_titan_diagnostics_carry_key(self):
        r04.install(None, 8, 0, False, False, b10_public_supply_order=True)
        self.assertIs(r04.B10_PUBLIC_SUPPLY_ORDER, True)
        r04.install(None, 8, 0, False, False, b10_public_supply_order=False)
        self.assertIs(r04.B10_PUBLIC_SUPPLY_ORDER, False)

        agent = TitanAgent(Features(r04_sale_window=True,
                                    r04_b10_public_supply_order=True))
        agent.act(full_observation(step=0), dict(CONFIG))
        self.assertIs(r04.B10_PUBLIC_SUPPLY_ORDER, True)
        self.assertIs(agent.diagnostics["b10_public_supply_order"], True)

    def test_b10_is_outermost_over_final_parent_action(self):
        original_core = r04._v3_core
        original_mirror = r04.MIRROR_HORIZON
        original_terminal = r04.TERMINAL_FERTILIZER
        original_goose = r04.GOOSE_RESCUE
        try:
            parent = action(("SELL", "MILK", 1), ("SELL", "WOOL", 1))
            r04._v3_core = lambda observation, configuration=None: parent
            r04.MIRROR_HORIZON = False
            r04.TERMINAL_FERTILIZER = False
            r04.GOOSE_RESCUE = False
            r04.B10_PUBLIC_SUPPLY_ORDER = True
            b10.ORDER.players.clear()

            self.assertIs(r04.v3_agent(obs(0), dict(CONFIG)), parent)
            self.assertIs(r04.v3_agent(obs(1), dict(CONFIG)), parent)
            out = r04.v3_agent(obs(2, {"WOOL": 10_003}), dict(CONFIG))
            self.assertEqual(out["market"][:2],
                             [["SELL", "WOOL", 1], ["SELL", "MILK", 1]])
        finally:
            r04._v3_core = original_core
            r04.MIRROR_HORIZON = original_mirror
            r04.TERMINAL_FERTILIZER = original_terminal
            r04.GOOSE_RESCUE = original_goose
            r04.B10_PUBLIC_SUPPLY_ORDER = False
            b10.ORDER.players.clear()

    def test_installed_epoch_gap_kills_state_and_cannot_reseed_mid_episode(self):
        original_core = r04._v3_core
        original_mirror = r04.MIRROR_HORIZON
        original_terminal = r04.TERMINAL_FERTILIZER
        original_goose = r04.GOOSE_RESCUE
        try:
            parent = action(("SELL", "MILK", 1), ("SELL", "WOOL", 1))
            r04._v3_core = lambda observation, configuration=None: parent
            r04.MIRROR_HORIZON = False
            r04.TERMINAL_FERTILIZER = False
            r04.GOOSE_RESCUE = False
            r04.B10_PUBLIC_SUPPLY_ORDER = True
            b10.ORDER.players.clear()

            r04.v3_agent(obs(0), dict(CONFIG))
            r04.v3_agent(obs(1), dict(CONFIG))
            self.assertIn(0, b10.ORDER.players)
            self.assertIs(r04.v3_agent(obs(3, {"WOOL": 10_050}), dict(CONFIG)), parent)
            self.assertEqual(b10.ORDER.players, {})
            self.assertIs(r04.v3_agent(obs(4, {"WOOL": 10_100}), dict(CONFIG)), parent)
            self.assertEqual(b10.ORDER.players, {})
        finally:
            r04._v3_core = original_core
            r04.MIRROR_HORIZON = original_mirror
            r04.TERMINAL_FERTILIZER = original_terminal
            r04.GOOSE_RESCUE = original_goose
            r04.B10_PUBLIC_SUPPLY_ORDER = False
            b10.ORDER.players.clear()

    def test_installed_step_zero_requires_standard_i0(self):
        parent = action(("SELL", "MILK", 1), ("SELL", "WOOL", 1))
        bad = obs(0, {"WOOL": 9_999})
        self.assertIs(b10.apply_public_supply_order(bad, parent, dict(CONFIG)), parent)
        self.assertEqual(b10.ORDER.players, {})


if __name__ == "__main__":
    unittest.main()
