"""Compact operator read model, published beside the canonical event ledger.

This view never grants custody. Its ages describe ``projected_at``; readers that
need a dispatch decision must use the runtime and its current provider/seat
reconciliation. Building the view is deliberately separate from deciding
whether a ledger write is necessary, so time alone cannot create a commit.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json

from .projector import project
from .routing import status

SCHEMA = "commons-swarm-status/v1"
STATUS_PATH = "holdings/swarm-status.json"
MAX_TASKS = 5000
MAX_UTF8_BYTES = 15 * 1024 * 1024 // 4  # 3.75 MiB, below the panel's 4 MiB read limit.
MAX_METADATA_SECTION_BYTES = 128 * 1024
UNKNOWN = "UNKNOWN"

_SUMMARY_CORE = ("counts", "recoverable_count", "stale_seat_count", "idle_seat_count",
                 "idle_capability_count", "collision_count", "liveness_basis", "observed_at")

_CORE = ("task_key", "state", "worker", "recoverable", "dispatchable", "lease")
_FIELDS = (
    "title", "repo", "issue", "pr", "model", "harness", "created_at", "started_at",
    "heartbeat", "latest_activity", "last_activity_at", "closed_at", "owner_liveness",
    "feed_cursor", "base_sha", "current_base_sha", "head_sha", "branch", "merge_sha",
    "artifact", "artifact_sha", "landed_sha", "needs_rebase", "blocker", "exact_error", "next_action",
    "superseded_by", "shipment_source", "shipment_kind", "shipment_claim", "priority",
    "required_capabilities", "source", "sources", "source_event_ids", "collision_count",
    "provider_state", "provider_observed_at", "provider_source", "provider_activity_at",
    "provider_freshness", "provider_age_s", "provider_reconciliation_pending",
    "reconciliation_needed", "previous_worker", "recovered_at", "released_at", "claim_transferred_at",
)


def _known(value):
    return value is not None and value != UNKNOWN and value != "" and value != [] and value != {}


def _compact_task(task):
    # Keep evidence objects and identifiers intact; omit only unknown/empty
    # optional fields. The projector already bounds provenance to 32 IDs.
    row = {field: copy.deepcopy(task.get(field, UNKNOWN)) for field in _CORE}
    row.update({field: copy.deepcopy(task[field]) for field in _FIELDS
                if field in task and _known(task[field])})
    return row


def _encoded(value):
    # Match the store's compact serializer exactly, excluding its final newline.
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _bounded_mapping(value, priority=()):
    """Keep complete fields within a bounded metadata section, never clipped facts."""
    if not isinstance(value, dict):
        if len(_encoded(value)) <= MAX_METADATA_SECTION_BYTES:
            return copy.deepcopy(value), 0
        return {}, 1
    keys = [key for key in priority if key in value]
    keys += sorted(key for key in value if key not in priority)
    kept, used = {}, 2  # Object braces.
    for key in keys:
        cost = len(_encoded({key: value[key]})) - 2 + bool(kept)
        if used + cost > MAX_METADATA_SECTION_BYTES:
            break
        kept[key] = copy.deepcopy(value[key])
        used += cost
    return kept, len(keys) - len(kept)


def _bounded_collisions(values):
    kept, used = [], 2  # Array brackets; preserve the most recent complete tail.
    for value in reversed(values[-50:]):
        cost = len(_encoded(value)) + bool(kept)
        if used + cost > MAX_METADATA_SECTION_BYTES:
            break
        kept.append(copy.deepcopy(value))
        used += cost
    kept.reverse()
    return kept, len(values) - len(kept)


def build(ledger_bytes, now=None, branch="state/claims", max_tasks=MAX_TASKS):
    """Project exactly these persisted ledger bytes without IO or mutation.

    The digest includes the ledger's original encoding/newline bytes, not a
    reserialization. This lets an operator bind the view to its sibling source.
    Both task count and compact UTF-8 bytes are bounded; summary counts cover
    the full projection. Omitted rows/metadata remain in the source ledger.
    """
    raw = ledger_bytes.encode("utf-8") if isinstance(ledger_bytes, str) else ledger_bytes
    if not isinstance(raw, bytes):
        raise ValueError("status snapshot requires exact UTF-8 ledger bytes")
    if isinstance(max_tasks, bool) or not isinstance(max_tasks, int) or not 0 <= max_tasks <= MAX_TASKS:
        raise ValueError("status snapshot max_tasks must be between 0 and 5000")
    try:
        state = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("status snapshot ledger is not valid UTF-8 JSON") from exc
    if not isinstance(state, dict) or state.get("schema") != "commons-swarm-runtime/v1":
        raise ValueError("status snapshot requires a canonical swarm runtime ledger")
    moment = now if now is not None else dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(moment, dt.datetime):
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=dt.timezone.utc)
        moment = moment.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    # Runtime owns seat overlay semantics. Import only when invoked, after the
    # runtime/store modules have finished initializing.
    from .runtime import _seats

    seats = _seats(state)
    view = project(state.get("events", []), now=moment, seats=seats,
                   provider_facts=state.get("provider_facts", {}))
    keys = sorted(view["tasks"])
    summary, summary_omitted = _bounded_mapping(status(view["tasks"], seats, moment), _SUMMARY_CORE)
    coverage, coverage_omitted = _bounded_mapping(state.get("coverage", {}))
    collisions, collisions_omitted = _bounded_collisions(view.get("collisions", []))
    snapshot = {
        "schema": SCHEMA,
        "authority": branch,
        "source_ledger_sha256": hashlib.sha256(raw).hexdigest(),
        "projected_at": moment,
        "tasks": [],
        "total": len(keys),
        # Reserve the longest possible representations before selecting rows:
        # false is one byte longer than true; total bounds omitted-task digits.
        "truncated": False,
        "omitted_tasks": len(keys),
        "byte_limited": False,
        "limits": {"task_rows": max_tasks, "utf8_bytes": MAX_UTF8_BYTES},
        "summary": summary,
        "collisions": collisions,
        "collisions_total": len(view.get("collisions", [])),
        "coverage": coverage,
        "metadata_truncated": bool(summary_omitted or coverage_omitted or collisions_omitted),
        "omitted_metadata": {"summary_fields": summary_omitted,
                             "coverage_fields": coverage_omitted, "collisions": collisions_omitted},
        "feed_cursor": state.get("cursors", {}).get("commons", {}).get("feed_cursor") or UNKNOWN,
    }
    used = len(_encoded(snapshot)) + 1  # The store appends one newline.
    if used > MAX_UTF8_BYTES:
        raise ValueError("status snapshot source identifiers exceed the byte budget")
    rows = snapshot["tasks"]
    for key in keys[:max_tasks]:
        row = _compact_task(view["tasks"][key])
        cost = len(_encoded(row)) + bool(rows)
        if used + cost > MAX_UTF8_BYTES:
            snapshot["byte_limited"] = True
            break
        rows.append(row)
        used += cost
    snapshot["omitted_tasks"] = len(keys) - len(rows)
    snapshot["truncated"] = bool(snapshot["omitted_tasks"])
    return snapshot
