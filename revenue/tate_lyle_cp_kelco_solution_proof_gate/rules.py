from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from .codec import GateInputError, RECORD_SCHEMA, REFERENCE_SCHEMA, _dict, _hex64, _keys, _str

HOLD_SPEC = "SPEC_REVISION_MISMATCH"
HOLD_REGION = "REGION_USE_CLAIM_MISMATCH"
HOLD_LEGACY = "LEGACY_MAPPING_BREAK"
HOLD_STABILITY = "PILOT_STABILITY_INCOMPLETE"
HOLD_OWNER = "OWNER_VERSION_UNBOUND"

_RECORD_FIELDS = {
    "schema", "record_id", "code", "ingredient_id", "spec_revision", "region", "use_ref", "use_level",
    "claim_ref", "allergen_label_hash", "legacy_code", "stability_result", "stability_protocol_version",
    "commercial_owner", "science_owner", "owner_version",
}
_REFERENCE_FIELDS = {
    "record_id", "code", "ingredient_id", "approved_spec_revision", "approved_region", "use_ref", "max_use_level",
    "approved_claim_ref", "legacy_code", "target_code", "mapping_version", "stability_protocol_version",
    "accepted_stability_result", "commercial_owner", "science_owner", "owner_version",
}


def _decimal_text(value: Any, name: str) -> str:
    text = _str(value, name)
    if text.startswith(("+", "-")) or "e" in text.lower():
        raise GateInputError(f"{name} must be plain non-negative decimal text")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise GateInputError(f"{name} must be decimal text") from exc
    if not number.is_finite() or number < 0:
        raise GateInputError(f"{name} must be finite non-negative decimal text")
    return text


def parse_record(raw: Any) -> dict[str, Any]:
    obj = _dict(raw, "record")
    _keys(obj, _RECORD_FIELDS, "record")
    if obj["schema"] != RECORD_SCHEMA:
        raise GateInputError("unsupported record schema")
    return {
        "record_id": _str(obj["record_id"], "record.record_id"),
        "code": _str(obj["code"], "record.code"),
        "ingredient_id": _str(obj["ingredient_id"], "record.ingredient_id"),
        "spec_revision": _str(obj["spec_revision"], "record.spec_revision"),
        "region": _str(obj["region"], "record.region"),
        "use_ref": _str(obj["use_ref"], "record.use_ref"),
        "use_level": _decimal_text(obj["use_level"], "record.use_level"),
        "claim_ref": _str(obj["claim_ref"], "record.claim_ref"),
        "allergen_label_hash": _hex64(obj["allergen_label_hash"], "record.allergen_label_hash"),
        "legacy_code": _str(obj["legacy_code"], "record.legacy_code"),
        "stability_result": _str(obj["stability_result"], "record.stability_result"),
        "stability_protocol_version": _str(obj["stability_protocol_version"], "record.stability_protocol_version"),
        "commercial_owner": _str(obj["commercial_owner"], "record.commercial_owner"),
        "science_owner": _str(obj["science_owner"], "record.science_owner"),
        "owner_version": _str(obj["owner_version"], "record.owner_version"),
    }


def parse_reference_set(raw: Any) -> dict[str, Any]:
    obj = _dict(raw, "references")
    _keys(obj, {"schema", "generation", "records"}, "references")
    if obj["schema"] != REFERENCE_SCHEMA:
        raise GateInputError("unsupported reference schema")
    generation = _str(obj["generation"], "references.generation")
    rows = obj["records"]
    if type(rows) is not list or not 1 <= len(rows) <= 500:
        raise GateInputError("references.records cardinality is out of bounds")
    by_id: dict[str, dict[str, Any]] = {}
    for index, raw_row in enumerate(rows):
        row = _dict(raw_row, f"references.records[{index}]")
        _keys(row, _REFERENCE_FIELDS, f"references.records[{index}]")
        parsed = {
            "record_id": _str(row["record_id"], "reference.record_id"),
            "code": _str(row["code"], "reference.code"),
            "ingredient_id": _str(row["ingredient_id"], "reference.ingredient_id"),
            "approved_spec_revision": _str(row["approved_spec_revision"], "reference.approved_spec_revision"),
            "approved_region": _str(row["approved_region"], "reference.approved_region"),
            "use_ref": _str(row["use_ref"], "reference.use_ref"),
            "max_use_level": _decimal_text(row["max_use_level"], "reference.max_use_level"),
            "approved_claim_ref": _str(row["approved_claim_ref"], "reference.approved_claim_ref"),
            "legacy_code": _str(row["legacy_code"], "reference.legacy_code"),
            "target_code": _str(row["target_code"], "reference.target_code"),
            "mapping_version": _str(row["mapping_version"], "reference.mapping_version"),
            "stability_protocol_version": _str(row["stability_protocol_version"], "reference.stability_protocol_version"),
            "accepted_stability_result": _str(row["accepted_stability_result"], "reference.accepted_stability_result"),
            "commercial_owner": _str(row["commercial_owner"], "reference.commercial_owner"),
            "science_owner": _str(row["science_owner"], "reference.science_owner"),
            "owner_version": _str(row["owner_version"], "reference.owner_version"),
        }
        rid = parsed["record_id"]
        if rid in by_id:
            raise GateInputError(f"duplicate reference record_id: {rid}")
        by_id[rid] = parsed
    return {"schema": REFERENCE_SCHEMA, "generation": generation, "records": [by_id[rid] for rid in sorted(by_id)]}


def classify(record: dict[str, Any], reference: dict[str, Any]) -> tuple[str, list[str]]:
    if record["record_id"] != reference["record_id"]:
        raise GateInputError("reference record_id mismatch")
    if record["code"] != reference["code"] or record["ingredient_id"] != reference["ingredient_id"]:
        raise GateInputError("reference identity mismatch")

    holds: list[str] = []
    if record["spec_revision"] != reference["approved_spec_revision"]:
        holds.append(HOLD_SPEC)
    if (
        record["region"] != reference["approved_region"]
        or record["use_ref"] != reference["use_ref"]
        or Decimal(record["use_level"]) > Decimal(reference["max_use_level"])
        or record["claim_ref"] != reference["approved_claim_ref"]
    ):
        holds.append(HOLD_REGION)
    if (
        record["legacy_code"] != reference["legacy_code"]
        or record["code"] != reference["target_code"]
    ):
        holds.append(HOLD_LEGACY)
    if (
        record["stability_result"] != reference["accepted_stability_result"]
        or record["stability_protocol_version"] != reference["stability_protocol_version"]
    ):
        holds.append(HOLD_STABILITY)
    if (
        record["commercial_owner"] != reference["commercial_owner"]
        or record["science_owner"] != reference["science_owner"]
        or record["owner_version"] != reference["owner_version"]
    ):
        holds.append(HOLD_OWNER)
    return ("HOLD" if holds else "PASS"), holds
