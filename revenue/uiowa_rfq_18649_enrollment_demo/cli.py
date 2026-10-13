"""Run the UIOWA-106 two-stage enrollment demo. Exit 0 ok, 2 refuse."""

from __future__ import annotations

import argparse
import json
import os
import sys

try:
    from .demo import materialize
    from .timeline import DemoError, compare_stages, load_stage
except ImportError:
    from demo import materialize
    from timeline import DemoError, compare_stages, load_stage


def main(argv=None):
    ap = argparse.ArgumentParser(description="RFQ 18649 ESS/IAM enrollment-period demo")
    ap.add_argument("--fixtures", help="existing stage1/stage2 directory")
    ap.add_argument("--out", help="materialize a fresh packet here (refused if exists)")
    args = ap.parse_args(argv)
    try:
        if args.out:
            materialize(args.out)
            root = args.out
        elif args.fixtures:
            root = args.fixtures
        else:
            raise DemoError("provide --fixtures or --out")
        s1 = load_stage(os.path.join(root, "stage1"))
        s2 = load_stage(os.path.join(root, "stage2"))
        diff = compare_stages(s1, s2)
    except (DemoError, OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        sys.stderr.write("REFUSED: %s\n" % exc)
        return 2
    report = {
        "stage1_conclusions": s1["conclusions"],
        "stage2_conclusions": s2["conclusions"],
        "diff": diff,
    }
    if args.out:
        with open(os.path.join(args.out, "comparison.json"), "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, sort_keys=True)
            fh.write("\n")
    else:
        json.dump(report, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
