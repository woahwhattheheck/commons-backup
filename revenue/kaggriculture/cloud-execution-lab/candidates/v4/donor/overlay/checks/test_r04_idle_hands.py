# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import unittest

import r04_idle_hands as ih


def tile_grid():
    return [[None for _ in range(10)] for _ in range(10)]


def observation(*, step=72, player=0, hands=None, inventories=None):
    hands = [[2, 2]] if hands is None else hands
    inventories = [{}, {}] if inventories is None else inventories
    tiles = tile_grid()
    return {
        "step": step,
        "player": player,
        "farms": [
            {"farmer": [1, 1], "hands": hands, "tiles": tiles},
            {"farmer": [8, 8], "hands": [], "tiles": tile_grid()},
        ],
        "private": {"inventories": inventories, "shed": {}},
    }


def action(*, farmer=None, hands=None):
    return {
        "farmer": ["PASS"] if farmer is None else farmer,
        "hands": [["PASS"]] if hands is None else hands,
        "market": [],
    }


def animal(kind="SHEEP", *, fed=False, cared=False):
    return {
        "kind": "PEN" if kind != "GOOSE" else "COOP",
        "animal": kind,
        "fed_today": fed,
        "cared_today": cared,
        "yield_units": 0,
    }


def wheat(*, planted_day=1, coverage=1, yield_units=0):
    return {
        "kind": "PLANT",
        "crop": "WHEAT",
        "planted_day": planted_day,
        "fertilized_until_day": coverage,
        "yield_units": yield_units,
        "watered_today": False,
    }


