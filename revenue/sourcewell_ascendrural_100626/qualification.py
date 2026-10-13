from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any, Iterable, Mapping

EXPECTED_RFP = "100626"
EXPECTED_ISSUER = "Sourcewell"
EXPECTED_TITLE = "AscendRural Innovation Challenge: Bridging Distance to Rural Care & Services"
EXPECTED_QUESTION_DEADLINE = "2026-09-28T15:30:00-05:00"
EXPECTED_CLOSE = "2026-10-06T15:30:00-05:00"
OFFICIAL_PORTAL_PREFIX = "https://proportal.sourcewell-mn.gov/"
PROBLEM_AREAS = frozenset({
    "transportation_access_and_coordination",
    "local_access_to_care",
    "chronic_condition_management",
    "last_mile_delivery_of_essentials",
    "business_of_rural_access",
})
REQUIRED_CONTROLLING_KINDS = frozenset({"RFP", "MASTER_AGREEMENT", "FAQ_OR_QA", "ADDENDA_INDEX"})
FORBIDDEN_AUTHORITY_FIELDS = (
    "emergency_dispatch_authority", "clinical_decision_authority", "diagnosis_authority",
    "treatment_authority", "eligibility_adjudication_authority", "payment_authority",
    "buyer_contact_authority", "submission_authority", "contract_signature_authority",
    "revenue_recognition_authority",
)

class QualificationError(ValueError):
    pass

def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")

def sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()

def _strict_keys(value: Mapping[str, Any], allowed: set[str], label: str) -> None:
    extra = set(value) - allowed
    if extra:
        raise QualificationError(f"{label}: unknown keys: {sorted(extra)}")

