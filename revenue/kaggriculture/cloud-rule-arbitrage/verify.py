# SPDX-License-Identifier: MIT
"""Verify the immutable T11 development decision from raw evaluator panels."""
import json
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent


def keyed(report, opponent=None):
    rows = report["games"]
    if opponent is not None:
        rows = [row for row in rows if row["opponent"] == opponent]
    return {(row["seed"], row["candidate_seat"]):
            (row["scores"], row["trace_sha256"]) for row in rows}


candidate = json.loads((HERE / "results/development-candidate.json").read_text())
control = json.loads((HERE / "results/development-control.json").read_text())
selection = json.loads((HERE / "SELECTION.json").read_text())
freeze = json.loads((HERE / "SOURCE-FREEZE.json").read_text())

assert candidate["seeds"] == selection["development_seeds"]
assert control["seeds"] == selection["development_seeds"]
assert all(row["status"] == "complete" for row in candidate["games"] + control["games"])
assert len(candidate["games"]) == selection["candidate_games"]
assert len(control["games"]) == selection["control_games"]
assert keyed(candidate, "arlene") == keyed(control)
assert candidate["summary"]["arlene"]["wins"] == 6
assert candidate["summary"]["frozen_sell"]["ties"] == 6
assert candidate["reproducibility"]["same_trace_and_scores"]
assert control["reproducibility"]["same_trace_and_scores"]
assert selection["status"] == "research-only-not-composed"
assert selection["promotion"] is False
for key, name in (("candidate_sha256", "candidate.py"),
                  ("cycle_sha256", "cycle.py"),
                  ("candidate_results_sha256", "results/development-candidate.json"),
                  ("control_results_sha256", "results/development-control.json")):
    assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == freeze[key]
print("T11 receipt verified: 18 games, exact neutral transform, held unspent")
