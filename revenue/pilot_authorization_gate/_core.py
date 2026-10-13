from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

POLICY_SCHEMA = "paid-pilot-authorization-policy/v1"
SNAPSHOT_SCHEMA = "paid-pilot-authorization-snapshot/v1"
SCOPE_SCHEMA = "paid-pilot-scope/v1"
RECEIPT_SCHEMA = "paid-pilot-authorization-receipt/v1"
READY = "FUNDED_EXECUTION_READY_EVIDENCE_ONLY"
PROPOSAL_READY = "PROPOSAL_READY"
HOLD = "HOLD"

MAX_JSON_BYTES = 1_048_576
MAX_STRING_BYTES = 1024
MAX_ITEMS = 128
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class GateInputError(ValueError):
    pass


def _obj(value: Any, name: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise GateInputError(f"{name} must be an object")
    return value


def _keys(value: dict[str, Any], expected: set[str], name: str) -> None:
    got = set(value)
    if got != expected:
        raise GateInputError(f"{name} fields mismatch; missing={sorted(expected-got)}, extra={sorted(got-expected)}")


def _str(value: Any, name: str, max_bytes: int = MAX_STRING_BYTES) -> str:
    if type(value) is not str or not value or len(value.encode("utf-8")) > max_bytes:
        raise GateInputError(f"{name} must be a non-empty bounded string")
    return value


def _id(value: Any, name: str) -> str:
    value = _str(value, name, 128)
    if _ID.fullmatch(value) is None:
        raise GateInputError(f"{name} must be a canonical identifier")
    return value


def _bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise GateInputError(f"{name} must be boolean")
    return value


def _int(value: Any, name: str, minimum: int = 0, maximum: int = 10**15) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise GateInputError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _utc(value: Any, name: str) -> datetime:
    value = _str(value, name, 64)
    if not value.endswith("Z"):
        raise GateInputError(f"{name} must be UTC and end in Z")
    try:
        dt = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise GateInputError(f"{name} must be ISO-8601 UTC") from exc
    if dt.utcoffset() != timezone.utc.utcoffset(dt):
        raise GateInputError(f"{name} must be UTC")
    return dt


def canonical_bytes(value: Any) -> bytes:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise GateInputError("input must be canonical JSON data") from exc
    if len(raw) > MAX_JSON_BYTES:
        raise GateInputError("canonical JSON exceeds 1 MiB")
    return raw


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _string_list(value: Any, name: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if type(value) is not list or len(value) > MAX_ITEMS or (not allow_empty and not value):
        raise GateInputError(f"{name} must be a bounded array")
    vals = tuple(_id(v, f"{name}[]") for v in value)
    if len(vals) != len(set(vals)):
        raise GateInputError(f"{name} contains duplicates")
    return tuple(sorted(vals))


def _parse_policy(raw: Any) -> dict[str, Any]:
    p = _obj(raw, "policy")
    _keys(p, {"schema", "accepted_funding_states", "max_proposal_age_seconds", "owner_approval_default_required"}, "policy")
    if p["schema"] != POLICY_SCHEMA:
        raise GateInputError("unsupported policy schema")
    states = _obj(p["accepted_funding_states"], "policy.accepted_funding_states")
    if not 1 <= len(states) <= 32:
        raise GateInputError("accepted_funding_states cardinality out of bounds")
    parsed_states: dict[str, tuple[str, ...]] = {}
    for funding_type, raw_states in sorted(states.items()):
        parsed_states[_id(funding_type, "funding type")] = _string_list(raw_states, f"funding states for {funding_type}")
    return {
        "states": parsed_states,
        "max_age": _int(p["max_proposal_age_seconds"], "policy.max_proposal_age_seconds", 1, 90 * 24 * 3600),
        "owner_default": _bool(p["owner_approval_default_required"], "policy.owner_approval_default_required"),
    }


def _parse_scope(raw: Any) -> dict[str, Any]:
    s = _obj(raw, "scope")
    _keys(s, {"schema", "scope_id", "version", "deliverables", "exclusions", "acceptance", "required_inputs", "price_minor", "currency", "owner_approval_required", "prepared_at", "expires_at"}, "scope")
    if s["schema"] != SCOPE_SCHEMA:
        raise GateInputError("unsupported scope schema")
    prepared = _utc(s["prepared_at"], "scope.prepared_at")
    expires = _utc(s["expires_at"], "scope.expires_at")
    if expires <= prepared:
        raise GateInputError("scope.expires_at must be after prepared_at")
    currency = _str(s["currency"], "scope.currency", 3)
    if _CURRENCY.fullmatch(currency) is None:
        raise GateInputError("scope.currency must be ISO-like uppercase 3-letter code")
    return {
        "schema": SCOPE_SCHEMA,
        "scope_id": _id(s["scope_id"], "scope.scope_id"),
        "version": _id(s["version"], "scope.version"),
        "deliverables": _string_list(s["deliverables"], "scope.deliverables"),
        "exclusions": _string_list(s["exclusions"], "scope.exclusions", allow_empty=True),
        "acceptance": _string_list(s["acceptance"], "scope.acceptance"),
        "required_inputs": _string_list(s["required_inputs"], "scope.required_inputs", allow_empty=True),
        "price_minor": _int(s["price_minor"], "scope.price_minor", 0),
        "currency": currency,
        "owner_approval_required": _bool(s["owner_approval_required"], "scope.owner_approval_required"),
        "prepared_at": s["prepared_at"],
        "expires_at": s["expires_at"],
    }


def _parse_buyer(raw: Any, scope_sha: str, evaluated: datetime) -> dict[str, Any] | None:
    if raw is None:
        return None
    b = _obj(raw, "buyer_approval")
    _keys(b, {"buyer_id", "decision", "scope_sha256", "approved_at"}, "buyer_approval")
    decision = _id(b["decision"], "buyer_approval.decision")
    if decision not in {"YES", "NO"}:
        raise GateInputError("buyer decision must be YES or NO")
    if b["scope_sha256"] != scope_sha:
        return {"buyer_id": _id(b["buyer_id"], "buyer_approval.buyer_id"), "decision": decision, "scope_mismatch": True, "approved_at": b["approved_at"]}
    approved = _utc(b["approved_at"], "buyer_approval.approved_at")
    if approved > evaluated:
        raise GateInputError("buyer approval cannot be in the future")
    return {"buyer_id": _id(b["buyer_id"], "buyer_approval.buyer_id"), "decision": decision, "scope_mismatch": False, "approved_at": b["approved_at"]}


def _parse_funding(raw: Any, scope_sha: str, evaluated: datetime) -> dict[str, Any] | None:
    if raw is None:
        return None
    f = _obj(raw, "funding")
    _keys(f, {"funding_id", "funding_type", "state", "scope_sha256", "amount_minor", "currency", "observed_at", "expires_at"}, "funding")
    observed = _utc(f["observed_at"], "funding.observed_at")
    if observed > evaluated:
        raise GateInputError("funding evidence cannot be in the future")
    expires_at = f["expires_at"]
    expires_dt = None if expires_at is None else _utc(expires_at, "funding.expires_at")
    currency = _str(f["currency"], "funding.currency", 3)
    if _CURRENCY.fullmatch(currency) is None:
        raise GateInputError("funding.currency invalid")
    return {
        "funding_id": _id(f["funding_id"], "funding.funding_id"),
        "funding_type": _id(f["funding_type"], "funding.funding_type"),
        "state": _id(f["state"], "funding.state"),
        "scope_mismatch": f["scope_sha256"] != scope_sha,
        "amount_minor": _int(f["amount_minor"], "funding.amount_minor", 0),
        "currency": currency,
        "observed_at": f["observed_at"],
        "expires_at": expires_at,
        "expired": expires_dt is not None and expires_dt <= evaluated,
    }


def _parse_intake(raw: Any, scope_sha: str) -> dict[str, Any] | None:
    if raw is None:
        return None
    i = _obj(raw, "intake")
    _keys(i, {"scope_sha256", "received_inputs"}, "intake")
    return {"scope_mismatch": i["scope_sha256"] != scope_sha, "received_inputs": _string_list(i["received_inputs"], "intake.received_inputs", allow_empty=True)}


def _parse_owner(raw: Any, scope_sha: str, evaluated: datetime) -> dict[str, Any] | None:
    if raw is None:
        return None
    o = _obj(raw, "owner_approval")
    _keys(o, {"owner_id", "decision", "scope_sha256", "approved_at"}, "owner_approval")
    decision = _id(o["decision"], "owner_approval.decision")
    if decision not in {"APPROVE", "REJECT"}:
        raise GateInputError("owner decision invalid")
    approved = _utc(o["approved_at"], "owner_approval.approved_at")
    if approved > evaluated:
        raise GateInputError("owner approval cannot be in the future")
    return {"owner_id": _id(o["owner_id"], "owner_approval.owner_id"), "decision": decision, "scope_mismatch": o["scope_sha256"] != scope_sha, "approved_at": o["approved_at"]}


def evaluate(policy: Any, snapshot: Any, *, evaluated_at: str) -> dict[str, Any]:
    evaluated = _utc(evaluated_at, "evaluated_at")
    pp = _parse_policy(policy)
    snap = _obj(snapshot, "snapshot")
    _keys(snap, {"schema", "capture_complete", "scope", "buyer_approval", "funding", "intake", "owner_approval", "captured_at"}, "snapshot")
    if snap["schema"] != SNAPSHOT_SCHEMA:
        raise GateInputError("unsupported snapshot schema")
    complete = _bool(snap["capture_complete"], "snapshot.capture_complete")
    captured = _utc(snap["captured_at"], "snapshot.captured_at")
    if captured > evaluated:
        raise GateInputError("snapshot cannot be captured in the future")

    scope = _parse_scope(snap["scope"])
    scope_sha = digest(scope)
    prepared = _utc(scope["prepared_at"], "scope.prepared_at")
    expires = _utc(scope["expires_at"], "scope.expires_at")
    buyer = _parse_buyer(snap["buyer_approval"], scope_sha, evaluated)
    funding = _parse_funding(snap["funding"], scope_sha, evaluated)
    intake = _parse_intake(snap["intake"], scope_sha)
    owner = _parse_owner(snap["owner_approval"], scope_sha, evaluated)

    holds: set[str] = set()
    blockers: set[str] = set()
    if not complete:
        holds.add("CAPTURE_INCOMPLETE")
    if evaluated >= expires:
        holds.add("SCOPE_EXPIRED")
    if int((evaluated - prepared).total_seconds()) > pp["max_age"]:
        holds.add("SCOPE_STALE")

    if buyer is None:
        blockers.add("BUYER_APPROVAL_MISSING")
    else:
        if buyer["scope_mismatch"]:
            holds.add("BUYER_SCOPE_MISMATCH")
        if buyer["decision"] != "YES":
            holds.add("BUYER_DID_NOT_APPROVE")

    if funding is None:
        blockers.add("FUNDING_EVIDENCE_MISSING")
    else:
        if funding["scope_mismatch"]:
            holds.add("FUNDING_SCOPE_MISMATCH")
        accepted_states = pp["states"].get(funding["funding_type"])
        if accepted_states is None:
            holds.add("FUNDING_TYPE_NOT_ACCEPTED")
        elif funding["state"] not in accepted_states:
            holds.add("FUNDING_STATE_NOT_EXECUTION_READY")
        if funding["amount_minor"] != scope["price_minor"]:
            holds.add("FUNDING_AMOUNT_MISMATCH")
        if funding["currency"] != scope["currency"]:
            holds.add("FUNDING_CURRENCY_MISMATCH")
        if funding["expired"]:
            holds.add("FUNDING_EXPIRED")

    required_inputs = set(scope["required_inputs"])
    if intake is None:
        if required_inputs:
            blockers.add("INTAKE_MISSING")
    else:
        if intake["scope_mismatch"]:
            holds.add("INTAKE_SCOPE_MISMATCH")
        missing = sorted(required_inputs - set(intake["received_inputs"]))
        if missing:
            blockers.add("INTAKE_INCOMPLETE:" + ",".join(missing))
        extras = sorted(set(intake["received_inputs"]) - required_inputs)
        if extras:
            holds.add("UNDECLARED_INTAKE_INPUT:" + ",".join(extras))

    owner_required = scope["owner_approval_required"] or pp["owner_default"]
    if owner_required:
        if owner is None:
            blockers.add("OWNER_APPROVAL_MISSING")
        else:
            if owner["scope_mismatch"]:
                holds.add("OWNER_SCOPE_MISMATCH")
            if owner["decision"] != "APPROVE":
                holds.add("OWNER_DID_NOT_APPROVE")

    if holds:
        decision = HOLD
    elif blockers:
        decision = PROPOSAL_READY
    else:
        decision = READY

    core = {
        "schema": RECEIPT_SCHEMA,
        "decision": decision,
        "holds": sorted(holds),
        "blockers": sorted(blockers),
        "evaluated_at": evaluated_at,
        "scope_id": scope["scope_id"],
        "scope_version": scope["version"],
        "scope_sha256": scope_sha,
        "snapshot_sha256": digest(snapshot),
        "price_minor": scope["price_minor"],
        "currency": scope["currency"],
        "buyer_approved": buyer is not None and buyer["decision"] == "YES" and not buyer["scope_mismatch"],
        "funding_ready": funding is not None and not any(code.startswith("FUNDING_") for code in holds),
        "required_input_count": len(required_inputs),
        "owner_approval_required": owner_required,
        "authority": "EXACT_SCOPE_EXECUTION_EVIDENCE_ONLY",
        "contract_legally_enforceable_inferred": False,
        "funds_collected_cash_inferred": False,
        "production_access_authorized": False,
        "scope_expansion_authorized": False,
        "revenue_recognized_inferred": False,
        "provider_mutation_performed": False,
    }
    receipt = dict(core)
    receipt["receipt_sha256"] = digest(core)
    return {"receipt": receipt, "scope": scope}


def verify(result: Any, *, policy: Any, snapshot: Any) -> bool:
    try:
        obj = _obj(result, "result")
        _keys(obj, {"receipt", "scope"}, "result")
        receipt = _obj(obj["receipt"], "receipt")
        if receipt.get("authority") != "EXACT_SCOPE_EXECUTION_EVIDENCE_ONLY":
            return False
        for field in (
            "contract_legally_enforceable_inferred", "funds_collected_cash_inferred", "production_access_authorized",
            "scope_expansion_authorized", "revenue_recognized_inferred", "provider_mutation_performed",
        ):
            if receipt.get(field) is not False:
                return False
        supplied = receipt.get("receipt_sha256")
        if type(supplied) is not str or _HEX64.fullmatch(supplied) is None:
            return False
        core = dict(receipt)
        core.pop("receipt_sha256")
        if digest(core) != supplied:
            return False
        expected = evaluate(policy, snapshot, evaluated_at=receipt["evaluated_at"])
        return canonical_bytes(expected) == canonical_bytes(obj)
    except (GateInputError, KeyError, TypeError, ValueError):
        return False
