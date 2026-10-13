#!/usr/bin/env python3
"""render_guide.py -- build OPERATOR_GUIDE.md from the manifest + a real survey.

The guide is generated, never hand-maintained, because a hand-maintained status
table drifts from reality within an hour on a board this busy. Regenerating is
the supported way to refresh it:

    python3 verify_kit.py --root /home/user/commons/revenue \
        --out-json /tmp/uiowa-kit-run/component_status.json \
        --out-csv  /tmp/uiowa-kit-run/component_status.csv \
        --out-md   /tmp/uiowa-kit-run/verification_log.md
    python3 render_guide.py --status /tmp/uiowa-kit-run/component_status.json --out /tmp/uiowa-kit-run/OPERATOR_GUIDE.md
"""

import argparse
import csv
import json
import os

LEGEND = """| status | what it means here | how it was decided |
|---|---|---|
| **WORKING** | the operator can run this today | `verify_kit.py` executed the component's own unittest suite (or its documented runner) in an isolated copy and saw it pass |
| **DRAFT** | exists, but do not assume it runs | no automated check ships with it, or the check failed, timed out, or needs a dependency this offline environment does not have |
| **MISSING** | a phase needs it and it is not built yet | no directory for it exists under the survey root |
| **UNMAPPED** | found on disk, not yet placed in a phase | lanes land continuously; this is a bookkeeping signal, not a quality judgement |

No status in this table was taken from a component's README. A README is its
author's claim; the status column is an execution result."""


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def status_badge(s):
    return {"WORKING": "**WORKING**", "DRAFT": "DRAFT", "MISSING": "MISSING",
            "UNMAPPED": "UNMAPPED"}.get(s, s)


