#!/usr/bin/env python3
"""Read local Git history into an explicitly bounded assessment worksheet."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60,
        env={**{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
             "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0"},
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or f"git exited {result.returncode}")
    return result.stdout


def collect(repo: Path, ref: str = "HEAD", limit: int = 500) -> dict:
    if not 1 <= limit <= 100000:
        raise ValueError("limit must be between 1 and 100000")
    pinned = git(repo, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}").strip()
    raw = git(repo, "log", "--first-parent", f"--max-count={limit + 1}",
              "-z", "--format=%H%x00%P%x00%cI%x00%s", pinned, "--")
    fields = raw.split("\0")
    if fields and fields[-1] == "":
        fields.pop()
    if len(fields) % 4:
        raise ValueError("unexpected Git history record format")
    rows = []
    for i in range(0, len(fields), 4):
        sha, parents, timestamp, subject = fields[i:i + 4]
        rows.append({"commit": sha, "parents": parents.split(), "committed_at": timestamp,
                     "subject": subject, "merge": len(parents.split()) > 1,
                     "reference_mentions": re.findall(r"(?<!\w)#\d+\b|\b[A-Z][A-Z0-9]+-\d+\b", subject)})
    limited = len(rows) > limit
    rows = rows[:limit]
    shallow = git(repo, "rev-parse", "--is-shallow-repository").strip() == "true"
    return {
        "schema": "source-control-history/v1", "pinned_commit": pinned,
        "scope": {"first_parent_only": True, "limit": limit, "limit_reached": limited,
                  "shallow_repository": shallow, "network_requested": False,
                  "history_complete": not limited and not shallow},
        "observed": {"commits": len(rows), "merge_commits": sum(r["merge"] for r in rows),
                     "subjects_with_reference_mentions": sum(bool(r["reference_mentions"]) for r in rows),
                     "newest_in_traversal": rows[0]["committed_at"] if rows else None,
                     "oldest_in_traversal": rows[-1]["committed_at"] if rows else None},
        "unknown": ["repository ownership and administrator continuity",
                    "deleted branches, pull requests, reviews and squashed branch topology",
                    "conflict-resolution quality and time spent",
                    "offsite restore success and recovery objectives",
                    "validity of referenced issues and deployment outcomes"],
        "commits": rows,
    }


def worksheet(report: dict) -> list[dict]:
    facts = report["observed"]
    evidence = "history.json @ " + report["pinned_commit"]
    definitions = [
        ("Repository ownership", "UNKNOWN: commit attribution does not establish administrative ownership",
         "Named accountable owner, backup operator and observed transfer exercise", "Map responsibility and rehearse transfer", "2–4 staff hours", "Repository stakeholders available"),
        ("Branching", f"{facts['merge_commits']} merge commits on the selected first-parent history; branch lifetime UNKNOWN",
         "Branch purpose, release constraints and branch/deletion records", "Compare short-lived and release branches against release obligations", "3–6 staff hours", "At least one representative release and its constraints"),
        ("Integration frequency", f"{facts['commits']} observed first-parent commits; cadence target and full interval UNKNOWN",
         "Representative observation window and definition of an integration", "Agree a context-specific integration interval and inspect exceptions", "2–3 staff hours", "Team capacity and release dependency information"),
        ("Conflict handling", "UNKNOWN: a merge commit alone does not show whether a conflict occurred",
         "An observed conflict, resolution decision and subsequent behavior", "Rehearse a representative conflict with the team", "2–4 staff hours", "Disposable repo and a participant who owns intended behavior"),
        ("Traceability", f"{facts['subjects_with_reference_mentions']} subjects contain reference-like text; target validity UNKNOWN",
         "Sample change-to-requirement-to-release links with reachable target evidence", "Adopt a minimal change rationale and stable reference convention", "2–5 staff hours", "A shared work identifier and an agreed release record"),
        ("Recoverability", "UNKNOWN: local history availability is not an independently demonstrated restore",
         "Independent restore result, objective and recovered-ref comparison", "Rehearse restore from an independently retained copy", "4–8 staff hours", "Backup operator, restore destination and recovery objectives"),
    ]
    rows = [{"practice": p, "observation": o, "source": evidence, "evidence_needed": need,
             "improvement_option": option, "effort_assumption": effort,
             "adoption_condition": condition, "assessment": "UNASSESSED"}
            for p, o, need, option, effort, condition in definitions]
    demo = report.get("demonstration")
    if demo:
        rows[1]["observation"] = "FICTIONAL DEMONSTRATION: " + demo["branch_pattern"]
        rows[2]["observation"] += "; scripted dates do not measure integration cadence"
        rows[3]["observation"] = (
            "FICTIONAL DEMONSTRATION: conflict resolved at " + demo["resolution_commit"]
            if demo["conflict_observed"] else
            "FICTIONAL DEMONSTRATION: this integration completed without a conflict"
        )
        rows[5]["observation"] = (
            "FICTIONAL DEMONSTRATION: local content recovered; independent offsite restore UNKNOWN"
        )
    return rows


def write_report(report: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=False)
    (out / "history.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    rows = worksheet(report)
    with (out / "worksheet.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--out", type=Path, required=True, help="new output directory")
    args = parser.parse_args(argv)
    try:
        report = collect(args.repo, args.ref, args.limit)
        write_report(report, args.out)
        print(json.dumps({"output": str(args.out), "pinned_commit": report["pinned_commit"],
                          "observed": report["observed"], "scope": report["scope"]}))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"source-control assessment: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
