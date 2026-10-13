#!/usr/bin/env python3
"""Offline CLI and compatibility surface for the Iowa RFQ 18649 carrier.

The public CLI is deliberately non-authorizing. Trusted hosts import
``compile_current`` and ``verify_current`` and supply an independently retained
authority root.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from workshare_contract import (
    AUTHORITY_SCHEMA,
    CANDIDATE_SCHEMA,
    ContractError,
    REPORT_SCHEMA,
    _parse_utc,
    _sha256_bytes,
    _sha256_value,
    authority_root_sha256,
    canonical_json_bytes,
    loads_strict,
    normalize_authority,
    normalize_candidate,
)
from workshare_engine import (
    compile_current,
    compile_historical,
    compile_untrusted_inspection,
    render_markdown,
    verify_current,
    verify_report_integrity,
)
from workshare_io import _load_file, _read_bounded_regular, _write_exclusive

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_compile = sub.add_parser(
        "compile",
        help="compile an UNTRUSTED_INSPECTION packet; public CLI cannot mint current READY",
    )
    p_compile.add_argument("candidate")
    p_compile.add_argument("authority")
    p_compile.add_argument("output")

    p_verify = sub.add_parser(
        "verify",
        help="verify semantic integrity only; public CLI has no trusted-root input",
    )
    p_verify.add_argument("report")

    p_render = sub.add_parser("render")
    p_render.add_argument("report")
    p_render.add_argument("output")

    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            candidate = _load_file(Path(args.candidate))
            authority = _load_file(Path(args.authority))
            normalized_authority = normalize_authority(authority)
            # Public inspection is deterministic and explicitly non-current.
            # Its clock is derived from the newest embedded source only because
            # this path can never mint review authority.
            inspection_at = max(
                _parse_utc(row["observed_at"], "source.observed_at")
                for row in normalized_authority["sources"]
            )
            report = compile_untrusted_inspection(candidate, authority, now=inspection_at)
            _write_exclusive(Path(args.output), canonical_json_bytes(report))
            print(f"{report['aggregate_state']} {report['receipt_sha256']}")
            return 0
        if args.command == "verify":
            report = _load_file(Path(args.report))
            result = verify_report_integrity(report)
            print(f"UNTRUSTED_INTEGRITY_ONLY {result['receipt_sha256']}")
            return 0
        if args.command == "render":
            report = _load_file(Path(args.report))
            _write_exclusive(Path(args.output), render_markdown(report).encode("utf-8"))
            print(report["receipt_sha256"])
            return 0
    except (ContractError, OSError) as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
