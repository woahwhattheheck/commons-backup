from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

SCHEMA = "paid-pilot-admission/v1"
RECEIPT_SCHEMA = "paid-pilot-admission-receipt/v1"
READY = "READY_FOR_OWNER_WORK_ADMISSION"

_HOLD = {
    "offer_expired": "HOLD_OFFER_EXPIRED",
    "acceptance_mismatch": "HOLD_ACCEPTANCE_MISMATCH",
    "funding_mismatch": "HOLD_FUNDING_MISMATCH",
    "funding_stale": "HOLD_FUNDING_STALE",
    "funding_future": "HOLD_FUNDING_FUTURE",
    "acceptance_future": "HOLD_ACCEPTANCE_FUTURE",
    "acceptance_after_funding": "HOLD_ACCEPTANCE_AFTER_FUNDING",
    "offer_future": "HOLD_OFFER_NOT_YET_ISSUED",
    "acceptance_before_offer": "HOLD_ACCEPTANCE_BEFORE_OFFER",
    "funding_before_offer": "HOLD_FUNDING_BEFORE_OFFER",
    "wrong_status": "HOLD_FUNDING_NOT_SETTLED",
}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_SETTLED = {"CAPTURED", "ESCROW_FUNDED"}
_SOURCE_AUTHORITIES = {"OWNER_VERIFIED_PROVIDER_READBACK", "OWNER_VERIFIED_ESCROW_READBACK"}


class AdmissionError(ValueError):
    pass


