# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
LAB = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(LAB))

import mechanics as m
from fert_hand_current import (
    FertHandCurrentABI,
    HISTORICAL_SOURCE_BLOB,
    HISTORICAL_SOURCE_COMMIT,
    HISTORICAL_SUBMISSION_SHA256,
    _fib,
)


def grid(target=None, *, planted_day=22):
    rows = [[None for _ in range(10)] for _ in range(10)]
    if target is not None:
        x, y = target
        rows[y][x] = {
            "kind": "PLANT",
            "crop": "CARROT",
            "planted_day": planted_day,
            "fertilized_until_day": -1,
            "yield_units": 1,
            "watered_today": False,
        }
    return rows


def farm(*, hands=None, target=None, money=10000, hires_today=0):
    return {
        "farmer": [0, 0],
        "hands": deepcopy(hands or []),
        "tiles": grid(target),
        "money": money,
        "hires_today": hires_today,
        "unlocked_quadrants": ["NW"],
    }


def observation(
    *,
    step=579,
    hands=None,
    inventories=None,
    shed=None,
    target=(2, 2),
    money=10000,
    hires_today=0,
):
    own_hands = deepcopy(hands or [])
    return {
        "player": 0,
        "step": step,
        "farms": [
            farm(
                hands=own_hands,
                target=target,
                money=money,
                hires_today=hires_today,
            ),
            farm(),
        ],
        "private": {
            "inventories": deepcopy(
                inventories if inventories is not None
                else [{} for _ in range(len(own_hands) + 1)]
            ),
            "shed": deepcopy(shed or {}),
            "seeds": {},
        },
        "market": {
            "prices": {"CARROT": 1000, "FERTILIZER": 10},
            "inventory": {},
        },
    }


def selected(*, farmer=None, hands=None, market=None):
    return {
        "farmer": deepcopy(farmer or ["PASS"]),
        "hands": deepcopy(hands or []),
        "market": deepcopy(market or []),
    }


