#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Sequence

try:
    from .contracts import *  # re-export the public contract surface
    from .contracts import _hex64, _read_regular, _write_exclusive
    from .engine import *  # re-export the public decision/verification surface
except ImportError:  # direct execution from this directory
    from contracts import *  # type: ignore # noqa: F403
    from contracts import _hex64, _read_regular, _write_exclusive  # type: ignore
    from engine import *  # type: ignore # noqa: F403

def _load_json_file(path: str | os.PathLike[str]) -> Any:
    return loads_strict(_read_regular(path))


def _cmd_compile(args: argparse.Namespace) -> int:
    policy_raw, _policy = load_retained_policy()
    evidence_raw = _load_json_file(args.evidence)
    report = compile_report(
        policy_raw,
        evidence_raw,
        expected_policy_sha256=RETAINED_POLICY_SHA256,
        now=utc_now(),
    )
    _write_exclusive(args.out, canon(report))
    print(report_receipt(report))
    return 0


def _cmd_verify_history(args: argparse.Namespace) -> int:
    report_raw = _load_json_file(args.report)
    verify_report_history(
        report_raw,
        expected_policy_sha256=RETAINED_POLICY_SHA256,
        expected_report_sha256=args.expected_report_sha256,
    )
    print(f"HISTORICAL_INTEGRITY_OK {args.expected_report_sha256}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    report_raw = _load_json_file(args.report)
    evidence_raw = _load_json_file(args.evidence)
    current = replay_current(
        report_raw,
        evidence_raw,
        expected_report_sha256=args.expected_report_sha256,
        now=utc_now(),
    )
    result = {
        "status": "CURRENT_REPLAY_OK",
        "generated_at": current["generated_at"],
        "ready": current["summary"]["ready"],
        "blocked": current["summary"]["blocked"],
        "current_report_sha256": report_receipt(current),
        "historical_report_sha256": _hex64(
            args.expected_report_sha256, "expected_report_sha256"
        ),
    }
    print(canon(result).decode("utf-8"), end="")
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    report_raw = _load_json_file(args.report)
    evidence_raw = _load_json_file(args.evidence)
    current = replay_current(
        report_raw,
        evidence_raw,
        expected_report_sha256=args.expected_report_sha256,
        now=utc_now(),
    )
    rendered = render_current_markdown(
        current, historical_report_sha256=args.expected_report_sha256
    )
    _write_exclusive(args.out, rendered)
    print(report_receipt(current))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compile and replay a retained-policy hotel room-turn evidence pilot. "
            "Production policy identity and UTC are not caller-selectable."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    compile_parser = sub.add_parser(
        "compile",
        help="compile a historical receipt using retained policy and verifier-owned UTC",
    )
    compile_parser.add_argument("--evidence", required=True)
    compile_parser.add_argument("--out", required=True)
    compile_parser.set_defaults(func=_cmd_compile)

    history_parser = sub.add_parser(
        "verify-history",
        help="verify historical integrity only; this makes no current-readiness claim",
    )
    history_parser.add_argument("--report", required=True)
    history_parser.add_argument("--expected-report-sha256", required=True)
    history_parser.set_defaults(func=_cmd_verify_history)

    verify_parser = sub.add_parser(
        "verify",
        help="authenticate history and replay the bound evidence at verifier-owned UTC",
    )
    verify_parser.add_argument("--report", required=True)
    verify_parser.add_argument("--evidence", required=True)
    verify_parser.add_argument("--expected-report-sha256", required=True)
    verify_parser.set_defaults(func=_cmd_verify)

    render_parser = sub.add_parser(
        "render",
        help="render current replay results, never historical READY state",
    )
    render_parser.add_argument("--report", required=True)
    render_parser.add_argument("--evidence", required=True)
    render_parser.add_argument("--expected-report-sha256", required=True)
    render_parser.add_argument("--out", required=True)
    render_parser.set_defaults(func=_cmd_render)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        return int(args.func(args))
    except (ContractError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
