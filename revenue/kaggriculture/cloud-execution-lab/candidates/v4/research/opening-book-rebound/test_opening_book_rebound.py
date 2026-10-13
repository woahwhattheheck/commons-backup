#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


book = load(HERE / "opening_book_rebound.py", "opening_book_rebound_test")


def action(farmer=None, market=None):
    return {
        "farmer": list(farmer or ["PASS"]),
        "hands": [],
        "market": [list(row) for row in (market or [])],
    }


def observation(step: int, *, melon: int = 0, strawberry: int = 0, wheat: int = 0):
    seeds = {crop: 0 for crop in ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON")}
    seeds.update({"WHEAT": wheat, "MELON": melon, "STRAWBERRY": strawberry})
    tiles = [[None for _ in range(10)] for _ in range(10)]
    farm = {
        "money": 3000,
        "hires_today": 0,
        "unlocked_quadrants": ["NW"],
        "farmer": [1, 1],
        "hands": [],
        "tiles": tiles,
    }
    return {
        "step": step,
        "player": 0,
        "farms": [farm, dict(farm)],
        "private": {"seeds": seeds},
    }


CFG = {
    "maxMarketOrdersPerTurn": 10,
    "boardSize": 10,
    "episodeSteps": 720,
    "farmHandCostMult": 1,
}


class OpeningBookReboundTests(unittest.TestCase):
    def make_book(self):
        return book.OpeningBookRebound(book.OpeningBookConfig(quota_per_target=1))

    def test_dependency_is_exact_current_priceseed(self):
        data = book.SEED_BUDGET_PATH.read_bytes()
        self.assertEqual(book.git_blob_sha(data), book.EXPECTED_SEED_BUDGET_BLOB)

    def test_disabled_is_exact_identity(self):
        adapter = self.make_book()
        parent = action()
        result, report = adapter.prepare(
            parent, observation(0), CFG, action(["PLANT", "WHEAT"]),
            episode="ep", route="r", enabled=False,
        )
        self.assertIs(result, parent)
        self.assertEqual(report["status"], "disabled")

    def test_prepare_only_buys_for_next_callback(self):
        adapter = self.make_book()
        parent = action()
        result, report = adapter.prepare(
            parent, observation(0), CFG, action(["PLANT", "WHEAT"]),
            episode="ep", route="r", enabled=True,
        )
        self.assertEqual(parent["farmer"], ["PASS"])
        self.assertEqual(result["farmer"], ["PASS"])
        self.assertEqual(result["market"], [["BUY_SEED", "MELON", 1]])
        self.assertEqual(report["status"], "purchase-proposed")
        self.assertEqual(report["opening_target"], "MELON")
        self.assertEqual(report["source_status"], "independently_reauthored_not_historical_donor")

    def test_real_return_and_observed_fill_are_required(self):
        adapter = self.make_book()
        parent = action()
        proposed, _ = adapter.prepare(
            parent, observation(0), CFG, action(["PLANT", "WHEAT"]),
            episode="ep", route="r", enabled=True,
        )
        self.assertTrue(adapter.record_returned(
            proposed, observation(0), CFG, episode="ep", route="r"))
        next_parent = action(["PLANT", "WHEAT"])
        planted, report = adapter.apply(
            next_parent, observation(1, melon=1, wheat=1), CFG,
            episode="ep", route="r",
        )
        self.assertEqual(planted["farmer"], ["PLANT", "MELON"])
        self.assertEqual(report["status"], "plant-proposed")
        self.assertEqual(report["planted"], {"MELON": 1, "STRAWBERRY": 0})

    def test_rejected_return_never_rewrites_next_action(self):
        adapter = self.make_book()
        proposed, _ = adapter.prepare(
            action(), observation(0), CFG, action(["PLANT", "WHEAT"]),
            episode="ep", route="r", enabled=True,
        )
        altered = {**proposed, "market": proposed["market"] + [["HIRE"]]}
        self.assertFalse(adapter.record_returned(
            altered, observation(0), CFG, episode="ep", route="r"))
        next_parent = action(["PLANT", "WHEAT"])
        result, report = adapter.apply(
            next_parent, observation(1, melon=1, wheat=1), CFG,
            episode="ep", route="r",
        )
        self.assertIs(result, next_parent)
        self.assertEqual(report["status"], "no-ticket")
        self.assertEqual(adapter.planted, {"MELON": 0, "STRAWBERRY": 0})

    def test_fill_shortfall_preserves_parent_and_quota(self):
        adapter = self.make_book()
        proposed, _ = adapter.prepare(
            action(), observation(0), CFG, action(["PLANT", "WHEAT"]),
            episode="ep", route="r", enabled=True,
        )
        self.assertTrue(adapter.record_returned(
            proposed, observation(0), CFG, episode="ep", route="r"))
        next_parent = action(["PLANT", "WHEAT"])
        result, report = adapter.apply(
            next_parent, observation(1, melon=0, wheat=1), CFG,
            episode="ep", route="r",
        )
        self.assertIs(result, next_parent)
        self.assertEqual(report["status"], "observed-fill-shortfall")
        self.assertEqual(adapter.planted, {"MELON": 0, "STRAWBERRY": 0})

    def test_quota_advances_melon_then_strawberry(self):
        adapter = self.make_book()
        first, _ = adapter.prepare(
            action(), observation(0), CFG, action(["PLANT", "WHEAT"]),
            episode="ep", route="r", enabled=True,
        )
        self.assertTrue(adapter.record_returned(first, observation(0), CFG,
                                                episode="ep", route="r"))
        adapter.apply(action(["PLANT", "WHEAT"]), observation(1, melon=1, wheat=1), CFG,
                      episode="ep", route="r")
        second, report = adapter.prepare(
            action(), observation(2, melon=1, wheat=1), CFG, action(["PLANT", "WHEAT"]),
            episode="ep", route="r", enabled=True,
        )
        self.assertEqual(second["market"], [["BUY_SEED", "STRAWBERRY", 1]])
        self.assertEqual(report["opening_target"], "STRAWBERRY")

    def test_opening_window_is_bounded(self):
        adapter = self.make_book()
        parent = action()
        result, report = adapter.prepare(
            parent, observation(72), CFG, action(["PLANT", "WHEAT"]),
            episode="ep", route="r", enabled=True,
        )
        self.assertIs(result, parent)
        self.assertEqual(report["status"], "outside-opening-window")

    def test_episode_change_resets_local_quota_and_budget_state(self):
        adapter = self.make_book()
        adapter._planted["MELON"] = 1
        adapter.reset("next")
        self.assertEqual(adapter.planted, {"MELON": 0, "STRAWBERRY": 0})


if __name__ == "__main__":
    unittest.main()
