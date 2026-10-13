"""Real-binary initialization checks; no official benchmark or checker claims.

Build solver first, or set ROADEF_SOLVER to an alternate compiled revision.
The three-node witness has load 10 on the direct route and load 1 on each
of the two links selected by waypoint 1.
"""

import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SOLVER = Path(os.environ.get("ROADEF_SOLVER", Path(__file__).with_name("solver"))).resolve()


class IncumbentPreservation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.network = {
            "nodes": [{"id": i} for i in range(3)],
            "links": [
                {"id": i, "from": a, "to": b, "metric": 1, "capacity": cap}
                for i, (a, b, cap) in enumerate([(0, 2, 1), (0, 1, 10), (1, 2, 10)])
            ],
        }
        self.traffic = {"num_time_slots": 1, "demands": [{"s": 0, "t": 2, "v": [10]}]}
        self.scenario = {"max_segments": 2, "budget": [], "interventions": []}
        self.incumbent = {"srpaths": [{"d": 0, "t": 0, "w": [1]}]}
        self.source = self.root / "incumbent.json"
        self.output = self.root / "result.json"
        self.source.write_text(json.dumps(self.incumbent))

    def run_solver(self, *, source=None, output=None, resume=True, rounds=0, seconds=30):
        inputs = []
        for name, value in [("net", self.network), ("tm", self.traffic), ("scenario", self.scenario)]:
            path = self.root / f"{name}.json"
            path.write_text(json.dumps(value))
            inputs.append(str(path))
        env = dict(os.environ)
        env.pop("CLOUD_INITIAL_SOLUTION", None)
        if resume:
            env["CLOUD_INITIAL_SOLUTION"] = str(source or self.source)
        env.update(SEDGE_MAX_ROUNDS=str(rounds), SEDGE_SECONDS=str(seconds),
                   SEDGE_STATS=str(self.root / "stats.json"))
        return subprocess.run([str(SOLVER), *inputs, str(output or self.output)],
                              cwd=self.root, env=env, capture_output=True, text=True, timeout=10)

    def assert_incumbent(self, output, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(output.read_text()), self.incumbent)
        stats = json.loads((self.root / "stats.json").read_text())
        self.assertTrue(stats["resumed"])
        self.assertEqual(stats["initial_mlu"], 1)
        self.assertEqual(stats["final_mlu"], 1)

    def test_same_path_zero_rounds_retains_loaded_routes(self):
        self.assert_incumbent(self.source, self.run_solver(output=self.source))

    def test_relative_and_absolute_aliases_retain_loaded_routes(self):
        self.assert_incumbent(self.source, self.run_solver(source=Path("incumbent.json"), output=self.source))

    def test_incumbent_symlink_to_output_retains_loaded_routes(self):
        alias = self.root / "alias.json"
        alias.symlink_to(self.source)
        self.assert_incumbent(self.source, self.run_solver(source=alias, output=self.source))
        self.assertTrue(alias.is_symlink())

    def test_output_symlink_keeps_original_incumbent(self):
        self.output.symlink_to(self.source)
        before = self.source.read_bytes()
        self.assert_incumbent(self.output, self.run_solver())
        self.assertEqual(self.source.read_bytes(), before)

    def test_hardlink_output_keeps_original_incumbent(self):
        self.output.hardlink_to(self.source)
        before = self.source.read_bytes()
        self.assert_incumbent(self.output, self.run_solver())
        self.assertEqual(self.source.read_bytes(), before)

    def test_distinct_output_retains_incumbent_and_input_bytes(self):
        before = self.source.read_bytes()
        self.assert_incumbent(self.output, self.run_solver())
        self.assertEqual(self.source.read_bytes(), before)

    def test_zero_seconds_still_publishes_validated_incumbent(self):
        self.assert_incumbent(self.source, self.run_solver(output=self.source, seconds=0))

    def test_fixed_round_search_matches_distinct_output(self):
        self.assert_incumbent(self.output, self.run_solver(rounds=4))
        distinct = self.output.read_bytes()
        self.assert_incumbent(self.source, self.run_solver(output=self.source, rounds=4))
        self.assertEqual(self.source.read_bytes(), distinct)

    def test_malformed_inplace_input_is_rejected_without_overwrite(self):
        self.source.write_bytes(b"{not JSON\n")
        before = self.source.read_bytes()
        result = self.run_solver(output=self.source)
        with self.subTest("reject"):
            self.assertNotEqual(result.returncode, 0)
        with self.subTest("preserve"):
            self.assertEqual(self.source.read_bytes(), before)

    def test_invalid_incumbents_preserve_existing_output(self):
        invalid = {
            "missing array": {},
            "unknown waypoint": {"srpaths": [{"d": 0, "t": 0, "w": [99]}]},
            "bad demand": {"srpaths": [{"d": 1, "t": 0, "w": [1]}]},
            "bad slot": {"srpaths": [{"d": 0, "t": 1, "w": [1]}]},
            "endpoint": {"srpaths": [{"d": 0, "t": 0, "w": [0]}]},
            "too many segments": {"srpaths": [{"d": 0, "t": 0, "w": [1, 1]}]},
            "duplicate index": {"srpaths": self.incumbent["srpaths"] * 2},
        }
        for label, candidate in invalid.items():
            with self.subTest(case=label):
                self.source.write_text(json.dumps(candidate))
                self.output.write_bytes(b"previous result must survive\n")
                before = self.output.read_bytes()
                result = self.run_solver()
                self.assertNotEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.output.read_bytes(), before)

    def test_transition_budget_rejection_preserves_output(self):
        self.traffic["num_time_slots"] = 2
        self.traffic["demands"][0]["v"] = [10, 10]
        self.scenario["budget"] = [{"t": 1, "value": 0}]
        self.output.write_bytes(b"prior solution\n")
        result = self.run_solver()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("transition budget", result.stderr)
        self.assertEqual(self.output.read_bytes(), b"prior solution\n")

    def test_missing_incumbent_does_not_create_output(self):
        self.source.unlink()
        result = self.run_solver()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_unreachable_initialization_preserves_output(self):
        self.network["links"] = [copy.deepcopy(self.network["links"][1])]
        self.output.write_bytes(b"prior solution\n")
        result = self.run_solver(resume=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unreachable", result.stderr)
        self.assertEqual(self.output.read_bytes(), b"prior solution\n")

    def test_nonresumed_initialization_still_writes_default_routes(self):
        result = self.run_solver(resume=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.output.read_text()), {"srpaths": []})
        stats = json.loads((self.root / "stats.json").read_text())
        self.assertFalse(stats["resumed"])
        self.assertEqual(stats["initial_mlu"], 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
