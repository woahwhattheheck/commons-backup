#!/usr/bin/env python3
"""Read the verified historical crosswalk without claiming live prize status.

This is an offline view of the original instrument, not a second verifier,
research selector, theorem prover, source downloader, or payment action.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import verify_crosswalk as vc


LIMITS = (
    "This is the retained September 18, 2026 snapshot, not a live-source check.",
    "Catalog value is not eligibility, an award, a receivable, cash, or revenue.",
    "Parallel platform rewards are excluded, not assumed payable together.",
    "A present Lean file is a recorded target, not a completed or accepted proof.",
    "A missing canonical path does not establish absence of formalization elsewhere.",
    "The ownership census is historical; refresh it before taking any theorem lane.",
)


def report_snapshot(doc: dict) -> dict:
    """Validate with the canonical verifier, then detach the displayed records."""
    digest = vc.verify(doc)
    snapshot = json.loads(json.dumps(doc, ensure_ascii=False))
    rows = snapshot["problems"]
    return {
        **snapshot,
        "status": "RETAINED_SNAPSHOT_VERIFIED",
        "snapshot_sha256": digest,
        "live_source_check_performed": False,
        "summary": {
            "row_count": len(rows),
            "catalog_value_usd": sum(r["reward_usd"] for r in rows),
            "parallel_rewards_included": False,
            "formal_present_count": sum(r["formal_target"]["status"] == "PRESENT" for r in rows),
            "formal_missing_count": sum(r["formal_target"]["status"] == "MISSING_AT_CANONICAL_PATH" for r in rows),
            "ppl_mapped_count": sum(r["ppl_id"] is not None for r in rows),
            "historical_active_take_count": sum(r["commons_ownership"]["status"] == "ACTIVE_TAKE" for r in rows),
        },
        "limits": list(LIMITS),
        "before_any_new_theorem_take": [
            "Read current primary sponsor terms and problem status.",
            "Check the current formal-source commit and exact target.",
            "Repeat the Commons ownership census and reconcile any active lane.",
            "Keep each sponsor's eligibility, submission and payment decision separate.",
        ],
    }


def markdown(report: dict) -> str:
    """Render a verified report produced here; this is presentation, not proof."""
    summary = report["summary"]
    lines = [
        "# Retained Erdős crosswalk — operator rehearsal",
        "",
        f"Snapshot: **{report['snapshot_date']}**. Live source check: **not performed**.",
        "",
        f"{summary['row_count']} retained rows; ${summary['catalog_value_usd']:,} historical catalog value, **not money received**.",
        f"Formal targets: {summary['formal_present_count']} present / {summary['formal_missing_count']} missing at the recorded canonical paths. "
        f"PPL mappings: {summary['ppl_mapped_count']}; historical active takes: {summary['historical_active_take_count']}.",
        "",
        "Rows follow the retained problem-number order, not a recommendation or expected-return ranking.",
        "",
        "| Erdős | Historical catalog value | Reward scope | Recorded formal target | PPL | Historical ownership |",
        "|---:|---:|---|---|---|---|",
    ]
    for row in report["problems"]:
        formal = row["formal_target"]
        target = f"`{formal['theorem']}`" if formal["status"] == "PRESENT" else "MISSING at canonical path"
        ppl = str(row["ppl_id"]) if row["ppl_id"] is not None else "UNKNOWN / not mapped"
        owner = row["commons_ownership"]
        custody = owner["carrier"] if owner["status"] == "ACTIVE_TAKE" else "No active take observed then"
        lines.append(f"| {row['erdos_number']} | ${row['reward_usd']:,} | {row['reward_scope']} | {target} | {ppl} | {custody} |")
    lines += [
        "",
        "## Three distinctions an operator must retain",
        "",
        "**#64:** the snapshot records an active proof-backend task. Its PPL mapping is unknown, not zero and not an invented mapping. This tool does not transfer its ownership.",
        "",
        "**#625:** the $1,000 catalog maximum is explicitly `disproof_maximum`. It is not a symmetric reward for either answer; no other reward is inferred here.",
        "",
        "**#625, #687 and #1191:** missing canonical files are preserved as missing at that commit. They are not converted to unprovable, solved, or absent everywhere.",
        "",
        "## What this check establishes",
        "",
        f"The supplied canonical JSON matches the retained snapshot identity `{report['snapshot_sha256']}`.",
        "Object-key order, indentation and Unicode escaping do not change that identity; row order and every retained field do.",
        "Editing a source commit, blob, theorem, PPL mapping, ownership record, amount, note or date is a new snapshot, not a successful verification of this one.",
        "",
        "## What still needs a fresh human or research decision",
        "",
    ]
    lines.extend(f"- {item}" for item in report["before_any_new_theorem_take"])
    lines += ["", "## Limits", ""]
    lines.extend(f"- {item}" for item in report["limits"])
    lines += ["", "For complete retained locators, blob identities, titles and notes, use `--format json`.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path(__file__).with_name("crosswalk.json"))
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args(argv)
    try:
        report = report_snapshot(vc.load_strict(args.input))
        text = markdown(report) if args.format == "markdown" else json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    except vc.CrosswalkError as exc:
        print(f"CROSSWALK_ERROR: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
