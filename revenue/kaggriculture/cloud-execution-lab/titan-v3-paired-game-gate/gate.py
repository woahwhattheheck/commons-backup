#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed promotion gate for paired Kaggriculture GAMES.jsonl panels.

Exit 0 = PROMOTE, 2 = INVALID evidence, 3 = valid evidence that is REJECTED.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Sequence

from contract import validate_contract, validate_evidence
from gate_common import (
    GateError, MAX_JSONL_BYTES, MAX_JSON_BYTES, SCHEMA_VERSION,
    atomic_write_json, read_json, sha256_file, snapshot_regular_file,
)
from metrics import analyze, evaluate_policy
from panel_load import expected_keys, load_games


def run_gate(
    *, contract_path: Path, evidence_path: Path,
    baseline_path: Path, candidate_path: Path,
) -> tuple[dict[str, Any], int]:
    sources = {
        "contract": (contract_path, MAX_JSON_BYTES, "contract"),
        "evidence": (evidence_path, MAX_JSON_BYTES, "evidence"),
        "baseline_games": (baseline_path, MAX_JSONL_BYTES, "baseline games"),
        "candidate_games": (candidate_path, MAX_JSONL_BYTES, "candidate games"),
    }
    with TemporaryDirectory(prefix="titan-v3-paired-gate-") as directory:
        snapshot_root = Path(directory)
        snapshots = {
            name: snapshot_regular_file(
                path, directory=snapshot_root, max_bytes=max_bytes, label=label
            )
            for name, (path, max_bytes, label) in sources.items()
        }
        paths = {name: snapshot.path for name, snapshot in snapshots.items()}
        hashes = {name: snapshot.sha256 for name, snapshot in snapshots.items()}
        sizes = {name: snapshot.bytes for name, snapshot in snapshots.items()}

        contract = validate_contract(read_json(paths["contract"], label="contract"))
        evidence = validate_evidence(read_json(paths["evidence"], label="evidence"), contract)
        expected = expected_keys(contract)
        baseline = load_games(paths["baseline_games"], label="baseline games", expected=expected)
        candidate = load_games(paths["candidate_games"], label="candidate games", expected=expected)
        if set(baseline) != set(candidate):
            raise GateError("baseline/candidate cell-key sets differ")
        metrics = analyze(baseline, candidate)
        checks = evaluate_policy(metrics, contract["policy"])

        changed_snapshots = {}
        for name, snapshot in snapshots.items():
            observed = sha256_file(snapshot.path)
            if observed != snapshot.sha256:
                changed_snapshots[name] = {
                    "expected": snapshot.sha256,
                    "observed": observed,
                }
        if changed_snapshots:
            raise GateError(f"private input snapshot changed during evaluation: {changed_snapshots}")

        promote = all(item["pass"] for item in checks)
        report = {
            "schema_version": SCHEMA_VERSION,
            "verdict": "PROMOTE" if promote else "REJECT",
            "valid": True,
            "panel_id": contract["panel_id"],
            "baseline_name": contract["baseline_name"],
            "candidate_name": contract["candidate_name"],
            "input_sha256": hashes,
            "input_bytes": sizes,
            "input_binding": "single-open private snapshots; hashes cover exactly parsed bytes",
            "provenance": evidence["provenance"],
            "exact_command": evidence["exact_command"],
            "grid": {
                "seeds": contract["seeds"], "opponents": contract["opponents"],
                "seats": contract["seats"], "expected_cells": contract["expected_cells"],
                "observed_baseline_cells": len(baseline),
                "observed_candidate_cells": len(candidate),
            },
            "policy": contract["policy"], "checks": checks, "metrics": metrics,
        }
        return report, 0 if promote else 3


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("contract", "evidence", "baseline", "candidate", "report"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    try:
        report, code = run_gate(
            contract_path=args.contract, evidence_path=args.evidence,
            baseline_path=args.baseline, candidate_path=args.candidate,
        )
    except (GateError, OSError, UnicodeError) as exc:
        report, code = {
            "schema_version": SCHEMA_VERSION, "verdict": "INVALID",
            "valid": False, "error": str(exc),
        }, 2
    atomic_write_json(args.report, report)
    if not args.quiet:
        print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
