# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import unittest

import r04_idle_hands as lane

CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10}


def _grid():
    return [[None for _ in range(10)] for _ in range(10)]


def _animal(kind="GOOSE", *, fed=False, cared=False):
    structure = "COOP" if kind == "GOOSE" else "PASTURE"
    return {
        "kind": structure,
        "animal": kind,
        "placed_day": 0,
        "yield_units": 0,
        "consecutive_unfed": 0,
        "fed_today": fed,
        "cared_today": cared,
        "fertilizer_available": False,
        "pending_care_bonus": 0,
    }


def _wheat(*, planted_day=0, coverage=-1):
    return {
        "kind": "PLANT",
        "crop": "WHEAT",
        "planted_day": planted_day,
        "watered_today": False,
        "consecutive_unwatered": 0,
        "yield_units": 1,
        "max_lifespan_step": 120,
        "fertilized_until_day": coverage,
    }


def _case(*, positions=None, inventories=None, tiles=None, step=48, player=0):
    positions = positions or [[1, 1]]
    inventories = inventories or [{} for _ in positions]
    grid = _grid()
    for (x, y), tile in (tiles or {}).items():
        grid[y][x] = tile
    farm = {"farmer": list(positions[0]), "hands": [list(x) for x in positions[1:]], "tiles": grid}
    other = {"farmer": [4, 4], "hands": [], "tiles": _grid()}
    obs = {
        "step": step,
        "player": player,
        "farms": [farm, other],
        "private": {"inventories": copy.deepcopy(inventories)},
    }
    action = {
        "farmer": ["PASS"],
        "hands": [["PASS"] for _ in positions[1:]],
        "market": [],
    }
    return obs, action


