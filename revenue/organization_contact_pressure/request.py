"""Strict organization-pressure request schema."""

from __future__ import annotations

from typing import Any

from .core import (
    REQUEST_SCHEMA, InputError, _expect_exact_fields, _expect_hex64,
    _expect_object, _expect_slug, _format_time, _parse_time, strict_json_loads,
)

def _normalize_request(data: bytes) -> dict[str, Any]:
    request = _expect_object(strict_json_loads(data), "request")
    fields = {
        "schema",
        "organization_scope_sha256",
        "proposed_route_scope_sha256",
        "proposed_event_id",
        "operation_id",
        "requested_at",
        "source_ref_sha256",
    }
    _expect_exact_fields(request, fields, "request")
    if request["schema"] != REQUEST_SCHEMA:
        raise InputError("unsupported request schema")
    return {
        "schema": REQUEST_SCHEMA,
        "organization_scope_sha256": _expect_hex64(
            request["organization_scope_sha256"], "organization_scope_sha256"
        ),
        "proposed_route_scope_sha256": _expect_hex64(
            request["proposed_route_scope_sha256"], "proposed_route_scope_sha256"
        ),
        "proposed_event_id": _expect_hex64(request["proposed_event_id"], "proposed_event_id"),
        "operation_id": _expect_slug(request["operation_id"], "operation_id"),
        "requested_at": _format_time(_parse_time(request["requested_at"], "requested_at")),
        "source_ref_sha256": _expect_hex64(request["source_ref_sha256"], "source_ref_sha256"),
    }
