#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


def load(path: Path):
    spec = importlib.util.spec_from_file_location("rank1_builder", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class BuilderTests(unittest.TestCase):
    def test_inserts_once_and_preserves_normal_dispatch(self):
        source = "class X {\npublic:\n    void run() {\n}\n};\n" + self.mod.MAIN_OLD
        changed = self.mod.transform(source)
        self.assertEqual(changed.count(self.mod.MARKER), 1)
        self.assertIn('setting("FLEET_RANK1", 0) != 0', changed)
        self.assertIn("else solver.run();", changed)

    def test_reapplication_rejected(self):
        source = "class X {\npublic:\n    void run() {\n}\n};\n" + self.mod.MAIN_OLD
        with self.assertRaisesRegex(ValueError, "already"):
            self.mod.transform(self.mod.transform(source))

    def test_missing_and_duplicate_anchors_rejected(self):
        with self.assertRaisesRegex(ValueError, "run"):
            self.mod.transform(self.mod.MAIN_OLD)
        source = "\n    void run() {\n\n    void run() {\n" + self.mod.MAIN_OLD
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.mod.transform(source)

    def test_real_source_compiles(self):
        changed = self.mod.transform(self.source.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            cpp = Path(folder) / "main.cpp"
            binary = Path(folder) / "candidate"
            cpp.write_text(changed, encoding="utf-8")
            result = subprocess.run([
                "g++", "-std=c++20", "-O2", "-DNDEBUG", "-Wall", "-Wextra", "-Werror",
                "-I", str(self.vendor), str(cpp), "-o", str(binary)
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            invoked = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(invoked.returncode, 2)
            self.assertIn("Usage:", invoked.stderr)

            # Native opt-in smoke: one demand overloads a direct edge, while a
            # one-waypoint path has spare capacity. The new pass must use the
            # original move()/ECMP implementation, publish the route and stop
            # after the next deterministic no-change pass.
            net = Path(folder) / "net.json"
            traffic = Path(folder) / "tm.json"
            scenario = Path(folder) / "scenario.json"
            incumbent = Path(folder) / "incumbent.json"
            solution = Path(folder) / "solution.json"
            stats = Path(folder) / "stats.json"
            report = Path(folder) / "rank1.json"
            net.write_text(json.dumps({
                "nodes": [{"id": i} for i in range(4)],
                "links": [
                    {"id": 0, "from": 0, "to": 3, "metric": 1.0, "capacity": 1.0},
                    {"id": 1, "from": 0, "to": 1, "metric": 1.0, "capacity": 10.0},
                    {"id": 2, "from": 1, "to": 3, "metric": 1.0, "capacity": 10.0},
                    {"id": 3, "from": 0, "to": 2, "metric": 1.0, "capacity": 5.0},
                    {"id": 4, "from": 2, "to": 3, "metric": 1.0, "capacity": 5.0},
                ]}), encoding="utf-8")
            traffic.write_text(json.dumps({"num_time_slots": 1,
                "demands": [{"s": 0, "t": 3, "v": [2.0]}]}), encoding="utf-8")
            scenario.write_text(json.dumps({"max_segments": 3, "interventions": [],
                "budget": [{"t": 0, "value": 0}]}), encoding="utf-8")
            incumbent.write_text('{"srpaths":[]}\n', encoding="utf-8")
            environment = os.environ.copy()
            environment.update({
                "CLOUD_INITIAL_SOLUTION": str(incumbent), "SEDGE_SECONDS": "5",
                "SEDGE_STATS": str(stats), "FLEET_RANK1": "1",
                "FLEET_RANK1_REPORT": str(report), "FLEET_RANK1_PASSES": "4",
                "FLEET_RANK1_DEMANDS": "4", "FLEET_RANK1_PAIR_NODES": "4",
            })
            smoke = subprocess.run([str(binary), str(net), str(traffic), str(scenario), str(solution)],
                                   env=environment, capture_output=True, text=True)
            self.assertEqual(smoke.returncode, 0, smoke.stderr)
            self.assertEqual(json.loads(solution.read_text()),
                             {"srpaths": [{"d": 0, "t": 0, "w": [1]}]})
            measured = json.loads(stats.read_text())
            self.assertEqual(measured["initial_mlu"], 2)
            self.assertEqual(measured["final_mlu"], 0.2)
            trace = json.loads(report.read_text())
            self.assertEqual(trace["accepted"], 1)
            self.assertEqual(trace["passes"][0]["top_contributors"], [{"d": 0, "load": 2}])
            self.assertEqual(trace["passes"][1]["accepted"], 0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--builder", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--vendor", type=Path, required=True)
    args, rest = parser.parse_known_args()
    BuilderTests.mod = load(args.builder)
    BuilderTests.source = args.source
    BuilderTests.vendor = args.vendor
    unittest.main(argv=[__file__, *rest])
