#!/usr/bin/env python3
"""Compare parent-compiler inspection reports without promoting evidence authority.

Only the parent compiler verifies reports. This module compares verified records,
retains their receipts, and suggests review questions; it does not score practices.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import html
import os
from pathlib import Path
import stat
import sys
from typing import Any

PARENT = Path(__file__).resolve().parent.parent / "uiowa_rfq_18649_workshare"
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))
from workshare_contract import (  # noqa: E402
    ContractError, DIMENSIONS, GROUPS, MAX_INPUT_BYTES, MODE_UNTRUSTED,
    _external_authority, canonical_json_bytes, loads_strict,
)
from workshare_verify import verify_report_integrity  # noqa: E402

SCHEMA = "uiowa-rfq18649-inspection-diff/v1"
STATUS = "DRAFT_NON_AUTHORITATIVE"
CELL_KEYS = tuple((g, d) for g in GROUPS for d in DIMENSIONS)
FIELD_KINDS = (
    ("CONTENT_REVISION", {"source_content_sha256"}),
    ("CELL_REASSIGNMENT", {"group", "dimension"}),
    ("REFERENCE_CHANGE", {"source_ref"}),
    ("ASSESSMENT_RECORD_CHANGE", {"claim", "maturity", "confidence_bp"}),
    ("EVIDENCE_METADATA_CHANGE", {"observed_at", "evidence_kind"}),
)
FOLLOW_UPS = {
    "HOLD_MISSING_EVIDENCE": "Identify evidence for this cell; missing records do not establish poor practice.",
    "HOLD_CONFLICT": "Reconcile the differing source assessments while retaining both accounts.",
    "HOLD_STALE_EVIDENCE": "Request an appropriately dated observation; do not infer a practice regression from age.",
}


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def key(row: dict[str, Any]) -> tuple[str, str]:
    return row["group"], row["dimension"]


def _snapshot(raw: Any) -> dict[str, Any]:
    # Copy first: outputs must not alias caller data. Callers must not mutate a
    # report concurrently with this copy; this library does not own their memory.
    value = copy.deepcopy(raw)
    if type(value) is not dict or value.get("mode") != MODE_UNTRUSTED:
        raise ContractError("comparison requires a parent UNTRUSTED_INSPECTION report")
    result = verify_report_integrity(value)  # Full semantic recompile, no trusted root.
    if (result["current_authority_verified"] is not False
            or value["trust"]["current_evidence_review_authority"] is not False):
        raise ContractError("inspection unexpectedly carries current authority")
    cells = value["assessment_matrix"]
    if len(cells) != len(CELL_KEYS) or {key(c) for c in cells} != set(CELL_KEYS):
        raise ContractError("parent report must contain the exact twelve assessment cells")
    return value


def _source_brief(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    # Claims, raw references and numeric assessments intentionally stay in the
    # original report. Hashes/IDs still require appropriate handling when private.
    return {
        "group": row["group"], "dimension": row["dimension"],
        "record_sha256": digest(row),
        "content_sha256": row["source_content_sha256"],
    }


def _source_changes(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    changes = []
    for source_id in sorted(before.keys() | after.keys()):
        old, new = before.get(source_id), after.get(source_id)
        if old == new:
            continue
        if old is None:
            fields, kinds = [], ["ADDED_SOURCE"]
        elif new is None:
            fields, kinds = [], ["REMOVED_SOURCE"]
        else:
            fields = sorted(f for f in old if old[f] != new[f])
            kinds = [name for name, members in FIELD_KINDS if members.intersection(fields)]
            substantive = set(fields) - {"authority_generation"}
            known = set().union(*(members for _, members in FIELD_KINDS))
            if substantive - known:
                kinds.append("OTHER_RECORD_CHANGE")
            if not substantive:
                kinds = ["GENERATION_REBIND_ONLY"]
        changes.append({
            "source_id": source_id, "changed_fields": fields, "kinds": kinds,
            "substantive_change": kinds != ["GENERATION_REBIND_ONLY"],
            "before": _source_brief(old), "after": _source_brief(new),
        })
    return changes


def _binding(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_receipt_sha256": report["receipt_sha256"],
        "evidence_root_sha256": report["authority_root_sha256"],
        "generation": report["evidence_authority"]["generation"],
        "evaluated_at": report["evaluated_at"],
        "mode": report["mode"],
        "aggregate_state": report["aggregate_state"],
        "status_counts": copy.deepcopy(report["status_counts"]),
    }


def compare_reports(before_raw: Any, after_raw: Any) -> dict[str, Any]:
    """Return a deterministic 12-cell delta after verifying both original reports.

    The stored evaluation times must be chronological. They are not a claim of
    present-day freshness; current verification remains the parent's concern.
    """
    before, after = _snapshot(before_raw), _snapshot(after_raw)
    if before["candidate"]["engagement"] != after["candidate"]["engagement"]:
        raise ContractError("cannot compare different engagement identities or terms")
    if before["evaluated_at"] > after["evaluated_at"]:
        raise ContractError("before report was evaluated after the after report")
    old_sources = {r["source_id"]: r for r in before["evidence_authority"]["sources"]}
    new_sources = {r["source_id"]: r for r in after["evidence_authority"]["sources"]}
    changes = _source_changes(old_sources, new_sources)
    change_by_id = {r["source_id"]: r for r in changes}
    old_cells = {key(c): c for c in before["assessment_matrix"]}
    new_cells = {key(c): c for c in after["assessment_matrix"]}
    cell_deltas, queue = [], []
    for group, dimension in CELL_KEYS:
        old, new = old_cells[group, dimension], new_cells[group, dimension]
        old_ids, new_ids = set(old["source_ids"]), set(new["source_ids"])
        relevant = [change_by_id[s] for s in sorted(old_ids | new_ids) if s in change_by_id]
        substantive = [r["source_id"] for r in relevant if r["substantive_change"]]
        status_changed = old["status"] != new["status"]
        reasons_changed = old["reason_codes"] != new["reason_codes"]
        evaluation_effect = bool((status_changed or reasons_changed) and not substantive
                                 and before["evaluated_at"] != after["evaluated_at"])
        reasons = []
        if substantive:
            reasons.append("EVIDENCE_RECORDS_CHANGED")
        if status_changed:
            reasons.append("STATUS_CHANGED")
        if reasons_changed:
            reasons.append("REASON_CODES_CHANGED")
        if evaluation_effect:
            reasons.append("EVALUATION_WINDOW_EFFECT")
        persistent_hold = new["status"] in FOLLOW_UPS and not status_changed
        row = {
            "group": group, "dimension": dimension,
            "before_status": old["status"], "after_status": new["status"],
            "before_reason_codes": list(old["reason_codes"]),
            "after_reason_codes": list(new["reason_codes"]),
            "before_source_ids": sorted(old_ids), "after_source_ids": sorted(new_ids),
            "added_source_ids": sorted(new_ids - old_ids),
            "removed_source_ids": sorted(old_ids - new_ids),
            "changed_source_ids": substantive,
            "generation_only_source_ids": [r["source_id"] for r in relevant if not r["substantive_change"]],
            "before_record_sha256s": list(old["source_record_sha256s"]),
            "after_record_sha256s": list(new["source_record_sha256s"]),
            "evidence_changed": bool(substantive),
            "status_changed": status_changed, "evaluation_window_effect": evaluation_effect,
            "changed": bool(reasons), "change_reasons": reasons,
            "persistent_hold": persistent_hold,
        }
        cell_deltas.append(row)
        questions = []
        if substantive:
            questions.append("Revisit draft findings and notes citing these source IDs; changed evidence is not automatically better or worse practice.")
        if new["status"] in FOLLOW_UPS:
            questions.append(FOLLOW_UPS[new["status"]])
        elif old["status"] in FOLLOW_UPS and status_changed:
            questions.append("Confirm why the prior hold no longer appears; this is not approval or a validated maturity gain.")
        if evaluation_effect:
            questions.append("Separate the stored evaluation-window effect from any actual change in practice.")
        if questions:
            queue.append({
                "group": group, "dimension": dimension,
                "trigger": "CHANGED_CELL" if row["changed"] else "PERSISTENT_HOLD",
                "source_ids": sorted(old_ids | new_ids), "questions": questions,
                "disposition": "UNREVIEWED",
            })
    result = {
        "schema": SCHEMA, "status": STATUS,
        "before": _binding(before), "after": _binding(after),
        "source_changes": changes, "cell_deltas": cell_deltas, "review_queue": queue,
        "summary": {
            "cells_total": len(cell_deltas),
            "cells_changed": sum(c["changed"] for c in cell_deltas),
            "cells_with_changed_evidence": sum(c["evidence_changed"] for c in cell_deltas),
            "cells_with_status_change": sum(c["status_changed"] for c in cell_deltas),
            "cells_with_evaluation_window_effect": sum(c["evaluation_window_effect"] for c in cell_deltas),
            "source_records_changed": len(changes),
            "source_records_substantively_changed": sum(c["substantive_change"] for c in changes),
            "generation_only_rebindings": sum(not c["substantive_change"] for c in changes),
            "review_queue_items": len(queue),
        },
        "interpretation": {
            "parent_semantic_integrity_verified": True,
            "evidence_authenticity_verified": False,
            "current_evidence_review_authority": False,
            "practice_improvement_inferred": False,
            "notes_automatically_transferred": False,
            "document_rename_inferred": False,
        },
        "external_authority": _external_authority(),
    }
    return {**result, "diff_receipt_sha256": digest(result)}


def verify_diff(before: Any, after: Any, delta: Any) -> dict[str, Any]:
    """Verify by recomputing from both original reports, not a self-checksum alone."""
    expected = compare_reports(before, after)
    if canonical_json_bytes(expected) != canonical_json_bytes(delta):
        raise ContractError("diff does not match the verified original reports")
    return {"integrity_valid": True, "status": STATUS,
            "diff_receipt_sha256": expected["diff_receipt_sha256"],
            "current_evidence_review_authority": False}


def _escape(value: Any) -> str:
    text = html.escape(str(value), quote=True)
    for char in "\\`*_{}[]()#+-.!|":
        text = text.replace(char, "\\" + char)
    return text.replace("\r", " ").replace("\n", " ")


def render_markdown(before: Any, after: Any) -> str:
    """Render directly from verified inputs; never render an unchecked delta."""
    delta = compare_reports(before, after)
    return _render_verified_delta(delta)


def _render_verified_delta(delta: dict[str, Any]) -> str:
    """Internal renderer for the result of this call's compare_reports()."""
    lines = ["# Inspection revision review", "", f"**{STATUS}**", "",
             "Changes describe supplied records, not verified University findings or practice improvement.",
             "No notes or dispositions have been transferred to another report receipt.", "",
             f"Before receipt: `{delta['before']['report_receipt_sha256']}`  ",
             f"After receipt: `{delta['after']['report_receipt_sha256']}`  ",
             f"Diff receipt: `{delta['diff_receipt_sha256']}`", "",
             "| Cell | Before | After | Record changes | Interpretation |",
             "|---|---|---|---|---|"]
    for row in delta["cell_deltas"]:
        values = [f"{row['group']} / {row['dimension']}", row["before_status"], row["after_status"],
                  ", ".join(row["changed_source_ids"]) or "none",
                  ", ".join(row["change_reasons"]) or ("Persistent hold" if row["persistent_hold"] else "Unchanged")]
        lines.append("| " + " | ".join(_escape(v) for v in values) + " |")
    lines += ["", "## Suggested review questions", ""]
    for item in delta["review_queue"]:
        lines += [f"### {_escape(item['group'])} / {_escape(item['dimension'])}", "",
                  *[f"- {_escape(question)}" for question in item["questions"]], ""]
    if not delta["review_queue"]:
        lines += ["No changed-cell or persistent-hold follow-up was identified.", ""]
    lines += ["## Receipt and authority limits", "",
              "Both source reports passed the parent semantic recompile. This establishes internal consistency only.",
              "Evaluation times are those stored in the reports, not a fresh current-authority check.",
              "Use verify with both original reports to check the JSON delta. All external authority flags remain false.", ""]
    return "\n".join(lines)


