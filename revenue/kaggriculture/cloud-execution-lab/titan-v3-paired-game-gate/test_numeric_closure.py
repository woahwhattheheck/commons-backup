# SPDX-License-Identifier: Apache-2.0
"""Adversarial numeric-closure regressions for the paired-game gate."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import gate
from test_support import Harness, rows


class NumericClosureTests(unittest.TestCase):
    def run_cli(self, harness: Harness, report_path: Path) -> tuple[subprocess.CompletedProcess[str], dict]:
        process = subprocess.run(
            [
                sys.executable,
                str(Path(gate.__file__).resolve()),
                "--contract", str(harness.contract),
                "--evidence", str(harness.evidence),
                "--baseline", str(harness.baseline),
                "--candidate", str(harness.candidate),
                "--report", str(report_path),
                "--quiet",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertTrue(report_path.is_file(), process.stderr)
        return process, json.loads(report_path.read_text(encoding="utf-8"))

    def assert_invalid_cli(self, baseline, candidate, expected_error: str) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            harness = Harness(root, baseline=baseline, candidate=candidate)
            process, report = self.run_cli(harness, root / "report.json")
        self.assertEqual(process.returncode, 2, process.stderr)
        self.assertEqual(report["verdict"], "INVALID")
        self.assertFalse(report["valid"])
        self.assertIn(expected_error, report["error"])

    def test_integer_too_large_for_binary_float_is_invalid(self):
        baseline, candidate = rows()
        candidate[0]["scores"][0] = 10**400
        self.assert_invalid_cli(
            baseline,
            candidate,
            "candidate games line 1 scores[0]: expected a finite number",
        )

    def test_finite_endpoints_whose_delta_overflows_are_invalid(self):
        baseline, candidate = rows()
        baseline[0]["scores"] = [-1e308, 0.0]
        candidate[0]["scores"] = [1e308, 0.0]
        self.assert_invalid_cli(
            baseline,
            candidate,
            "cell ['arlene', 101, 0] own_delta: expected a finite number",
        )

    def test_finite_cell_deltas_whose_pair_mean_overflows_are_invalid(self):
        baseline, candidate = rows()
        for row in baseline:
            row["scores"] = [0.0, 0.0]
        for row in candidate:
            row["scores"] = [0.0, 0.0]
            row["scores"][row["candidate_seat"]] = 1e308
        self.assert_invalid_cli(
            baseline,
            candidate,
            "pair ['apex', 101] seat_mean_own_delta: derived mean is not finite",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
