# SPDX-License-Identifier: Apache-2.0
"""Pinned official-engine FEED/EOD transitions for the existing F3 helper.

This exercises real interpreter function bodies, not the legacy R04 router or
an entire match. Only framework seed import and renderer specification I/O are
excluded when loading the source. Fixtures start from initialized engine farms.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import os
from pathlib import Path
from types import ModuleType, SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent if HERE.name == "checks" else HERE
SOURCE = Path(os.environ.get("TITAN_F3_SOURCE", str(ROOT / "r04_v217_eod_tail.py")))
ENGINE_SOURCE = Path(os.environ.get(
    "TITAN_ENGINE_SOURCE",
    str(ROOT.parents[3] / "reference" / "engine" / "kaggriculture.py"),
))
ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
CONFIG = dict(episodeSteps=720, turnsPerDay=24, boardSize=10,
              shedCapacity=100, maxMarketOrdersPerTurn=10)
TAPE = [{"farmer": ["PASS"], "hands": [], "market": []} for _ in range(719)]


def load_engine():
    raw = ENGINE_SOURCE.read_bytes()
    actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if actual != ENGINE_BLOB:
        raise RuntimeError(f"engine pin drift: expected {ENGINE_BLOB}, got {actual}")
    parsed = ast.parse(raw.decode("utf-8"), filename=str(ENGINE_SOURCE))
    nodes = []
    for node in parsed.body:
        if (isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "json_path"
                        for target in node.targets)):
            break
        if isinstance(node, ast.ImportFrom) and node.module == "kaggle_environments.utils":
            continue
        nodes.append(node)
    module = ModuleType("f3_pinned_official_engine")
    module.__file__ = str(ENGINE_SOURCE)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ENGINE_SOURCE), "exec"),
         module.__dict__)
    # Fixtures do not call _initialize: no substitute resolver is installed.
    if "interpreter" not in module.__dict__ or "resolve_episode_seed" in module.__dict__:
        raise RuntimeError("unexpected engine extraction boundary")
    return module


def load_tail():
    spec = importlib.util.spec_from_file_location("f3_engine_tail", SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load F3 helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ENGINE = load_engine()
TAIL = load_tail()


class LiveView:
    def __init__(self, farm, private):
        self.farm, self.private = farm, private

    @property
    def positions(self):
        return [self.farm["farmer"], *self.farm["hands"]]

    @property
    def tiles(self):
        return self.farm["tiles"]

    def inventory(self, worker):
        return self.private["inventories"][worker]

    def beside_shed(self, position):
        return ENGINE._is_shed_adjacent(position, 10)


def make_state(step, seat, *, held_wheat, target):
    farms = [ENGINE._new_farm(10, 3000) for _ in range(2)]
    privates = [ENGINE._new_private() for _ in range(2)]
    # Authorize the eastward route with the real land purchase operation.
    ENGINE._do_buy_land(farms[seat], 10)
    x, y = target
    animal = ENGINE._new_animal("SHEEP", 0)
    animal["consecutive_unfed"] = 1
    farms[seat]["tiles"][y][x] = animal
    privates[seat]["shed"]["WHEAT"] = 8
    privates[seat]["inventories"][0] = {"WHEAT": held_wheat} if held_wheat else {}
    market, town = ENGINE._new_market(), ENGINE._new_town()
    state = []
    for player in range(2):
        observation = SimpleNamespace(farms=farms, private=privates[player],
                                      market=market, town=town, player=player,
                                      step=step, day=step // 24, hour=step % 24)
        state.append(SimpleNamespace(observation=observation,
                                     action={"farmer": ["PASS"], "hands": [], "market": []},
                                     status="ACTIVE", reward=0.0))
    env = SimpleNamespace(configuration=SimpleNamespace(**CONFIG, weedSpawnChance=0.0),
                          info={"seed": 0}, done=False)
    return state, env


def run_commands(state, env, seat, step, commands):
    for offset, command in enumerate(commands):
        for item in state:
            item.observation.step = step + offset
            item.action = {"farmer": ["PASS"], "hands": [], "market": []}
        state[seat].action["farmer"] = command
        result = ENGINE.interpreter(state, env)
        if result is not state:
            raise RuntimeError("interpreter returned an unexpected state object")
        env.done = all(item.status == "DONE" for item in state)


def make_plan(state, seat, step):
    obs = state[seat].observation
    view = LiveView(obs.farms[seat], obs.private)
    return TAIL.plan_v217_eod_tail(
        view, {"plan": 7, "v217_used": 0}, step,
        {"farmer": ["PASS"], "hands": [], "market": []}, [],
        tape=TAPE, projected_wheat=obs.private["shed"]["WHEAT"],
        configuration=CONFIG, enabled=True,
    )


class F3OfficialEngineReset(unittest.TestCase):
    def test_108_real_feed_reset_timelines_and_controls(self):
        count = 0
        # Starting on day2 permits an animal placed day0 to have one hungry day.
        for day in range(2, 29):
            step = day * 24 + 20
            for seat in (0, 1):
                for held_wheat in (0, 1):
                    target = (7, 4) if held_wheat else (6, 4)
                    state, env = make_state(step, seat, held_wheat=held_wheat, target=target)
                    control, control_env = copy.deepcopy((state, env))
                    plan = make_plan(state, seat, step)
                    with self.subTest(day=day, seat=seat, held_wheat=held_wheat):
                        self.assertIsNotNone(plan)
                        self.assertEqual(len(plan["commands"]), 4)
                        self.assertEqual(plan["commands"][-1], ["FEED"])
                        run_commands(state, env, seat, step, plan["commands"])
                        run_commands(control, control_env, seat, step, [["PASS"]] * 4)
                        farm = state[seat].observation.farms[seat]
                        x, y = target
                        self.assertEqual(farm["tiles"][y][x]["animal"], "SHEEP")
                        self.assertEqual(farm["tiles"][y][x]["consecutive_unfed"], 0)
                        self.assertFalse(farm["tiles"][y][x]["fed_today"])
                        self.assertEqual(farm["farmer"], [4, 4])
                        self.assertEqual(state[seat].observation.private["inventories"], [{}])
                        self.assertEqual(state[seat].observation.day, day + 1)
                        self.assertEqual(state[seat].observation.hour, 0)
                        self.assertFalse(env.done)
                        dead_tile = control[seat].observation.farms[seat]["tiles"][y][x]
                        self.assertEqual(dead_tile, {"kind": "PASTURE"})
                    count += 1
        self.assertEqual(count, 108)

    def test_early_feed_has_no_immediate_reset(self):
        for seat in (0, 1):
            state, env = make_state(500, seat, held_wheat=1, target=(6, 4))
            self.assertIsNone(make_plan(state, seat, 500))
            run_commands(state, env, seat, 500, [["EAST"], ["EAST"], ["FEED"]])
            self.assertEqual(state[seat].observation.farms[seat]["farmer"], [6, 4])
            self.assertEqual(state[seat].observation.hour, 23)
            self.assertFalse(env.done)

    def test_final_episode_callback_has_no_nightly_reset(self):
        for seat in (0, 1):
            state, env = make_state(716, seat, held_wheat=1, target=(6, 4))
            self.assertIsNone(make_plan(state, seat, 716))
            run_commands(state, env, seat, 716, [["EAST"], ["EAST"], ["FEED"]])
            self.assertTrue(env.done)
            self.assertEqual([item.status for item in state], ["DONE", "DONE"])
            self.assertEqual(state[seat].observation.farms[seat]["farmer"], [6, 4])
            self.assertEqual(state[seat].observation.day, 29)
            self.assertEqual(state[seat].observation.hour, 23)


if __name__ == "__main__":
    unittest.main()
