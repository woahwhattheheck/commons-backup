#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import route_matrix_row_receipt as rr
from p04_route_ranker import normalize_row


def farm(money, *, hands=0, crop=None, animal=None):
    cell0 = {"kind": "PLANT", "crop": crop} if crop else None
    cell1 = {"kind": "PASTURE", "animal": animal} if animal else None
    return {
        "money": money,
        "farmer": [4, 4],
        "hands": [[3, 3] for _ in range(hands)],
        "tiles": [[cell0, cell1], [None, "LOCKED"]],
    }


def observation(step=144, player=0):
    return {
        "step": step,
        "player": player,
        "farms": [
            farm(1234.0, hands=1, crop="WHEAT", animal="SHEEP"),
            farm(999.0, crop="CARROT", animal="GOOSE"),
        ],
        "market": {
            "prices": {"WOOL": 210, "MILK": 150, "WHEAT": 25, "CARROT": 35},
            "inventory": {"WOOL": 9990, "MILK": 10010, "WHEAT": 10000, "CARROT": 10000},
            "params": {"not": "persisted"},
        },
        "town": {
            "unlocked_shops": ["PIZZA_SHOP", "YARN_STORE", "BAKERY"],
            "future_unlock": "not persisted",
        },
        "private": {
            "shed": {"WOOL": 99},
            "inventories": [{"WHEAT": 4}],
        },
        "future_rng": "not persisted",
    }


def manifest(plan=7):
    return {
        "schema": rr.ROUTE_MANIFEST_SCHEMA,
        "baseline_candidate_archive_sha256": rr.PRODUCTION_ARCHIVE_SHA256,
        "v31_archive_sha256": "1" * 64,
        "delivery_archive_sha256": "2" * 64,
        "plan_index": plan,
        "selection_step": rr.ROUTE_STEP,
        "selection_kind": "shop_pair",
        "route_step": rr.ROUTE_STEP,
        "final_plan_step": rr.FINAL_PLAN_STEP,
        "terminal_plan": rr.TERMINAL_PLAN,
        "changed_members": [rr.ROUTER],
        "router_before_sha256": rr.ROUTER_SHA256,
        "router_after_sha256": "3" * 64,
        "candidate_archive_sha256": "4" * 64,
        "files": {rr.ROUTER: "3" * 64},
        "kaggle_submission_hold": True,
    }


class SnapshotTests(unittest.TestCase):
    def test_public_snapshot_is_p04_compatible_and_private_free(self):
        snapshot = rr.public_step144_snapshot(observation())
        self.assertEqual(snapshot["first_two_shops"], ["PIZZA_SHOP", "YARN_STORE"])
        self.assertEqual(snapshot["incumbent_plan"], 7)
        self.assertEqual(snapshot["own"]["worker_count"], 2)
        self.assertEqual(snapshot["own"]["animal_counts"], {"SHEEP": 1})
        self.assertEqual(snapshot["own"]["crop_counts"], {"WHEAT": 1})
        self.assertEqual(snapshot["rival"]["animal_counts"], {"GOOSE": 1})
        self.assertEqual(snapshot["rival"]["crop_counts"], {"CARROT": 1})
        payload = json.dumps(snapshot, sort_keys=True)
        self.assertNotIn("private", payload)
        self.assertNotIn("future_rng", payload)
        self.assertNotIn("params", payload)

    def test_snapshot_requires_exact_step144(self):
        with self.assertRaisesRegex(ValueError, "exactly step 144"):
            rr.public_step144_snapshot(observation(step=143))

    def test_unknown_visible_tile_fails_closed(self):
        value = observation()
        value["farms"][0]["tiles"][0][0] = "MYSTERY"
        with self.assertRaisesRegex(ValueError, "unknown visible cell"):
            rr.public_step144_snapshot(value)


class ManifestTests(unittest.TestCase):
    def test_step144_manifest_contract(self):
        self.assertEqual(rr.validate_route_manifest(manifest(7), 7)["plan_index"], 7)

    def test_terminal_manifest_is_not_a_p04_row(self):
        value = manifest(7)
        value["selection_step"] = rr.FINAL_PLAN_STEP
        value["selection_kind"] = "terminal"
        with self.assertRaisesRegex(ValueError, "step-144 matrix"):
            rr.validate_route_manifest(value, 7)


