"""Fail-closed procurement/teaming gate for OCS2026.01 pursuit work.

The gate never mints submission, pricing, legal, or buyer authority. It only
classifies what internal drafting/building posture is supported by supplied evidence.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

SCHEMA = "tjlabs.nm-ocs-tprm.qualification.v1"
RECEIPT_SCHEMA = "tjlabs.nm-ocs-tprm.qualification-receipt.v1"
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_PRIME = {"VERIFIED", "UNKNOWN", "NOT_ELIGIBLE"}
_ALLOWED_PACKET = {"VERIFIED", "UNVERIFIED"}
_ALLOWED_LEGAL = {"QUALIFIED_PARTNER_BOUND", "UNBOUND", "NOT_REQUIRED_BY_VERIFIED_PACKET"}


class ValidationError(ValueError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValidationError(str(exc)) from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _exact(value: Any, keys: set[str], where: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise ValidationError(f"{where} keys mismatch")
    return value


def _digest_or_none(value: Any, where: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str or not _SHA_RE.fullmatch(value):
        raise ValidationError(f"{where} invalid sha256")
    return value


def normalize(payload: Any) -> dict[str, Any]:
    p = copy.deepcopy(payload)
    _exact(
        p,
        {
            "schema",
            "opportunity_id",
            "controlling_packet",
            "prime_eligibility",
            "legal_scope",
            "owner_authorities",
        },
        "qualification",
    )
    if p["schema"] != SCHEMA or p["opportunity_id"] != "OCS2026.01":
        raise ValidationError("unsupported opportunity/schema")

    packet = _exact(
        p["controlling_packet"],
        {"status", "sha256", "source_url"},
        "controlling_packet",
    )
    if type(packet["status"]) is not str or packet["status"] not in _ALLOWED_PACKET:
        raise ValidationError("controlling_packet.status invalid")
    packet["sha256"] = _digest_or_none(packet["sha256"], "controlling_packet.sha256")
    if packet["status"] == "VERIFIED" and packet["sha256"] is None:
        raise ValidationError("verified controlling packet requires digest")
    if packet["status"] == "UNVERIFIED" and packet["sha256"] is not None:
        raise ValidationError("unverified packet cannot carry authoritative digest")
    if type(packet["source_url"]) is not str or not packet["source_url"].startswith("https://"):
        raise ValidationError("controlling_packet.source_url must be https URL")

    prime = _exact(
        p["prime_eligibility"],
        {"status", "evidence_sha256", "note"},
        "prime_eligibility",
    )
    if type(prime["status"]) is not str or prime["status"] not in _ALLOWED_PRIME:
        raise ValidationError("prime eligibility status invalid")
    prime["evidence_sha256"] = _digest_or_none(
        prime["evidence_sha256"], "prime_eligibility.evidence_sha256"
    )
    if prime["status"] in {"VERIFIED", "NOT_ELIGIBLE"} and prime["evidence_sha256"] is None:
        raise ValidationError("eligibility conclusion requires evidence digest")
    if type(prime["note"]) is not str or not prime["note"] or len(prime["note"]) > 600:
        raise ValidationError("prime eligibility note invalid")

    legal = _exact(p["legal_scope"], {"status", "evidence_sha256"}, "legal_scope")
    if type(legal["status"]) is not str or legal["status"] not in _ALLOWED_LEGAL:
        raise ValidationError("legal_scope.status invalid")
    legal["evidence_sha256"] = _digest_or_none(
        legal["evidence_sha256"], "legal_scope.evidence_sha256"
    )
    if legal["status"] == "QUALIFIED_PARTNER_BOUND" and legal["evidence_sha256"] is None:
        raise ValidationError("qualified legal partner requires evidence digest")
    if (
        legal["status"] == "NOT_REQUIRED_BY_VERIFIED_PACKET"
        and packet["status"] != "VERIFIED"
    ):
        raise ValidationError("legal-scope not-required conclusion needs verified packet")

    owner = _exact(
        p["owner_authorities"],
        {"pricing", "submission", "external_contact", "signature"},
        "owner_authorities",
    )
    for key, value in owner.items():
        if type(value) is not bool:
            raise ValidationError(f"owner_authorities.{key} must be bool")

    return p


def compile_qualification(payload: Any) -> dict[str, Any]:
    source = normalize(payload)
    holds: list[str] = []

    if source["controlling_packet"]["status"] != "VERIFIED":
        holds.append("HOLD_CONTROLLING_RFQ_REQUIRED")

    prime_status = source["prime_eligibility"]["status"]
    if prime_status == "UNKNOWN":
        holds.append("HOLD_PRIME_ELIGIBILITY_UNVERIFIED")
    elif prime_status == "NOT_ELIGIBLE":
        holds.append("DIRECT_PRIME_NOT_ELIGIBLE")

    legal_status = source["legal_scope"]["status"]
    if legal_status == "UNBOUND":
        holds.append("HOLD_LEGAL_SCOPE_PARTNER_UNBOUND")

    if source["controlling_packet"]["status"] != "VERIFIED":
        posture = "TEAMING_RESEARCH_ONLY"
    elif prime_status == "NOT_ELIGIBLE":
        posture = "TEAMING_DRAFT_READY_FOR_OWNER_REVIEW"
    elif prime_status == "UNKNOWN":
        posture = "TEAMING_DRAFT_READY_FOR_OWNER_REVIEW"
    elif legal_status == "UNBOUND":
        posture = "PRIME_TECHNICAL_DRAFT_ONLY"
    else:
        posture = "PRIME_DRAFT_READY_FOR_OWNER_REVIEW"

    # Even when owner flags are true, this artifact only records them. It never
    # converts self-declared flags into provider-side authority.
    core = {
        "schema": RECEIPT_SCHEMA,
        "source": source,
        "posture": posture,
        "holds": sorted(holds),
        "technical_workshare": {
            "toolset_engineering": True,
            "evidence_lineage": True,
            "vendor_tiering_workflow": True,
            "assessment_monitoring_workflow": True,
            "test_evaluation_harness": True,
            "implementation_documentation": True,
            "training_evidence": True,
            "legal_opinion": False,
            "procurement_certification": False,
        },
        "authority": {
            "price_authorized": False,
            "submission_authorized": False,
            "external_contact_authorized": False,
            "signature_authorized": False,
            "legal_advice_authorized": False,
            "award_or_revenue_claimed": False,
        },
    }
    return {**core, "receipt_sha256": _sha(core)}


def verify_receipt(receipt: Any) -> bool:
    if type(receipt) is not dict or "source" not in receipt:
        return False
    try:
        expected = compile_qualification(receipt["source"])
        return _canonical_bytes(receipt) == _canonical_bytes(expected)
    except (ValueError, TypeError, RecursionError):
        return False
