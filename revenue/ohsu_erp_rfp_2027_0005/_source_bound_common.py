from __future__ import annotations

import datetime as _dt
import hashlib
import json
from typing import Any

from ._source_bound_constants import ContractError, MAX_STDIN_BYTES, _SHA256_CHARS

def _canonical(obj: Any) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
def _sha(obj: Any) -> str:
    return hashlib.sha256(_canonical(obj)).hexdigest()
def _workshare() -> dict[str, Any]:
    return {
        "commercial_status": "PROPOSED_NOT_ACCEPTED",
        "fixed_price_usd": 12500,
        "delivery_window_status": "TO_NEGOTIATE",
        "scope": [
            "source-bound requirement register across interviews, current-state artifacts, controls, and future-state needs",
            "requirement to evidence to owner to gap/risk traceability with orphan detection",
            "deterministic coverage and contradiction reports across finance, HR, supply-chain, and administrative workflows",
            "decision receipts separating observed current-state evidence, stakeholder assertions, and consultant recommendations",
            "AI/automation opportunity entries with explicit human approval, source provenance, and control requirements",
        ],
    }
def _authority_false() -> dict[str, bool]:
    return {
        "buyer_contact_authorized": False,
        "intent_to_bid_authorized": False,
        "proposal_submission_authorized": False,
        "prime_eligibility_verified_by_ohsu": False,
        "teaming_commitment_accepted": False,
        "contract_accepted": False,
        "payment_verified": False,
        "revenue_recognized": False,
    }
def _require_keys(obj: dict[str, Any], *, exact: set[str], where: str) -> None:
    got = set(obj)
    if got != exact:
        raise ContractError(
            f"{where} keys mismatch; missing={sorted(exact - got)} extra={sorted(got - exact)}"
        )
def _require_sha256(value: Any, where: str, *, allow_none: bool = False) -> str | None:
    if allow_none and value is None:
        return None
    if not isinstance(value, str) or len(value) != 64 or any(c not in _SHA256_CHARS for c in value):
        raise ContractError(f"{where} must be exact lowercase sha256")
    return value
def _require_utc_instant(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ContractError(f"{where} must be UTC Z timestamp")
    try:
        parsed = _dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError(f"{where} invalid UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != _dt.timedelta(0):
        raise ContractError(f"{where} must be UTC")
    return parsed.astimezone(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
def _parse_strict_json(raw: bytes, where: str) -> Any:
    if len(raw) > MAX_STDIN_BYTES:
        raise ContractError(f"{where} exceeds {MAX_STDIN_BYTES} bytes")
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise ContractError(f"{where} is not strict UTF-8") from exc

    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise ContractError(f"{where} duplicate JSON key: {key}")
            out[key] = value
        return out

    def bad_constant(token: str) -> Any:
        raise ContractError(f"{where} non-finite JSON number: {token}")

    try:
        return json.loads(text, object_pairs_hook=hook, parse_constant=bad_constant)
    except ContractError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ContractError(f"{where} invalid JSON") from exc
