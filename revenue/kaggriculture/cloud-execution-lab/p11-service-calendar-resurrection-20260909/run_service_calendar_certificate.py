#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read a P11 calendar payload and emit a deterministic JSON certificate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from service_calendar import CalendarInputError, admit_payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", help="input JSON path; stdin when omitted")
    parser.add_argument("--output", help="write certificate to this path instead of stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        text = Path(args.input).read_text(encoding="utf-8") if args.input else sys.stdin.read()
        payload = json.loads(text)
        certificate = admit_payload(payload)
    except (OSError, json.JSONDecodeError, CalendarInputError) as exc:
        print(json.dumps({"schema": "titan-p11-service-calendar/v1", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1

    rendered = json.dumps(certificate, indent=2, sort_keys=True) + "\n"
    if args.output:
        try:
            Path(args.output).write_text(rendered, encoding="utf-8")
        except OSError as exc:
            print(json.dumps({"schema": certificate["schema"], "error": str(exc)}, sort_keys=True), file=sys.stderr)
            return 1
    else:
        sys.stdout.write(rendered)
    return 0 if certificate["admitted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
