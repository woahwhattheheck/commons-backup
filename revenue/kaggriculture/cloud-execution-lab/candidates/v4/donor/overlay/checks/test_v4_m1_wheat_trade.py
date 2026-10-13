# SPDX-License-Identifier: Apache-2.0
"""Focused checks for V4 ``r04_m1_wheat_trade``.

Run in a materialised candidate package:

    python -B -m unittest -v checks/test_v4_m1_wheat_trade.py
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

import r04_full_router as r04  # noqa: E402
import r04_m1_wheat_trade as lane  # noqa: E402
from titan_runtime import Features, TitanAgent  # noqa: E402

CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10,
          "shedCapacity": 100, "maxMarketOrdersPerTurn": 10,
          "farmHandCostMult": 1}


class AttrConfig:
    def __init__(self, values):
        self.__dict__.update(values)


def empty_action():
    return {"farmer": ["PASS"], "hands": [["PASS"]], "market": []}


def tape_with_pickup(step, quantity=3):
    tape = [empty_action() for _ in range(719)]
    tape[step] = {"farmer": ["PASS"], "hands": [["PICKUP", "WHEAT", quantity]], "market": []}
    return tape


def observation(step, market_inventory=100, wheat_price=20, shed=None, money=10000.0):
    tiles = [["LOCKED"] * 10 for _ in range(10)]
    for y in range(3, 7):
        for x in range(3, 7):
            tiles[y][x] = {"kind": "SOIL"}
    farm = {"tiles": tiles, "farmer": [4, 4], "hands": [[5, 4]],
            "money": money, "unlocked_quadrants": ["NW"], "hires_today": 0}
    prices = {product: 10 for product in r04.PRODUCTS}
    prices["WHEAT"] = wheat_price
    return {"step": step, "day": step // 24, "hour": step % 24, "player": 0,
            "farms": [farm, copy.deepcopy(farm)],
            "private": {"inventories": [{}, {}], "shed": shed or {}},
            "market": {"prices": prices,
                       "inventory": {product: (market_inventory if product == "WHEAT" else 10000)
                                     for product in r04.PRODUCTS}},
            "town": {"unlocked_shops": ["BAKERY", "YARN_STORE"]}}


class M1WheatTrade(unittest.TestCase):
    def setUp(self):
        lane.reset_for_tests()

    def tearDown(self):
        lane.reset_for_tests()
        r04.M1_WHEAT_TRADE = False

    def run_lane(self, obs, parent, tape, configuration=CONFIG, enabled=True):
        return lane.apply_m1_wheat_trade(
            obs, parent, tape, configuration=configuration, enabled=enabled)

    def prime(self, step=100, inventory=100, configuration=CONFIG):
        parent = empty_action()
        self.run_lane(observation(step, market_inventory=inventory), parent,
                      tape_with_pickup(step + 4), configuration=configuration)

    def test_key_ships_off_and_features_accept_it(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        self.assertIs(data["r04_m1_wheat_trade"], False)
        self.assertIs(Features(**data).r04_m1_wheat_trade, False)

    def test_disabled_is_exact_parent_object(self):
        parent = empty_action()
        out = self.run_lane(observation(101, market_inventory=98), parent,
                            tape_with_pickup(104), enabled=False)
        self.assertIs(out, parent)

    def test_two_to_six_step_pickup_buys_only_shortage_under_public_scarcity(self):
        self.prime(step=100, inventory=100)
        parent = empty_action()
        out = self.run_lane(observation(101, market_inventory=98, shed={"WHEAT": 1}),
                            parent, tape_with_pickup(104, 4))
        self.assertIsNot(out, parent)
        self.assertEqual(out["market"], [["BUY_PRODUCT", "WHEAT", 3]])
        self.assertEqual(lane.REPORT["buy_units"], 3)

    def test_future_pickup_must_belong_to_current_actor(self):
        self.prime(step=100, inventory=100)
        obs = observation(101, market_inventory=98)
        obs["farms"][0]["hands"] = []
        obs["private"]["inventories"] = [{}]
        parent = {"farmer": ["PASS"], "hands": [], "market": []}

        out = self.run_lane(obs, parent, tape_with_pickup(104, 2))
        self.assertIs(out, parent)
        self.assertEqual(lane.REPORT["future_pickups"], 0)
        self.assertEqual(lane.REPORT["buy_orders"], 0)

    def test_future_pickup_requires_shed_reachability(self):
        self.prime(step=100, inventory=100)
        obs = observation(101, market_inventory=98)
        obs["farms"][0]["hands"] = [[0, 0]]
        parent = empty_action()
        out = self.run_lane(obs, parent, tape_with_pickup(104, 2))
        self.assertIs(out, parent)
        self.assertEqual(lane.REPORT["future_pickups"], 0)
        self.assertEqual(lane.REPORT["buy_orders"], 0)

    def test_literal_future_moves_can_certify_shed_reachability(self):
        self.prime(step=100, inventory=100)
        obs = observation(101, market_inventory=98)
        obs["farms"][0]["hands"] = [[5, 2]]
        tape = tape_with_pickup(104, 2)
        tape[102]["hands"] = [["SOUTH"]]
        tape[103]["hands"] = [["SOUTH"]]
        parent = empty_action()
        out = self.run_lane(obs, parent, tape)
        self.assertEqual(out["market"], [["BUY_PRODUCT", "WHEAT", 2]])
        self.assertEqual(lane.REPORT["future_pickups"], 1)

    def test_current_literal_move_is_part_of_pickup_reachability(self):
        self.prime(step=100, inventory=100)
        obs = observation(101, market_inventory=98)
        obs["farms"][0]["hands"] = [[5, 3]]
        parent = empty_action()
        parent["hands"] = [["SOUTH"]]
        out = self.run_lane(obs, parent, tape_with_pickup(104, 2))
        self.assertEqual(out["market"], [["BUY_PRODUCT", "WHEAT", 2]])

    def test_future_actor_cardinality_drift_fails_closed(self):
        self.prime(step=100, inventory=100)
        tape = tape_with_pickup(104, 2)
        tape[102]["hands"] = []
        parent = empty_action()
        out = self.run_lane(observation(101, market_inventory=98), parent, tape)
        self.assertIs(out, parent)
        self.assertEqual(lane.REPORT["buy_orders"], 0)

    def test_one_turn_wheat_pickup_vetoes_later_m1_shortage(self):
        self.prime(step=100, inventory=100)
        tape = tape_with_pickup(104, 2)
        tape[102]["hands"] = [["PICKUP", "WHEAT", 1]]
        parent = empty_action()
        out = self.run_lane(observation(101, market_inventory=98), parent, tape)
        self.assertIs(out, parent)
        self.assertEqual(lane.REPORT["buy_orders"], 0)

    def test_dead_market_suffix_before_pickup_does_not_veto(self):
        self.prime(step=100, inventory=100)
        tape = tape_with_pickup(104, 2)
        tape[103]["market"] = [[] for _ in range(10)] + [["BUY_SEED", "CARROT", 1]]
        parent = empty_action()
        out = self.run_lane(observation(101, market_inventory=98), parent, tape)
        self.assertEqual(out["market"], [["BUY_PRODUCT", "WHEAT", 2]])
        self.assertEqual(lane.REPORT["buy_orders"], 1)

    def test_future_shed_inflow_before_pickup_vetoes_capacity_hazard(self):
        for command in (["DROP"], ["PLACE", "CARROT", 2]):
            with self.subTest(command=command):
                lane.reset_for_tests()
                self.prime(step=100, inventory=100)
                tape = tape_with_pickup(104, 2)
                tape[102]["farmer"] = list(command)
                parent = empty_action()
                out = self.run_lane(
                    observation(101, market_inventory=98, shed={"CARROT": 98}),
                    parent,
                    tape,
                )
                self.assertIs(out, parent)
                self.assertEqual(lane.REPORT["future_pickups"], 0)
                self.assertEqual(lane.REPORT["buy_orders"], 0)

    def test_engine_float_money_activates(self):
        self.prime(step=100, inventory=100)
        parent = empty_action()
        out = self.run_lane(observation(101, market_inventory=98, money=3000.0),
                            parent, tape_with_pickup(104, 2))
        self.assertEqual(out["market"], [["BUY_PRODUCT", "WHEAT", 2]])

    def test_money_poison_fails_closed(self):
        for bad in (True, float("nan"), float("inf"), -1.0):
            with self.subTest(money=bad):
                lane.reset_for_tests()
                self.prime(step=100, inventory=100)
                parent = empty_action()
                out = self.run_lane(observation(101, market_inventory=98, money=bad),
                                    parent, tape_with_pickup(104, 2))
                self.assertIs(out, parent)

    def test_standard_configuration_is_literal_and_attribute_compatible(self):
        attr = AttrConfig(CONFIG)
        self.prime(step=100, inventory=100, configuration=attr)
        parent = empty_action()
        out = self.run_lane(observation(101, market_inventory=98), parent,
                            tape_with_pickup(104, 2), configuration=attr)
        self.assertEqual(out["market"], [["BUY_PRODUCT", "WHEAT", 2]])

        bad_configs = [
            None,
            {key: value for key, value in CONFIG.items() if key != "episodeSteps"},
            dict(CONFIG, turnsPerDay=23),
            dict(CONFIG, marketParams={"custom": 1}),
            dict(CONFIG, maxMarketOrdersPerTurn=True),
        ]
        for bad in bad_configs:
            with self.subTest(configuration=bad):
                lane.reset_for_tests()
                self.prime(step=100, inventory=100)
                parent = empty_action()
                out = lane.apply_m1_wheat_trade(
                    observation(101, market_inventory=98), parent, tape_with_pickup(104, 2),
                    configuration=bad, enabled=True)
                self.assertIs(out, parent)

    def test_current_action_shape_and_actor_cardinality_fail_closed(self):
        malformed = [
            {"hands": [["PASS"]], "market": []},
            {"farmer": ["PASS"], "hands": [["PASS"]]},
            {"farmer": ["PASS"], "hands": [], "market": []},
            {"farmer": [], "hands": [["PASS"]], "market": []},
        ]
        for parent in malformed:
            with self.subTest(parent=parent):
                lane.reset_for_tests()
                self.prime(step=100, inventory=100)
                out = self.run_lane(observation(101, market_inventory=98), parent,
                                    tape_with_pickup(104, 2))
                self.assertIs(out, parent)

    def test_malformed_player_fails_closed_without_coercion(self):
        self.prime(step=100, inventory=100)
        parent = empty_action()
        obs = observation(101, market_inventory=98)
        obs["player"] = "0"
        self.assertIs(self.run_lane(obs, parent, tape_with_pickup(104, 2)), parent)

    def test_generated_outer_wrapper_preflights_player_before_m1_lookup(self):
        source = (ROOT / "r04_full_router.py").read_text(encoding="utf-8")
        self.assertNotIn("player = int(observation['player'])", source)
        self.assertIn(
            "player = observation.get('player') if isinstance(observation, dict) else None",
            source,
        )
        self.assertIn("if type(player) is int:", source)
        self.assertIn(
            "except (AttributeError, KeyError, TypeError, IndexError, ValueError):",
            source,
        )

    def test_no_public_scarcity_is_exact_parent(self):
        self.prime(step=100, inventory=100)
        parent = empty_action()
        out = self.run_lane(observation(101, market_inventory=100), parent,
                            tape_with_pickup(104))
        self.assertIs(out, parent)

    def test_next_turn_pickup_is_left_to_v226(self):
        self.prime(step=100, inventory=100)
        parent = empty_action()
        out = self.run_lane(observation(101, market_inventory=98), parent,
                            tape_with_pickup(102))
        self.assertIs(out, parent)

    def test_current_purchase_veto_preserves_funding_order(self):
        self.prime(step=100, inventory=100)
        parent = empty_action()
        parent["market"] = [["HIRE"]]
        out = self.run_lane(observation(101, market_inventory=98), parent,
                            tape_with_pickup(104))
        self.assertIs(out, parent)
        self.assertEqual(lane.REPORT["funding_vetoes"], 1)

    def test_future_purchase_before_pickup_vetoes_early_spend(self):
        self.prime(step=100, inventory=100)
        tape = tape_with_pickup(104)
        tape[103]["market"] = [["BUY_SEED", "CARROT", 1]]
        parent = empty_action()
        out = self.run_lane(observation(101, market_inventory=98), parent, tape)
        self.assertIs(out, parent)

    def test_future_purchase_after_pickup_same_day_vetoes_early_spend(self):
        self.prime(step=100, inventory=100)
        tape = tape_with_pickup(103, 2)
        tape[110]["market"] = [["BUY_LAND"]]
        parent = empty_action()
        out = self.run_lane(observation(101, market_inventory=98), parent, tape)
        self.assertIs(out, parent)
        self.assertEqual(lane.REPORT["future_pickups"], 0)
        self.assertEqual(lane.REPORT["buy_orders"], 0)

    def test_next_day_purchase_does_not_block_same_day_pickup(self):
        self.prime(step=100, inventory=100)
        tape = tape_with_pickup(103, 2)
        tape[120]["market"] = [["BUY_LAND"]]
        parent = empty_action()
        out = self.run_lane(observation(101, market_inventory=98), parent, tape)
        self.assertEqual(out["market"], [["BUY_PRODUCT", "WHEAT", 2]])
        self.assertEqual(lane.REPORT["future_pickups"], 1)
        self.assertEqual(lane.REPORT["buy_orders"], 1)

    def test_shared_shed_capacity_veto(self):
        self.prime(step=100, inventory=100)
        parent = empty_action()
        out = self.run_lane(observation(101, market_inventory=98,
                                        shed={"CARROT": 99}),
                            parent, tape_with_pickup(104, 3))
        self.assertIs(out, parent)
        self.assertEqual(lane.REPORT["capacity_vetoes"], 1)

    def test_cash_floor_veto(self):
        self.prime(step=100, inventory=100)
        parent = empty_action()
        # Three units at an observed $20: the stale +$10 bound required $1090
        # and would admit $1100; the proven +$25 same-turn bound requires $1135.
        out = self.run_lane(observation(101, market_inventory=98, money=1100.0,
                                        wheat_price=20),
                            parent, tape_with_pickup(104, 3))
        self.assertIs(out, parent)
        self.assertEqual(lane.REPORT["funding_vetoes"], 1)

    def test_own_previous_buy_cannot_self_certify_scarcity(self):
        self.prime(step=100, inventory=100)
        first = self.run_lane(observation(101, market_inventory=98), empty_action(),
                              tape_with_pickup(104, 2))
        self.assertEqual(first["market"], [["BUY_PRODUCT", "WHEAT", 2]])
        parent = empty_action()
        out = self.run_lane(observation(102, market_inventory=96), parent,
                            tape_with_pickup(105, 2))
        self.assertIs(out, parent)

    def test_parent_wheat_buy_cannot_self_certify_next_scarcity(self):
        self.prime(step=100, inventory=100)
        parent_buy = empty_action()
        parent_buy["market"] = [["BUY_PRODUCT", "WHEAT", 2]]
        first = self.run_lane(
            observation(101, market_inventory=98),
            parent_buy,
            tape_with_pickup(104, 2),
        )
        self.assertIs(first, parent_buy)

        parent = empty_action()
        out = self.run_lane(
            observation(102, market_inventory=96),
            parent,
            tape_with_pickup(105, 2),
        )
        self.assertIs(out, parent)
        self.assertEqual(lane.REPORT["buy_orders"], 0)

    def test_install_and_titan_diagnostics_carry_key(self):
        r04.install(None, 8, 0, False, False, m1_wheat_trade=True)
        self.assertIs(r04.M1_WHEAT_TRADE, True)
        r04.install(None, 8, 0, False, False, m1_wheat_trade=False)
        self.assertIs(r04.M1_WHEAT_TRADE, False)

        agent = TitanAgent(Features(r04_sale_window=True, r04_m1_wheat_trade=True))
        agent.act(observation(0, market_inventory=100), dict(CONFIG))
        self.assertIs(r04.M1_WHEAT_TRADE, True)
        self.assertIs(agent.diagnostics["m1_wheat_trade"], True)


if __name__ == "__main__":
    unittest.main()
