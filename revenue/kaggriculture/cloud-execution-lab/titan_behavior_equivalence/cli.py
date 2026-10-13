# SPDX-License-Identifier: Apache-2.0
"""Command-line entrypoint for the TITAN behavior-equivalence gate."""
from __future__ import annotations

import argparse
import sys
from typing import Sequence

from .analysis import analyze_equivalence
from .core import BehaviorGateError, ZERO_SHA256, _mapping, _seal, load_strict, preflight_family
from .receipts import _write_json, _write_markdown, append_ledger, verify_ledger

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser(
        "preflight", help="reject duplicate exact executable registrations before results"
    )
    preflight.add_argument("--family", required=True)
    preflight.add_argument("--json-out")
    preflight.add_argument("--markdown-out")
    preflight.add_argument("--ledger")

    analyze = subparsers.add_parser(
        "analyze", help="report complete-grid observational behavior equivalence"
    )
    analyze.add_argument("--family", required=True)
    analyze.add_argument("--observations", required=True)
    analyze.add_argument("--json-out")
    analyze.add_argument("--markdown-out")
    analyze.add_argument("--ledger")

    verify = subparsers.add_parser("verify-ledger", help="verify the append-only receipt chain")
    verify.add_argument("--ledger", required=True)
    verify.add_argument("--json-out")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "preflight":
            report = preflight_family(_mapping(load_strict(args.family), args.family))
            if args.ledger:
                append_ledger(args.ledger, report, "preflight")
            _write_json(report, args.json_out)
            _write_markdown(report, args.markdown_out)
            return 0 if report["verdict"] == "PASS" else 2
        if args.command == "analyze":
            report = analyze_equivalence(
                _mapping(load_strict(args.family), args.family),
                _mapping(load_strict(args.observations), args.observations),
            )
            if args.ledger:
                append_ledger(args.ledger, report, "analysis")
            _write_json(report, args.json_out)
            _write_markdown(report, args.markdown_out)
            return 0 if report["verdict"] == "PASS" else 2
        if args.command == "verify-ledger":
            entries = verify_ledger(args.ledger)
            report = _seal(
                {
                    "schema": "titan-behavior-equivalence-ledger-verification/v1",
                    "verdict": "PASS",
                    "entries": len(entries),
                    "head_entry_sha256": entries[-1]["entry_sha256"] if entries else ZERO_SHA256,
                    "family_sha256": entries[-1]["family_sha256"] if entries else ZERO_SHA256,
                }
            )
            _write_json(report, args.json_out)
            return 0
        raise AssertionError(f"unhandled command: {args.command}")
    except BehaviorGateError as exc:
        sys.stderr.write(f"behavior-equivalence gate refused input: {exc}\n")
        return 2
