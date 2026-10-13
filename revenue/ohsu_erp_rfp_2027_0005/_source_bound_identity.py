from __future__ import annotations

from typing import Any

from ._source_bound_common import _require_keys, _require_sha256
from ._source_bound_constants import (
    CONTROLLING_PACK_SHA256,
    PROFESSIONAL_SERVICES_CONTRACT_SHA256,
    RESPONDENT_REF,
    SUPPLIER_QA_SHA256,
    ContractError,
    _REQUIRED_SET,
)

def _normalize_source_binding(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ContractError("facts.source_binding must be object")
    _require_keys(
        value,
        exact={
            "controlling_pack_sha256",
            "supplier_qa_sha256",
            "professional_services_contract_sha256",
        },
        where="facts.source_binding",
    )
    pack = _require_sha256(value["controlling_pack_sha256"], "facts.source_binding.controlling_pack_sha256")
    qa = _require_sha256(value["supplier_qa_sha256"], "facts.source_binding.supplier_qa_sha256")
    psc = _require_sha256(
        value["professional_services_contract_sha256"],
        "facts.source_binding.professional_services_contract_sha256",
    )
    if pack != CONTROLLING_PACK_SHA256:
        raise ContractError("controlling pack digest differs from received source binding")
    if qa != SUPPLIER_QA_SHA256:
        raise ContractError("supplier Q&A digest differs from received source binding")
    if psc != PROFESSIONAL_SERVICES_CONTRACT_SHA256:
        raise ContractError("professional services contract digest differs from received source binding")
    return {
        "controlling_pack_sha256": pack,
        "supplier_qa_sha256": qa,
        "professional_services_contract_sha256": psc,
    }

def _normalize_commitment(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError("facts.teaming_commitment must be object")
    _require_keys(
        value,
        exact={"status", "partner_ref", "evidence_sha256"},
        where="facts.teaming_commitment",
    )
    status = value["status"]
    if status not in {"UNCONFIRMED", "CONFIRMED"}:
        raise ContractError("facts.teaming_commitment.status invalid")
    partner_ref = value["partner_ref"]
    evidence = _require_sha256(
        value["evidence_sha256"],
        "facts.teaming_commitment.evidence_sha256",
        allow_none=True,
    )
    if status == "UNCONFIRMED":
        if partner_ref is not None or evidence is not None:
            raise ContractError("unconfirmed teaming commitment cannot carry partner identity or evidence")
        return {"status": status, "partner_ref": None, "evidence_sha256": None}
    if not isinstance(partner_ref, str) or not partner_ref.strip() or len(partner_ref) > 128:
        raise ContractError("confirmed teaming commitment requires bounded partner_ref")
    normalized_ref = partner_ref.strip()
    if normalized_ref == RESPONDENT_REF:
        raise ContractError("confirmed teaming partner must differ from canonical respondent")
    if evidence is None:
        raise ContractError("confirmed teaming commitment requires evidence_sha256")
    return {"status": status, "partner_ref": normalized_ref, "evidence_sha256": evidence}

def _normalize_requirements(value: Any, *, route: str, commitment: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ContractError("facts.requirements must be list")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        where = f"facts.requirements[{index}]"
        if not isinstance(raw, dict):
            raise ContractError(f"{where} must be object")
        _require_keys(
            raw,
            exact={"requirement_id", "state", "basis", "entity_ref", "evidence_sha256"},
            where=where,
        )
        rid = raw["requirement_id"]
        if rid not in _REQUIRED_SET:
            raise ContractError(f"{where}.requirement_id is not a normalized minimum gate")
        if rid in seen:
            raise ContractError(f"duplicate requirement_id: {rid}")
        seen.add(rid)

        state = raw["state"]
        if state not in {"SATISFIED", "MISSING", "UNKNOWN"}:
            raise ContractError(f"{where}.state invalid")
        basis = raw["basis"]
        if basis not in {"NONE", "RESPONDENT", "NAMED_COMMITTED_TEAM_PARTNER"}:
            raise ContractError(f"{where}.basis invalid")
        entity_ref = raw["entity_ref"]
        evidence = _require_sha256(raw["evidence_sha256"], f"{where}.evidence_sha256", allow_none=True)

        if state != "SATISFIED":
            if basis != "NONE" or entity_ref is not None or evidence is not None:
                raise ContractError(f"{where} non-SATISFIED gate cannot carry qualification evidence")
        else:
            if basis == "NONE" or evidence is None:
                raise ContractError(f"{where} SATISFIED requires explicit basis and evidence")
            if not isinstance(entity_ref, str) or not entity_ref.strip() or len(entity_ref) > 128:
                raise ContractError(f"{where} SATISFIED requires bounded entity_ref")
            entity_ref = entity_ref.strip()
            if basis == "NAMED_COMMITTED_TEAM_PARTNER":
                if route != "TEAMING":
                    raise ContractError("team-partner qualification basis is forbidden outside TEAMING route")
                if commitment["status"] != "CONFIRMED":
                    raise ContractError("unconfirmed outreach target contributes zero qualifications")
                if entity_ref != commitment["partner_ref"]:
                    raise ContractError("team qualification entity does not match confirmed partner")
            elif basis == "RESPONDENT":
                if entity_ref != RESPONDENT_REF:
                    raise ContractError("RESPONDENT qualification entity must match canonical respondent")

        out.append({
            "requirement_id": rid,
            "state": state,
            "basis": basis,
            "entity_ref": entity_ref,
            "evidence_sha256": evidence,
        })

    if seen != _REQUIRED_SET:
        raise ContractError(
            f"facts.requirements must cover exact normalized gate set; missing={sorted(_REQUIRED_SET - seen)}"
        )
    out.sort(key=lambda row: row["requirement_id"])
    return out
