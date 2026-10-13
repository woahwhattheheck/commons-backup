"""Authenticated retained organization event ledger."""

from __future__ import annotations

import hmac
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from .authority import AuthorityView
from .core import (
    LEDGER_SCHEMA, MAX_EVENTS, MAX_JSON_BYTES, MAX_SAFE_INTEGER, ActiveKey,
    EventView, InputError, LedgerView, VerificationError, _canonical_bytes,
    _expect_exact_fields, _expect_hex64, _expect_int, _expect_key_id,
    _expect_object, _expect_slug, _format_time, _hmac_hex, _parse_time,
    _sha256, strict_json_loads,
)
from .events import _normalize_event
from .ledger_head import _verify_current_ledger_head
from .storage import _read_regular_file


def _normalize_ledger_document(document: Mapping[str, Any]) -> tuple[dict[str, Any], str, tuple[EventView, ...], tuple[str, ...]]:
    fields = {
        "schema",
        "organization_scope_sha256",
        "generation",
        "policy_generation",
        "updated_at",
        "events",
        "key_id",
        "verifier_id",
        "signature",
    }
    _expect_exact_fields(document, fields, "ledger")
    if document["schema"] != LEDGER_SCHEMA:
        raise InputError("unsupported ledger schema")
    events_raw = document["events"]
    if type(events_raw) is not list or len(events_raw) > MAX_EVENTS:
        raise InputError("events must be a bounded list")
    normalized_rows: list[dict[str, Any]] = []
    views: list[EventView] = []
    for item in events_raw:
        row, view = _normalize_event(item)
        normalized_rows.append(row)
        views.append(view)
    order = sorted(range(len(views)), key=lambda index: (views[index].observed_at, views[index].event_id, views[index].canonical))
    normalized_rows = [normalized_rows[index] for index in order]
    views = [views[index] for index in order]
    conflicts: set[str] = set()
    seen: dict[str, bytes] = {}
    signed_rows: list[dict[str, Any]] = []
    dedup_views: list[EventView] = []
    for row, view in zip(normalized_rows, views):
        prior = seen.get(view.event_id)
        if prior is None:
            seen[view.event_id] = view.canonical
            signed_rows.append(row)
            dedup_views.append(view)
        elif prior != view.canonical:
            # Preserve both conflicting meanings in the authenticated projection,
            # but discard byte-identical replay so replay is logically and
            # cryptographically idempotent.
            conflicts.add(f"EVENT_ID_MUTATION:{view.event_id}")
            signed_rows.append(row)
    generation = _expect_int(document["generation"], "ledger.generation", minimum=0, maximum=MAX_SAFE_INTEGER)
    if generation != len(seen):
        conflicts.add("LEDGER_GENERATION_COUNT_MISMATCH")
    body = {
        "schema": LEDGER_SCHEMA,
        "organization_scope_sha256": _expect_hex64(
            document["organization_scope_sha256"], "ledger.organization_scope_sha256"
        ),
        "generation": generation,
        "policy_generation": _expect_int(
            document["policy_generation"], "ledger.policy_generation", minimum=1, maximum=MAX_SAFE_INTEGER
        ),
        "updated_at": _format_time(_parse_time(document["updated_at"], "ledger.updated_at")),
        "events": signed_rows,
        "key_id": _expect_key_id(document["key_id"]),
        "verifier_id": _expect_slug(document["verifier_id"], "ledger.verifier_id"),
    }
    signature = _expect_hex64(document["signature"], "ledger.signature")
    return body, signature, tuple(dedup_views), tuple(sorted(conflicts))


def _load_ledger(
    root: Path,
    active: ActiveKey,
    authority: AuthorityView,
    now: datetime,
) -> LedgerView:
    organization = authority.organization_scope_sha256
    raw = _read_regular_file(root / "ledgers" / f"{organization}.json", limit=MAX_JSON_BYTES, private=True)
    try:
        document = _expect_object(strict_json_loads(raw), "ledger")
        body, signature, events, conflicts = _normalize_ledger_document(document)
    except InputError as exc:
        raise VerificationError("retained ledger is malformed") from exc
    if body["organization_scope_sha256"] != organization:
        raise VerificationError("ledger path/scope mismatch")
    if body["policy_generation"] != authority.policy_generation:
        raise VerificationError("ledger policy generation mismatch")
    if body["key_id"] != active.key_id or body["verifier_id"] != active.verifier_id:
        raise VerificationError("ledger is not bound to the active verifier generation")
    if not hmac.compare_digest(signature, _hmac_hex(active.key, body)):
        raise VerificationError("ledger HMAC is invalid")
    updated = _parse_time(body["updated_at"], "ledger.updated_at")
    skew = timedelta(seconds=authority.max_future_skew_seconds)
    if updated > now + skew:
        raise VerificationError("ledger is future-updated")
    if updated < authority.issued_at:
        raise VerificationError("ledger predates its authority generation")
    if now - updated > timedelta(seconds=authority.ledger_max_age_seconds):
        raise VerificationError("ledger coverage is stale")
    allowed_routes = set(authority.route_scope_sha256s)
    extra_conflicts = set(conflicts)
    for event in events:
        if event.organization_scope_sha256 != organization:
            extra_conflicts.add(f"EVENT_ORGANIZATION_TRANSPLANT:{event.event_id}")
        if event.route_scope_sha256 not in allowed_routes:
            extra_conflicts.add(f"UNKNOWN_ROUTE_SCOPE:{event.event_id}")
        if event.observed_at > now + skew:
            extra_conflicts.add(f"FUTURE_EVENT:{event.event_id}")
        if event.observed_at > updated + skew:
            extra_conflicts.add(f"EVENT_AFTER_LEDGER_UPDATE:{event.event_id}")
    canonical = {**body, "signature": signature}
    state_body = dict(body)
    state_body.pop("updated_at")
    ledger = LedgerView(
        organization_scope_sha256=organization,
        generation=body["generation"],
        policy_generation=body["policy_generation"],
        updated_at=updated,
        events=events,
        conflicts=tuple(sorted(extra_conflicts)),
        key_id=active.key_id,
        verifier_id=active.verifier_id,
        digest=_sha256(_canonical_bytes(canonical)),
        state_digest=_sha256(_canonical_bytes(state_body)),
    )
    _verify_current_ledger_head(root, active, authority, ledger, now)
    return ledger
