#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run S1 lifecycle checks through the byte-pinned official interpreter.

No production materializer is executed. Fixtures use the engine's own farm,
private, animal and market constructors; every turn runs its real interpreter
(including market commits, unit actions, town consumption, refresh and EOD).
The external Kaggle seed resolver is import-shimmed to RAISE if initialization
is accidentally called. AttrDict plus a one-step clock increment reproduce the
framework transport only. FEED_PREBUY is an explicit feature-state test seam,
not proof of R04 install/config integration or of field economics.

Example:
  python test_s1_engine_lifecycle.py --engine /path/kaggriculture.py \\
      --helper /path/r04_s1_fert_sweep.py --receipt /tmp/s1-engine.json
  python -O test_s1_engine_lifecycle.py --engine /path/kaggriculture.py \\
      --helper /path/r04_s1_fert_sweep.py

For a reviewed successor, supply --expected-helper-blob <exact Git blob>.
The engine requires its sibling kaggriculture.json, as in the official source.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
import types
import unittest
from contextlib import contextmanager
from pathlib import Path

ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
HELPER_BLOB = "8003f06e696a940a7e02eecc862c2d26f43fad12"
CONFIG = {
    "episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10,
    "shedCapacity": 100, "maxMarketOrdersPerTurn": 10,
    "farmHandCostMult": 1,
}
TARGETS = ((4, 3), (3, 4), (4, 2))
ENGINE = None
LANE = None
EVIDENCE = []


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def load_pinned(name: str, filename: Path, expected_blob: str):
    data = filename.read_bytes()
    actual = git_blob(data)
    if actual != expected_blob:
        raise ValueError(f"{filename}: expected Git blob {expected_blob}, got {actual}")
    spec = importlib.util.spec_from_file_location(name, filename)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import {filename}")
    module = importlib.util.module_from_spec(spec)
    # Avoid using cached bytecode: execute the exact bytes just hashed.
    sys.modules[name] = module
    exec(compile(data, str(filename), "exec"), module.__dict__)
    return module


@contextmanager
def modules_temporarily(mapping):
    absent = object()
    old = {name: sys.modules.get(name, absent) for name in mapping}
    sys.modules.update(mapping)
    try:
        yield
    finally:
        for name, previous in old.items():
            if previous is absent:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


def forbidden_seed_resolver(*args, **kwargs):
    raise RuntimeError("Fixture unexpectedly invoked external Kaggle initialization")


