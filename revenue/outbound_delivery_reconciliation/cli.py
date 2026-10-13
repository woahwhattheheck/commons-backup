from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .reconcile import ReconciliationError, canonical_json, reconcile, verify

MAX_INPUT_BYTES = 2 * 1024 * 1024


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReconciliationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ReconciliationError(f"non-finite JSON constant: {value}")


def _read_json(path: str):
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise ReconciliationError(f"{path}: input exceeds {MAX_INPUT_BYTES} bytes")
    try:
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReconciliationError(f"{path}: invalid JSON: {exc}") from exc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Offline outbound provider-delivery reconciliation")
    sub = parser.add_subparsers(dest="command", required=True)
    p_compile = sub.add_parser("compile")
    p_compile.add_argument("--original", required=True)
    p_compile.add_argument("--events", required=True)
    p_verify = sub.add_parser("verify")
    p_verify.add_argument("--report", required=True)
    p_verify.add_argument("--original", required=True)
    p_verify.add_argument("--events", required=True)
    args = parser.parse_args(argv)

    try:
        original = _read_json(args.original)
        events = _read_json(args.events)
        if args.command == "compile":
            sys.stdout.write(canonical_json(reconcile(original, events)) + "\n")
            return 0
        report = _read_json(args.report)
        ok = verify(report, original, events)
        sys.stdout.write(("VERIFIED" if ok else "INVALID") + "\n")
        return 0 if ok else 2
    except (OSError, ReconciliationError) as exc:
        sys.stderr.write(f"HOLD: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
