# SPDX-License-Identifier: Apache-2.0
"""Focused source/engine gate for W2 CARE-bank COLLECT->FEED admission.

No promotion is asserted here. The test binds the admission theorem to the
official engine and proves fail-closed route/source custody while preserving
the pre-existing repeated-FEED->CARE API.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
reference_override = os.environ.get("TITAN_REFERENCE_ROOT")
REFERENCE = Path(reference_override).resolve() if reference_override else (HERE.parents[4] / "reference").resolve()
SOURCE = Path(os.environ.get("W2_SOURCE", HERE / "dead_feed_care.py")).resolve()
ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
CFG = {"boardSize": 10, "turnsPerDay": 24, "episodeSteps": 720, "shedCapacity": 100}


def blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


lane = load(SOURCE, "_w2_carebank_candidate")
evaluator = load(REFERENCE / "evaluator/evaluate.py", "_w2_carebank_evaluator")
engine, _ = evaluator.get_engine(REFERENCE / "engine", REFERENCE / "evaluator/loader.py")


def fixture(*, step=690, placed=21, pending=2, units=0, wheat=4, fertilizer=True,
            fed=False, cared=True, unfed=0, hands=0, rows=None):
    tiles = [[None for _ in range(10)] for __ in range(10)]
    tiles[4][2] = {
        "kind": "PASTURE", "animal": "COW", "placed_day": placed,
        "yield_units": units, "consecutive_unfed": unfed,
        "fed_today": fed, "cared_today": cared,
        "fertilizer_available": fertilizer, "pending_care_bonus": pending,
    }
    farm = {
        "farmer": [2, 4], "hands": [[2, 4] for _ in range(hands)],
        "tiles": tiles, "money": 100, "unlocked_quadrants": ["NW"], "hires_today": 0,
    }
    other = {
        "farmer": [4, 4], "hands": [],
        "tiles": [[None for _ in range(10)] for __ in range(10)],
        "money": 100, "unlocked_quadrants": ["NW"], "hires_today": 0,
    }
    private = {
        "inventories": [{"WHEAT": wheat} for _ in range(hands + 1)],
        "shed": {}, "seeds": {},
    }
    observation = {"step": step, "player": 0, "farms": [farm, other], "private": private}
    if rows is None:
        rows = [["COLLECT_FERTILIZER"], *([["PASS"]] * hands)]
    action = {"farmer": rows[0], "hands": rows[1:], "market": []}
    route = [{"farmer": ["PASS"], "hands": [], "market": []} for _ in range(720)]
    return observation, action, route


class CarebankFeedSwap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if blob(REFERENCE / "engine/kaggriculture.py") != ENGINE_BLOB:
            raise ValueError("official engine blob mismatch")

    def test_exact_engine_trade_realizes_old_bank(self):
        obs, action, route = fixture()
        plan = lane.plan_carebank_feed_swap(action, obs, CFG, route)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["realizable_bonus"], 2)
        candidate = lane.apply_carebank_feed_swap(action, obs, CFG, route, enabled=True)
        self.assertEqual(candidate["farmer"], ["FEED"])
        self.assertEqual(action["farmer"], ["COLLECT_FERTILIZER"])

        left_farm, left_private = copy.deepcopy((obs["farms"][0], obs["private"]))
        right_farm, right_private = copy.deepcopy((obs["farms"][0], obs["private"]))
        engine._apply_unit_action(left_farm, left_private, 0, action["farmer"], 10, 28, 24, 100)
        engine._apply_unit_action(right_farm, right_private, 0, candidate["farmer"], 10, 28, 24, 100)
        self.assertEqual(left_private["inventories"][0]["FERTILIZER"], 1)
        self.assertEqual(right_private["inventories"][0]["WHEAT"], 3)
        self.assertTrue(right_farm["tiles"][4][2]["fed_today"])

        engine._daily_refresh_animals(left_farm, 28)
        engine._daily_refresh_animals(right_farm, 28)
        left = left_farm["tiles"][4][2]
        right = right_farm["tiles"][4][2]
        self.assertEqual((left["yield_units"], left["pending_care_bonus"], left["consecutive_unfed"]),
                         (1, 0, 1))
        self.assertEqual((right["yield_units"], right["pending_care_bonus"], right["consecutive_unfed"]),
                         (3, 1, 0))

    def test_value_preconditions_fail_closed(self):
        cases = [
            {"pending": 0},
            {"placed": 20},
            {"units": 5},
            {"fertilizer": False},
            {"wheat": 0},
            {"fed": True},
        ]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                obs, action, route = fixture(**kwargs)
                self.assertEqual(lane.plan_carebank_feed_swap(action, obs, CFG, route), [])

    def test_current_same_site_feed_blocks(self):
        obs, action, route = fixture(
            hands=1, rows=[["COLLECT_FERTILIZER"], ["FEED"]])
        self.assertEqual(lane.plan_carebank_feed_swap(action, obs, CFG, route), [])

    def test_current_hire_and_duplicate_collect_block(self):
        obs, action, route = fixture()
        action["market"] = [["HIRE"]]
        self.assertEqual(lane.plan_carebank_feed_swap(action, obs, CFG, route), [])

        obs, action, route = fixture(
            hands=1, rows=[["COLLECT_FERTILIZER"], ["COLLECT_FERTILIZER"]])
        self.assertEqual(lane.plan_carebank_feed_swap(action, obs, CFG, route), [])

    def test_extended_farmer_collect_competes_with_exact_hand(self):
        obs, action, route = fixture(
            hands=1,
            rows=[["COLLECT_FERTILIZER", "extra"], ["COLLECT_FERTILIZER"]])
        self.assertEqual(lane.plan_carebank_feed_swap(action, obs, CFG, route), [])
        farm, private = copy.deepcopy((obs["farms"][0], obs["private"]))
        engine._apply_unit_action(
            farm, private, 0, action["farmer"], 10, 28, 24, 100)
        self.assertEqual(private["inventories"][0]["FERTILIZER"], 1)

    def test_extended_hand_collect_competes_with_exact_farmer(self):
        obs, action, route = fixture(
            hands=1,
            rows=[["COLLECT_FERTILIZER"], ["COLLECT_FERTILIZER", "extra"]])
        self.assertEqual(lane.plan_carebank_feed_swap(action, obs, CFG, route), [])
        farm, private = copy.deepcopy((obs["farms"][0], obs["private"]))
        engine._apply_unit_action(
            farm, private, 1, action["hands"][0], 10, 28, 24, 100)
        self.assertEqual(private["inventories"][1]["FERTILIZER"], 1)

    def test_future_feed_hire_and_malformed_route_block(self):
        obs, action, route = fixture()
        route[691] = {"farmer": ["PASS"], "hands": [["FEED"]], "market": []}
        self.assertEqual(lane.plan_carebank_feed_swap(action, obs, CFG, route), [])

        obs, action, route = fixture()
        route[691] = {"farmer": ["PASS"], "hands": [], "market": [["HIRE"]]}
        self.assertEqual(lane.plan_carebank_feed_swap(action, obs, CFG, route), [])

        obs, action, route = fixture()
        route[691] = "malformed"
        self.assertEqual(lane.plan_carebank_feed_swap(action, obs, CFG, route), [])

    def test_eod_needs_no_future_route(self):
        obs, action, _ = fixture(step=695, placed=21)
        plan = lane.plan_carebank_feed_swap(action, obs, CFG, None)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["route_certificate"]["checked_steps"], 0)

    def test_malformed_pending_bank_fails_closed(self):
        obs, action, route = fixture(pending=10_000)
        self.assertEqual(lane.plan_carebank_feed_swap(action, obs, CFG, route), [])

    def test_disabled_and_nomatch_identity(self):
        obs, action, route = fixture()
        self.assertIs(lane.apply_carebank_feed_swap(action, obs, CFG, route), action)
        obs["farms"][0]["tiles"][4][2]["pending_care_bonus"] = 0
        self.assertIs(lane.apply_carebank_feed_swap(
            action, obs, CFG, route, enabled=True), action)

    def test_truthy_enable_poison_is_identity_and_telemetry_inert(self):
        poison = ("false", 1, 1.0, [True], {"enabled": False})
        for token in poison:
            with self.subTest(seam="carebank", token=token):
                obs, action, route = fixture()
                before = copy.deepcopy(lane.telemetry)
                self.assertIs(
                    lane.apply_carebank_feed_swap(
                        action, obs, CFG, route, enabled=token
                    ),
                    action,
                )
                self.assertEqual(lane.telemetry, before)
            with self.subTest(seam="dead_feed_care", token=token):
                obs, action, _ = fixture(
                    step=240, placed=0, pending=0, fed=True, cared=False,
                    rows=[["FEED"]],
                )
                before = copy.deepcopy(lane.telemetry)
                self.assertIs(
                    lane.apply_dead_feed_care(action, obs, CFG, enabled=token),
                    action,
                )
                self.assertEqual(lane.telemetry, before)

    def test_literal_true_remains_active_on_both_apply_seams(self):
        obs, action, route = fixture()
        carebank = lane.apply_carebank_feed_swap(
            action, obs, CFG, route, enabled=True
        )
        self.assertEqual(carebank["farmer"], ["FEED"])
        self.assertEqual(action["farmer"], ["COLLECT_FERTILIZER"])

        obs, action, _ = fixture(
            step=240, placed=0, pending=0, fed=True, cared=False,
            rows=[["FEED"]],
        )
        dead_feed = lane.apply_dead_feed_care(action, obs, CFG, enabled=True)
        self.assertEqual(dead_feed["farmer"], ["CARE"])
        self.assertEqual(action["farmer"], ["FEED"])

    def test_legacy_repeated_feed_care_unchanged(self):
        obs, action, _ = fixture(
            step=240, placed=0, pending=0, fed=True, cared=False,
            rows=[["FEED"]])
        result = lane.apply_dead_feed_care(action, obs, CFG, enabled=True)
        self.assertEqual(result["farmer"], ["CARE"])


if __name__ == "__main__":
    unittest.main()
