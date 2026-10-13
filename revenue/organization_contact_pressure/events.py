"""Strict canonical organization contact events."""

from __future__ import annotations

from typing import Any

from .core import (
    EVENT_KINDS, EVENT_OWNER_RELEASE, EventView, InputError, _canonical_bytes,
    _expect_exact_fields, _expect_hex64, _expect_object, _expect_string,
    _format_time, _parse_time,
)

def _normalize_event(value: Any) -> tuple[dict[str, Any], EventView]:
    event = _expect_object(value, "event")
    fields = {
        "event_id",
        "organization_scope_sha256",
        "route_scope_sha256",
        "kind",
        "observed_at",
        "source_ref_sha256",
        "provider_evidence_sha256",
        "target_event_id",
    }
    _expect_exact_fields(event, fields, "event")
    kind = _expect_string(event["kind"], "event.kind", maximum=32)
    if kind not in EVENT_KINDS:
        raise InputError("unsupported event.kind")
    target = event["target_event_id"]
    if kind == EVENT_OWNER_RELEASE:
        target = _expect_hex64(target, "event.target_event_id")
    elif target is not None:
        raise InputError("only OWNER_RELEASE may set target_event_id")
    body = {
        "event_id": _expect_hex64(event["event_id"], "event.event_id"),
        "organization_scope_sha256": _expect_hex64(
            event["organization_scope_sha256"], "event.organization_scope_sha256"
        ),
        "route_scope_sha256": _expect_hex64(event["route_scope_sha256"], "event.route_scope_sha256"),
        "kind": kind,
        "observed_at": _format_time(_parse_time(event["observed_at"], "event.observed_at")),
        "source_ref_sha256": _expect_hex64(event["source_ref_sha256"], "event.source_ref_sha256"),
        "provider_evidence_sha256": _expect_hex64(
            event["provider_evidence_sha256"], "event.provider_evidence_sha256"
        ),
        "target_event_id": target,
    }
    canonical = _canonical_bytes(body)
    return body, EventView(
        event_id=body["event_id"],
        organization_scope_sha256=body["organization_scope_sha256"],
        route_scope_sha256=body["route_scope_sha256"],
        kind=kind,
        observed_at=_parse_time(body["observed_at"], "event.observed_at"),
        source_ref_sha256=body["source_ref_sha256"],
        provider_evidence_sha256=body["provider_evidence_sha256"],
        target_event_id=target,
        canonical=canonical,
    )
