#!/usr/bin/env python3
"""host/render_contract.py — a workflow file is not a passing run.

Slack 1787637223.298509 (SPECTER render-QA taking): claimed isolated
current-main reconciliation and workflow-contract tests after "finding
no live render_check claim." The claim was stale. The YAML gate and
p/rivet-ship-render-check-20260825-01.md were already on official
main. The leftover was the contract: three Chromium runs failed
(visual.html Page.goto timeout 45000ms) because render_check.py's
HTTP server was single-threaded.

Talk about the taking without this leftover is CLAIMED. A YAML file
with a failed last main run is NOT_LANDED. Threading shipped plus a
failed last run is CANDIDATE. A successful last main run is
INTEGRATED. titan: NOT_WRITTEN. No auth.

  python3 host/render_contract.py
  python3 host/render_contract.py --root .
  python3 host/render_contract.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


COMMAND = (
    "python3 render_check.py 8bit.html 8walk.html pixel.html visual.html "
    "--receipt receipts/render"
)
PAGES = ("8bit.html", "8walk.html", "pixel.html", "visual.html")
WORKFLOW = ".github/workflows/render-check.yml"
TOOL = "render_check.py"
DEFAULT_CATALOG = os.path.join("ground", "RENDER_CONTRACT.json")
SLACK_TS = "1787637223.298509"
FAILED_MAIN_RUN = 32812516738


def load_catalog(text):
    """Parse the run catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"runs": [], "error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"runs": [], "error": "catalog is not an object"}
    errors = []
    raw_runs = data.get("runs")
    if raw_runs is None:
        raw_runs = []
    elif not isinstance(raw_runs, list):
        errors.append("runs is not a list")
        raw_runs = []
    runs = []
    for item in raw_runs:
        if not isinstance(item, dict):
            continue
        run_id = item.get("id")
        conclusion = str(item.get("conclusion") or "").strip().lower()
        branch = str(item.get("head_branch") or item.get("branch") or "").strip()
        event = str(item.get("event") or "").strip()
        if run_id in (None, ""):
            continue
        try:
            run_id = int(run_id)
        except (TypeError, ValueError):
            continue
        runs.append(
            {
                "id": run_id,
                "conclusion": conclusion,
                "head_branch": branch,
                "event": event,
            }
        )
    raw_hands_off = data.get("hands_off")
    if raw_hands_off is None:
        hands_off = []
    elif isinstance(raw_hands_off, list):
        hands_off = list(raw_hands_off)
    else:
        errors.append("hands_off is not a list")
        hands_off = []
    catalog = {
        "runs": runs,
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "source_id": str(data.get("source_id") or "").strip(),
        "hands_off": hands_off,
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
    }
    if errors:
        catalog["error"] = "; ".join(errors)
    return catalog


def folded_body(text):
    """YAML line continuations still name the same command."""
    return " ".join(str(text or "").replace("\\", " ").split())


def parse_workflow(text):
    """Pure parser so tests do not need Chromium."""
    body = str(text or "")
    pages = [page for page in PAGES if page in body]
    return {
        "has_exact_command": COMMAND in folded_body(body),
        "pages": pages,
        "page_count": len(pages),
        "has_playwright": "playwright" in body,
        "has_receipt": "receipt" in body.lower() or "upload-artifact" in body,
        "has_workflow_dispatch": "workflow_dispatch" in body,
    }


def parse_tool(text):
    """The hang leftover lives in the checker, not the YAML."""
    body = str(text or "")
    return {
        "has_threading": "ThreadingMixIn" in body,
        "swallows_broken_pipe": "BrokenPipeError" in body,
    }


def last_main_run(runs):
    """Prefer the newest push-to-main row. Catalog is newest-first."""
    rows = list(runs or [])
    for row in rows:
        if row.get("head_branch") == "main" and row.get("event") == "push":
            return row
    for row in rows:
        if row.get("head_branch") == "main":
            return row
    return rows[0] if rows else None


