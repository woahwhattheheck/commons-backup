from __future__ import annotations

from typing import Any

from .constants import CATEGORIES, FINANCIAL_CLASSES, INPUT_KEYS, INPUT_SCHEMA, REQ_KEYS, STAGES
from .evidence_model import _normalize_evidence
from .strict import RegistryError, _parse_utc, _require_enum, _require_exact_keys, _require_id, canonical_json

def _normalize_requirement(item: Any, index: int) -> dict[str, Any]:
    where = f"requirements[{index}]"
    item = _require_exact_keys(item, REQ_KEYS, where)
    category = _require_enum(item["category"], CATEGORIES, f"{where}.category")
    fin = item["required_financial_class"]
    if category == "FINANCIAL_STATEMENT":
        fin = _require_enum(fin, FINANCIAL_CLASSES, f"{where}.required_financial_class")
    elif fin is not None:
        raise RegistryError(f"{where}:FINANCIAL_CLASS_ONLY_FOR_FINANCIAL")
    subject_id = _require_id(item["subject_id"], f"{where}.subject_id", nullable=True)
    if category.startswith("REFERENCE_") and subject_id is None:
        raise RegistryError(f"{where}:REFERENCE_REQUIRES_SUBJECT")
    if category in {"STAFF_CV", "STAFF_AVAILABILITY"} and subject_id is None:
        raise RegistryError(f"{where}:STAFF_REQUIRES_SUBJECT")
    return {
        "id": _require_id(item["id"], f"{where}.id"),
        "category": category,
        "stage": _require_enum(item["stage"], STAGES, f"{where}.stage"),
        "subject_id": subject_id,
        "opportunity_id": _require_id(item["opportunity_id"], f"{where}.opportunity_id"),
        "required_financial_class": fin,
    }


def normalize_input(payload: Any) -> dict[str, Any]:
    payload = _require_exact_keys(payload, INPUT_KEYS, "root")
    if payload["schema"] != INPUT_SCHEMA:
        raise RegistryError("root.schema:UNSUPPORTED")
    if not isinstance(payload["evidence"], list) or len(payload["evidence"]) > 4096:
        raise RegistryError("root.evidence:EXPECTED_BOUNDED_LIST")
    if not isinstance(payload["requirements"], list) or not payload["requirements"] or len(payload["requirements"]) > 2048:
        raise RegistryError("root.requirements:EXPECTED_NONEMPTY_BOUNDED_LIST")
    as_of = _parse_utc(payload["as_of"], "root.as_of")
    assert as_of is not None
    evidence = [_normalize_evidence(item, i) for i, item in enumerate(payload["evidence"])]
    requirements = [_normalize_requirement(item, i) for i, item in enumerate(payload["requirements"])]
    req_ids = [r["id"] for r in requirements]
    if len(req_ids) != len(set(req_ids)):
        raise RegistryError("root.requirements:DUPLICATE_ID")
    normalized = {
        "schema": INPUT_SCHEMA,
        "generation_id": _require_id(payload["generation_id"], "root.generation_id"),
        "entity_id": _require_id(payload["entity_id"], "root.entity_id"),
        "as_of": payload["as_of"],
        "evidence": sorted(evidence, key=lambda x: (x["id"], canonical_json(x))),
        "requirements": sorted(requirements, key=lambda x: x["id"]),
    }
    return normalized
