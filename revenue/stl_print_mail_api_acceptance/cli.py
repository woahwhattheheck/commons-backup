"""CLI for the deterministic print/mail acceptance rail."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .validator import FixtureError, evaluate_fixture


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate print/mail acceptance evidence")
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
        receipt = evaluate_fixture(fixture)
    except (OSError, json.JSONDecodeError, FixtureError) as exc:
        parser.error(str(exc))
    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