def load_json(path: Path) -> Any:
    # Bounded regular-file read, without following a final-component symlink on
    # platforms supporting O_NOFOLLOW. Not a concurrent-filesystem custody proof.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_INPUT_BYTES:
            raise ContractError("input must be a bounded regular JSON file")
        raw = handle.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ContractError("input exceeds the JSON byte limit")
    text = raw.decode("utf-8")
    try:
        return loads_strict(text)
    except ContractError:
        raise  # Preserve the parent's specific strict-JSON diagnostics.
    except ValueError as exc:
        # Python's integer digit limit is reported as ValueError, not
        # JSONDecodeError. Keep this bounded input failure in the CLI contract.
        raise ContractError("JSON decoder rejected a value") from exc


def write_new(path: Path, raw: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)


def write_bundle(before: Any, after: Any, destination: Path) -> dict[str, Any]:
    """Compare once and publish paired views with a final manifest."""
    delta = compare_reports(before, after)
    outputs = {
        "delta.json": canonical_json_bytes(delta),
        "review.md": _render_verified_delta(delta).encode("utf-8"),
    }
    manifest = {
        "schema": "uiowa-rfq18649-inspection-diff-bundle/v1",
        "status": STATUS,
        "before": delta["before"],
        "after": delta["after"],
        "diff_receipt_sha256": delta["diff_receipt_sha256"],
        "outputs": {name: {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
                    for name, raw in outputs.items()},
        "external_authority": _external_authority(),
    }
    manifest_raw = canonical_json_bytes(manifest)
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, raw in outputs.items():
        write_new(destination / name, raw)
    # A missing final manifest identifies an interrupted output operation.
    # Preserve already written files; never clean up an operator's evidence.
    write_new(destination / "manifest.json", manifest_raw)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    compare = sub.add_parser("compare", help="create a new JSON or Markdown comparison")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    compare.add_argument("output", type=Path)
    compare.add_argument("--format", choices=("json", "markdown"), default="json")
    bundle = sub.add_parser("bundle", help="create paired JSON/Markdown views and a final manifest in one computation")
    bundle.add_argument("before", type=Path)
    bundle.add_argument("after", type=Path)
    bundle.add_argument("output", type=Path, help="new output directory; never overwritten")
    verify = sub.add_parser("verify", help="recompute a JSON diff using its original reports")
    verify.add_argument("before", type=Path)
    verify.add_argument("after", type=Path)
    verify.add_argument("delta", type=Path)
    args = parser.parse_args(argv)
    try:
        before, after = load_json(args.before), load_json(args.after)
        if args.command == "verify":
            result = verify_diff(before, after, load_json(args.delta))
            print(f"UNTRUSTED_DIFF_INTEGRITY_ONLY {result['diff_receipt_sha256']}")
        elif args.command == "bundle":
            result = write_bundle(before, after, args.output)
            print(f"{STATUS} {result['diff_receipt_sha256']}; output={args.output}")
        else:
            if args.format == "markdown":
                raw = render_markdown(before, after).encode("utf-8")
            else:
                raw = canonical_json_bytes(compare_reports(before, after))
            write_new(args.output, raw)
            print(STATUS)
        return 0
    except (ContractError, OSError, UnicodeError, RecursionError) as exc:
        reason = str(exc).encode("unicode_escape").decode("ascii")[:240]
        print(f"ERROR: {type(exc).__name__}: {reason}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
