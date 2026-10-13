from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
from pathlib import Path
from typing import Any

STATUSES = {
    "CURRENT_FOR_OWNER_USE",
    "EXPIRED_REQUOTE_REQUIRED",
    "SUPERSEDED",
    "HOLD_NO_VALIDITY_BASIS",
    "HOLD_SOURCE_DRIFT",
}
EVENT_KINDS_V1 = {"AMENDMENT", "REDLINE", "CHANGE_ORDER"}
EVENT_KINDS_V2 = EVENT_KINDS_V1 | {"REPRICE", "WITHDRAWAL"}
_ACTIVE_RAIL_STATES = {"ACTIVE", "PRESENT", "PRESENT_NON_AUTHORITATIVE"}

_ALLOWED_OFFER_KEYS_V1 = {
    "schema_version", "offer_id", "source_generation", "pricing_revision", "currency",
    "scope", "economics", "issued_on", "validity", "buyer_deadline", "payment_rail",
}
_ALLOWED_OFFER_KEYS_V2 = _ALLOWED_OFFER_KEYS_V1 | {"source_digest_sha256"}
_ALLOWED_CURRENT_KEYS_V1 = {
    "schema_version", "offer_id", "source_generation", "pricing_revision", "currency",
    "scope", "economics", "superseding_events",
}
_ALLOWED_CURRENT_KEYS_V2 = _ALLOWED_CURRENT_KEYS_V1 | {
    "source_digest_sha256", "source_status", "source_observed_at", "payment_rail",
}
_ALLOWED_VALIDITY_KEYS = {"mode", "valid_until", "valid_for_seconds"}
_ALLOWED_EVENT_KEYS_V1 = {"kind", "event_id", "observed_at", "applies_to_offer_id", "source_generation"}
_ALLOWED_EVENT_KEYS_V2 = _ALLOWED_EVENT_KEYS_V1 | {"source_digest_sha256"}

_MAX_INPUT_CHARS = 2_000_000
_MAX_INT_TOKEN_DIGITS = 256
_MAX_DEPTH = 32
_MAX_COLLECTION = 512
_MAX_TEXT = 100_000
_MAX_FIELD_TEXT = 2_048

_AUTHORITY = {
    "owner_review_only": True,
    "buyer_acceptance": False,
    "contract_signed": False,
    "checkout_or_payment_rail_is_acceptance": False,
    "payment_authorized": False,
    "revenue_recognized": False,
    "outbound_authorized": False,
}


class GateError(ValueError):
    pass


def _valid_unicode_scalar_text(value: str) -> bool:
    return not any(0xD800 <= ord(ch) <= 0xDFFF for ch in value)


def _strict_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise GateError("duplicate JSON key")
        out[key] = value
    return out


def _reject_constant(_token: str) -> None:
    raise GateError("non-finite JSON numbers are not allowed")


def _reject_float(_token: str) -> None:
    raise GateError("floating point JSON numbers are not allowed")


def _parse_int_token(token: str) -> int:
    unsigned = token[1:] if token.startswith("-") else token
    if len(unsigned) > _MAX_INT_TOKEN_DIGITS:
        raise GateError("JSON integer token is too large")
    try:
        return int(token)
    except (ValueError, OverflowError):
        raise GateError("invalid JSON integer token") from None


def strict_json_loads(text: str) -> Any:
    if type(text) is not str:
        raise GateError("JSON input must be text")
    if len(text) > _MAX_INPUT_CHARS:
        raise GateError("JSON input is too large")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_object_pairs,
            parse_constant=_reject_constant,
            parse_float=_reject_float,
            parse_int=_parse_int_token,
        )
        _validate_json_tree(value, "json")
        return value
    except GateError:
        raise
    except (json.JSONDecodeError, UnicodeError, ValueError, OverflowError, RecursionError) as exc:
        raise GateError(f"invalid JSON: {type(exc).__name__}") from None


def _canonical(value: Any) -> bytes:
    _validate_json_tree(value, "canonical")
    try:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError, UnicodeError, OverflowError, RecursionError) as exc:
        raise GateError(f"not canonical JSON data: {type(exc).__name__}") from None
    return (text + "\n").encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _reject_unknown(obj: dict[str, Any], allowed: set[str], label: str) -> None:
    if set(obj) - allowed:
        raise GateError(f"{label}: unknown keys")