class IdleHandsTests(unittest.TestCase):
    def test_all_disabled_is_exact_parent(self):
        obs, parent = _case(tiles={(1, 1): _animal()})
        self.assertIs(lane.apply_all(parent, obs, CONFIG), parent)

    def test_feed_rewrites_literal_pass_with_own_wheat(self):
        obs, parent = _case(inventories=[{"WHEAT": 1}], tiles={(1, 1): _animal(fed=False)})
        before = copy.deepcopy(parent)
        out = lane.apply_feed(parent, obs, CONFIG, enabled=True)
        self.assertEqual(out["farmer"], ["FEED"])
        self.assertEqual(parent, before)
        self.assertIsNot(out, parent)

    def test_feed_without_wheat_or_already_fed_is_identity(self):
        obs, parent = _case(tiles={(1, 1): _animal(fed=False)})
        self.assertIs(lane.apply_feed(parent, obs, CONFIG, enabled=True), parent)
        obs, parent = _case(inventories=[{"WHEAT": 2}], tiles={(1, 1): _animal(fed=True)})
        self.assertIs(lane.apply_feed(parent, obs, CONFIG, enabled=True), parent)

    def test_feed_can_rewrite_independent_actors(self):
        obs, parent = _case(
            positions=[[1, 1], [2, 2]],
            inventories=[{"WHEAT": 1}, {"WHEAT": 1}],
            tiles={(1, 1): _animal("GOOSE"), (2, 2): _animal("COW")},
        )
        out = lane.apply_feed(parent, obs, CONFIG, enabled=True)
        self.assertEqual(out["farmer"], ["FEED"])
        self.assertEqual(out["hands"], [["FEED"]])

    def test_duplicate_occupancy_site_never_transforms(self):
        obs, parent = _case(
            positions=[[1, 1], [1, 1]],
            inventories=[{"WHEAT": 1}, {"WHEAT": 1}],
            tiles={(1, 1): _animal("GOOSE")},
        )
        self.assertIs(lane.apply_feed(parent, obs, CONFIG, enabled=True), parent)

    def test_care_goose_only_requires_already_fed_uncared(self):
        obs, parent = _case(tiles={(1, 1): _animal("GOOSE", fed=True, cared=False)})
        out = lane.apply_care(parent, obs, CONFIG, enabled=True, goose_only=True)
        self.assertEqual(out["farmer"], ["CARE"])
        obs, parent = _case(tiles={(1, 1): _animal("COW", fed=True, cared=False)})
        self.assertIs(lane.apply_care(parent, obs, CONFIG, enabled=True, goose_only=True), parent)
        obs, parent = _case(tiles={(1, 1): _animal("GOOSE", fed=False, cared=False)})
        self.assertIs(lane.apply_care(parent, obs, CONFIG, enabled=True, goose_only=True), parent)

    def test_care_all_accepts_fed_cow_but_not_already_cared(self):
        obs, parent = _case(tiles={(1, 1): _animal("COW", fed=True, cared=False)})
        self.assertEqual(lane.apply_care(parent, obs, CONFIG, enabled=True)["farmer"], ["CARE"])
        obs, parent = _case(tiles={(1, 1): _animal("COW", fed=True, cared=True)})
        self.assertIs(lane.apply_care(parent, obs, CONFIG, enabled=True), parent)

    def test_wheat_fertilize_age_two_and_four_only_when_not_currently_covered(self):
        for day, planted in ((2, 0), (4, 0), (7, 3)):
            with self.subTest(day=day, planted=planted):
                obs, parent = _case(
                    step=day * 24,
                    inventories=[{"FERTILIZER": 1}],
                    tiles={(1, 1): _wheat(planted_day=planted, coverage=day - 1)},
                )
                out = lane.apply_wheat_fertilize(parent, obs, CONFIG, enabled=True)
                self.assertEqual(out["farmer"], ["FERTILIZE"])
        for day, planted in ((1, 0), (5, 0)):
            obs, parent = _case(
                step=day * 24,
                inventories=[{"FERTILIZER": 1}],
                tiles={(1, 1): _wheat(planted_day=planted, coverage=-1)},
            )
            self.assertIs(lane.apply_wheat_fertilize(parent, obs, CONFIG, enabled=True), parent)
        obs, parent = _case(
            step=48,
            inventories=[{"FERTILIZER": 1}],
            tiles={(1, 1): _wheat(planted_day=0, coverage=2)},
        )
        self.assertIs(lane.apply_wheat_fertilize(parent, obs, CONFIG, enabled=True), parent)

    def test_wheat_fertilize_requires_carried_fertilizer(self):
        obs, parent = _case(step=48, tiles={(1, 1): _wheat(planted_day=0, coverage=-1)})
        self.assertIs(lane.apply_wheat_fertilize(parent, obs, CONFIG, enabled=True), parent)

    def test_apply_all_does_not_double_service_one_actor(self):
        obs, parent = _case(inventories=[{"WHEAT": 1}], tiles={(1, 1): _animal("GOOSE", fed=False, cared=False)})
        out = lane.apply_all(parent, obs, CONFIG, feed_all=True, care_all=True)
        self.assertEqual(out["farmer"], ["FEED"])

    def test_idle_all_master_enables_local_layers(self):
        obs, parent = _case(
            step=48,
            inventories=[{"FERTILIZER": 1}],
            tiles={(1, 1): _wheat(planted_day=0, coverage=-1)},
        )
        self.assertEqual(lane.apply_all(parent, obs, CONFIG, idle_all=True)["farmer"], ["FERTILIZE"])

    def test_malformed_and_nonstandard_inputs_fail_closed(self):
        obs, parent = _case(inventories=[{"WHEAT": 1}], tiles={(1, 1): _animal()})
        bad = dict(CONFIG); bad["boardSize"] = True
        self.assertIs(lane.apply_feed(parent, obs, bad, enabled=True), parent)
        poison = copy.deepcopy(parent); poison["farmer"] = ["PASS", "payload"]
        self.assertIs(lane.apply_feed(poison, obs, CONFIG, enabled=True), poison)
        three = copy.deepcopy(obs); three["farms"].append(copy.deepcopy(obs["farms"][0]))
        self.assertIs(lane.apply_feed(parent, three, CONFIG, enabled=True), parent)
        third = copy.deepcopy(three); third["player"] = 2
        self.assertIs(lane.apply_feed(parent, third, CONFIG, enabled=True), parent)

    def test_actor_cardinality_and_inventory_poison_fail_closed(self):
        obs, parent = _case(
            positions=[[1, 1], [2, 2]], inventories=[{"WHEAT": 1}, {"WHEAT": 1}],
            tiles={(1, 1): _animal(), (2, 2): _animal()},
        )
        short = copy.deepcopy(parent); short["hands"] = []
        self.assertIs(lane.apply_feed(short, obs, CONFIG, enabled=True), short)
        poisoned = copy.deepcopy(obs); poisoned["private"]["inventories"][0]["WHEAT"] = True
        self.assertIs(lane.apply_feed(parent, poisoned, CONFIG, enabled=True), parent)

    def test_strict_tile_metadata_poison_fails_closed(self):
        tile = _animal(); tile["fed_today"] = 0
        obs, parent = _case(inventories=[{"WHEAT": 1}], tiles={(1, 1): tile})
        self.assertIs(lane.apply_feed(parent, obs, CONFIG, enabled=True), parent)
        plant = _wheat(planted_day=0, coverage=-1); plant["planted_day"] = "0"
        obs, parent = _case(step=48, inventories=[{"FERTILIZER": 1}], tiles={(1, 1): plant})
        self.assertIs(lane.apply_wheat_fertilize(parent, obs, CONFIG, enabled=True), parent)


if __name__ == "__main__":
    unittest.main()
