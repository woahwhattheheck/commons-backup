"""Deterministic operator brief over the landed Jev activity ledger/action receipts.

The compiler is deliberately transport-free.  It verifies the exact ledger generation,
optionally verifies provider-readback action receipts, and emits one discoverable record plus
a concise Markdown projection.  A connector/controller may publish that projection, but must
reuse the stable operation marker and provider readback rather than spraying duplicate posts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from integrations.command_center.jev_event_ledger import REPORT_SCHEMA as LEDGER_SCHEMA
from integrations.command_center.jev_event_ledger import MAX_BYTES, LedgerError, verify_report

SCHEMA = "commons.jev_activity_brief/v1"
OPERATION_ID = "jev16537-activity-brief-v1"
MAX_RECEIPTS = 256
MAX_ATTENTION = 12
MAX_ATTENTION_PAGE = 100
ATTENTION_KINDS = {"ASK", "OWNER_DIRECTION", "HANDOFF", "COLLISION"}
AUTHORITY = {
    "provider_send_authority": False,
    "provider_edit_authority": False,
    "claim_authority": False,
    "merge_authority": False,
    "payment_authority": False,
    "raw_private_text_included": False,
}


class ActivityBriefError(ValueError):
    """Malformed, unverifiable, or contradictory activity-brief input."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ActivityBriefError("not canonical JSON data") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _time(value: Any, where: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise ActivityBriefError(f"{where}: expected RFC3339 UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ActivityBriefError(f"{where}: invalid timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise ActivityBriefError(f"{where}: timestamp is not UTC")
    return parsed


def _safe_link(value: str) -> str:
    """Render an already-validated source URL without creating Markdown syntax."""
    return value.replace("<", "%3C").replace(">", "%3E")


def _window_map(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    windows = report.get("windows")
    if type(windows) is not list:
        raise ActivityBriefError("ledger windows missing")
    result = {}
    for row in windows:
        if type(row) is not dict or type(row.get("label")) is not str:
            raise ActivityBriefError("ledger window malformed")
        if row["label"] in result:
            raise ActivityBriefError("duplicate ledger window label")
        result[row["label"]] = row
    required = {"15m", "1h", "24h", "historical"}
    if set(result) != required:
        raise ActivityBriefError("ledger window set mismatch")
    return result


def _receipt_projection(receipts: list[dict[str, Any]], evaluated_at: datetime) -> list[dict[str, Any]]:
    if type(receipts) is not list or len(receipts) > MAX_RECEIPTS:
        raise ActivityBriefError("action receipts: invalid count")
    if not receipts:
        return []
    from integrations.command_center.jev_action_loop import ActionLoopError, verify_receipt

    output = []
    seen = set()
    for raw in receipts:
        try:
            verified = verify_receipt(raw)
        except (ActionLoopError, TypeError, ValueError) as exc:
            raise ActivityBriefError("action receipt failed verification") from exc
        observed = _time(raw.get("observed_at"), "receipt.observed_at")
        if observed > evaluated_at:
            raise ActivityBriefError("action receipt is newer than ledger snapshot")
        digest = verified["receipt_sha256"]
        if digest in seen:
            continue
        seen.add(digest)
        output.append({
            "operation_id": verified["operation_id"],
            "plan_sha256": raw["plan_sha256"],
            "provider": raw["provider"],
            "destination_id": raw["destination_id"],
            "provider_resource_id": raw["provider_resource_id"],
            "outcome": verified["outcome"],
            "confirmed": verified["confirmed"],
            "observed_at": raw["observed_at"],
            "source_url": raw["source_url"],
            "receipt_sha256": digest,
        })
    return sorted(output, key=lambda row: (
        _time(row["observed_at"], "receipt.observed_at"),
        row["operation_id"], row["receipt_sha256"],
    ))


def _operation_projection(receipts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarize verified history using the existing action-loop replay semantics."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in receipts:
        grouped.setdefault(row["operation_id"], []).append(row)
    output = []
    for operation_id, history in grouped.items():
        bindings = {
            (row["provider"], row["destination_id"], row["plan_sha256"])
            for row in history
        }
        if len(bindings) != 1:
            raise ActivityBriefError("action receipts: one operation binds different plans or targets")
        history = sorted(history, key=lambda row: (
            _time(row["observed_at"], "receipt.observed_at"), row["receipt_sha256"],
        ))
        confirmed = [row for row in history if row["confirmed"]]
        uncertain = [row for row in history if row["outcome"] == "DELIVERY_UNCERTAIN"]
        # A later rejection cannot prove an earlier uncertain attempt was not delivered.
        # Conversely, any exact confirmation prevents replay, even after a later error.
        effective = (confirmed or uncertain or history)[-1]
        resources = sorted({row["provider_resource_id"] for row in confirmed})
        next_action = (
            "CHECK_DUPLICATE_DELIVERY_DO_NOT_REPLAY" if len(resources) > 1 else
            "DO_NOT_REPLAY" if confirmed else
            "READ_BACK_EXISTING_OPERATION" if uncertain else
            "RETRY_SAME_OPERATION_ID"
        )
        output.append({
            "operation_id": operation_id,
            "plan_sha256": effective["plan_sha256"],
            "provider": effective["provider"],
            "destination_id": effective["destination_id"],
            "provider_resource_id": effective["provider_resource_id"],
            "outcome": effective["outcome"],
            "confirmed": bool(confirmed),
            "next_action": next_action,
            "observed_at": effective["observed_at"],
            "first_observed_at": history[0]["observed_at"],
            "last_observed_at": history[-1]["observed_at"],
            "source_url": effective["source_url"],
            "source_urls": sorted({row["source_url"] for row in history}),
            "receipt_count": len(history),
            "receipt_sha256": effective["receipt_sha256"],
            "confirmed_resource_ids": resources,
        })
    return sorted(output, key=lambda row: (
        _time(row["last_observed_at"], "operation.last_observed_at"), row["operation_id"],
    ))


def _action_summary(receipts: list[dict[str, Any]], operations: list[dict[str, Any]]) -> dict[str, int]:
    history_counts = Counter(row["outcome"] for row in receipts)
    operation_counts = Counter(row["outcome"] for row in operations)
    return {
        # Keep these established fields as receipt-history counts for existing consumers.
        "receipt_count": len(receipts),
        "confirmed": history_counts.get("CONFIRMED", 0),
        "delivery_uncertain": history_counts.get("DELIVERY_UNCERTAIN", 0),
        "rejected": history_counts.get("REJECTED", 0),
        "operation_count": len(operations),
        "confirmed_operations": operation_counts.get("CONFIRMED", 0),
        "delivery_uncertain_operations": operation_counts.get("DELIVERY_UNCERTAIN", 0),
        "rejected_operations": operation_counts.get("REJECTED", 0),
        "duplicate_delivery_operations": sum(len(row["confirmed_resource_ids"]) > 1 for row in operations),
    }


def _render_action_lines(record: dict[str, Any]) -> list[str]:
    action = record["actions"]
    # Preserve the exact rendering of older saved v1 records and their existing digests.
    if "action_operations" not in record:
        lines = ["", "## Action receipts", ""]
        lines.append(
            f"Supplied verified receipts: **{action['receipt_count']}** · confirmed **{action['confirmed']}** · "
            f"delivery-uncertain **{action['delivery_uncertain']}** · rejected **{action['rejected']}**."
        )
        for row in record["action_receipts"][-8:]:
            link = _safe_link(row["source_url"])
            lines.append(f"- `{row['operation_id']}` · **{row['outcome']}** · <{link}>")
        return lines
    lines = ["", "## Action operations", ""]
    lines.append(
        f"Distinct operations in supplied history: **{action['operation_count']}** · "
        f"confirmed **{action['confirmed_operations']}** · "
        f"delivery-uncertain **{action['delivery_uncertain_operations']}** · "
        f"rejected **{action['rejected_operations']}**."
    )
    lines.append(f"Retained receipt history: **{action['receipt_count']}** records; not a count of distinct actions or Jev-processed events.")
    if action["duplicate_delivery_operations"]:
        lines.append(f"Operations confirmed at multiple provider resources: **{action['duplicate_delivery_operations']}**; inspect existing resources, do not replay.")
    # Show unresolved delivery observations before confirmations, oldest first in each class.
    operations = sorted(record["action_operations"], key=lambda row: (
        0 if len(row["confirmed_resource_ids"]) > 1 else
        {"DELIVERY_UNCERTAIN": 1, "REJECTED": 2, "CONFIRMED": 3}[row["outcome"]],
        _time(row["first_observed_at"], "operation.first_observed_at"), row["operation_id"],
    ))
    for row in operations[:8]:
        link = _safe_link(row["source_url"])
        lines.append(f"- `{row['operation_id']}` · **{row['outcome']}** · `{row['next_action']}` · <{link}>")
    if len(operations) > 8:
        lines.append(f"Showing 8 of {len(operations)} operation states; all are retained in JSON `action_operations`.")
    lines.append("Next actions describe existing receipt state, not permission to send, claim work, or treat an obligation as resolved.")
    return lines


def _attention(
    report: dict[str, Any], evaluated_at: datetime, *, order: str = "newest",
    limit: int = MAX_ATTENTION, cursor: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Page candidate events, not inferred unresolved obligations or unread messages."""
    if type(order) is not str or order not in {"newest", "oldest"}:
        raise ActivityBriefError("attention order must be newest or oldest")
    if type(limit) is not int or not 1 <= limit <= MAX_ATTENTION_PAGE:
        raise ActivityBriefError(f"attention limit must be 1..{MAX_ATTENTION_PAGE}")
    events = report.get("events")
    if type(events) is not list:
        raise ActivityBriefError("ledger events missing")
    rows = []
    for event in events:
        if type(event) is not dict:
            raise ActivityBriefError("ledger event malformed")
        if event.get("kind") not in ATTENTION_KINDS:
            continue
        event_time = _time(event.get("provider_event_time"), "event.provider_event_time")
        age_seconds = max(0, int((evaluated_at - event_time).total_seconds()))
        urls = event.get("source_urls")
        if type(urls) is not list or not urls:
            raise ActivityBriefError("attention event lacks source links")
        rows.append({
            "event_id": event.get("event_id"),
            "kind": event.get("kind"),
            "provider": event.get("provider"),
            "work_id": event.get("work_id"),
            "actor_id": event.get("actor_id"),
            "provider_event_time": event.get("provider_event_time"),
            "age_seconds": age_seconds,
            "primary_source_id": event["primary_source_id"],
            "source_urls": sorted(set(urls)),
        })
    rows.sort(key=lambda row: (
        _time(row["provider_event_time"], "event.provider_event_time"), str(row["event_id"])
    ))
    oldest, newest = (rows[0], rows[-1]) if rows else (None, None)
    if order == "newest":
        rows.reverse()
    total = len(rows)
    offset = 0
    ledger_digest = report["ledger_receipt_sha256"]
    if cursor is not None:
        match = re.fullmatch(
            r"v1:([0-9a-f]{64}):(newest|oldest):([0-9]{1,3}):([0-9]{1,6})", cursor
        ) if type(cursor) is str else None
        if match is None:
            raise ActivityBriefError("invalid attention cursor")
        digest, cursor_order, cursor_limit, cursor_offset = match.groups()
        if digest != ledger_digest:
            raise ActivityBriefError("attention snapshot changed; restart without a cursor")
        if cursor_order != order or int(cursor_limit) != limit:
            raise ActivityBriefError("attention cursor requires the same order and limit")
        offset = int(cursor_offset)
        if offset and offset >= total:
            raise ActivityBriefError("attention cursor is outside this snapshot")
    page = rows[offset:offset + limit]
    end = offset + len(page)

    def continuation(position: int) -> str:
        return f"v1:{ledger_digest}:{order}:{limit}:{position}"

    historical = _window_map(report)["historical"]
    coverage = historical["coverage"]
    summary = {
        "total_candidates": total,
        "shown_candidates": len(page),
        "remaining_candidates": total - end,
        "offset": offset,
        "limit": limit,
        "order": order,
        "next_cursor": continuation(end) if end < total else None,
        "previous_cursor": continuation(max(0, offset - limit)) if offset else None,
        "oldest_candidate_at": oldest["provider_event_time"] if oldest else None,
        "oldest_age_seconds": oldest["age_seconds"] if oldest else None,
        "newest_candidate_at": newest["provider_event_time"] if newest else None,
        "by_kind": dict(sorted(Counter(row["kind"] for row in rows).items())),
        "by_provider": dict(sorted(Counter(row["provider"] for row in rows).items())),
        "by_primary_source": dict(sorted(Counter(row["primary_source_id"] for row in rows).items())),
        "coverage_state": coverage["state"],
        "coverage_window": {"start": historical["start"], "end": historical["end"]},
        "incomplete_or_stale_sources": coverage["incomplete_or_stale_sources"],
        "unresolved_count": None,
        "processed_count": None,
    }
    return page, summary


def _render_markdown(record: dict[str, Any]) -> str:
    source = record["source"]
    freshness = record["freshness"]
    windows = {row["label"]: row for row in record["windows"]}
    lines = [
        "# Jev swarm activity brief",
        "",
        f"Snapshot `{source['snapshot_id']}` · observed `{source['evaluated_at']}` · ledger `{source['ledger_receipt_sha256'][:12]}…`.",
        "",
        "## Coverage and volume",
        "",
        (
            f"Sources: **{freshness['source_count']}** · fresh **{freshness['fresh']}** · "
            f"degraded/stale **{freshness['degraded']}** · partial/paginated **{freshness['partial']}**."
        ),
    ]
    for label in ("15m", "1h", "24h", "historical"):
        row = windows[label]
        stage = row["by_stage"]
        qualifier = "exact" if row["coverage_state"] == "COMPLETE" else "lower-bound"
        lines.append(
            f"- **{label}**: {row['event_count']} events ({qualifier}); "
            f"claims {stage.get('CLAIM', 0)}, sessions {stage.get('CONFIRMED_SESSION', 0)}, "
            f"accepted {stage.get('PROVIDER_ACCEPTED', 0)}, landed {stage.get('LANDED', 0)}, "
            f"business outcomes {stage.get('BUSINESS_OUTCOME', 0)}."
        )
    if freshness["degraded_source_ids"]:
        lines.extend([
            "",
            "Degraded source IDs: " + ", ".join(f"`{item}`" for item in freshness["degraded_source_ids"]),
        ])

    lines.extend(["", "## Attention candidates", ""])
    attention = record.get("attention")
    if attention is not None:
        first = attention["offset"] + 1 if attention["shown_candidates"] else 0
        last = attention["offset"] + attention["shown_candidates"]
        lines.extend([
            f"Candidate events in supplied snapshot: **{attention['total_candidates']}**; "
            f"source coverage **{attention['coverage_state']}**. "
            f"Showing {first}–{last}, {attention['order']} first; "
            f"{attention['remaining_candidates']} remain after this page.",
            "",
        ])
        if attention["oldest_candidate_at"] is not None:
            lines.extend([
                f"Oldest candidate: `{attention['oldest_candidate_at']}` "
                f"(age {attention['oldest_age_seconds']}s at the snapshot).",
                "",
            ])
        if attention["next_cursor"] is not None:
            lines.extend([
                f"Next page: `--attention-order {attention['order']} "
                f"--attention-limit {attention['limit']} "
                f"--attention-cursor {attention['next_cursor']}` on the same report.",
                "",
            ])
    if not record["attention_candidates"]:
        lines.append("No ASK / OWNER_DIRECTION / HANDOFF / COLLISION events are present in this bounded ledger snapshot.")
    else:
        for row in record["attention_candidates"]:
            work = f" · work `{row['work_id']}`" if row["work_id"] else ""
            link = _safe_link(row["source_urls"][0])
            lines.append(
                f"- **{row['kind']}** · `{row['provider']}` · age {row['age_seconds']}s{work} · <{link}>"
            )
    lines.extend(["", "These are event-kind candidates, not assertions that an obligation remains unanswered or that an actor is currently active."])

    lines.extend(_render_action_lines(record))

    lines.extend([
        "",
        "## Continuation contract",
        "",
        f"Stable update operation: `{record['operation_id']}`. A publishing controller should edit/read back the existing provider resource for this operation, or create it once when no prior resource exists. This compiler has no send/edit/claim/merge/payment authority.",
        "",
        f"<!-- jev-activity-operation:{record['operation_id']} generation:{record['generation_sha256']} -->",
    ])
    return "\n".join(lines) + "\n"


def compile_brief(
    ledger_report: dict[str, Any], action_receipts: list[dict[str, Any]] | None = None, *,
    attention_order: str = "newest", attention_limit: int = MAX_ATTENTION,
    attention_cursor: str | None = None,
) -> dict[str, Any]:
    """Verify a ledger generation and compile one deterministic operator/shared record."""
    if type(ledger_report) is not dict or ledger_report.get("schema") != LEDGER_SCHEMA:
        raise ActivityBriefError("unsupported ledger report schema")
    if not verify_report(ledger_report):
        raise ActivityBriefError("ledger report failed integrity verification")
    evaluated_at = _time(ledger_report.get("evaluated_at"), "ledger.evaluated_at")
    windows = _window_map(ledger_report)
    receipts = _receipt_projection([] if action_receipts is None else action_receipts, evaluated_at)
    attention_rows, attention_summary = _attention(
        ledger_report, evaluated_at, order=attention_order,
        limit=attention_limit, cursor=attention_cursor,
    )

    source_summary = ledger_report.get("source_summary")
    if type(source_summary) is not dict:
        raise ActivityBriefError("ledger source summary missing")
    freshness_counts = source_summary.get("freshness_counts")
    if type(freshness_counts) is not dict:
        raise ActivityBriefError("ledger freshness counts missing")
    degraded_ids = source_summary.get("stale_or_degraded_sources")
    partial_ids = source_summary.get("partial_or_paginated_sources")
    if type(degraded_ids) is not list or type(partial_ids) is not list:
        raise ActivityBriefError("ledger source degradation lists missing")

    projected_windows = []
    for label in ("15m", "1h", "24h", "historical"):
        row = windows[label]
        coverage = row.get("coverage")
        if type(coverage) is not dict or coverage.get("state") not in {"COMPLETE", "LOWER_BOUND"}:
            raise ActivityBriefError("ledger window coverage malformed")
        projected_windows.append({
            "label": label,
            "start": row.get("start"),
            "end": row.get("end"),
            "event_count": row.get("event_count"),
            "distinct_observed_contributors": row.get("distinct_observed_contributors"),
            "distinct_work_items": row.get("distinct_work_items"),
            "by_stage": row.get("by_stage"),
            "by_provider": row.get("by_provider"),
            "by_kind": row.get("by_kind"),
            "coverage_state": coverage.get("state"),
            "incomplete_or_stale_sources": coverage.get("incomplete_or_stale_sources"),
            "source_window_receipt_sha256": row.get("window_receipt_sha256"),
        })

    operations = _operation_projection(receipts)
    record = {
        "schema": SCHEMA,
        "operation_id": OPERATION_ID,
        "source": {
            "ledger_schema": ledger_report["schema"],
            "snapshot_id": ledger_report.get("snapshot_id"),
            "evaluated_at": ledger_report["evaluated_at"],
            "clock_source": ledger_report.get("clock_source"),
            "ledger_receipt_sha256": ledger_report.get("ledger_receipt_sha256"),
        },
        "freshness": {
            "source_count": source_summary.get("source_count"),
            "fresh": freshness_counts.get("FRESH", 0),
            "degraded": sum(value for key, value in freshness_counts.items() if key != "FRESH"),
            "partial": len(partial_ids),
            "degraded_source_ids": sorted(set(degraded_ids)),
            "partial_or_paginated_source_ids": sorted(set(partial_ids)),
        },
        "windows": projected_windows,
        "attention_candidates": attention_rows,
        "attention": attention_summary,
        "actions": _action_summary(receipts, operations),
        "action_receipts": receipts,
        "action_operations": operations,
        "publication": {
            "mode": "EDIT_EXISTING_OR_CREATE_ONCE",
            "operation_marker": OPERATION_ID,
            "requires_provider_readback": True,
        },
        "authority": dict(AUTHORITY),
    }
    generation_material = dict(record)
    record["generation_sha256"] = _digest(generation_material)
    record["markdown"] = _render_markdown(record)
    record["record_sha256"] = _digest({key: value for key, value in record.items() if key != "record_sha256"})
    return record


def verify_brief(record: dict[str, Any]) -> bool:
    """Verify a compiled brief has not drifted after compilation."""
    try:
        if type(record) is not dict or record.get("schema") != SCHEMA:
            return False
        if record.get("operation_id") != OPERATION_ID or record.get("authority") != AUTHORITY:
            return False
        expected_record = record.get("record_sha256")
        if type(expected_record) is not str or len(expected_record) != 64:
            return False
        body = {key: value for key, value in record.items() if key != "record_sha256"}
        if _digest(body) != expected_record:
            return False
        generation_body = {
            key: value for key, value in record.items()
            if key not in {"generation_sha256", "markdown", "record_sha256"}
        }
        expected_generation = record.get("generation_sha256")
        if type(expected_generation) is not str or _digest(generation_body) != expected_generation:
            return False
        if record.get("markdown") != _render_markdown(record):
            return False
        publication = record.get("publication")
        return publication == {
            "mode": "EDIT_EXISTING_OR_CREATE_ONCE",
            "operation_marker": OPERATION_ID,
            "requires_provider_readback": True,
        }
    except (ActivityBriefError, TypeError, ValueError, KeyError):
        return False


def _read_json(path: str) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ActivityBriefError("duplicate JSON key")
            result[key] = value
        return result

    def constant(value):
        raise ActivityBriefError(f"non-finite JSON constant: {value}")

    with open(path, "rb") as handle:
        data = handle.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ActivityBriefError(f"{path}: input exceeds {MAX_BYTES} bytes")
    return json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)


def _create_output(path: str, output: str) -> None:
    """Publish a complete new file without replacing an existing destination."""
    destination = Path(path)
    staging = destination.parent / (".jev-brief-" + uuid4().hex + ".tmp")
    created = False
    try:
        with open(staging, "x", encoding="utf-8", newline="\n") as handle:
            created = True
            handle.write(output)
            handle.flush()
            os.fsync(handle.fileno())
        # Atomic create-only publication also preserves a concurrent writer.
        os.link(staging, destination)
    finally:
        if created:
            staging.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", help="existing compiled event-ledger report JSON")
    parser.add_argument("--receipts", help="optional JSON array of provider readback receipts")
    parser.add_argument("--attention-order", choices=("newest", "oldest"), default="newest")
    parser.add_argument("--attention-limit", type=int, default=MAX_ATTENTION)
    parser.add_argument("--attention-cursor", help="continuation from this same ledger snapshot")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", help="atomically create a new file; default is standard output")
    args = parser.parse_args(argv)
    try:
        record = compile_brief(
            _read_json(args.report),
            _read_json(args.receipts) if args.receipts else None,
            attention_order=args.attention_order, attention_limit=args.attention_limit,
            attention_cursor=args.attention_cursor,
        )
        output = record["markdown"] if args.format == "markdown" else json.dumps(
            record, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        ) + "\n"
        if args.output:
            _create_output(args.output, output)
        else:
            sys.stdout.write(output)
        return 0
    except (OSError, ActivityBriefError, LedgerError, ValueError, TypeError,
            KeyError, RecursionError) as exc:
        print(f"jev_activity_brief: {exc}", file=sys.stderr)
        return 2


__all__ = ["ActivityBriefError", "OPERATION_ID", "SCHEMA", "compile_brief", "verify_brief", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