class IdleHandsTests(unittest.TestCase):
    def assert_identity_nonmutation(self, fn, obs, parent):
        before_obs = copy.deepcopy(obs)
        before_parent = copy.deepcopy(parent)
        out = fn(parent, obs)
        self.assertIs(out, parent)
        self.assertEqual(obs, before_obs)
        self.assertEqual(parent, before_parent)

    def test_feed_disabled_exact_identity(self):
        obs = observation(inventories=[{"WHEAT": 1}, {}])
        obs["farms"][0]["tiles"][1][1] = animal(fed=False)
        self.assert_identity_nonmutation(lambda a, o: ih.apply_feed(a, o), obs, action())

    def test_feed_farmer_literal_pass(self):
        obs = observation(inventories=[{"WHEAT": 1}, {}])
        obs["farms"][0]["tiles"][1][1] = animal(fed=False)
        parent = action()
        out = ih.apply_feed(parent, obs, enabled=True)
        self.assertIsNot(out, parent)
        self.assertEqual(out["farmer"], ["FEED"])
        self.assertEqual(out["hands"], [["PASS"]])
        self.assertEqual(parent["farmer"], ["PASS"])

    def test_feed_hand_literal_pass(self):
        obs = observation(inventories=[{}, {"WHEAT": 2}])
        obs["farms"][0]["tiles"][2][2] = animal("GOOSE", fed=False)
        out = ih.apply_feed(action(), obs, enabled=True)
        self.assertEqual(out["hands"], [["FEED"]])

    def test_feed_requires_positive_strict_wheat(self):
        for value in (0, -1, True, 1.0, "1", None):
            obs = observation(inventories=[{"WHEAT": value}, {}])
            obs["farms"][0]["tiles"][1][1] = animal(fed=False)
            parent = action()
            with self.subTest(value=value):
                self.assertIs(ih.apply_feed(parent, obs, enabled=True), parent)

    def test_feed_rejects_already_fed_or_nonanimal(self):
        for tile in (animal(fed=True), wheat(planted_day=1, coverage=1)):
            obs = observation(inventories=[{"WHEAT": 1}, {}])
            obs["farms"][0]["tiles"][1][1] = tile
            parent = action()
            self.assertIs(ih.apply_feed(parent, obs, enabled=True), parent)

    def test_feed_nonpass_is_hard_noop_for_that_actor(self):
        obs = observation(inventories=[{"WHEAT": 1}, {}])
        obs["farms"][0]["tiles"][1][1] = animal(fed=False)
        parent = action(farmer=["CARE"])
        self.assertIs(ih.apply_feed(parent, obs, enabled=True), parent)

    def test_duplicate_eligible_workers_on_one_tile_are_ambiguous(self):
        obs = observation(hands=[[1, 1]], inventories=[{"WHEAT": 1}, {"WHEAT": 1}])
        obs["farms"][0]["tiles"][1][1] = animal(fed=False)
        parent = action()
        self.assertIs(ih.apply_feed(parent, obs, enabled=True), parent)

    def test_care_all_handles_fed_uncared_sheep(self):
        obs = observation()
        obs["farms"][0]["tiles"][1][1] = animal("SHEEP", fed=True, cared=False)
        out = ih.apply_care(action(), obs, care_all=True)
        self.assertEqual(out["farmer"], ["CARE"])

    def test_care_goose_only_handles_goose(self):
        obs = observation()
        obs["farms"][0]["tiles"][1][1] = animal("GOOSE", fed=True, cared=False)
        out = ih.apply_care(action(), obs, care_goose=True)
        self.assertEqual(out["farmer"], ["CARE"])

    def test_care_goose_only_ignores_sheep(self):
        obs = observation()
        obs["farms"][0]["tiles"][1][1] = animal("SHEEP", fed=True, cared=False)
        parent = action()
        self.assertIs(ih.apply_care(parent, obs, care_goose=True), parent)

    def test_care_requires_fed_and_uncared(self):
        for fed, cared in ((False, False), (False, True), (True, True)):
            obs = observation()
            obs["farms"][0]["tiles"][1][1] = animal("GOOSE", fed=fed, cared=cared)
            parent = action()
            with self.subTest(fed=fed, cared=cared):
                self.assertIs(ih.apply_care(parent, obs, care_all=True), parent)

    def test_care_flags_off_identity(self):
        obs = observation()
        obs["farms"][0]["tiles"][1][1] = animal("GOOSE", fed=True, cared=False)
        parent = action()
        self.assertIs(ih.apply_care(parent, obs), parent)

    def test_wheat_fertilize_ages_two_three_four(self):
        # step 120 => day 5, so planted days 3/2/1 are ages 2/3/4.
        for planted in (3, 2, 1):
            obs = observation(step=120, inventories=[{"FERTILIZER": 1}, {}])
            obs["farms"][0]["tiles"][1][1] = wheat(planted_day=planted, coverage=4, yield_units=2)
            out = ih.apply_wheat_fertilize(action(), obs, enabled=True)
            with self.subTest(planted=planted):
                self.assertEqual(out["farmer"], ["FERTILIZE"])

    def test_wheat_fertilize_rejects_age_outside_window(self):
        for planted in (4, 0):  # ages 1 and 5 at day 5
            obs = observation(step=120, inventories=[{"FERTILIZER": 1}, {}])
            obs["farms"][0]["tiles"][1][1] = wheat(planted_day=planted, coverage=4, yield_units=2)
            parent = action()
            with self.subTest(planted=planted):
                self.assertIs(ih.apply_wheat_fertilize(parent, obs, enabled=True), parent)

    def test_wheat_fertilize_requires_uncovered_tile(self):
        for coverage in (5, 6):
            obs = observation(step=120, inventories=[{"FERTILIZER": 1}, {}])
            obs["farms"][0]["tiles"][1][1] = wheat(planted_day=2, coverage=coverage, yield_units=2)
            parent = action()
            self.assertIs(ih.apply_wheat_fertilize(parent, obs, enabled=True), parent)

    def test_wheat_fertilize_requires_strict_positive_fertilizer(self):
        for value in (0, -1, True, 1.0, "1", None):
            obs = observation(step=120, inventories=[{"FERTILIZER": value}, {}])
            obs["farms"][0]["tiles"][1][1] = wheat(planted_day=2, coverage=4, yield_units=2)
            parent = action()
            with self.subTest(value=value):
                self.assertIs(ih.apply_wheat_fertilize(parent, obs, enabled=True), parent)

    def test_wheat_fertilize_rejects_no_marginal_yield_headroom(self):
        for units in (5, 6):
            obs = observation(step=120, inventories=[{"FERTILIZER": 1}, {}])
            obs["farms"][0]["tiles"][1][1] = wheat(planted_day=2, coverage=4, yield_units=units)
            parent = action()
            self.assertIs(ih.apply_wheat_fertilize(parent, obs, enabled=True), parent)

    def test_wheat_fertilize_rejects_other_crop(self):
        obs = observation(step=120, inventories=[{"FERTILIZER": 1}, {}])
        tile = wheat(planted_day=2, coverage=4, yield_units=2)
        tile["crop"] = "CARROT"
        obs["farms"][0]["tiles"][1][1] = tile
        parent = action()
        self.assertIs(ih.apply_wheat_fertilize(parent, obs, enabled=True), parent)

    def test_atomic_malformed_actor_surface_fails_closed(self):
        variants = []
        obs = observation(inventories=[{"WHEAT": 1}, {}])
        obs["farms"][0]["tiles"][1][1] = animal(fed=False)
        variants.append((obs, {"farmer": ["PASS"], "hands": "bad", "market": []}))
        bad_pos = copy.deepcopy(obs); bad_pos["farms"][0]["hands"] = [[True, 2]]
        variants.append((bad_pos, action()))
        bad_inv = copy.deepcopy(obs); bad_inv["private"]["inventories"][1] = {"WHEAT": True}
        variants.append((bad_inv, action()))
        bad_pass = copy.deepcopy(action()); bad_pass["hands"] = [["PASS", 1]]
        variants.append((obs, bad_pass))
        for variant_obs, parent in variants:
            with self.subTest(parent=parent):
                self.assertIs(ih.apply_feed(parent, variant_obs, enabled=True), parent)

    def test_invalid_player_and_step_fail_closed(self):
        for key, value in (("player", True), ("player", 2), ("step", True), ("step", -1)):
            obs = observation(inventories=[{"WHEAT": 1}, {}])
            obs["farms"][0]["tiles"][1][1] = animal(fed=False)
            obs[key] = value
            parent = action()
            self.assertIs(ih.apply_feed(parent, obs, enabled=True), parent)

    def test_apply_all_global_gate_off_is_exact_identity(self):
        obs = observation(inventories=[{"WHEAT": 1}, {}])
        obs["farms"][0]["tiles"][1][1] = animal(fed=False)
        parent = action()
        self.assertIs(ih.apply_all(parent, obs, feed_all=True), parent)

    def test_apply_all_transforms_independent_actors_once(self):
        obs = observation(step=120, inventories=[{"WHEAT": 1}, {"FERTILIZER": 1}])
        obs["farms"][0]["tiles"][1][1] = animal("GOOSE", fed=False, cared=False)
        obs["farms"][0]["tiles"][2][2] = wheat(planted_day=2, coverage=4, yield_units=2)
        parent = action()
        out = ih.apply_all(parent, obs, idle_all=True, feed_all=True, wheat_fert=True)
        self.assertEqual(out["farmer"], ["FEED"])
        self.assertEqual(out["hands"], [["FERTILIZE"]])

    def test_apply_all_care_does_not_reuse_actor_changed_by_feed(self):
        obs = observation(inventories=[{"WHEAT": 1}, {}])
        obs["farms"][0]["tiles"][1][1] = animal("GOOSE", fed=False, cared=False)
        out = ih.apply_all(action(), obs, idle_all=True, feed_all=True, care_all=True)
        self.assertEqual(out["farmer"], ["FEED"])

    def test_nonmutation_on_activation(self):
        obs = observation(inventories=[{"WHEAT": 1}, {}])
        obs["farms"][0]["tiles"][1][1] = animal(fed=False)
        parent = action()
        before_obs = copy.deepcopy(obs)
        before_parent = copy.deepcopy(parent)
        out = ih.apply_feed(parent, obs, enabled=True)
        self.assertIsNot(out, parent)
        self.assertEqual(obs, before_obs)
        self.assertEqual(parent, before_parent)

    def test_install_default_off_identity(self):
        obs = observation(inventories=[{"WHEAT": 1}, {}])
        obs["farms"][0]["tiles"][1][1] = animal(fed=False)
        parent_action = action()
        wrapped = ih.install(lambda _o, _c=None: parent_action)
        self.assertIs(wrapped(obs, None), parent_action)

    def test_install_enabled_feed(self):
        obs = observation(inventories=[{"WHEAT": 1}, {}])
        obs["farms"][0]["tiles"][1][1] = animal(fed=False)
        parent_action = action()
        wrapped = ih.install(lambda _o, _c=None: parent_action, idle_all=True, feed_all=True)
        out = wrapped(obs, None)
        self.assertEqual(out["farmer"], ["FEED"])


if __name__ == "__main__":
    unittest.main()
