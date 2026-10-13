# SPDX-License-Identifier: Apache-2.0
"""R04 lane B5 "fert-daily-sweep" checks.

    python -m unittest -v checks/test_v3_r04_fert_daily_sweep.py

Covers the daily fertilizer sweep: flag-off identity, idle-worker collection on
fertilizer-available animal tiles, no displacement of real commands, per-step
target claiming, shed delivery (DROP) with its inventory-work guards, the daily
boolean reset (no stacking), the early-sale plumbing (shed stock visible to the
E184 window, no market rows added by the lane), malformed-observation safety,
and the apply_v3.py / manifest wiring. Standard library only.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_fert_daily_sweep as sweep  # noqa: E402
import r04_full_router as r04  # noqa: E402

SIZE = 10
CENTER = SIZE // 2  # shed-access tiles: x/y in (4, 5)


def animal_tile(available=True):
    return {"kind": "PASTURE", "animal": "COW", "placed_day": 3,
            "fertilizer_available": available}


def make_obs(step, tile_overrides=None, positions=None, inventories=None,
             player=0):
    tiles = [[{"kind": "SOIL"} for _ in range(SIZE)] for _ in range(SIZE)]
    for (x, y), tile in (tile_overrides or {}).items():
        tiles[y][x] = tile
    positions = positions or [[0, 0]]
    farm = {"tiles": tiles, "farmer": list(positions[0]),
            "hands": [list(p) for p in positions[1:]],
            "money": 1000, "unlocked_quadrants": ["NW"], "hires_today": 0}
    n_workers = len(positions)
    invs = [dict(inv) for inv in (inventories or [])]
    invs += [{} for _ in range(n_workers - len(invs))]
    return {"step": step, "day": step // 24, "hour": step % 24, "player": player,
            "farms": [farm, copy.deepcopy(farm)],
            "private": {"inventories": invs, "shed": {}},
            "market": {"prices": {p: 10 for p in r04.PRODUCTS}},
            "town": {"unlocked_shops": ["BAKERY", "YARN_STORE"]}}


def make_action(commands, market=None):
    return {"farmer": list(commands[0]),
            "hands": [list(c) for c in commands[1:]],
            "market": [list(o) for o in (market or [])]}


def blank_tape(steps=719):
    return [{"farmer": ["PASS"], "hands": [], "market": []}
            for _ in range(steps)]


class SweepTest(unittest.TestCase):
    def tearDown(self):
        sweep.reset()
        r04.FERT_DAILY_SWEEP = False
        r04.SALE_EXCLUDED = ("WHEAT", "FERTILIZER")

    # --- collection -----------------------------------------------------

    def test_collect_on_available_animal_tile(self):
        obs = make_obs(100, {(2, 2): animal_tile(True)}, positions=[[2, 2]])
        out = sweep.apply_fert_daily_sweep(
            obs, make_action([["PASS"]]), blank_tape())
        self.assertEqual(out["farmer"], ["COLLECT_FERTILIZER"])
        self.assertEqual(sweep.get_report()["collected"], 1)

    def test_no_collect_when_flag_false(self):
        obs = make_obs(100, {(2, 2): animal_tile(False)}, positions=[[2, 2]])
        action = make_action([["PASS"]])
        out = sweep.apply_fert_daily_sweep(obs, action, blank_tape())
        self.assertIs(out, action)

    def test_no_collect_without_animal(self):
        obs = make_obs(100, {(2, 2): {"kind": "PASTURE"}}, positions=[[2, 2]])
        action = make_action([["PASS"]])
        out = sweep.apply_fert_daily_sweep(obs, action, blank_tape())
        self.assertIs(out, action)

    def test_non_pass_commands_never_touched(self):
        # A real command on a fertilizer tile keeps it: no displacement.
        obs = make_obs(100, {(2, 2): animal_tile(True)}, positions=[[2, 2]])
        for command in (["WATER"], ["HARVEST"], ["NORTH"], ["FERTILIZE"],
                        ["COLLECT_FERTILIZER"], ["DROP"]):
            action = make_action([command])
            out = sweep.apply_fert_daily_sweep(obs, action, blank_tape())
            self.assertIs(out, action, command)

    def test_two_workers_one_tile_collect_once(self):
        obs = make_obs(100, {(2, 2): animal_tile(True)},
                       positions=[[2, 2], [2, 2]],
                       inventories=[{}, {}])
        out = sweep.apply_fert_daily_sweep(
            obs, make_action([["PASS"], ["PASS"]]), blank_tape())
        self.assertEqual(out["farmer"], ["COLLECT_FERTILIZER"])
        self.assertEqual(out["hands"], [["PASS"]])
        rep = sweep.get_report()
        self.assertEqual(rep["collected"], 1)
        self.assertEqual(rep["collect_skipped_claimed"], 1)

    def test_independent_tiles_both_collect(self):
        obs = make_obs(100, {(2, 2): animal_tile(True), (7, 7): animal_tile(True)},
                       positions=[[2, 2], [7, 7]], inventories=[{}, {}])
        out = sweep.apply_fert_daily_sweep(
            obs, make_action([["PASS"], ["PASS"]]), blank_tape())
        self.assertEqual(out["farmer"], ["COLLECT_FERTILIZER"])
        self.assertEqual(out["hands"], [["COLLECT_FERTILIZER"]])

    # --- daily boolean reset: no stacking --------------------------------

    def test_daily_reset_collects_each_day(self):
        # The flag is a per-day boolean; the sweep is stateless across days so
        # each day's fresh unit is collected when a worker idles on the tile.
        for step in (100, 124):  # two consecutive days
            obs = make_obs(step, {(2, 2): animal_tile(True)}, positions=[[2, 2]])
            out = sweep.apply_fert_daily_sweep(
                obs, make_action([["PASS"]]), blank_tape())
            self.assertEqual(out["farmer"], ["COLLECT_FERTILIZER"], step)
        self.assertEqual(sweep.get_report()["collected"], 2)

    # --- delivery --------------------------------------------------------

    def test_drop_beside_shed(self):
        obs = make_obs(100, positions=[[4, 4]],
                       inventories=[{"FERTILIZER": 2}])
        out = sweep.apply_fert_daily_sweep(
            obs, make_action([["PASS"]]), blank_tape())
        self.assertEqual(out["farmer"], ["DROP"])
        self.assertEqual(sweep.get_report()["dropped"], 1)

    def test_no_drop_away_from_shed(self):
        obs = make_obs(100, positions=[[0, 0]],
                       inventories=[{"FERTILIZER": 2}])
        action = make_action([["PASS"]])
        out = sweep.apply_fert_daily_sweep(obs, action, blank_tape())
        self.assertIs(out, action)

    def test_no_drop_without_tape(self):
        # The deliver half needs the tape for its inventory-work guard.
        obs = make_obs(100, positions=[[4, 4]],
                       inventories=[{"FERTILIZER": 2}])
        action = make_action([["PASS"]])
        out = sweep.apply_fert_daily_sweep(obs, action, None)
        self.assertIs(out, action)

    def test_no_drop_with_animal_in_inventory(self):
        # A held animal waits on a tape-planned PLACE; DROP would strand it.
        obs = make_obs(100, positions=[[4, 4]],
                       inventories=[{"FERTILIZER": 1, "COW": 1}])
        action = make_action([["PASS"]])
        out = sweep.apply_fert_daily_sweep(obs, action, blank_tape())
        self.assertIs(out, action)
        self.assertEqual(sweep.get_report()["drop_skipped_guard"], 1)

    def test_no_drop_before_planned_fertilize(self):
        tape = blank_tape()
        tape[105] = {"farmer": ["FERTILIZE"], "hands": [], "market": []}
        obs = make_obs(100, positions=[[4, 4]],
                       inventories=[{"FERTILIZER": 1}])
        action = make_action([["PASS"]])
        out = sweep.apply_fert_daily_sweep(obs, action, tape)
        self.assertIs(out, action)
        self.assertEqual(sweep.get_report()["drop_skipped_guard"], 1)

    def test_no_drop_before_planned_feed(self):
        tape = blank_tape()
        tape[110] = {"farmer": ["FEED"], "hands": [], "market": []}
        obs = make_obs(100, positions=[[4, 4]],
                       inventories=[{"WHEAT": 1, "FERTILIZER": 1}])
        action = make_action([["PASS"]])
        out = sweep.apply_fert_daily_sweep(obs, action, tape)
        self.assertIs(out, action)

    def test_drop_ok_when_work_is_tomorrow(self):
        # FERTILIZE tomorrow is not starved: end-of-day inventory sweep takes
        # the fertilizer to the shed tonight regardless.
        tape = blank_tape()
        tape[130] = {"farmer": ["FERTILIZE"], "hands": [], "market": []}
        obs = make_obs(100, positions=[[4, 4]],
                       inventories=[{"FERTILIZER": 1}])
        out = sweep.apply_fert_daily_sweep(obs, make_action([["PASS"]]), tape)
        self.assertEqual(out["farmer"], ["DROP"])

    def test_drop_moves_mixed_products(self):
        # Non-animal products ride the DROP into the shed for the sale window.
        obs = make_obs(100, positions=[[4, 4]],
                       inventories=[{"MILK": 2, "FERTILIZER": 1}])
        out = sweep.apply_fert_daily_sweep(
            obs, make_action([["PASS"]]), blank_tape())
        self.assertEqual(out["farmer"], ["DROP"])

    # --- early-sale plumbing ----------------------------------------------

    def test_dropped_fertilizer_is_visible_to_sale_window(self):
        # The lane's DROP must surface in projected_shed so reserve_sales can
        # advance the tape's planned FERTILIZER SELL rows (early sale).
        obs = make_obs(300, positions=[[4, 4]],
                       inventories=[{"FERTILIZER": 3}])
        out = sweep.apply_fert_daily_sweep(
            obs, make_action([["PASS"]]), blank_tape())
        self.assertEqual(out["farmer"], ["DROP"])
        view = r04.FarmView(obs)
        self.assertEqual(r04.projected_shed(out, view).get("FERTILIZER"), 3)

    def test_lane_adds_no_market_rows(self):
        obs = make_obs(100, {(2, 2): animal_tile(True)}, positions=[[2, 2]])
        market = [["SELL", "WHEAT", 5]]
        out = sweep.apply_fert_daily_sweep(
            obs, make_action([["PASS"]], market), blank_tape())
        self.assertEqual(out["market"], market)

    def test_sale_window_advances_fertilizer_when_enabled(self):
        # With the V3.1 sale_fertilizer default, FERTILIZER is advanceable.
        r04.install(None, sale_fertilizer=True)
        self.assertNotIn("FERTILIZER", r04.SALE_EXCLUDED)

    # --- malformed input: never raises, action unchanged -------------------

    def test_malformed_observations_are_safe(self):
        good_action = make_action([["PASS"]])
        cases = [
            {},
            {"step": "nope"},
            {"step": 100},  # no farms
            {"step": 100, "farms": [], "player": 0},
            {"step": 100, "farms": [{"tiles": [], "farmer": [0, 0]}],
             "player": 0, "private": {"inventories": [{}]}},
            {"step": 100, "farms": [{"tiles": [[None]], "farmer": [99, 99]}],
             "player": 0, "private": {"inventories": [{}]}},
            {"step": 100, "farms": [{"tiles": [[None]], "farmer": [True, 0]}],
             "player": 0, "private": {"inventories": [{}]}},
        ]
        for obs in cases:
            out = sweep.apply_fert_daily_sweep(obs, good_action, blank_tape())
            self.assertIs(out, good_action, obs)
        for bad_action in (None, [], {"farmer": None}):
            obs = make_obs(100, {(2, 2): animal_tile(True)}, positions=[[2, 2]])
            out = sweep.apply_fert_daily_sweep(obs, bad_action, blank_tape())
            self.assertIs(out, bad_action)

    # --- router wiring -------------------------------------------------------

    def test_flag_off_is_identity_through_v3_agent(self):
        r04.FERT_DAILY_SWEEP = False
        seen = {}

        def stub(observation, configuration=None):
            action = make_action([["PASS"]])
            seen["action"] = action
            return action

        real = r04.POLICY_AGENT
        r04.POLICY_AGENT = stub
        try:
            obs = make_obs(100, {(2, 2): animal_tile(True)}, positions=[[2, 2]])
            out = r04.v3_agent(obs)
            self.assertIs(out, seen["action"])
            self.assertEqual(out["farmer"], ["PASS"])
        finally:
            r04.POLICY_AGENT = real

    def test_flag_on_rewrites_through_v3_agent(self):
        r04.FERT_DAILY_SWEEP = True

        def stub(observation, configuration=None):
            return make_action([["PASS"]])

        real = r04.POLICY_AGENT
        r04.POLICY_AGENT = stub
        try:
            obs = make_obs(100, {(2, 2): animal_tile(True)}, positions=[[2, 2]])
            out = r04.v3_agent(obs)
            self.assertEqual(out["farmer"], ["COLLECT_FERTILIZER"])
        finally:
            r04.POLICY_AGENT = real
            r04.FERT_DAILY_SWEEP = False

    def test_install_wires_the_flag(self):
        self.assertFalse(r04.FERT_DAILY_SWEEP)
        self.assertIs(r04.install(None, fert_daily_sweep=True), r04.v3_agent)
        self.assertTrue(r04.FERT_DAILY_SWEEP)
        r04.install(None, fert_daily_sweep=False)
        self.assertFalse(r04.FERT_DAILY_SWEEP)

    def test_fert_sweep_tape_none_when_unreadable(self):
        self.assertIsNone(r04._fert_sweep_tape({}))
        self.assertIsNone(r04._fert_sweep_tape({"player": "x"}))


class WiringTests(unittest.TestCase):
    @unittest.skipIf(not (ROOT / "titan_runtime.py").exists(),
                     "generated runtime only exists in the materialized tree")
    def test_features_default_off(self):
        from titan_runtime import Features  # noqa: E402
        self.assertIs(Features().r04_fert_daily_sweep, False)

    @unittest.skipIf(not (ROOT / "titan_runtime.py").exists(),
                     "generated runtime only exists in the materialized tree")
    def test_generated_runtime_carries_the_flag(self):
        # apply_v3.py wires the TITAN-CONFIG.json key through Features, the
        # install() call, and the diagnostics of the generated runtime.
        text = (ROOT / "titan_runtime.py").read_text(encoding="utf-8")
        self.assertIn("r04_fert_daily_sweep: bool = False", text)
        self.assertIn("or f.r04_sale_window or f.r04_fert_daily_sweep", text)
        self.assertIn("bool(self.features.r04_fert_daily_sweep)", text)
        self.assertIn("self.diagnostics['fert_daily_sweep']", text)

    @unittest.skipIf(not (Path(__file__).resolve().parents[2] / "V3-MANIFEST.json").exists(),
                     "manifest lives in the source tree, not the materialized tree")
    def test_manifest_registers_the_lane(self):
        manifest = json.loads(
            (Path(__file__).resolve().parents[2] / "V3-MANIFEST.json").read_text(encoding="utf-8"))
        entry = manifest["keys"]["r04_fert_daily_sweep"]
        self.assertFalse(entry["default"])
        self.assertIn("r04_fert_daily_sweep.py", entry["module"])
        r04_lane = next(l for l in manifest["lanes"] if l.get("id") == "R04")
        self.assertIn("r04_fert_daily_sweep", r04_lane["key"])


if __name__ == "__main__":
    unittest.main()
