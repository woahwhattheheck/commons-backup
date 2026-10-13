#!/usr/bin/env python3
"""CLI for the read-only Outreach Yield Observatory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from revenue.outreach_yield_observatory import (  # noqa: E402
    ObservatoryError,
    dumps_report,
    evaluate_document,
    render_markdown,
)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Evaluate de-identified, already-recorded outreach evidence. "
            "This command has no provider or send capability."
        )
    )
    p.add_argument("input", type=Path, help="JSON evidence document")
    p.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="output format (default: json)",
    )
    p.add_argument("-o", "--output", type=Path, help="write output to this path")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        report = evaluate_document(payload)
    except (OSError, json.JSONDecodeError, ObservatoryError) as exc:
        print(f"outreach-yield-observatory: {exc}", file=sys.stderr)
        return 2

    text = dumps_report(report) if args.format == "json" else render_markdown(report)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
