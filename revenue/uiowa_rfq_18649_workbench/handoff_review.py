#!/usr/bin/env python3
"""Offline reconciliation of draft analyst handoffs against one parent report.

No scoring, provenance certification, automatic adjudication, or external actions.
The existing parent compiler alone verifies the original report's semantics.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any

HANDOFF_SCHEMA = "uiowa-rfq18649-analyst-handoff-draft/v1"
REVIEW_SCHEMA = "uiowa-rfq18649-analyst-reconciliation-draft/v1"
MODE = "UNTRUSTED_INSPECTION"
DRAFT = "DRAFT_NON_AUTHORITATIVE"
GROUPS = ("ESS", "RIS", "IAM")
DIMENSIONS = ("software", "security", "deployment", "ai_readiness")
CELLS = tuple((group, dimension) for group in GROUPS for dimension in DIMENSIONS)
DISPOSITIONS = frozenset({"UNREVIEWED", "NEEDS_EVIDENCE", "DISCUSS_WITH_PRIME", "TECHNICAL_DRAFT_NOTE"})
AUTHORITY_KEYS = frozenset({
    "buyer_approved", "prime_approved", "current_evidence_review_authority",
    "submission_authorized", "signature_authorized", "invoice_or_payment_authorized",
    "recognized_revenue",
})
HANDOFF_KEYS = frozenset({
    "schema", "status", "report_receipt_sha256", "report_mode", "aggregate_state",
    "synthetic_demo", "cell_notes", "authority",
})
NOTE_KEYS = frozenset({"group", "dimension", "compiler_status", "disposition", "analyst_note"})
MAX_BYTES = 2 * 1024 * 1024
MAX_HANDOFFS = 20
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")


class ReviewError(ValueError):
    """Actionable intake failure; error messages never echo note content."""


def canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ReviewError("value is not finite, UTF-8-compatible JSON") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _object(value: Any, keys: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ReviewError(f"{label}: unexpected or missing fields")
    return value


def _string(value: Any, label: str, max_units: int, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value):
        raise ReviewError(f"{label}: expected string")
    try:
        units = len(value.encode("utf-16-le")) // 2
    except UnicodeError as exc:
        raise ReviewError(f"{label}: unpaired Unicode surrogate") from exc
    if units > max_units:
        raise ReviewError(f"{label}: exceeds {max_units} UTF-16 units")
    return value


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReviewError("duplicate JSON member")
        result[key] = value
    return result


def _not_finite(_: str) -> Any:
    raise ReviewError("non-finite JSON number")


def load_json(path: Path) -> Any:
    """Bounded regular-file read; never follow a final-component symlink on POSIX."""
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
            raise ReviewError("input must be a regular file of at most 2 MiB")
        raw = stream.read(MAX_BYTES + 1)
        after = os.fstat(stream.fileno())
    if len(raw) > MAX_BYTES or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ReviewError("input exceeded limit or changed while being read")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_not_finite)
        pending = [(value, 0)]
        while pending:
            item, depth = pending.pop()
            if depth > 64:
                raise ReviewError("JSON nesting exceeds 64 levels")
            if isinstance(item, dict):
                pending.extend((child, depth + 1) for child in item.values())
            elif isinstance(item, list):
                pending.extend((child, depth + 1) for child in item)
        canonical(value)  # Also reject float overflow (e.g. 1e999) and bad Unicode.
        return value
    except ReviewError:
        raise
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ReviewError("input must be strict UTF-8 JSON") from exc


def _parent_module():
    parent = Path(__file__).resolve().parents[1] / "uiowa_rfq_18649_workshare"
    if not (parent / "compiler.py").is_file():
        raise ReviewError("parent compiler missing; use the full Commons checkout")
    if str(parent) not in sys.path:
        sys.path.insert(0, str(parent))
    try:
        module = importlib.import_module("compiler")
    except (ImportError, OSError) as exc:
        raise ReviewError("parent compiler could not be loaded") from exc
    if Path(module.__file__).resolve() != parent / "compiler.py":
        raise ReviewError("another module shadows the parent compiler")
    return module


def _parent_integrity(report: Any) -> dict[str, Any]:
    carrier = _parent_module()
    try:
        return carrier.verify_report_integrity(report)
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        raise ReviewError("parent compiler rejected report integrity") from exc


def _report_cells(report: Any) -> dict[tuple[str, str], dict[str, Any]]:
    if not isinstance(report, dict) or report.get("mode") != MODE:
        raise ReviewError("only UNTRUSTED_INSPECTION parent reports are supported")
    if report.get("synthetic_demo") is not None or report.get("schema") == "SYNTHETIC_UI_DEMO_NOT_COMPILER_OUTPUT":
        raise ReviewError("UI-only demo report is not compiler output")
    trust = report.get("trust")
    if not isinstance(trust, dict) or any(trust.get(key) is not False for key in (
            "authority_root_supplied_out_of_band", "current_evidence_review_authority")):
        raise ReviewError("report must not carry trusted-root or current review authority")
    receipt = report.get("receipt_sha256")
    if not isinstance(receipt, str) or not SHA256.fullmatch(receipt):
        raise ReviewError("report receipt must be lowercase SHA-256")
    integrity = _parent_integrity(report)
    if (not isinstance(integrity, dict) or integrity.get("integrity_valid") is not True
            or integrity.get("semantic_recompile_valid") is not True
            or integrity.get("trusted_authority_root_verified") is not False
            or integrity.get("current_authority_verified") is not False
            or integrity.get("receipt_sha256") != receipt):
        raise ReviewError("parent verifier did not confirm non-authoritative semantic integrity")
    matrix = report.get("assessment_matrix")
    if not isinstance(matrix, list) or len(matrix) != len(CELLS):
        raise ReviewError("report must contain twelve assessment cells")
    result = {}
    for cell in matrix:
        if not isinstance(cell, dict):
            raise ReviewError("report cell must be an object")
        group = _string(cell.get("group"), "report cell group", 3)
        dimension = _string(cell.get("dimension"), "report cell dimension", 32)
        key = (group, dimension)
        if key not in CELLS or key in result:
            raise ReviewError("unknown or duplicate report cell")
        _string(cell.get("status"), "report cell status", 128)
        result[key] = cell
    return result


def _handoff_notes(handoff: Any, report: dict[str, Any], cells: dict) -> dict:
    value = _object(handoff, HANDOFF_KEYS, "handoff")
    if value["schema"] != HANDOFF_SCHEMA or value["status"] != DRAFT:
        raise ReviewError("handoff schema/status not supported")
    if value["report_receipt_sha256"] != report["receipt_sha256"] or value["report_mode"] != MODE:
        raise ReviewError("handoff belongs to a different report receipt or mode")
    if value["aggregate_state"] != report["aggregate_state"]:
        raise ReviewError("handoff aggregate state differs from original report")
    if value["synthetic_demo"] is not False:
        raise ReviewError("UI-only demonstration handoffs cannot be reconciled")
    authority = _object(value["authority"], AUTHORITY_KEYS, "handoff authority")
    if any(flag is not False for flag in authority.values()):
        raise ReviewError("all handoff authority flags must be literal false")
    notes = value["cell_notes"]
    if not isinstance(notes, list) or len(notes) != len(CELLS):
        raise ReviewError("handoff must contain twelve cell notes")
    result = {}
    for row in notes:
        row = _object(row, NOTE_KEYS, "cell note")
        group = _string(row["group"], "note group", 3)
        dimension = _string(row["dimension"], "note dimension", 32)
        key = (group, dimension)
        if key not in cells or key in result:
            raise ReviewError("unknown or duplicate handoff cell")
        if row["compiler_status"] != cells[key]["status"]:
            raise ReviewError("handoff compiler status differs from original report")
        disposition = _string(row["disposition"], "disposition", 32)
        if disposition not in DISPOSITIONS:
            raise ReviewError("unknown analyst disposition")
        _string(row["analyst_note"], "analyst note", 4000, empty=True)
        result[key] = dict(row)
    return result


def reconcile(report: Any, handoffs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Compare one to twenty exports without changing evidence or adjudicating notes.

    Labels are operator-supplied identifiers, NOT verified people or independent votes.
    """
    if not isinstance(handoffs, list) or not 1 <= len(handoffs) <= MAX_HANDOFFS:
        raise ReviewError("supply between one and twenty labeled handoffs")
    cells = _report_cells(report)
    reviewed = {}
    inputs = []
    content_groups: dict[str, list[str]] = {}
    for item in handoffs:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ReviewError("each handoff needs a label and document")
        label, document = item
        if not isinstance(label, str) or not LABEL.fullmatch(label) or label in reviewed:
            raise ReviewError("labels must be unique ASCII identifiers of 1-64 characters")
        notes = _handoff_notes(document, report, cells)
        reviewed[label] = notes
        normalized = dict(document, cell_notes=[notes[key] for key in CELLS])
        content_sha = digest(normalized)
        inputs.append({"label": label, "normalized_handoff_sha256": content_sha})
        content_groups.setdefault(content_sha, []).append(label)
    labels = sorted(reviewed)
    output_cells = []
    queue = []
    counts: dict[str, int] = {}
    for group, dimension in CELLS:
        key = (group, dimension)
        entries = [{"label": label, "disposition": reviewed[label][key]["disposition"],
                    "analyst_note": reviewed[label][key]["analyst_note"]} for label in labels]
        dispositions = {entry["disposition"] for entry in entries}
        active = dispositions - {"UNREVIEWED"}
        reasons = []
        if not active:
            reasons.append("ALL_UNREVIEWED")
        elif "UNREVIEWED" in dispositions:
            reasons.append("INCOMPLETE_REVIEW")
        if len(active) > 1:
            reasons.append("DISPOSITION_DISAGREEMENT")
        if len({entry["analyst_note"] for entry in entries}) > 1:
            reasons.append("NOTE_VARIATION_REQUIRES_REVIEW")
        if not reasons:
            # Reimporting one saved handoff under new labels adds no review
            # content. Keep its queue membership identical to a single import;
            # all labels and notes remain preserved in the output entries.
            reasons.append("SINGLE_DRAFT_ENTRY" if len(content_groups) == 1 else "MATCHING_DRAFT_ENTRIES")
        for reason in reasons:
            counts[reason] = counts.get(reason, 0) + 1
        if reasons != ["MATCHING_DRAFT_ENTRIES"]:
            queue.append({"group": group, "dimension": dimension, "reason_codes": reasons})
        original = cells[key]
        output_cells.append({"group": group, "dimension": dimension,
                             "compiler_status": original["status"],
                             "source_ids": list(original.get("source_ids", [])),
                             "source_record_sha256s": list(original.get("source_record_sha256s", [])),
                             "compiler_reason_codes": list(original.get("reason_codes", [])),
                             "review_reason_codes": reasons, "entries": entries})
    result = {
        "schema": REVIEW_SCHEMA, "status": DRAFT, "report_mode": MODE,
        "report_receipt_sha256": report["receipt_sha256"],
        "aggregate_state": report["aggregate_state"],
        "original_report_semantic_integrity_verified": True,
        "source_authenticity_verified": False,
        "reviewer_identity_verified": False,
        "inputs": sorted(inputs, key=lambda item: item["label"]),
        "input_count": len(inputs), "distinct_handoff_content_count": len(content_groups),
        "identical_content_groups": sorted([sorted(group) for group in content_groups.values() if len(group) > 1]),
        "assessment_cells": output_cells, "review_queue": queue,
        "reason_counts": counts,
        "authority": {key: False for key in sorted(AUTHORITY_KEYS)},
    }
    result["reconciliation_sha256"] = digest(result)
    return result


