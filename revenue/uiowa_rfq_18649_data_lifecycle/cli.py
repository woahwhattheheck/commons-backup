"""Run from any working directory: python /path/to/cli.py packet.json new-output-dir."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__:
    from .lifecycle import InputError, MAX_BYTES, assess, findings_csv, loads, markdown
else:
    from lifecycle import InputError, MAX_BYTES, assess, findings_csv, loads, markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("output", type=Path, help="New directory; existing paths are never overwritten")
    args = parser.parse_args(argv)
    try:
        with args.packet.open("rb") as source:
            raw = source.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise InputError("input exceeds 2 MB")
        report = assess(loads(raw.decode("utf-8")))
        products = {"report.json": json.dumps(report, indent=2, ensure_ascii=True) + "\n",
                    "assessment.md": markdown(report), "follow-ups.csv": findings_csv(report)}
        args.output.mkdir(parents=False, exist_ok=False)
        for name, text in products.items():
            with (args.output / name).open("x", encoding="utf-8", newline="") as target:
                target.write(text)
        print(json.dumps({"status": "OFFLINE_ASSESSMENT_WRITTEN", "output": str(args.output),
                          "report_sha256": report["report_sha256"], "summary": report["summary"]}, sort_keys=True))
        return 0
    except (InputError, OSError, UnicodeError) as exc:
        print(f"assessment error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
