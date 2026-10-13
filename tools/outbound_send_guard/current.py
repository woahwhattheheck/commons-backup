"""Fail-closed embedded CURRENT surface for the outbound send guard.

Positive CURRENT authority deliberately does not exist in an imported caller-
controlled Python interpreter. Use the direct isolated CLI boundary documented
in ``cli.py``. Historical/integrity reconstruction remains available here.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from . import _guard_core as _core_engine

CURRENT_RECEIPT_SCHEMA = "outbound-send-guard-current-receipt/v1"
HISTORICAL_RECEIPT_SCHEMA = "outbound-send-guard-historical-receipt/v1"
CURRENT_VERIFICATION_SCHEMA = "outbound-send-guard-current-verification/v1"
POLICY_GENERATION = "outbound-send-guard-current-policy/1"
MODE_CURRENT = "CURRENT"
MODE_HISTORICAL = "HISTORICAL_INTEGRITY_ONLY"
MODE_EMBEDDED = "EMBEDDED_CURRENT_UNAVAILABLE"
MAX_EVIDENCE_AGE_SECONDS = 900
MAX_REQUEST_AGE_SECONDS = 900
MAX_FUTURE_SKEW_SECONDS = 300
POSITIVE_RECEIPT_TTL_SECONDS = 60
MAX_INPUT_BYTES = 2 * 1024 * 1024
DECISIONS = {"ALLOW_NEW", "REPLY_ONLY", "HOLD", "DO_NOT_RESEND"}
POSITIVE = {"ALLOW_NEW", "REPLY_ONLY"}
EMBEDDED_REASON = (
    "embedded CURRENT authority is unavailable; use direct isolated startup: "
    "python -I -S tools/outbound_send_guard/cli.py ..."
)


class CurrentGuardError(_core_engine.GuardError):
    pass


# Safe helper compatibility only. No evaluator or CLI is exposed here.
guard = SimpleNamespace(
    GuardError=_core_engine.GuardError,
    canonical_bytes=_core_engine.canonical_bytes,
    digest_bytes=_core_engine.digest_bytes,
    digest_object=_core_engine.digest_object,
    parse_json_bytes=_core_engine.parse_json_bytes,
    parse_time=_core_engine.parse_time,
    format_time=_core_engine.format_time,
    normalize_email=_core_engine.normalize_email,
)


def _snapshot(value: Any, label: str) -> tuple[dict[str, Any], bytes]:
    if type(value) is not dict:
        raise CurrentGuardError(f"{label} must be an object")
    try:
        raw = _core_engine.canonical_bytes(value)
    except (TypeError, ValueError) as exc:
        raise CurrentGuardError(f"{label} is not canonical JSON") from exc
    return _core_engine.parse_json_bytes(raw, f"{label} canonical snapshot"), raw


def _embedded_receipt(
    intent: dict[str, Any],
    evidence: dict[str, Any],
    *,
    source_mode: str,
    ib: bytes,
    eb: bytes,
) -> dict[str, Any]:
    core = _core_engine.evaluate(intent, evidence)
    core_payload = deepcopy(core["payload"])
    historical = core_payload["decision"]
    decision = "DO_NOT_RESEND" if historical == "DO_NOT_RESEND" else "HOLD"
    payload = {
        "schema_version": CURRENT_RECEIPT_SCHEMA,
        "policy_generation": POLICY_GENERATION,
        "mode": MODE_EMBEDDED,
        "source": {
            "custody_mode": source_mode,
            "intent_object_sha256": _core_engine.digest_object(intent),
            "evidence_object_sha256": _core_engine.digest_object(evidence),
            "byte_custody": (
                {
                    "intent_sha256": _core_engine.digest_bytes(ib),
                    "evidence_sha256": _core_engine.digest_bytes(eb),
                }
                if source_mode == "exact_consumed_bytes"
                else None
            ),
        },
        "core_receipt_sha256": core["receipt_sha256"],
        "core": core_payload,
        "historical_decision": historical,
        "decision": decision,
        "reasons": [EMBEDDED_REASON],
        "temporal_reasons": [EMBEDDED_REASON],
        "verified_at": None,
        "valid_until": None,
        "current_policy": None,
        "current_preflight_clear": False,
        "net_new_send_preflight_clear": False,
        "reply_preflight_clear": False,
        "side_effects_authorized": False,
    }
    return {"payload": payload, "receipt_sha256": _core_engine.digest_object(payload)}


def compile_current(
    intent_raw: dict[str, Any], evidence_raw: dict[str, Any]
) -> dict[str, Any]:
    """Return a non-authorizing embedded projection; never positive CURRENT."""
    intent, ib = _snapshot(intent_raw, "intent")
    evidence, eb = _snapshot(evidence_raw, "evidence")
    return _embedded_receipt(
        intent, evidence, source_mode="canonical_objects", ib=ib, eb=eb
    )


def compile_current_bytes(intent_bytes: bytes, evidence_bytes: bytes) -> dict[str, Any]:
    """Return a non-authorizing exact-byte embedded projection."""
    if type(intent_bytes) is not bytes or type(evidence_bytes) is not bytes:
        raise CurrentGuardError("intent/evidence bytes must be bytes")
    if len(intent_bytes) > MAX_INPUT_BYTES or len(evidence_bytes) > MAX_INPUT_BYTES:
        raise CurrentGuardError(f"input exceeds {MAX_INPUT_BYTES} bytes")
    intent = _core_engine.parse_json_bytes(intent_bytes, "intent")
    evidence = _core_engine.parse_json_bytes(evidence_bytes, "evidence")
    return _embedded_receipt(
        intent,
        evidence,
        source_mode="exact_consumed_bytes",
        ib=intent_bytes,
        eb=evidence_bytes,
    )


def compile_historical_at(
    intent_raw: dict[str, Any],
    evidence_raw: dict[str, Any],
    *,
    historical_at: datetime,
) -> dict[str, Any]:
    """Explicit integrity replay. Outward authority is permanently HOLD."""
    if type(historical_at) is not datetime or historical_at.tzinfo is None:
        raise CurrentGuardError("historical_at must be timezone-aware")
    intent, _ = _snapshot(intent_raw, "intent")
    evidence, _ = _snapshot(evidence_raw, "evidence")
    core = _core_engine.evaluate(intent, evidence)
    historical = core["payload"]["decision"]
    payload = {
        "schema_version": HISTORICAL_RECEIPT_SCHEMA,
        "mode": MODE_HISTORICAL,
        "historical_at": historical_at.isoformat(),
        "core_receipt_sha256": core["receipt_sha256"],
        "core": deepcopy(core["payload"]),
        "historical_decision": historical,
        "decision": "HOLD",
        "reasons": ["historical replay cannot authorize current outbound action"],
        "current_preflight_clear": False,
        "net_new_send_preflight_clear": False,
        "reply_preflight_clear": False,
        "side_effects_authorized": False,
    }
    return {"payload": payload, "receipt_sha256": _core_engine.digest_object(payload)}


def verify_current(
    intent_raw: dict[str, Any],
    evidence_raw: dict[str, Any],
    receipt_raw: dict[str, Any],
) -> dict[str, Any]:
    del intent_raw, evidence_raw, receipt_raw
    payload = {
        "schema_version": CURRENT_VERIFICATION_SCHEMA,
        "mode": MODE_EMBEDDED,
        "historical_valid": False,
        "expired": True,
        "current_semantics_match": False,
        "current_preflight_valid": False,
        "current_decision": "HOLD",
        "reasons": [EMBEDDED_REASON],
        "side_effects_authorized": False,
    }
    return {"payload": payload, "receipt_sha256": _core_engine.digest_object(payload)}


def verify_current_bytes(
    intent_bytes: bytes, evidence_bytes: bytes, receipt_bytes: bytes
) -> dict[str, Any]:
    del intent_bytes, evidence_bytes, receipt_bytes
    return verify_current({}, {}, {})


def main(argv: list[str] | None = None) -> int:
    del argv
    return 4
