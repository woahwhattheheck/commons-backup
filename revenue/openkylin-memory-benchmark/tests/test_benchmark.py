import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import kylin_memory_bench as bench


class BenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = bench._read_dataset(ROOT / "sample" / "dataset.jsonl")
        cls.ids = {row["id"] for row in cls.dataset}
        cls.reference = bench._load_evidence(ROOT / "sample" / "reference-agent.json", cls.ids)
        cls.forgetful = bench._load_evidence(ROOT / "sample" / "forgetful-agent.json", cls.ids)

    def test_dataset_covers_exact_required_dimensions(self):
        self.assertEqual({row["dimension"] for row in self.dataset}, set(bench.DIMENSIONS))

    def test_reference_agent_scores_100(self):
        report = bench.score(self.dataset, self.reference)
        self.assertEqual(report["overall"], 100.0)
        self.assertTrue(all(score == 100.0 for score in report["dimensions"].values()))

    def test_forgetful_agent_fails_every_dimension(self):
        report = bench.score(self.dataset, self.forgetful)
        self.assertLess(report["overall"], 50.0)
        self.assertTrue(all(score < 100.0 for score in report["dimensions"].values()))
        failures = [a for s in report["scenarios"] for a in s["assertions"] if not a["passed"]]
        self.assertGreaterEqual(len(failures), 6)
        self.assertTrue(all(a["reason"] for a in failures))

    def test_unknown_channel_is_rejected(self):
        bad = json.loads(json.dumps(self.reference))
        bad["records"][0]["channels"]["browser"] = []
        with self.assertRaisesRegex(ValueError, "unknown channels"):
            bench.validate_evidence(bad, self.ids)

    def test_duplicate_scenario_record_is_rejected(self):
        bad = json.loads(json.dumps(self.reference))
        bad["records"].append(bad["records"][0])
        with self.assertRaisesRegex(ValueError, "duplicate evidence record"):
            bench.validate_evidence(bad, self.ids)

    def test_nonfinite_or_boolean_weight_is_rejected(self):
        for value in (True, float("inf"), 0, -1):
            with self.subTest(value=value):
                bad = json.loads(json.dumps(self.dataset))
                bad[0]["assertions"][0]["weight"] = value
                with self.assertRaises(ValueError):
                    bench.validate_dataset(bad)

    def test_compare_cli_writes_explainable_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            cmd = [
                sys.executable, str(ROOT / "kylin_memory_bench.py"), "compare",
                "--dataset", str(ROOT / "sample" / "dataset.jsonl"),
                "--evidence", str(ROOT / "sample" / "reference-agent.json"),
                "--evidence", str(ROOT / "sample" / "forgetful-agent.json"),
                "--out-dir", tmp,
            ]
            proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = json.loads(proc.stdout)
            self.assertEqual(result["reference-agent"], 100.0)
            self.assertLess(result["forgetful-agent"], 50.0)
            out = Path(tmp)
            self.assertTrue((out / "comparison.json").is_file())
            self.assertIn("<svg", (out / "radar.svg").read_text(encoding="utf-8"))
            self.assertIn("**FAIL**", (out / "forgetful-agent.report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
