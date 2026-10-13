#!/usr/bin/env python3
"""Rendering, compilation, and semantic verification."""
from __future__ import annotations

from typing import Any

from .schema import (
    AUTHORITY_CEILING, COMPILER, RECEIPT_SCHEMA, REPORT_SCHEMA,
    CompiledBundle, RegistryError, _canonical, _digest, load_strict_json,
)
from .normalize import _normalize
from .classify import _derive

def _markdown(report):
    lines = [
        "# Swarm work terminality registry",
        "",
        f"- Evaluation: `{report['evaluated_at_utc']}`",
        f"- Snapshot SHA-256: `{report['snapshot_sha256']}`",
        "",
        "> Triage evidence only. Re-read live provider state immediately before any merge, close, ref mutation, ownership claim, Muse action, outbound send, spend, payment, or revenue action.",
        "",
        "## Items",
    ]
    for row in report["items"]:
        suffix = f" → `{row['canonical_successor_item_id']}`" if row["canonical_successor_item_id"] else ""
        lines += [
            f"### `{row['item_id']}` — {row['classification']}",
            f"- Provider: `{row['provider_state']}` via `{row['provider_observation_id']}` ({row['provider_observation_age_seconds']}s old)",
            f"- Next action: **{row['recommended_next_action']}**{suffix}",
            f"- Active owners: {', '.join(row['active_owners']) if row['active_owners'] else 'none'}",
        ]
        if row["reasons"]:
            lines.append("- Reasons: " + "; ".join(row["reasons"]))
        lines.append("")
    lines += ["## Authority ceiling"]
    lines += [f"- `{key}` = `false`" for key in sorted(AUTHORITY_CEILING)]
    lines.append("")
    return "\n".join(lines)


def compile_snapshot(candidate: Any) -> CompiledBundle:
    snapshot = _normalize(candidate)
    snapshot_json = _canonical(snapshot)
    rows = _derive(snapshot)
    report = {
        "schema_version": REPORT_SCHEMA,
        "compiler": COMPILER,
        "evaluated_at_utc": snapshot["evaluated_at_utc"],
        "snapshot_sha256": _digest(snapshot_json),
        "items": rows,
        "authority_ceiling": dict(AUTHORITY_CEILING),
        "truth_note": "Retained-snapshot triage only; every provider mutation requires a fresh live recensus.",
    }
    report_json = _canonical(report)
    report_markdown = _markdown(report)
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "compiler": COMPILER,
        "snapshot_sha256": _digest(snapshot_json),
        "report_json_sha256": _digest(report_json),
        "report_markdown_sha256": _digest(report_markdown),
        "classification_sha256": _digest(_canonical(rows)),
        "authority_ceiling": dict(AUTHORITY_CEILING),
    }
    return CompiledBundle(report_json, report_markdown, _canonical(receipt))


def verify_bundle(candidate: Any, report_json: str, report_markdown: str, receipt_json: str) -> bool:
    expected = compile_snapshot(candidate)
    if report_json != expected.report_json:
        raise RegistryError("report JSON does not match semantic recompile")
    if report_markdown != expected.report_markdown:
        raise RegistryError("report Markdown does not match semantic recompile")
    if receipt_json != expected.receipt_json:
        raise RegistryError("receipt does not match semantic recompile")
    receipt = load_strict_json(receipt_json)
    if receipt.get("report_json_sha256") != _digest(report_json):
        raise RegistryError("report JSON digest mismatch")
    if receipt.get("report_markdown_sha256") != _digest(report_markdown):
        raise RegistryError("report Markdown digest mismatch")
    return True
