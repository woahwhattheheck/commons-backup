#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Full official-interpreter evidence for B7's day-boundary priority repair.

No evaluator, runtime import, market substitute, or game initialization is used.
The exact engine executes units, market, town, decay, EOD, and terminal rewards.
Only its unused seed-resolution import is supplied by an explicit raising shim.
Use B7_TEST_ARM=donor to reproduce failures on the preserved predecessor.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import compose_b7_eod_gate as composer

HERE = Path(__file__).resolve().parent
ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
SPEC_BLOB = "b354d06b742fe48402513792253f1a5c29366b20"
ORACLE_BLOB = "109bf70a385b211eede790f00a2de05a979b4e02"
REPAIRED_BLOB = "d7fc5688eed719f0de9ef935cbe2db2ff8d55774"
ARM = os.environ.get("B7_TEST_ARM", "repaired")
if ARM not in ("donor", "repaired"):
    raise ValueError("B7_TEST_ARM must be donor or repaired")
METRICS = {"interpreter_calls": 0, "non_eod_cells": 0,
           "eod_priority_cells": 0, "seed_calls": 0, "witnesses": []}


def pinned_bytes(path, expected):
    data = path.read_bytes()
    got = composer.git_blob_sha(data)
    if got != expected:
        raise ValueError(f"source drift at {path}: expected {expected}, got {got}")
    return data


def load_source(name, source, path):
    module = ModuleType(name)
    module.__file__ = str(path)
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


def load_engine(path):
    source = pinned_bytes(path, ENGINE_BLOB)
    pinned_bytes(path.with_suffix(".json"), SPEC_BLOB)
    package = ModuleType("kaggle_environments")
    package.__path__ = []
    utils = ModuleType("kaggle_environments.utils")

    def forbidden_seed(*args, **kwargs):
        METRICS["seed_calls"] += 1
        raise RuntimeError("B7 full-turn tests forbid initialization/seed resolution")

    utils.resolve_episode_seed = forbidden_seed
    package.utils = utils
    # Restore all pre-existing module bindings, including on import failure.
    with patch.dict(sys.modules, {package.__name__: package, utils.__name__: utils}):
        return load_source("_b7_full_turn_engine", source, path)


def find_lab():
    for parent in HERE.parents:
        if (parent / "reference/engine/kaggriculture.py").is_file():
            return parent
    raise RuntimeError("pinned lab engine not found; no synthetic fallback")


def pass_action(hands=0):
    return {"farmer": ["PASS"], "hands": [["PASS"] for _ in range(hands)], "market": []}


def fixture(engine, *, seat=0, step=263, spawn=(4, 4), actor=0,
            actors=2, room=0, item="WHEAT", qty=10, later_milk=10,
            turns=24, capacity=100):
    farms = [engine._new_farm(10, 3000) for _ in range(2)]
    farms[seat]["farmer"] = list(spawn)
    farms[seat]["hands"] = [list(spawn) for _ in range(actors - 1)]
    private = [engine._new_private(), engine._new_private()]
    private[seat]["inventories"] = [{} for _ in range(actors)]
    private[seat]["inventories"][actor] = {item: qty}
    if later_milk:
        if actor >= actors - 1:
            raise ValueError("competing cargo requires a later actor")
        private[seat]["inventories"][-1] = {"MILK": later_milk}
    private[seat]["shed"]["CARROT"] = capacity - room
    market = engine._new_market()
    town = engine._new_town()
    state = [SimpleNamespace(
        observation=SimpleNamespace(player=i, step=step, day=step // turns,
                                    hour=step % turns, farms=farms,
                                    private=private[i], market=market, town=town),
        action=pass_action(actors - 1 if i == seat else 0),
        reward=0, status="ACTIVE") for i in range(2)]
    action = state[seat].action
    if actor == 0:
        action["farmer"] = ["DROP"]
    else:
        action["hands"][actor - 1] = ["DROP"]
    cfg = SimpleNamespace(boardSize=10, turnsPerDay=turns, shedCapacity=capacity,
                          maxMarketOrdersPerTurn=10, episodeSteps=720,
                          weedSpawnChance=0)
    return state, SimpleNamespace(configuration=cfg, info={"seed": 1701}, done=False)


