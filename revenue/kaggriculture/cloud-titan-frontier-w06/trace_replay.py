#!/usr/bin/env python3
"""Source-pinned Titan-vs-Apex replay, transition tracer, and counterfactual screener.

This offline diagnostic never calls Kaggle, mutates a submission, or selects a
production policy. Agent modules are executable code; use an isolated runner.
The existing official evaluator remains the game driver and process boundary.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from w06_common import SCHEMA, canonical, plain, sha256_file, verify_and_extract, write_json  # noqa: E402
from w06_run import replay  # noqa: E402
from w06_trace import analyze_transitions, apply_intervention, intervention_candidates  # noqa: E402

__all__ = [
    "SCHEMA", "canonical", "plain", "sha256_file", "verify_and_extract", "write_json",
    "analyze_transitions", "apply_intervention", "intervention_candidates", "replay",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify-release", help="verify and safely extract the pinned candidate archive")
    verify.add_argument("--archive", type=Path, required=True)
    verify.add_argument("--pin", type=Path, required=True)
    verify.add_argument("--output", type=Path, required=True)
    verify.add_argument("--receipt", type=Path)

    run = subparsers.add_parser("replay", help="run the exact both-seat Apex counterexample and bounded interventions")
    run.add_argument("--pin", type=Path, required=True)
    run.add_argument("--candidate", type=Path, required=True)
    run.add_argument("--candidate-callable", default="agent")
    run.add_argument("--apex", type=Path, required=True)
    run.add_argument("--apex-callable", default="agent")
    run.add_argument("--evaluator", type=Path, required=True)
    run.add_argument("--loader", type=Path, required=True)
    run.add_argument("--engine-dir", type=Path, required=True)
    run.add_argument("--seed", type=int, default=2611002002)
    run.add_argument("--rng-seed", type=int, default=20260907)
    run.add_argument("--action-timeout", type=float, default=4.0)
    run.add_argument("--startup-timeout", type=float, default=15.0)
    run.add_argument("--game-timeout", type=float, default=180.0)
    run.add_argument("--max-interventions-per-seat", type=int, default=4)
    run.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "verify-release":
        receipt = verify_and_extract(args.archive.resolve(), args.pin.resolve(), args.output.resolve())
        if args.receipt:
            write_json(args.receipt, receipt)
        print(canonical(receipt).decode("utf-8"))
        return 0
    if args.max_interventions_per_seat < 0 or args.max_interventions_per_seat > 12:
        parser.error("--max-interventions-per-seat must be between 0 and 12")
    if any(not math.isfinite(value) or value <= 0 for value in (args.action_timeout, args.startup_timeout, args.game_timeout)):
        parser.error("timeouts must be finite and positive")
    return replay(args)


if __name__ == "__main__":
    raise SystemExit(main())
