# SPDX-License-Identifier: Apache-2.0
"""End-to-end promotion queue test with a mocked gate script.

The stub gate honors the real gate.py CLI contract
(--contract/--evidence/--baseline/--candidate/--report, exit 0/2/3) and
evaluates one real policy key (min_mean_own_delta) over the paired cells,
so the queue's orchestration, verdict combination, receipt sealing, and
rerun semantics are exercised without the heavyweight real gate.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROMOTE_PY = Path(__file__).resolve().parent.parent / "promote.py"

STUB_GATE = r"""#!/usr/bin/env python3
# Mocked gate.py: honors the real CLI contract (exit 0/2/3) and evaluates
# one real policy key (min_mean_own_delta) over the paired cells.
import argparse, json, sys
from pathlib import Path

def evaluate(contract_path, evidence_path, baseline_path, candidate_path):
    contract = json.loads(Path(contract_path).read_text())
    evidence = json.loads(Path(evidence_path).read_text())
    if evidence["provenance"] != contract["provenance"]:
        return None, 2, "INVALID: provenance drift"

    def load(path):
        rows = {}
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if line:
                row = json.loads(line)
                rows[(row["opponent"], row["seed"], row["candidate_seat"])] = row
        return rows

    baseline = load(baseline_path)
    candidate = load(candidate_path)
    if set(baseline) != set(candidate):
        return None, 2, "INVALID: cell sets differ"
    deltas = [
        candidate[k]["scores"][candidate[k]["candidate_seat"]]
        - baseline[k]["scores"][baseline[k]["candidate_seat"]]
        for k in baseline
    ]
    mean_delta = sum(deltas) / len(deltas)
    policy = contract["policy"]
    passed = mean_delta >= policy["min_mean_own_delta"]
    verdict = "PROMOTE" if passed else "REJECT"
    report = {
        "schema_version": 1,
        "verdict": verdict,
        "valid": True,
        "panel_id": contract["panel_id"],
        "grid": {
            "seeds": contract["seeds"],
            "opponents": contract["opponents"],
            "seats": contract["seats"],
            "expected_cells": contract["expected_cells"],
        },
        "checks": [
            {"name": "min_mean_own_delta", "pass": passed,
             "detail": {"mean": mean_delta}},
        ],
        "metrics": {
            "aggregate": {
                "own_delta": {"mean": mean_delta, "median": mean_delta},
                "margin_delta": {"mean": mean_delta},
                "result_regressions": 0,
                "new_losses": 0,
            }
        },
    }
    return report, (0 if passed else 3), ""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", required=True)
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()
    report, code, err = evaluate(
        args.contract, args.evidence, args.baseline, args.candidate)
    if err:
        print(err, file=sys.stderr)
        return code
    Path(args.report).write_text(json.dumps(report, indent=2))
    return code

if __name__ == "__main__":
    raise SystemExit(main())
"""

STUB_DUAL_GATE = r"""#!/usr/bin/env python3
# Mocked dual_predecessor_gate.py: honors the real 14-arg CLI contract and
# report shape (verdict + comparisons{predecessor_a,predecessor_b}), running
# the mocked paired gate once per slot and AND-ing the verdicts.
import argparse, json, os, sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gate as paired

