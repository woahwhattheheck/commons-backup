#!/usr/bin/env python3
"""Check whether reported measures can carry the claims made from them.

    python3 check_soundness.py --measures fixtures/measures_UNSOUND.json
    python3 check_soundness.py --measures fixtures/measures_SOUND.json
    python3 check_soundness.py --measures fixtures/measures_SOUND.json --format json

Exit status: 0 no errors, 1 errors present, 2 the measure set could not be read.

The thresholds are arguments, not laws. `--min-denominator` sets the point below
which a proportion should be stated as a count; the default of 8 is a
readability judgement, not a statistical one, and an engagement is expected to
set its own. Stdlib only, no network, deterministic.
"""
from __future__ import annotations

import argparse
import json
import sys

import soundness


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--measures", required=True)
    p.add_argument("--format", default="text", choices=["text", "json"])
    p.add_argument("--out")
    p.add_argument("--min-denominator", type=int,
                   default=soundness.MIN_DENOMINATOR_FOR_RATE,
                   help="below this, a proportion is reported as a count")
    args = p.parse_args(argv)

    if args.min_denominator < 1:
        print("error: --min-denominator must be at least 1", file=sys.stderr)
        return 2

    try:
        measures = soundness.load_measures(args.measures)
        findings = soundness.check(measures, min_denominator=args.min_denominator)
    except (OSError, UnicodeError, soundness.MeasureError, json.JSONDecodeError) as exc:
        print(f"error: could not load measures: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        body = json.dumps({
            "measures_checked": len(measures),
            "min_denominator_for_rate": args.min_denominator,
            "passed": not any(f.severity == soundness.ERROR for f in findings),
            "findings": [f.to_dict() for f in findings],
        }, indent=2) + "\n"
    else:
        body = soundness.render_text(measures, findings)
    sys.stdout.write(body)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(body)
    return 1 if any(f.severity == soundness.ERROR for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
