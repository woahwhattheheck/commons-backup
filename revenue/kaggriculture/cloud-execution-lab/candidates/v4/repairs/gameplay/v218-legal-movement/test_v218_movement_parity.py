#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Pinned full-engine component oracle; synthetic parent tapes, not full games.

TITAN_ROUTER selects canonical a3e2 or authenticated historical 21c4 fixture.
TITAN_ENGINE selects exact kaggriculture.py with its adjacent specification.
Only the external seed resolver is supplied by the fixture loader;
all moves, stock, terrain actions, markets, night and terminal logic are real.
"""
from __future__ import annotations
import ast
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest

import v218_movement_parity as repair

HERE = Path(__file__).resolve().parent
REPORT = {"scope": "FULL_ENGINE_WITH_PINNED_V218_COMPONENTS_AND_SYNTHETIC_PARENT",
          "production_activation": False, "full_game_economics": False}
SPEC_BLOB = "b354d06b742fe48402513792253f1a5c29366b20"
CONFIG = dict(episodeSteps=720, turnsPerDay=24, boardSize=10,
              shedCapacity=100, maxMarketOrdersPerTurn=10)
CORNERS = ((4, 4), (5, 4), (4, 5), (5, 5))

class Struct(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc
    __setattr__ = dict.__setitem__

def locate(variable, suffix):
    if variable in os.environ:
        return Path(os.environ[variable])
    for parent in HERE.parents:
        candidate = parent / suffix
        if candidate.is_file():
            return candidate
    raise RuntimeError(f"set {variable} to the exact pinned source file")

def load_engine(path):
    if repair.git_blob(path.read_bytes()) != repair.ENGINE_BLOB:
        raise repair.PinError("official engine identity mismatch")
    if repair.git_blob(path.with_name("kaggriculture.json").read_bytes()) != SPEC_BLOB:
        raise repair.PinError("official engine specification identity mismatch")
    names = ("kaggle_environments", "kaggle_environments.utils")
    missing = object()
    prior = {name: sys.modules.get(name, missing) for name in names}
    package = types.ModuleType(names[0])
    utilities = types.ModuleType(names[1])
    utilities.resolve_episode_seed = lambda env: env.info["seed"]
    package.utils = utilities
    try:
        sys.modules.update({names[0]: package, names[1]: utilities})
        spec = importlib.util.spec_from_file_location("_v218_official_engine", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name in names:
            if prior[name] is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior[name]

def component_code(text):
    body = []
    for node in ast.parse(text).body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in repair.COMPONENT_SHA256:
            body.append(node)
        if (isinstance(node, ast.FunctionDef) and node.name == "agent"
                and any(isinstance(n, ast.Name) and n.id == "_V218_PARENT" for n in ast.walk(node))):
            node.name = "run_agent"
            body.append(node)
    return compile(ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])),
                   "<pinned-v218-components>", "exec")

def namespace(code, engine, tape=None, plan=2):
    if tape is None:
        tape = [{"farmer": ["WATER"], "hands": [["PASS"]], "market": []}
                for _ in range(719)]
        tape[718]["market"] = [["SELL", "FERTILIZER", 100]]
    states = [types.SimpleNamespace(plan=plan, last_step=712, queues={}) for _ in range(2)]
    ns = {"copy": copy, "_V217_MOVES": engine.FARMER_MOVES,
          "_V218_PARENT": lambda obs, cfg: copy.deepcopy(tape[obs["step"]]),
          "_V218_REPORT": dict(plans=0, planned_units=0, collections=0, aborts=0, capacity_declines=0),
          "_POLICY": types.SimpleNamespace(tapes=[tape] * 3, players=states)}
    exec(code, ns)
    return ns

def fixture(engine, seat=0, start=(5, 5), target=(3, 4), stock=0):
    cfg = Struct(CONFIG)
    env = types.SimpleNamespace(configuration=cfg, info={"seed": 101}, done=False)
    state = [Struct(observation=Struct(), action={}, status="ACTIVE", reward=0) for _ in range(2)]
    engine._initialize(state, env)
    farm = state[seat].observation.farms[seat]
    farm["hands"] = [list(start)]
    animal = engine._new_animal("SHEEP", 0)
    animal["fertilizer_available"] = True
    farm["tiles"][target[1]][target[0]] = animal
    private = state[seat].observation.private
    private["inventories"] = [{}, {}]
    private["shed"]["CARROT"] = stock
    state[0].observation.market["inventory"]["FERTILIZER"] = 20000
    engine._refresh_prices(state[0].observation.market)
    for entry in state:
        entry.observation.step = 712
    return state, env

def episode_tail(code, engine, seat=0, start=(5, 5), target=(3, 4), stock=0):
    ns = namespace(code, engine)
    state, env = fixture(engine, seat, start, target, stock)
    trace = []
    for step in range(712, 719):
        for entry in state:
            entry.observation.step = step
            entry.action = engine.pass_agent(None)
        action = ns["run_agent"](state[seat].observation, env.configuration)
        state[seat].action = action
        engine.interpreter(state, env)
        trace.append({"step": step, "action": copy.deepcopy(action),
                      "position": copy.deepcopy(state[0].observation.farms[seat]["hands"])})
    return state, trace, dict(ns["_V218_REPORT"])

class MovementParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path("revenue/kaggriculture/cloud-execution-lab")
        cls.router = locate("TITAN_ROUTER", root / "candidates/v4/donor/overlay/r04_full_router.py")
        cls.engine_path = locate("TITAN_ENGINE", root / "checks/reference/engine/kaggriculture.py")
        cls.raw = cls.router.read_bytes()
        cls.router_blob = repair.git_blob(cls.raw)
        if cls.router_blob not in (repair.CURRENT_ROUTER_BLOB, repair.HISTORICAL_FIXTURE_BLOB):
            raise repair.PinError("oracle router fixture is not a named authenticated whole file")
        cls.source = cls.raw.decode("utf-8")
        repair.verify(cls.source)
        cls.post = repair.transform(cls.source, enabled=True)
        cls.old_code, cls.new_code = map(component_code, (cls.source, cls.post))
        cls.engine = load_engine(cls.engine_path)
        REPORT.update(router_blob=cls.router_blob, engine_blob=repair.ENGINE_BLOB,
                      current_router_input=cls.router_blob == repair.CURRENT_ROUTER_BLOB,
                      whole_router_executed=False,
                      component_sha256=repair.COMPONENT_SHA256,
                      postimage_blob=repair.git_blob(cls.post.encode()))

    def test_off_is_exact_identity(self):
        self.assertIs(repair.transform(self.source), self.source)
        self.assertEqual(repair.transform("future source", enabled=False), "future source")

    def test_exactly_two_filters_change(self):
        expected = self.source.replace(repair.PATH_OLD, repair.PATH_NEW).replace(repair.SHEDS_OLD, repair.SHEDS_NEW)
        self.assertEqual(self.post, expected)
        self.assertEqual(self.source.count(repair.PATH_OLD), 1)
        self.assertEqual(self.source.count(repair.SHEDS_OLD), 1)
        compile(self.post, "<transformed-router>", "exec")

    def test_guard_source_drift_is_rejected(self):
        for old, new in (("state.plan!=2", "state.plan!=1"), ("if len(final)<=7", "if len(final)<=8"),
                         ("_v218_capacity_bound(view)>100", "_v218_capacity_bound(view)>101")):
            with self.subTest(old=old), self.assertRaises(repair.PinError):
                repair.transform(self.source.replace(old, new), enabled=True)

    def test_double_apply_rejected(self):
        with self.assertRaises(repair.PinError):
            repair.transform(self.post, enabled=True)

    def test_missing_or_duplicate_components_rejected(self):
        with self.assertRaises(repair.PinError):
            repair.transform("x=1", enabled=True)
        with self.assertRaises(repair.PinError):
            repair.transform(self.source + "\ndef _v218_path(a,b,c): return []\n", enabled=True)

    def test_enable_requires_literal_bool(self):
        for enabled in (1, 0, "true", None):
            with self.subTest(enabled=enabled), self.assertRaises(TypeError):
                repair.transform(self.source, enabled=enabled)

    def test_all_board_routes_match_actual_engine_movement(self):
        old = namespace(self.old_code, self.engine)["_v218_path"]
        new = namespace(self.new_code, self.engine)["_v218_path"]
        checked = admitted = retained = 0
        quadrants = ("NW", "NE", "SW", "SE")
        for count in range(1, 5):
            allowed = quadrants[:count]
            tiles = [[None if self.engine._quadrant_of(x, y, 10) in allowed else "LOCKED"
                      for x in range(10)] for y in range(10)]
            farm = self.engine._new_farm(10, 3000)
            farm["tiles"] = tiles
            private = self.engine._new_private()
            for sy in range(10):
                for sx in range(10):
                    for ey in range(10):
                        for ex in range(10):
                            start, end = (sx, sy), (ex, ey)
                            previous, path = old(start, end, tiles), new(start, end, tiles)
                            self.assertIsNotNone(path)
                            self.assertEqual(len(path), abs(ex - sx) + abs(ey - sy))
                            if previous is not None:
                                self.assertEqual(path, previous)
                                retained += 1
                            else:
                                admitted += 1
                            farm["farmer"] = list(start)
                            for command in path:
                                self.engine._apply_unit_action(farm, private, 0, command, 10, 29, 24, 100)
                            self.assertEqual(farm["farmer"], list(end))
                            checked += 1
        REPORT["movement_paths"] = dict(checked=checked, newly_admitted=admitted, retained_exact=retained)

    def test_out_of_bounds_remains_rejected(self):
        path = namespace(self.new_code, self.engine)["_v218_path"]
        board = [[None] * 10 for _ in range(10)]
        for end in ((-1, 4), (10, 4), (4, -1), (4, 10)):
            self.assertIsNone(path((4, 4), end, board))

    def test_locked_shed_drop_is_real_but_plant_remains_illegal(self):
        for seat in (0, 1):
            for position in CORNERS[1:]:
                state, env = fixture(self.engine, seat=seat)
                farm = state[0].observation.farms[seat]
                private = state[seat].observation.private
                farm["farmer"] = list(position)
                private = state[seat].observation.private
                private["inventories"][0] = {"FERTILIZER": 3}
                state[seat].action = {"farmer": ["DROP"], "hands": [], "market": []}
                self.engine.interpreter(state, env)
                self.assertEqual(private["shed"]["FERTILIZER"], 3)
                self.assertEqual(farm["tiles"][position[1]][position[0]], "LOCKED")
                for entry in state:
                    entry.observation.step = 713
                private["seeds"]["WHEAT"] = 1
                state[seat].action = {"farmer": ["PLANT", "WHEAT"], "hands": [], "market": []}
                self.engine.interpreter(state, env)
                self.assertEqual(private["seeds"]["WHEAT"], 1)
                self.assertEqual(farm["tiles"][position[1]][position[0]], "LOCKED")

    def test_terminal_pair_grid(self):
        cells = improved = 0
        by_seat = [0, 0]
        for seat in (0, 1):
            for start in CORNERS:
                for y in range(5):
                    for x in range(5):
                        for stock in (0, 99, 100):
                            target = (x, y)
                            before, _, _ = episode_tail(self.old_code, self.engine, seat, start, target, stock)
                            after, _, report = episode_tail(self.new_code, self.engine, seat, start, target, stock)
                            own0, own1 = before[0].observation.farms[seat], after[0].observation.farms[seat]
                            delta = own1["money"] - own0["money"]
                            self.assertIn(delta, (0, 1))
                            self.assertEqual(report["aborts"], 0)
                            self.assertEqual(after[seat].status, "DONE")
                            self.assertEqual(after[seat].observation.private["shed"]["CARROT"], stock)
                            self.assertEqual(after[seat].observation.private["inventories"], [{}, {}])
                            self.assertEqual(before[0].observation.farms[1-seat], after[0].observation.farms[1-seat])
                            self.assertEqual(before[0].observation.market, after[0].observation.market)
                            if stock == 100:
                                self.assertEqual(report["plans"], 0)
                            if delta:
                                improved += 1
                                by_seat[seat] += 1
                            cells += 1
        self.assertGreater(improved, 0)
        self.assertEqual(by_seat[0], by_seat[1])
        REPORT["terminal_pairs"] = dict(cells=cells, improved=improved, improved_by_seat=by_seat,
                                        other_cells_equal_cash=cells-improved, cash_delta_values=[0, 1])

    def test_exact_locked_start_witness_and_final_callback_drop(self):
        witnesses = []
        for seat in (0, 1):
            for start, target in (((5, 5), (3, 4)), ((4, 5), (2, 4))):
                before, _, _ = episode_tail(self.old_code, self.engine, seat, start, target)
                after, trace, report = episode_tail(self.new_code, self.engine, seat, start, target)
                self.assertEqual(before[0].observation.farms[seat]["money"], 3000)
                self.assertEqual(after[0].observation.farms[seat]["money"], 3001)
                self.assertEqual(report["collections"], 1)
                self.assertEqual(report["aborts"], 0)
                if target == (2, 4):
                    self.assertEqual(trace[-1]["action"]["hands"][0], ["DROP"])
                    self.assertEqual(trace[-1]["action"]["market"], [["SELL", "FERTILIZER", 100]])
                witnesses.append(dict(seat=seat, start=start, target=target,
                                      old_cash=3000, new_cash=3001, trace=trace))
        REPORT["witnesses"] = witnesses

    def test_unchanged_plan_price_time_stock_and_parent_guards(self):
        cases = ("plan", "price", "time", "stock", "busy", "pending", "purchase", "not_available")
        for label in cases:
            for code in (self.old_code, self.new_code):
                ns = namespace(code, self.engine)
                state, env = fixture(self.engine)
                obs = state[0].observation
                policy = ns["_POLICY"].players[0]
                tape = ns["_POLICY"].tapes[2]
                if label == "plan": policy.plan = 1
                elif label == "price": obs.market["prices"]["FERTILIZER"] = 2
                elif label == "time": policy.last_step = 713
                elif label == "stock": obs.private["shed"]["CARROT"] = 100
                elif label == "busy": tape[714]["hands"] = [["NORTH"]]
                elif label == "pending": policy.queues = {1: [["NORTH"]]}
                elif label == "purchase": tape[714]["market"] = [["BUY_PRODUCT", "WHEAT", 1]]
                elif label == "not_available": obs.farms[0]["tiles"][4][3]["fertilizer_available"] = False
                self.assertIsNone(ns["_v218_plan"](obs, tape[712]), label)

    def test_cli_never_overwrites(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / "source.py", Path(folder) / "candidate.py"
            source.write_bytes(self.raw)
            command = [sys.executable, str(HERE / "v218_movement_parity.py"), str(source)]
            self.assertEqual(subprocess.run(command + [str(source)], capture_output=True).returncode, 2)
            output.write_text("KEEP")
            self.assertEqual(subprocess.run(command + [str(output)], capture_output=True).returncode, 2)
            self.assertEqual(output.read_text(), "KEEP")
            output.unlink()
            self.assertEqual(subprocess.run(command + [str(output)], capture_output=True).returncode, 0)
            self.assertEqual(output.read_bytes(), self.raw)
            self.assertEqual(source.read_bytes(), self.raw)

    def test_inputs_unchanged(self):
        self.assertEqual(self.router.read_bytes(), self.raw)
        self.assertEqual(repair.git_blob(self.engine_path.read_bytes()), repair.ENGINE_BLOB)

if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(MovementParityTests))
    REPORT.update(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                  skipped=len(result.skipped), optimized=not __debug__)
    print(json.dumps(REPORT, sort_keys=True, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
