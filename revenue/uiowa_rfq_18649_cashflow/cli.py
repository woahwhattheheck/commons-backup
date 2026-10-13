"""Project the UIOWA-009 cash-flow workbook. Exit 0 ok, 2 refuse."""

from __future__ import annotations

import argparse
import json
import os
import sys

try:
    from .engine import prime_university_register, project_all
    from .formulas import FormulaParityError, assert_parity
    from .render import invoices_markdown, pack, weekly_csv
    from .workbook import CashflowError, load_workbook
except ImportError:
    from engine import prime_university_register, project_all
    from formulas import FormulaParityError, assert_parity
    from render import invoices_markdown, pack, weekly_csv
    from workbook import CashflowError, load_workbook


def main(argv=None):
    ap = argparse.ArgumentParser(description="RFQ 18649 TJLabs cash-flow projection")
    ap.add_argument("--workbook", required=True)
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    try:
        workbook = load_workbook(args.workbook)
        projections = project_all(workbook)
        for p in projections.values():
            assert_parity(p)
        packed = pack(workbook)
    except (CashflowError, FormulaParityError, OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
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
        with open(os.path.join(args.out, "dashboard.md"), "w", encoding="utf-8") as fh:
            fh.write(packed["dashboard_md"])
            if not packed["dashboard_md"].endswith("\n"):
                fh.write("\n")
        with open(
            os.path.join(args.out, "prime_university_register.json"), "w", encoding="utf-8"
        ) as fh:
            json.dump(prime_university_register(workbook), fh, indent=2, sort_keys=True)
            fh.write("\n")
        for name, p in projections.items():
            d = os.path.join(args.out, name)
            os.makedirs(d)
            with open(os.path.join(d, "weekly.csv"), "w", encoding="utf-8") as fh:
                fh.write(weekly_csv(p))
            with open(os.path.join(d, "invoices.md"), "w", encoding="utf-8") as fh:
                fh.write(invoices_markdown(p))
    else:
        sys.stdout.write(packed["dashboard_md"])
        if not packed["dashboard_md"].endswith("\n"):
            sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
