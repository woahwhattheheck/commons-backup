"""Render the six UIOWA-139 packets. Exit 0 ok, 2 refuse."""

from __future__ import annotations

import argparse
import json
import os
import sys

try:
    from .dispositions import CaseError
    from .renderer import bundle, load_cases_dir, render_decision_aid, render_markdown
except ImportError:
    from dispositions import CaseError
    from renderer import bundle, load_cases_dir, render_decision_aid, render_markdown


def main(argv=None):
    ap = argparse.ArgumentParser(description="RFQ 18649 acceptance/scope disposition packets")
    ap.add_argument("--cases", required=True, help="directory of six case JSON files")
    ap.add_argument("--out", help="output directory (refused if it already exists)")
    args = ap.parse_args(argv)
    try:
        cases = load_cases_dir(args.cases)
        packed = bundle(cases)
    except (CaseError, OSError, json.JSONDecodeError) as exc:
        sys.stderr.write("REFUSED: %s\n" % exc)
        return 2
    if args.out:
        if os.path.exists(args.out):
            sys.stderr.write("REFUSED: output already exists (%s)\n" % args.out)
            return 2
        os.makedirs(args.out)
        with open(os.path.join(args.out, "bundle.json"), "w", encoding="utf-8") as fh:
            json.dump(packed, fh, indent=2, sort_keys=True)
            fh.write("\n")
        with open(os.path.join(args.out, "decision_aid.md"), "w", encoding="utf-8") as fh:
            fh.write(render_decision_aid())
        for item in packed["cases"]:
            cid = item["case"]["id"].lower()
            with open(os.path.join(args.out, cid + ".md"), "w", encoding="utf-8") as fh:
                fh.write(render_markdown(item))
            with open(os.path.join(args.out, cid + ".json"), "w", encoding="utf-8") as fh:
                json.dump(item, fh, indent=2, sort_keys=True)
                fh.write("\n")
        index = ["# UIOWA-139 disposition packets", ""]
        for item in packed["cases"]:
            c = item["case"]
            index.append(
                "- [%s](%s.md) — %s (`%s`)"
                % (c["id"], c["id"].lower(), c["title"], c["disposition"])
            )
        index.append("")
        with open(os.path.join(args.out, "00-INDEX.md"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(index) + "\n")
    else:
        sys.stdout.write(render_decision_aid())
        for item in packed["cases"]:
            sys.stdout.write("\n")
            sys.stdout.write(render_markdown(item))
    return 0


if __name__ == "__main__":
    sys.exit(main())