def render_markdown(result: dict[str, Any]) -> str:
    """Render a result produced by reconcile; JSON code blocks keep notes literal."""
    lines = ["# Draft analyst reconciliation", "", "DRAFT_NON_AUTHORITATIVE — not adjudication or University findings.",
             "", f"Report receipt: `{result['report_receipt_sha256']}`",
             f"Reconciliation receipt: `{result['reconciliation_sha256']}`", "",
             f"Input labels: {result['input_count']}; distinct handoff contents: {result['distinct_handoff_content_count']}.",
             "Labels are not authenticated reviewers. Identical content is not independent corroboration.",
             "Matching entries are not acceptance; differing words are not automatically contradictory evidence.",
             "", "## Review queue", "", "```json", json.dumps(result["review_queue"], indent=2), "```", ""]
    if result["identical_content_groups"]:
        lines.extend(["## Identical content groups", "", "```json",
                      json.dumps(result["identical_content_groups"], indent=2), "```", ""])
    for cell in result["assessment_cells"]:
        lines.extend([f"## {cell['group']} / {cell['dimension']}", "", "```json",
                      json.dumps(cell, ensure_ascii=True, indent=2), "```", ""])
    return "\n".join(lines)


def _write_new(path: Path, content: bytes) -> None:
    """Exclusive output; never overwrite an input or existing result."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _blank_handoff(report: dict[str, Any]) -> dict[str, Any]:
    return {"schema": HANDOFF_SCHEMA, "status": DRAFT,
            "report_receipt_sha256": report["receipt_sha256"], "report_mode": MODE,
            "aggregate_state": report["aggregate_state"], "synthetic_demo": False,
            "cell_notes": [{"group": cell["group"], "dimension": cell["dimension"],
                            "compiler_status": cell["status"], "disposition": "UNREVIEWED",
                            "analyst_note": ""} for cell in report["assessment_matrix"]],
            "authority": {key: False for key in sorted(AUTHORITY_KEYS)}}


def write_example(directory: Path) -> None:
    """Use only the repository's explicitly synthetic parent fixtures."""
    carrier = _parent_module()
    fixtures = Path(carrier.__file__).parent / "fixtures"
    candidate = load_json(fixtures / "synthetic_packet.json")
    authority = load_json(fixtures / "synthetic_authority.json")
    normalized = carrier.normalize_authority(authority)
    when = max(carrier._parse_utc(row["observed_at"], "observed_at") for row in normalized["sources"])
    report = carrier.compile_untrusted_inspection(candidate, authority, now=when)
    first, second = _blank_handoff(report), _blank_handoff(report)
    for handoff in (first, second):
        handoff["cell_notes"][0].update(disposition="TECHNICAL_DRAFT_NOTE", analyst_note="FICTIONAL: inspect a second release record.")
    first["cell_notes"][1].update(disposition="NEEDS_EVIDENCE", analyst_note="FICTIONAL: owner record not supplied.")
    second["cell_notes"][1].update(disposition="DISCUSS_WITH_PRIME", analyst_note="FICTIONAL: clarify the sample boundary first.")
    second["cell_notes"][2].update(disposition="NEEDS_EVIDENCE", analyst_note="FICTIONAL: follow up on the rollback demonstration.")
    result = reconcile(report, [("analyst-a", first), ("analyst-b", second)])
    outputs = {"report.json": canonical(report), "analyst-a.json": canonical(first),
               "analyst-b.json": canonical(second), "reconciliation.json": canonical(result),
               "reconciliation.md": render_markdown(result).encode(),
               "README.txt": b"SYNTHETIC REHEARSAL ONLY. No University observations or verified reviewer identities.\n"}
    directory.mkdir(parents=False, exist_ok=False)
    for name, content in outputs.items():
        _write_new(directory / name, content + b"\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    compare = commands.add_parser("compare", help="validate and reconcile draft exports")
    compare.add_argument("report", type=Path)
    compare.add_argument("--handoff", nargs=2, metavar=("LABEL", "PATH"), action="append", required=True)
    compare.add_argument("--format", choices=("json", "markdown"), default="json")
    compare.add_argument("--output", type=Path, required=True, help="new private output file; never overwritten")
    example = commands.add_parser("example", help="write a synthetic parent-compiler rehearsal into a NEW directory")
    example.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "example":
            write_example(args.directory)
            print("SYNTHETIC_REHEARSAL_WRITTEN")
        else:
            if len(args.handoff) > MAX_HANDOFFS:
                raise ReviewError("at most twenty handoffs are supported")
            result = reconcile(load_json(args.report), [(label, load_json(Path(path))) for label, path in args.handoff])
            content = canonical(result) + b"\n" if args.format == "json" else render_markdown(result).encode("utf-8")
            _write_new(args.output, content)
            print(f"{DRAFT} {result['reconciliation_sha256']}")
        return 0
    except (ReviewError, OSError, ValueError) as exc:
        # OSError may include a sensitive local pathname. Do not print it.
        detail = str(exc) if isinstance(exc, ReviewError) else "file operation or parent compilation failed"
        print(f"ERROR: {detail}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
