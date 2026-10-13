#!/usr/bin/env python3
"""Integrated AI decision case: quality, lifecycle and economics in one run.

    python3 ai_decision_case.py --case examples/beneficial.json
    python3 ai_decision_case.py --case examples/unfavourable.json --sweep
    python3 ai_decision_case.py --case examples/beneficial.json \
        --set analyst_hourly_cost=40 --diff
    python3 ai_decision_case.py --case examples/undecidable.json --format json

Exit status
  0  the case ran and its explanation passed the citation audit
  1  the explanation failed the audit -- an unsourced or dangling quantity was
     emitted, which is a defect in this tool and not something to ship past
  2  the case could not be loaded

Python 3 standard library only. No network. No clock, no RNG, sorted traversal:
two runs on the same case are byte-identical.
"""
from __future__ import annotations

import argparse
import json
import sys

import explain
import export
import sensitivity
from case import decide
from model import CaseLoadError, load_case


def _apply_sets(case, assignments):
    for raw in assignments or []:
        if "=" not in raw:
            raise ValueError(f"--set expects name=value, got {raw!r}")
        name, value = raw.split("=", 1)
        try:
            case = sensitivity.with_assumption(case, name.strip(), float(value))
        except (KeyError, ValueError) as exc:
            raise ValueError(f"--set {raw!r}: {exc}") from exc
    return case


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--case", required=True, help="path to a synthetic case JSON file")
    p.add_argument("--format", default="markdown", choices=["markdown", "json", "text"])
    p.add_argument("--set", action="append", dest="sets", metavar="NAME=VALUE",
                   help="override an assumption and re-run (repeatable)")
    p.add_argument("--sweep", action="store_true",
                   help="classify every assumption and report the break-even margin")
    p.add_argument("--diff", action="store_true",
                   help="with --set, print the line-level explanation diff")
    p.add_argument("--out", help="write JSON, Markdown and CSV artifacts here")
    args = p.parse_args(argv)

    try:
        base_case = load_case(args.case)
        case = _apply_sets(base_case, args.sets)
    except (OSError, KeyError, ValueError, TypeError) as exc:
        print(f"error: could not load case: {exc}", file=sys.stderr)
        return 2

    decision = decide(case)
    text = explain.render(case, decision)
    problems = explain.audit_explanation(text, case)

    payload = {
        "input_basis": "SYNTHETIC",
        "result_basis": "MODELED_NOT_OBSERVED",
        "institution_finding": False,
        "spend_authorized": False,
        "effective_case": export.case_document(case),
        "decision": decision.to_dict(),
        "explanation_audit": {
            "passed": not problems,
            "problems": problems,
            "checked_lines_rule": "every line stating a quantity must cite a record "
                                  "id, and every cited id must resolve to a record "
                                  "in this case",
        },
    }
    if args.sweep:
        payload["assumption_classification"] = sensitivity.classify_assumptions(case)
        payload["verdict_margin"] = sensitivity.find_verdict_flip(case)
    if args.diff and args.sets:
        before = explain.render(base_case, decide(base_case))
        payload["explanation_diff"] = sensitivity.explanation_diff(before, text)

    if args.out:
        try:
            export.write_outputs(args.out, case, decision, payload, text)
        except (OSError, ValueError) as exc:
            print(f"error: could not write outputs: {exc}", file=sys.stderr)
            return 2

    if args.format == "json":
        sys.stdout.write(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    else:
        sys.stdout.write(text)
        sys.stdout.write("\n")
        if args.sweep:
            sys.stdout.write("## Which assumptions can change the answer\n\n")
            sys.stdout.write("| assumption | classification | verdict at low | "
                             "verdict at high |\n|---|---|---|---|\n")
            for row in payload["assumption_classification"]:
                sys.stdout.write(
                    f"| {row['assumption']} | {row['classification']} | "
                    f"{row['verdict_at_low']} | {row['verdict_at_high']} |\n")
            sys.stdout.write("\n" + payload["verdict_margin"]["note"] + "\n\n")
        if problems:
            sys.stdout.write("## Explanation audit: FAILED\n\n")
            for problem in problems:
                sys.stdout.write(f"- {problem}\n")
            sys.stdout.write("\n")
        else:
            sys.stdout.write("Explanation audit: PASSED — every quantity above "
                             "cites a record in this case.\n")

    if "explanation_diff" in payload and args.format != "json":
        sys.stdout.write("\n## What changed when the assumption moved\n\n```\n")
        diff = payload["explanation_diff"]
        sys.stdout.write("\n".join(diff) if diff else
                         "(no line of the explanation changed)")
        sys.stdout.write("\n```\n")

    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
