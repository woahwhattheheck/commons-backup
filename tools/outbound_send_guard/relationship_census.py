#!/usr/bin/env python3
"""Offline provider relationship census / custody projection.

This module intentionally grants no external-send authority.  It authenticates a
caller-supplied provider/workspace snapshot, binds every route observation to an
opaque target, and projects current custody so downstream dedupe + lease gates can
fail closed before outreach.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

CENSUS_SCHEMA = "outbound-provider-relationship-census/v1"
AUTHORITY_SCHEMA = "outbound-provider-relationship-census-authority/v1"
RECEIPT_SCHEMA = "outbound-provider-relationship-custody-receipt/v1"
TARGET_BINDING_SCHEMA = "outbound-provider-relationship-target-binding/v1"
TRANSFER_SCHEMA = "outbound-provider-relationship-transfer/v1"
DEFAULT_MAX_SNAPSHOT_AGE_SECONDS = 900
DEFAULT_MAX_FUTURE_SKEW_SECONDS = 300
MAX_ROUTES = 256
MAX_BYTES = 2 * 1024 * 1024
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")

RELATIONSHIP_STATES = frozenset(
    {
        "CLEAR",
        "ACTIVE_OWNER",
        "WAITING_REPLY",
        "INBOUND_NEEDS_OWNER",
        "UNSUBSCRIBED",
        "DNR",
        "HARD_BOUNCE",
        "TRANSFER_PENDING",
        "TRANSFERRED",
        "CLOSED",
    }
)
OWNER_REQUIRED_STATES = frozenset(
    {
        "ACTIVE_OWNER",
        "WAITING_REPLY",
        "INBOUND_NEEDS_OWNER",
        "TRANSFER_PENDING",
        "TRANSFERRED",
        "CLOSED",
    }
)
CONTACT_BLOCK_STATES = frozenset({"UNSUBSCRIBED", "DNR", "HARD_BOUNCE"})


class CensusError(ValueError):
    pass


class DuplicateKeyError(CensusError):
    pass


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateKeyError(f"duplicate JSON object key: {key}")
        out[key] = value
    return out


def _dict(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise CensusError(f"{label} must be an object")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise CensusError(f"{label} must be a list")
    return value


def _only(obj: Mapping[str, Any], allowed: set[str], label: str) -> None:
    extra = set(obj) - allowed
    if extra:
        raise CensusError(f"{label} has unknown fields: {', '.join(sorted(extra))}")


def _text(value: Any, label: str, *, max_len: int = 256) -> str:
    if type(value) is not str:
        raise CensusError(f"{label} must be a string")
    text = value.strip()
    if not text:
        raise CensusError(f"{label} must not be empty")
    if len(text) > max_len:
        raise CensusError(f"{label} exceeds {max_len} characters")
    if any(ord(ch) < 32 for ch in text):
        raise CensusError(f"{label} contains control characters")
    return text


def _token(value: Any, label: str) -> str:
    text = _text(value, label)
    if not _TOKEN_RE.fullmatch(text):
        raise CensusError(f"{label} contains unsupported characters")
    return text


def _no_email_token(value: Any, label: str) -> str:
    text = _token(value, label)
    if "@" in text:
        raise CensusError(f"{label} must be opaque and must not contain a raw email address")
    return text


def _opaque_target(value: Any, label: str = "target_scope") -> str:
    return _no_email_token(value, label)


def _sha256(value: Any, label: str) -> str:
    text = _text(value, label, max_len=64)
    if not _HEX64_RE.fullmatch(text):
        raise CensusError(f"{label} must be lowercase SHA-256 hex")
    return text


def _bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise CensusError(f"{label} must be a boolean")
    return value


def _int(value: Any, label: str, *, low: int, high: int) -> int:
    if type(value) is not int:
        raise CensusError(f"{label} must be an integer")
    if not low <= value <= high:
        raise CensusError(f"{label} must be between {low} and {high}")
    return value


def _time(value: Any, label: str) -> datetime:
    text = _text(value, label, max_len=64)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise CensusError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CensusError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _fmt(value: datetime) -> str:
    value = value.astimezone(timezone.utc)
    return value.isoformat(
        timespec="microseconds" if value.microsecond else "seconds"
    ).replace("+00:00", "Z")


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def digest_object(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def parse_json_bytes(raw: bytes, label: str = "census") -> dict[str, Any]:
    if type(raw) is not bytes:
        raise CensusError(f"{label} bytes must be bytes")
    if len(raw) > MAX_BYTES:
        raise CensusError(f"{label} exceeds {MAX_BYTES} bytes")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise CensusError(f"{label} must be UTF-8 JSON") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                CensusError(f"{label} contains non-finite number {token}")
            ),
        )
    except CensusError:
        raise
    except json.JSONDecodeError as exc:
        raise CensusError(f"{label} is not valid JSON: {exc.msg}") from exc
    return _dict(value, label)


def target_binding_sha256(target_scope: str, route_sha256: str) -> str:
    target = _opaque_target(target_scope)
    route = _sha256(route_sha256, "route_sha256")
    return digest_object(
        {
            "schema_version": TARGET_BINDING_SCHEMA,
            "target_scope": target,
            "route_sha256": route,
        }
    )


def route_set_sha256(target_scope: str, route_sha256s: list[str]) -> str:
    target = _opaque_target(target_scope)
    normalized = sorted({_sha256(value, "route_sha256") for value in route_sha256s})
    if not normalized:
        raise CensusError("route_sha256s must not be empty")
    return digest_object(
        {
            "schema_version": TARGET_BINDING_SCHEMA,
            "target_scope": target,
            "route_sha256s": normalized,
        }
    )


def _parse_routes(raw: Any, target_scope: str, declared_routes: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    rows = _list(raw, "census.route_observations")
    if not rows:
        raise CensusError("census.route_observations must not be empty")
    if len(rows) > MAX_ROUTES:
        raise CensusError(f"census.route_observations exceeds {MAX_ROUTES} rows")
    declared = set(declared_routes)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    binding_failures: list[str] = []
    for index, item in enumerate(rows):
        label = f"census.route_observations[{index}]"
        obj = _dict(item, label)
        _only(
            obj,
            {
                "route_sha256",
                "target_binding_sha256",
                "state",
                "owner",
                "generation",
                "observed_at",
                "event_sha256",
            },
            label,
        )
        route = _sha256(obj.get("route_sha256"), f"{label}.route_sha256")
        if route not in declared:
            binding_failures.append(f"UNDECLARED_ROUTE:{route[:12]}")
        if route in seen:
            raise CensusError(f"{label}.route_sha256 is duplicated")
        seen.add(route)
        binding = _sha256(
            obj.get("target_binding_sha256"), f"{label}.target_binding_sha256"
        )
        expected_binding = target_binding_sha256(target_scope, route)
        if binding != expected_binding:
            binding_failures.append(f"TARGET_BINDING_MISMATCH:{route[:12]}")
        state = _token(obj.get("state"), f"{label}.state")
        if state not in RELATIONSHIP_STATES:
            raise CensusError(f"{label}.state is unsupported")
        owner_raw = obj.get("owner")
        owner = None if owner_raw is None else _no_email_token(owner_raw, f"{label}.owner")
        generation = _int(obj.get("generation"), f"{label}.generation", low=0, high=2**63 - 1)
        observed_at = _time(obj.get("observed_at"), f"{label}.observed_at")
        event_sha = _sha256(obj.get("event_sha256"), f"{label}.event_sha256")
        if state in OWNER_REQUIRED_STATES and owner is None:
            binding_failures.append(f"OWNER_MISSING:{route[:12]}")
        if state == "CLEAR" and owner is not None:
            binding_failures.append(f"CLEAR_ROUTE_HAS_OWNER:{route[:12]}")
        out.append(
            {
                "route_sha256": route,
                "target_binding_sha256": binding,
                "state": state,
                "owner": owner,
                "generation": generation,
                "observed_at": _fmt(observed_at),
                "event_sha256": event_sha,
            }
        )
    missing = sorted(declared - seen)
    for route in missing:
        binding_failures.append(f"DECLARED_ROUTE_MISSING:{route[:12]}")
    out.sort(key=lambda row: row["route_sha256"])
    return out, binding_failures


def _parse_relationship(raw: Any) -> dict[str, Any]:
    obj = _dict(raw, "census.relationship")
    _only(obj, {"state", "owner", "generation"}, "census.relationship")
    state = _token(obj.get("state"), "census.relationship.state")
    if state not in RELATIONSHIP_STATES:
        raise CensusError("census.relationship.state is unsupported")
    owner_raw = obj.get("owner")
    owner = None if owner_raw is None else _no_email_token(owner_raw, "census.relationship.owner")
    generation = _int(
        obj.get("generation"), "census.relationship.generation", low=0, high=2**63 - 1
    )
    if state == "CLEAR" and owner is not None:
        raise CensusError("CLEAR relationship must not name an owner")
    if state in OWNER_REQUIRED_STATES and owner is None:
        raise CensusError(f"{state} relationship requires an owner")
    return {"state": state, "owner": owner, "generation": generation}


def _parse_transfer(raw: Any, *, target_scope: str, route_hashes: list[str]) -> dict[str, Any] | None:
    if raw is None:
        return None
    obj = _dict(raw, "census.transfer")
    _only(
        obj,
        {
            "schema_version",
            "target_route_set_sha256",
            "from_owner",
            "to_owner",
            "from_generation",
            "to_generation",
            "release_actor",
            "release_authority",
            "released_at",
            "release_ref_sha256",
            "accept_actor",
            "accepted_at",
            "accept_ref_sha256",
        },
        "census.transfer",
    )
    if obj.get("schema_version") != TRANSFER_SCHEMA:
        raise CensusError(f"census.transfer.schema_version must equal {TRANSFER_SCHEMA!r}")
    result = {
        "schema_version": TRANSFER_SCHEMA,
        "target_route_set_sha256": _sha256(
            obj.get("target_route_set_sha256"), "census.transfer.target_route_set_sha256"
        ),
        "from_owner": _no_email_token(obj.get("from_owner"), "census.transfer.from_owner"),
        "to_owner": _no_email_token(obj.get("to_owner"), "census.transfer.to_owner"),
        "from_generation": _int(
            obj.get("from_generation"), "census.transfer.from_generation", low=0, high=2**63 - 2
        ),
        "to_generation": _int(
            obj.get("to_generation"), "census.transfer.to_generation", low=1, high=2**63 - 1
        ),
        "release_actor": _no_email_token(obj.get("release_actor"), "census.transfer.release_actor"),
        "release_authority": _token(
            obj.get("release_authority"), "census.transfer.release_authority"
        ),
        "released_at": _fmt(_time(obj.get("released_at"), "census.transfer.released_at")),
        "release_ref_sha256": _sha256(
            obj.get("release_ref_sha256"), "census.transfer.release_ref_sha256"
        ),
        "accept_actor": _no_email_token(obj.get("accept_actor"), "census.transfer.accept_actor"),
        "accepted_at": _fmt(_time(obj.get("accepted_at"), "census.transfer.accepted_at")),
        "accept_ref_sha256": _sha256(
            obj.get("accept_ref_sha256"), "census.transfer.accept_ref_sha256"
        ),
    }
    expected_set = route_set_sha256(target_scope, route_hashes)
    if result["target_route_set_sha256"] != expected_set:
        result["_semantic_error"] = "TRANSFER_TARGET_BINDING_MISMATCH"
    elif result["to_generation"] != result["from_generation"] + 1:
        result["_semantic_error"] = "TRANSFER_GENERATION_NOT_INCREMENTED"
    elif not (
        result["release_actor"] == result["from_owner"]
        or result["release_authority"] == "ADMIN"
    ):
        result["_semantic_error"] = "TRANSFER_RELEASE_NOT_AUTHORIZED"
    elif result["release_authority"] not in {"OWNER", "ADMIN"}:
        result["_semantic_error"] = "TRANSFER_RELEASE_AUTHORITY_INVALID"
    elif result["accept_actor"] != result["to_owner"]:
        result["_semantic_error"] = "TRANSFER_ACCEPTOR_MISMATCH"
    elif _time(result["accepted_at"], "census.transfer.accepted_at") < _time(
        result["released_at"], "census.transfer.released_at"
    ):
        result["_semantic_error"] = "TRANSFER_ACCEPT_PRECEDES_RELEASE"
    return result


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    _only(
        raw,
        {
            "schema_version",
            "target_scope",
            "route_sha256s",
            "current_worker",
            "claimed_generation",
            "census",
            "authority",
        },
        "census input",
    )
    if raw.get("schema_version") != CENSUS_SCHEMA:
        raise CensusError(f"schema_version must equal {CENSUS_SCHEMA!r}")
    target_scope = _opaque_target(raw.get("target_scope"))
    current_worker = _no_email_token(raw.get("current_worker"), "current_worker")
    claimed_generation = _int(
        raw.get("claimed_generation"), "claimed_generation", low=0, high=2**63 - 1
    )
    route_list = _list(raw.get("route_sha256s"), "route_sha256s")
    if not route_list:
        raise CensusError("route_sha256s must not be empty")
    if len(route_list) > MAX_ROUTES:
        raise CensusError(f"route_sha256s exceeds {MAX_ROUTES} rows")
    route_hashes = sorted({_sha256(value, "route_sha256s[]") for value in route_list})
    if len(route_hashes) != len(route_list):
        raise CensusError("route_sha256s must be unique")

    census = _dict(raw.get("census"), "census")
    _only(
        census,
        {
            "provider",
            "workspace_sha256",
            "snapshot_id",
            "snapshot_at",
            "coverage_started_at",
            "complete",
            "route_observations",
            "relationship",
            "transfer",
        },
        "census",
    )
    provider = _no_email_token(census.get("provider"), "census.provider")
    workspace_sha = _sha256(census.get("workspace_sha256"), "census.workspace_sha256")
    snapshot_id = _no_email_token(census.get("snapshot_id"), "census.snapshot_id")
    snapshot_at = _time(census.get("snapshot_at"), "census.snapshot_at")
    coverage_started_at = _time(census.get("coverage_started_at"), "census.coverage_started_at")
    complete = _bool(census.get("complete"), "census.complete")
    relationship = _parse_relationship(census.get("relationship"))
    route_observations, binding_failures = _parse_routes(
        census.get("route_observations"), target_scope, route_hashes
    )
    transfer = _parse_transfer(
        census.get("transfer"), target_scope=target_scope, route_hashes=route_hashes
    )

    authority_raw = raw.get("authority")
    if authority_raw is None:
        key_id = "unsigned"
        signature = None
    else:
        authority = _dict(authority_raw, "authority")
        _only(authority, {"schema_version", "scheme", "key_id", "signature_sha256"}, "authority")
        if authority.get("schema_version") != AUTHORITY_SCHEMA:
            raise CensusError(f"authority.schema_version must equal {AUTHORITY_SCHEMA!r}")
        if authority.get("scheme") != "HMAC-SHA256":
            raise CensusError("authority.scheme must equal 'HMAC-SHA256'")
        key_id = _token(authority.get("key_id"), "authority.key_id")
        signature_raw = authority.get("signature_sha256")
        signature = None if signature_raw is None else _sha256(signature_raw, "authority.signature_sha256")

    normalized_census = {
        "provider": provider,
        "workspace_sha256": workspace_sha,
        "snapshot_id": snapshot_id,
        "snapshot_at": _fmt(snapshot_at),
        "coverage_started_at": _fmt(coverage_started_at),
        "complete": complete,
        "route_observations": route_observations,
        "relationship": relationship,
        "transfer": ({key: value for key, value in transfer.items() if not key.startswith("_")} if transfer else None),
    }
    return {
        "schema_version": CENSUS_SCHEMA,
        "target_scope": target_scope,
        "route_sha256s": route_hashes,
        "current_worker": current_worker,
        "claimed_generation": claimed_generation,
        "census": normalized_census,
        "authority": {
            "schema_version": AUTHORITY_SCHEMA,
            "scheme": "HMAC-SHA256",
            "key_id": key_id,
            "signature_sha256": signature,
        },
        "_binding_failures": binding_failures,
        "_transfer_semantic_error": transfer.get("_semantic_error") if transfer else None,
    }


def signing_material(normalized: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": AUTHORITY_SCHEMA,
        "key_id": normalized["authority"]["key_id"],
        "target_scope": normalized["target_scope"],
        "route_sha256s": normalized["route_sha256s"],
        "census": normalized["census"],
    }


def compute_signature(normalized: Mapping[str, Any], key: bytes) -> str:
    if type(key) is not bytes or len(key) < 32:
        raise CensusError("provider HMAC key must contain at least 32 bytes")
    return hmac.new(key, canonical_bytes(signing_material(normalized)), hashlib.sha256).hexdigest()


def _authority_valid(normalized: Mapping[str, Any], key: bytes) -> bool:
    try:
        expected = compute_signature(normalized, key)
    except CensusError:
        return False
    signature = normalized["authority"].get("signature_sha256")
    return isinstance(signature, str) and hmac.compare_digest(expected, signature)


def _semantic_reasons(
    normalized: Mapping[str, Any], *, key: bytes, now: datetime, max_snapshot_age_seconds: int, max_future_skew_seconds: int
) -> list[str]:
    reasons: list[str] = []
    census = normalized["census"]
    snapshot_at = _time(census["snapshot_at"], "census.snapshot_at")
    coverage_started_at = _time(census["coverage_started_at"], "census.coverage_started_at")
    if not _authority_valid(normalized, key):
        reasons.append("AUTHORITY_SIGNATURE_INVALID")
    if census["complete"] is not True:
        reasons.append("CENSUS_INCOMPLETE")
    if coverage_started_at > snapshot_at:
        reasons.append("COVERAGE_START_AFTER_SNAPSHOT")
    if snapshot_at > now + timedelta(seconds=max_future_skew_seconds):
        reasons.append("SNAPSHOT_IN_FUTURE")
    if snapshot_at < now - timedelta(seconds=max_snapshot_age_seconds):
        reasons.append("SNAPSHOT_STALE")
    reasons.extend(normalized["_binding_failures"])

    for row in census["route_observations"]:
        if _time(row["observed_at"], "route observed_at") > snapshot_at:
            reasons.append(f"ROUTE_AFTER_SNAPSHOT:{row['route_sha256'][:12]}")

    relationship = census["relationship"]
    rel_state = relationship["state"]
    rel_owner = relationship["owner"]
    rel_generation = relationship["generation"]
    if rel_generation != normalized["claimed_generation"]:
        reasons.append("CLAIMED_GENERATION_MISMATCH")
    if rel_state in CONTACT_BLOCK_STATES:
        reasons.append(f"CONTACT_BLOCKED:{rel_state}")
    elif rel_state != "CLEAR" and rel_owner != normalized["current_worker"]:
        reasons.append("CURRENT_OWNER_MISMATCH")

    # Route-level state may reveal an older/parallel owner even if aggregate state
    # is accidentally marked CLEAR.  Any such contradiction holds the census.
    nonclear_rows = [row for row in census["route_observations"] if row["state"] != "CLEAR"]
    if rel_state == "CLEAR" and nonclear_rows:
        reasons.append("RELATIONSHIP_CLEAR_WITH_NONCLEAR_ROUTE")
    if rel_state != "CLEAR" and not nonclear_rows:
        reasons.append("RELATIONSHIP_NOT_SUPPORTED_BY_ROUTE_HISTORY")

    for row in census["route_observations"]:
        if row["generation"] > rel_generation:
            reasons.append(f"ROUTE_GENERATION_AHEAD:{row['route_sha256'][:12]}")
        if row["state"] in CONTACT_BLOCK_STATES:
            reasons.append(f"ROUTE_CONTACT_BLOCKED:{row['route_sha256'][:12]}:{row['state']}")
        elif row["state"] != "CLEAR":
            if row["owner"] != normalized["current_worker"]:
                reasons.append(f"ROUTE_OWNER_MISMATCH:{row['route_sha256'][:12]}")
            if row["generation"] != rel_generation:
                reasons.append(f"ROUTE_GENERATION_MISMATCH:{row['route_sha256'][:12]}")

    transfer = census["transfer"]
    transfer_error = normalized["_transfer_semantic_error"]
    if transfer_error:
        reasons.append(transfer_error)
    if rel_state in {"TRANSFER_PENDING", "TRANSFERRED"} and transfer is None:
        reasons.append("TRANSFER_PROOF_MISSING")
    if transfer is not None:
        released = _time(transfer["released_at"], "transfer.released_at")
        accepted = _time(transfer["accepted_at"], "transfer.accepted_at")
        if released > snapshot_at or accepted > snapshot_at:
            reasons.append("TRANSFER_AFTER_SNAPSHOT")
        if relationship["owner"] != transfer["to_owner"]:
            reasons.append("TRANSFER_OWNER_NOT_LIVE_OWNER")
        if relationship["generation"] != transfer["to_generation"]:
            reasons.append("TRANSFER_GENERATION_NOT_LIVE")
        if rel_state == "TRANSFER_PENDING":
            reasons.append("TRANSFER_STILL_PENDING")
    return sorted(set(reasons))


def evaluate(
    raw: dict[str, Any],
    *,
    provider_hmac_key: bytes,
    now: datetime | None = None,
    source_sha256: str | None = None,
    max_snapshot_age_seconds: int = DEFAULT_MAX_SNAPSHOT_AGE_SECONDS,
    max_future_skew_seconds: int = DEFAULT_MAX_FUTURE_SKEW_SECONDS,
) -> dict[str, Any]:
    normalized = _normalize(_dict(raw, "census input"))
    key = provider_hmac_key
    if type(key) is not bytes or len(key) < 32:
        raise CensusError("provider HMAC key must contain at least 32 bytes")
    if type(max_snapshot_age_seconds) is not int or not 0 <= max_snapshot_age_seconds <= 604800:
        raise CensusError("max_snapshot_age_seconds must be an integer between 0 and 604800")
    if type(max_future_skew_seconds) is not int or not 0 <= max_future_skew_seconds <= 86400:
        raise CensusError("max_future_skew_seconds must be an integer between 0 and 86400")
    evaluated_at = now or datetime.now(timezone.utc)
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
        raise CensusError("now must include a timezone")
    evaluated_at = evaluated_at.astimezone(timezone.utc)

    reasons = _semantic_reasons(
        normalized,
        key=key,
        now=evaluated_at,
        max_snapshot_age_seconds=max_snapshot_age_seconds,
        max_future_skew_seconds=max_future_skew_seconds,
    )
    relationship = normalized["census"]["relationship"]
    if reasons:
        decision = "HOLD"
        custody = "unproven"
    elif relationship["state"] == "CLEAR":
        decision = "CUSTODY_CLEAR"
        custody = "no_live_owner_observed"
    else:
        decision = "CURRENT_OWNER"
        custody = "current_worker_owns_live_generation"

    transfer = normalized["census"]["transfer"]
    transfer_receipt_sha = digest_object(transfer) if transfer is not None else None
    payload = {
        "schema_version": RECEIPT_SCHEMA,
        "target_scope": normalized["target_scope"],
        "target_route_set_sha256": route_set_sha256(
            normalized["target_scope"], normalized["route_sha256s"]
        ),
        "route_sha256s": normalized["route_sha256s"],
        "provider": normalized["census"]["provider"],
        "workspace_sha256": normalized["census"]["workspace_sha256"],
        "snapshot_id": normalized["census"]["snapshot_id"],
        "snapshot_at": normalized["census"]["snapshot_at"],
        "coverage_started_at": normalized["census"]["coverage_started_at"],
        "evaluated_at": _fmt(evaluated_at),
        "current_worker": normalized["current_worker"],
        "claimed_generation": normalized["claimed_generation"],
        "relationship": relationship,
        "decision": decision,
        "custody": custody,
        "reasons": reasons,
        "provider_census_object_sha256": digest_object(normalized["census"]),
        "authority_material_sha256": digest_object(signing_material(normalized)),
        "source_exact_bytes_sha256": source_sha256,
        "transfer_receipt_sha256": transfer_receipt_sha,
        "requires_outbound_send_guard": True,
        "requires_atomic_send_lease": True,
        "external_send_authorized": False,
        "side_effects_authorized": False,
    }
    return {"payload": payload, "receipt_sha256": digest_object(payload)}


def evaluate_bytes(
    raw: bytes,
    *,
    provider_hmac_key: bytes,
    now: datetime | None = None,
    max_snapshot_age_seconds: int = DEFAULT_MAX_SNAPSHOT_AGE_SECONDS,
    max_future_skew_seconds: int = DEFAULT_MAX_FUTURE_SKEW_SECONDS,
) -> dict[str, Any]:
    parsed = parse_json_bytes(raw)
    return evaluate(
        parsed,
        provider_hmac_key=provider_hmac_key,
        now=now,
        source_sha256=hashlib.sha256(raw).hexdigest(),
        max_snapshot_age_seconds=max_snapshot_age_seconds,
        max_future_skew_seconds=max_future_skew_seconds,
    )


def _read_exact_once(path: Path) -> bytes:
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
    except OSError as exc:
        raise CensusError(f"cannot read census {path}: {exc}") from exc
    if len(raw) > MAX_BYTES:
        raise CensusError(f"census exceeds {MAX_BYTES} bytes")
    return raw


def _aliases(a: Path, b: Path) -> bool:
    try:
        if a.resolve(strict=False) == b.resolve(strict=False):
            return True
    except OSError as exc:
        raise CensusError(f"cannot resolve path identity: {exc}") from exc
    try:
        return os.path.samefile(a, b)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise CensusError(f"cannot compare path identity: {exc}") from exc


def _atomic_publish_new(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(path):
        raise CensusError(f"output already exists: {path}")
    try:
        fd, staged_name = tempfile.mkstemp(prefix=f".{path.name}.stage-", dir=str(path.parent))
    except OSError as exc:
        raise CensusError(f"cannot stage output {path}: {exc}") from exc
    staged = Path(staged_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(staged, path)
        except FileExistsError as exc:
            raise CensusError(f"output already exists: {path}") from exc
        if os.name != "nt":
            dfd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
    except CensusError:
        raise
    except OSError as exc:
        raise CensusError(f"cannot publish output {path}: {exc}") from exc
    finally:
        try:
            staged.unlink(missing_ok=True)
        except OSError:
            pass


def _key_from_env() -> bytes:
    value = os.environ.get("OUTBOUND_RELATIONSHIP_CENSUS_HMAC_KEY_HEX")
    if value is None:
        raise CensusError("OUTBOUND_RELATIONSHIP_CENSUS_HMAC_KEY_HEX is required")
    try:
        key = bytes.fromhex(value)
    except ValueError as exc:
        raise CensusError("OUTBOUND_RELATIONSHIP_CENSUS_HMAC_KEY_HEX must be hex") from exc
    if len(key) < 32:
        raise CensusError("OUTBOUND_RELATIONSHIP_CENSUS_HMAC_KEY_HEX must decode to at least 32 bytes")
    return key


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed provider relationship census / custody projection"
    )
    parser.add_argument("--census", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--max-snapshot-age-seconds",
        type=int,
        default=DEFAULT_MAX_SNAPSHOT_AGE_SECONDS,
    )
    parser.add_argument(
        "--max-future-skew-seconds",
        type=int,
        default=DEFAULT_MAX_FUTURE_SKEW_SECONDS,
    )
    args = parser.parse_args(argv)
    try:
        if _aliases(args.census, args.out):
            raise CensusError("output must not alias census input")
        raw = _read_exact_once(args.census)
        receipt = evaluate_bytes(
            raw,
            provider_hmac_key=_key_from_env(),
            max_snapshot_age_seconds=args.max_snapshot_age_seconds,
            max_future_skew_seconds=args.max_future_skew_seconds,
        )
        encoded = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
        _atomic_publish_new(args.out, encoded)
        return 0 if receipt["payload"]["decision"] != "HOLD" else 4
    except CensusError as exc:
        print(f"outbound-relationship-census: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