def main():
    ap = argparse.ArgumentParser()
    for slot in ("predecessor-a", "predecessor-b"):
        ap.add_argument(f"--{slot}-contract", required=True)
        ap.add_argument(f"--{slot}-evidence", required=True)
        ap.add_argument(f"--{slot}-games", required=True)
        ap.add_argument(f"--{slot}-receipt", required=True)
        ap.add_argument(f"--{slot}-artifact", required=True)
    ap.add_argument("--candidate-games", required=True)
    ap.add_argument("--candidate-artifact", required=True)
    ap.add_argument("--engine-artifact", required=True)
    ap.add_argument("--runner-artifact", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    reports = {}
    codes = []
    for key, slot in (("predecessor_a", "predecessor-a"),
                      ("predecessor_b", "predecessor-b")):
        report, code, err = paired.evaluate(
            getattr(args, f"{slot}_contract".replace("-", "_")),
            getattr(args, f"{slot}_evidence".replace("-", "_")),
            getattr(args, f"{slot}_games".replace("-", "_")),
            args.candidate_games,
        )
        if err:
            print(f"{key}: {err}", file=sys.stderr)
            return 2
        reports[key] = report
        codes.append(code)
    verdict = "PROMOTE" if all(c == 0 for c in codes) else "REJECT"
    Path(args.report).write_text(json.dumps(
        {"schema_version": 1, "verdict": verdict, "comparisons": reports},
        indent=2))
    return 0 if verdict == "PROMOTE" else 3

if __name__ == "__main__":
    raise SystemExit(main())
"""


def write_panel(path: Path, own: float, rival: float = 50.0) -> None:
    rows = []
    for opponent in ("arlene", "apex"):
        for seed in (101, 102):
            for seat in (0, 1):
                scores = [rival, rival]
                scores[seat] = own
                rows.append(
                    {
                        "opponent": opponent,
                        "seed": seed,
                        "candidate_seat": seat,
                        "status": "complete",
                        "scores": scores,
                    }
                )
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def write_policy(path: Path, min_mean_own_delta: float) -> None:
    path.write_text(
        json.dumps(
            {
                "min_mean_own_delta": min_mean_own_delta,
                "min_median_own_delta": min_mean_own_delta,
                "min_mean_margin_delta": min_mean_own_delta,
                "min_positive_cell_fraction": 0.0,
                "min_positive_pair_fraction": 0.0,
                "max_result_regressions": 8,
                "max_baseline_win_regressions": 8,
                "max_new_losses": 8,
                "max_negative_opponent_strata": 2,
                "max_negative_seat_strata": 2,
                "min_worst_cell_own_delta": None,
                "require_any_change": False,
            }
        )
    )


class MockedEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.state = self.root / "state"
        gate_dir = self.root / "fake-gate"
        gate_dir.mkdir()
        (gate_dir / "gate.py").write_text(STUB_GATE)
        (gate_dir / "dual_predecessor_gate.py").write_text(STUB_DUAL_GATE)
        self.gate_dir = gate_dir

        self.engine_id = self.root / "engine.json"
        self.engine_id.write_text(json.dumps({"engine": "stub-1.0"}))
        self.runner_id = self.root / "runner.json"
        self.runner_id.write_text(json.dumps({"runner": "stub-evaluator"}))
        self.control_games = self.root / "control.GAMES.jsonl"
        write_panel(self.control_games, own=100.0)
        self.control_artifact = self.root / "control.bin"
        self.control_artifact.write_bytes(b"frozen-control-bytes")
        self.land_artifact = self.root / "land.bin"
        self.land_artifact.write_bytes(b"land-bytes-different")

        config = {
            "schema_version": 1,
            "policy_version": "promotion-policy/v1",
            "engine": {"commit": "a" * 40, "identity_file": str(self.engine_id)},
            "runner": {"commit": "b" * 40, "identity_file": str(self.runner_id)},
            "slots": {
                "frozen_control": {
                    "name": "frozen-control",
                    "games": str(self.control_games),
                    "artifact_file": str(self.control_artifact),
                },
                "land": {
                    "name": "land",
                    "games": str(self.control_games),
                    "artifact_file": str(self.land_artifact),
                },
            },
        }
        self.config = self.root / "predecessors.json"
        self.config.write_text(json.dumps(config))

    def tearDown(self):
        self.td.cleanup()

    def _cli(self, *argv) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(PROMOTE_PY), "--state-dir", str(self.state), *argv],
            capture_output=True,
            text=True,
        )

    def _run(self, *argv) -> subprocess.CompletedProcess:
        """Run the queue against the mocked gate scripts (never the real ones)."""
        return self._cli(
            "run", *argv, "--predecessors", str(self.config),
            "--gate-dir", str(self.gate_dir),
        )

    def _submit(self, name, own, policy_delta, artifact_tag=None):
        cand_games = self.root / f"{name}.GAMES.jsonl"
        write_panel(cand_games, own=own)
        artifact = self.root / f"{name}.bin"
        artifact.write_bytes(f"candidate-{artifact_tag or name}".encode())
        policy = self.root / f"{name}.policy.json"
        write_policy(policy, policy_delta)
        proc = self._cli(
            "submit", "--name", name, "--artifact", str(artifact),
            "--games", str(cand_games), "--policy", str(policy),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        first = proc.stdout.splitlines()[0]
        self.assertTrue(first.startswith("SUBMITTED") or first.startswith("DUPLICATE"),
                        proc.stdout)
        return first.split()[1]

    def test_promote_path_end_to_end(self):
        sub = self._submit("good", own=110.0, policy_delta=5.0)
        proc = self._run("--id", sub)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("PROMOTE", proc.stdout)

        status = self._cli("status", sub)
        entry = json.loads(status.stdout)
        self.assertEqual(entry["status"], "passed")
        self.assertIsNotNone(entry["last_receipt"])

        receipt = self._cli("receipt", sub, "--verify")
        self.assertEqual(receipt.returncode, 0, receipt.stdout)
        self.assertIn("OK", receipt.stdout)

        raw = self._cli("receipt", sub)
        doc = json.loads(raw.stdout)
        self.assertEqual(doc["verdict"], "PROMOTE")
        self.assertEqual(len(doc["comparisons"]), 2)
        self.assertEqual(
            {c["slot"] for c in doc["comparisons"]}, {"frozen_control", "land"}
        )
        self.assertTrue(all(c["verdict"] == "PROMOTE" for c in doc["comparisons"]))

    def test_reject_then_rerun(self):
        sub = self._submit("weak", own=100.0, policy_delta=50.0)
        proc = self._run("--id", sub)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("REJECT", proc.stdout)
        entry = json.loads(self._cli("status", sub).stdout)
        self.assertEqual(entry["status"], "failed")
        first_receipt = entry["last_receipt"]
        self.assertIsNotNone(first_receipt)

        rerun = self._cli("rerun", sub)
        self.assertEqual(rerun.returncode, 0, rerun.stdout)
        entry = json.loads(self._cli("status", sub).stdout)
        self.assertEqual(entry["status"], "pending")

        proc = self._run("--id", sub)
        self.assertNotEqual(proc.returncode, 0)
        entry = json.loads(self._cli("status", sub).stdout)
        self.assertEqual(entry["status"], "failed")
        # rerun is deterministic: same verdict, chained receipt
        self.assertNotEqual(entry["last_receipt"], first_receipt)
        raw = self._cli("receipt", sub)
        doc = json.loads(raw.stdout)
        self.assertEqual(doc["verdict"], "REJECT")
        verify = self._cli("receipt", sub, "--verify")
        self.assertEqual(verify.returncode, 0)

    def test_fifo_and_dedupe(self):
        first = self._submit("one", own=110.0, policy_delta=5.0)
        second = self._submit("two", own=110.0, policy_delta=5.0)
        # identical input bytes (same artifact/panel/policy bytes) dedupe,
        # even under a different candidate name (names are not pinned)
        dup = self._submit("three", own=110.0, policy_delta=5.0, artifact_tag="one")
        self.assertEqual(dup, first)
        listing = self._cli("list", "--status", "pending").stdout
        lines = [ln for ln in listing.splitlines() if ln.startswith("pq-")]
        self.assertEqual([ln.split()[0] for ln in lines], [first, second])

        proc = self._run("--all")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for sub in (first, second):
            entry = json.loads(self._cli("status", sub).stdout)
            self.assertEqual(entry["status"], "passed")


if __name__ == "__main__":
    unittest.main()
