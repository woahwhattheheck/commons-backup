"""Bounded, deterministic views of existing normalized work observations.

No provider reads, storage, dispatch, relevance model or peer-specific state.
build_index is a shared-cache input, not a bounded public response. select is
the public page boundary. Filtering never changes access to the underlying data.
Input is the existing WorkstreamStore.state() shape (already sanitized at ingest).
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import re
from urllib.parse import parse_qsl, urlencode, urlsplit

from .summary import epoch, item_freshness, reduce_source_health, source_freshness

SCHEMA = "commons-deathstar-context/v1"
DEFAULT_LIMIT = 20
MAX_LIMIT = 100
FILTER_LIMITS = {"query": 240, "owner": 4000, "provider": 4000,
                 "source": 512, "kind": 4000, "status": 4000}
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT, "default": DEFAULT_LIMIT},
        "offset": {"type": "integer", "minimum": 0, "default": 0},
        **{key: {"type": "string", "maxLength": size, "default": ""}
           for key, size in FILTER_LIMITS.items()},
        "if_revision": {"type": ["string", "null"], "maxLength": 64},
        "order": {"type": "string", "enum": ["priority", "seat", "oldest"],
                  "default": "priority", "description": "Discovery order within explicit priority bands; never a claim."},
        "seat": {"type": "string", "maxLength": 128, "pattern": "^[A-Za-z0-9_.:-]*$",
                 "default": "", "description": "Public routing label required only for order=seat; not a credential or assignment."},
    },
    "additionalProperties": False,
}
_PRIVATE_QUERY = re.compile(r"(?:^|[-_])(?:token|secret|password|signature|credential|authorization|api[-_]?key)(?:$|[-_])", re.I)


def _map(value):
    return value if isinstance(value, dict) else {}


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _identity(value, name):
    if not isinstance(value, str) or not value or len(value) > 512 or any(ord(c) < 32 for c in value):
        raise ValueError(name + " must be an exact nonempty WorkStore ID of at most 512 characters.")
    return value


def _text(value, size, omitted, name):
    if not isinstance(value, str):
        return None
    if len(value) > size:
        omitted[name] = len(value) - size
    return value[:size]


def _stamp(value):
    return value if isinstance(value, str) and len(value) <= 80 and epoch(value) is not None else None


def _scalar(value, omitted, name):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value if math.isfinite(value) else None
    return _text(value, 120, omitted, name)


def _link(value):
    # Omit unsafe/oversize links rather than returning a different destination.
    if value is None or value == "":
        return None, None
    if not isinstance(value, str) or len(value) > 2048:
        return None, "invalid_or_oversize"
    if any(c.isspace() or ord(c) < 32 for c in value):
        return None, "invalid"
    try:
        parts = urlsplit(value)
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname or parts.username is not None or parts.password is not None:
            return None, "unsafe"
        for key, _ in parse_qsl(parts.query, keep_blank_values=True) + parse_qsl(parts.fragment, keep_blank_values=True):
            if _PRIVATE_QUERY.search(key):
                return None, "credential_parameter"
    except ValueError:
        return None, "invalid"
    return value, None


def _source(raw, source_id, tick):
    omitted = {}
    coverage = _map(raw.get("coverage"))
    good_coverage = _map(raw.get("last_good_coverage"))
    url, link_omitted = _link(raw.get("url"))
    row = {
        "source_id": source_id,
        "provider": _text(raw.get("provider"), 512, omitted, "provider"),
        "label": _text(raw.get("label"), 180, omitted, "label"),
        "status": _text(raw.get("status"), 80, omitted, "status"),
        "sync_mode": _text(raw.get("sync_mode"), 80, omitted, "sync_mode"),
        "freshness": source_freshness(raw, tick),
        "observed_at": _stamp(raw.get("observed_at")),
        "last_good_observed_at": _stamp(raw.get("last_good_observed_at")),
        "last_attempt_at": _stamp(raw.get("last_attempt_at")),
        "last_success_at": _stamp(raw.get("last_success_at")),
        "activity_as_of": _stamp(raw.get("activity_as_of")),
        "retained_last_good": raw.get("retained_last_good") is True,
        "has_error": bool(raw.get("error")),
        "coverage": {
            "complete": coverage.get("complete") if type(coverage.get("complete")) is bool else None,
            "last_good_complete": good_coverage.get("complete") if type(good_coverage.get("complete")) is bool else None,
            "pagination_remaining": _scalar(coverage.get("pagination_remaining"), omitted, "coverage.pagination_remaining"),
        },
        "stale_after_seconds": _scalar(raw.get("stale_after_seconds", 900), omitted, "stale_after_seconds"),
        "url": url, "link_omitted": link_omitted,
        "missing": not bool(raw), "truncated_characters": omitted,
    }
    return row


def _priority(item, owner_work):
    # An explicit null override clears a source priority, just as owner direction does.
    value = owner_work["priority"] if "priority" in owner_work else item.get("priority")
    try:
        number = float(value)
        return number if not isinstance(value, bool) and math.isfinite(number) and number >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _item(raw, source, tick):
    omitted = {}
    source_id = _identity(raw.get("source_id"), "source_id")
    item_id = _identity(raw.get("id"), "item_id")
    owner_work = _map(raw.get("owner_work"))
    owner_revision = owner_work.get("revision", 0)
    job = _map(owner_work.get("job"))
    assigned = owner_work.get("owner") if "owner" in owner_work else job.get("owner")
    assignment_basis = "owner_work.owner" if "owner" in owner_work else "owner_work.job.owner" if "owner" in job else None
    action = owner_work.get("next_action") if "next_action" in owner_work else raw.get("next_action")
    priority_value = owner_work.get("priority") if "priority" in owner_work else raw.get("priority")
    url, link_omitted = _link(raw.get("url"))
    updated = _stamp(raw.get("updated_at"))
    observed_activity = _stamp(raw.get("activity_observed_at"))
    activities = [(epoch(stamp), field, stamp) for field, stamp in
                  (("updated_at", updated), ("activity_observed_at", observed_activity))
                  if stamp is not None and epoch(stamp) <= tick + 300]
    activity = max(activities) if activities else None
    row = {
        "source_id": source_id, "item_id": item_id,
        "_exact_filters": {key: value if isinstance(value, str) else "" for key, value in
                           (("owner", raw.get("owner")), ("kind", raw.get("kind")),
                            ("status", raw.get("status")), ("provider", raw.get("provider") or source.get("provider")))},
        "provider": _text(raw.get("provider") or source.get("provider"), 512, omitted, "provider"),
        "kind": _text(raw.get("kind"), 512, omitted, "kind"),
        "status": _text(raw.get("status"), 512, omitted, "status"),
        "title": _text(raw.get("title"), 180, omitted, "title"),
        "project": _text(raw.get("project"), 180, omitted, "project"),
        "owner": _text(raw.get("owner"), 512, omitted, "owner"),
        "owner_basis": "provider_record",
        "assigned_owner": _text(assigned, 512, omitted, "assigned_owner"),
        "assigned_owner_basis": assignment_basis if isinstance(assigned, str) and assigned else None,
        "owner_work_revision": owner_revision if type(owner_revision) is int and owner_revision >= 0 else None,
        "priority": _scalar(priority_value, omitted, "priority"),
        "priority_rank": _priority(raw, owner_work),
        "priority_basis": "owner_work.priority" if "priority" in owner_work else "provider_record.priority" if "priority" in raw else None,
        "next_action": _text(action, 280, omitted, "next_action"),
        "needs_attention": raw.get("needs_attention") is True,
        "control": bool(raw.get("control") or raw.get("countable") is False
                        or str(raw.get("row_type", "")).lower() == "control"
                        or str(raw.get("record_type", "")).lower() == "control"),
        "freshness": item_freshness(raw, source, tick),
        "updated_at": updated, "activity_observed_at": observed_activity,
        "activity_at": activity[2] if activity else None,
        "activity_basis": activity[1] if activity else None,
        "last_ingested_at": _stamp(raw.get("last_seen_at")),
        "source_observed_at": _stamp(source.get("last_good_observed_at")),
        "due_at": _stamp(owner_work.get("due_at") if "due_at" in owner_work else raw.get("due_at")),
        "url": url, "link_omitted": link_omitted,
        "detail_ref": {"source_id": source_id, "item_id": item_id},
        "detail_url": "/api/context/item?" + urlencode({"source_id": source_id, "item_id": item_id}),
        "truncated_characters": omitted,
    }
    return row


def _sort_key(row):
    rank = row["priority_rank"]
    activity = epoch(row["activity_at"])
    return (rank is None, rank if rank is not None else 0,
            activity is None, -(activity if activity is not None else 0),
            row["source_id"], row["item_id"])


def _discovery_key(row, order, seat):
    rank = row["priority_rank"]
    priority = (rank is None, rank if rank is not None else 0)
    identity = (row["source_id"], row["item_id"])
    if order == "seat":
        # Exclude the inventory revision: new observations must not reshuffle
        # the relative order of existing identities within a priority band.
        return priority + (_hash(["context-seat/v1", seat, *identity]),) + identity
    activity = epoch(row["activity_at"])
    return priority + (activity is None, activity if activity is not None else 0) + identity


def build_index(work, now=None):
    """Build an unpaginated compact shared index, never a public firehose.

    A new evaluation is needed as time advances even when the database signature
    does not change: freshness can cross a threshold. No age/read clock is hashed.
    The hash describes the compact inventory, not hidden bodies or event history.
    """
    if not isinstance(work, dict) or not isinstance(work.get("sources", []), list) or not isinstance(work.get("items", []), list):
        raise ValueError("Expected WorkstreamStore.state() sources/items lists.")
    current = datetime.now(timezone.utc) if now is None else now
    if not isinstance(current, datetime) or current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be a timezone-aware datetime.")
    tick = current.timestamp()
    sources = {}
    for raw in work.get("sources", []):
        if not isinstance(raw, dict):
            raise ValueError("Each source must be an object.")
        source_id = _identity(raw.get("id"), "source_id")
        if source_id in sources:
            raise ValueError("Duplicate source ID in WorkStore state.")
        sources[source_id] = raw
    source_stats = {key: {"records": 0, "retained_records": 0, "oldest_ingested_at": None}
                    for key in sources}
    rows, identities = [], set()
    missing = set()
    for raw in work.get("items", []):
        if not isinstance(raw, dict):
            raise ValueError("Each item must be an object.")
        source_id = _identity(raw.get("source_id"), "source_id")
        row = _item(raw, sources.get(source_id, {}), tick)
        identity = (source_id, row["item_id"])
        if identity in identities:
            raise ValueError("Duplicate source_id/item_id in WorkStore state.")
        identities.add(identity)
        rows.append(row)
        # Match summary's all-record debt detail from this same snapshot/tick.
        stats = source_stats.get(source_id)
        if stats is not None:
            stats["records"] += 1
            stats["retained_records"] += int(row["freshness"] == "retained")
            seen = raw.get("last_seen_at")
            if epoch(seen) is not None and (stats["oldest_ingested_at"] is None or seen < stats["oldest_ingested_at"]):
                stats["oldest_ingested_at"] = seen
        if source_id not in sources:
            missing.add(source_id)
    rows.sort(key=_sort_key)
    source_rows = [_source(sources.get(key, {}), key, tick) for key in sorted(set(sources) | missing)]
    # All-source health is independent of item filters/pages; empty pages still expose it.
    source_health = reduce_source_health(sources, tick)
    for debt in source_health["coverage_debt"]:
        debt.update(source_stats[debt["id"]])
    content = {"schema": SCHEMA, "items": rows, "sources": source_rows}
    return {**content, "content_revision": _hash(content),
            "evaluated_at": current.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "store_observed_at": _stamp(work.get("observed_at")),
            "input_source_count": len(sources),
            "source_health": source_health}


def select(index, limit=DEFAULT_LIMIT, offset=0, query="", owner="", provider="",
           source="", kind="", status="", if_revision=None, order="priority", seat=""):
    """Select a bounded page. Exact filters are ANDed; query is a substring.

    owner matches the provider-reported item.owner label, NOT an assigned worker.
    Text matching is case-insensitive except source (an exact stable identifier).
    Exact filters compare original normalized values, never truncated display text.
    Search examines only the returned compact fields, never hidden body/notes.
    Revision binds the inventory, selection, offset and limit. On unchanged,
    items=[] means reuse the previous identical page; sources and source_health stay present.
    Offset navigation is stable within a revision, not a historical snapshot.
    Optional seat/oldest ordering changes discovery only, never eligibility or
    ownership. All orders retain explicit priority bands and the same filters.
    """
    if type(limit) is not int or not 1 <= limit <= MAX_LIMIT or type(offset) is not int or offset < 0:
        raise ValueError("Context pagination requires limit 1..100 and nonnegative offset.")
    if not isinstance(order, str) or order not in {"priority", "seat", "oldest"}:
        raise ValueError("Context order must be priority, seat or oldest.")
    if not isinstance(seat, str) or len(seat) > 128 or re.fullmatch(r"[A-Za-z0-9_.:-]*", seat) is None:
        raise ValueError("Context seat must be a public routing label of at most 128 characters.")
    if (order == "seat") != bool(seat):
        raise ValueError("A nonempty seat is required only with context order=seat.")
    raw_filters = {"query": query, "owner": owner, "provider": provider, "source": source, "kind": kind, "status": status}
    filters = {}
    for key, value in raw_filters.items():
        if not isinstance(value, str) or len(value) > FILTER_LIMITS[key]:
            raise ValueError("Invalid context " + key + " filter.")
        filters[key] = value if key == "source" else value.strip().casefold() if key == "query" else value.casefold()
    if if_revision is not None and (not isinstance(if_revision, str) or len(if_revision) > 64):
        raise ValueError("Invalid context revision.")
    if not any(filters.values()):
        # Discovery ordering may sort this list; never reorder the shared index.
        matches = list(index["items"])
    else:
        matches = []
        for row in index["items"]:
            if filters["source"] and row["source_id"] != filters["source"]:
                continue
            if any(filters[key] and row["_exact_filters"][key].casefold() != filters[key]
                   for key in ("owner", "provider", "kind", "status")):
                continue
            if filters["query"]:
                searchable = " ".join(str(row.get(key) or "") for key in
                                      ("source_id", "item_id", "provider", "kind", "status",
                                       "title", "project", "owner", "assigned_owner", "next_action"))
                if filters["query"] not in searchable.casefold():
                    continue
            matches.append(row)
    if order != "priority":
        matches.sort(key=lambda row: _discovery_key(row, order, seat))
    page = matches[offset:offset + limit]
    source_ids = {row["source_id"] for row in page}
    page_sources = [row for row in index["sources"] if row["source_id"] in source_ids]
    health = index.get("source_health") or reduce_source_health({}, 0)
    # Bind visible all-source health into the opaque revision so empty/filtered
    # pages still invalidate when source freshness/coverage debt moves.
    selection = {"content": index["content_revision"], "filters": filters, "limit": limit, "offset": offset,
                 "source_health": {"state": health.get("state"), "coverage_debt_count": health.get("coverage_debt_count"),
                                   "freshness": health.get("freshness"), "total": health.get("total")}}
    if order != "priority":
        selection["ordering"] = {"order": order, "seat": seat}
    revision = _hash(selection)
    unchanged = if_revision == revision
    before = min(offset, len(matches))
    after = max(0, len(matches) - offset - len(page))
    result = {
        "ok": True, "schema": SCHEMA, "revision": revision, "unchanged": unchanged,
        "content_revision": index["content_revision"],
        "evaluated_at": index["evaluated_at"], "store_observed_at": index["store_observed_at"],
        "provider_requests": 0, "filters": filters,
        "counts": {"inventory_records": len(index["items"]), "matching_records": len(matches),
                   "page_records": len(page), "returned_records": 0 if unchanged else len(page),
                   "inventory_sources": index["input_source_count"],
                   "matching_sources": len({row["source_id"] for row in matches}),
                   "page_sources": len(page_sources)},
        "pagination": {"limit": limit, "offset": offset,
                       "next_offset": offset + len(page) if after else None,
                       "previous_offset": max(0, offset - limit) if offset else None},
        "omissions": {"filtered_records": len(index["items"]) - len(matches),
                     "records_before_page": before, "records_after_page": after,
                     "unchanged_records": len(page) if unchanged else 0,
                     "off_page_sources": len(index["sources"]) - len(page_sources)},
        "items": [] if unchanged else [{key: value for key, value in row.items() if key != "_exact_filters"} for row in page],
        "sources": page_sources,
        "source_health": health,
        "scope": "Existing normalized observations only; filters/pages do not restrict peer access. owner is a provider label; assigned_owner is explicit direction. No body or event history. source_health is all cached sources, independent of item filters and page membership.",
    }
    if order != "priority":
        result["ordering"] = {
            "order": order, "seat": seat, "priority_first": True,
            "basis": "stable_seat_identity_hash" if order == "seat" else "oldest_known_activity_unknown_last",
            "scope": "Discovery only; no reservation, eligibility decision or ownership transfer. Recheck source context and current claims before acting.",
        }
    # Prevent callers from mutating a shared cached index through returned rows.
    return json.loads(_json(result))


def project(work, now=None, **selection):
    """Convenience entry point; shared caches may call build_index/select separately."""
    return select(build_index(work, now=now), **selection)