class AttrDict(dict):
    """Kaggle-style attribute access over the same mutable dictionary."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class World:
    def __init__(self, *, player=0, native_hands=1, step=110,
                 species="GOOSE", targets=TARGETS, fed=True, seed=2718):
        self.player = player
        self.step = step
        self.farms = [ENGINE._new_farm(10, 5000) for _ in range(2)]
        self.privates = [ENGINE._new_private() for _ in range(2)]
        for _ in range(native_hands):
            ENGINE._do_hire(self.farms[player], self.privates[player], 10, 1)
        for x, y in targets:
            tile = ENGINE._new_animal(species, 0)
            tile.update(fertilizer_available=True, fed_today=fed)
            self.farms[player]["tiles"][y][x] = tile
        self.market = ENGINE._new_market()
        self.town = ENGINE._new_town()
        self.env = types.SimpleNamespace(configuration=AttrDict(CONFIG),
                                         info={"seed": seed}, done=False)
        self.state = [types.SimpleNamespace(
            observation=AttrDict(step=step, day=step // 24, hour=step % 24,
                player=i, farms=self.farms, private=self.privates[i],
                market=self.market, town=self.town),
            action={}, status="ACTIVE", reward=0,
        ) for i in range(2)]

    @property
    def farm(self):
        return self.farms[self.player]

    @property
    def private(self):
        return self.privates[self.player]

    def observation(self):
        # Real callbacks receive a view; the engine remains authoritative.
        return copy.deepcopy(self.state[self.player].observation)

    def pass_action(self, player=None):
        player = self.player if player is None else player
        return {"farmer": ["PASS"],
                "hands": [["PASS"] for _ in self.farms[player]["hands"]],
                "market": []}

    def advance(self, action, opponent=None):
        self.state[self.player].action = copy.deepcopy(action)
        other = 1 - self.player
        self.state[other].action = copy.deepcopy(
            self.pass_action(other) if opponent is None else opponent)
        ENGINE.interpreter(self.state, self.env)
        # The framework, not interpreter(), advances observation.step.
        self.step += 1
        for row in self.state:
            row.observation.step = self.step


def tape():
    return [{"farmer": ["PASS"], "hands": [], "market": []}
            for _ in range(720)]


def clear_lane():
    LANE._STATE.clear()
    for key in LANE.REPORT:
        LANE.REPORT[key] = 0


def parent_pass(obs, configuration=None):
    return {"farmer": ["PASS"],
            "hands": [["PASS"] for _ in obs["farms"][obs["player"]]["hands"]],
            "market": []}


def callback(tc, wrapped, world):
    observation = world.observation()
    before = copy.deepcopy(observation)
    action = wrapped(observation, CONFIG)
    tc.assertEqual(observation, before, "S1 mutated the engine callback observation")
    return action


class S1EngineLifecycle(unittest.TestCase):
    def setUp(self):
        clear_lane()
        self.feature = types.ModuleType("r04_full_router")
        self.feature.FEED_PREBUY = False
        self.scope = modules_temporarily({"r04_full_router": self.feature})
        self.scope.__enter__()
        self.addCleanup(self.scope.__exit__, None, None, None)

    def test_real_hire_cost_spawn_and_next_callback_custody_both_seats(self):
        spawns = set()
        for player in (0, 1):
            for native_hands in range(8):
                with self.subTest(player=player, native_hands=native_hands):
                    clear_lane()
                    world = World(player=player, native_hands=native_hands)
                    wrapped = LANE.wrap(parent_pass, lambda obs: tape())
                    money = world.farm["money"]
                    cost = ENGINE._hire_cost(world.farm["hires_today"], 1)
                    expected_spawn = ENGINE._spawn_hand(world.farm, 10)
                    first = callback(self, wrapped, world)
                    self.assertEqual(first["market"], [["HIRE"]])
                    self.assertEqual(len(first["hands"]), native_hands)
                    world.advance(first)
                    self.assertEqual(world.farm["money"], money - cost)
                    self.assertEqual(world.farm["hands"][-1], expected_spawn)
                    self.assertEqual(len(world.private["inventories"]), native_hands + 2)
                    self.assertEqual(world.private["inventories"][-1], {})
                    self.assertEqual(LANE.REPORT["hires"], 0)
                    second = callback(self, wrapped, world)
                    self.assertEqual(LANE._STATE[player].index, native_hands)
                    self.assertEqual(LANE.REPORT["hires"], 1)
                    self.assertEqual(len(second["hands"]), native_hands + 1)
                    self.assertEqual(second["market"], [])
                    spawns.add(tuple(expected_spawn))
        self.assertEqual(spawns, set(ENGINE._shed_access_tiles(10)))

    def test_full_interpreter_eod_conserves_parent_and_refreshes_collected_animals(self):
        for species in ("GOOSE", "COW", "SHEEP"):
            for player in (0, 1):
                with self.subTest(species=species, player=player):
                    clear_lane()
                    world = World(player=player, species=species)
                    baseline = copy.deepcopy(world)
                    wrapped = LANE.wrap(parent_pass, lambda obs: tape())
                    hire_cost = ENGINE._hire_cost(world.farm["hires_today"], 1)
                    while world.step < 120:
                        action = callback(self, wrapped, world)
                        world.advance(action)
                        baseline.advance(baseline.pass_action())
                    recovered = world.private["shed"]["FERTILIZER"]
                    self.assertGreaterEqual(recovered, 2)
                    self.assertLessEqual(recovered, len(TARGETS))
                    self.assertEqual(LANE.REPORT["collections"], recovered)
                    self.assertEqual(world.farm["hands"], [])
                    self.assertEqual(world.private["inventories"], [{}])
                    self.assertEqual(world.farm["hires_today"], 0)
                    self.assertEqual(world.farm["money"], baseline.farm["money"] - hire_cost)
                    # Only the real HIRE debit and recovered inventory may differ.
                    normalized_farm = copy.deepcopy(world.farm)
                    normalized_farm["money"] += hire_cost
                    self.assertEqual(normalized_farm, baseline.farm)
                    normalized_private = copy.deepcopy(world.private)
                    normalized_private["shed"]["FERTILIZER"] -= recovered
                    self.assertEqual(normalized_private, baseline.private)
                    self.assertEqual(world.farms[1-player], baseline.farms[1-player])
                    self.assertEqual(world.privates[1-player], baseline.privates[1-player])
                    self.assertEqual(world.market, baseline.market)
                    self.assertEqual(world.town, baseline.town)
                    for x, y in TARGETS:
                        self.assertIs(world.farm["tiles"][y][x]["fertilizer_available"], True)
                    EVIDENCE.append({"kind": "paired_fixture", "species": species,
                        "player": player, "callbacks": 10, "recovered_fertilizer": recovered,
                        "cash_delta": -hire_cost, "parent_state_equal_except_recovery_and_hire": True})

    def test_hand_is_not_commanded_on_hire_turn_and_locked_spawn_can_move(self):
        world = World(native_hands=0)
        wrapped = LANE.wrap(parent_pass, lambda obs: tape())
        first = callback(self, wrapped, world)
        self.assertEqual(first["hands"], [])
        world.advance(first)
        spawn = list(world.farm["hands"][0])
        self.assertEqual(world.farm["tiles"][spawn[1]][spawn[0]], "LOCKED")
        self.assertEqual(world.private["inventories"][1], {})
        second = callback(self, wrapped, world)
        self.assertIn(second["hands"][0][0], ENGINE.FARMER_MOVES)
        world.advance(second)
        self.assertNotEqual(world.farm["hands"][0], spawn)

    def test_original_actor_commands_and_cargo_stay_at_real_indices(self):
        for player in (0, 1):
            clear_lane()
            world = World(player=player, native_hands=3)
            expected = {"farmer": ["WEST"],
                        "hands": [["NORTH"], ["EAST"], ["SOUTH"]], "market": []}
            seen = []
            def parent(obs, configuration=None):
                seen.append(copy.deepcopy(obs))
                return copy.deepcopy(expected)
            wrapped = LANE.wrap(parent, lambda obs: tape())
            world.advance(callback(self, wrapped, world))
            for index in range(4):
                world.private["inventories"][index]["WOOL"] = index + 1
            original_positions = copy.deepcopy([world.farm["farmer"], *world.farm["hands"][:3]])
            action = callback(self, wrapped, world)
            self.assertEqual(seen[-1]["farms"][player]["hands"], world.farm["hands"][:3])
            self.assertEqual(seen[-1]["private"]["inventories"], world.private["inventories"][:4])
            self.assertEqual(action["farmer"], expected["farmer"])
            self.assertEqual(action["hands"][:3], expected["hands"])
            world.advance(action)
            for index, command in enumerate([expected["farmer"], *expected["hands"]]):
                dx, dy = ENGINE.FARMER_MOVES[command[0]]
                x, y = original_positions[index]
                self.assertEqual(ENGINE._farmer_position(world.farm, index), [x+dx, y+dy])
                self.assertEqual(world.private["inventories"][index], {"WOOL": index+1})

    def test_collection_is_real_once_only_and_eod_removes_hidden_index(self):
        world = World()
        wrapped = LANE.wrap(parent_pass, lambda obs: tape())
        world.advance(callback(self, wrapped, world))
        collected = False
        while world.step < 120:
            action = callback(self, wrapped, world)
            if action["hands"][-1] == ["COLLECT_FERTILIZER"] and not collected:
                position = tuple(world.farm["hands"][-1])
                inventory = len(world.private["inventories"]) - 1
                before = world.private["inventories"][inventory].get("FERTILIZER", 0)
                world.advance(action)
                self.assertIs(world.farm["tiles"][position[1]][position[0]]["fertilizer_available"], False)
                self.assertEqual(world.private["inventories"][inventory].get("FERTILIZER", 0), before + 1)
                # Use the real unit-action handler a second time on the same tile.
                ENGINE._apply_unit_action(world.farm, world.private, inventory,
                    ["COLLECT_FERTILIZER"], 10, 4, 24, 100)
                self.assertEqual(world.private["inventories"][inventory].get("FERTILIZER", 0), before + 1)
                collected = True
            else:
                world.advance(action)
        self.assertTrue(collected)
        action = callback(self, wrapped, world)
        self.assertEqual(action["hands"], [])
        self.assertEqual(action["market"], [])
        self.assertIsNone(LANE._STATE[0].index)
        self.assertEqual(LANE._STATE[0].day, 5)

    def test_failed_real_hire_does_not_hide_an_existing_hand_or_retry(self):
        world = World(native_hands=2)
        wrapped = LANE.wrap(parent_pass, lambda obs: tape())
        first = callback(self, wrapped, world)
        self.assertEqual(first["market"], [["HIRE"]])
        # Adversarial callback/execution divergence, not a claim it occurs normally.
        world.farm["money"] = 0.0
        world.advance(first)
        self.assertEqual(len(world.farm["hands"]), 2)
        world.farm["money"] = 5000.0
        second = callback(self, wrapped, world)
        self.assertEqual(second["hands"], [["PASS"], ["PASS"]])
        self.assertEqual(second["market"], [])
        self.assertIsNone(LANE._STATE[0].index)
        self.assertEqual(LANE.REPORT["hire_failures"], 1)
        self.assertEqual(LANE.REPORT["hires"], 0)

    def test_real_market_executes_preserved_sell_prefix_before_appended_hire(self):
        world = World()
        world.private["shed"]["CARROT"] = 2
        def parent(obs, configuration=None):
            result = parent_pass(obs, configuration)
            result["market"] = [["SELL", "CARROT", 2]]
            return result
        wrapped = LANE.wrap(parent, lambda obs: tape())
        first = callback(self, wrapped, world)
        self.assertEqual(first["market"], [["SELL", "CARROT", 2], ["HIRE"]])
        before = world.farm["money"]
        supply = world.market["inventory"]["CARROT"]
        revenue = sum(ENGINE.market_price("CARROT", supply + i) for i in range(2))
        cost = ENGINE._hire_cost(world.farm["hires_today"], 1)
        world.advance(first)
        self.assertEqual(world.private["shed"]["CARROT"], 0)
        self.assertEqual(world.farm["money"], before + revenue - cost)
        self.assertEqual(len(world.farm["hands"]), 2)

    def test_exact_ten_row_cap_retains_parent_and_nine_rows_admits_real_hire(self):
        for rows in (9, 10, 11):
            clear_lane()
            world = World()
            sentinel = parent_pass(world.observation())
            sentinel["market"] = [[] for _ in range(rows)]
            wrapped = LANE.wrap(lambda obs, cfg=None: sentinel, lambda obs: tape())
            result = callback(self, wrapped, world)
            if rows >= 10:
                self.assertIs(result, sentinel)
            else:
                self.assertEqual(result["market"], sentinel["market"] + [["HIRE"]])
            world.advance(result)
            self.assertEqual(len(world.farm["hands"]), 2 if rows == 9 else 1)

    def test_f2_cash_floor_survives_actual_fibonacci_debit(self):
        self.feature.FEED_PREBUY = True
        for player in (0, 1):
            for native_hands in (0, 2, 7):
                for delta in (-0.25, 0.0, 0.25):
                    with self.subTest(player=player, hands=native_hands, delta=delta):
                        clear_lane()
                        world = World(player=player, native_hands=native_hands)
                        cost = ENGINE._hire_cost(world.farm["hires_today"], 1)
                        world.farm["money"] = 1000.0 + cost + delta
                        wrapped = LANE.wrap(parent_pass, lambda obs: tape())
                        result = callback(self, wrapped, world)
                        world.advance(result)
                        self.assertEqual(len(world.farm["hands"]), native_hands + (delta >= 0))
                        if delta >= 0:
                            self.assertEqual(world.farm["money"], 1000.0 + delta)

    def test_late_hire_admission_never_exceeds_real_collection_budget(self):
        admitted = 0
        for player in (0, 1):
            for hour in range(14, 23):
                with self.subTest(player=player, hour=hour):
                    clear_lane()
                    world = World(player=player, step=96 + hour)
                    wrapped = LANE.wrap(parent_pass, lambda obs: tape())
                    first = callback(self, wrapped, world)
                    if first["market"] != [["HIRE"]]:
                        continue
                    admitted += 1
                    callbacks = 23 - hour
                    predicted = min(LANE._reachable_count(start, list(TARGETS), callbacks)
                                    for start in ENGINE._shed_access_tiles(10))
                    world.advance(first)
                    while world.step < 120:
                        world.advance(callback(self, wrapped, world))
                    actual = world.private["shed"]["FERTILIZER"]
                    self.assertGreaterEqual(actual, predicted)
                    self.assertEqual(actual, LANE.REPORT["collections"])
        self.assertGreater(admitted, 0)

    def test_noop_candidate_returns_exact_parent_and_engine_state_matches(self):
        for targets in ((), ((5, 5), (6, 5))):
            for player in (0, 1):
                clear_lane()
                world = World(player=player, targets=targets)
                baseline = copy.deepcopy(world)
                sentinel = parent_pass(world.observation())
                wrapped = LANE.wrap(lambda obs, cfg=None: sentinel, lambda obs: tape())
                result = callback(self, wrapped, world)
                self.assertIs(result, sentinel)
                world.advance(result)
                baseline.advance(sentinel)
                self.assertEqual(world.farms, baseline.farms)
                self.assertEqual(world.privates, baseline.privates)
                self.assertEqual(world.market, baseline.market)

    def test_eod_cargo_drops_before_hands_disappear_without_parent_loss(self):
        world = World()
        world.private["shed"]["WHEAT"] = 65
        world.private["inventories"][0]["WOOL"] = 5
        world.private["inventories"][1]["EGG"] = 5
        wrapped = LANE.wrap(parent_pass, lambda obs: tape())
        while world.step < 120:
            world.advance(callback(self, wrapped, world))
        self.assertEqual(world.private["shed"]["WHEAT"], 65)
        self.assertEqual(world.private["shed"]["WOOL"], 5)
        self.assertEqual(world.private["shed"]["EGG"], 5)
        self.assertGreaterEqual(world.private["shed"]["FERTILIZER"], 2)
        self.assertEqual(world.private["inventories"], [{}])
        self.assertLessEqual(sum(world.private["shed"].values()), 100)

    def test_later_reactive_parent_hire_preserves_middle_hidden_index(self):
        for player in (0, 1):
            with self.subTest(player=player):
                clear_lane()
                world = World(player=player, native_hands=1)
                calls = []
                def parent(obs, configuration=None):
                    calls.append(copy.deepcopy(obs))
                    result = parent_pass(obs, configuration)
                    if obs["step"] == 111:
                        # Reactive parent behavior, not an authored tape HIRE.
                        result["market"] = [["HIRE"]]
                    elif obs["step"] == 112:
                        result["hands"] = [["WEST"], ["NORTH"]]
                    return result
                wrapped = LANE.wrap(parent, lambda obs: tape())
                world.advance(callback(self, wrapped, world))
                world.advance(callback(self, wrapped, world))
                self.assertEqual(len(world.farm["hands"]), 3)
                self.assertEqual(LANE._STATE[player].index, 1)
                before = copy.deepcopy(world.farm["hands"])
                world.private["inventories"][1] = {"WOOL": 1}
                world.private["inventories"][2] = {"FERTILIZER": 1}
                world.private["inventories"][3] = {"EGG": 2}
                result = callback(self, wrapped, world)
                self.assertEqual(result["hands"][0], ["WEST"])
                self.assertEqual(result["hands"][2], ["NORTH"])
                self.assertEqual(calls[-1]["farms"][player]["hands"], [before[0], before[2]])
                self.assertEqual(calls[-1]["private"]["inventories"], [{}, {"WOOL": 1}, {"EGG": 2}])
                world.advance(result)
                self.assertEqual(world.farm["hands"][0], [before[0][0]-1, before[0][1]])
                self.assertEqual(world.farm["hands"][2], [before[2][0], before[2][1]-1])
                self.assertEqual(world.private["inventories"][1], {"WOOL": 1})
                self.assertEqual(world.private["inventories"][3], {"EGG": 2})

    def test_terminal_s1_day_eod_cannot_leak_worker_into_day24_owner(self):
        for player in (0, 1):
            clear_lane()
            world = World(player=player, step=23*24+14)
            wrapped = LANE.wrap(parent_pass, lambda obs: tape())
            while world.step < 24*24:
                world.advance(callback(self, wrapped, world))
            self.assertGreaterEqual(world.private["shed"]["FERTILIZER"], 2)
            self.assertEqual(world.farm["hands"], [])
            # Reuse the same wrapped callable into the reserved endgame day.
            while world.step < 25*24:
                result = callback(self, wrapped, world)
                self.assertEqual(result["market"], [])
                self.assertEqual(result["hands"], [])
                world.advance(result)
            self.assertEqual(LANE.REPORT["hires"], 1)

    def test_incomplete_day_evidence_cannot_buy_a_real_extra_hand(self):
        for player in (0, 1):
            clear_lane()
            world = World(player=player)
            sentinel = parent_pass(world.observation())
            wrapped = LANE.wrap(lambda obs, cfg=None: sentinel,
                                lambda obs: tape()[:obs["step"]+1])
            result = callback(self, wrapped, world)
            self.assertIs(result, sentinel)
            before = world.farm["money"]
            world.advance(result)
            self.assertEqual(len(world.farm["hands"]), 1)
            self.assertEqual(world.farm["money"], before)

    def test_quote_conversion_overflow_is_fail_closed_at_direct_admission(self):
        world = World()
        obs = world.observation()
        obs["market"]["prices"]["FERTILIZER"] = 10 ** 1000
        sentinel = parent_pass(obs)
        day_state = LANE._Day(4)
        before = copy.deepcopy(obs)
        self.assertIs(LANE._consider_hire(obs, sentinel, day_state, tape(), CONFIG), sentinel)
        self.assertEqual(obs, before)
        self.assertIsNone(day_state.pending)
        self.assertFalse(day_state.tried)

    def test_malformed_parent_does_not_count_a_collection_that_engine_never_receives(self):
        world = World()
        sentinel = {"farmer": ["PASS"], "hands": [], "market": []}
        reject = False
        def parent(obs, configuration=None):
            return sentinel if reject else parent_pass(obs, configuration)
        wrapped = LANE.wrap(parent, lambda obs: tape())
        world.advance(callback(self, wrapped, world))
        while world.step < 119:
            x, y = world.farm["hands"][-1]
            tile = world.farm["tiles"][y][x]
            if isinstance(tile, dict) and tile.get("fertilizer_available") is True:
                break
            world.advance(callback(self, wrapped, world))
        self.assertLess(world.step, 119, "fixture must reach an available collection")
        reject = True
        before_count = LANE.REPORT["collections"]
        before_cargo = copy.deepcopy(world.private["inventories"])
        action = callback(self, wrapped, world)
        self.assertIs(action, sentinel)
        self.assertEqual(LANE.REPORT["collections"], before_count)
        world.advance(action)
        self.assertEqual(world.private["inventories"], before_cargo)

    def test_two_seats_use_separate_worker_state_in_same_engine_turns(self):
        world = World(player=0)
        # Give the opponent the same legal fixture without sharing private state.
        world.farms[1] = copy.deepcopy(world.farms[0])
        world.privates[1] = copy.deepcopy(world.privates[0])
        world.state[1].observation.private = world.privates[1]
        agents = [LANE.wrap(parent_pass, lambda obs: tape()) for _ in range(2)]
        while world.step < 120:
            actions = []
            for player in (0, 1):
                world.player = player
                actions.append(callback(self, agents[player], world))
            world.player = 0
            world.advance(actions[0], actions[1])
        self.assertEqual(LANE.REPORT["hires"], 2)
        self.assertIsNot(LANE._STATE[0], LANE._STATE[1])
        self.assertEqual(world.privates[0]["shed"]["FERTILIZER"], world.privates[1]["shed"]["FERTILIZER"])
        self.assertGreaterEqual(world.privates[0]["shed"]["FERTILIZER"], 2)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--helper", type=Path, required=True)
    parser.add_argument("--expected-helper-blob", default=HELPER_BLOB)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    global ENGINE, LANE
    try:
        utils = types.ModuleType("kaggle_environments.utils")
        utils.resolve_episode_seed = forbidden_seed_resolver
        package = types.ModuleType("kaggle_environments")
        package.__path__ = []
        package.utils = utils
        with modules_temporarily({"kaggle_environments": package,
                                  "kaggle_environments.utils": utils}):
            ENGINE = load_pinned("s1_official_engine", args.engine, ENGINE_BLOB)
        LANE = load_pinned("s1_helper_under_test", args.helper, args.expected_helper_blob)
    except (OSError, ValueError, ImportError) as exc:
        print(f"SOURCE VERIFICATION FAILED: {exc}", file=sys.stderr)
        return 2
    EVIDENCE.clear()
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(S1EngineLifecycle))
    receipt = {"schema": "s1-engine-lifecycle/v1", "engine_blob": ENGINE_BLOB,
        "helper_blob": args.expected_helper_blob, "python": sys.version.split()[0],
        "optimized": not __debug__, "tests_run": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors),
        "skipped": len(result.skipped), "success": result.wasSuccessful(),
        "paired_fixtures": EVIDENCE,
        "scope": "actual official interpreter over controlled native-state fixtures; not full R04 package, field economics, or activation proof",
        "transport_seams": ["AttrDict", "framework observation.step increment",
                            "unused seed resolver raises if called", "FEED_PREBUY feature-state module"],
        "engine_transition_stubs": False,
    }
    text = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(text, encoding="utf-8")
    print(text)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
