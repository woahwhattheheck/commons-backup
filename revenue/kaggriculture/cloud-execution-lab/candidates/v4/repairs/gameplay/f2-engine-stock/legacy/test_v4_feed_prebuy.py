# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_feed_prebuy as lane
import r04_full_router as r04


def _tile_grid():
    tiles = [[None for _ in range(10)] for _ in range(10)]
    tiles[4][6] = {
        "animal": "GOOSE",
        "fed_today": False,
        "consecutive_unfed": 1,
    }
    return tiles


def _observation(wheat=0, money=5000.0, wheat_price=30, egg_price=100):
    return {
        "step": 39,
        "player": 0,
        "farms": [{
            "money": money,
            "farmer": [4, 4],
            "hands": [],
            "tiles": _tile_grid(),
        }],
        "private": {
            "shed": {"WHEAT": wheat},
            "inventories": [{}],
        },
        "market": {
            "inventory": {"WHEAT": 10000},
            "prices": {
                "WHEAT": wheat_price,
                "EGG": egg_price,
                "MILK": 100,
                "WOOL": 100,
                "FERTILIZER": 10,
                "CARROT": 50,
                "TOMATO": 50,
                "STRAWBERRY": 50,
                "MELON": 50,
            }
        },
    }


def _action():
    return {"farmer": ["PASS"], "hands": [], "market": []}


def _standard_config():
    return {
        "episodeSteps": 720,
        "boardSize": 10,
        "turnsPerDay": 24,
        "shedCapacity": 100,
        "maxMarketOrdersPerTurn": 10,
        "marketParams": {},
    }


def _apply(observation, action, configuration=None, enabled=True):
    if configuration is None:
        configuration = _standard_config()
    return lane.apply_feed_prebuy(
        observation, action, configuration=configuration, enabled=enabled)