def _json_text(value: Any, label: str, *, nonempty: bool = False, max_len: int = _MAX_TEXT) -> str:
    if type(value) is not str:
        raise GateError(f"{label}: expected text")
    if len(value) > max_len:
        raise GateError(f"{label}: text too long")
    if not _valid_unicode_scalar_text(value):
        raise GateError(f"{label}: invalid Unicode scalar value")
    if any(ord(ch) < 32 for ch in value):
        raise GateError(f"{label}: control characters are not allowed")
    if nonempty and not value.strip():
        raise GateError(f"{label}: expected non-empty text")
    return value


def _text(value: Any, label: str) -> str:
    return _json_text(value, label, nonempty=True, max_len=_MAX_FIELD_TEXT)


def _integer(value: Any, label: str, *, minimum: int | None = None) -> int:
    if type(value) is not int:
        raise GateError(f"{label}: expected integer")
    if minimum is not None and value < minimum:
        raise GateError(f"{label}: expected >= {minimum}")
    return value


def _hash(value: Any, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise GateError(f"{label}: expected lowercase sha256")
    return text


def _parse_time(value: Any, label: str) -> _dt.datetime:
    text = _text(value, label)
    try:
        parsed = _dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        raise GateError(f"{label}: invalid ISO-8601 timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GateError(f"{label}: timezone is required")
    return parsed.astimezone(_dt.timezone.utc)


def _utc_now(_now=_dt.datetime.now, _utc=_dt.timezone.utc) -> _dt.datetime:
    # Capture the trusted stdlib callable at import time so ordinary rebinding of
    # gate._dt.datetime cannot select a historical clock for public evaluation.
    return _now(_utc).replace(microsecond=0)


def _validate_json_tree(value: Any, label: str, depth: int = 0) -> None:
    if depth > _MAX_DEPTH:
        raise GateError(f"{label}: maximum JSON depth exceeded")
    if value is None or type(value) is bool or type(value) is int:
        return
    if type(value) is str:
        _json_text(value, label)
        return
    if isinstance(value, float):
        raise GateError(f"{label}: floats are not allowed")
    if isinstance(value, list):
        if len(value) > _MAX_COLLECTION:
            raise GateError(f"{label}: collection too large")
        for idx, item in enumerate(value):
            _validate_json_tree(item, f"{label}[{idx}]", depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > _MAX_COLLECTION:
            raise GateError(f"{label}: collection too large")
        for idx, (key, item) in enumerate(value.items()):
            _json_text(key, f"{label}.key[{idx}]", nonempty=True, max_len=_MAX_FIELD_TEXT)
            _validate_json_tree(item, f"{label}.value[{idx}]", depth + 1)
        return
    raise GateError(f"{label}: unsupported value type")


def _currency(value: Any) -> str:
    text = _text(value, "currency")
    if len(text) != 3 or not text.isascii() or not text.isalpha() or text.upper() != text:
        raise GateError("currency: expected uppercase ISO-like three-letter code")
    return text


def _validate_economics(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        raise GateError(f"{label}: expected non-empty object")
    _validate_json_tree(value, label)
    for key, item in value.items():
        if key.endswith("_minor_units"):
            _integer(item, f"{label}.money", minimum=0)
    return value


def _validate_scope(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        raise GateError(f"{label}: expected non-empty object")
    _validate_json_tree(value, label)
    return value


def _validate_payment_rail(value: Any, label: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or not value:
        raise GateError(f"{label}: expected object or null")
    _validate_json_tree(value, label)
    state = value.get("state")
    if state is not None:
        _text(state, f"{label}.state")
    return value


def _rail_identity(value: dict[str, Any] | None) -> Any:
    if value is None:
        return None
    return {key: item for key, item in value.items() if key != "state"}


def _rail_state(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    state = value.get("state")
    return state if type(state) is str else None


def _validate_offer(offer: Any) -> dict[str, Any]:
    if not isinstance(offer, dict):
        raise GateError("issued_offer: expected object")
    version = offer.get("schema_version")
    if version == 1:
        _reject_unknown(offer, _ALLOWED_OFFER_KEYS_V1, "issued_offer")
    elif version == 2:
        _reject_unknown(offer, _ALLOWED_OFFER_KEYS_V2, "issued_offer")
        _hash(offer.get("source_digest_sha256"), "issued_offer.source_digest_sha256")
    else:
        raise GateError("issued_offer.schema_version: expected 1 or 2")
    _text(offer.get("offer_id"), "issued_offer.offer_id")
    _text(offer.get("source_generation"), "issued_offer.source_generation")
    _text(offer.get("pricing_revision"), "issued_offer.pricing_revision")
    _currency(offer.get("currency"))
    _validate_scope(offer.get("scope"), "issued_offer.scope")
    _validate_economics(offer.get("economics"), "issued_offer.economics")
    issued_at = _parse_time(offer.get("issued_on"), "issued_offer.issued_on")

    validity = offer.get("validity")
    if not isinstance(validity, dict):
        raise GateError("issued_offer.validity: expected object")
    _reject_unknown(validity, _ALLOWED_VALIDITY_KEYS, "issued_offer.validity")
    mode = _text(validity.get("mode"), "issued_offer.validity.mode")
    if mode not in {"VALID_UNTIL", "VALID_FOR_SECONDS", "NO_EXPIRY_STATED"}:
        raise GateError("issued_offer.validity.mode: unsupported mode")
    if mode == "VALID_UNTIL":
        if set(validity) != {"mode", "valid_until"}:
            raise GateError("VALID_UNTIL requires exactly mode + valid_until")
        _parse_time(validity["valid_until"], "issued_offer.validity.valid_until")
    elif mode == "VALID_FOR_SECONDS":
        if set(validity) != {"mode", "valid_for_seconds"}:
            raise GateError("VALID_FOR_SECONDS requires exactly mode + valid_for_seconds")
        _integer(validity.get("valid_for_seconds"), "issued_offer.validity.valid_for_seconds", minimum=1)
    elif set(validity) != {"mode"}:
        raise GateError("NO_EXPIRY_STATED accepts only mode")

    if offer.get("buyer_deadline") is not None:
        _parse_time(offer["buyer_deadline"], "issued_offer.buyer_deadline")
    _validate_payment_rail(offer.get("payment_rail"), "issued_offer.payment_rail")
    if issued_at.microsecond:
        raise GateError("issued_offer.issued_on: sub-second precision is not supported")
    return offer


def _validate_event(event: Any, idx: int, version: int) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise GateError(f"current_offer.superseding_events[{idx}]: expected object")
    if version == 1:
        _reject_unknown(event, _ALLOWED_EVENT_KEYS_V1, f"event[{idx}]")
        kinds = EVENT_KINDS_V1
    else:
        _reject_unknown(event, _ALLOWED_EVENT_KEYS_V2, f"event[{idx}]")
        _hash(event.get("source_digest_sha256"), f"event[{idx}].source_digest_sha256")
        kinds = EVENT_KINDS_V2
    kind = _text(event.get("kind"), f"event[{idx}].kind")
    if kind not in kinds:
        raise GateError(f"event[{idx}].kind: unsupported kind")
    _text(event.get("event_id"), f"event[{idx}].event_id")
    _parse_time(event.get("observed_at"), f"event[{idx}].observed_at")
    _text(event.get("applies_to_offer_id"), f"event[{idx}].applies_to_offer_id")
    _text(event.get("source_generation"), f"event[{idx}].source_generation")
    return event


def _validate_current(current: Any) -> dict[str, Any]:
    if not isinstance(current, dict):
        raise GateError("current_offer: expected object")
    version = current.get("schema_version")
    if version == 1:
        _reject_unknown(current, _ALLOWED_CURRENT_KEYS_V1, "current_offer")
    elif version == 2:
        _reject_unknown(current, _ALLOWED_CURRENT_KEYS_V2, "current_offer")
        _hash(current.get("source_digest_sha256"), "current_offer.source_digest_sha256")
        status = _text(current.get("source_status"), "current_offer.source_status")
        if status not in {"CURRENT", "STALE", "WITHDRAWN"}:
            raise GateError("current_offer.source_status: unsupported status")
        observed = _parse_time(current.get("source_observed_at"), "current_offer.source_observed_at")
        if observed.microsecond:
            raise GateError("current_offer.source_observed_at: sub-second precision is not supported")
        _validate_payment_rail(current.get("payment_rail"), "current_offer.payment_rail")
    else:
        raise GateError("current_offer.schema_version: expected 1 or 2")

    _text(current.get("offer_id"), "current_offer.offer_id")
    _text(current.get("source_generation"), "current_offer.source_generation")
    _text(current.get("pricing_revision"), "current_offer.pricing_revision")
    _currency(current.get("currency"))
    _validate_scope(current.get("scope"), "current_offer.scope")
    _validate_economics(current.get("economics"), "current_offer.economics")
    events = current.get("superseding_events")
    if not isinstance(events, list) or len(events) > _MAX_COLLECTION:
        raise GateError("current_offer.superseding_events: expected bounded list")
    seen: set[str] = set()
    for idx, event in enumerate(events):
        _validate_event(event, idx, version)
        event_id = event["event_id"]
        if event_id in seen:
            raise GateError("duplicate superseding event_id")
        seen.add(event_id)
        if version == 2:
            if event["source_generation"] != current["source_generation"]:
                raise GateError("superseding event source generation is not current")
            if event["source_digest_sha256"] != current["source_digest_sha256"]:
                raise GateError("superseding event source digest is not current")
            if _parse_time(event["observed_at"], "event.observed_at") > _parse_time(current["source_observed_at"], "current_offer.source_observed_at"):
                raise GateError("superseding event postdates current source observation")
    return current


def _validity_expiry(offer: dict[str, Any]) -> _dt.datetime | None:
    issued = _parse_time(offer["issued_on"], "issued_offer.issued_on")
    validity = offer["validity"]
    if validity["mode"] == "NO_EXPIRY_STATED":
        return None
    if validity["mode"] == "VALID_UNTIL":
        return _parse_time(validity["valid_until"], "issued_offer.validity.valid_until")
    return issued + _dt.timedelta(seconds=_integer(validity["valid_for_seconds"], "valid_for_seconds", minimum=1))


def _effective_expiry(offer: dict[str, Any]) -> tuple[_dt.datetime | None, str]:
    expiry = _validity_expiry(offer)
    mode = offer["validity"]["mode"]
    if mode == "NO_EXPIRY_STATED":
        basis = "NO_EXPIRY_STATED"
    elif mode == "VALID_UNTIL":
        basis = "EXPLICIT_VALID_UNTIL"
    else:
        basis = "ISSUED_PLUS_VALID_FOR_SECONDS"
    if offer.get("buyer_deadline") is not None:
        deadline = _parse_time(offer["buyer_deadline"], "issued_offer.buyer_deadline")
        if expiry is None or deadline < expiry:
            expiry = deadline
            basis = f"{basis}+BUYER_DEADLINE_CAP"
    return expiry, basis


def _diff(issued: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    fields = ["source_generation", "pricing_revision", "currency", "scope", "economics"]
    result = []
    for field in fields:
        if issued[field] != current[field]:
            result.append({"field": field, "issued": issued[field], "current": current[field]})
    return result


def _active_superseders(issued: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    issued_at = _parse_time(issued["issued_on"], "issued_offer.issued_on")
    active = []
    for event in current["superseding_events"]:
        if event["applies_to_offer_id"] != issued["offer_id"]:
            continue
        observed = _parse_time(event["observed_at"], "event.observed_at")
        if observed <= issued_at:
            continue
        active.append(event)
    return sorted(active, key=lambda e: (e["observed_at"], e["event_id"]))


def _source_reasons(issued: dict[str, Any], current: dict[str, Any], now: _dt.datetime) -> list[str]:
    reasons: list[str] = []
    if issued["schema_version"] != 2 or current["schema_version"] != 2:
        reasons.append("LEGACY_SOURCE_EVIDENCE_MISSING")
        return reasons
    issued_at = _parse_time(issued["issued_on"], "issued_offer.issued_on")
    observed = _parse_time(current["source_observed_at"], "current_offer.source_observed_at")
    if issued["source_generation"] != current["source_generation"]:
        reasons.append("SOURCE_GENERATION_DRIFT")
    if issued["source_digest_sha256"] != current["source_digest_sha256"]:
        reasons.append("SOURCE_DIGEST_DRIFT")
    if current["source_status"] != "CURRENT":
        reasons.append(f"SOURCE_STATUS_{current['source_status']}")
    if observed < issued_at:
        reasons.append("SOURCE_OBSERVED_BEFORE_ISSUANCE")
    if observed > now:
        reasons.append("SOURCE_OBSERVED_IN_FUTURE")

    issued_rail = _validate_payment_rail(issued.get("payment_rail"), "issued_offer.payment_rail")
    current_rail = _validate_payment_rail(current.get("payment_rail"), "current_offer.payment_rail")
    if _rail_identity(issued_rail) != _rail_identity(current_rail):
        reasons.append("PAYMENT_RAIL_IDENTITY_DRIFT")
    if issued_rail is not None:
        state = _rail_state(current_rail)
        if current_rail is None or state not in _ACTIVE_RAIL_STATES:
            reasons.append("PAYMENT_RAIL_NOT_CURRENT")
    return sorted(set(reasons))


def _time_reasons(issued: dict[str, Any], now: _dt.datetime) -> list[str]:
    reasons: list[str] = []
    issued_at = _parse_time(issued["issued_on"], "issued_offer.issued_on")
    if now < issued_at:
        reasons.append("RUNTIME_BEFORE_ISSUANCE")
    validity_expiry = _validity_expiry(issued)
    if validity_expiry is None:
        reasons.append("NO_EXPIRY_STATED")
    elif now > validity_expiry:
        reasons.append("OFFER_VALIDITY_EXPIRED")
    if issued.get("buyer_deadline") is not None:
        deadline = _parse_time(issued["buyer_deadline"], "issued_offer.buyer_deadline")
        if now > deadline:
            reasons.append("BUYER_DEADLINE_PASSED")
    return reasons


def _evaluate_at(
    issued_offer: Any,
    current_offer: Any,
    now: _dt.datetime,
    *,
    _clock_basis: str = "TEST_EXPLICIT",
) -> dict[str, Any]:
    issued = _validate_offer(issued_offer)
    current = _validate_current(current_offer)
    if now.tzinfo is None or now.utcoffset() is None:
        raise GateError("runtime clock must be timezone-aware")
    now = now.astimezone(_dt.timezone.utc).replace(microsecond=0)
    if _clock_basis not in {"PROCESS_UTC", "TEST_EXPLICIT"}:
        raise GateError("unsupported clock basis")
    if issued["offer_id"] != current["offer_id"]:
        raise GateError("offer_id mismatch")

    changes = _diff(issued, current)
    superseders = _active_superseders(issued, current)
    expiry, validity_basis = _effective_expiry(issued)
    source_reasons = _source_reasons(issued, current, now)
    time_reasons = _time_reasons(issued, now)

    if superseders:
        status = "SUPERSEDED"
        reason = "later source-bound supersession evidence applies to this offer"
    elif any(item["field"] in {"pricing_revision", "currency", "scope", "economics"} for item in changes):
        status = "SUPERSEDED"
        reason = "current offer economics/scope/currency/revision differ from issued offer"
    elif source_reasons:
        status = "HOLD_SOURCE_DRIFT"
        reason = "controlling source/payment currentness evidence is missing or drifted"
    elif expiry is not None and expiry < _parse_time(issued["issued_on"], "issued_offer.issued_on"):
        status = "HOLD_NO_VALIDITY_BASIS"
        reason = "effective validity endpoint predates issuance"
    elif expiry is not None and now > expiry:
        status = "EXPIRED_REQUOTE_REQUIRED"
        reason = "effective validity endpoint has passed"
    elif issued["validity"]["mode"] == "NO_EXPIRY_STATED":
        status = "HOLD_NO_VALIDITY_BASIS"
        reason = "offer states no expiry; owner review is required before reuse"
    elif now < _parse_time(issued["issued_on"], "issued_offer.issued_on"):
        status = "HOLD_NO_VALIDITY_BASIS"
        reason = "runtime clock precedes offer issuance"
    else:
        status = "CURRENT_FOR_OWNER_USE"
        reason = "source/economics unchanged, source evidence current, and explicit validity remains current"

    delta = {
        "offer_id": issued["offer_id"],
        "status": "PROPOSED_NOT_ACCEPTED",
        "issued_source_generation": issued["source_generation"],
        "current_source_generation": current["source_generation"],
        "changes": changes,
        "superseding_events": superseders,
        "source_currentness_reasons": source_reasons,
        "time_reasons": time_reasons,
        "buyer_acceptance_inferred": False,
        "payment_authority_inferred": False,
    }
    source_binding: dict[str, Any] = {
        "issued_generation": issued["source_generation"],
        "current_generation": current["source_generation"],
    }
    if issued["schema_version"] == 2:
        source_binding["issued_digest_sha256"] = issued["source_digest_sha256"]
    if current["schema_version"] == 2:
        source_binding.update({
            "current_digest_sha256": current["source_digest_sha256"],
            "current_status": current["source_status"],
            "current_observed_at": current["source_observed_at"],
        })

    body = {
        "schema_version": 2,
        "status": status,
        "reason": reason,
        "offer_id": issued["offer_id"],
        "evaluated_at": now.isoformat().replace("+00:00", "Z"),
        "clock_basis": _clock_basis,
        "validity_basis": validity_basis,
        "effective_valid_until": None if expiry is None else expiry.isoformat().replace("+00:00", "Z"),
        "issued_offer_sha256": _sha(issued),
        "current_offer_sha256": _sha(current),
        "scope_sha256": _sha(issued["scope"]),
        "economics_sha256": _sha(issued["economics"]),
        "source_binding": source_binding,
        "requote_delta": delta,
        # Source-literal authority ceiling. _AUTHORITY remains a compatibility
        # descriptor for callers/tests, but is not a semantic trust root: ordinary
        # mutation or rebinding of either the facade alias or this core global
        # cannot widen packet authority.
        "authority": {
            "owner_review_only": True,
            "buyer_acceptance": False,
            "contract_signed": False,
            "checkout_or_payment_rail_is_acceptance": False,
            "payment_authorized": False,
            "revenue_recognized": False,
            "outbound_authorized": False,
        },
    }
    body["receipt_sha256"] = _sha(body)
    return body


def evaluate_offer(issued_offer: Any, current_offer: Any) -> dict[str, Any]:
    return _evaluate_at(issued_offer, current_offer, _utc_now(), _clock_basis="PROCESS_UTC")


def _semantic_projection(packet: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in packet.items() if key not in {"evaluated_at", "receipt_sha256"}}


def verify_packet(issued_offer: Any, current_offer: Any, packet: Any) -> bool:
    if not isinstance(packet, dict):
        return False
    try:
        if packet.get("schema_version") != 2 or packet.get("clock_basis") != "PROCESS_UTC":
            return False
        evaluated_at = _parse_time(packet.get("evaluated_at"), "packet.evaluated_at")
        expected = _evaluate_at(
            issued_offer,
            current_offer,
            evaluated_at,
            _clock_basis="PROCESS_UTC",
        )
        if _canonical(expected) != _canonical(packet):
            return False
        live = _evaluate_at(
            issued_offer,
            current_offer,
            _utc_now(),
            _clock_basis="PROCESS_UTC",
        )
        if _semantic_projection(live) != _semantic_projection(packet):
            return False
    except (GateError, ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        return False
    return True


def _load(path: str) -> Any:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise GateError(f"cannot read input: {type(exc).__name__}") from None
    return strict_json_loads(text)


def _write_new(path: str, value: Any) -> None:
    target = Path(path)
    try:
        with target.open("xb") as fh:
            fh.write(_canonical(value))
            fh.flush()
    except FileExistsError:
        raise GateError("refusing to overwrite existing output") from None
    except (OSError, UnicodeError, ValueError, OverflowError, RecursionError) as exc:
        raise GateError(f"cannot write output: {type(exc).__name__}") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Proposal validity / requote owner-review gate")
    sub = parser.add_subparsers(dest="command", required=True)
    compile_p = sub.add_parser("compile")
    compile_p.add_argument("--issued", required=True)
    compile_p.add_argument("--current", required=True)
    compile_p.add_argument("--out", required=True)
    verify_p = sub.add_parser("verify")
    verify_p.add_argument("--issued", required=True)
    verify_p.add_argument("--current", required=True)
    verify_p.add_argument("--packet", required=True)
    try:
        ns = parser.parse_args(argv)
        issued = _load(ns.issued)
        current = _load(ns.current)
        if ns.command == "compile":
            _write_new(ns.out, evaluate_offer(issued, current))
            return 0
        packet = _load(ns.packet)
        if not verify_packet(issued, current, packet):
            raise GateError("verification failed")
        print("VERIFIED")
        return 0
    except GateError as exc:
        print(f"ERROR: {exc}")
        return 2
    except (UnicodeError, ValueError, OverflowError, RecursionError, OSError) as exc:
        print(f"ERROR: bounded runtime failure: {type(exc).__name__}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
