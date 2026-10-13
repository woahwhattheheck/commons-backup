from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

OFFER_ID = "tenderproof-rfp-evidence-sprint-v1"
OFFER_PRICE_USD = Decimal("2500.00")
SCHEMA_VERSION = "tenderproof.paid-intake.v1"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class IntakeError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _strict_bool(value: Any, path: str) -> bool:
    if type(value) is not bool:
        raise IntakeError(f"{path} must be boolean")
    return value


def _nonempty(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IntakeError(f"{path} must be a non-empty string")
    return value.strip()


def _money(value: Any, path: str) -> Decimal:
    if isinstance(value, bool):
        raise IntakeError(f"{path} must be a decimal-compatible amount")
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise IntakeError(f"{path} must be a decimal-compatible amount") from exc
    if amount < 0:
        raise IntakeError(f"{path} cannot be negative")
    return amount


@dataclass(frozen=True)
class GateResult:
    state: str
    blockers: tuple[str, ...]
    offer_id: str = OFFER_ID
    expected_price_usd: str = str(OFFER_PRICE_USD)


def validate_intake(data: Any) -> GateResult:
    if not isinstance(data, dict):
        raise IntakeError("intake root must be an object")

    if data.get("offer_id") != OFFER_ID:
        raise IntakeError(f"offer_id must equal {OFFER_ID}")

    buyer = data.get("buyer")
    if not isinstance(buyer, dict):
        raise IntakeError("buyer must be an object")
    _nonempty(buyer.get("organization"), "buyer.organization")
    _nonempty(buyer.get("contact_route"), "buyer.contact_route")

    buyer_yes = _strict_bool(data.get("buyer_yes"), "buyer_yes")
    scope_accepted = _strict_bool(data.get("scope_accepted"), "scope_accepted")
    buyer_authorized_inputs = _strict_bool(data.get("buyer_authorized_inputs"), "buyer_authorized_inputs")

    funding = data.get("funding")
    if not isinstance(funding, dict):
        raise IntakeError("funding must be an object")
    payment_received = _strict_bool(funding.get("payment_received"), "funding.payment_received")
    amount = _money(funding.get("amount_usd", 0), "funding.amount_usd")
    receipt_ref = funding.get("receipt_ref")
    if receipt_ref is not None and not isinstance(receipt_ref, str):
        raise IntakeError("funding.receipt_ref must be a string or null")

    solicitation = data.get("solicitation")
    if not isinstance(solicitation, dict):
        raise IntakeError("solicitation must be an object")
    title = solicitation.get("title")
    source_ref = solicitation.get("source_ref")
    digest = solicitation.get("content_sha256")

    evidence = data.get("evidence_register")
    if not isinstance(evidence, list):
        raise IntakeError("evidence_register must be an array")
    evidence_ids: set[str] = set()
    for i, item in enumerate(evidence):
        if not isinstance(item, dict):
            raise IntakeError(f"evidence_register[{i}] must be an object")
        eid = _nonempty(item.get("id"), f"evidence_register[{i}].id")
        if eid in evidence_ids:
            raise IntakeError(f"duplicate evidence id: {eid}")
        evidence_ids.add(eid)
        _nonempty(item.get("source_ref"), f"evidence_register[{i}].source_ref")
        _strict_bool(item.get("buyer_supplied"), f"evidence_register[{i}].buyer_supplied")

    blockers: list[str] = []
    if not buyer_yes:
        blockers.append("BUYER_YES_REQUIRED")
    if not scope_accepted:
        blockers.append("SCOPE_ACCEPTANCE_REQUIRED")
    if not payment_received:
        blockers.append("PAYMENT_REQUIRED")
    elif amount != OFFER_PRICE_USD:
        blockers.append("PAYMENT_AMOUNT_MISMATCH")
    elif not receipt_ref or not receipt_ref.strip():
        blockers.append("PAYMENT_RECEIPT_REQUIRED")
    if not buyer_authorized_inputs:
        blockers.append("BUYER_INPUT_AUTHORIZATION_REQUIRED")

    if not isinstance(title, str) or not title.strip():
        blockers.append("SOLICITATION_TITLE_REQUIRED")
    if not isinstance(source_ref, str) or not source_ref.strip():
        blockers.append("SOLICITATION_SOURCE_REQUIRED")
    if not isinstance(digest, str) or not _HEX64.fullmatch(digest):
        blockers.append("SOLICITATION_SHA256_REQUIRED")
    if not evidence:
        blockers.append("EVIDENCE_REGISTER_REQUIRED")

    if blockers:
        if "BUYER_YES_REQUIRED" in blockers:
            state = "HOLD_NO_BUYER_YES"
        elif "SCOPE_ACCEPTANCE_REQUIRED" in blockers:
            state = "HOLD_SCOPE_NOT_ACCEPTED"
        elif any(x.startswith("PAYMENT_") for x in blockers):
            state = "HOLD_UNFUNDED"
        else:
            state = "HOLD_INPUTS"
        return GateResult(state=state, blockers=tuple(blockers))

    return GateResult(state="READY_FOR_DELIVERY", blockers=())


def build_receipt(data: Any) -> dict[str, Any]:
    result = validate_intake(data)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "offer_id": OFFER_ID,
        "expected_price_usd": str(OFFER_PRICE_USD),
        "gate": asdict(result),
        "intake_sha256": sha256_text(canonical_json(data)),
        "authority": {
            "proposal_submission_authorized": False,
            "legal_or_certification_assertion_authorized": False,
            "buyer_communication_authorized_by_gate": False,
            "revenue_recognition_authorized_by_gate": False,
        },
    }
    receipt_hash = sha256_text(canonical_json(normalized))
    normalized["receipt"] = {"payload_sha256": receipt_hash, "schema_version": SCHEMA_VERSION}
    return normalized


def verify_receipt(receipt: Any) -> bool:
    if not isinstance(receipt, dict):
        return False
    marker = receipt.get("receipt")
    if not isinstance(marker, dict) or marker.get("schema_version") != SCHEMA_VERSION:
        return False
    bare = dict(receipt)
    bare.pop("receipt", None)
    if marker.get("payload_sha256") != sha256_text(canonical_json(bare)):
        return False
    authority = bare.get("authority")
    required_false = (
        "proposal_submission_authorized",
        "legal_or_certification_assertion_authorized",
        "buyer_communication_authorized_by_gate",
        "revenue_recognition_authorized_by_gate",
    )
    return isinstance(authority, dict) and all(authority.get(k) is False for k in required_false)
