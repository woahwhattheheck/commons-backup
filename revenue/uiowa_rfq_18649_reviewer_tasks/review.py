#!/usr/bin/env python3
"""Task-oriented reading and version-bound continuation of a discussion bundle."""
from __future__ import annotations

import argparse
import copy
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "uiowa_rfq_18649_discussion"))
import discussion

register = discussion.register
DEFAULT = HERE.parent / "uiowa_rfq_18649_discussion/examples"
EDITABLE = set(register.REC_FIELDS) - {"recommendation_id", "finding_ids", "scope"}


def source_sha(pack):
    return pack["sources"]["inputs/register.json"]["sha256"]


def table(value):
    return str(value).replace("|", "\\|").replace("\n", " ") if value is not None else "UNKNOWN"


def show(pack, identity):
    card = next((c for c in pack["cards"] if c["card_id"] == identity), None)
    if card is None:
        raise ValueError("unknown card ID: " + identity)
    # Reuse the delivered renderer, with only the requested card selected.
    selected = dict(pack, cards=[card])
    return discussion.render_markdown(selected)


def compare(pack):
    out = ["# Group comparison", "", pack["notice"], "",
           "States below come from the supplied inspection report. No cross-group rank or maturity average is inferred.", "",
           "| Group | Dimension | Status | Reason |", "|---|---|---|---|"]
    for card in pack["cards"]:
        if not card["card_id"].startswith("cell:"):
            continue
        cell = pack["citations"][card["card_id"]]["original"]
        out.append("| " + " | ".join(table(x) for x in (cell["group"], cell["dimension"],
                   cell["status"], "; ".join(cell["reason_codes"]))) + " |")
    out += ["", "Report evaluated at: " + pack["report_evaluated_at"],
            "Report receipt: " + pack["report_receipt"],
            "Register source SHA-256: " + source_sha(pack), ""]
    return "\n".join(out)


def tasks(pack):
    out = ["# Reviewer continuation", "", pack["notice"], "",
           "The bundle is source-bound and semantically checked. These are operator tasks, not a participant usability study.", "",
           "Register source SHA-256: " + source_sha(pack), "", "## Five tasks", ""]
    findings = [c for c in pack["cards"] if c["card_id"].startswith("finding:")]
    unknown = [c for c in pack["cards"] if c["state"].startswith("HOLD_")]
    recs = [c for c in pack["cards"] if c["card_id"].startswith("recommendation:")]
    preferred = next((c for c in recs if c["state"] == "PROPOSED_WITH_UNKNOWNS"), recs[0] if recs else None)
    out += ["1. Locate support: use `show --card ID` for " + (findings[0]["card_id"] if findings else "a finding (none supplied)") + ". Read its exact excerpts and limitations.",
            "2. Compare groups: use `compare`. Compare statuses and reasons; the report does not authorize a league table.",
            "3. Explain an unknown: use `show --card ID` for " + (unknown[0]["card_id"] if unknown else "a held cell (none supplied)") + ". Follow its source/reason fields.",
            "4. Revise a recommendation: use `revise --recommendation ID --changes FILE --expected-sha256 HASH`. "
            "Preview first; add `--out NEW_DIRECTORY` to save a new version. Suggested editable record: "
            + (preferred["card_id"].split(":", 1)[1] if preferred else "NONE") + ".",
            "5. Locate roadmap impact: read the preview's before/after item, then open the new bundle's discussion.html "
            "and register/roadmap.json. Preserved unknowns remain planning work.", "",
            "Finding identity, evidence links and recommendation scope are preserved by this editor. "
            "Changing those requires the canonical register workflow and a new evidence mapping, not a planning-field patch.", ""]
    return "\n".join(out)


