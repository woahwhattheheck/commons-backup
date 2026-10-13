"""Quote a scope-change worksheet. Exit 0 proposed, 1 HOLD/ERROR, 2 refuse."""

from __future__ import annotations

import argparse
import json
import os
import sys

try:
    from .calculator import ERROR, ScopeError, load_worksheet, quote, render_worksheet
except ImportError:
    from calculator import ERROR, ScopeError, load_worksheet, quote, render_worksheet


def main(argv=None):
    ap = argparse.ArgumentParser(description="RFQ 18649 scope-change quotation")
    ap.add_argument("--worksheet", required=True)
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    try:
        sheet = load_worksheet(args.worksheet)
        result = quote(sheet)
    except (ScopeError, OSError, json.JSONDecodeError) as exc:
        sys.stderr.write("REFUSED: %s\n" % exc)
        return 2
    text = render_worksheet(result)
    if args.out:
        if os.path.exists(args.out):
            sys.stderr.write("REFUSED: output already exists (%s)\n" % args.out)
            return 2
        os.makedirs(args.out)
        with open(os.path.join(args.out, "quote.json"), "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, sort_keys=True)
            fh.write("\n")
        with open(os.path.join(args.out, "quote.md"), "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
    if result["totals"]["status"] != "PROPOSED_NOT_ACCEPTED" or any(
        i["severity"] == ERROR for i in result["issues"]
    ):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