@dataclass(frozen=True)
class Evaluation:
    status: str
    reasons: tuple[str, ...]
    receipt: dict[str, Any]


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _require_object(value: Any, name: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise AdmissionError(f"{name} must be an object")
    return value


def _keys(obj: dict[str, Any], required: set[str], name: str) -> None:
    if set(obj) != required:
        missing = sorted(required - set(obj))
        extra = sorted(set(obj) - required)
        raise AdmissionError(f"{name} keys mismatch missing={missing} extra={extra}")


def _text(value: Any, name: str, *, max_len: int = 256) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > max_len:
        raise AdmissionError(f"{name} must be non-empty trimmed text <= {max_len}")
    if any(ord(ch) < 32 for ch in value):
        raise AdmissionError(f"{name} contains control characters")
    return value


def _sha(value: Any, name: str) -> str:
    value = _text(value, name, max_len=64)
    if not _HEX64.fullmatch(value):
        raise AdmissionError(f"{name} must be lowercase sha256 hex")
    return value


def _integer(value: Any, name: str, *, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise AdmissionError(f"{name} must be integer in [{low}, {high}]")
    return value


def _string_list(value: Any, name: str, *, maximum: int = 200) -> list[str]:
    if type(value) is not list or not value or len(value) > maximum:
        raise AdmissionError(f"{name} must be a non-empty list with <= {maximum} entries")
    out = [_text(item, f"{name}[]", max_len=512) for item in value]
    if len(set(out)) != len(out):
        raise AdmissionError(f"{name} entries must be unique")
    if out != sorted(out):
        raise AdmissionError(f"{name} entries must be sorted for stable authority binding")
    return out


def _utc(value: Any, name: str) -> datetime:
    text = _text(value, name, max_len=32)
    if not text.endswith("Z"):
        raise AdmissionError(f"{name} must use UTC Z form")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise AdmissionError(f"{name} must be RFC3339 UTC") from exc
    if parsed.tzinfo != timezone.utc or parsed.microsecond:
        raise AdmissionError(f"{name} must be whole-second UTC")
    return parsed


def _utc_text(value: datetime) -> str:
    value = value.astimezone(timezone.utc).replace(microsecond=0)
    return value.isoformat().replace("+00:00", "Z")


def normalize_packet(packet: Any) -> dict[str, Any]:
    root = _require_object(packet, "packet")
    _keys(root, {"schema", "offer", "acceptance", "funding"}, "packet")
    if root["schema"] != SCHEMA:
        raise AdmissionError(f"schema must equal {SCHEMA}")

    offer = _require_object(root["offer"], "offer")
    _keys(
        offer,
        {
            "offer_id",
            "buyer_scope",
            "currency",
            "price_minor",
            "admission_funding_minor",
            "scope",
            "acceptance_criteria",
            "issued_at",
            "expires_at",
            "funding_freshness_seconds",
        },
        "offer",
    )
    offer_id = _text(offer["offer_id"], "offer.offer_id")
    buyer_scope = _text(offer["buyer_scope"], "offer.buyer_scope")
    currency = _text(offer["currency"], "offer.currency", max_len=3)
    if not _CURRENCY.fullmatch(currency):
        raise AdmissionError("offer.currency must be ISO-style uppercase 3 letters")
    price_minor = _integer(offer["price_minor"], "offer.price_minor", low=1, high=10**12)
    admission = _integer(offer["admission_funding_minor"], "offer.admission_funding_minor", low=1, high=price_minor)
    scope = _string_list(offer["scope"], "offer.scope")
    criteria = _string_list(offer["acceptance_criteria"], "offer.acceptance_criteria")
    issued_at = _utc(offer["issued_at"], "offer.issued_at")
    expires_at = _utc(offer["expires_at"], "offer.expires_at")
    if expires_at <= issued_at:
        raise AdmissionError("offer.expires_at must be after offer.issued_at")
    freshness = _integer(
        offer["funding_freshness_seconds"],
        "offer.funding_freshness_seconds",
        low=60,
        high=7 * 24 * 60 * 60,
    )
    normalized_offer = {
        "acceptance_criteria": criteria,
        "admission_funding_minor": admission,
        "buyer_scope": buyer_scope,
        "currency": currency,
        "expires_at": _utc_text(expires_at),
        "funding_freshness_seconds": freshness,
        "issued_at": _utc_text(issued_at),
        "offer_id": offer_id,
        "price_minor": price_minor,
        "scope": scope,
    }
    offer_sha = digest(normalized_offer)

    acceptance = _require_object(root["acceptance"], "acceptance")
    _keys(acceptance, {"offer_id", "offer_sha256", "accepted_at", "evidence_sha256"}, "acceptance")
    normalized_acceptance = {
        "accepted_at": _utc_text(_utc(acceptance["accepted_at"], "acceptance.accepted_at")),
        "evidence_sha256": _sha(acceptance["evidence_sha256"], "acceptance.evidence_sha256"),
        "offer_id": _text(acceptance["offer_id"], "acceptance.offer_id"),
        "offer_sha256": _sha(acceptance["offer_sha256"], "acceptance.offer_sha256"),
    }

    funding = _require_object(root["funding"], "funding")
    _keys(
        funding,
        {
            "offer_id",
            "offer_sha256",
            "currency",
            "status",
            "amount_minor",
            "observed_at",
            "evidence_sha256",
            "source_authority",
        },
        "funding",
    )
    normalized_funding = {
        "amount_minor": _integer(funding["amount_minor"], "funding.amount_minor", low=0, high=10**12),
        "currency": _text(funding["currency"], "funding.currency", max_len=3),
        "evidence_sha256": _sha(funding["evidence_sha256"], "funding.evidence_sha256"),
        "observed_at": _utc_text(_utc(funding["observed_at"], "funding.observed_at")),
        "offer_id": _text(funding["offer_id"], "funding.offer_id"),
        "offer_sha256": _sha(funding["offer_sha256"], "funding.offer_sha256"),
        "source_authority": _text(funding["source_authority"], "funding.source_authority"),
        "status": _text(funding["status"], "funding.status", max_len=32),
    }
    if not _CURRENCY.fullmatch(normalized_funding["currency"]):
        raise AdmissionError("funding.currency must be ISO-style uppercase 3 letters")
    if normalized_funding["source_authority"] not in _SOURCE_AUTHORITIES:
        raise AdmissionError(f"funding.source_authority must be one of {sorted(_SOURCE_AUTHORITIES)}")

    return {
        "schema": SCHEMA,
        "offer": normalized_offer,
        "acceptance": normalized_acceptance,
        "funding": normalized_funding,
        "derived": {"offer_sha256": offer_sha},
    }


def _evaluate_at(packet: Any, *, at: datetime) -> Evaluation:
    """Historical evaluator used only behind trusted current evaluation and receipt verification."""
    if at.tzinfo is None:
        raise AdmissionError("evaluation time must be timezone-aware")
    now = at.astimezone(timezone.utc).replace(microsecond=0)
    normalized = normalize_packet(packet)
    offer = normalized["offer"]
    acceptance = normalized["acceptance"]
    funding = normalized["funding"]
    offer_sha = normalized["derived"]["offer_sha256"]

    accepted_at = _utc(acceptance["accepted_at"], "acceptance.accepted_at")
    observed_at = _utc(funding["observed_at"], "funding.observed_at")
    expires_at = _utc(offer["expires_at"], "offer.expires_at")
    issued_at = _utc(offer["issued_at"], "offer.issued_at")
    reasons: list[str] = []

    if now < issued_at:
        reasons.append(_HOLD["offer_future"])
    if now > expires_at:
        reasons.append(_HOLD["offer_expired"])
    if accepted_at < issued_at:
        reasons.append(_HOLD["acceptance_before_offer"])
    if observed_at < issued_at:
        reasons.append(_HOLD["funding_before_offer"])
    if accepted_at > now:
        reasons.append(_HOLD["acceptance_future"])
    if observed_at > now:
        reasons.append(_HOLD["funding_future"])
    if accepted_at > observed_at:
        reasons.append(_HOLD["acceptance_after_funding"])

    if acceptance["offer_id"] != offer["offer_id"] or acceptance["offer_sha256"] != offer_sha:
        reasons.append(_HOLD["acceptance_mismatch"])
    if (
        funding["offer_id"] != offer["offer_id"]
        or funding["offer_sha256"] != offer_sha
        or funding["currency"] != offer["currency"]
        or funding["amount_minor"] < offer["admission_funding_minor"]
        or funding["amount_minor"] > offer["price_minor"]
    ):
        reasons.append(_HOLD["funding_mismatch"])
    if funding["status"] not in _SETTLED:
        reasons.append(_HOLD["wrong_status"])
    if observed_at <= now and int((now - observed_at).total_seconds()) > offer["funding_freshness_seconds"]:
        reasons.append(_HOLD["funding_stale"])

    reasons = sorted(set(reasons))
    status = READY if not reasons else reasons[0]
    input_sha = digest({k: normalized[k] for k in ("schema", "offer", "acceptance", "funding")})
    receipt_core = {
        "schema": RECEIPT_SCHEMA,
        "evaluated_at": _utc_text(now),
        "evaluation_kind": "CURRENT_AT_EVALUATION",
        "historical_only_after_evaluation": True,
        "status": status,
        "reasons": reasons,
        "offer_id": offer["offer_id"],
        "buyer_scope": offer["buyer_scope"],
        "currency": offer["currency"],
        "price_minor": offer["price_minor"],
        "admission_funding_minor": offer["admission_funding_minor"],
        "observed_funding_minor": funding["amount_minor"],
        "funding_status": funding["status"],
        "funding_source_authority": funding["source_authority"],
        "offer_sha256": offer_sha,
        "scope_sha256": digest(offer["scope"]),
        "acceptance_criteria_sha256": digest(offer["acceptance_criteria"]),
        "acceptance_evidence_sha256": acceptance["evidence_sha256"],
        "funding_evidence_sha256": funding["evidence_sha256"],
        "input_sha256": input_sha,
        "external_authority": {
            "buyer_contact": False,
            "contract_or_signature": False,
            "payment_or_refund": False,
            "provider_mutation": False,
            "work_start": False,
            "buyer_acceptance_claim": False,
            "payment_claim": False,
            "revenue_recognition": False,
        },
    }
    receipt = dict(receipt_core)
    receipt["receipt_sha256"] = digest(receipt_core)
    return Evaluation(status=status, reasons=tuple(reasons), receipt=receipt)


def evaluate(packet: Any) -> Evaluation:
    """Evaluate a current owner-admission decision using the host process UTC clock."""
    return _evaluate_at(packet, at=datetime.now(timezone.utc))


def verify(packet: Any, receipt: Any) -> bool:
    """Verify historical receipt integrity only; never mint current work-admission authority."""
    supplied = _require_object(receipt, "receipt")
    evaluated_at = _utc(supplied.get("evaluated_at"), "receipt.evaluated_at")
    expected = _evaluate_at(packet, at=evaluated_at).receipt
    return supplied == expected


def markdown(receipt: dict[str, Any]) -> str:
    lines = [
        "# Paid Pilot Admission Receipt",
        "",
        f"- Status: `{receipt['status']}`",
        f"- Offer: `{receipt['offer_id']}`",
        f"- Buyer scope: `{receipt['buyer_scope']}`",
        f"- Evaluated at: `{receipt['evaluated_at']}`",
        f"- Price: `{receipt['price_minor']} {receipt['currency']} minor units`",
        f"- Admission funding required: `{receipt['admission_funding_minor']}`",
        f"- Observed funding: `{receipt['observed_funding_minor']}` / `{receipt['funding_status']}`",
        f"- Funding source authority label: `{receipt['funding_source_authority']}`",
        f"- Offer SHA-256: `{receipt['offer_sha256']}`",
        f"- Input SHA-256: `{receipt['input_sha256']}`",
        f"- Receipt SHA-256: `{receipt['receipt_sha256']}`",
        "",
        "## Holds",
    ]
    if receipt["reasons"]:
        lines.extend(f"- `{reason}`" for reason in receipt["reasons"])
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Authority ceiling",
            "This receipt is evidence for owner review only. It does not contact a buyer, create a contract/signature, move money, mutate a provider, start work, or recognize buyer acceptance/payment/revenue.",
            "A receipt is historical immediately after evaluation; re-evaluate against current evidence before any owner admission decision.",
        ]
    )
    return "\n".join(lines) + "\n"