from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

SCHEMA = "pci.fill-finish-batch-readiness/v2"
DECISION_SCHEMA = "pci.fill-finish-batch-readiness-decision/v2"
DEFAULT_MAX_DECISION_AGE_SECONDS = 24 * 60 * 60

_REASON_ORDER = (
    "TRUSTED_DEFINITION_MISMATCH",
    "RECIPE_MISMATCH",
    "MATERIAL_COVERAGE_MISMATCH",
    "MATERIAL_UNRELEASED",
    "EQUIPMENT_COVERAGE_MISMATCH",
    "CALIBRATION_EXPIRED",
    "ENVIRONMENT_HOLD",
    "ENVIRONMENT_STALE_FOR_SLOT",
    "INSPECTION_LINEAGE_MISMATCH",
    "BOM_MISMATCH",
)
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,95}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class ReadinessError(ValueError):
    def __init__(self, code: str, detail: str | None = None):
        message = code if detail is None else f"{code}: {detail}"
        super().__init__(message)
        self.code = code
        self.detail = detail or code


def _fail(code: str, detail: str | None = None) -> None:
    raise ReadinessError(code, detail)


def _obj(value: Any, code: str) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(code)
    return value


def _exact_keys(value: dict[str, Any], keys: tuple[str, ...], code: str) -> None:
    if set(value) != set(keys):
        _fail(code)


def _identifier(value: Any, field: str) -> str:
    if type(value) is not str or not _ID_RE.fullmatch(value):
        _fail("INVALID_IDENTIFIER", field)
    return value


def _digest(value: Any, field: str) -> str:
    if type(value) is not str or not _DIGEST_RE.fullmatch(value):
        _fail("INVALID_DIGEST", field)
    return value


def _bool(value: Any, field: str) -> bool:
    if type(value) is not bool:
        _fail("BOOLEAN_REQUIRED", field)
    return value


def _timestamp(value: Any, field: str) -> tuple[str, datetime]:
    if type(value) is not str or not _TS_RE.fullmatch(value):
        _fail("NONCANONICAL_TIMESTAMP", field)
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _fail("INVALID_TIMESTAMP", field)
    if dt.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _fail("NONCANONICAL_TIMESTAMP", field)
    return value, dt


def _evidence_time(value: Any, field: str, trusted_as_of_dt: datetime) -> str:
    text, dt = _timestamp(value, field)
    if dt > trusted_as_of_dt:
        _fail("EVIDENCE_AFTER_TRUSTED_AS_OF", field)
    return text


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ReadinessError("NONCANONICAL_VALUE", str(exc)) from exc


