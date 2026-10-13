# SPDX-License-Identifier: Apache-2.0
"""Focused checks for V4 ``r04_c5_wheat_demand``.

Run in a materialised candidate package:

    python -B -m unittest -v checks/test_v4_c5_wheat_demand.py
"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_c5_wheat_demand as c5  # noqa: E402
import r04_full_router as r04  # noqa: E402
from titan_runtime import Features, TitanAgent  # noqa: E402

CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10,
          "shedCapacity": 100, "maxMarketOrdersPerTurn": 10,
          "farmHandCostMult": 1}


def obs(step, inventory, *, price=25, shops=None, player=0):
    return {"step": step, "player": player,
            "market": {"inventory": {"WHEAT": inventory},
                       "prices": {"WHEAT": price}},
            "town": {"unlocked_shops": list(shops or [])}}


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


class C5WheatDemandTests(unittest.TestCase):
    def setUp(self):
        c5.reset_state()
        if hasattr(r04, "C5_WHEAT_DEMAND"):
            r04.C5_WHEAT_DEMAND = False

    def tearDown(self):
        c5.reset_state()
        if hasattr(r04, "C5_WHEAT_DEMAND"):
            r04.C5_WHEAT_DEMAND = False

    def test_key_ships_off_and_features_accept_it(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        self.assertIs(data["r04_c5_wheat_demand"], False)
        self.assertIs(Features(**data).r04_c5_wheat_demand, False)

    def test_gross_buy_lower_bound(self):
        self.assertEqual(c5._rival_wheat_buy_lower_bound(100, 97, 0, 0), 3)
        self.assertEqual(c5._rival_wheat_buy_lower_bound(100, 97, 1, 2), 0)

    def test_town_consumption_is_subtracted(self):
        self.assertEqual(c5._town_wheat_consumption(obs(4, 100, shops=["BAKERY"])), 1)
        self.assertEqual(c5._town_wheat_consumption(obs(24, 100, shops=["BAKERY", "PIZZA_SHOP"])), 3)

    def test_positive_signal_relocates_only_existing_wheat_sell(self):
        rider = c5.WheatDemandRider(enabled=True)
        rider.apply(obs(1, 100), action())
        parent = action(("SELL", "WHEAT", 3), ("SELL", "MILK", 2), ("SELL", "WOOL", 1))
        original = copy.deepcopy(parent)
        out = rider.apply(obs(2, 99, price=30), parent)
        self.assertEqual(parent, original)
        self.assertEqual(out["market"], [[], ["SELL", "MILK", 2], ["SELL", "WOOL", 1], ["SELL", "WHEAT", 3]])
        self.assertEqual(rider.telemetry["relocations"], 1)
        self.assertEqual(rider.telemetry["moved_units"], 3)

    def test_disabled_wrapper_is_exact_identity_without_state(self):
        parent = action(("SELL", "WHEAT", 3))
        self.assertIs(c5.apply_c5_wheat_demand(obs(1, 100), parent, enabled=False), parent)
        self.assertEqual(c5.RIDER.players, {})

    def test_invalid_player_never_seeds_or_uses_transition_state(self):
        rider = c5.WheatDemandRider(enabled=True)
        parent = action(("SELL", "WHEAT", 3))
        self.assertIs(rider.apply(obs(1, 100, player=2), parent), parent)
        self.assertIs(rider.apply(obs(2, 99, price=30, player=2), parent), parent)
        self.assertEqual(rider.players, {})
        self.assertEqual(rider.telemetry["confirmed_rival_buy_transitions"], 0)
        self.assertEqual(rider.telemetry["relocations"], 0)

    def test_malformed_step_with_known_player_clears_only_that_latch(self):
        rider = c5.WheatDemandRider(enabled=True)
        rider.apply(obs(1, 100, player=0), action())
        rider.apply(obs(1, 200, player=1), action())
        self.assertEqual(set(rider.players), {0, 1})

        bad = obs(2, 99, player=0)
        bad["step"] = "2"
        parent = action(("SELL", "WHEAT", 3))
        self.assertIs(rider.apply(bad, parent), parent)
        self.assertNotIn(0, rider.players)
        self.assertIn(1, rider.players)

        self.assertIs(rider.apply(obs(2, 99, price=30, player=0), parent), parent)
        self.assertEqual(rider.telemetry["confirmed_rival_buy_transitions"], 0)
        self.assertEqual(rider.telemetry["relocations"], 0)

    def test_unidentifiable_player_clears_all_transition_state(self):
        rider = c5.WheatDemandRider(enabled=True)
        rider.apply(obs(1, 100, player=0), action())
        rider.apply(obs(1, 200, player=1), action())
        self.assertEqual(set(rider.players), {0, 1})

        bad = obs(2, 99, player=0)
        bad["player"] = True
        parent = action(("SELL", "WHEAT", 3))
        self.assertIs(rider.apply(bad, parent), parent)
        self.assertEqual(rider.players, {})

        self.assertIs(rider.apply(obs(2, 99, price=30, player=0), parent), parent)
        self.assertEqual(rider.telemetry["confirmed_rival_buy_transitions"], 0)
        self.assertEqual(rider.telemetry["relocations"], 0)

    def test_own_buy_upper_bound_masks_self_caused_inventory_drop(self):
        rider = c5.WheatDemandRider(enabled=True)
        rider.apply(obs(1, 100), action(("BUY_PRODUCT", "WHEAT", 2)))
        parent = action(("SELL", "WHEAT", 3))
        self.assertIs(rider.apply(obs(2, 98, price=30), parent), parent)
        self.assertEqual(rider.telemetry["confirmed_rival_buy_transitions"], 0)

    def test_tuple_market_rows_are_engine_inert(self):
        parent = {"farmer": ["PASS"], "hands": [],
                  "market": [("SELL", "WHEAT", 3), ["SELL", "MILK", 1]]}
        out, moved = c5._relocate_wheat_sell(parent, 10)
        self.assertIs(out, parent)
        self.assertIsNone(moved)

        self.assertEqual(
            c5._own_wheat_buy_upper(
                {"market": [("BUY_PRODUCT", "WHEAT", 9), ["BUY_PRODUCT", "WHEAT", 2]]}, 10
            ),
            2,
        )
        self.assertIs(c5._cash_spending(("HIRE",)), False)
        self.assertIs(c5._cash_spending(["HIRE"]), True)

    def test_later_purchase_veto_preserves_sale_funding(self):
        rider = c5.WheatDemandRider(enabled=True)
        rider.apply(obs(1, 100), action())
        parent = action(("SELL", "WHEAT", 3), ("HIRE",), ("SELL", "MILK", 1))
        self.assertIs(rider.apply(obs(2, 99, price=30), parent), parent)

    def test_same_product_ambiguity_and_floor_price_preserve_parent(self):
        rider = c5.WheatDemandRider(enabled=True)
        rider.apply(obs(1, 100), action())
        parent = action(("SELL", "WHEAT", 3), ("BUY_PRODUCT", "WHEAT", 1))
        self.assertIs(rider.apply(obs(2, 99, price=30), parent), parent)
        rider = c5.WheatDemandRider(enabled=True)
        rider.apply(obs(1, 100), action())
        parent = action(("SELL", "WHEAT", 3))
        self.assertIs(rider.apply(obs(2, 99, price=1), parent), parent)

    def test_current_evidence_poison_fails_before_mutation_and_resets(self):
        rider = c5.WheatDemandRider(enabled=True)
        rider.apply(obs(1, 100), action())
        parent = action(("SELL", "WHEAT", 3))
        self.assertIs(rider.apply(obs(2, 99, price=30, shops=["UNKNOWN"]), parent), parent)
        self.assertEqual(rider.players, {})
        self.assertEqual(rider.telemetry["relocations"], 0)

    def test_runtime_cap_parity_and_type_poison(self):
        rider = c5.WheatDemandRider(enabled=True)
        rider.apply(obs(1, 100), action(), {"maxMarketOrdersPerTurn": 3})
        parent = action(("SELL", "WHEAT", 3), ("SELL", "MILK", 1))
        out = rider.apply(obs(2, 99, price=30), parent, {"maxMarketOrdersPerTurn": 3})
        self.assertEqual(out["market"], [[], ["SELL", "MILK", 1], ["SELL", "WHEAT", 3]])

        for cap in (1, 0, -3):
            rider = c5.WheatDemandRider(enabled=True)
            cfg = {"maxMarketOrdersPerTurn": cap}
            rider.apply(obs(1, 100), action(), cfg)
            parent = action(("SELL", "WHEAT", 3))
            self.assertIs(rider.apply(obs(2, 99, price=30), parent, cfg), parent)

        for cap in (True, 3.0, "3", None):
            rider = c5.WheatDemandRider(enabled=True)
            rider.apply(obs(1, 100), action())
            parent = action(("SELL", "WHEAT", 3))
            self.assertIs(rider.apply(obs(2, 99, price=30), parent, {"maxMarketOrdersPerTurn": cap}), parent)
            self.assertEqual(rider.players, {})

    def test_raw_tail_beyond_cap_is_untouched(self):
        cfg = {"maxMarketOrdersPerTurn": 3}
        rider = c5.WheatDemandRider(enabled=True)
        rider.apply(obs(1, 100), action(), cfg)
        parent = action(("SELL", "WHEAT", 3), ("SELL", "MILK", 1),
                        ("SELL", "WOOL", 1), ("SELL", "EGG", 9))
        original = copy.deepcopy(parent)
        self.assertIs(rider.apply(obs(2, 99, price=30), parent, cfg), parent)
        self.assertEqual(parent, original)

    def test_struct_like_public_maps_are_supported(self):
        rider = c5.WheatDemandRider(enabled=True)
        first = SimpleNamespace(step=1, player=0,
            market=SimpleNamespace(inventory=SimpleNamespace(WHEAT=100), prices=SimpleNamespace(WHEAT=25)),
            town=SimpleNamespace(unlocked_shops=[]))
        second = SimpleNamespace(step=2, player=0,
            market=SimpleNamespace(inventory=SimpleNamespace(WHEAT=99), prices=SimpleNamespace(WHEAT=30)),
            town=SimpleNamespace(unlocked_shops=[]))
        rider.apply(first, action())
        out = rider.apply(second, action(("SELL", "WHEAT", 3)))
        self.assertEqual(out["market"], [[], ["SELL", "WHEAT", 3]])

    def test_install_and_diagnostics_carry_key(self):
        r04.install(c5_wheat_demand=True)
        self.assertIs(r04.C5_WHEAT_DEMAND, True)
        r04.install(c5_wheat_demand=False)
        self.assertIs(r04.C5_WHEAT_DEMAND, False)
        agent = TitanAgent(Features(r04_sale_window=True, r04_c5_wheat_demand=True))
        agent.act(full_observation(), dict(CONFIG))
        self.assertIs(r04.C5_WHEAT_DEMAND, True)
        self.assertIs(agent.diagnostics["c5_wheat_demand"], True)

    def test_c5_is_final_market_transform_and_after_b10_if_present(self):
        source = Path(r04.__file__).read_text(encoding="utf-8")
        c5_at = source.index("if C5_WHEAT_DEMAND:")
        self.assertGreater(c5_at, source.index("if GOOSE_RESCUE:"))
        if "if B10_PUBLIC_SUPPLY_ORDER:" in source:
            self.assertGreater(c5_at, source.index("if B10_PUBLIC_SUPPLY_ORDER:"))


if __name__ == "__main__":
    unittest.main()