def _parse_time(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except Exception as exc:
        raise QualificationError(f"{label}: invalid ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise QualificationError(f"{label}: timezone required")
    return parsed

@dataclass(frozen=True)
class QualificationReceipt:
    disposition: str
    blockers: tuple[str, ...]
    verified_facts: tuple[str, ...]
    opportunity_digest: str
    controlling_digest: str | None
    product_digest: str
    receipt_digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "sourcewell.ascendrural.qualification/v1",
            "disposition": self.disposition,
            "blockers": list(self.blockers),
            "verified_facts": list(self.verified_facts),
            "opportunity_digest": self.opportunity_digest,
            "controlling_digest": self.controlling_digest,
            "product_digest": self.product_digest,
            "receipt_digest": self.receipt_digest,
        }

def qualify(opportunity: Mapping[str, Any], controlling_docs: Iterable[Mapping[str, Any]], product: Mapping[str, Any], *, verified_at: datetime) -> QualificationReceipt:
    if verified_at.tzinfo is None:
        raise QualificationError("verified_at must be timezone-aware")
    _strict_keys(opportunity, {"rfp_id", "issuer", "title", "status", "question_deadline", "close_deadline", "submission_type", "official_portal_url", "problem_areas", "public_budget", "source_observed_at"}, "opportunity")
    if opportunity.get("rfp_id") != EXPECTED_RFP: raise QualificationError("wrong RFP id")
    if opportunity.get("issuer") != EXPECTED_ISSUER: raise QualificationError("wrong issuer")
    if opportunity.get("title") != EXPECTED_TITLE: raise QualificationError("wrong title")
    if opportunity.get("status") != "OPEN": raise QualificationError("opportunity must be OPEN")
    if opportunity.get("question_deadline") != EXPECTED_QUESTION_DEADLINE: raise QualificationError("question deadline drift")
    if opportunity.get("close_deadline") != EXPECTED_CLOSE: raise QualificationError("close deadline drift")
    if opportunity.get("submission_type") != "ONLINE_ONLY": raise QualificationError("submission route drift")
    portal = opportunity.get("official_portal_url")
    if not isinstance(portal, str) or not portal.startswith(OFFICIAL_PORTAL_PREFIX): raise QualificationError("official portal must be Sourcewell")
    if opportunity.get("public_budget") is not None: raise QualificationError("public budget is not established by the open notice")
    areas = opportunity.get("problem_areas")
    if not isinstance(areas, list) or not areas: raise QualificationError("problem_areas must be non-empty list")
    if len(set(areas)) != len(areas): raise QualificationError("duplicate problem area")
    if not set(areas).issubset(PROBLEM_AREAS): raise QualificationError("unknown problem area")
    observed = _parse_time(str(opportunity.get("source_observed_at")), "source_observed_at")
    if observed > verified_at: raise QualificationError("source observation is in the future")
    blockers: list[str] = []
    if verified_at >= _parse_time(EXPECTED_CLOSE, "close_deadline"):
        blockers.append("DEADLINE_CLOSED")

    _strict_keys(product, {"name", "version", "problem_areas", "low_bandwidth_mode", "idempotent_replay", "evidence_bound_status", "operator_review_required", *FORBIDDEN_AUTHORITY_FIELDS}, "product")
    if product.get("name") != "Rural Access Relay": raise QualificationError("unexpected product")
    if product.get("version") != 1: raise QualificationError("unexpected product version")
    p_areas = product.get("problem_areas")
    if not isinstance(p_areas, list) or not p_areas: raise QualificationError("product problem areas required")
    if not set(p_areas).issubset(set(areas)): raise QualificationError("product claims problem area outside source notice")
    for field in ("low_bandwidth_mode", "idempotent_replay", "evidence_bound_status", "operator_review_required"):
        if product.get(field) is not True: raise QualificationError(f"{field} must be true")
    for field in FORBIDDEN_AUTHORITY_FIELDS:
        if product.get(field) is not False: raise QualificationError(f"{field} must be explicitly false")

    docs = list(controlling_docs)
    seen_kind: set[str] = set()
    normalized_docs: list[dict[str, Any]] = []
    for i, doc in enumerate(docs):
        if not isinstance(doc, Mapping): raise QualificationError(f"controlling_docs[{i}] must be object")
        _strict_keys(doc, {"kind", "name", "sha256", "source_url", "retrieved_at", "superseded"}, f"controlling_docs[{i}]")
        kind = doc.get("kind")
        if kind not in REQUIRED_CONTROLLING_KINDS: raise QualificationError(f"unknown controlling document kind: {kind!r}")
        if kind in seen_kind: raise QualificationError(f"duplicate controlling document kind: {kind}")
        seen_kind.add(str(kind))
        digest = doc.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest): raise QualificationError(f"{kind}: invalid sha256")
        url = doc.get("source_url")
        if not isinstance(url, str) or not url.startswith(OFFICIAL_PORTAL_PREFIX): raise QualificationError(f"{kind}: source must be official portal")
        if doc.get("superseded") is not False: raise QualificationError(f"{kind}: superseded must be false")
        retrieved = _parse_time(str(doc.get("retrieved_at")), f"{kind}.retrieved_at")
        if retrieved > verified_at: raise QualificationError(f"{kind}: retrieved_at in future")
        normalized_docs.append(dict(doc))
    missing = sorted(REQUIRED_CONTROLLING_KINDS - seen_kind)
    if missing:
        blockers.extend(f"CONTROLLING_{kind}_REQUIRED" for kind in missing)

    opportunity_digest = sha256_json(dict(opportunity))
    product_digest = sha256_json(dict(product))
    controlling_digest = sha256_json(sorted(normalized_docs, key=lambda d: d["kind"])) if normalized_docs else None
    if not blockers:
        disposition = "CONTROLLING_SOURCE_BOUND_REVIEW_REQUIRED"
        blockers = ["REQUIREMENTS_AND_PROPOSAL_REVIEW_REQUIRED"]
    else:
        disposition = "HOLD"
    verified_facts = (
        f"RFP={EXPECTED_RFP}", "STATUS=OPEN_AT_SOURCE_OBSERVATION",
        f"QUESTION_DEADLINE={EXPECTED_QUESTION_DEADLINE}", f"CLOSE_DEADLINE={EXPECTED_CLOSE}",
        "PUBLIC_BUDGET=UNKNOWN", "PRODUCT_AUTHORITY=NON_TRANSACTING_NON_CLINICAL",
    )
    body = {"schema": "sourcewell.ascendrural.qualification/v1", "disposition": disposition, "blockers": blockers, "verified_facts": list(verified_facts), "opportunity_digest": opportunity_digest, "controlling_digest": controlling_digest, "product_digest": product_digest}
    return QualificationReceipt(disposition, tuple(blockers), verified_facts, opportunity_digest, controlling_digest, product_digest, sha256_json(body))

def verify_receipt(receipt: Mapping[str, Any]) -> bool:
    _strict_keys(receipt, {"schema", "disposition", "blockers", "verified_facts", "opportunity_digest", "controlling_digest", "product_digest", "receipt_digest"}, "receipt")
    if receipt.get("schema") != "sourcewell.ascendrural.qualification/v1": return False
    digest = receipt.get("receipt_digest")
    if not isinstance(digest, str): return False
    body = dict(receipt); body.pop("receipt_digest", None)
    return sha256_json(body) == digest
