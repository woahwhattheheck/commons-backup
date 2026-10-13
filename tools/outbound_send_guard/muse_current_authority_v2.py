"""Fail-closed current-authority seal for Muse election v2 receipts.

This is a composition donor for canonical issue #14503. It carries the already
landed #14505 authority law into v2 without inventing a third election protocol:
caller-supplied Slack snapshots are analysis evidence, not provider-authenticated
current authority, and caller-supplied clocks cannot mint terminal election
outcomes.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

RECEIPT_SCHEMA = "outbound-muse-publication-election-receipt/v2"
AUTHORITY_MODE = "UNAUTHENTICATED_SNAPSHOT_ANALYSIS"
UNAUTHENTICATED_SNAPSHOT_REASON = "SNAPSHOT_AUTHORITY_UNVERIFIED"
CURRENT_POSITIVE_DISABLED_REASON = "CURRENT_SELECTED_REQUIRES_PROVIDER_AUTHENTICATED_SNAPSHOT"
CURRENT_NEGATIVE_DISABLED_REASON = "CURRENT_NOT_SELECTED_REQUIRES_PROVIDER_AUTHENTICATED_SNAPSHOT"
FUTURE_SKEW_SECONDS = 30

_REQUIRED_BINDING_FIELDS = (
    "request_sha256", "request_id", "publication_key", "candidate_sha256",
    "claimant", "operation_id", "lease_binding_sha256",
)
_SELECTION_FIELDS = ("selection_message_ts", "selected_at", "selection_binding_sha256")
_WINNER_FIELDS = ("winner_request_id", "winner_candidate_sha256", "winner_message_ts")
_SOURCE_PAYLOAD_FIELDS = frozenset(
    {
        "schema_version",
        "request_sha256",
        "request_id",
        "publication_key",
        "candidate_sha256",
        "claimant",
        "operation_id",
        "lease_binding_sha256",
        "snapshot_sha256",
        "decision",
        "reasons",
        "compiled_at",
        "request_message_ts",
        "selection_message_ts",
        "selected_at",
        "selection_binding_sha256",
        "winner_request_id",
        "winner_candidate_sha256",
        "winner_message_ts",
        "muse_user_id",
        "muse_dm_conversation_id",
        "requires_current_worker_lease_possession",
        "requires_fresh_provider_preflight",
        "external_send_authorized",
        "side_effects_authorized",
    }
)
_AUTHORITY_ENVELOPE_FIELDS = frozenset(
    {
        "authority_mode",
        "snapshot_authenticated",
        "snapshot_authentication_sha256",
        "valid_until",
        "request_context_sha256",
    }
)
_SEALED_PAYLOAD_FIELDS = _SOURCE_PAYLOAD_FIELDS | _AUTHORITY_ENVELOPE_FIELDS


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _fmt(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(value: Any) -> datetime | None:
    if type(value) is not str:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return parsed if _fmt(parsed) == value else None


def _canon(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canon(value)).hexdigest()


def _require_exact_fields(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"{label}: exact fields required; missing={missing}; extra={extra}")


def _validate_source_receipt(receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    if type(receipt) is not dict or set(receipt) != {"payload", "receipt_sha256"}:
        raise ValueError("receipt must contain exactly payload and receipt_sha256")
    payload = receipt["payload"]
    if type(payload) is not dict:
        raise ValueError("receipt.payload must be an object")
    _require_exact_fields(payload, _SOURCE_PAYLOAD_FIELDS, "receipt.payload")
    if payload.get("schema_version") != RECEIPT_SCHEMA:
        raise ValueError("receipt.payload.schema_version: unsupported schema")
    claimed = receipt["receipt_sha256"]
    if type(claimed) is not str or claimed != _digest(payload):
        raise ValueError("receipt: source digest mismatch")
    return payload


def _binding_payload(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    if any(name not in payload for name in _REQUIRED_BINDING_FIELDS):
        return None
    return {name: payload[name] for name in _REQUIRED_BINDING_FIELDS}


def seal_untrusted_snapshot_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Return a verifier-clocked HOLD receipt for raw snapshot analysis.

    The incoming deterministic receipt must be exact-schema and digest-valid.
    The function deliberately does not accept `now`. Tests may patch `_utc_now`,
    but production callers cannot backdate current authority through the API.
    Until a reviewed provider-authenticated adapter exists, caller-supplied Muse
    bytes cannot prove either terminal SELECTED or terminal NOT_SELECTED.
    """
    source_payload = _validate_source_receipt(receipt)
    payload = copy.deepcopy(source_payload)
    binding = _binding_payload(payload)
    if binding is None:
        raise ValueError("receipt.payload is missing request binding fields")

    payload["compiled_at"] = _fmt(_utc_now())
    payload["authority_mode"] = AUTHORITY_MODE
    payload["snapshot_authenticated"] = False
    payload["snapshot_authentication_sha256"] = None
    payload["valid_until"] = None
    payload["request_context_sha256"] = _digest(binding)
    payload["external_send_authorized"] = False
    payload["side_effects_authorized"] = False

    decision = payload.get("decision")
    if decision in {"SELECTED", "NOT_SELECTED"}:
        payload["decision"] = "HOLD"
        reasons = payload.get("reasons")
        reasons = [] if type(reasons) is not list else [x for x in reasons if type(x) is str and x]
        reasons.append(UNAUTHENTICATED_SNAPSHOT_REASON)
        if decision == "SELECTED":
            reasons.append(CURRENT_POSITIVE_DISABLED_REASON)
        else:
            reasons.append(CURRENT_NEGATIVE_DISABLED_REASON)
        payload["reasons"] = sorted(set(reasons))
        for name in _SELECTION_FIELDS + _WINNER_FIELDS:
            payload[name] = None

    sealed = {"payload": payload, "receipt_sha256": _digest(payload)}
    if not verify_untrusted_snapshot_receipt(sealed):
        raise ValueError("sealed receipt violates unauthenticated authority contract")
    return sealed


