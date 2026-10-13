# SPDX-License-Identifier: Apache-2.0
"""Exact-source and official-engine discriminators; supports Python -O."""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys
import types
import unittest
from compose_geometry import compose, BEFORE, AFTER, CORNERS

RUNTIME = None
MUTANT = None
MUTANTS = {
    "missing_se_corner": ("frozenset(_shed_access_tiles(board_size))", "frozenset(_shed_access_tiles(board_size)[:-1])"),
    "fixed_board_size": ("frozenset(_shed_access_tiles(board_size))", "frozenset(_shed_access_tiles(10))"),
    "lost_vector_normalization": ("return tuple(pos) in _cached_shed_access(board_size)", "return pos in _cached_shed_access(board_size)"),
    "wrong_half_boundary": ("frozenset(_shed_access_tiles(board_size))", "frozenset(_shed_access_tiles(board_size+1))"),
    "mutable_geometry": ("frozenset(_shed_access_tiles(board_size))", "set(_shed_access_tiles(board_size))"),
    "unbounded_cache": ("maxsize=16, typed=True", "maxsize=None, typed=True"),
}
REPORT = {"membership_cases": 0, "unit_cases": 0, "interpreter_pairs": 0}


def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def module(name, source):
    result = types.ModuleType(name)
    exec(compile(source, name, "exec"), result.__dict__)
    return result


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class GeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (RUNTIME / "mechanics.py").read_text()
        if blob(cls.source.encode()) != "044a4f9c0a4a44dde10ada57563238bcaf82075d":
            raise ValueError("This receipt requires the authenticated native mechanics")
        ep = RUNTIME / "checks/reference/engine/kaggriculture.py"
        engine_pins = {
            "kaggriculture.py": "3c202c7ee921da239356789e266b694635103fc4",
            "kaggriculture.json": "b354d06b742fe48402513792253f1a5c29366b20",
            "utils.py": "91c8822ee6201ba4a5a8416c7dbe34f95dd61c87",
        }
        for name, expected in engine_pins.items():
            if blob((ep.parent / name).read_bytes()) != expected:
                raise ValueError("Official engine pin mismatch: " + name)
        loader = load(RUNTIME / "checks/reference/evaluator/loader.py", "geometry_loader")
        cls.engine, _ = loader.get_engine(ep.parent)
        cls.Struct = loader.Struct
        cls.old = module("old_mechanics", cls.source)
        candidate = compose(cls.source)
        if MUTANT:
            before, after = MUTANTS[MUTANT]
            if candidate.count(before) != 1: raise ValueError("Mutant anchor changed")
            candidate = candidate.replace(before, after, 1)
        cls.new = module("new_mechanics", candidate)
        REPORT["mechanics_blob"] = blob(cls.source.encode())
        REPORT["candidate_blob"] = blob(compose(cls.source).encode())
        REPORT["executed_candidate_blob"] = blob(candidate.encode())
        REPORT["engine_blob"] = blob(ep.read_bytes())

    def test_only_membership_seam_changes(self):
        self.assertEqual(compose(self.source).replace(AFTER, BEFORE, 1), self.source)

    def test_unrelated_source_is_preserved(self):
        extra = self.source + "\n# Independent quote-kernel composition marker\n"
        self.assertEqual(compose(extra).replace(AFTER, BEFORE, 1), extra)

    def test_changed_and_duplicate_sources_rejected(self):
        for text in (self.source.replace(CORNERS, CORNERS.replace("half = board_size // 2", "half = 0")),
                     self.source.replace(BEFORE, BEFORE + "\n" + BEFORE),
                     self.source.replace(CORNERS, CORNERS + "\n" + CORNERS),
                     compose(self.source), self.source + "\n_cached_shed_access = None\n"):
            with self.subTest(text=text[-40:]):
                with self.assertRaises(ValueError): compose(text)

    def test_exhaustive_membership_and_vector_shape(self):
        for size in range(-2, 33):
            for x in range(-3, 35):
                for y in range(-3, 35):
                    pos = [x, y]
                    self.assertEqual(self.new._is_shed_adjacent(pos, size),
                                     self.engine._is_shed_adjacent(pos, size))
                    REPORT["membership_cases"] += 1
        for pos in ([], [4], [4, 4, 4], (4, 4), [4.0, 4.0], [True, False], "44"):
            for size in (4, 5, 10, 10.0):
                self.assertEqual(self.new._is_shed_adjacent(pos, size),
                                 self.engine._is_shed_adjacent(pos, size))
        self.assertTrue(self.new._is_shed_adjacent(iter([4, 4]), 10))

    def test_geometry_is_immutable_and_bounded(self):
        f = self.new._cached_shed_access
        f.cache_clear()
        self.assertIsInstance(f(10), frozenset)
        with self.assertRaises(AttributeError): f(10).add((0, 0))
        for size in range(300): f(size)
        self.assertEqual(f.cache_info().maxsize, 16)
        self.assertLessEqual(f.cache_info().currsize, 16)
        f.cache_clear(); f(10); f(10.0)
        self.assertEqual(f.cache_info().currsize, 2)

    def test_public_corner_list_remains_detached(self):
        first = self.new._shed_access_tiles(10)
        first.clear()
        self.assertEqual(self.new._shed_access_tiles(10), self.engine._shed_access_tiles(10))
        self.assertTrue(self.new._is_shed_adjacent([5, 5], 10))

    def test_official_unit_action_matrix(self):
        rng = random.Random(991204)
        actions = [["DROP"], ["PICKUP", "WHEAT", 3], ["PICKUP", "FERTILIZER", 2],
                   ["PLACE", "WHEAT", 4], ["PLACE", "FERTILIZER", 1], ["PLACE", "COW"],
                   ["PLANT", "WHEAT"], ["WATER"], ["FEED"], ["CARE"], ["COLLECT"],
                   ["HARVEST"], ["FERTILIZE"], ["NORTH"], ["SOUTH"], ["EAST"], ["WEST"], ["PASS"]]
        for i in range(5000):
            size = rng.choice((4, 5, 6, 10, 12)); half = size // 2
            farm = self.engine._new_farm(size, 1000)
            positions = self.engine._shed_access_tiles(size) + [(0, 0), (size-1, size-1)]
            farm["farmer"] = list(rng.choice(positions))
            farm["hands"] = [list(rng.choice(positions)) for _ in range(2)]
            private = self.engine._new_private()
            private["shed"] = {"WHEAT": rng.randrange(6), "FERTILIZER": rng.randrange(4)}
            private["seeds"] = {"WHEAT": 20}
            private["inventories"] = [{"WHEAT": 3, "FERTILIZER": 2, "COW": 1} for _ in range(3)]
            idx = rng.randrange(3); pos = self.engine._farmer_position(farm, idx)
            tile = rng.choice(("LOCKED", "EMPTY", "PLANT", "COW", "PASTURE"))
            if tile == "PLANT": tile = self.engine._new_plant("WHEAT", 1, 24)
            elif tile == "COW": tile = self.engine._new_animal("COW", 1)
            elif tile == "PASTURE": tile = {"kind": "PASTURE"}
            farm["tiles"][pos[1]][pos[0]] = tile
            action = rng.choice(actions); capacity = rng.choice((0, 5, 10, 100))
            left, right = copy.deepcopy((farm, private)), copy.deepcopy((farm, private))
            self.engine._apply_unit_action(*left, idx, action, size, 5, 24, capacity)
            self.new._apply_unit_action(*right, idx, action, size, 5, 24, capacity)
            self.assertEqual(left, right, (i, size, idx, action))
            REPORT["unit_cases"] += 1

    def test_full_interpreter_geometry_substitution(self):
        e, S = self.engine, self.Struct
        original = e._is_shed_adjacent
        for seat in (0, 1):
            for size in (4, 6, 10):
                for step in (10, 23, 718):
                    for corner in e._shed_access_tiles(size):
                        for op in (["DROP"], ["PICKUP", "WHEAT", 3], ["PLACE", "FERTILIZER", 2]):
                            cfg = S({k: v.get("default") if isinstance(v, dict) else v
                                     for k, v in e.specification["configuration"].items()})
                            cfg.update(boardSize=size, weedSpawnChance=0)
                            farms = [e._new_farm(size, 500), e._new_farm(size, 500)]
                            farms[seat]["farmer"] = list(corner)
                            market = e._new_market(); e._refresh_prices(market)
                            states = []
                            for player in (0, 1):
                                private = e._new_private()
                                private["shed"] = {"WHEAT": 5, "FERTILIZER": 2}
                                private["inventories"] = [{"FERTILIZER": 2, "MILK": 3}]
                                states.append(S(observation=S(player=player, step=step, day=step//24,
                                    hour=step%24, farms=farms, private=private, market=market,
                                    town={"unlocked_shops": []}), action={"farmer": op if player==seat else ["PASS"],
                                    "hands": [], "market": []}, status="ACTIVE", reward=0))
                            env = S(configuration=cfg, done=False, info={"seed": 44112})
                            a, b = copy.deepcopy((states, env)), copy.deepcopy((states, env))
                            try:
                                e._is_shed_adjacent = original; e.interpreter(*a)
                                e._is_shed_adjacent = self.new._is_shed_adjacent; e.interpreter(*b)
                            finally: e._is_shed_adjacent = original
                            self.assertEqual(a, b, (seat, size, step, corner, op))
                            REPORT["interpreter_pairs"] += 1


def main():
    global RUNTIME, MUTANT
    p = argparse.ArgumentParser(); p.add_argument("--runtime", type=Path, required=True)
    p.add_argument("--report", type=Path); p.add_argument("--mutant", choices=sorted(MUTANTS))
    args = p.parse_args(); RUNTIME = args.runtime.resolve(); MUTANT = args.mutant
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(GeometryTests))
    REPORT.update(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors), optimized=not __debug__, mutant=MUTANT)
    if args.report: args.report.write_text(json.dumps(REPORT, indent=2) + "\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__": main()