def classify(row):
    """Turn a measured workflow + tool + run catalog into a desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": "render-check contract body not read. Absence was not stillness.",
        }
    if not row.get("has_exact_command") or int(row.get("page_count") or 0) < len(PAGES):
        missing = [page for page in PAGES if page not in (row.get("pages") or [])]
        return {
            "state": "NOT_LANDED",
            "note": (
                "workflow contract is missing the exact free-runner command. "
                "Missing: %s. SPECTER / workflow-contract talk is CLAIMED."
            )
            % (", ".join(missing) if missing else "exact command"),
        }
    last = last_main_run(row.get("runs"))
    conclusion = str((last or {}).get("conclusion") or "").strip().lower()
    run_id = (last or {}).get("id")
    threaded = bool(row.get("has_threading") and row.get("swallows_broken_pipe"))
    if conclusion == "failure" and not threaded:
        return {
            "state": "NOT_LANDED",
            "note": (
                "last main render-check run %s failed. Single-thread HTTP "
                "plus BrokenPipe left visual.html at Page.goto timeout. "
                "A workflow file is not a passing run. SPECTER taking is CLAIMED."
            )
            % (run_id or FAILED_MAIN_RUN),
        }
    if conclusion == "failure" and threaded:
        return {
            "state": "CANDIDATE",
            "note": (
                "last main render-check run %s failed. ThreadingMixIn + "
                "BrokenPipe swallow shipped. A workflow file is not a passing run."
            )
            % (run_id or FAILED_MAIN_RUN),
        }
    if conclusion == "success":
        return {
            "state": "INTEGRATED",
            "note": (
                "workflow contract names the exact command and last main "
                "run %s succeeded. A Slack taking is still not the file."
            )
            % (run_id or "ok"),
        }
    if not threaded:
        return {
            "state": "NOT_LANDED",
            "note": (
                "render_check.py still uses a single-thread HTTP server. "
                "SPECTER / workflow-contract talk is CLAIMED until the hang ships."
            ),
        }
    return {
        "state": "CANDIDATE",
        "note": (
            "workflow contract and threading leftover are on this tree. "
            "A workflow file is not a run URL."
        ),
    }


def measure_root(root):
    root = os.path.abspath(root)
    workflow_path = os.path.join(root, WORKFLOW)
    tool_path = os.path.join(root, TOOL)
    catalog_path = os.path.join(root, DEFAULT_CATALOG)
    row = {
        "measured": True,
        "workflow": WORKFLOW,
        "tool": TOOL,
        "catalog": DEFAULT_CATALOG,
        "titan": "NOT_WRITTEN",
        "slack_ts": SLACK_TS,
    }
    if os.path.isfile(workflow_path):
        with open(workflow_path, "r", encoding="utf-8", errors="replace") as handle:
            row.update(parse_workflow(handle.read()))
        row["workflow_present"] = True
    else:
        row.update(parse_workflow(""))
        row["workflow_present"] = False
    if os.path.isfile(tool_path):
        with open(tool_path, "r", encoding="utf-8", errors="replace") as handle:
            row.update(parse_tool(handle.read()))
        row["tool_present"] = True
    else:
        row.update(parse_tool(""))
        row["tool_present"] = False
    if os.path.isfile(catalog_path):
        with open(catalog_path, "r", encoding="utf-8", errors="replace") as handle:
            catalog = load_catalog(handle.read())
        row["runs"] = catalog.get("runs") or []
        row["catalog_present"] = True
        row["hands_off"] = catalog.get("hands_off") or []
        if catalog.get("error"):
            row["catalog_error"] = catalog["error"]
    else:
        row["runs"] = []
        row["catalog_present"] = False
        row["hands_off"] = []
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure the render-check workflow contract, not just the YAML"
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
    missing = classify(
        {
            "measured": True,
            **parse_workflow("python3 render_check.py board.html\n"),
            **parse_tool(""),
            "runs": [],
        }
    )
    assert missing["state"] == "NOT_LANDED"
    failed_hang = classify(
        {
            "measured": True,
            **parse_workflow(
                COMMAND
                + "\nplaywright\nupload-artifact\nworkflow_dispatch:\n"
            ),
            **parse_tool("class Server(socketserver.TCPServer):\n    pass\n"),
            "runs": [
                {
                    "id": FAILED_MAIN_RUN,
                    "conclusion": "failure",
                    "head_branch": "main",
                    "event": "push",
                }
            ],
        }
    )
    assert failed_hang["state"] == "NOT_LANDED"
    assert "32812516738" in failed_hang["note"]
    failed_fixed = classify(
        {
            "measured": True,
            **parse_workflow(
                COMMAND
                + "\nplaywright\nupload-artifact\nworkflow_dispatch:\n"
            ),
            **parse_tool(
                "class Server(socketserver.ThreadingMixIn, socketserver.TCPServer):\n"
                "    daemon_threads = True\n"
                "except BrokenPipeError:\n    return\n"
            ),
            "runs": [
                {
                    "id": FAILED_MAIN_RUN,
                    "conclusion": "failure",
                    "head_branch": "main",
                    "event": "push",
                }
            ],
        }
    )
    assert failed_fixed["state"] == "CANDIDATE"
    ok = classify(
        {
            "measured": True,
            **parse_workflow(
                COMMAND
                + "\nplaywright\nupload-artifact\nworkflow_dispatch:\n"
            ),
            **parse_tool("ThreadingMixIn\nBrokenPipeError\n"),
            "runs": [
                {
                    "id": 9,
                    "conclusion": "success",
                    "head_branch": "main",
                    "event": "push",
                }
            ],
        }
    )
    assert ok["state"] == "INTEGRATED"
    catalog = load_catalog(
        json.dumps(
            {
                "runs": [
                    {
                        "id": FAILED_MAIN_RUN,
                        "conclusion": "failure",
                        "head_branch": "main",
                        "event": "push",
                    }
                ]
            }
        )
    )
    assert last_main_run(catalog["runs"])["id"] == FAILED_MAIN_RUN
    return True


if __name__ == "__main__":
    sys.exit(main())