def verify_untrusted_snapshot_receipt(receipt: Mapping[str, Any]) -> bool:
    """Verify the fail-closed unauthenticated current-authority envelope.

    A receipt can prove only HOLD analysis while `authority_mode` is
    unauthenticated snapshot analysis. Terminal SELECTED and NOT_SELECTED both
    require a separately reviewed provider-authenticated source boundary.
    Unknown source or envelope fields are rejected rather than carried through.
    """
    try:
        if type(receipt) is not dict or set(receipt) != {"payload", "receipt_sha256"}:
            return False
        payload = receipt["payload"]
        if type(payload) is not dict:
            return False
        _require_exact_fields(payload, _SEALED_PAYLOAD_FIELDS, "receipt.payload")
        if payload.get("schema_version") != RECEIPT_SCHEMA:
            return False
        claimed = receipt["receipt_sha256"]
        if type(claimed) is not str or _digest(payload) != claimed:
            return False
        if payload.get("authority_mode") != AUTHORITY_MODE:
            return False
        if payload.get("snapshot_authenticated") is not False or payload.get("snapshot_authentication_sha256") is not None:
            return False
        if payload.get("external_send_authorized") is not False or payload.get("side_effects_authorized") is not False:
            return False
        if payload.get("requires_current_worker_lease_possession") is not True or payload.get("requires_fresh_provider_preflight") is not True:
            return False
        compiled = _parse_utc(payload.get("compiled_at"))
        if compiled is None or compiled > _utc_now() + timedelta(seconds=FUTURE_SKEW_SECONDS):
            return False
        binding = _binding_payload(payload)
        if binding is None or payload.get("request_context_sha256") != _digest(binding):
            return False
        if payload.get("decision") != "HOLD":
            return False
        if payload.get("valid_until") is not None:
            return False
        if any(payload.get(name) is not None for name in _SELECTION_FIELDS + _WINNER_FIELDS):
            return False
        reasons = payload.get("reasons")
        if type(reasons) is not list or reasons != sorted(set(reasons)) or any(type(x) is not str or not x for x in reasons):
            return False
        if not reasons:
            return False
        return True
    except (TypeError, ValueError, OverflowError):
        return False
