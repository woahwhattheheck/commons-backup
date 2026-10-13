"""Schedule the UIOWA-002 staffing workbook. Exit 0 ok, 2 refuse."""

from __future__ import annotations

import argparse
import json
import os
import sys

try:
    from .engine import schedule
    from .render import eval_formula_sheet, formula_sheet, pack
    from .workbook import StaffingError, load_workbook
except ImportError:
    from engine import schedule
    from render import eval_formula_sheet, formula_sheet, pack
    from workbook import StaffingError, load_workbook


def main(argv=None):
    ap = argparse.ArgumentParser(description="RFQ 18649 staffing plan")
    ap.add_argument("--workbook", required=True)
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    try:
        workbook = load_workbook(args.workbook)
        result = schedule(workbook)
        rows = formula_sheet(result)
        got = eval_formula_sheet(rows)
        for row, value in zip(rows, got):
            if value != row["engine_total"]:
                raise StaffingError(
                    "formula parity failed week %s (%s != %s)"
                    % (row["week"], value, row["engine_total"])
                )
        packed = pack(workbook)
    except (StaffingError, OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        sys.stderr.write("REFUSED: %s\n" % exc)
        return 2
    if args.out:
        if os.path.exists(args.out):
            sys.stderr.write("REFUSED: output already exists (%s)\n" % args.out)
            return 2
        os.makedirs(args.out)
        with open(os.path.join(args.out, "pack.json"), "w", encoding="utf-8") as fh:
            json.dump(packed, fh, indent=2, sort_keys=True)
            fh.write("\n")
        with open(os.path.join(args.out, "calendar.md"), "w", encoding="utf-8") as fh:
            fh.write(packed["calendar_md"])
            if not packed["calendar_md"].endswith("\n"):
                fh.write("\n")
    else:
        sys.stdout.write(packed["calendar_md"])
        if not packed["calendar_md"].endswith("\n"):
            sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