def proposal(pack, recommendation_id, changes, expected_sha):
    actual = source_sha(pack)
    if expected_sha != actual:
        raise ValueError("STALE_EDIT: expected register SHA-256 does not match this bundle; read its current tasks first")
    if not isinstance(changes, dict) or not changes or set(changes) - EDITABLE:
        raise ValueError("changes must be a nonempty object using only: " + ", ".join(sorted(EDITABLE)))
    # Read the source already bound and validated by discussion.verify_bundle.
    old = pack["roadmap"]["source_register"]
    updated = copy.deepcopy(old)
    rec = next((r for r in updated["recommendations"] if r["recommendation_id"] == recommendation_id), None)
    if rec is None:
        raise ValueError("unknown recommendation ID: " + recommendation_id)
    before = copy.deepcopy(rec)
    rec.update(changes)
    updated = register.normalize(updated)
    changed = {key: {"before": before[key], "after": rec[key]} for key in sorted(changes) if before[key] != rec[key]}
    if not changed:
        raise ValueError("NO_CHANGE: proposed fields already have these values")
    def item(reg):
        return next(x for x in register.roadmap_view(reg)["items"] if x["recommendation_ref"] == recommendation_id)
    content = register.dumps(updated).encode("utf-8")
    return updated, dict(schema="uiowa.reviewer-revision.v1", status="DRAFT_PROPOSAL",
        notice=discussion.NOTICE, recommendation_id=recommendation_id, changes=changed,
        source_register_sha256=actual, revised_register_sha256=discussion.sha(content),
        source_report_receipt=pack["report_receipt"], finding_ids_preserved=rec["finding_ids"],
        scope_preserved=rec["scope"], roadmap_before=item(old), roadmap_after=item(updated),
        effort_before=register.summary(old), effort_after=register.summary(updated),
        remaining_review_items=register.review_items(updated))


def save_revision(bundle, pack, updated, receipt, out):
    # Capture the bound source snapshots, then rebuild from those bytes. Do not
    # trust a pathname that could change between inspection and publication.
    raw_sources = {}
    for name, binding in pack["sources"].items():
        raw = discussion.read(bundle / name)
        if discussion.sha(raw) != binding["sha256"]:
            raise ValueError("SOURCE_CHANGED_DURING_EDIT:" + name)
        raw_sources[name] = raw
    with tempfile.TemporaryDirectory(prefix="uiowa-review-") as work:
        root = Path(work)
        for name, raw in raw_sources.items():
            dest = root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
        (root / "inputs/register.json").write_text(register.dumps(updated), encoding="utf-8")
        revised, snapshots = discussion.build(root / "inputs/search/manifest.json", root / "inputs/report.json", root / "inputs/register.json")
    # Reject existing destinations rather than silently replacing a prior draft.
    out.mkdir(parents=True, exist_ok=False)
    for name, raw in snapshots.items():
        dest = out / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("xb") as stream:
            stream.write(raw)
    payloads = {"discussion.json": discussion.dumps(revised), "discussion.md": discussion.render_markdown(revised),
                "discussion.html": discussion.render_html(revised), "revision.json": discussion.dumps(receipt),
                "reviewer-tasks.md": tasks(revised)}
    with (out / "source-register.json").open("xb") as stream:
        stream.write(raw_sources["inputs/register.json"])
    for name, text in payloads.items():
        with (out / name).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
    # Canonical editable CSV, full register, report and roadmap; no projection fork.
    register.export_bundle(updated, out / "register")
    return revised


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bundle", type=Path, default=DEFAULT, help="Source-bound discussion export directory")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("tasks")
    sub.add_parser("compare")
    s = sub.add_parser("show")
    s.add_argument("--card", required=True)
    r = sub.add_parser("revise")
    r.add_argument("--recommendation", required=True)
    r.add_argument("--changes", type=Path, required=True, help="JSON object replacing selected editable fields")
    r.add_argument("--expected-sha256", required=True, help="Exact register source digest printed by tasks")
    r.add_argument("--out", type=Path, help="New output directory; omit for a read-only preview")
    args = ap.parse_args()
    pack = discussion.verify_bundle(args.bundle)
    if args.command == "tasks":
        print(tasks(pack), end="")
    elif args.command == "compare":
        print(compare(pack), end="")
    elif args.command == "show":
        print(show(pack, args.card), end="")
    else:
        changes = register.loads(discussion.read(args.changes).decode("utf-8"))
        updated, receipt = proposal(pack, args.recommendation, changes, args.expected_sha256)
        if args.out is not None:
            save_revision(args.bundle, pack, updated, receipt, args.out)
            receipt = dict(receipt, publication="NEW_DRAFT_WRITTEN", output=str(args.out))
        else:
            receipt = dict(receipt, publication="PREVIEW_ONLY")
        print(discussion.dumps(receipt), end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError, RecursionError) as exc:
        print("reviewer-task error: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
