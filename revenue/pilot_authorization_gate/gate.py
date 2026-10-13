from __future__ import annotations

from typing import Any
from . import _core

GateInputError = _core.GateInputError
HOLD = _core.HOLD
PROPOSAL_READY = _core.PROPOSAL_READY
READY = _core.READY
digest = _core.digest
canonical_bytes = _core.canonical_bytes

def _add_hold(result: dict[str, Any], code: str, *, buyer_ok: bool | None = None, funding_ok: bool | None = None) -> None:
    receipt = result["receipt"]
    holds = set(receipt["holds"])
    holds.add(code)
    receipt["holds"] = sorted(holds)
    receipt["decision"] = HOLD
    if buyer_ok is not None:
        receipt["buyer_approved"] = buyer_ok
    if funding_ok is not None:
        receipt["funding_ready"] = funding_ok

def _rehash(result: dict[str, Any]) -> None:
    core = dict(result["receipt"])
    core.pop("receipt_sha256", None)
    result["receipt"]["receipt_sha256"] = digest(core)

def evaluate(policy: Any, snapshot: Any, *, evaluated_at: str) -> dict[str, Any]:
    result = _core.evaluate(policy, snapshot, evaluated_at=evaluated_at)
    snap = _core._obj(snapshot, "snapshot")
    scope = result["scope"]
    captured = _core._utc(snap["captured_at"], "snapshot.captured_at")
    prepared = _core._utc(scope["prepared_at"], "scope.prepared_at")

    if scope["price_minor"] <= 0:
        raise GateInputError("scope.price_minor must be positive for a paid pilot")
    if captured < prepared:
        raise GateInputError("snapshot.captured_at cannot predate scope.prepared_at")

    buyer = snap["buyer_approval"]
    if buyer is not None:
        buyer_dt = _core._utc(buyer["approved_at"], "buyer_approval.approved_at")
        if buyer_dt > captured:
            raise GateInputError("buyer approval cannot occur after snapshot capture")
        if buyer_dt < prepared:
            _add_hold(result, "BUYER_APPROVAL_PREDATES_SCOPE", buyer_ok=False)

    funding = snap["funding"]
    if funding is not None:
        observed = _core._utc(funding["observed_at"], "funding.observed_at")
        if observed > captured:
            raise GateInputError("funding evidence cannot be observed after snapshot capture")
        expires_at = funding["expires_at"]
        if expires_at is not None and _core._utc(expires_at, "funding.expires_at") <= observed:
            raise GateInputError("funding.expires_at must be after funding.observed_at")
        if observed < prepared:
            _add_hold(result, "FUNDING_EVIDENCE_PREDATES_SCOPE", funding_ok=False)

    owner = snap["owner_approval"]
    if owner is not None:
        owner_dt = _core._utc(owner["approved_at"], "owner_approval.approved_at")
        if owner_dt > captured:
            raise GateInputError("owner approval cannot occur after snapshot capture")
        if owner_dt < prepared:
            _add_hold(result, "OWNER_APPROVAL_PREDATES_SCOPE")
        if owner["decision"] != "APPROVE":
            _add_hold(result, "OWNER_DID_NOT_APPROVE")
        if owner["scope_sha256"] != result["receipt"]["scope_sha256"]:
            _add_hold(result, "OWNER_SCOPE_MISMATCH")

    _rehash(result)
    return result

def verify(result: Any, *, policy: Any, snapshot: Any) -> bool:
    try:
        obj = _core._obj(result, "result")
        _core._keys(obj, {"receipt", "scope"}, "result")
        receipt = _core._obj(obj["receipt"], "receipt")
        if receipt.get("authority") != "EXACT_SCOPE_EXECUTION_EVIDENCE_ONLY":
            return False
        for field in (
            "contract_legally_enforceable_inferred", "funds_collected_cash_inferred",
            "production_access_authorized", "scope_expansion_authorized",
            "revenue_recognized_inferred", "provider_mutation_performed",
        ):
            if receipt.get(field) is not False:
                return False
        supplied = receipt.get("receipt_sha256")
        if type(supplied) is not str or _core._HEX64.fullmatch(supplied) is None:
            return False
        core = dict(receipt)
        core.pop("receipt_sha256")
        if digest(core) != supplied:
            return False
        expected = evaluate(policy, snapshot, evaluated_at=receipt["evaluated_at"])
        return canonical_bytes(expected) == canonical_bytes(obj)
    except (GateInputError, KeyError, TypeError, ValueError):
        return False
