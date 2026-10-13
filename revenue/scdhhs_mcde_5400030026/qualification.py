"""Fail-closed evidence compiler for SCDHHS solicitation 5400030026."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2
HERE = Path(__file__).resolve().parent
SOURCE_CONTRACT = json.loads((HERE / "source_contract.json").read_text(encoding="utf-8"))
OPERATION_KEY = SOURCE_CONTRACT["operation_key"]
ROUTES = {"prime_offeror", "subcontractor_to_qualified_prime"}


class QualificationError(ValueError):
    """Malformed or ambiguous evidence packet."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise QualificationError(f"value is not canonical finite JSON: {exc}") from exc


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def source_contract_sha256() -> str:
    return _sha256(SOURCE_CONTRACT)


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise QualificationError(f"{path} must be an object")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise QualificationError(f"{path} must be an array")
    return value


def _str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QualificationError(f"{path} must be a non-empty string")
    return value.strip()


def _optional_str(value: Any, path: str) -> str | None:
    return None if value is None else _str(value, path)


def _bool(value: Any, path: str) -> bool:
    if type(value) is not bool:
        raise QualificationError(f"{path} must be a boolean")
    return value


def _int(value: Any, path: str) -> int:
    if type(value) is not int or value < 0:
        raise QualificationError(f"{path} must be a non-negative integer")
    return value


def _digest(value: Any, path: str) -> str:
    text = _str(value, path)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise QualificationError(f"{path} must be a lowercase SHA-256 digest")
    return text


def _optional_digest(value: Any, path: str) -> str | None:
    return None if value is None else _digest(value, path)


def _refs(value: Any, path: str) -> list[str]:
    rows = _list(value, path)
    refs = [_str(item, f"{path}[{i}]") for i, item in enumerate(rows)]
    if len(refs) != len(set(refs)):
        raise QualificationError(f"{path} contains duplicate references")
    return refs


def _source_snapshot_match(observed: Any) -> tuple[bool, list[str]]:
    """Compare caller bytes to the retained snapshot; never claim live currentness."""
    obs = _mapping(observed, "source_observation")
    reasons: list[str] = []
    if obs.get("solicitation_number") != SOURCE_CONTRACT["solicitation"]["number"]:
        reasons.append("SOURCE_SNAPSHOT_SOLICITATION_MISMATCH")

    count = _int(obs.get("attachment_count"), "source_observation.attachment_count")
    rows = _list(obs.get("attachments"), "source_observation.attachments")
    if count != len(rows):
        reasons.append("SOURCE_SNAPSHOT_COUNT_INCONSISTENT")

    normalized: list[dict[str, str]] = []
    names: list[str] = []
    for i, raw in enumerate(rows):
        item = _mapping(raw, f"source_observation.attachments[{i}]")
        name = _str(item.get("name"), f"source_observation.attachments[{i}].name")
        posted_at = _str(item.get("posted_at"), f"source_observation.attachments[{i}].posted_at")
        normalized.append({"name": name, "posted_at": posted_at})
        names.append(name)
    if len(names) != len(set(names)):
        reasons.append("SOURCE_SNAPSHOT_DUPLICATE_ATTACHMENT_NAME")
    if count != len(SOURCE_CONTRACT["attachment_manifest"]) or normalized != SOURCE_CONTRACT["attachment_manifest"]:
        reasons.append("SOURCE_SNAPSHOT_ATTACHMENT_MANIFEST_MISMATCH")

    control = _mapping(obs.get("controlling_document"), "source_observation.controlling_document")
    expected = SOURCE_CONTRACT["controlling_document"]
    if control.get("name") != expected["name"] or control.get("posted_at") != expected["posted_at"]:
        reasons.append("SOURCE_SNAPSHOT_CONTROLLING_DOCUMENT_MISMATCH")
    return not reasons, sorted(set(reasons))


def _entities(value: Any) -> list[dict[str, Any]]:
    rows = _list(value, "offeror.similar_healthcare_entities")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, raw in enumerate(rows):
        base = f"offeror.similar_healthcare_entities[{i}]"
        item = _mapping(raw, base)
        name = _str(item.get("entity_name"), f"{base}.entity_name")
        key = name.casefold()
        if key in seen:
            raise QualificationError("offeror.similar_healthcare_entities must be distinct")
        seen.add(key)
        out.append(
            {
                "entity_name": name,
                "as_prime_contractor": _bool(item.get("as_prime_contractor"), f"{base}.as_prime_contractor"),
                "similar_size_scope": _bool(item.get("similar_size_scope"), f"{base}.similar_size_scope"),
                "evidence_refs": _refs(item.get("evidence_refs"), f"{base}.evidence_refs"),
            }
        )
    return out


def _implementations(value: Any) -> list[dict[str, Any]]:
    rows = _list(value, "offeror.adt_implementations")
    out: list[dict[str, Any]] = []
    for i, raw in enumerate(rows):
        base = f"offeror.adt_implementations[{i}]"
        item = _mapping(raw, base)
        out.append(
            {
                "environment": _str(item.get("environment"), f"{base}.environment"),
                "covered_lives": _int(item.get("covered_lives"), f"{base}.covered_lives"),
                "successful": _bool(item.get("successful"), f"{base}.successful"),
                "evidence_refs": _refs(item.get("evidence_refs"), f"{base}.evidence_refs"),
            }
        )
    return out


