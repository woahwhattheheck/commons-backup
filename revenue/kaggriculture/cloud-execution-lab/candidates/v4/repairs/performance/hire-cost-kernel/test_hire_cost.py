# SPDX-License-Identifier: Apache-2.0
"""Offline kernel, composition and full-interpreter differential tests.

TITAN_RUNTIME must point to an unpacked, authenticated source archive. A mutant
source can be supplied through HIRE_COST_MUTANT_FILE for behavioral gates only.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import importlib.util
import itertools
import json
import os
from pathlib import Path
import sys
import types
import unittest
from compose_hire_cost import AFTER, BEFORE, DECLARATION, TABLE, SourceDriftError, compose_source

ROOT = Path(os.environ["TITAN_RUNTIME"]).resolve()
SOURCE = (ROOT / "mechanics.py").read_text()
ENGINE_SHA = "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e"
COUNTS = {"scalar_comparisons": 0, "hire_cost_comparisons": 0,
          "hire_transition_pairs": 0, "full_interpreter_pairs": 0}


def module(name, text):
    value = types.ModuleType(name)
    exec(compile(text, name, "exec"), value.__dict__)
    return value


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


BASE = module("hire_cost_baseline", SOURCE)
STAGED = compose_source(SOURCE)
if os.environ.get("HIRE_COST_MUTANT_FILE"):
    STAGED = Path(os.environ["HIRE_COST_MUTANT_FILE"]).read_text()
CAND = module("hire_cost_candidate", STAGED)
ENGINE_DIR = ROOT / "checks/reference/engine"
if hashlib.sha256((ENGINE_DIR / "kaggriculture.py").read_bytes()).hexdigest() != ENGINE_SHA:
    raise RuntimeError("official engine source drift")
for name in ("kaggriculture.py", "kaggriculture.json", "utils.py"):
    if not (ENGINE_DIR / name).is_file():
        raise RuntimeError("missing offline engine cache: " + name)
LOADER = load("hire_cost_pinned_loader", ROOT / "checks/reference/evaluator/loader.py")
ENGINE, ENGINE_HASHES = LOADER.get_engine(ENGINE_DIR)


def encoded(value):
    # Compare mapping insertion order as well as values.
    return json.dumps(value, separators=(",", ":"), allow_nan=False)


def segments(text):
    lines = text.splitlines(keepends=True)
    return {n.name: "".join(lines[n.lineno-1:n.end_lineno])
            for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)}


def fresh(seed=9600911, size=10, mult=1, cap=10):
    S = LOADER.Struct
    cfg = S({k: v.get("default") if isinstance(v, dict) else v
             for k, v in ENGINE.specification["configuration"].items()})
    cfg.update(seed=seed, boardSize=size, farmHandCostMult=mult, maxMarketOrdersPerTurn=cap)
    env = S(configuration=cfg, done=False, info={})
    state = [S(observation=S(), action={}, status="ACTIVE", reward=0) for _ in range(2)]
    ENGINE.interpreter(state, env)
    return state, env


class ContractTests(unittest.TestCase):
    def test_method_preimage_and_postimage(self):
        for text, expected in ((SOURCE, BEFORE), (compose_source(SOURCE), AFTER)):
            self.assertEqual(hashlib.sha256(segments(text)["_fib"].encode()).hexdigest(), expected)

    def test_idempotent(self):
        self.assertEqual(compose_source(compose_source(SOURCE)), compose_source(SOURCE))

    def test_every_other_function_unchanged(self):
        before, after = segments(SOURCE), segments(compose_source(SOURCE))
        del before["_fib"]; del after["_fib"]
        self.assertEqual(before, after)

    def test_disjoint_peer_changes_survive(self):
        text = SOURCE.replace("HINGE_GAIN = 8.0", "HINGE_GAIN = 7.99")
        text += "\n# peer geometry and quote source must survive\nPEER_SENTINEL = ('quote', 'geometry')\n"
        result = compose_source(text)
        self.assertIn("HINGE_GAIN = 7.99", result)
        self.assertTrue(result.endswith("PEER_SENTINEL = ('quote', 'geometry')\n"))
        self.assertEqual(segments(text)["_spawn_hand"], segments(result)["_spawn_hand"])
        self.assertEqual(segments(text)["market_price"], segments(result)["market_price"])

    def test_method_drift_missing_duplicate_decorator_and_crlf(self):
        variants = [SOURCE.replace("for _ in range(n):", "for _ in range(n+1):"),
                    SOURCE.replace("def _fib(n):", "def renamed_fib(n):"),
                    SOURCE + "\ndef _fib(n):\n    return n\n",
                    SOURCE.replace("def _fib(n):", "@anything\ndef _fib(n):"),
                    SOURCE.replace("\n", "\r\n"), "def broken("]
        for text in variants:
            with self.subTest(suffix=text[-40:]):
                with self.assertRaises(SourceDriftError):
                    compose_source(text)
        with self.assertRaises(TypeError):
            compose_source(b"not decoded")

    def test_preexisting_table_collision_rejected(self):
        for suffix in ("_TITAN_HIRE_FIB64 = ()", "import math as _TITAN_HIRE_FIB64",
                       "def _TITAN_HIRE_FIB64():\n    return 1"):
            with self.subTest(suffix=suffix):
                with self.assertRaises(SourceDriftError):
                    compose_source(SOURCE + "\n" + suffix + "\n")

    def test_corrupt_missing_rebound_deleted_table_rejected(self):
        composed = compose_source(SOURCE)
        for text in (composed.replace(DECLARATION, ""),
                     composed.replace(DECLARATION, "_TITAN_HIRE_FIB64 = (1,)\n\n"),
                     composed + "\n_TITAN_HIRE_FIB64 = ()\n",
                     composed + "\ndel _TITAN_HIRE_FIB64\n",
                     composed + "\nimport math as _TITAN_HIRE_FIB64\n",
                     composed + "\ndef _TITAN_HIRE_FIB64():\n    pass\n"):
            with self.subTest(suffix=text[-50:]):
                with self.assertRaises(SourceDriftError):
                    compose_source(text)

    def test_fixed_table_independent_recurrence(self):
        a, b = 1, 1
        expected = []
        for _ in range(64):
            expected.append(a); a, b = b, a + b
        self.assertEqual(tuple(expected), TABLE)
        self.assertEqual(len(TABLE), 64)
        self.assertTrue(all(type(n) is int for n in TABLE))

    def test_official_predecessor_asts_match(self):
        names = ("_fib", "_hire_cost", "_do_hire")
        def selected(text):
            return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(text).body
                    if isinstance(n, ast.FunctionDef) and n.name in names}
        self.assertEqual(selected(SOURCE), selected((ENGINE_DIR / "kaggriculture.py").read_text()))


class BehaviorTests(unittest.TestCase):
    def same_scalar(self, value):
        try:
            left = ENGINE._fib(value); le = None
        except Exception as exc:
            left = None; le = (type(exc), str(exc))
        try:
            right = CAND._fib(value); re = None
        except Exception as exc:
            right = None; re = (type(exc), str(exc))
        self.assertEqual(le, re)
        self.assertEqual(left, right)
        self.assertIs(type(left), type(right))
        COUNTS["scalar_comparisons"] += 1

    def test_lookup_boundary_negative_and_large_exact_integers(self):
        for n in list(range(-256, 513)) + [-10**100, 1024, 4096, 10000]:
            with self.subTest(n=n):
                self.same_scalar(n)

    def test_boolean_and_int_subclass_original_semantics(self):
        class OddInt(int):
            def __lt__(self, other):
                raise AssertionError("comparison must not replace range(n)")
            def __ge__(self, other):
                raise AssertionError("comparison must not replace range(n)")
            def __index__(self):
                return 17
        for n in (False, True, OddInt(-3), OddInt(0), OddInt(7), OddInt(63), OddInt(64)):
            self.same_scalar(n)

    def test_index_protocol_and_side_effect_count(self):
        class Indexed:
            def __init__(self, value): self.value, self.calls = value, 0
            def __index__(self): self.calls += 1; return self.value
        for n in (-9, 0, 2, 63, 64, 128):
            a, b = Indexed(n), Indexed(n)
            self.assertEqual(ENGINE._fib(a), CAND._fib(b))
            self.assertEqual((a.calls, b.calls), (1, 1))
            COUNTS["scalar_comparisons"] += 1

    def test_unsupported_inputs_preserve_error_class_and_message(self):
        class BadIndex:
            def __index__(self): return 1.5
        for n in (None, 0.0, 1.0, 3.75, float("inf"), float("nan"), "3", [], {}, BadIndex()):
            with self.subTest(kind=type(n).__name__):
                self.same_scalar(n)

    def test_hire_cost_integer_money_and_multiplier_matrix(self):
        for n, mult in itertools.product(range(-4, 131), (-3, 0, 1, 3, 7, 10**15, 10**80)):
            expected, actual = ENGINE._hire_cost(n, mult), CAND._hire_cost(n, mult)
            self.assertEqual(expected, actual)
            self.assertIs(type(actual), int)
            COUNTS["hire_cost_comparisons"] += 1

    def test_float_multiplier_stays_original_arithmetic(self):
        for n, mult in itertools.product((0, 1, 2, 10, 63, 64, 128), (0.0, 0.1, 1.5, float("inf"))):
            self.assertEqual(ENGINE._hire_cost(n, mult), CAND._hire_cost(n, mult))
            self.assertIs(type(CAND._hire_cost(n, mult)), float)
            COUNTS["hire_cost_comparisons"] += 1

    def test_no_mutable_cache_or_game_state_growth(self):
        table = CAND._TITAN_HIRE_FIB64
        before = dict(vars(CAND))
        for n in range(-5, 300): CAND._fib(n)
        self.assertIs(CAND._TITAN_HIRE_FIB64, table)
        self.assertIs(type(table), tuple)
        self.assertEqual(vars(CAND), before)

    def test_actual_hire_transition_affordability_spawn_and_aliases(self):
        for n, mult, delta, size in itertools.product((0, 1, 2, 5, 12, 63, 64, 128), (1, 3), (-1, 0, 1), (6, 10)):
            state, _ = fresh(size=size, mult=mult)
            farm = state[0].observation.farms[0]
            private = state[0].observation.private
            cost = ENGINE._hire_cost(n, mult)
            farm.update(money=cost + delta, hires_today=n)
            a, pa = copy.deepcopy((farm, private)); b, pb = copy.deepcopy((farm, private))
            hands, invs = b["hands"], pb["inventories"]
            ENGINE._do_hire(a, pa, size, mult); CAND._do_hire(b, pb, size, mult)
            self.assertEqual(encoded((a, pa)), encoded((b, pb)))
            self.assertIs(b["hands"], hands); self.assertIs(pb["inventories"], invs)
            COUNTS["hire_transition_pairs"] += 1


class InterpreterTests(unittest.TestCase):
    def test_complete_turns_both_seats_caps_and_eod(self):
        # Direct interpreter calls preserve units, raw empty market slots, hire
        # affordability, private inventory, town, spawning, and day-end reset.
        for seat, n, mult, delta, eod, cap in itertools.product(
                (0, 1), (0, 1, 8, 20, 63, 64), (1, 3), (-1, 0, 1), (False, True), (1, 3)):
            state, env = fresh(mult=mult, cap=cap)
            cost = ENGINE._hire_cost(n, mult)
            state[0].observation.farms[seat].update(money=cost + delta, hires_today=n)
            for s in state:
                s.observation.step = 23 if eod else 10
                s.action = {"farmer": ["PASS"], "hands": [], "market": []}
            state[seat].action["market"] = [["HIRE"], [], ["HIRE"], ["HIRE"]]
            a, ea = copy.deepcopy((state, env)); b, eb = copy.deepcopy((state, env))
            ENGINE.interpreter(a, ea)
            original = ENGINE._fib
            try:
                ENGINE._fib = CAND._fib
                ENGINE.interpreter(b, eb)
            finally:
                ENGINE._fib = original
            self.assertEqual(encoded(a), encoded(b)); self.assertEqual(encoded(ea), encoded(eb))
            COUNTS["full_interpreter_pairs"] += 1


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2)
    print("CASE_COUNTS " + json.dumps(COUNTS, sort_keys=True))
    sys.exit(not result.result.wasSuccessful())