class FakeActor:
    calls = 0

    def act(self, observation, configuration, timeout):
        type(self).calls += 1
        return {"kind": "action", "action": {"type": "PASS"}}


class FakeEvaluator:
    Actor = FakeActor

    @staticmethod
    def play(
        engine,
        specs,
        cache,
        loader,
        seed,
        candidate_seat,
        rng_seed,
        action_timeout,
        startup_timeout,
        game_timeout,
    ):
        actors = [FakeActor(), FakeActor()]
        for step in (143, 144, 145):
            for seat, actor in enumerate(actors):
                value = observation(step=step, player=seat)
                actor.act(value, {}, action_timeout)
        return {
            "seed": seed,
            "candidate_seat": candidate_seat,
            "status": "complete",
            "scores": [100.0, 90.0],
            "failure": None,
            "steps": rr.EXPECTED_STEPS,
            "episode_steps": rr.EXPECTED_EPISODE_STEPS,
            "trace_sha256": "a" * 64,
        }


class ObserverTests(unittest.TestCase):
    def test_observer_delegates_every_call_once_and_captures_candidate_only(self):
        FakeActor.calls = 0
        game, snapshot = rr.play_with_public_snapshot(
            FakeEvaluator,
            object(),
            ["candidate", "opponent"],
            Path("."),
            Path("."),
            1209131101,
            0,
            20260912,
            1.25,
            10.0,
            900.0,
        )
        self.assertEqual(FakeActor.calls, 6)
        self.assertEqual(game["status"], "complete")
        self.assertEqual(snapshot["own"]["cash"], 1234.0)
        self.assertEqual(snapshot["rival"]["crop_counts"], {"CARROT": 1})

    def test_row_roundtrips_through_merged_p04_normalizer(self):
        snapshot = rr.public_step144_snapshot(observation())
        game = {
            "seed": 1209131101,
            "candidate_seat": 0,
            "status": "complete",
            "scores": [100.0, 90.0],
            "failure": None,
            "steps": rr.EXPECTED_STEPS,
            "episode_steps": rr.EXPECTED_EPISODE_STEPS,
        }
        row = rr.make_row(manifest(7), 7, 1209131101, "apex_v7", 0, snapshot, game)
        self.assertEqual(normalize_row(row), row)
        self.assertEqual(row["terminal_margin"], 10.0)

    def test_incomplete_game_rejected(self):
        snapshot = rr.public_step144_snapshot(observation())
        game = {
            "seed": 1209131101,
            "candidate_seat": 0,
            "status": "failed",
            "scores": None,
            "failure": {"kind": "timeout"},
            "steps": 12,
            "episode_steps": rr.EXPECTED_EPISODE_STEPS,
        }
        with self.assertRaisesRegex(ValueError, "completed failure-free"):
            rr.make_row(manifest(7), 7, 1209131101, "apex_v7", 0, snapshot, game)


class PublicationTests(unittest.TestCase):
    def test_preexisting_receipt_is_untouched_and_row_rolls_back(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            row_path = root / "row.jsonl"
            receipt_path = root / "row.receipt.json"
            receipt_path.write_text("sentinel\n", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                rr._publish_pair(row_path, receipt_path, {"row": 1}, {"receipt": 1})
            self.assertFalse(row_path.exists())
            self.assertEqual(receipt_path.read_text(encoding="utf-8"), "sentinel\n")

    def test_success_publishes_both_create_exclusive(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            row_path = root / "row.jsonl"
            receipt_path = root / "row.receipt.json"
            rr._publish_pair(row_path, receipt_path, {"row": 1}, {"receipt": 1})
            self.assertEqual(json.loads(row_path.read_text()), {"row": 1})
            self.assertEqual(json.loads(receipt_path.read_text()), {"receipt": 1})
            with self.assertRaises(FileExistsError):
                rr._publish_pair(row_path, receipt_path, {"row": 2}, {"receipt": 2})


if __name__ == "__main__":
    unittest.main()