def _subcontractors(value: Any) -> tuple[int, list[str]]:
    rows = _list(value, "subcontractors")
    reasons: list[str] = []
    for i, raw in enumerate(rows):
        base = f"subcontractors[{i}]"
        item = _mapping(raw, base)
        name = _str(item.get("business_name"), f"{base}.business_name")
        scope = _str(item.get("scope"), f"{base}.scope")
        cost = _int(item.get("cost_share_percent"), f"{base}.cost_share_percent")
        if cost > 100:
            raise QualificationError(f"{base}.cost_share_percent must be <= 100")
        government_access = _bool(item.get("government_information_access"), f"{base}.government_information_access")
        critical = _bool(item.get("critical_services"), f"{base}.critical_services")
        relationship = _bool(item.get("relationship_explained"), f"{base}.relationship_explained")
        qualification_refs = _refs(item.get("qualification_evidence_refs", []), f"{base}.qualification_evidence_refs")

        address = _optional_str(item.get("business_address"), f"{base}.business_address")
        phone = _optional_str(item.get("phone"), f"{base}.phone")
        poc = _optional_str(item.get("point_of_contact"), f"{base}.point_of_contact")
        tin_ref = _optional_str(item.get("taxpayer_id_evidence_ref"), f"{base}.taxpayer_id_evidence_ref")
        tin_sha = _optional_digest(item.get("taxpayer_id_evidence_sha256"), f"{base}.taxpayer_id_evidence_sha256")
        identification_refs = _refs(item.get("identification_evidence_refs", []), f"{base}.identification_evidence_refs")

        must_identify = cost > 10 or government_access or critical
        assembled = all((name, scope, address, phone, poc, tin_ref, tin_sha, identification_refs))
        if must_identify and not assembled:
            reasons.append("SUBCONTRACTOR_IDENTIFICATION_INCOMPLETE")
        elif must_identify:
            # Caller-authored private-evidence references cannot self-clear §5.5.
            reasons.append("SUBCONTRACTOR_IDENTIFICATION_REVIEW_REQUIRED")
        if qualification_refs and not relationship:
            reasons.append("SUBCONTRACTOR_RELATIONSHIP_UNEXPLAINED")
    return len(rows), sorted(set(reasons))


def _security(value: Any) -> tuple[int, list[str]]:
    obj = _mapping(value, "proposal_readiness.security_controls")
    required = SOURCE_CONTRACT["proposal_readiness"]["security_controls"]
    extra = sorted(set(obj) - set(required))
    if extra:
        raise QualificationError(f"unknown security controls: {', '.join(extra)}")
    ready_count = 0
    reasons: list[str] = []
    for key in required:
        base = f"proposal_readiness.security_controls.{key}"
        item = _mapping(obj.get(key), base)
        ready = _bool(item.get("ready"), f"{base}.ready")
        refs = _refs(item.get("evidence_refs"), f"{base}.evidence_refs")
        if ready and refs:
            ready_count += 1
        else:
            reasons.append(f"READINESS_SECURITY_{key.upper()}")
    return ready_count, reasons


