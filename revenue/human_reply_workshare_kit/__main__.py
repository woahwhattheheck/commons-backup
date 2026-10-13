from __future__ import annotations

import argparse
import pathlib
import sys

from .core import WorkshareError, compile_offer, render_receipt_json, strict_json_loads


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compile a bounded human-reply paid-workshare proposal with hard commercial truth guards."
    )
    parser.add_argument("input", type=pathlib.Path, help="UTF-8 JSON input")
    parser.add_argument(
        "--format",
        choices=("markdown", "receipt"),
        default="markdown",
        help="render the workshare one-pager or the deterministic receipt",
    )
    args = parser.parse_args(argv)
    try:
        raw = strict_json_loads(args.input.read_text(encoding="utf-8"))
        compiled = compile_offer(raw)
    except (OSError, UnicodeError, WorkshareError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.format == "receipt":
        sys.stdout.write(render_receipt_json(compiled))
    else:
        sys.stdout.write(compiled.markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
