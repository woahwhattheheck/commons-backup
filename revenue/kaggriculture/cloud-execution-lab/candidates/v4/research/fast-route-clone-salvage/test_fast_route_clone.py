#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import time
import unittest

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

repair = load("fast_route_clone_repair", HERE / "fast_route_clone.py")
RUNTIME = None


def candidate_helpers(candidate: bytes):
    tree = ast.parse(candidate.decode("utf-8"))
    keep = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_ROUTE_JSON_SCALARS" for t in node.targets):
            keep.append(node)
        if isinstance(node, ast.FunctionDef) and node.name in {"_is_fast_route_action", "_clone_route_action"}:
            keep.append(node)
    module = ast.Module(body=keep, type_ignores=[])
    ast.fix_missing_locations(module)
    ns = {"deepcopy": copy.deepcopy}
    exec(compile(module, "<clone-helpers>", "exec"), ns)
    return ns["_is_fast_route_action"], ns["_clone_route_action"]


class FastRouteCloneTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if RUNTIME is None:
            raise unittest.SkipTest("runtime not supplied")
        cls.runtime = RUNTIME
        cls.source = (cls.runtime / "integrated_selected.py").read_bytes()
        cls.candidate = repair.materialize_bytes(cls.source)
        is_fast, clone = candidate_helpers(cls.candidate)
        cls.is_fast = staticmethod(is_fast)
        cls.clone = staticmethod(clone)
        sys.path.insert(0, str(cls.runtime))
        cls.integrated = load("_fast_clone_integrated", cls.runtime / "integrated_selected.py")
        cls.production = cls.integrated.make_production()
        cls.routes = cls.production.agent.R

    @classmethod
    def tearDownClass(cls):
        if RUNTIME is not None and sys.path and sys.path[0] == str(RUNTIME):
            sys.path.pop(0)

    def test_source_and_current_default_reachability(self):
        self.assertEqual(repair.git_blob(self.source), repair.SOURCE_GIT_BLOB)
        cfg = json.loads((self.runtime / "TITAN-CONFIG.json").read_text())
        self.assertEqual(cfg.get("consumer"), "frozen")
        # This exact callsite belongs to the ordered consumer and is cold under the current default.
        runtime = (self.runtime / "titan_runtime.py").read_text()
        self.assertIn("if f.consumer == 'ordered':", runtime)
        self.assertIn("from integrated_selected import IntegratedSelectedAgent", runtime)

    def test_materializer_exactly_one_callsite_and_compiles(self):
        before = self.source.decode()
        after = self.candidate.decode()
        self.assertEqual(before.count(repair.CLONE_PREIMAGE), 1)
        self.assertEqual(after.count(repair.CLONE_POSTIMAGE), 1)
        self.assertNotIn(repair.CLONE_PREIMAGE, after)
        self.assertEqual(after.count("def _clone_route_action("), 1)

    def test_all_current_route_actions_equal_deepcopy_and_alias_safe(self):
        count = 0
        self.assertEqual(len(self.routes), 4)
        for route_id, tape in self.routes.items():
            self.assertEqual(len(tape), 720)
            for step, template in enumerate(tape):
                with self.subTest(route=route_id, step=step):
                    snapshot = copy.deepcopy(template)
                    self.assertTrue(self.is_fast(template))
                    got = self.clone(template)
                    self.assertEqual(got, snapshot)
                    self.assertIsNot(got, template)
                    self.assertIsNot(got["farmer"], template["farmer"])
                    self.assertIsNot(got["hands"], template["hands"])
                    self.assertIsNot(got["market"], template["market"])
                    for left, right in zip(got["hands"], template["hands"]):
                        self.assertIsNot(left, right)
                    for left, right in zip(got["market"], template["market"]):
                        self.assertIsNot(left, right)
                    got["farmer"].append("__probe__")
                    if got["hands"]:
                        got["hands"][0].append("__probe__")
                    if got["market"]:
                        got["market"][0].append("__probe__")
                    self.assertEqual(template, snapshot)
                    count += 1
        self.assertEqual(count, 2880)

    def test_future_schema_fails_closed_to_real_deepcopy(self):
        cases = [
            {"farmer": ["PASS"], "hands": [], "market": [], "future": {"x": [1]}},
            {"farmer": ["PASS", {"future": [1]}], "hands": [], "market": []},
            {"farmer": ["PASS"], "hands": [["PASS", {"x": 1}]], "market": []},
            {"farmer": ["PASS"], "hands": [], "market": [("SELL", "WOOL", 1)]},
        ]
        for value in cases:
            snapshot = copy.deepcopy(value)
            self.assertFalse(self.is_fast(value))
            got = self.clone(value)
            self.assertEqual(got, snapshot)
            self.assertIsNot(got, value)

    def test_source_drift_fails_closed(self):
        with self.assertRaises(repair.MaterializationError):
            repair.materialize_bytes(self.source + b"\n# drift\n")


def benchmark(runtime: Path, repeats=5, loops=2):
    sys.path.insert(0, str(runtime))
    try:
        integrated = load("_fast_clone_bench_integrated", runtime / "integrated_selected.py")
        rows = [a for tape in integrated.make_production().agent.R.values() for a in tape]
    finally:
        sys.path.pop(0)
    candidate = repair.materialize_bytes((runtime / "integrated_selected.py").read_bytes())
    _, clone = candidate_helpers(candidate)
    out = {}
    for name, fn in (("deepcopy", copy.deepcopy), ("fast_clone", clone)):
        samples=[]
        for _ in range(repeats):
            start=time.perf_counter_ns()
            for _ in range(loops):
                [fn(row) for row in rows]
            samples.append((time.perf_counter_ns()-start)/1e6)
        out[name] = {"median_ms": statistics.median(samples), "samples_ms": samples}
    out["speedup"] = out["deepcopy"]["median_ms"] / out["fast_clone"]["median_ms"]
    out["rows_per_sample"] = len(rows)*loops
    return out


def main():
    global RUNTIME
    p=argparse.ArgumentParser()
    p.add_argument("--runtime", type=Path, required=True)
    p.add_argument("--receipt", type=Path)
    args, rest=p.parse_known_args()
    RUNTIME=args.runtime.resolve()
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(FastRouteCloneTest)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    bench=benchmark(RUNTIME)
    receipt={
        "schema":"titan-v4-fast-route-clone-salvage/v1",
        "artifact_id":10175943272,
        "artifact_zip_sha256":"3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8",
        "source_manifest_sha256":hashlib.sha256((RUNTIME/"SOURCE.json").read_bytes()).hexdigest(),
        "integrated_selected_git_blob":repair.git_blob((RUNTIME/"integrated_selected.py").read_bytes()),
        "routes":4,
        "route_actions":2880,
        "current_default_consumer":json.loads((RUNTIME/"TITAN-CONFIG.json").read_text()).get("consumer"),
        "current_default_reachable":False,
        "tests":{"mode":"optimized" if sys.flags.optimize else "normal","count":5,"failures":0,"errors":0},
        "benchmark":bench,
        "disposition":"SOURCE_ONLY_COLD_DEFAULT; do not activate/change consumer from this evidence",
    }
    if args.receipt:
        args.receipt.write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    print(json.dumps(receipt,sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
