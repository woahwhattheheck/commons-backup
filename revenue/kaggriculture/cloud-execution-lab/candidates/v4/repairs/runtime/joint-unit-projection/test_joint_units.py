# SPDX-License-Identifier: Apache-2.0
"""Offline, full-interpreter contracts for current native joint-unit replay.

Run: python test_joint_units.py --package /path/to/extracted-b567-package
All assertions use unittest and remain effective under python -O.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
import compose as repair

ROOT = None
PREFIX = None
ENGINE_CALLS = 0
MATRIX_CASES = 0
SOURCE_SHA256 = "e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2"
POSITIONS = ([3, 4], [4, 3], [5, 3], [6, 4])
MOVES = ("EAST", "SOUTH", "SOUTH", "WEST")


def verify_package(root):
    data = (root / "SOURCE.json").read_bytes()
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise ValueError("Expected complete b567 package SOURCE.json")
    manifest = json.loads(data)["runtime"]
    for name, entry in manifest.items():
        data = (root / name).read_bytes()
        if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError(f"Runtime manifest mismatch: {name}")
    for name, pin in (("scheduler.py", repair.SCHEDULER_BLOB), ("frozen_selected.py", repair.FROZEN_BLOB)):
        if repair.git_blob((root / name).read_bytes()) != pin:
            raise ValueError(f"Native source mismatch: {name}")
    return len(manifest)


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def from_source(name, filename, source):
    module = types.ModuleType(name)
    module.__file__ = str(ROOT / filename)
    sys.modules[name] = module
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def build_pair(scheduler_source, frozen_source):
    # Production's literal star-import resolves to the candidate helper.
    old = sys.modules.get("scheduler")
    candidate = from_source("scheduler", "scheduler.py", scheduler_source)
    try:
        frozen = from_source("unitflow_frozen", "frozen_selected.py", frozen_source)
    finally:
        if old is None:
            sys.modules.pop("scheduler", None)
        else:
            sys.modules["scheduler"] = old
    return candidate, frozen


class JointUnits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest_count = verify_package(ROOT)
        sys.path.insert(0, str(ROOT))
        ev = load_file("unitflow_ev", ROOT / "checks/reference/evaluator/evaluate.py")
        cls.ev = ev
        cls.engine, cls.engine_hashes = ev.get_engine(
            ROOT / "checks/reference/engine", ROOT / "checks/reference/evaluator/loader.py")
        cls.old_sources = tuple((ROOT / n).read_text() for n in ("scheduler.py", "frozen_selected.py"))
        cls.new_sources = repair.compose_sources(*cls.old_sources)
        cls.old_s, cls.old_f = build_pair(*cls.old_sources)
        cls.new_s, cls.new_f = build_pair(*cls.new_sources)

    def fixture(self, seat=0, actors=3, seeds=2, cargo=1, stock=99):
        e, S = self.engine, self.ev.Struct
        cfg = S({k: v.get("default") if isinstance(v, dict) else v
                 for k, v in e.specification["configuration"].items()})
        cfg.weedSpawnChance = 0
        farms = [e._new_farm(10, 0), e._new_farm(10, 0)]
        f = farms[seat]
        f["tiles"] = [[None] * 10 for _ in range(10)]
        f["farmer"] = list(POSITIONS[0])
        f["hands"] = [list(pos) for pos in POSITIONS[1:actors]]
        market = e._new_market()
        town = {"unlocked_shops": []}
        state = []
        for i in range(2):
            p = e._new_private()
            if i == seat:
                p["shed"].update({"WHEAT": max(0, stock - 1), "MILK": int(stock > 0)})
                p["seeds"]["WHEAT"] = seeds
                p["seeds"]["CARROT"] = seeds
                p["inventories"] = [{"FERTILIZER": cargo} if cargo else {} for _ in range(actors)]
            state.append(S(observation=S(player=i, step=1, day=0, hour=1,
                                         farms=farms, private=p, market=market, town=town),
                           action={}, status="ACTIVE", reward=0))
        return state, S(configuration=cfg, done=False, info={"seed": 9600803})

    def step(self, state, env, seat, action, t=1):
        global ENGINE_CALLS
        for s in state:
            s.observation.step = t
            s.action = {"farmer": ["PASS"], "hands": [], "market": []}
        state[seat].action = copy.deepcopy(action)
        self.engine.interpreter(state, env)
        ENGINE_CALLS += 1
        return state[0].observation.farms[seat], state[seat].observation.private

    def route(self, actors=3, extra=False, sell=False):
        row = {"farmer": ["PASS"], "hands": [["PASS"] for _ in range(actors - 1)], "market": []}
        route = [copy.deepcopy(row) for _ in range(8)]
        count = actors + int(extra)
        route[2] = {"farmer": ["PLANT", "WHEAT"],
                    "hands": [["PLANT", "WHEAT"] for _ in range(count - 1)], "market": []}
        route[3] = {"farmer": ["FERTILIZE"], "hands": [["FERTILIZE"] for _ in range(actors - 1)], "market": []}
        route[4] = {"farmer": [MOVES[0]], "hands": [[m] for m in MOVES[1:actors]], "market": []}
        route[5] = {"farmer": ["DROP"], "hands": [["DROP"] for _ in range(actors - 1)], "market": []}
        if sell:
            route[6]["market"] = [["SELL", "FERTILIZER", 10]]
        return route

    def projected(self, module, obs, action, capacity=100):
        f, p = copy.deepcopy(obs.farms[obs.player]), copy.deepcopy(obs.private)
        module.apply_projected_units(f, p, action, 10, 0, 24, capacity)
        return f, p

    def test_01_full_engine_unit_matrix(self):
        global MATRIX_CASES
        for seat, actors, raw_count, seeds, mixed in itertools.product(
                range(2), range(1, 5), range(1, 7), range(7), (False, True)):
            state, env = self.fixture(seat, actors, seeds, cargo=0, stock=0)
            rows = [["PLANT", "CARROT" if mixed and i % 2 else "WHEAT"] for i in range(raw_count)]
            action = {"farmer": rows[0], "hands": rows[1:], "market": []}
            obs = state[seat].observation
            before, action_before = copy.deepcopy(obs), copy.deepcopy(action)
            projected = self.projected(self.new_s, obs, action)
            self.assertEqual(obs, before)
            self.assertEqual(action, action_before)
            actual = self.step(state, env, seat, action)
            with self.subTest(seat=seat, actors=actors, raw=raw_count, seeds=seeds, mixed=mixed):
                self.assertEqual(projected, actual)
            MATRIX_CASES += 1

    def test_02_shortage_cannot_hide_drop_overflow(self):
        for seat, actors in itertools.product(range(2), range(2, 5)):
            state, env = self.fixture(seat, actors, actors - 1)
            obs = state[seat].observation
            route = self.route(actors)
            route[1]["market"] = [["SELL", "MILK", 1]]
            verdicts = []
            for module in (self.old_s, self.new_s):
                seller = module.SellScheduler.__new__(module.SellScheduler)
                seller.controller = types.SimpleNamespace(R=[route], cur=0)
                f, p = module.post_units(obs, route[1], env.configuration)
                check = seller.receipt_profile(obs, route[1], f, p, 5, "MILK", env.configuration)
                verdicts.append(check(((1, 1),)))
            self.assertEqual(verdicts, [True, False])
            for t in range(1, 6):
                _, p = self.step(state, env, seat, route[t], t)
            self.assertEqual(p["seeds"]["WHEAT"], actors - 1)
            self.assertEqual(p["shed"]["FERTILIZER"], 2)
            self.assertEqual(sum(p["shed"].values()), 100)
            self.assertEqual(sum(sum(inv.values()) for inv in p["inventories"]), 0)
            # DROP discarded actors-2 units; forecast formerly assumed actors-1 spent.
            self.assertEqual(actors - p["shed"]["FERTILIZER"], actors - 2)

    def test_03_funding_trace_matches_actual_realized_sale(self):
        for seat, actors in itertools.product(range(2), range(2, 5)):
            state, env = self.fixture(seat, actors, actors - 1, stock=0)
            obs = state[seat].observation
            route = self.route(actors, sell=True)
            traces = [module._funding_trace(obs, env.configuration, obs.farms[seat],
                                           obs.private, route, 1, 6, [])
                      for module in (self.old_f, self.new_f)]
            for t in range(1, 7):
                f, p = self.step(state, env, seat, route[t], t)
            self.assertEqual(traces[1]["cash"], f["money"])
            self.assertEqual(traces[1]["executed_sales"][0][2], actors)
            self.assertEqual(traces[0]["executed_sales"][0][2], 1)
            self.assertLess(traces[0]["cash"], f["money"])

    def test_04_event_requires_joint_admission_even_for_nonexistent_hand(self):
        for seat in range(2):
            state, env = self.fixture(seat, 1, 1, stock=0)
            obs = state[seat].observation
            route = self.route(1, extra=True)
            found = [module.represented_shed_event(1, 4, 5, route, obs.farms[seat],
                                                   obs.private, env.configuration)
                     for module in (self.old_f, self.new_f)]
            self.assertEqual(found, [None, 5])
            for t in range(1, 6):
                _, p = self.step(state, env, seat, route[t], t)
            self.assertEqual(p["shed"]["FERTILIZER"], 1)

    def test_05_funded_admission_retains_old_future_results(self):
        for seat, actors in itertools.product(range(2), range(1, 5)):
            state, env = self.fixture(seat, actors, actors, stock=0)
            obs = state[seat].observation
            route = self.route(actors, sell=True)
            results = []
            for module in (self.old_f, self.new_f):
                results.append((module._funding_trace(obs, env.configuration, obs.farms[seat],
                                                     obs.private, route, 1, 6, []),
                                module.represented_shed_event(1, 4, 5, route, obs.farms[seat],
                                                             obs.private, env.configuration)))
            self.assertEqual(results[0], results[1])

    def test_06_invalid_tile_requests_still_count(self):
        for seat, tile in itertools.product(range(2), ("LOCKED", {"kind": "WEED"})):
            state, env = self.fixture(seat, 2, 1, stock=0)
            obs = state[seat].observation
            obs.farms[seat]["tiles"][3][4] = copy.deepcopy(tile)
            action = {"farmer": ["PLANT", "WHEAT"], "hands": [["PLANT", "WHEAT"]]}
            projected = self.projected(self.new_s, obs, action)
            actual = self.step(state, env, seat, action)
            self.assertEqual(projected, actual)
            self.assertIsNone(actual[0]["tiles"][4][3])
            self.assertEqual(actual[1]["seeds"]["WHEAT"], 1)

    def test_07_raw_shape_matches_interpreter(self):
        actions = [None, [], {}, {"hands": None}, {"hands": (["PLANT", "WHEAT"],)},
                   {"farmer": ["PLANT"]}, {"farmer": ("PLANT", "WHEAT")},
                   {"farmer": ["PLANT", "WHEAT"], "hands": [("PLANT", "WHEAT")]},
                   {"farmer": ["PLANT", "WHEAT"], "hands": [[], None, ["PLANT"]]}]
        for seat, action in itertools.product(range(2), actions):
            state, env = self.fixture(seat, 2, 1, stock=0)
            predicted = self.projected(self.new_s, state[seat].observation, action)
            self.assertEqual(predicted, self.step(state, env, seat, action))

    def test_08_current_post_units_retains_detachment_and_parity(self):
        for seeds in range(5):
            state, env = self.fixture(0, 3, seeds)
            obs = state[0].observation
            action = self.route()[2]
            before = copy.deepcopy(obs)
            self.assertEqual(self.old_s.post_units(obs, action, env.configuration),
                             self.new_s.post_units(obs, action, env.configuration))
            f, p = self.new_s.post_units(obs, action, env.configuration)
            f["tiles"][0][0] = {"changed": True}
            p["shed"]["WHEAT"] = -100
            self.assertEqual(obs, before)

    def test_09_current_post_units_handles_short_plant_as_engine_noop(self):
        state, env = self.fixture(0, 1, 1)
        obs = state[0].observation
        action = {"farmer": ["PLANT"], "hands": [], "market": []}
        predicted = self.new_s.post_units(obs, action, env.configuration)
        self.assertEqual(predicted, self.step(state, env, 0, action))

    def test_10_exact_scope_reverses_to_original_bytes(self):
        s, f = self.new_sources
        s = s.replace(repair.HELPER, "", 1).replace(repair.POST_NEW, repair.POST_OLD, 1)
        s = s.replace(repair.RECEIPT_NEW, repair.RECEIPT_OLD, 1)
        f = f.replace(repair.FUNDING_NEW, repair.FUNDING_OLD, 1).replace(repair.EVENT_NEW, repair.EVENT_OLD, 1)
        self.assertEqual((s, f), self.old_sources)

    def test_11_missing_duplicate_and_partial_seams_reject(self):
        s, f = self.old_sources
        for broken_s, broken_f in ((s.replace(repair.POST_OLD, "", 1), f),
                                   (s + "\n" + repair.POST_OLD, f),
                                   (s, f.replace(repair.FUNDING_OLD, "", 1)),
                                   (s, f.replace(repair.EVENT_OLD, "", 1)), self.new_sources):
            with self.assertRaises((ValueError, SyntaxError)):
                repair.compose_sources(broken_s, broken_f)

    def test_12_other_source_edits_are_preserved(self):
        s, f = self.old_sources
        # A disjoint, real control parameter and import-adjacent comment survive.
        s = s.replace("HORIZON = 8", "HORIZON = 7")
        f += "\n# independent source owner marker\n"
        out_s, out_f = repair.compose_sources(s, f)
        self.assertIn("HORIZON = 7", out_s)
        self.assertTrue(out_f.endswith("# independent source owner marker\n"))

    def test_13_behavioral_mutants_are_detected(self):
        variants = {
            "no_gate": repair.HELPER.replace("command[1] in blocked", "False"),
            "strict_boundary": repair.HELPER.replace("count > seeds.get(crop, 0)", "count >= seeds.get(crop, 0)"),
            "truncate_ghost": repair.HELPER.replace("actions = [farmer, *hands]", "actions = [farmer, *hands[:len(farm['hands'])]]"),
            "wrong_crop": repair.HELPER.replace("command[1] in blocked", "'CARROT' in blocked"),
        }
        for name, text in variants.items():
            mutant = from_source("unitflow_mutant", "scheduler.py", "import mechanics as m\n" + text)
            mismatches = 0
            for seeds, extra in ((1, False), (2, False), (2, True)):
                state, env = self.fixture(0, 2, seeds, cargo=0, stock=0)
                action = self.route(2, extra=extra)[2]
                predicted = self.projected(mutant, state[0].observation, action)
                actual = self.step(state, env, 0, action)
                mismatches += predicted != actual
            self.assertGreater(mismatches, 0, name)

    def test_14_cli_reproduces_and_refuses_overwrite_or_wrong_pin(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            command = [sys.executable, str(Path(repair.__file__)), "--package", str(ROOT), "--output", str(output)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            for name, source in zip(("scheduler.py", "frozen_selected.py"), self.new_sources):
                self.assertEqual((output / name).read_text(), source)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            command[command.index(str(output))] = str(Path(directory) / "wrong")
            bad = subprocess.run(command + ["--scheduler-blob", "0" * 40], capture_output=True)
            self.assertNotEqual(bad.returncode, 0)
            self.assertFalse((Path(directory) / "wrong").exists())

    def test_15_package_unchanged(self):
        self.assertEqual(verify_package(ROOT), self.manifest_count)


    def test_16_existing_prefix_repair_composes_without_resetting_it(self):
        data = PREFIX.read_bytes()
        self.assertEqual(repair.git_blob(data), "2958bff92c7d95d9e113b2406e7de1bb7a28de08")
        prefix = load_file("unitflow_prefix", PREFIX)
        predecessor = prefix.transform(self.old_sources[0].encode()).decode()
        sources = repair.compose_sources(predecessor, self.old_sources[1])
        combined, frozen = build_pair(*sources)
        # Reversing only our unit edits recovers the entire exact peer postimage.
        restored = sources[0].replace(repair.HELPER, "", 1)
        restored = restored.replace(repair.POST_NEW, repair.POST_OLD, 1)
        restored = restored.replace(repair.RECEIPT_NEW, repair.RECEIPT_OLD, 1)
        self.assertEqual(restored, predecessor)
        self.assertIs(frozen.apply_projected_units, combined.apply_projected_units)
        for seat, stock in itertools.product(range(2), (97, 99)):
            state, env = self.fixture(seat, 3, 2, stock=stock)
            env.configuration.maxMarketOrdersPerTurn = 1
            obs = state[seat].observation
            route = self.route(3)
            route[1]["market"] = [["SELL", "MILK", 1]]
            route[2]["market"] = [[], ["BUY_ANIMAL", "COW", 999]]
            seller = combined.SellScheduler.__new__(combined.SellScheduler)
            seller.controller = types.SimpleNamespace(R=[route], cur=0)
            f, p = combined.post_units(obs, route[1], env.configuration)
            verdict = seller.receipt_profile(obs, route[1], f, p, 5, "MILK", env.configuration)(((1, 1),))
            self.assertEqual(verdict, stock == 97)
            for t in range(1, 6):
                _, p = self.step(state, env, seat, route[t], t)
            self.assertEqual(p["shed"].get("COW", 0), 0)
            self.assertEqual(sum(p["shed"].values()), min(100, stock + 2))


def main():
    global ROOT, PREFIX
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--prefix-transformer", type=Path, required=True)
    args = parser.parse_args()
    ROOT = args.package.resolve()
    PREFIX = args.prefix_transformer.resolve()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(JointUnits)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {"tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "skips": len(result.skipped), "full_interpreter_calls": ENGINE_CALLS,
              "unit_matrix_cases": MATRIX_CASES, "optimized": not __debug__,
              "verified_runtime_members": getattr(JointUnits, "manifest_count", 0),
              "full_games": 0}
    print("UNITFLOW_RESULT=" + json.dumps(report, sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
