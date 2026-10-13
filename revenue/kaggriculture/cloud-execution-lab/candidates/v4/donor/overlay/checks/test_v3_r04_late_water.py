# SPDX-License-Identifier: Apache-2.0
"""R04 lane L1 "kill-late-water": suppression of provably dead WATER commands.

    python -m unittest -v checks/test_v3_r04_late_water.py

Covers the window constants (672-718, coupled to the route's LAST_STEP), each
suppression reason (non-plant tile, already watered today, dead/dying crop, the
defensive past-last-step), that productive WATERs and every non-WATER command are
untouched, that malformed observations never raise and leave the action unchanged,
the module report counters, the off-identity of the wiring (flag off -> v3_agent
output identical), install() plumbing, and the TITAN-CONFIG / delegate wiring.
Standard library only.
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

import r04_full_router as r04  # noqa: E402
import r04_kill_late_water as klw  # noqa: E402
from titan_runtime import Features, TitanAgent  # noqa: E402

CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10, "shedCapacity": 100,
          "maxMarketOrdersPerTurn": 10, "farmHandCostMult": 1}
DEFAULT_KILL = Features().r04_kill_late_water


def plant_tile(crop="WHEAT", watered_today=False, max_lifespan_step=720, yield_units=1):
    return {"kind": "PLANT", "crop": crop, "planted_day": 25,
            "watered_today": watered_today, "yield_units": yield_units,
            "consecutive_unwatered": 0, "fertilized_until_day": -1,
            "max_lifespan_step": max_lifespan_step}


def late_observation(step, tiles=(), farmer=(4, 4), hands=()):
    """Synthetic 10x10 farm; tiles is ((x, y), tile-or-sentinel) pairs."""
    size = 10
    grid = [[{"kind": "SOIL"} for _ in range(size)] for _ in range(size)]
    for (x, y), tile in tiles:
        grid[y][x] = tile
    farm = {"tiles": grid, "farmer": list(farmer),
            "hands": [list(position) for position in hands],
            "money": 1000, "unlocked_quadrants": ["NW"], "hires_today": 0}
    return {"step": step, "day": step // 24, "hour": step % 24, "player": 0,
            "farms": [farm, copy.deepcopy(farm)],
            "private": {"inventories": [{}], "shed": {}},
            "market": {"prices": {}, "inventory": {}},
            "town": {"unlocked_shops": []}}


class KillLateWaterBase(unittest.TestCase):
    def setUp(self):
        self._policy_agent = r04.POLICY_AGENT
        klw.reset()

    def tearDown(self):
        r04.POLICY_AGENT = self._policy_agent
        r04.KILL_LATE_WATER = False
        r04.ROW_ORDER = False
        r04.EVENING_FLUSH = False
        r04.OPEN_ROUNDTRIP = 0
        klw.reset()


class WindowTests(KillLateWaterBase):
    def test_window_constants_match_the_route(self):
        self.assertEqual((klw.LATE_START, klw.LATE_END), (672, 718))
        self.assertEqual(klw.LATE_END, r04.LAST_STEP)

    def test_outside_the_window_the_action_is_untouched(self):
        obs = late_observation(671, [((4, 4), "LOCKED")])
        action = {"farmer": ["WATER"], "hands": [["WATER"]], "market": []}
        self.assertIs(klw.apply_kill_late_water(obs, action), action)
        obs = late_observation(719, [((4, 4), "LOCKED")])
        self.assertIs(klw.apply_kill_late_water(obs, action), action)

    def test_window_edges_suppress(self):
        for step in (672, 718):
            obs = late_observation(step, [((4, 4), "LOCKED")], hands=[(4, 4)])
            out = klw.apply_kill_late_water(
                obs, {"farmer": ["WATER"], "hands": [["WATER"]], "market": []})
            self.assertEqual(out["farmer"], ["PASS"])
            self.assertEqual(out["hands"], [["PASS"]])


class ReasonTests(KillLateWaterBase):
    def run_layer(self, step, tiles, farmer=(4, 4), hands=(), farmer_cmd="WATER",
                  hand_cmds=None):
        obs = late_observation(step, tiles, farmer=farmer, hands=hands)
        hand_cmds = [["WATER"] for _ in hands] if hand_cmds is None else hand_cmds
        action = {"farmer": [farmer_cmd], "hands": [list(c) for c in hand_cmds],
                  "market": []}
        return klw.apply_kill_late_water(obs, action), action

    def test_non_plant_tiles_become_pass(self):
        for sentinel in ("LOCKED", {"kind": "SOIL"}, {"kind": "WEED"}, None,
                         {"kind": "COOP"}, {"kind": "PASTURE"}):
            out, _ = self.run_layer(700, [((4, 4), sentinel)], hands=[(4, 4)])
            self.assertEqual(out["hands"], [["PASS"]], sentinel)

    def test_already_watered_becomes_pass(self):
        tile = plant_tile(watered_today=True)
        out, _ = self.run_layer(700, [((4, 4), tile)], hands=[(4, 4)])
        self.assertEqual(out["hands"], [["PASS"]])

    def test_dead_or_dying_becomes_pass(self):
        for mls in (700, 699, 672):
            tile = plant_tile(max_lifespan_step=mls)
            out, _ = self.run_layer(700, [((4, 4), tile)], hands=[(4, 4)])
            self.assertEqual(out["hands"], [["PASS"]], mls)

    def test_crop_alive_past_this_step_is_kept(self):
        tile = plant_tile(max_lifespan_step=701)
        out, _ = self.run_layer(700, [((4, 4), tile)], hands=[(4, 4)])
        self.assertEqual(out["hands"], [["WATER"]])

    def test_past_last_step_reason(self):
        tile = plant_tile(max_lifespan_step=721)
        self.assertEqual(klw.suppress_reason(719, tile), "past_last")
        self.assertEqual(klw.suppress_reason(720, tile), "past_last")
        # dead_or_dying still takes precedence when the crop is already dead.
        self.assertEqual(klw.suppress_reason(720, plant_tile(max_lifespan_step=720)),
                         "dead_or_dying")

    def test_productive_water_is_kept_not_harvested(self):
        tile = plant_tile(watered_today=False, max_lifespan_step=720, yield_units=3)
        out, _ = self.run_layer(700, [((4, 4), tile)], hands=[(4, 4)])
        self.assertEqual(out["hands"], [["WATER"]])

    def test_farmer_water_is_suppressed(self):
        out, _ = self.run_layer(700, [((4, 4), "LOCKED")])
        self.assertEqual(out["farmer"], ["PASS"])

    def test_non_water_commands_are_untouched(self):
        tiles = [((4, 4), plant_tile(watered_today=True)),
                 ((5, 5), plant_tile(watered_today=True))]
        out, _ = self.run_layer(700, tiles, farmer=(4, 4), hands=[(5, 5)],
                                farmer_cmd="HARVEST",
                                hand_cmds=[["PLANT", "WHEAT"]])
        self.assertEqual(out["farmer"], ["HARVEST"])
        self.assertEqual(out["hands"], [["PLANT", "WHEAT"]])

    def test_mixed_workers_only_dead_waters_suppressed(self):
        tiles = [((4, 4), "LOCKED"),
                 ((5, 5), plant_tile(watered_today=True)),
                 ((6, 6), plant_tile(watered_today=False, max_lifespan_step=720))]
        out, _ = self.run_layer(700, tiles, farmer=(4, 4),
                                hands=[(5, 5), (6, 6), (7, 7)],
                                hand_cmds=[["WATER"], ["WATER"], ["HARVEST"]])
        self.assertEqual(out["farmer"], ["PASS"])
        self.assertEqual(out["hands"], [["PASS"], ["WATER"], ["HARVEST"]])

    def test_input_action_is_not_mutated(self):
        obs = late_observation(700, [((4, 4), "LOCKED")], hands=[(4, 4)])
        action = {"farmer": ["WATER"], "hands": [["WATER"]], "market": []}
        frozen = copy.deepcopy(action)
        klw.apply_kill_late_water(obs, action)
        self.assertEqual(action, frozen)


class RobustnessTests(KillLateWaterBase):
    def test_malformed_observations_never_raise(self):
        action = {"farmer": ["WATER"], "hands": [["WATER"]], "market": []}
        bad_observations = [
            {},
            {"step": 700},
            {"step": 700, "farms": []},
            {"step": 700, "player": 5, "farms": [{"tiles": [], "farmer": [0, 0]}]},
            {"step": 700, "player": 0,
             "farms": [{"tiles": None, "farmer": [0, 0], "hands": []}]},
            {"step": 700, "player": 0,
             "farms": [{"tiles": [[{"kind": "SOIL"}]], "farmer": [99, 99],
                        "hands": [[-1, -1]]}]},
            {"step": "not-a-step", "player": 0, "farms": []},
        ]
        for obs in bad_observations:
            self.assertIs(klw.apply_kill_late_water(obs, action), action, obs)

    def test_malformed_action_never_raises(self):
        obs = late_observation(700, [((4, 4), "LOCKED")])
        for action in (None, [], "WATER", {"farmer": ["WATER"], "hands": None}):
            try:
                klw.apply_kill_late_water(obs, action)
            except Exception as error:  # pragma: no cover
                self.fail("raised %r on %r" % (error, action))


class ReportTests(KillLateWaterBase):
    def test_report_counts_reasons_and_steps(self):
        klw.reset()
        tiles = [((0, 0), "LOCKED"),
                 ((1, 1), plant_tile(watered_today=True)),
                 ((2, 2), plant_tile(watered_today=True)),
                 ((3, 3), plant_tile(max_lifespan_step=700)),
                 ((4, 4), plant_tile(watered_today=False, max_lifespan_step=720))]
        hands = [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4)]
        obs = late_observation(700, tiles, farmer=(9, 9), hands=hands)
        action = {"farmer": ["PASS"],
                  "hands": [["WATER"]] * 5, "market": []}
        klw.apply_kill_late_water(obs, action)
        report = klw.get_report()
        self.assertEqual(report["steps_active"], 1)
        self.assertEqual(report["non_plant"], 1)
        self.assertEqual(report["already_watered"], 2)
        self.assertEqual(report["dead_or_dying"], 1)
        self.assertEqual(report["past_last"], 0)
        self.assertEqual(report["productive_kept"], 1)
        klw.reset()
        self.assertEqual(klw.get_report()["steps_active"], 0)


class WiringTests(KillLateWaterBase):
    def test_flag_off_is_identity(self):
        sentinel = {"farmer": ["WATER"], "hands": [["WATER"], ["HARVEST"]],
                    "market": [["SELL", "WHEAT", 1]]}
        r04.POLICY_AGENT = lambda observation, configuration=None: copy.deepcopy(sentinel)
        r04.KILL_LATE_WATER = False
        out = r04.v3_agent(late_observation(700), dict(CONFIG))
        self.assertEqual(out, sentinel)

    def test_flag_on_suppresses_between_policy_and_row_order(self):
        calls = []

        def fake_policy(observation, configuration=None):
            calls.append("policy")
            return {"farmer": ["WATER"], "hands": [], "market": []}

        r04.POLICY_AGENT = fake_policy
        r04.KILL_LATE_WATER = True
        out = r04.v3_agent(late_observation(700, [((4, 4), "LOCKED")]), dict(CONFIG))
        self.assertEqual(calls, ["policy"])
        self.assertEqual(out["farmer"], ["PASS"])

    def test_install_defaults_leave_the_flag_off(self):
        self.assertIs(DEFAULT_KILL, False)
        self.assertIs(r04.KILL_LATE_WATER, False)
        r04.install(None, 8)
        self.assertIs(r04.KILL_LATE_WATER, False)

    def test_install_sets_the_flag(self):
        r04.install(None, 8, 0, False, False, True, True, True)
        self.assertIs(r04.KILL_LATE_WATER, True)
        r04.install(None, 8, 0, False, False, True, True, False)
        self.assertIs(r04.KILL_LATE_WATER, False)

    def test_key_ships_off_and_reaches_the_delegate(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        self.assertIs(data["r04_kill_late_water"], False)
        self.assertIs(Features(**data).r04_kill_late_water, False)
        self.assertFalse(TitanAgent(Features())._v3_active())
        self.assertTrue(TitanAgent(Features(r04_kill_late_water=True))._v3_active())
        for on in (True, False):
            agent = TitanAgent(Features(r04_sale_window=True, r04_kill_late_water=on))
            agent.act(late_observation(0), dict(CONFIG))
            self.assertIs(r04.KILL_LATE_WATER, on)
            self.assertIs(agent.diagnostics["kill_late_water"], on)

    def test_release_note_documents_the_lane(self):
        note = (ROOT / "TITAN-RELEASE.md").read_text(encoding="utf-8")
        self.assertIn("r04_kill_late_water", note)


if __name__ == "__main__":
    unittest.main(verbosity=2)
