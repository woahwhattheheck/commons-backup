import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "kylin_memory_bench.py"
RUN_DEMO = ROOT / "run_demo.sh"
DATASET = ROOT / "sample" / "dataset.jsonl"
REFERENCE = ROOT / "sample" / "reference-agent.json"


class CompareContractTests(unittest.TestCase):
    def _run(self, evidence_paths, out_dir):
        cmd = [
            sys.executable,
            str(CLI),
            "compare",
            "--dataset",
            str(DATASET),
        ]
        for path in evidence_paths:
            cmd.extend(["--evidence", str(path)])
        cmd.extend(["--out-dir", str(out_dir)])
        return subprocess.run(cmd, text=True, capture_output=True, check=False)

    def test_compare_requires_at_least_two_evidence_bundles(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "out"
            proc = self._run([REFERENCE], out_dir)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("at least two evidence bundles", proc.stderr)
            self.assertFalse(out_dir.exists())

    def test_compare_rejects_duplicate_agent_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "out"
            proc = self._run([REFERENCE, REFERENCE], out_dir)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("agent names must be unique", proc.stderr)
            self.assertFalse(out_dir.exists())

    def test_compare_rejects_output_slug_collision_before_writing(self):
        payload = json.loads(REFERENCE.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            left = tmp_path / "left.json"
            right = tmp_path / "right.json"
            out_dir = tmp_path / "out"
            left_payload = json.loads(json.dumps(payload))
            right_payload = json.loads(json.dumps(payload))
            left_payload["agent"] = "agent one"
            right_payload["agent"] = "agent-one"
            left.write_text(json.dumps(left_payload), encoding="utf-8")
            right.write_text(json.dumps(right_payload), encoding="utf-8")
            proc = self._run([left, right], out_dir)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("output names collide after sanitization", proc.stderr)
            self.assertFalse(out_dir.exists())

    def test_compare_rejects_case_insensitive_slug_collision_before_writing(self):
        payload = json.loads(REFERENCE.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            upper = tmp_path / "upper.json"
            lower = tmp_path / "lower.json"
            out_dir = tmp_path / "out"
            upper_payload = json.loads(json.dumps(payload))
            lower_payload = json.loads(json.dumps(payload))
            upper_payload["agent"] = "Agent"
            lower_payload["agent"] = "agent"
            upper.write_text(json.dumps(upper_payload), encoding="utf-8")
            lower.write_text(json.dumps(lower_payload), encoding="utf-8")
            proc = self._run([upper, lower], out_dir)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("output names collide after sanitization", proc.stderr)
            self.assertFalse(out_dir.exists())

    def test_documented_demo_runner_is_executable(self):
        self.assertTrue(
            RUN_DEMO.stat().st_mode & 0o111,
            "run_demo.sh must remain executable because README documents ./run_demo.sh",
        )


if __name__ == "__main__":
    unittest.main()
