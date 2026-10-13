# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import gate
from test_support import Harness, contract, evidence, policy, rows


class PolicyRejectionTests(unittest.TestCase):
    def test_positive_mean_cannot_hide_a_win_to_loss_regression(self):
        baseline, candidate = rows(delta=20)
        candidate[0]["scores"] = [130.0, 200.0]
        with tempfile.TemporaryDirectory() as td:
            report, code = Harness(Path(td), baseline=baseline, candidate=candidate).run()
        self.assertEqual((code, report["verdict"]), (3, "REJECT"))
        self.assertGreater(report["metrics"]["aggregate"]["own_delta"]["mean"], 0)
        self.assertEqual(report["metrics"]["aggregate"]["baseline_win_regressions"], 1)
        failed = {item["name"] for item in report["checks"] if not item["pass"]}
        self.assertTrue({"result_regressions", "baseline_win_regressions", "new_losses"} <= failed)

    def test_negative_opponent_stratum_rejects_global_positive_mean(self):
        baseline, candidate = rows(delta=20)
        for row in candidate:
            if row["opponent"] == "arlene":
                row["scores"][row["candidate_seat"]] -= 30
        contract_value = contract(policy=policy(
            max_result_regressions=8, max_baseline_win_regressions=8, max_new_losses=8
        ))
        with tempfile.TemporaryDirectory() as td:
            report, code = Harness(
                Path(td), contract_value=contract_value,
                evidence_value=evidence(contract_value["provenance"]),
                baseline=baseline, candidate=candidate,
            ).run()
        self.assertEqual(code, 3)
        self.assertGreater(report["metrics"]["aggregate"]["own_delta"]["mean"], 0)
        self.assertEqual(report["metrics"]["aggregate"]["negative_opponent_strata"], 1)

    def test_identity_candidate_rejected_when_change_required(self):
        baseline, _ = rows()
        contract_value = contract(policy=policy(
            min_mean_own_delta=0, min_median_own_delta=0, min_mean_margin_delta=0,
            min_positive_cell_fraction=0, min_positive_pair_fraction=0,
            min_worst_cell_own_delta=0,
        ))
        with tempfile.TemporaryDirectory() as td:
            report, code = Harness(
                Path(td), contract_value=contract_value,
                evidence_value=evidence(contract_value["provenance"]),
                baseline=baseline, candidate=deepcopy(baseline),
            ).run()
        self.assertEqual(code, 3)
        self.assertEqual(report["metrics"]["aggregate"]["changed_cells"], 0)
        check = next(item for item in report["checks"] if item["name"] == "any_score_change")
        self.assertFalse(check["pass"])

    def test_worst_cell_floor_is_enforced(self):
        baseline, candidate = rows(delta=10)
        candidate[0]["scores"][candidate[0]["candidate_seat"]] -= 50
        contract_value = contract(policy=policy(
            min_mean_own_delta=0, min_median_own_delta=0, min_mean_margin_delta=0,
            min_positive_cell_fraction=0, min_positive_pair_fraction=0,
            max_result_regressions=8, max_baseline_win_regressions=8, max_new_losses=8,
            max_negative_opponent_strata=2, max_negative_seat_strata=2,
            min_worst_cell_own_delta=-20,
        ))
        with tempfile.TemporaryDirectory() as td:
            report, code = Harness(
                Path(td), contract_value=contract_value,
                evidence_value=evidence(contract_value["provenance"]),
                baseline=baseline, candidate=candidate,
            ).run()
        self.assertEqual(code, 3)
        check = next(item for item in report["checks"] if item["name"] == "worst_cell_own_delta")
        self.assertEqual(check["actual"], -40)
        self.assertFalse(check["pass"])


class CliTests(unittest.TestCase):
    def command(self, harness, report_path):
        return [
            sys.executable, str(Path(gate.__file__).resolve()),
            "--contract", str(harness.contract), "--evidence", str(harness.evidence),
            "--baseline", str(harness.baseline), "--candidate", str(harness.candidate),
            "--report", str(report_path), "--quiet",
        ]

    def test_cli_writes_atomic_machine_report_and_stable_exit(self):
        with tempfile.TemporaryDirectory() as td:
            root, harness = Path(td), Harness(Path(td))
            report_path = root / "nested" / "report.json"
            process = subprocess.run(self.command(harness, report_path), capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(json.loads(report_path.read_text())["verdict"], "PROMOTE")
            self.assertEqual(list(report_path.parent.glob(".*.tmp")), [])

    def test_cli_invalid_evidence_exits_two_and_writes_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            baseline, candidate = rows()
            candidate.pop()
            harness = Harness(root, baseline=baseline, candidate=candidate)
            report_path = root / "invalid.json"
            process = subprocess.run(self.command(harness, report_path), capture_output=True, text=True)
            self.assertEqual(process.returncode, 2)
            report = json.loads(report_path.read_text())
            self.assertEqual(report["verdict"], "INVALID")
            self.assertIn("missing 1 cells", report["error"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
