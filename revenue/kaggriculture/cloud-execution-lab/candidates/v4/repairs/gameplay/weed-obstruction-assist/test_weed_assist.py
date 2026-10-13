from __future__ import annotations

import copy
import unittest

from weed_assist import assist_same_turn_weed_obstructions


def obs(*, farmer=(0, 0), hands=(), weeds=(), seeds=None, player=0):
    tiles = [[None for _ in range(5)] for _ in range(5)]
    for x, y in weeds:
        tiles[y][x] = {"kind": "WEED"}
    farm = {"farmer": list(farmer), "hands": [list(p) for p in hands], "tiles": tiles}
    other = {"farmer": [4, 4], "hands": [], "tiles": [[None for _ in range(5)] for _ in range(5)]}
    farms = [farm, other] if player == 0 else [other, farm]
    seed_map = {c: 0 for c in ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON")}
    if seeds:
        seed_map.update(seeds)
    return {"player": player, "farms": farms, "private": {"seeds": seed_map}}


def action(farmer, hands, market=None):
    return {"farmer": farmer, "hands": hands, "market": [] if market is None else market}


class WeedAssistTests(unittest.TestCase):
    def test_disabled_exact_identity(self):
        parent = action(["PASS"], [["PLANT", "CARROT"]])
        out, report = assist_same_turn_weed_obstructions(
            obs(hands=[(0, 0)], weeds=[(0, 0)], seeds={"CARROT": 1}),
            parent,
            enabled=False,
        )
        self.assertIs(out, parent)
        self.assertEqual(report["reason"], "disabled")

    def test_farmer_digs_for_later_hand_plant(self):
        parent = action(["PASS"], [["PLANT", "CARROT"]], [["SELL", "WHEAT", 3]])
        saved = copy.deepcopy(parent)
        out, report = assist_same_turn_weed_obstructions(
            obs(hands=[(0, 0)], weeds=[(0, 0)], seeds={"CARROT": 1}),
            parent,
            enabled=True,
        )
        self.assertIsNot(out, parent)
        self.assertEqual(parent, saved)
        self.assertEqual(out["farmer"], ["DIG"])
        self.assertEqual(out["hands"], [["PLANT", "CARROT"]])
        self.assertEqual(out["market"], parent["market"])
        self.assertTrue(report["changed"])
        self.assertEqual(report["rewrites"][0]["helper_actor_index"], 0)
        self.assertEqual(report["rewrites"][0]["target_actor_index"], 1)

    def test_hand_digs_for_later_hand_build(self):
        parent = action(["NORTH"], [["PASS"], ["BUILD_COOP"]])
        out, _ = assist_same_turn_weed_obstructions(
            obs(farmer=(2, 2), hands=[(1, 1), (1, 1)], weeds=[(1, 1)]),
            parent,
            enabled=True,
        )
        self.assertEqual(out["hands"], [["DIG"], ["BUILD_COOP"]])

    def test_later_pass_cannot_help_earlier_target(self):
        parent = action(["PLANT", "CARROT"], [["PASS"]])
        out, report = assist_same_turn_weed_obstructions(
            obs(hands=[(0, 0)], weeds=[(0, 0)], seeds={"CARROT": 1}),
            parent,
            enabled=True,
        )
        self.assertIs(out, parent)
        self.assertFalse(report["changed"])

    def test_non_colocated_pass_is_identity(self):
        parent = action(["PASS"], [["BUILD_PASTURE"]])
        out, _ = assist_same_turn_weed_obstructions(
            obs(farmer=(0, 0), hands=[(1, 1)], weeds=[(1, 1)]),
            parent,
            enabled=True,
        )
        self.assertIs(out, parent)

    def test_no_weed_is_identity(self):
        parent = action(["PASS"], [["BUILD_PASTURE"]])
        out, _ = assist_same_turn_weed_obstructions(
            obs(hands=[(0, 0)]),
            parent,
            enabled=True,
        )
        self.assertIs(out, parent)

    def test_atomic_plant_oversubscription_blocks_assist(self):
        parent = action(["PASS"], [["PLANT", "CARROT"], ["PLANT", "CARROT"]])
        # Second hand row is engine-visible raw suffix: one live hand only.
        out, report = assist_same_turn_weed_obstructions(
            obs(hands=[(0, 0)], weeds=[(0, 0)], seeds={"CARROT": 1}),
            parent,
            enabled=True,
        )
        self.assertIs(out, parent)
        self.assertFalse(report["changed"])

    def test_suffix_pass_cannot_be_helper(self):
        parent = action(["PLANT", "MELON"], [["PASS"]])
        out, _ = assist_same_turn_weed_obstructions(
            obs(hands=[], weeds=[(0, 0)], seeds={"MELON": 1}),
            parent,
            enabled=True,
        )
        self.assertIs(out, parent)

    def test_unsafe_intervening_colocated_build_blocks(self):
        parent = action(["PASS"], [["BUILD_COOP", "extra"], ["PLANT", "CARROT"]])
        out, _ = assist_same_turn_weed_obstructions(
            obs(
                hands=[(0, 0), (0, 0)],
                weeds=[(0, 0)],
                seeds={"CARROT": 1},
            ),
            parent,
            enabled=True,
        )
        self.assertIs(out, parent)

    def test_latest_preceding_pass_is_used(self):
        parent = action(["PASS"], [["PASS"], ["BUILD_PASTURE"]])
        out, report = assist_same_turn_weed_obstructions(
            obs(hands=[(0, 0), (0, 0)], weeds=[(0, 0)]),
            parent,
            enabled=True,
        )
        self.assertEqual(out["farmer"], ["PASS"])
        self.assertEqual(out["hands"], [["DIG"], ["BUILD_PASTURE"]])
        self.assertEqual(report["rewrites"][0]["helper_actor_index"], 1)

    def test_intervening_move_is_safe(self):
        parent = action(["PASS"], [["EAST"], ["BUILD_PASTURE"]])
        out, _ = assist_same_turn_weed_obstructions(
            obs(hands=[(0, 0), (0, 0)], weeds=[(0, 0)]),
            parent,
            enabled=True,
        )
        self.assertEqual(out["farmer"], ["DIG"])

    def test_two_disjoint_assists(self):
        parent = action(
            ["PASS"],
            [["BUILD_COOP"], ["PASS"], ["PLANT", "WHEAT"]],
            [["SELL", "WOOL", 1]],
        )
        out, report = assist_same_turn_weed_obstructions(
            obs(
                farmer=(0, 0),
                hands=[(0, 0), (2, 2), (2, 2)],
                weeds=[(0, 0), (2, 2)],
                seeds={"WHEAT": 1},
            ),
            parent,
            enabled=True,
        )
        self.assertEqual(out["farmer"], ["DIG"])
        self.assertEqual(out["hands"], [["BUILD_COOP"], ["DIG"], ["PLANT", "WHEAT"]])
        self.assertEqual(len(report["rewrites"]), 2)

    def test_malformed_target_is_identity(self):
        for bad in (["PLANT"], ["PLANT", "POTATO"], ["BUILD_COOP", "extra"], "PLANT", []):
            with self.subTest(bad=bad):
                parent = action(["PASS"], [bad])
                out, _ = assist_same_turn_weed_obstructions(
                    obs(hands=[(0, 0)], weeds=[(0, 0)], seeds={"CARROT": 1}),
                    parent,
                    enabled=True,
                )
                self.assertIs(out, parent)

    def test_malformed_observation_or_action_fails_closed(self):
        parent = action(["PASS"], [["BUILD_COOP"]])
        for bad_obs in ({}, {"player": True}, {"player": 0, "farms": []}):
            with self.subTest(bad_obs=bad_obs):
                out, _ = assist_same_turn_weed_obstructions(bad_obs, parent, enabled=True)
                self.assertIs(out, parent)
        for bad_action in (None, [], {"farmer": ["PASS"]}, {"hands": []}):
            with self.subTest(bad_action=bad_action):
                out, _ = assist_same_turn_weed_obstructions(
                    obs(hands=[(0, 0)], weeds=[(0, 0)]),
                    bad_action,
                    enabled=True,
                )
                self.assertIs(out, bad_action)

    def test_player_one_uses_own_farm(self):
        parent = action(["PASS"], [["BUILD_COOP"]])
        out, _ = assist_same_turn_weed_obstructions(
            obs(player=1, hands=[(1, 1)], farmer=(1, 1), weeds=[(1, 1)]),
            parent,
            enabled=True,
        )
        self.assertEqual(out["farmer"], ["DIG"])

    def test_raw_suffix_is_preserved_when_other_crop(self):
        parent = action(["PASS"], [["PLANT", "CARROT"], ["PLANT", "WHEAT"], ["SOUTH"]])
        out, _ = assist_same_turn_weed_obstructions(
            obs(hands=[(0, 0)], weeds=[(0, 0)], seeds={"CARROT": 1, "WHEAT": 0}),
            parent,
            enabled=True,
        )
        self.assertEqual(out["hands"][1:], parent["hands"][1:])

    def test_build_does_not_require_seed_state(self):
        o = obs(hands=[(0, 0)], weeds=[(0, 0)])
        o["private"] = {}
        parent = action(["PASS"], [["BUILD_COOP"]])
        out, _ = assist_same_turn_weed_obstructions(o, parent, enabled=True)
        self.assertEqual(out["farmer"], ["DIG"])

    def test_minimal_engine_witness_plant_executes_after_assist(self):
        o = obs(hands=[(0, 0)], weeds=[(0, 0)], seeds={"CARROT": 1})
        parent = action(["PASS"], [["PLANT", "CARROT"]])
        repaired, _ = assist_same_turn_weed_obstructions(o, parent, enabled=True)

        def run(rows):
            tile = {"kind": "WEED"}
            seeds = 1
            demand = sum(1 for row in rows if isinstance(row, list) and len(row) >= 2
                         and row[0] == "PLANT" and row[1] == "CARROT")
            blocked = demand > seeds
            for row in rows:
                op = row[0]
                if op == "DIG" and tile is not None:
                    tile = None
                elif op == "PLANT" and not blocked and tile is None and seeds > 0:
                    seeds -= 1
                    tile = {"kind": "PLANT", "crop": "CARROT"}
            return tile, seeds

        baseline_tile, baseline_seeds = run([parent["farmer"], *parent["hands"]])
        fixed_tile, fixed_seeds = run([repaired["farmer"], *repaired["hands"]])
        self.assertEqual(baseline_tile, {"kind": "WEED"})
        self.assertEqual(baseline_seeds, 1)
        self.assertEqual(fixed_tile, {"kind": "PLANT", "crop": "CARROT"})
        self.assertEqual(fixed_seeds, 0)

    def test_minimal_engine_witness_build_executes_after_assist(self):
        o = obs(hands=[(0, 0)], weeds=[(0, 0)])
        parent = action(["PASS"], [["BUILD_COOP"]])
        repaired, _ = assist_same_turn_weed_obstructions(o, parent, enabled=True)

        def run(rows):
            tile = {"kind": "WEED"}
            for row in rows:
                if row[0] == "DIG" and tile is not None:
                    tile = None
                elif row[0] == "BUILD_COOP" and tile is None:
                    tile = {"kind": "COOP"}
            return tile

        self.assertEqual(run([parent["farmer"], *parent["hands"]]), {"kind": "WEED"})
        self.assertEqual(run([repaired["farmer"], *repaired["hands"]]), {"kind": "COOP"})


if __name__ == "__main__":
    unittest.main()
