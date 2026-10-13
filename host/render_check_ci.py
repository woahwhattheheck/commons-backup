#!/usr/bin/env python3
"""host/render_check_ci.py — is render_check.py wired to current-main CI?

Slack 1787634739.531389 (DEMON 8-bit/pixel utilization report):
render_check.py caught real invisible-sprite / pileup / dead-reply.js
failures but was NOT wired to current-main CI. This leftover measures
the free-runner visual-diff gate. Talk about the gate without the
workflow is CLAIMED. Missing workflow is NOT_LANDED.

It does not invent Chromium success. A workflow file is not a run URL.
titan: NOT_WRITTEN. No auth.

  python3 host/render_check_ci.py
  python3 host/render_check_ci.py --root .
  python3 host/render_check_ci.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


REQUIRED_PAGES = ("8bit.html", "8walk.html", "pixel.html", "visual.html")
WORKFLOW = ".github/workflows/render-check.yml"
TOOL = "render_check.py"


def parse_workflow(text):
    """Pure parser so tests do not need the live tree or Chromium."""
    body = str(text or "")
    pages = [page for page in REQUIRED_PAGES if page in body]
    return {
        "measured": True,
        "pages": pages,
        "page_count": len(pages),
        "has_tool": TOOL in body,
        "has_playwright": "playwright" in body,
        "has_receipt": "receipt" in body.lower() or "upload-artifact" in body,
        "has_workflow_dispatch": "workflow_dispatch" in body,
        "titan": "NOT_WRITTEN",
    }


def classify(row):
    """Turn a measured workflow into a land-desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": "render-check workflow body not read. Absence was not stillness.",
        }
    pages = int(row.get("page_count") or 0)
    if (
        row.get("has_tool")
        and pages == len(REQUIRED_PAGES)
        and row.get("has_playwright")
        and row.get("has_receipt")
    ):
        return {
            "state": "INTEGRATED",
            "note": (
                "free-runner visual-diff gate names %s plus %s and publishes "
                "Chromium receipts. A workflow file is not a run URL. Talk is not a land."
            )
            % (TOOL, ", ".join(REQUIRED_PAGES)),
        }
    missing = [page for page in REQUIRED_PAGES if page not in (row.get("pages") or [])]
    return {
        "state": "NOT_LANDED",
        "note": (
            "render_check.py is not a current-main CI gate. Missing: %s. "
            "Visual-diff / Chromium-receipt talk is CLAIMED until the leftover ships."
        )
        % (", ".join(missing) if missing else "tool/playwright/receipt"),
    }


def measure_root(root):
    path = os.path.join(os.path.abspath(root), WORKFLOW)
    if not os.path.isfile(path):
        return {
            "measured": True,
            "pages": [],
            "page_count": 0,
            "has_tool": False,
            "has_playwright": False,
            "has_receipt": False,
            "has_workflow_dispatch": False,
            "workflow": WORKFLOW,
            "present": False,
            "titan": "NOT_WRITTEN",
        }
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        row = parse_workflow(handle.read())
    row["workflow"] = WORKFLOW
    row["present"] = True
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure whether render_check.py is a current-main CI gate"
    )
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the stdlib fixtures and exit",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    row = measure_root(args.root)
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    missing = classify(parse_workflow("# battery only\npython3 test_land_desk.js\n"))
    assert missing["state"] == "NOT_LANDED"
    wired = classify(
        parse_workflow(
            "\n".join(
                [
                    "name: render-check",
                    "on:",
                    "  workflow_dispatch:",
                    "jobs:",
                    "  chromium:",
                    "    steps:",
                    "      - run: python3 -m pip install playwright",
                    "      - run: python3 render_check.py 8bit.html 8walk.html pixel.html visual.html --receipt receipts/render",
                    "      - uses: actions/upload-artifact@v4",
                ]
            )
        )
    )
    assert wired["state"] == "INTEGRATED"
    assert "8bit.html" in wired["note"]
    return True


if __name__ == "__main__":
    sys.exit(main())
