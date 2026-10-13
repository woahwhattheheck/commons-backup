#!/usr/bin/env python3
"""Check or repair UIOWA-132 commercial facts across a five-document bundle.

Output is internal draft reconciliation only. It is not buyer contact,
submission, invoice, payment, revenue, or scheduling.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from checker import FactsError, check_bundle, load_bundle, render_facts_markdown
from repair import repair_text

REQUIRED = (
    "proposal.md",
    "fee_schedule.md",
    "staffing.md",
    "scope_exhibit.md",
    "option_sheet.md",
)


def _write(path: Path | None, text: str) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="directory of five required .md documents")
    parser.add_argument("--json-out", type=Path, help="write the facts/findings JSON here")
    parser.add_argument("--md-out", type=Path, help="write the facts table markdown here")
    parser.add_argument(
        "--repair-out",
        type=Path,
        help="write repaired drafts into this directory without collapsing prime/subcontract labels",
    )
    args = parser.parse_args(argv)
    try:
        bundle = load_bundle(args.bundle)
        result = check_bundle(bundle)
        payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
        table = render_facts_markdown(result)
        _write(args.json_out, payload)
        _write(args.md_out, table)
        if args.repair_out is not None:
            args.repair_out.mkdir(parents=True, exist_ok=True)
            for name, doc in bundle.items():
                repaired = repair_text(doc.text)
                dest = args.repair_out / f"{name}.md"
                dest.write_text(repaired, encoding="utf-8", newline="\n")
        print(table)
        print(f"consistent={result['consistent']} findings={len(result['findings'])}")
        print(
            "AUTHORITY: draft reconciliation only; "
            "buyer contact / submission / invoice / payment / revenue / scheduling remain false."
        )
    except FactsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0 if result["consistent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
