#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
import os
import subprocess
import tempfile
import textwrap
import unittest

HERE = Path(__file__).resolve().parent

SOLVER = r"""#!/usr/bin/python3 -S
import json
import os
from pathlib import Path
import sys

network, traffic, scenario, output = map(Path, sys.argv[1:5])
stats = Path(os.environ["SEDGE_STATS"])
joint = int(os.environ["FLEET_JOINT"])
rounds = int(os.environ["SEDGE_MAX_ROUNDS"])
resume = os.environ.get("CLOUD_INITIAL_SOLUTION")
mode = os.environ.get("FAKE_SOLVER_MODE", "write")
budget = "joint-budget" in traffic.name
if budget:
    vector = [10, 8, 7] if joint == 0 else [10, 8, 6]
    total_cost, budget_used = 3, [0, 3]
else:
    vector = [10, 8, 1] if joint == 0 else [9, 8, 1]
    total_cost, budget_used = 0, [0, 0]
if rounds == 0 and resume:
    payload = json.loads(Path(resume).read_text(encoding="utf-8"))
else:
    payload = {"vector": vector, "total_cost": total_cost,
               "generation": os.environ.get("FAKE_GENERATION", "1")}
skip_output = mode in {"skip_all", "skip_output"} or (
    mode == "skip_resume_output" and rounds == 0)
skip_stats = mode in {"skip_all", "skip_stats"} or (
    mode == "skip_resume_stats" and rounds == 0)
if not skip_output:
    output.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
if not skip_stats:
    stats.write_text(json.dumps({
        "accepted": 0 if joint == 0 else 1,
        "joint_accepted": 0 if joint == 0 else 1,
        "budget_used": budget_used,
        "resumed": bool(resume),
        "resume_input": resume,
    }, sort_keys=True) + "\n", encoding="utf-8")
"""

CHECKER = r"""#!/usr/bin/python3 -S
import argparse
import json
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument("--net")
parser.add_argument("--tm")
parser.add_argument("--scenario")
parser.add_argument("--srpaths", type=Path, required=True)
parser.add_argument("--max-decimal-places")
args = parser.parse_args()
payload = json.loads(args.srpaths.read_text(encoding="utf-8"))
print(json.dumps({
    "valid": True,
    "saturations": [{"sat": value} for value in payload["vector"]],
    "total_cost": payload["total_cost"],
}, sort_keys=True))
"""


class VerifyJointOutputOwnership(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="verify-joint-output-")
        self.addCleanup(self.temp.cleanup)
        self.sandbox = Path(self.temp.name)
        self.output = self.sandbox / "out"
        self.solver = self.sandbox / "fake_solver.py"
        self.checker = self.sandbox / "fake_checker.py"
        self.solver.write_text(textwrap.dedent(SOLVER), encoding="utf-8")
        self.checker.write_text(textwrap.dedent(CHECKER), encoding="utf-8")
        self.solver.chmod(0o755)
        self.checker.chmod(0o755)
        self.command = [
            "/usr/bin/python3", "-S", str(HERE / "verify_joint.py"),
            "--solver", str(self.solver),
            "--checker", str(self.checker),
            "--output", str(self.output),
        ]

    def run_verify(self, **changes):
        env = os.environ.copy()
        env.update({key: str(value) for key, value in changes.items()})
        return subprocess.run(self.command, env=env, text=True, capture_output=True)

    def seed_success(self, generation="1"):
        result = self.run_verify(FAKE_GENERATION=generation)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads((self.output / "summary.json").read_text(encoding="utf-8"))

    def test_current_cells_replace_stale_bytes_and_resume_from_detached_snapshot(self):
        first = self.seed_success("first")
        for case in ("joint", "joint-budget"):
            output = (self.output / f"{case} resume in place.json").resolve()
            stats = json.loads(
                (self.output / f"{case} resume in place-stats.json").read_text(encoding="utf-8"))
            resume = Path(stats["resume_input"])
            self.assertNotEqual(resume, output)
            self.assertFalse(resume.exists())
        log = self.output / "joint-enabled.log"
        checker = self.output / "joint-enabled-checker.json"
        log.write_text("stale log\n", encoding="utf-8")
        checker.write_text("stale checker\n", encoding="utf-8")
        second_result = self.run_verify(FAKE_GENERATION="second")
        self.assertEqual(second_result.returncode, 0, second_result.stderr)
        second = json.loads((self.output / "summary.json").read_text(encoding="utf-8"))
        self.assertNotEqual(first["cases"][0]["after_sha256"],
                            second["cases"][0]["after_sha256"])
        self.assertIn('"second"', (self.output / "joint-enabled.json").read_text())
        self.assertNotIn("stale", log.read_text(encoding="utf-8"))
        self.assertNotIn("stale", checker.read_text(encoding="utf-8"))

    def assert_missing_cell_rejected(self, mode):
        self.seed_success()
        result = self.run_verify(FAKE_SOLVER_MODE=mode)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("without creating current output cells", result.stderr)
        self.assertFalse((self.output / "summary.json").exists())

    def test_zero_exit_without_output_cannot_reuse_previous_run(self):
        self.assert_missing_cell_rejected("skip_output")

    def test_zero_exit_without_stats_cannot_reuse_previous_run(self):
        self.assert_missing_cell_rejected("skip_stats")

    def test_same_path_resume_must_create_a_fresh_output(self):
        self.assert_missing_cell_rejected("skip_resume_output")

    def test_directory_in_deterministic_cell_fails_before_solver(self):
        self.output.mkdir()
        (self.output / "joint-disabled.json").mkdir()
        result = self.run_verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Output cell is a directory", result.stderr)
        self.assertFalse((self.output / "summary.json").exists())


if __name__ == "__main__":
    unittest.main()