def observation(state, seat):
    return vars(state[seat].observation)


def snapshot(state):
    return [copy.deepcopy(vars(s)) for s in state]


def outcome_snapshot(state):
    # Input actions intentionally differ; compare all engine-produced state.
    return [{k: copy.deepcopy(v) for k, v in vars(agent).items() if k != "action"}
            for agent in state]


def interpret(engine, state, env):
    METRICS["interpreter_calls"] += 1
    result = engine.interpreter(state, env)
    if result is not state:
        raise AssertionError("unexpected official interpreter container replacement")
    return state


class FullTurnB7Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lab = find_lab()
        cls.donor_bytes = pinned_bytes(HERE / "legacy/b7_shed_room_guard.py", composer.DONOR_BLOB)
        cls.repaired_bytes = composer.repair_source(cls.donor_bytes)
        if composer.git_blob_sha(cls.repaired_bytes) != REPAIRED_BLOB:
            raise ValueError("composed B7 output drift")
        cls.donor = load_source("_b7_donor", cls.donor_bytes, HERE / "legacy/b7_shed_room_guard.py")
        cls.repaired = load_source("_b7_repaired", cls.repaired_bytes, HERE / "composed-in-memory.py")
        cls.helper = cls.donor if ARM == "donor" else cls.repaired
        cls.engine = load_engine(cls.lab / "reference/engine/kaggriculture.py")
        cls.oracle = load_source("_b7_original_oracle",
                                pinned_bytes(HERE / "current_engine_oracle.py", ORACLE_BLOB),
                                HERE / "current_engine_oracle.py")
        # Also verifies the exact current runtime bytes and hook order, without importing it.
        cls.pins = cls.oracle.assert_pins(cls.lab.parents[2])

    def transform(self, state, env, seat=0, helper=None):
        action = state[seat].action
        before = copy.deepcopy(state)
        out = (helper or self.helper).transform(observation(state, seat), action,
                                               vars(env.configuration), enabled=True)
        self.assertEqual(snapshot(state), snapshot(before))
        return out

    def test_original_matrix_still_passes(self):
        result = self.oracle.run_matrix(self.repaired, self.engine)
        self.assertEqual(result["cells"], 128)
        self.assertEqual(result["changed_cells"], 80)
        self.assertEqual(result["unchanged_cells"], 48)

    def test_original_order_boundaries_still_pass(self):
        self.assertEqual(self.oracle.run_order_boundaries(self.repaired, self.engine)["count"], 5)

    def test_exact_counterexample_and_repair_both_seats(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                initial, env = fixture(self.engine, seat=seat)
                initial[seat].action["market"] = [["SELL", "CARROT", 10]]
                control, legacy, fixed = [copy.deepcopy(initial) for _ in range(3)]
                legacy[seat].action = self.transform(legacy, env, seat, self.donor)
                fixed_original = fixed[seat].action
                fixed[seat].action = self.transform(fixed, env, seat)
                self.assertIs(fixed[seat].action, fixed_original)
                for state in (control, legacy, fixed):
                    interpret(self.engine, state, copy.deepcopy(env))
                self.assertEqual(snapshot(fixed), snapshot(control))
                self.assertEqual(control[seat].observation.private["shed"]["MILK"], 10)
                self.assertEqual(legacy[seat].observation.private["shed"]["MILK"], 0)
                self.assertEqual(legacy[seat].observation.private["shed"]["WHEAT"], 10)
                for state in (control, legacy, fixed):
                    for agent in state:
                        agent.observation.step = 264
                        agent.action = pass_action()
                    state[seat].action["market"] = [["SELL", "WHEAT", 10], ["SELL", "MILK", 10]]
                    interpret(self.engine, state, copy.deepcopy(env))
                cash = [state[seat].observation.farms[seat]["money"]
                        for state in (control, legacy, fixed)]
                self.assertEqual(cash, [4834.0, 3565.0, 4834.0])
                METRICS["witnesses"].append({"seat": seat, "parent_cash": cash[0],
                                           "donor_cash": cash[1], "repaired_cash": cash[2],
                                           "donor_delta": cash[1] - cash[0]})

    def test_eod_identity_all_spawns_actor_indices_and_day_lengths(self):
        for seat in (0, 1):
            for spawn in ((4, 4), (5, 4), (4, 5), (5, 5)):
                for actor in (0, 1, 3):
                    for turns in (1, 6, 24, 48):
                        with self.subTest(seat=seat, spawn=spawn, actor=actor, turns=turns):
                            state, env = fixture(self.engine, seat=seat, spawn=spawn, actor=actor,
                                                 actors=5, turns=turns, step=11 * turns - 1)
                            state[seat].action["market"] = [["SELL", "CARROT", 10]]
                            original = state[seat].action
                            out = self.transform(state, env, seat)
                            self.assertIs(out, original)
                            control = copy.deepcopy(state)
                            state[seat].action = out
                            interpret(self.engine, state, copy.deepcopy(env))
                            interpret(self.engine, control, copy.deepcopy(env))
                            self.assertEqual(snapshot(state), snapshot(control))
                            METRICS["eod_priority_cells"] += 1

    def test_non_eod_full_interpreter_differential(self):
        for seat in (0, 1):
            for spawn in ((4, 4), (5, 4), (4, 5), (5, 5)):
                for actor in (0, 1, 3):
                    for step in (240, 262, 264, 718):
                        for room in (0, 1, 5):
                            for item in self.engine.PRODUCTS:
                                with self.subTest(seat=seat, spawn=spawn, actor=actor,
                                                  step=step, room=room, item=item):
                                    initial, env = fixture(self.engine, seat=seat, spawn=spawn,
                                                           actor=actor, actors=4, step=step,
                                                           room=room, item=item, qty=6, later_milk=0)
                                    initial[seat].action["market"] = [["SELL", item, 6]]
                                    initial[1-seat].observation.private["shed"][item] = 3
                                    initial[1-seat].action["market"] = [["SELL", item, 3]]
                                    parent, legacy, fixed = [copy.deepcopy(initial) for _ in range(3)]
                                    legacy[seat].action = self.transform(legacy, env, seat, self.donor)
                                    fixed[seat].action = self.transform(fixed, env, seat)
                                    self.assertEqual(fixed[seat].action, legacy[seat].action)
                                    for state in (parent, legacy, fixed):
                                        interpret(self.engine, state, copy.deepcopy(env))
                                    self.assertEqual(snapshot(fixed), snapshot(legacy))
                                    inv = fixed[seat].observation.private["inventories"][actor]
                                    self.assertEqual(inv.pop(item), 6 - room)
                                    # After removing only the saved cargo, EVERY state field agrees:
                                    # both money balances, market/shed, tiles, rival, reward, status.
                                    self.assertEqual(outcome_snapshot(fixed), outcome_snapshot(parent))
                                    METRICS["non_eod_cells"] += 1

    def test_eod_conservative_noop_even_without_competing_cargo(self):
        state, env = fixture(self.engine, actors=1, later_milk=0)
        state[0].action["market"] = [["SELL", "CARROT", 10]]
        action = state[0].action
        self.assertIs(self.transform(state, env), action)

    def test_off_identity_even_with_malformed_clock(self):
        action = object()
        for value in (None, {}, [], False):
            self.assertIs(self.helper.transform(value, action, None, enabled=False), action)

    def test_invalid_or_missing_step_fails_closed(self):
        for step in (None, True, False, "263", 263.0, -1, [], {}, float("nan"), float("inf")):
            with self.subTest(step=step):
                state, env = fixture(self.engine, step=240)
                state[0].observation.step = step
                self.assertIs(self.transform(state, env), state[0].action)
        state, env = fixture(self.engine, step=240)
        del state[0].observation.step
        self.assertIs(self.transform(state, env), state[0].action)

    def test_invalid_day_length_fails_closed(self):
        for turns in (None, 0, -1, True, "24", 24.0, [], {}, float("nan"), float("inf")):
            with self.subTest(turns=turns):
                state, env = fixture(self.engine, step=240)
                env.configuration.turnsPerDay = turns
                self.assertIs(self.transform(state, env), state[0].action)

    def test_missing_day_length_uses_official_default(self):
        for step, same in ((262, False), (263, True), (264, False)):
            with self.subTest(step=step):
                state, env = fixture(self.engine, step=step, later_milk=0)
                del env.configuration.turnsPerDay
                out = self.transform(state, env)
                self.assertEqual(out is state[0].action, same)

    def test_all_day_boundary_neighbors(self):
        for turns in (2, 6, 24, 48):
            for day in (0, 1, 10, 28):
                for offset in (-2, -1, 0):
                    step = (day + 1) * turns + offset
                    state, env = fixture(self.engine, step=step, turns=turns, later_milk=0)
                    out = self.transform(state, env)
                    self.assertEqual(out is state[0].action, offset == -1)

    def test_off_by_one_boundary_mutant_is_detected(self):
        mutant_source = self.repaired_bytes.replace(b"(step + 1) % turns_per_day", b"step % turns_per_day")
        mutant = load_source("_b7_wrong_boundary", mutant_source, HERE / "mutant.py")
        state, env = fixture(self.engine)
        self.assertIsNot(self.transform(state, env, helper=mutant), state[0].action)

    def test_blanket_noop_mutant_is_detected(self):
        mutant = SimpleNamespace(transform=lambda observation, action, configuration=None,
                                 enabled=False: action)
        with self.assertRaises(self.oracle.OracleError):
            self.oracle.run_matrix(mutant, self.engine)

    def test_wrong_actor_pass_mutant_is_detected(self):
        def destructive(observation, action, configuration=None, enabled=False):
            if not enabled:
                return action
            out = copy.deepcopy(action)
            out["farmer"] = ["PASS"]
            return out
        mutant = SimpleNamespace(transform=destructive)
        with self.assertRaises(self.oracle.OracleError):
            self.oracle.run_matrix(mutant, self.engine)

    def test_source_composition_changes_only_gate(self):
        self.assertEqual(self.repaired_bytes.replace(composer.GATE.encode(), b"", 1), self.donor_bytes)
        self.assertEqual(composer.git_blob_sha(self.repaired_bytes), REPAIRED_BLOB)
        self.assertEqual(self.repaired_bytes.count(composer.GATE.encode()), 1)

    def test_source_drift_rejected_not_silently_rebased(self):
        for data in (b"", self.donor_bytes + b"\n", self.donor_bytes[:-1], self.repaired_bytes):
            with self.subTest(length=len(data)):
                with self.assertRaises(ValueError):
                    composer.repair_source(data)
        with self.assertRaises(TypeError):
            composer.repair_source(self.donor_bytes.decode())

    def test_engine_import_restores_module_bindings(self):
        names = ("kaggle_environments", "kaggle_environments.utils")
        sentinels = {name: ModuleType(name) for name in names}
        with patch.dict(sys.modules, sentinels):
            engine = load_engine(self.lab / "reference/engine/kaggriculture.py")
            for name in names:
                self.assertIs(sys.modules[name], sentinels[name])
            self.assertTrue(callable(engine.interpreter))

    def test_raise_on_seed_resolution_no_fake_rng(self):
        before = METRICS["seed_calls"]
        with self.assertRaisesRegex(RuntimeError, "forbid initialization"):
            self.engine.resolve_episode_seed(None)
        self.assertEqual(METRICS["seed_calls"], before + 1)
        METRICS["seed_calls"] = before  # negative-control call, not an executed-turn call

    def test_unchanged_inputs_and_source_bytes(self):
        state, env = fixture(self.engine)
        before, cfg = snapshot(state), copy.deepcopy(vars(env.configuration))
        self.transform(state, env)
        self.assertEqual(snapshot(state), before)
        self.assertEqual(vars(env.configuration), cfg)
        self.assertEqual(pinned_bytes(HERE / "legacy/b7_shed_room_guard.py", composer.DONOR_BLOB),
                         self.donor_bytes)
        self.assertEqual(METRICS["seed_calls"], 0)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(FullTurnB7Tests))
    print(json.dumps({"status": "PASS" if result.wasSuccessful() else "FAIL",
                      "arm": ARM, "tests": result.testsRun,
                      "failures": len(result.failures), "errors": len(result.errors),
                      "metrics": METRICS, "repaired_blob": REPAIRED_BLOB,
                      "scope": "constructed full-turn evidence; not field economics or runtime promotion"},
                     indent=2, sort_keys=True))
    raise SystemExit(not result.wasSuccessful())
