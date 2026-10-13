# SPDX-License-Identifier: Apache-2.0
"""W1 subset regressions; run against repaired r04_dead_water_harvest on PYTHONPATH."""
from __future__ import annotations

import copy
import itertools
import unittest
from unittest import mock

import r04_dead_water_harvest as lane


CONFIG = {"episodeSteps": 720, "turnsPerDay": 24,
          "boardSize": 10, "shedCapacity": 100}


def fixture(weights, room, *, player=0, commands=None, carried=0):
    """Distinct mature, already-watered TOMATO plots; room precedes unit work."""
    board = [[{"kind": "SOIL"} for _ in range(10)] for _ in range(10)]
    positions = [[i % 10, i // 10] for i in range(len(weights))]
    for (x, y), weight in zip(positions, weights):
        board[y][x] = {"kind": "PLANT", "crop": "TOMATO", "planted_day": 18,
                       "yield_units": weight, "watered_today": True,
                       "max_lifespan_step": -1}
    farm = {"farmer": positions[0], "hands": positions[1:], "tiles": board}
    inventories = [{} for _ in weights]
    inventories[0] = {"WHEAT": carried}
    obs = {"step": 695, "day": 28, "player": player,
           "farms": [copy.deepcopy(farm), copy.deepcopy(farm)],
           "private": {"shed": {"WHEAT": 100 - room - carried},
                       "inventories": inventories}}
    rows = copy.deepcopy(commands) if commands is not None else [["WATER"] for _ in weights]
    action = {"farmer": rows[0], "hands": rows[1:], "market": []}
    return obs, action


def commands(action):
    return [action["farmer"]] + action["hands"]


def selected(action):
    return tuple(i for i, row in enumerate(commands(action)) if row == ["HARVEST"])


def oracle(weights, room):
    """Independent brute force; maximum units then lexicographic actor-index tie."""
    best = (0, ())
    for mask in range(1 << len(weights)):
        indices = tuple(i for i in range(len(weights)) if mask & (1 << i))
        units = sum(weights[i] for i in indices)
        if units <= room and (units > best[0] or (units == best[0] and indices < best[1])):
            best = (units, indices)
    return best[1]


class CapacitySubsetTest(unittest.TestCase):
    def setUp(self):
        lane.reset()

    def apply(self, obs, action):
        return lane.apply_dead_water_harvest(obs, action, CONFIG, enabled=True)

    def test_overfull_set_recovers_fitting_hand(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                lane.reset()
                obs, action = fixture([6, 4], 4, player=seat)
                out = self.apply(obs, action)
                self.assertEqual(selected(out), (1,))
                self.assertEqual(out["farmer"], ["WATER"])
                self.assertEqual(lane.get_report()["recovered"], 1)

    def test_selection_is_not_largest_first_greedy(self):
        obs, action = fixture([6, 5, 5], 10)
        self.assertEqual(selected(self.apply(obs, action)), (1, 2))

    def test_fitting_farmer_is_kept_when_hand_is_too_large(self):
        obs, action = fixture([3, 101], 3)
        out = self.apply(obs, action)
        self.assertEqual(selected(out), (0,))
        self.assertEqual(out["hands"], [["WATER"]])

    def test_mandatory_harvest_gets_capacity_before_optional_candidates(self):
        rows = [["WATER"], ["WATER"], ["HARVEST"]]
        obs, action = fixture([6, 4, 3], 7, commands=rows)
        out = self.apply(obs, action)
        self.assertEqual(selected(out), (1, 2))
        self.assertEqual(lane.get_report()["recovered"], 1)
        self.assertIs(out["hands"][1], action["hands"][1])

    def test_mandatory_fertilizer_collection_is_reserved(self):
        rows = [["WATER"], ["WATER"], ["COLLECT_FERTILIZER"]]
        obs, action = fixture([6, 4, 0], 5, commands=rows)
        out = self.apply(obs, action)
        self.assertEqual(selected(out), (1,))
        self.assertEqual(out["hands"][1], ["COLLECT_FERTILIZER"])

    def test_carried_inventory_is_not_available_for_optional_harvest(self):
        obs, action = fixture([6, 4], 4, carried=10)
        self.assertEqual(selected(self.apply(obs, action)), (1,))
        obs["private"]["inventories"][0]["WHEAT"] += 1
        self.assertIs(self.apply(obs, action), action)

    def test_all_fit_matches_original_all_candidate_behavior(self):
        obs, action = fixture([6, 4], 10)
        out = self.apply(obs, action)
        self.assertEqual(selected(out), (0, 1))
        self.assertEqual(lane.get_report()["capacity_block"], 0)
        self.assertEqual(lane.get_report()["recovered"], 2)

    def test_no_fit_is_exact_identity_without_false_recovery(self):
        obs, action = fixture([6, 4], 3)
        self.assertIs(self.apply(obs, action), action)
        self.assertEqual(lane.get_report()["recovered"], 0)
        self.assertEqual(lane.get_report()["capacity_block"], 1)

    def test_mandatory_overflow_never_credits_optional_recovery(self):
        obs, action = fixture([1, 1, 5], 4,
                              commands=[["WATER"], ["WATER"], ["HARVEST"]])
        self.assertIs(self.apply(obs, action), action)
        self.assertEqual(lane.get_report()["recovered"], 0)

    def test_tie_break_is_stable_actor_index_order(self):
        obs, action = fixture([4, 2, 2], 4)
        for _ in range(3):
            self.assertEqual(selected(self.apply(obs, action)), (0,))
        obs, action = fixture([3, 3, 3], 6)
        self.assertEqual(selected(self.apply(obs, action)), (0, 1))

    def test_outputs_preserve_parent_and_observation_bytes(self):
        obs, action = fixture([6, 4], 4)
        action["market"] = [["SELL", "WHEAT", 1]]
        action["extra"] = {"opaque": [1, 2, 3]}
        before = copy.deepcopy((obs, action))
        out = self.apply(obs, action)
        self.assertEqual((obs, action), before)
        self.assertEqual(selected(out), (1,))
        self.assertIs(out["market"], action["market"])
        self.assertIs(out["extra"], action["extra"])
        self.assertIs(out["farmer"], action["farmer"])
        self.assertIsNot(out["hands"][0], action["hands"][0])

    def test_untrusted_sibling_yield_rejects_entire_partial_transform(self):
        for bad in (None, True, -1, "4", 1.5):
            with self.subTest(bad=bad):
                obs, action = fixture([6, 4, 3], 7,
                                      commands=[["WATER"], ["WATER"], ["HARVEST"]])
                obs["farms"][0]["tiles"][0][2]["yield_units"] = bad
                self.assertIs(self.apply(obs, action), action)

    def test_malformed_sibling_commands_still_fail_closed(self):
        for row in ([], ["UNKNOWN"], "PASS", None):
            obs, action = fixture([6, 4, 0], 4)
            action["hands"][1] = row
            self.assertIs(self.apply(obs, action), action)

    def test_invalid_inventory_surface_still_fails_closed(self):
        for bad in (None, True, -1, "1", 1.5):
            obs, action = fixture([6, 4], 4)
            obs["private"]["inventories"][1]["WOOL"] = bad
            self.assertIs(self.apply(obs, action), action)
        obs, action = fixture([6, 4], 4)
        obs["private"]["inventories"].pop()
        self.assertIs(self.apply(obs, action), action)

    def test_disabled_identity_even_when_subset_would_fit(self):
        obs, action = fixture([6, 4], 4)
        self.assertIs(lane.apply_dead_water_harvest(obs, action, CONFIG, enabled=False), action)
        self.assertEqual(lane.get_report()["recovered"], 0)

    def test_market_inflow_malformed_and_inert_rows_keep_existing_vetoes(self):
        for market in ([["BUY_PRODUCT", "WHEAT", 1]],
                       [["BUY_ANIMAL", "SHEEP", 1]], [[]], [["SELL"]],
                       [["SELL", "WHEAT", 0]], [["HIRE", "extra"]]):
            obs, action = fixture([6, 4], 4)
            action["market"] = market
            self.assertIs(self.apply(obs, action), action)

    def test_does_not_credit_market_sales_as_storage_room(self):
        obs, action = fixture([6, 4], 3)
        action["market"] = [["SELL", "WHEAT", 100]]
        self.assertIs(self.apply(obs, action), action)

    def test_whole_farm_capacity_bound_for_every_selected_case(self):
        count = 0
        for weights in itertools.product(range(1, 5), repeat=3):
            for room in range(13):
                obs, action = fixture(weights, room)
                before = copy.deepcopy((obs, action))
                out = self.apply(obs, action)
                indices = selected(out)
                self.assertEqual(indices, oracle(weights, room))
                total = sum(obs["private"]["shed"].values())
                total += sum(sum(inv.values()) for inv in obs["private"]["inventories"])
                total += sum(weights[i] for i in indices)
                self.assertLessEqual(total, 100)
                self.assertEqual((obs, action), before)
                if not indices:
                    self.assertIs(out, action)
                count += 1
        self.assertEqual(count, 832)

    def test_bounded_selector_matches_exhaustive_powerset_oracle(self):
        count = 0
        for length in range(6):
            for weights in itertools.product(range(1, 5), repeat=length):
                items = list(enumerate(weights))
                for room in range(13):
                    self.assertEqual(tuple(lane._max_recovered_subset(items, room)),
                                     oracle(weights, room), (weights, room))
                    count += 1
        self.assertEqual(count, 17745)

    def test_selector_never_splits_harvest_or_expands_to_huge_yield(self):
        huge = 10 ** 1000
        self.assertEqual(lane._max_recovered_subset([(0, huge), (1, 4)], 4), [1])
        self.assertEqual(lane._max_recovered_subset([(0, 6)], 5), [])
        self.assertEqual(lane._max_recovered_subset([(i, 1) for i in range(100)], 99),
                         list(range(99)))

    def test_selector_rejects_invalid_capacity_or_candidate_contract(self):
        for room in (True, -1, 101, "4", None, 4.0):
            self.assertEqual(lane._max_recovered_subset([(0, 4)], room), [])
        for items in ([(0, True)], [(0, 0)], [(0, -1)], [(0, 1.5)],
                      [(True, 2)], [(0, 1), (0, 2)], [(2, 1), (1, 2)]):
            self.assertEqual(lane._max_recovered_subset(items, 4), [])

    def test_expired_annual_can_fill_subset_without_touching_live_annual(self):
        obs, action = fixture([6, 4, 2], 4)
        first, second, third = obs["farms"][0]["tiles"][0][:3]
        first.update(crop="WHEAT", planted_day=26, max_lifespan_step=744)
        second.update(crop="CARROT", planted_day=25, watered_today=False,
                      max_lifespan_step=695)
        third.update(crop="WHEAT", planted_day=26, max_lifespan_step=744)
        out = self.apply(obs, action)
        self.assertEqual(selected(out), (1,))
        self.assertEqual(out["farmer"], ["WATER"])
        self.assertEqual(out["hands"][1], ["WATER"])

    def test_partial_selection_requires_unchanged_final_capacity_certificate(self):
        obs, action = fixture([6, 4], 4)
        with mock.patch.object(lane, "_capacity_safe", side_effect=[False, True, False]) as proof:
            self.assertIs(self.apply(obs, action), action)
        self.assertEqual(proof.call_count, 3)
        self.assertEqual(proof.call_args.args[-1], [1])
        self.assertEqual(lane.get_report()["recovered"], 0)

    def test_all_fit_does_not_invoke_new_selector(self):
        obs, action = fixture([6, 4], 10)
        with mock.patch.object(lane, "_max_recovered_subset", side_effect=RuntimeError("unused")) as choose:
            self.assertEqual(selected(self.apply(obs, action)), (0, 1))
        choose.assert_not_called()

    def test_window_geometry_and_configuration_are_not_broadened(self):
        for step in (671, 694, 696, 718, 719):
            obs, action = fixture([6, 4], 4)
            obs.update(step=step, day=step // 24)
            self.assertIs(self.apply(obs, action), action)
        obs, action = fixture([6, 4], 4)
        obs["farms"][0]["hands"][0] = [0, 0]
        self.assertIs(self.apply(obs, action), action)
        obs, action = fixture([6, 4], 4)
        cfg = dict(CONFIG, shedCapacity=101)
        self.assertIs(lane.apply_dead_water_harvest(obs, action, cfg), action)


if __name__ == "__main__":
    unittest.main()
