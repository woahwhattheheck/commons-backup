"""Offline verifier entrypoint."""

from __future__ import annotations

import sys

from revenue.multi_framework_evidence_freshness.gate import load_strict_json

from .wrapper import DiagnosticError, verify_diagnostic


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python -m revenue.multi_framework_evidence_freshness_pilot.verify DIAGNOSTIC_JSON", file=sys.stderr)
        return 2
    try:
        print(verify_diagnostic(load_strict_json(argv[0])))
        return 0
    except (DiagnosticError, OSError) as exc:
        print(f"HOLD:{exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