def compile_qualification(packet: Any, *, source_observation: Any) -> dict[str, Any]:
    packet = _mapping(packet, "packet")
    route = _str(packet.get("route"), "packet.route")
    if route not in ROUTES:
        raise QualificationError(f"packet.route must be one of {sorted(ROUTES)}")

    offeror = _mapping(packet.get("offeror"), "packet.offeror")
    legal_name = _str(offeror.get("legal_name"), "offeror.legal_name")
    prime_months = _int(offeror.get("prime_contractor_months"), "offeror.prime_contractor_months")
    prime_refs = _refs(offeror.get("prime_experience_evidence_refs"), "offeror.prime_experience_evidence_refs")
    adt_months = _int(offeror.get("realtime_adt_months"), "offeror.realtime_adt_months")
    health_adt_months = _int(offeror.get("healthcare_adt_months"), "offeror.healthcare_adt_months")
    adt_refs = _refs(offeror.get("adt_experience_evidence_refs"), "offeror.adt_experience_evidence_refs")
    entities = _entities(offeror.get("similar_healthcare_entities"))
    implementations = _implementations(offeror.get("adt_implementations"))
    subcontractor_count, subcontractor_reasons = _subcontractors(packet.get("subcontractors"))

    readiness = _mapping(packet.get("proposal_readiness"), "packet.proposal_readiness")
    pm_mcde = _int(readiness.get("project_manager_mcde_months"), "proposal_readiness.project_manager_mcde_months")
    pm_health = _int(readiness.get("project_manager_healthcare_months"), "proposal_readiness.project_manager_healthcare_months")
    pm_refs = _refs(readiness.get("project_manager_evidence_refs"), "proposal_readiness.project_manager_evidence_refs")
    security_ready, security_reasons = _security(readiness.get("security_controls"))

    snapshot_match, source_reasons = _source_snapshot_match(source_observation)
    minimums = SOURCE_CONTRACT["mandatory_minimums"]
    qualifying_entities = [
        row for row in entities
        if row["as_prime_contractor"] and row["similar_size_scope"] and row["evidence_refs"]
    ]
    million_life = [
        row for row in implementations
        if row["successful"]
        and row["covered_lives"] >= minimums["successful_adt_min_lives"]
        and row["evidence_refs"]
    ]

    mandatory: list[str] = []
    if prime_months < minimums["prime_contractor_months"] or not prime_refs:
        mandatory.append("MANDATORY_PRIME_CONTRACTOR_EXPERIENCE")
    if len(qualifying_entities) < minimums["similar_size_scope_healthcare_entities"]:
        mandatory.append("MANDATORY_THREE_SIMILAR_HEALTHCARE_ENTITIES")
    if adt_months < minimums["realtime_adt_months"] or not adt_refs:
        mandatory.append("MANDATORY_REALTIME_ADT_EXPERIENCE")
    if health_adt_months < minimums["healthcare_adt_months"] or not adt_refs:
        mandatory.append("MANDATORY_HEALTHCARE_ADT_EXPERIENCE")
    if not million_life:
        mandatory.append("MANDATORY_SUCCESSFUL_ONE_MILLION_LIVES_ADT")

    readiness_reasons = list(subcontractor_reasons) + list(security_reasons)
    if pm_mcde < SOURCE_CONTRACT["proposal_readiness"]["project_manager_mcde_months"] or not pm_refs:
        readiness_reasons.append("READINESS_PROJECT_MANAGER_MCDE_EXPERIENCE")
    if pm_health < SOURCE_CONTRACT["proposal_readiness"]["project_manager_healthcare_months"] or not pm_refs:
        readiness_reasons.append("READINESS_PROJECT_MANAGER_HEALTHCARE_EXPERIENCE")

    teaming_prime: str | None = None
    teaming_candidate = False
    prime_evidence_ready = False
    if source_reasons:
        decision, reasons = "HOLD_SOURCE_SNAPSHOT_MISMATCH", source_reasons
    elif route == "prime_offeror" and mandatory:
        decision, reasons = "SNAPSHOT_MANDATORY_EVIDENCE_GAP", mandatory
    elif route == "prime_offeror" and readiness_reasons:
        decision, reasons = "SNAPSHOT_PROPOSAL_EVIDENCE_GAP", readiness_reasons
    elif route == "prime_offeror":
        decision = "PRIME_EVIDENCE_READY_FOR_LIVE_SOURCE_REVIEW"
        reasons = ["LIVE_SOURCE_REVIEW_REQUIRED"]
        prime_evidence_ready = True
    else:
        teaming = _mapping(packet.get("teaming"), "packet.teaming")
        teaming_prime = _str(teaming.get("prospective_prime_legal_name"), "teaming.prospective_prime_legal_name")
        relationship = _bool(teaming.get("relationship_explained"), "teaming.relationship_explained")
        review_refs = _refs(teaming.get("prime_review_evidence_refs"), "teaming.prime_review_evidence_refs")
        reasons = list(subcontractor_reasons) + ["QUALIFIED_PRIME_REVIEW_REQUIRED"]
        if not relationship or not review_refs:
            reasons.append("TEAMING_PRIME_EVIDENCE_OR_RELATIONSHIP_INCOMPLETE")
        teaming_candidate = relationship and bool(review_refs) and not subcontractor_reasons
        decision = "TEAMING_DISCOVERY"

    result = {
        "schema_version": SCHEMA_VERSION,
        "operation_key": OPERATION_KEY,
        "route": route,
        "offeror_legal_name": legal_name,
        "teaming_prime_legal_name": teaming_prime,
        "source_contract_sha256": source_contract_sha256(),
        "source_observation_sha256": _sha256(source_observation),
        "packet_sha256": _sha256(packet),
        "source_snapshot_match": snapshot_match,
        "source_current": False,
        "live_source_review_required": True,
        "deadline_status": "NOT_EVALUATED",
        "decision": decision,
        "reasons": sorted(set(reasons)),
        "prime_qualification_candidate": False,
        "prime_evidence_ready": prime_evidence_ready,
        "teaming_evidence_candidate": teaming_candidate,
        "submission_authorized": False,
        "authority": dict(SOURCE_CONTRACT["authority"]),
        "evidence_summary": {
            "qualifying_similar_healthcare_entities": len(qualifying_entities),
            "successful_million_life_adt_implementations": len(million_life),
            "subcontractor_count": subcontractor_count,
            "security_controls_ready": security_ready,
            "security_controls_required": len(SOURCE_CONTRACT["proposal_readiness"]["security_controls"]),
        },
    }
    result["receipt_sha256"] = _sha256(result)
    return result


def verify_receipt(packet: Any, *, source_observation: Any, receipt: Any) -> bool:
    try:
        return _canonical(compile_qualification(packet, source_observation=source_observation)) == _canonical(receipt)
    except (QualificationError, TypeError, ValueError):
        return False