def render(manifest, report, unknowns):
    by_phase = {}
    for r in report["components"]:
        by_phase.setdefault(r["phase"], []).append(r)
    c = report["counts"]

    L = []
    L.append("# RFQ 18649 — operator handoff")
    L.append("")
    L.append("> **Preparation kit for an assessment that has not been awarded.** Nothing in this")
    L.append("> repository is a University of Iowa finding, and every example input is synthetic")
    L.append("> and labelled as fiction. The kit is what an operator runs; the University's real")
    L.append("> inputs are listed at the end and are all **UNKNOWN** until supplied.")
    L.append("")
    L.append("**Read this first.** You are picking up work built by many hands. The status")
    L.append("column below is not a promise from the people who wrote each component — it is the")
    L.append("result of the recorded `verify_kit.py` survey. WORKING requires observed execution")
    L.append("on an isolated copy; missing and unexecuted components remain unproven.")
    L.append("")
    L.append("- survey root: `%s`" % report["survey_root"])
    if "generated_at_utc" in report:
        L.append("- snapshot taken (UTC): **%s** · python %s" % (report["generated_at_utc"], report["python"]))
    else:
        L.append("- normalized observation format: `%s` · python %s"
                 % (report["artifact_format"], report["python"]))
        L.append("- timestamp, physical roots and durations: retain the separate --out-run-json record")
    L.append("- **WORKING %d · DRAFT %d · MISSING %d · UNMAPPED %d**"
             % (c["WORKING"], c["DRAFT"], c["MISSING"], c["UNMAPPED"]))
    L.append("")
    L.append("## Refresh the status table before you rely on it")
    L.append("")
    L.append("```bash")
    L.append("cd revenue/uiowa_rfq_18649_operator_handoff")
    L.append("mkdir -p /tmp/uiowa-kit-run")
    L.append("python3 verify_kit.py --out-run-json /tmp/uiowa-kit-run/raw_run.json --root ../ \\")
    L.append("    --out-json /tmp/uiowa-kit-run/component_status.json \\")
    L.append("    --out-csv  /tmp/uiowa-kit-run/component_status.csv \\")
    L.append("    --out-md   /tmp/uiowa-kit-run/verification_log.md")
    L.append("python3 render_guide.py --status /tmp/uiowa-kit-run/component_status.json --out /tmp/uiowa-kit-run/OPERATOR_GUIDE.md")
    L.append("```")
    L.append("")
    L.append("`verify_kit.py` copies every lane to a temporary directory before running anything,")
    L.append("so it cannot modify work owned by another author. The copies are deleted afterwards.")
    L.append("")
    L.append("## Status legend")
    L.append("")
    L.append(LEGEND)
    L.append("")
    L.append("## The six phases at a glance")
    L.append("")
    L.append("| # | phase | components | WORKING | DRAFT | MISSING |")
    L.append("|---|---|---|---|---|---|")
    for ph in sorted(manifest["phases"], key=lambda p: p["order"]):
        rows = by_phase.get(ph["id"], [])
        L.append("| %d | [%s](#%d-%s) | %d | %d | %d | %d |" % (
            ph["order"], ph["title"], ph["order"], ph["id"].replace("_", "-"), len(rows),
            sum(1 for r in rows if r["status"] == "WORKING"),
            sum(1 for r in rows if r["status"] == "DRAFT"),
            sum(1 for r in rows if r["status"] == "MISSING")))
    L.append("")

    for ph in sorted(manifest["phases"], key=lambda p: p["order"]):
        rows = by_phase.get(ph["id"], [])
        L.append("---")
        L.append("")
        L.append("## %d. %s" % (ph["order"], ph["title"]))
        L.append("")
        L.append("%s" % ph["purpose"])
        L.append("")
        if ph.get("operator_does"):
            L.append("**What the operator does in this phase**")
            L.append("")
            for step in ph["operator_does"]:
                L.append("- %s" % step)
            L.append("")
        L.append("| component (directory under `revenue/`) | status | what it is for |")
        L.append("|---|---|---|")
        for r in sorted(rows, key=lambda r: (r["status"] != "WORKING", r["component"])):
            L.append("| `%s` | %s | %s |" % (r["component"], status_badge(r["status"]),
                                             r["role"] or "-"))
        L.append("")
        runnable = [r for r in rows if r["status"] == "WORKING" and r["check_files"]]
        runners = [r for r in rows if r["status"] == "WORKING" and not r["check_files"]]
        if runnable or runners:
            L.append("**Commands that were executed for this phase in the snapshot above**")
            L.append("")
            L.append("```bash")
            for r in runnable:
                for cf in r["check_files"]:
                    sub = os.path.dirname(cf)
                    cd = "revenue/%s%s" % (r["component"], ("/" + sub) if sub else "")
                    L.append("(cd %s && python3 -m unittest %s)"
                             % (cd, os.path.splitext(os.path.basename(cf))[0]))
            for r in runners:
                for run in r["runs"]:
                    L.append("(cd revenue/%s && %s)" % (r["component"], run["command"]))
            L.append("```")
            L.append("")
        blocked = [r for r in rows if r["status"] in ("DRAFT", "MISSING")]
        if blocked:
            L.append("**What is not ready in this phase, and why**")
            L.append("")
            for r in blocked:
                L.append("- `%s` — **%s**: %s" % (r["component"], r["status"], r["reason"]))
            L.append("")

    unmapped = by_phase.get("unassigned", [])
    L.append("---")
    L.append("")
    L.append("## Lanes discovered on disk but not yet placed in a phase")
    L.append("")
    if unmapped:
        L.append("These landed after `kit_manifest.json` was last written. Assign each one to a")
        L.append("phase in the manifest; nothing is dropped silently.")
        L.append("")
        L.append("| component | underlying observation |")
        L.append("|---|---|")
        for r in unmapped:
            L.append("| `%s` | %s |" % (r["component"], r["reason"]))
    else:
        L.append("None at the time of this snapshot: every lane found under the survey root is")
        L.append("placed in a phase by `kit_manifest.json`.")
    L.append("")

    L.append("---")
    L.append("")
    L.append("## University inputs still needed — all UNKNOWN")
    L.append("")
    L.append("Every row below is an input the kit cannot manufacture. None of them has been")
    L.append("supplied, and none of them is being approximated, defaulted, or scored as zero.")
    L.append("A component that needs one of these cannot produce a real result until it arrives.")
    L.append("")
    L.append("| id | phase | input needed | why the kit needs it | blocks | status |")
    L.append("|---|---|---|---|---|---|")
    for u in unknowns:
        L.append("| %s | %s | %s | %s | `%s` | **%s** |" % (
            u["input_id"], u["phase"], u["input_needed"], u["why_needed"],
            u["blocks_component"], u["status"]))
    L.append("")
    L.append("---")
    L.append("")
    L.append("## Limits of this handoff")
    L.append("")
    L.append("- The status table describes the recorded source snapshot and Python environment.")
    L.append("  Re-run `verify_kit.py` when inputs change; keep raw run metadata for observation time.")
    L.append("- WORKING means *the component's own check passed*. It does not mean the component")
    L.append("  is correct for the University's real evidence, and it is not a maturity rating.")
    L.append("- DRAFT on a document component means only that prose cannot be machine-checked. It")
    L.append("  is not a claim that the document is bad; it needs a human read.")
    L.append("- No component here certifies compliance, scores an individual, or ranks the")
    L.append("  University against peers, and this handoff does not add such a capability.")
    L.append("")
    return "\n".join(L).rstrip() + "\n"


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=os.path.join(here, "kit_manifest.json"))
    ap.add_argument("--status", default=os.path.join(here, "sample", "component_status.json"))
    ap.add_argument("--unknowns", default=os.path.join(here, "university_inputs.csv"))
    ap.add_argument("--out", default=os.path.join(here, "OPERATOR_GUIDE.md"))
    args = ap.parse_args(argv)
    manifest = load(args.manifest)
    report = load(args.status)
    with open(args.unknowns, encoding="utf-8") as fh:
        unknowns = list(csv.DictReader(fh))
    text = render(manifest, report, unknowns)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("wrote %s (%d bytes, %d components, %d UNKNOWN university inputs)"
          % (args.out, len(text), len(report["components"]), len(unknowns)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