class FeedPrebuyTests(unittest.TestCase):
    def setUp(self):
        self.old_policy = r04._POLICY
        tape = [{"farmer": ["PASS"], "hands": [], "market": []} for _ in range(719)]
        state = SimpleNamespace(
            plan=0,
            last_step=39,
            day=1,
            queues={},
            v217_used=0,
            v217_task=None,
        )
        r04._POLICY = SimpleNamespace(players={0: state}, tapes=[tape])

    def tearDown(self):
        r04._POLICY = self.old_policy

    def test_disabled_returns_exact_parent(self):
        parent = _action()
        self.assertIs(_apply(_observation(), parent, enabled=False), parent)

    def test_two_wheat_prebuy_unlocks_literal_v217_rescue(self):
        parent = _action()
        out = _apply(_observation(wheat=0), parent)
        self.assertIsNot(out, parent)
        self.assertEqual(out["market"], [["BUY_PRODUCT", "WHEAT", 2]])
        self.assertEqual(parent["market"], [])

    def test_explicit_standard_config_preserves_activation(self):
        out = _apply(_observation(wheat=0), _action(), configuration=_standard_config())
        self.assertEqual(out["market"], [["BUY_PRODUCT", "WHEAT", 2]])

    def test_kaggle_attribute_config_preserves_activation(self):
        values = _standard_config()
        values.pop("marketParams")  # absent is standard semantics too
        config = SimpleNamespace(**values)
        out = lane.apply_feed_prebuy(
            _observation(wheat=0), _action(), configuration=config, enabled=True)
        self.assertEqual(out["market"], [["BUY_PRODUCT", "WHEAT", 2]])

    def test_missing_config_and_nonstandard_episode_fail_closed(self):
        parent = _action()
        self.assertIs(
            lane.apply_feed_prebuy(_observation(), parent, configuration=None, enabled=True),
            parent,
        )

        config = _standard_config()
        config["episodeSteps"] = 721
        parent = _action()
        self.assertIs(_apply(_observation(), parent, configuration=config), parent)

        attr_config = SimpleNamespace(**_standard_config())
        attr_config.episodeSteps = 721
        parent = _action()
        self.assertIs(
            lane.apply_feed_prebuy(
                _observation(), parent, configuration=attr_config, enabled=True),
            parent,
        )

    def test_engine_float_money_activates_and_type_poison_fails_closed(self):
        out = _apply(_observation(money=5000.0), _action())
        self.assertEqual(out["market"], [["BUY_PRODUCT", "WHEAT", 2]])

        class IntSubclass(int):
            pass

        class FloatSubclass(float):
            pass

        for bad_money in (
            True,
            float("nan"),
            float("inf"),
            float("-inf"),
            -1.0,
            "5000",
            IntSubclass(5000),
            FloatSubclass(5000.0),
            10 ** 1000,
        ):
            parent = _action()
            with self.subTest(money=bad_money):
                self.assertIs(
                    _apply(_observation(money=bad_money), parent),
                    parent,
                )

    def test_public_wheat_stock_must_cover_exact_prebuy_quantity(self):
        bad_inventories = (
            {"WHEAT": 0},
            {"WHEAT": 1},
            {"WHEAT": True},
            {"WHEAT": 2.0},
            {"WHEAT": -1},
            {"WHEAT": "2"},
            {"WHEAT": None},
            {},
        )
        for inventory in bad_inventories:
            obs = _observation(wheat=0)
            obs["market"]["inventory"] = inventory
            parent = _action()
            with self.subTest(inventory=inventory):
                self.assertIs(_apply(obs, parent), parent)

        obs = _observation(wheat=0)
        del obs["market"]["inventory"]
        parent = _action()
        self.assertIs(_apply(obs, parent), parent)

        obs = _observation(wheat=0)
        obs["market"]["inventory"] = {"WHEAT": 2}
        out = _apply(obs, _action())
        self.assertEqual(out["market"], [["BUY_PRODUCT", "WHEAT", 2]])

    def test_one_wheat_prebuy_is_minimal_when_one_is_already_stored(self):
        out = _apply(_observation(wheat=1), _action())
        self.assertEqual(out["market"], [["BUY_PRODUCT", "WHEAT", 1]])

    def test_does_not_buy_when_v217_is_already_funded(self):
        parent = _action()
        self.assertIs(_apply(_observation(wheat=2), parent), parent)

    def test_existing_market_order_is_a_hard_barrier(self):
        parent = _action()
        parent["market"] = [["SELL", "CARROT", 1]]
        self.assertIs(_apply(_observation(), parent), parent)

    def test_nonpass_unit_action_is_a_hard_barrier(self):
        parent = _action()
        parent["farmer"] = ["EAST"]
        self.assertIs(_apply(_observation(), parent), parent)

    def test_actor_surface_must_be_explicit_and_cardinality_exact(self):
        obs = _observation()
        malformed = []
        missing_farmer = _action(); missing_farmer.pop("farmer")
        missing_hands = _action(); missing_hands.pop("hands")
        empty_farmer = _action(); empty_farmer["farmer"] = []
        malformed.extend((missing_farmer, missing_hands, empty_farmer))
        for parent in malformed:
            with self.subTest(parent=parent):
                self.assertIs(_apply(obs, parent), parent)

        one_hand_obs = _observation()
        one_hand_obs["farms"][0]["hands"] = [[4, 4]]
        parent = _action()
        self.assertIs(_apply(one_hand_obs, parent), parent)

        one_hand_obs["private"]["inventories"] = [{}, {}]
        parent = {"farmer": ["PASS"], "hands": [["PASS"]], "market": []}
        out = _apply(one_hand_obs, parent)
        self.assertEqual(out["market"], [["BUY_PRODUCT", "WHEAT", 2]])

    def test_nonstandard_engine_contract_fails_closed(self):
        obs = _observation()
        variants = (
            ("episodeSteps", 719),
            ("boardSize", 11),
            ("turnsPerDay", 23),
            ("shedCapacity", 99),
            ("maxMarketOrdersPerTurn", 9),
            ("boardSize", True),
            ("shedCapacity", 100.0),
        )
        for key, value in variants:
            config = _standard_config()
            config[key] = value
            parent = _action()
            with self.subTest(key=key, value=value):
                self.assertIs(
                    _apply(obs, parent, configuration=config),
                    parent,
                )

        for market_params in ({"WHEAT": {}}, [], "", 0, False):
            parent = _action()
            config = _standard_config(); config["marketParams"] = market_params
            with self.subTest(marketParams=market_params):
                self.assertIs(_apply(obs, parent, configuration=config), parent)

        parent = _action()
        self.assertIs(
            lane.apply_feed_prebuy(obs, parent, configuration=[], enabled=True),
            parent,
        )

    def test_malformed_negative_planner_target_fails_closed(self):
        obs = _observation(wheat=0)
        # Without strict target validation, [-1, 4] aliases the last tile in
        # Python and can make malformed planner state look like a real animal.
        obs["farms"][0]["tiles"][4][-1] = {
            "animal": "GOOSE",
            "fed_today": False,
            "consecutive_unfed": 1,
        }
        parent = _action()

        def malformed_plan(view, _state, _next_step, _next_action, _pending):
            return {"target": [-1, 4]} if view.shed.get("WHEAT", 0) >= 2 else None

        with mock.patch.object(r04, "_v217_plan", side_effect=malformed_plan):
            self.assertIs(_apply(obs, parent), parent)

    def test_low_output_value_rejects_purchase(self):
        parent = _action()
        self.assertIs(
            _apply(_observation(wheat_price=40, egg_price=50), parent),
            parent,
        )

    def test_cash_reserve_rejects_purchase(self):
        parent = _action()
        self.assertIs(_apply(_observation(money=1050.0), parent), parent)

    def test_capacity_rejects_purchase(self):
        obs = _observation()
        obs["private"]["shed"] = {"WHEAT": 0, "CARROT": 99}
        parent = _action()
        self.assertIs(_apply(obs, parent), parent)

    def test_wrong_hour_returns_exact_parent(self):
        obs = _observation()
        obs["step"] = 38
        r04._POLICY.players[0].last_step = 38
        parent = _action()
        self.assertIs(_apply(obs, parent), parent)

    def test_parent_and_observation_are_not_mutated(self):
        obs = _observation()
        parent = _action()
        before_obs = copy.deepcopy(obs)
        before_parent = copy.deepcopy(parent)
        _apply(obs, parent)
        self.assertEqual(obs, before_obs)
        self.assertEqual(parent, before_parent)


if __name__ == "__main__":
    unittest.main()