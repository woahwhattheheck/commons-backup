# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import copy
import unittest
from ghost_plant_admission import repair_ghost_plant_poisoning


def observation(seeds, *, live_hands=1, seat=0):
    farms = [{"hands": []}, {"hands": []}]
    farms[seat]["hands"] = [[1 + i, 0] for i in range(live_hands)]
    return {"player": seat, "farms": farms, "private": {"seeds": dict(seeds)}}


def action(farmer=None, hands=None, market=None):
    return {"farmer": ["PASS"] if farmer is None else farmer,
            "hands": [] if hands is None else hands,
            "market": [] if market is None else market}


class GhostPlantAdmissionUnitTests(unittest.TestCase):
    def test_simple_poisoning_changes_only_latest_ghost(self):
        parent = action(["PLANT", "CARROT"],
                        [["PLANT", "CARROT"], ["PLANT", "CARROT"]],
                        [["SELL", "WHEAT", 1]])
        saved = copy.deepcopy(parent)
        out, report = repair_ghost_plant_poisoning(
            observation({"CARROT": 2}), parent, enabled=True)
        self.assertEqual(out["hands"], [["PLANT", "CARROT"], ["PASS"]])
        self.assertEqual(out["farmer"], parent["farmer"])
        self.assertEqual(out["market"], parent["market"])
        self.assertEqual(parent, saved)
        self.assertEqual(report["replaced_hand_indexes"], [1])
        self.assertEqual(report["repaired_crops"], ["CARROT"])

    def test_minimum_edit_prefers_latest_suffix_row(self):
        parent = action(["PLANT", "CARROT"], [
            ["PLANT", "CARROT"], ["PLANT", "CARROT"], ["PLANT", "CARROT"]])
        out, report = repair_ghost_plant_poisoning(
            observation({"CARROT": 3}), parent, enabled=True)
        self.assertEqual(out["hands"], [
            ["PLANT", "CARROT"], ["PLANT", "CARROT"], ["PASS"]])
        self.assertEqual(report["replaced_hand_indexes"], [2])

    def test_hand_only_live_request_is_not_misclassified_ghost(self):
        parent = action(["PASS"], [["PLANT", "WHEAT"], ["PLANT", "WHEAT"]])
        out, report = repair_ghost_plant_poisoning(
            observation({"WHEAT": 1}), parent, enabled=True)
        self.assertEqual(out["hands"], [["PLANT", "WHEAT"], ["PASS"]])
        self.assertEqual(report["replaced_hand_indexes"], [1])

    def test_genuine_live_oversubscription_is_untouched(self):
        parent = action(["PLANT", "CARROT"], [
            ["PLANT", "CARROT"], ["PLANT", "CARROT"], ["PLANT", "CARROT"]])
        out, report = repair_ghost_plant_poisoning(
            observation({"CARROT": 2}, live_hands=2), parent, enabled=True)
        self.assertIs(out, parent)
        self.assertFalse(report["changed"])
        self.assertEqual(report["reason"], "no_certified_poisoning")

    def test_enough_seed_for_raw_vector_is_exact_identity(self):
        parent = action(["PLANT", "CARROT"],
                        [["PLANT", "CARROT"], ["PLANT", "CARROT"]])
        out, report = repair_ghost_plant_poisoning(
            observation({"CARROT": 3}), parent, enabled=True)
        self.assertIs(out, parent)
        self.assertFalse(report["changed"])

    def test_disabled_is_exact_identity(self):
        parent = action(["PLANT", "CARROT"],
                        [["PLANT", "CARROT"], ["PLANT", "CARROT"]])
        out, report = repair_ghost_plant_poisoning(
            observation({"CARROT": 2}), parent, enabled=False)
        self.assertIs(out, parent)
        self.assertEqual(report["reason"], "disabled")

    def test_malformed_plant_crop_fails_closed(self):
        parent = action(["PLANT", "CARROT"], [["PLANT", []], ["PLANT", "CARROT"]])
        out, report = repair_ghost_plant_poisoning(
            observation({"CARROT": 1}), parent, enabled=True)
        self.assertIs(out, parent)
        self.assertFalse(report["certified"])
        self.assertEqual(report["reason"], "malformed_plant_crop")

    def test_multicrop_repairs_are_independent(self):
        parent = action(["PLANT", "CARROT"], [
            ["PLANT", "TOMATO"], ["PLANT", "CARROT"], ["PLANT", "TOMATO"]])
        out, report = repair_ghost_plant_poisoning(
            observation({"CARROT": 1, "TOMATO": 1}), parent, enabled=True)
        self.assertEqual(out["hands"], [["PLANT", "TOMATO"], ["PASS"], ["PASS"]])
        self.assertEqual(report["repaired_crops"], ["CARROT", "TOMATO"])

    def test_seat_one_uses_its_own_live_hand_count(self):
        parent = action(["PLANT", "WHEAT"], [["PLANT", "WHEAT"], ["PLANT", "WHEAT"]])
        out, report = repair_ghost_plant_poisoning(
            observation({"WHEAT": 2}, seat=1), parent, enabled=True)
        self.assertTrue(report["changed"])
        self.assertEqual(out["hands"][-1], ["PASS"])


if __name__ == "__main__":
    unittest.main()
