"""Authenticated organization authority records."""

from __future__ import annotations

import hmac
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from .core import (
    AUTHORITY_SCHEMA, MAX_ROUTES, MAX_SAFE_INTEGER, ActiveKey, AuthorityView,
    InputError, VerificationError, _canonical_bytes, _expect_exact_fields,
    _expect_hex64, _expect_int, _expect_key_id, _expect_object, _expect_slug,
    _format_time, _hmac_hex, _parse_time, _sha256, strict_json_loads,
)
from .storage import _read_regular_file

def _normalize_policy(value: Any) -> dict[str, int]:
    policy = _expect_object(value, "policy")
    fields = {
        "policy_generation",
        "contact_cooldown_seconds",
        "request_max_age_seconds",
        "ledger_max_age_seconds",
        "ready_validity_seconds",
        "max_future_skew_seconds",
    }
    _expect_exact_fields(policy, fields, "policy")
    return {
        "policy_generation": _expect_int(
            policy["policy_generation"], "policy.policy_generation", minimum=1, maximum=MAX_SAFE_INTEGER
        ),
        "contact_cooldown_seconds": _expect_int(
            policy["contact_cooldown_seconds"],
            "policy.contact_cooldown_seconds",
            minimum=60,
            maximum=2_592_000,
        ),
        "request_max_age_seconds": _expect_int(
            policy["request_max_age_seconds"],
            "policy.request_max_age_seconds",
            minimum=30,
            maximum=86_400,
        ),
        "ledger_max_age_seconds": _expect_int(
            policy["ledger_max_age_seconds"],
            "policy.ledger_max_age_seconds",
            minimum=30,
            maximum=86_400,
        ),
        "ready_validity_seconds": _expect_int(
            policy["ready_validity_seconds"],
            "policy.ready_validity_seconds",
            minimum=15,
            maximum=600,
        ),
        "max_future_skew_seconds": _expect_int(
            policy["max_future_skew_seconds"],
            "policy.max_future_skew_seconds",
            minimum=0,
            maximum=300,
        ),
    }


def _normalize_authority_document(document: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    fields = {
        "schema",
        "organization_scope_sha256",
        "route_scope_sha256s",
        "policy",
        "issued_at",
        "valid_until",
        "key_id",
        "verifier_id",
        "signature",
    }
    _expect_exact_fields(document, fields, "authority")
    if document["schema"] != AUTHORITY_SCHEMA:
        raise InputError("unsupported authority schema")
    organization = _expect_hex64(document["organization_scope_sha256"], "organization_scope_sha256")
    routes_raw = document["route_scope_sha256s"]
    if type(routes_raw) is not list or not routes_raw or len(routes_raw) > MAX_ROUTES:
        raise InputError("route_scope_sha256s must be a non-empty bounded list")
    routes = sorted(_expect_hex64(item, "route_scope_sha256s[]") for item in routes_raw)
    if len(set(routes)) != len(routes):
        raise InputError("route_scope_sha256s contains duplicates")
    body = {
        "schema": AUTHORITY_SCHEMA,
        "organization_scope_sha256": organization,
        "route_scope_sha256s": routes,
        "policy": _normalize_policy(document["policy"]),
        "issued_at": _format_time(_parse_time(document["issued_at"], "issued_at")),
        "valid_until": _format_time(_parse_time(document["valid_until"], "valid_until")),
        "key_id": _expect_key_id(document["key_id"]),
        "verifier_id": _expect_slug(document["verifier_id"], "verifier_id"),
    }
    signature = _expect_hex64(document["signature"], "signature")
    return body, signature


def _load_authority(root: Path, active: ActiveKey, organization: str, now: datetime) -> AuthorityView:
    raw = _read_regular_file(root / "authorities" / f"{organization}.json", limit=262_144, private=True)
    try:
        document = _expect_object(strict_json_loads(raw), "authority")
        body, signature = _normalize_authority_document(document)
    except InputError as exc:
        raise VerificationError("retained authority is malformed") from exc
    if body["organization_scope_sha256"] != organization:
        raise VerificationError("authority path/scope mismatch")
    if body["key_id"] != active.key_id or body["verifier_id"] != active.verifier_id:
        raise VerificationError("authority is not bound to the active verifier generation")
    expected = _hmac_hex(active.key, body)
    if not hmac.compare_digest(signature, expected):
        raise VerificationError("authority HMAC is invalid")
    issued = _parse_time(body["issued_at"], "issued_at")
    valid_until = _parse_time(body["valid_until"], "valid_until")
    policy = body["policy"]
    skew = timedelta(seconds=policy["max_future_skew_seconds"])
    if issued > now + skew:
        raise VerificationError("authority is future-issued")
    if valid_until < now:
        raise VerificationError("authority is expired")
    if valid_until <= issued:
        raise VerificationError("authority validity interval is invalid")
    if valid_until - issued > timedelta(days=366):
        raise VerificationError("authority validity interval is unbounded")
    canonical = {**body, "signature": signature}
    return AuthorityView(
        organization_scope_sha256=organization,
        route_scope_sha256s=tuple(body["route_scope_sha256s"]),
        policy_generation=policy["policy_generation"],
        contact_cooldown_seconds=policy["contact_cooldown_seconds"],
        request_max_age_seconds=policy["request_max_age_seconds"],
        ledger_max_age_seconds=policy["ledger_max_age_seconds"],
        ready_validity_seconds=policy["ready_validity_seconds"],
        max_future_skew_seconds=policy["max_future_skew_seconds"],
        issued_at=issued,
        valid_until=valid_until,
        key_id=active.key_id,
        verifier_id=active.verifier_id,
        digest=_sha256(_canonical_bytes(canonical)),
    )