def route_tail(step, *, hand_count=0):
    end = min(((step // 24) + 1) * 24, 720)
    return [
        {
            "farmer": ["PASS"],
            "hands": [["PASS"] for _ in range(hand_count)],
            "market": [],
        }
        for _ in range(max(0, end - step - 1))
    ]


class FertHandCurrentABITests(unittest.TestCase):
    def test_provenance_is_exact_submitted_v31(self):
        self.assertEqual(
            HISTORICAL_SOURCE_COMMIT,
            "a90d888f03987ef0b35cfd20ec3519c6144db08a",
        )
        self.assertEqual(
            HISTORICAL_SOURCE_BLOB,
            "79fefde712a38f802e9d77e68b3f8943fe137cd3",
        )
        self.assertEqual(
            HISTORICAL_SUBMISSION_SHA256,
            "5db3921f85efbc7596e5a1e7e198fc5f4644ceea43d8e8323c74ded7b4ba4361",
        )

    def test_hire_cost_matches_pinned_engine_fibonacci(self):
        for hires in range(15):
            with self.subTest(hires=hires):
                self.assertEqual(_fib(hires), m._hire_cost(hires, 1))

    def test_profitable_hire_appends_without_reordering_parent_market(self):
        adapter = FertHandCurrentABI()
        obs = observation()
        parent = selected(market=[["SELL", "WOOL", 1], ["BUY_SEED", "CARROT", 1]])
        before = deepcopy((obs, parent))

        result, report = adapter.transform_selected(
            obs, {}, parent, future_actions=route_tail(obs["step"])
        )

        self.assertTrue(report["changed"])
        self.assertEqual(report["reason"], "admit_fertilizer_hand")
        self.assertEqual(result["market"][:2], parent["market"])
        self.assertEqual(result["market"][-2:], [
            ["HIRE"],
            ["BUY_PRODUCT", "FERTILIZER", 1],
        ])
        self.assertEqual((obs, parent), before)

    def test_same_step_hire_retry_is_identical(self):
        adapter = FertHandCurrentABI()
        obs = observation()
        parent = selected(market=[["SELL", "WOOL", 1]])
        tail = route_tail(obs["step"])

        first, first_report = adapter.transform_selected(
            obs, {}, parent, future_actions=tail
        )
        retry, retry_report = adapter.transform_selected(
            obs, {}, parent, future_actions=tail
        )

        self.assertEqual(retry, first)
        self.assertEqual(first_report["reason"], "admit_fertilizer_hand")
        self.assertEqual(retry_report["reason"], "reapply_hire_plan")

    def test_successful_hire_is_hidden_from_parent_view(self):
        adapter = FertHandCurrentABI()
        step = 579
        adapter.transform_selected(
            observation(step=step),
            {},
            selected(),
            future_actions=route_tail(step),
        )

        next_obs = observation(
            step=580,
            hands=[[4, 4]],
            inventories=[{"CARROT": 2}, {"FERTILIZER": 0}],
            shed={"FERTILIZER": 1},
        )
        before = deepcopy(next_obs)
        view, report = adapter.parent_observation(next_obs)

        self.assertTrue(report["changed"])
        self.assertEqual(report["reason"], "hide_owned_hand")
        self.assertEqual(view["farms"][0]["hands"], [])
        self.assertEqual(view["private"]["inventories"], [{"CARROT": 2}])
        self.assertEqual(next_obs, before)

    def test_owned_hand_pickup_is_reinserted_at_exact_index(self):
        adapter = FertHandCurrentABI()
        step = 579
        adapter.transform_selected(
            observation(step=step, hands=[[8, 8]], inventories=[{}, {}]),
            {},
            selected(hands=[["PASS"]]),
            future_actions=route_tail(step, hand_count=1),
        )
        # The candidate hire becomes hand index 1, after the incumbent hand.
        next_obs = observation(
            step=580,
            hands=[[8, 8], [4, 4]],
            inventories=[{}, {}, {}],
            shed={"FERTILIZER": 2},
        )
        view, view_report = adapter.parent_observation(next_obs)
        self.assertEqual(view_report["owned_index"], 1)
        self.assertEqual(view["farms"][0]["hands"], [[8, 8]])

        parent = selected(hands=[["WEST"]], market=[["SELL", "WOOL", 1]])
        result, report = adapter.transform_selected(
            next_obs,
            {},
            parent,
            future_actions=route_tail(580, hand_count=1),
        )
        self.assertEqual(report["owned_index"], 1)
        self.assertEqual(result["hands"], [
            ["WEST"],
            ["PICKUP", "FERTILIZER", 1],
        ])
        self.assertEqual(result["market"], parent["market"])

        retry, _ = adapter.transform_selected(
            next_obs,
            {},
            parent,
            future_actions=route_tail(580, hand_count=1),
        )
        self.assertEqual(retry, result)

    def test_owned_hand_fertilizes_without_mutating_parent_commands(self):
        adapter = FertHandCurrentABI()
        adapter.transform_selected(
            observation(step=579),
            {},
            selected(),
            future_actions=route_tail(579),
        )
        # Resolve ownership and mark the first shed pickup complete.
        pickup_obs = observation(
            step=580,
            hands=[[4, 4]],
            inventories=[{}, {}],
            shed={"FERTILIZER": 1},
        )
        adapter.parent_observation(pickup_obs)
        adapter.transform_selected(
            pickup_obs,
            {},
            selected(),
            future_actions=route_tail(580),
        )

        target_obs = observation(
            step=581,
            hands=[[2, 2]],
            inventories=[{}, {"FERTILIZER": 1}],
            target=(2, 2),
        )
        parent_view, _ = adapter.parent_observation(target_obs)
        self.assertEqual(parent_view["farms"][0]["hands"], [])
        action = selected(farmer=["WEST"], market=[["SELL", "MILK", 1]])
        result, report = adapter.transform_selected(
            target_obs,
            {},
            action,
            future_actions=route_tail(581),
        )
        self.assertEqual(report["command"], ["FERTILIZE"])
        self.assertEqual(result["farmer"], action["farmer"])
        self.assertEqual(result["market"], action["market"])
        self.assertEqual(result["hands"], [["FERTILIZE"]])

    def test_future_parent_hire_blocks_candidate(self):
        adapter = FertHandCurrentABI()
        obs = observation()
        tail = route_tail(obs["step"])
        tail[0]["market"] = [["HIRE"]]

        result, report = adapter.transform_selected(
            obs, {}, selected(), future_actions=tail
        )
        self.assertFalse(report["changed"])
        self.assertEqual(report["reason"], "future_parent_hire")
        self.assertIsInstance(result, dict)

    def test_complete_route_tail_is_required_for_new_hire(self):
        adapter = FertHandCurrentABI()
        obs = observation()
        for tail in (None, [], route_tail(obs["step"])[:-1]):
            with self.subTest(tail=tail):
                fresh = FertHandCurrentABI()
                result, report = fresh.transform_selected(
                    obs, {}, selected(), future_actions=tail
                )
                self.assertFalse(report["changed"])
                self.assertEqual(report["reason"], "missing_complete_route_tail")
                self.assertEqual(result, selected())

    def test_malformed_route_tail_fails_closed_before_scanning(self):
        obs = observation()
        malformed = route_tail(obs["step"])
        malformed[0]["hands"] = 17
        result, report = FertHandCurrentABI().transform_selected(
            obs, {}, selected(), future_actions=malformed
        )
        self.assertFalse(report["changed"])
        self.assertEqual(report["reason"], "missing_complete_route_tail")
        self.assertEqual(result, selected())

    def test_market_capacity_and_parent_hire_fail_closed(self):
        obs = observation()
        tail = route_tail(obs["step"])

        adapter = FertHandCurrentABI()
        parent_hire = selected(market=[["HIRE"]])
        result, report = adapter.transform_selected(
            obs, {}, parent_hire, future_actions=tail
        )
        self.assertEqual(report["reason"], "parent_hire_present")
        self.assertEqual(result, parent_hire)

        adapter = FertHandCurrentABI()
        full = selected(market=[["SELL", "WOOL", 1] for _ in range(10)])
        result, report = adapter.transform_selected(
            obs, {}, full, future_actions=tail
        )
        self.assertEqual(report["reason"], "market_capacity")
        self.assertEqual(result, full)

    def test_nonstandard_config_and_identity_types_fail_closed(self):
        parent = selected()
        cases = [
            ({"boardSize": 8}, observation(), "outside_standard_config"),
            ({"maxMarketOrdersPerTurn": 9}, observation(), "outside_standard_config"),
            ({"turnsPerDay": 12}, observation(), "outside_standard_config"),
            ({"episodeSteps": 721}, observation(), "outside_standard_config"),
            ({"farmHandCostMult": 2}, observation(), "outside_standard_config"),
        ]
        for cfg, obs, reason in cases:
            with self.subTest(cfg=cfg):
                result, report = FertHandCurrentABI().transform_selected(
                    obs, cfg, parent, future_actions=route_tail(obs["step"])
                )
                self.assertEqual(report["reason"], reason)
                self.assertEqual(result, parent)

        for player, step in ((True, 579), (0, True), ("0", 579), (2, 579), (0, -1)):
            with self.subTest(player=player, step=step):
                obs = observation()
                obs["player"] = player
                obs["step"] = step
                result, report = FertHandCurrentABI().transform_selected(
                    obs, {}, parent, future_actions=route_tail(579)
                )
                self.assertEqual(report["reason"], "malformed_observation")
                self.assertEqual(result, parent)

    def test_hand_cardinality_drift_never_reindexes_parent(self):
        adapter = FertHandCurrentABI()
        adapter.transform_selected(
            observation(step=579),
            {},
            selected(),
            future_actions=route_tail(579),
        )
        next_obs = observation(
            step=580,
            hands=[[4, 4]],
            inventories=[{}, {}],
            shed={"FERTILIZER": 1},
        )
        adapter.parent_observation(next_obs)

        wrong_parent = selected(hands=[["PASS"]])
        result, report = adapter.transform_selected(
            next_obs,
            {},
            wrong_parent,
            future_actions=route_tail(580),
        )
        self.assertEqual(report["reason"], "parent_hand_cardinality")
        self.assertEqual(result, wrong_parent)

    def test_day_rollover_drops_stale_owned_hand_state(self):
        adapter = FertHandCurrentABI()
        adapter.transform_selected(
            observation(step=579),
            {},
            selected(),
            future_actions=route_tail(579),
        )
        hired = observation(
            step=580,
            hands=[[4, 4]],
            inventories=[{}, {}],
            shed={"FERTILIZER": 1},
        )
        adapter.parent_observation(hired)

        next_day = observation(step=600, hands=[], inventories=[{}], target=None)
        view, report = adapter.parent_observation(next_day)
        self.assertFalse(report["changed"])
        self.assertEqual(report["reason"], "no_owned_hand")
        self.assertEqual(view["farms"][0]["hands"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
