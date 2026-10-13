# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import json
from pathlib import Path

import gate

H0, H1, H2, H3 = (character * 64 for character in "0123")
G0, G1 = "a" * 40, "b" * 40


def policy(**overrides):
    value = {
        "min_mean_own_delta": 1.0,
        "min_median_own_delta": 1.0,
        "min_mean_margin_delta": 1.0,
        "min_positive_cell_fraction": 0.5,
        "min_positive_pair_fraction": 0.5,
        "max_result_regressions": 0,
        "max_baseline_win_regressions": 0,
        "max_new_losses": 0,
        "max_negative_opponent_strata": 0,
        "max_negative_seat_strata": 0,
        "min_worst_cell_own_delta": -20.0,
        "require_any_change": True,
    }
    value.update(overrides)
    return value


def contract(**overrides):
    value = {
        "schema_version": 1,
        "panel_id": "panel-1",
        "baseline_name": "canonical",
        "candidate_name": "challenger",
        "seeds": [101, 102],
        "opponents": ["arlene", "apex"],
        "seats": [0, 1],
        "expected_cells": 8,
        "provenance": {
            "engine_commit": G0,
            "engine_sha256": H0,
            "runner_commit": G1,
            "runner_sha256": H1,
            "baseline_artifact_sha256": H2,
            "candidate_artifact_sha256": H3,
        },
        "policy": policy(),
    }
    value.update(overrides)
    return value


def evidence(provenance=None, **overrides):
    value = {
        "schema_version": 1,
        "panel_id": "panel-1",
        "provenance": deepcopy(provenance or contract()["provenance"]),
        "exact_command": "python gauntlet.py --seeds 101,102 --opponents arlene,apex",
    }
    value.update(overrides)
    return value


def rows(delta=10.0):
    baseline, candidate = [], []
    for opponent in ("arlene", "apex"):
        for seed in (101, 102):
            for seat in (0, 1):
                before = [100.0, 80.0] if seat == 0 else [80.0, 100.0]
                after = list(before)
                after[seat] += delta
                common = {"opponent": opponent, "seed": seed, "candidate_seat": seat, "status": "complete"}
                baseline.append({**common, "scores": before})
                candidate.append({**common, "scores": after})
    return baseline, candidate


def write_json(path: Path, value):
    path.write_text(json.dumps(value, allow_nan=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, values):
    path.write_text("".join(json.dumps(value, allow_nan=True) + "\n" for value in values), encoding="utf-8")


class Harness:
    def __init__(self, root: Path, *, contract_value=None, evidence_value=None, baseline=None, candidate=None):
        self.contract = root / "contract.json"
        self.evidence = root / "evidence.json"
        self.baseline = root / "baseline.jsonl"
        self.candidate = root / "candidate.jsonl"
        baseline_rows, candidate_rows = rows()
        write_json(self.contract, contract_value or contract())
        write_json(self.evidence, evidence_value or evidence())
        write_jsonl(self.baseline, baseline if baseline is not None else baseline_rows)
        write_jsonl(self.candidate, candidate if candidate is not None else candidate_rows)

    def run(self):
        return gate.run_gate(
            contract_path=self.contract, evidence_path=self.evidence,
            baseline_path=self.baseline, candidate_path=self.candidate,
        )