def sha256(value: Any) -> str:
    payload = value if isinstance(value, (bytes, bytearray)) else canonical_json(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalize_unique_ids(raw: Any, field: str) -> list[str]:
    if type(raw) is not list or not raw:
        _fail("RECIPE_REQUIREMENTS_REQUIRED", field)
    values = [_identifier(value, f"{field}[{i}]") for i, value in enumerate(raw)]
    if len(set(values)) != len(values):
        _fail("DUPLICATE_RECIPE_REQUIREMENT", field)
    return sorted(values)


def _normalize_pair(raw: Any, field: str) -> dict[str, str]:
    obj = _obj(raw, f"{field.upper()}_OBJECT_REQUIRED")
    _exact_keys(obj, ("component_id", "version"), f"{field.upper()}_FIELDS")
    return {
        "component_id": _identifier(obj["component_id"], f"{field}.component_id"),
        "version": _identifier(obj["version"], f"{field}.version"),
    }


def normalize_trusted_definition(raw: Any) -> dict[str, Any]:
    definition = _obj(copy.deepcopy(raw), "TRUSTED_DEFINITION_REQUIRED")
    _exact_keys(
        definition,
        (
            "recipe_id",
            "version",
            "approved_digest",
            "required_material_components",
            "required_equipment_ids",
            "required_bom",
        ),
        "TRUSTED_DEFINITION_FIELDS",
    )
    required_bom_raw = definition["required_bom"]
    if type(required_bom_raw) is not list or not required_bom_raw:
        _fail("TRUSTED_BOM_REQUIRED")
    required_bom = [_normalize_pair(value, f"trusted_definition.required_bom[{i}]") for i, value in enumerate(required_bom_raw)]
    bom_keys = [(value["component_id"], value["version"]) for value in required_bom]
    if len(set(bom_keys)) != len(bom_keys):
        _fail("DUPLICATE_TRUSTED_BOM_COMPONENT")
    required_bom.sort(key=lambda value: (value["component_id"], value["version"]))
    return {
        "recipe_id": _identifier(definition["recipe_id"], "trusted_definition.recipe_id"),
        "version": _identifier(definition["version"], "trusted_definition.version"),
        "approved_digest": _digest(definition["approved_digest"], "trusted_definition.approved_digest"),
        "required_material_components": _normalize_unique_ids(
            definition["required_material_components"], "trusted_definition.required_material_components"
        ),
        "required_equipment_ids": _normalize_unique_ids(
            definition["required_equipment_ids"], "trusted_definition.required_equipment_ids"
        ),
        "required_bom": required_bom,
    }


def normalize_packet(raw: Any, *, trusted_as_of: str) -> dict[str, Any]:
    trusted_as_of_s, trusted_as_of_dt = _timestamp(trusted_as_of, "trusted_as_of")
    packet = _obj(copy.deepcopy(raw), "PACKET_REQUIRED")
    _exact_keys(
        packet,
        (
            "schema_version",
            "packet_id",
            "batch_id",
            "planned_slot_at",
            "recipe",
            "materials",
            "equipment",
            "environment",
            "fill_inspection",
            "bom",
        ),
        "PACKET_FIELDS",
    )
    if packet["schema_version"] != SCHEMA:
        _fail("SCHEMA_MISMATCH")
    packet_id = _identifier(packet["packet_id"], "packet_id")
    batch_id = _identifier(packet["batch_id"], "batch_id")
    planned_slot_at, slot_dt = _timestamp(packet["planned_slot_at"], "planned_slot_at")
    if trusted_as_of_dt > slot_dt:
        _fail("TRUSTED_AS_OF_AFTER_PLANNED_SLOT")

    recipe = _obj(packet["recipe"], "RECIPE_REQUIRED")
    _exact_keys(
        recipe,
        (
            "recipe_id",
            "version",
            "approved",
            "approved_digest",
            "observed_at",
            "scheduled_recipe_id",
            "scheduled_version",
            "required_material_components",
            "required_equipment_ids",
        ),
        "RECIPE_FIELDS",
    )
    recipe_n = {
        "recipe_id": _identifier(recipe["recipe_id"], "recipe.recipe_id"),
        "version": _identifier(recipe["version"], "recipe.version"),
        "approved": _bool(recipe["approved"], "recipe.approved"),
        "approved_digest": _digest(recipe["approved_digest"], "recipe.approved_digest"),
        "observed_at": _evidence_time(recipe["observed_at"], "recipe.observed_at", trusted_as_of_dt),
        "scheduled_recipe_id": _identifier(recipe["scheduled_recipe_id"], "recipe.scheduled_recipe_id"),
        "scheduled_version": _identifier(recipe["scheduled_version"], "recipe.scheduled_version"),
        "required_material_components": _normalize_unique_ids(
            recipe["required_material_components"], "recipe.required_material_components"
        ),
        "required_equipment_ids": _normalize_unique_ids(
            recipe["required_equipment_ids"], "recipe.required_equipment_ids"
        ),
    }

    materials = packet["materials"]
    if type(materials) is not list or not materials:
        _fail("MATERIALS_REQUIRED")
    materials_n: list[dict[str, Any]] = []
    material_ids: set[str] = set()
    for i, raw_item in enumerate(materials):
        item = _obj(raw_item, "MATERIAL_OBJECT_REQUIRED")
        _exact_keys(item, ("lot_id", "component", "released", "release_digest", "observed_at"), "MATERIAL_FIELDS")
        lot_id = _identifier(item["lot_id"], f"materials[{i}].lot_id")
        if lot_id in material_ids:
            _fail("DUPLICATE_MATERIAL_LOT", lot_id)
        material_ids.add(lot_id)
        materials_n.append(
            {
                "lot_id": lot_id,
                "component": _identifier(item["component"], f"materials[{i}].component"),
                "released": _bool(item["released"], f"materials[{i}].released"),
                "release_digest": _digest(item["release_digest"], f"materials[{i}].release_digest"),
                "observed_at": _evidence_time(item["observed_at"], f"materials[{i}].observed_at", trusted_as_of_dt),
            }
        )
    materials_n.sort(key=lambda x: (x["component"], x["lot_id"]))

    equipment = packet["equipment"]
    if type(equipment) is not list or not equipment:
        _fail("EQUIPMENT_REQUIRED")
    equipment_n: list[dict[str, Any]] = []
    equipment_ids: set[str] = set()
    for i, raw_item in enumerate(equipment):
        item = _obj(raw_item, "EQUIPMENT_OBJECT_REQUIRED")
        _exact_keys(
            item,
            ("equipment_id", "calibration_valid_until", "calibration_digest", "observed_at"),
            "EQUIPMENT_FIELDS",
        )
        equipment_id = _identifier(item["equipment_id"], f"equipment[{i}].equipment_id")
        if equipment_id in equipment_ids:
            _fail("DUPLICATE_EQUIPMENT", equipment_id)
        equipment_ids.add(equipment_id)
        valid_until, _ = _timestamp(item["calibration_valid_until"], f"equipment[{i}].calibration_valid_until")
        equipment_n.append(
            {
                "equipment_id": equipment_id,
                "calibration_valid_until": valid_until,
                "calibration_digest": _digest(item["calibration_digest"], f"equipment[{i}].calibration_digest"),
                "observed_at": _evidence_time(item["observed_at"], f"equipment[{i}].observed_at", trusted_as_of_dt),
            }
        )
    equipment_n.sort(key=lambda x: x["equipment_id"])

    environment = _obj(packet["environment"], "ENVIRONMENT_REQUIRED")
    _exact_keys(
        environment,
        ("isolator_state", "em_state", "captured_at", "valid_until", "evidence_digest"),
        "ENVIRONMENT_FIELDS",
    )
    captured_at = _evidence_time(environment["captured_at"], "environment.captured_at", trusted_as_of_dt)
    _, captured_dt = _timestamp(captured_at, "environment.captured_at")
    valid_until, valid_until_dt = _timestamp(environment["valid_until"], "environment.valid_until")
    if valid_until_dt < captured_dt:
        _fail("ENVIRONMENT_VALIDITY_BEFORE_CAPTURE")
    environment_n = {
        "isolator_state": _identifier(environment["isolator_state"], "environment.isolator_state"),
        "em_state": _identifier(environment["em_state"], "environment.em_state"),
        "captured_at": captured_at,
        "valid_until": valid_until,
        "evidence_digest": _digest(environment["evidence_digest"], "environment.evidence_digest"),
    }

    inspection = _obj(packet["fill_inspection"], "FILL_INSPECTION_REQUIRED")
    _exact_keys(
        inspection,
        (
            "fill_weight_batch_id",
            "inspection_batch_id",
            "recipe_digest",
            "fill_weight_digest",
            "inspection_digest",
            "observed_at",
        ),
        "FILL_INSPECTION_FIELDS",
    )
    inspection_n = {
        "fill_weight_batch_id": _identifier(inspection["fill_weight_batch_id"], "fill_inspection.fill_weight_batch_id"),
        "inspection_batch_id": _identifier(inspection["inspection_batch_id"], "fill_inspection.inspection_batch_id"),
        "recipe_digest": _digest(inspection["recipe_digest"], "fill_inspection.recipe_digest"),
        "fill_weight_digest": _digest(inspection["fill_weight_digest"], "fill_inspection.fill_weight_digest"),
        "inspection_digest": _digest(inspection["inspection_digest"], "fill_inspection.inspection_digest"),
        "observed_at": _evidence_time(inspection["observed_at"], "fill_inspection.observed_at", trusted_as_of_dt),
    }

    bom = _obj(packet["bom"], "BOM_REQUIRED")
    _exact_keys(bom, ("required", "staged", "evidence_digest", "observed_at"), "BOM_FIELDS")
    required_raw, staged_raw = bom["required"], bom["staged"]
    if type(required_raw) is not list or not required_raw or type(staged_raw) is not list or not staged_raw:
        _fail("BOM_COMPONENTS_REQUIRED")
    required_n = [_normalize_pair(v, f"bom.required[{i}]") for i, v in enumerate(required_raw)]
    staged_n = [_normalize_pair(v, f"bom.staged[{i}]") for i, v in enumerate(staged_raw)]
    for label, values in (("required", required_n), ("staged", staged_n)):
        keys = [(v["component_id"], v["version"]) for v in values]
        if len(set(keys)) != len(keys):
            _fail("DUPLICATE_BOM_COMPONENT", label)
        values.sort(key=lambda x: (x["component_id"], x["version"]))
    bom_n = {
        "required": required_n,
        "staged": staged_n,
        "evidence_digest": _digest(bom["evidence_digest"], "bom.evidence_digest"),
        "observed_at": _evidence_time(bom["observed_at"], "bom.observed_at", trusted_as_of_dt),
    }

    return {
        "schema_version": SCHEMA,
        "packet_id": packet_id,
        "batch_id": batch_id,
        "planned_slot_at": planned_slot_at,
        "recipe": recipe_n,
        "materials": materials_n,
        "equipment": equipment_n,
        "environment": environment_n,
        "fill_inspection": inspection_n,
        "bom": bom_n,
    }


def evaluate(raw_packet: Any, *, trusted_as_of: str, trusted_definition: Any) -> dict[str, Any]:
    trusted_as_of_s, _ = _timestamp(trusted_as_of, "trusted_as_of")
    definition = normalize_trusted_definition(trusted_definition)
    packet = normalize_packet(raw_packet, trusted_as_of=trusted_as_of_s)
    slot_dt = _timestamp(packet["planned_slot_at"], "planned_slot_at")[1]
    reasons: list[str] = []

    recipe = packet["recipe"]
    definition_projection = {
        "recipe_id": recipe["recipe_id"],
        "version": recipe["version"],
        "approved_digest": recipe["approved_digest"],
        "required_material_components": recipe["required_material_components"],
        "required_equipment_ids": recipe["required_equipment_ids"],
        "required_bom": packet["bom"]["required"],
    }
    if canonical_json(definition_projection) != canonical_json(definition):
        reasons.append("TRUSTED_DEFINITION_MISMATCH")
    if (
        not recipe["approved"]
        or recipe["scheduled_recipe_id"] != definition["recipe_id"]
        or recipe["scheduled_version"] != definition["version"]
    ):
        reasons.append("RECIPE_MISMATCH")

    required_materials = set(definition["required_material_components"])
    observed_materials = {item["component"] for item in packet["materials"]}
    if observed_materials != required_materials:
        reasons.append("MATERIAL_COVERAGE_MISMATCH")
    if any(not item["released"] for item in packet["materials"]):
        reasons.append("MATERIAL_UNRELEASED")

    required_equipment = set(definition["required_equipment_ids"])
    observed_equipment = {item["equipment_id"] for item in packet["equipment"]}
    if observed_equipment != required_equipment:
        reasons.append("EQUIPMENT_COVERAGE_MISMATCH")
    for item in packet["equipment"]:
        if _timestamp(item["calibration_valid_until"], "calibration_valid_until")[1] < slot_dt:
            reasons.append("CALIBRATION_EXPIRED")
            break

    environment = packet["environment"]
    if environment["isolator_state"] != "READY" or environment["em_state"] != "PASS":
        reasons.append("ENVIRONMENT_HOLD")
    if _timestamp(environment["valid_until"], "environment.valid_until")[1] < slot_dt:
        reasons.append("ENVIRONMENT_STALE_FOR_SLOT")

    inspection = packet["fill_inspection"]
    if (
        inspection["fill_weight_batch_id"] != packet["batch_id"]
        or inspection["inspection_batch_id"] != packet["batch_id"]
        or inspection["recipe_digest"] != definition["approved_digest"]
    ):
        reasons.append("INSPECTION_LINEAGE_MISMATCH")

    required_bom = [(x["component_id"], x["version"]) for x in definition["required_bom"]]
    packet_required_bom = [(x["component_id"], x["version"]) for x in packet["bom"]["required"]]
    staged_bom = [(x["component_id"], x["version"]) for x in packet["bom"]["staged"]]
    if packet_required_bom != required_bom or staged_bom != required_bom:
        reasons.append("BOM_MISMATCH")

    reasons = [reason for reason in _REASON_ORDER if reason in reasons]
    evidence_digests = sorted(
        [recipe["approved_digest"]]
        + [m["release_digest"] for m in packet["materials"]]
        + [e["calibration_digest"] for e in packet["equipment"]]
        + [
            environment["evidence_digest"],
            inspection["fill_weight_digest"],
            inspection["inspection_digest"],
            packet["bom"]["evidence_digest"],
        ]
    )
    source_digest = sha256(packet)
    trusted_definition_digest = sha256(definition)
    core = {
        "schema_version": DECISION_SCHEMA,
        "packet_id": packet["packet_id"],
        "batch_id": packet["batch_id"],
        "evaluated_at": trusted_as_of_s,
        "planned_slot_at": packet["planned_slot_at"],
        "status": "READY" if not reasons else "HOLD",
        "hold_reasons": reasons,
        "source_digest": source_digest,
        "trusted_definition_digest": trusted_definition_digest,
        "evidence_digests": evidence_digests,
        "authority": {
            "batch_release": False,
            "qa_qp_disposition": False,
            "recipe_authoring": False,
            "equipment_mutation": False,
            "environment_mutation": False,
            "label_device_release": False,
            "provider_mutation": False,
            "revenue_recognition": False,
        },
    }
    return {**core, "receipt_digest": sha256(core)}


def verify_decision(
    raw_packet: Any,
    raw_decision: Any,
    *,
    trusted_definition: Any,
    expected_evaluated_at: str,
    trusted_verify_at: str,
    max_age_seconds: int = DEFAULT_MAX_DECISION_AGE_SECONDS,
) -> dict[str, Any]:
    if type(max_age_seconds) is not int or isinstance(max_age_seconds, bool) or max_age_seconds < 1:
        _fail("INVALID_MAX_AGE")
    expected_evaluated_at_s, evaluated_dt = _timestamp(expected_evaluated_at, "expected_evaluated_at")
    trusted_verify_at_s, verify_dt = _timestamp(trusted_verify_at, "trusted_verify_at")
    if verify_dt < evaluated_dt:
        _fail("VERIFY_BEFORE_EVALUATION")
    decision = _obj(copy.deepcopy(raw_decision), "DECISION_REQUIRED")
    expected = evaluate(
        raw_packet,
        trusted_as_of=expected_evaluated_at_s,
        trusted_definition=trusted_definition,
    )
    if canonical_json(decision) != canonical_json(expected):
        _fail("DECISION_MISMATCH")
    age_seconds = int((verify_dt - evaluated_dt).total_seconds())
    if age_seconds > max_age_seconds:
        _fail("DECISION_STALE")
    return {
        "valid": True,
        "fresh": True,
        "trusted_verify_at": trusted_verify_at_s,
        "age_seconds": age_seconds,
        "receipt_digest": expected["receipt_digest"],
        "trusted_definition_digest": expected["trusted_definition_digest"],
        "status": expected["status"],
    }
