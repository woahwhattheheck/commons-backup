#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest

import frontier_replay_profile as p


PINNED = 56156662


def pack():
    return {
        "frontier_targets": [
            {"rank": 1, "rated_submission_id": PINNED},
            {"rank": 2, "rated_submission_id": 56161578},
        ]
    }


def identity(submission=PINNED, episode=108115160):
    return {
        "episode": {
            "id": episode,
            "agents": [
                {"submissionId": submission},
                {"submissionId": 56161578},
            ],
        }
    }


def row(action0=None, action1=None):
    return [
        {"action": action0},
        {"action": action1},
    ]


def raw(obj):
    return json.dumps(obj, sort_keys=True).encode()


class ReplayProfileTest(unittest.TestCase):
    def build(self, replay, *, submission=PINNED, ident=None, seat=0, frontier_pack=None):
        ident = identity() if ident is None else ident
        frontier_pack = pack() if frontier_pack is None else frontier_pack
        return p.build_profile(
            replay,
            raw(replay),
            frontier_pack,
            raw(frontier_pack),
            ident,
            raw(ident),
            submission_id=submission,
            seat=seat,
        )

    def test_row_t_plus_1_and_market_prefix_semantics(self):
        replay = {
            "id": 108115160,
            "configuration": {"turnsPerDay": 24, "maxMarketOrdersPerTurn": 2},
            "steps": [
                row({"farmer": ["DIG"]}),
                row({
                    "farmer": ["PLANT", "WHEAT"],
                    "hands": [["WATER"], ["CARE"]],
                    "market": [["SELL", "WHEAT", "2"], ["HIRE"], ["SELL", "MILK", 3]],
                }),
                row({
                    "farmer": ["HARVEST"],
                    "market": [["BUY_LAND"], ["BUY_ANIMAL", "COW", 1]],
                }),
            ],
        }
        out = self.build(replay)
        totals = out["totals"]
        self.assertEqual(totals["decision_steps"], 2)
        self.assertEqual(totals["unit_ops"]["PLANT"], 1)
        self.assertEqual(totals["unit_ops"]["PLANT:WHEAT"], 1)
        self.assertNotIn("DIG", totals["unit_ops"])
        self.assertEqual(totals["market_quantities"]["SELL:WHEAT"], 2)
        self.assertEqual(totals["market_orders"]["HIRE"], 1)
        self.assertEqual(totals["market_orders"]["BUY_LAND"], 1)
        self.assertEqual(totals["market_quantities"]["BUY_ANIMAL:COW"], 1)
        self.assertEqual(totals["truncated_market_rows"], 1)
        self.assertNotIn("SELL:MILK", totals["market_orders"])

    def test_engine_quantity_coercion_and_trailing_fields(self):
        replay = {
            "id": 108115160,
            "configuration": {"maxMarketOrdersPerTurn": 10},
            "steps": [row(), row({"market": [
                ["SELL", "WHEAT", 2.9, "meta"],
                ["SELL", "MILK", True],
                ["SELL", "WOOL", "x"],
                ["BUY_SEED", "CARROT", "3", {"ignored": True}],
            ]})],
        }
        out = self.build(replay)["totals"]
        self.assertEqual(out["market_quantities"]["SELL:WHEAT"], 2)
        self.assertEqual(out["market_quantities"]["SELL:MILK"], 1)
        self.assertEqual(out["market_quantities"]["BUY_SEED:CARROT"], 3)
        self.assertEqual(out["malformed_market_rows"], 1)

    def test_unpinned_submission_fails_closed(self):
        replay = {"id": 108115160, "steps": [row(), row()]}
        with self.assertRaisesRegex(p.ReplayProfileError, "not a pinned rated frontier target"):
            self.build(replay, submission=999)

    def test_frontier_pack_submission_ids_are_type_exact(self):
        replay = {"id": 108115160, "steps": [row(), row()]}
        malformed = {"frontier_targets": [{"rank": 1, "rated_submission_id": True}]}
        with self.assertRaisesRegex(p.ReplayProfileError, "rated_submission_id must be a plain integer"):
            self.build(
                replay,
                submission=1,
                ident=identity(submission=1),
                frontier_pack=malformed,
            )

    def test_frontier_pack_rejects_duplicate_and_malformed_targets(self):
        replay = {"id": 108115160, "steps": [row(), row()]}
        duplicate = {
            "frontier_targets": [
                {"rank": 1, "rated_submission_id": PINNED},
                {"rank": 2, "rated_submission_id": PINNED},
            ]
        }
        with self.assertRaisesRegex(p.ReplayProfileError, "duplicate rated_submission_id"):
            self.build(replay, frontier_pack=duplicate)

        non_object = {
            "frontier_targets": [
                {"rank": 1, "rated_submission_id": PINNED},
                PINNED,
            ]
        }
        with self.assertRaisesRegex(p.ReplayProfileError, r"frontier_targets\[1\] must be an object"):
            self.build(replay, frontier_pack=non_object)

    def test_identity_manifest_mismatch_fails_closed(self):
        replay = {"id": 108115160, "steps": [row(), row()]}
        with self.assertRaisesRegex(p.ReplayProfileError, "identity mismatch"):
            self.build(replay, ident=identity(submission=56145462))

    def test_replay_episode_mismatch_fails_closed(self):
        replay = {"id": 999, "steps": [row(), row()]}
        with self.assertRaisesRegex(p.ReplayProfileError, "episode mismatch"):
            self.build(replay)

    def test_phase_boundaries_are_day_based(self):
        steps = [row()]
        for decision_step in range(21):
            action = {"market": [["SELL", "WHEAT", 1]]} if decision_step in (9, 10, 20) else {}
            steps.append(row(action))
        replay = {
            "id": 108115160,
            "configuration": {"turnsPerDay": 1},
            "steps": steps,
        }
        out = self.build(replay)
        self.assertEqual(out["phases"]["early"]["active_step_counts"]["sale"], 1)
        self.assertEqual(out["phases"]["mid"]["active_step_counts"]["sale"], 1)
        self.assertEqual(out["phases"]["late"]["active_step_counts"]["sale"], 1)

    def test_malformed_units_are_counted_not_crashed(self):
        replay = {
            "id": 108115160,
            "steps": [row(), row({"farmer": "NORTH", "hands": [None, [], ["FEED"]]})],
        }
        out = self.build(replay)["totals"]
        self.assertEqual(out["malformed_unit_actions"], 3)
        self.assertEqual(out["unit_ops"]["FEED"], 1)

    def test_canonical_json_is_deterministic(self):
        replay = {"id": 108115160, "steps": [row(), row({"market": [["HIRE"]]})]}
        profile = self.build(replay)
        a = p.canonical_json(profile)
        b = p.canonical_json(profile)
        self.assertEqual(a, b)
        self.assertTrue(a.endswith("\n"))
        self.assertEqual(json.loads(a)["identity"]["submission_id"], PINNED)


if __name__ == "__main__":
    unittest.main()
