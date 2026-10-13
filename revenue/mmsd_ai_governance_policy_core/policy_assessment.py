"""Deterministic AI inventory/risk/control assessment for public-utility policy work.

This package does not make legal conclusions, approve AI use, authorize procurement,
change operational systems, or adopt policy. It turns approved inventory evidence into
a bounded review packet for human policy/governance work.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
import math
import re
from typing import Any, Mapping

CONTRACT = "mmsd-ai-governance-assessment/v1"
RESULT_VERSION = "mmsd-ai-governance-result/v1"

KINDS = {"GENERATIVE", "OPERATIONAL"}
LIFECYCLES = {"DISCOVERY", "PILOT", "PRODUCTION", "PROCUREMENT"}
AUTOMATION = {"ASSISTIVE", "RECOMMENDATION", "AUTONOMOUS"}
DATA_CLASSES = {
    "PUBLIC",
    "INTERNAL",
    "PUBLIC_RECORD",
    "PERSONAL",
    "SECURITY_SENSITIVE",
    "CRITICAL_INFRASTRUCTURE",
}
IMPACT_AREAS = {
    "ADMINISTRATIVE",
    "PUBLIC_COMMUNICATION",
    "FINANCIAL",
    "EMPLOYMENT",
    "SAFETY",
    "WASTEWATER_PROCESS",
    "INFRASTRUCTURE",
    "CYBERSECURITY",
}
TIER_ORDER = {"T1_LOW": 1, "T2_MODERATE": 2, "T3_HIGH": 3, "T4_CRITICAL": 4}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,95}$")
SECRET_PATTERNS = [
    re.compile(r"\b(?:sk|rk)-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.I),
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----", re.I),
]

INPUT_KEYS = {"contract", "inventory", "control_evidence"}
SYSTEM_KEYS = {
    "system_id",
    "name",
    "ai_kind",
    "lifecycle",
    "automation_level",
    "data_classes",
    "impact_areas",
    "external_vendor",
    "internet_connected",
    "can_change_operational_state",
    "public_facing_output",
    "owner_role",
}
EVIDENCE_KEYS = {
    "system_id",
    "evidence_id",
    "captured_at",
    "inventory_evidence_sha256",
    "controls",
}
CONTROL_KEYS = {
    "named_owner",
    "approved_use_case",
    "data_classification",
    "records_retention",
    "records_export",
    "vendor_terms_review",
    "security_review",
    "incident_response",
    "logging_monitoring",
    "human_oversight",
    "output_validation",
    "change_management",
    "ot_safety_review",
    "fail_safe_or_rollback",
    "staff_training",
    "data_residency_known",
}
RESULT_KEYS = {
    "version",
    "state",
    "as_of",
    "inventory_sha256",
    "systems",
    "portfolio_summary",
    "authority",
    "result_sha256",
}


class GovernanceError(ValueError):
    """Fail-closed validation error."""


def _dict(value: Any, where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise GovernanceError(f"{where}: expected plain object")
    return value


def _list(value: Any, where: str) -> list[Any]:
    if type(value) is not list:
        raise GovernanceError(f"{where}: expected array")
    return value


def _exact(value: Mapping[str, Any], keys: set[str], where: str) -> None:
    got = set(value)
    if got != keys:
        raise GovernanceError(
            f"{where}: schema mismatch missing={sorted(keys-got)} extra={sorted(got-keys)}"
        )


def _str(value: Any, where: str, *, max_len: int = 512) -> str:
    if type(value) is not str or not value.strip():
        raise GovernanceError(f"{where}: non-empty string required")
    if len(value) > max_len:
        raise GovernanceError(f"{where}: string too long")
    _reject_secret(value, where)
    return value


def _id(value: Any, where: str) -> str:
    text = _str(value, where, max_len=96)
    if not ID_RE.fullmatch(text):
        raise GovernanceError(f"{where}: invalid identifier")
    return text


def _bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise GovernanceError(f"{where}: boolean required")
    return value


def _sha(value: Any, where: str) -> str:
    if type(value) is not str or not SHA256_RE.fullmatch(value):
        raise GovernanceError(f"{where}: lowercase sha256 hex required")
    return value


def _instant(value: Any, where: str) -> datetime:
    text = _str(value, where, max_len=32)
    if not text.endswith("Z"):
        raise GovernanceError(f"{where}: canonical UTC Z timestamp required")
    try:
        dt = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise GovernanceError(f"{where}: invalid timestamp") from exc
    if dt.tzinfo != timezone.utc or dt.microsecond != 0:
        raise GovernanceError(f"{where}: second-precision canonical UTC required")
    if dt.strftime("%Y-%m-%dT%H:%M:%SZ") != text:
        raise GovernanceError(f"{where}: second-precision canonical UTC required")
    return dt


def _reject_secret(value: str, where: str) -> None:
    if any(p.search(value) for p in SECRET_PATTERNS):
        raise GovernanceError(f"{where}: secret-shaped material rejected")
    compact = value.lower().replace(" ", "")
    for label in ("api_key=", "apikey=", "secret=", "access_token=", "private_key="):
        if label in compact:
            raise GovernanceError(f"{where}: secret-shaped material rejected")


def _enum(value: Any, allowed: set[str], where: str) -> str:
    text = _str(value, where, max_len=64)
    if text not in allowed:
        raise GovernanceError(f"{where}: unsupported value")
    return text


def _unique_enums(value: Any, allowed: set[str], where: str) -> tuple[str, ...]:
    rows = _list(value, where)
    if not rows:
        raise GovernanceError(f"{where}: at least one value required")
    if len(rows) > len(allowed):
        raise GovernanceError(f"{where}: too many values")
    out = []
    seen = set()
    for i, item in enumerate(rows):
        parsed = _enum(item, allowed, f"{where}[{i}]")
        if parsed in seen:
            raise GovernanceError(f"{where}: duplicate value {parsed}")
        seen.add(parsed)
        out.append(parsed)
    return tuple(sorted(out))


def _reject_noncanonical(value: Any, where: str = "$") -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise GovernanceError(f"{where}: non-finite float")
        raise GovernanceError(f"{where}: floats forbidden")
    if type(value) is list:
        for i, child in enumerate(value):
            _reject_noncanonical(child, f"{where}[{i}]")
        return
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                raise GovernanceError(f"{where}: non-string key")
            _reject_noncanonical(child, f"{where}.{key}")
        return
    raise GovernanceError(f"{where}: unsupported type {type(value).__name__}")


def canonical_json(value: Any) -> str:
    _reject_noncanonical(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def loads_strict(text: str) -> Any:
    def hook(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise GovernanceError(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    def bad_constant(value):
        raise GovernanceError(f"non-finite JSON number: {value}")

    try:
        value = json.loads(text, object_pairs_hook=hook, parse_constant=bad_constant)
    except json.JSONDecodeError as exc:
        raise GovernanceError(f"invalid JSON: {exc.msg}") from exc
    _reject_noncanonical(value)
    return value


def _system(raw: Any, index: int) -> dict[str, Any]:
    obj = _dict(raw, f"inventory[{index}]")
    _exact(obj, SYSTEM_KEYS, f"inventory[{index}]")
    sid = _id(obj["system_id"], f"inventory[{index}].system_id")
    name = _str(obj["name"], f"system {sid}.name", max_len=160)
    owner_role = _str(obj["owner_role"], f"system {sid}.owner_role", max_len=160)
    return {
        "system_id": sid,
        "name": name,
        "ai_kind": _enum(obj["ai_kind"], KINDS, f"system {sid}.ai_kind"),
        "lifecycle": _enum(obj["lifecycle"], LIFECYCLES, f"system {sid}.lifecycle"),
        "automation_level": _enum(
            obj["automation_level"], AUTOMATION, f"system {sid}.automation_level"
        ),
        "data_classes": list(_unique_enums(obj["data_classes"], DATA_CLASSES, f"system {sid}.data_classes")),
        "impact_areas": list(_unique_enums(obj["impact_areas"], IMPACT_AREAS, f"system {sid}.impact_areas")),
        "external_vendor": _bool(obj["external_vendor"], f"system {sid}.external_vendor"),
        "internet_connected": _bool(obj["internet_connected"], f"system {sid}.internet_connected"),
        "can_change_operational_state": _bool(
            obj["can_change_operational_state"], f"system {sid}.can_change_operational_state"
        ),
        "public_facing_output": _bool(
            obj["public_facing_output"], f"system {sid}.public_facing_output"
        ),
        "owner_role": owner_role,
    }


def _inherent_tier(system: Mapping[str, Any]) -> str:
    data = set(system["data_classes"])
    impacts = set(system["impact_areas"])
    automation = system["automation_level"]

    critical = (
        system["ai_kind"] == "OPERATIONAL"
        and (
            system["can_change_operational_state"]
            or automation == "AUTONOMOUS"
            or bool(impacts & {"SAFETY", "WASTEWATER_PROCESS", "INFRASTRUCTURE"})
        )
    )
    if critical:
        return "T4_CRITICAL"

    high = (
        bool(data & {"PERSONAL", "SECURITY_SENSITIVE", "CRITICAL_INFRASTRUCTURE"})
        or bool(impacts & {"FINANCIAL", "EMPLOYMENT", "CYBERSECURITY", "SAFETY"})
        or automation == "AUTONOMOUS"
        or system["can_change_operational_state"]
        or (system["public_facing_output"] and automation != "ASSISTIVE")
    )
    if high:
        return "T3_HIGH"

    moderate = (
        system["external_vendor"]
        or system["internet_connected"]
        or system["public_facing_output"]
        or "PUBLIC_RECORD" in data
        or automation == "RECOMMENDATION"
        or system["lifecycle"] in {"PRODUCTION", "PROCUREMENT"}
    )
    if moderate:
        return "T2_MODERATE"
    return "T1_LOW"


BASE_CONTROLS = {
    "named_owner",
    "approved_use_case",
    "data_classification",
    "records_retention",
    "logging_monitoring",
    "staff_training",
}
T2_CONTROLS = BASE_CONTROLS | {
    "human_oversight",
    "output_validation",
    "incident_response",
    "records_export",
}
T3_CONTROLS = T2_CONTROLS | {
    "security_review",
    "change_management",
    "fail_safe_or_rollback",
}
T4_CONTROLS = T3_CONTROLS | {"ot_safety_review"}


def _required_controls(system: Mapping[str, Any], tier: str) -> tuple[str, ...]:
    if tier == "T1_LOW":
        controls = set(BASE_CONTROLS)
    elif tier == "T2_MODERATE":
        controls = set(T2_CONTROLS)
    elif tier == "T3_HIGH":
        controls = set(T3_CONTROLS)
    else:
        controls = set(T4_CONTROLS)

    if system["external_vendor"]:
        controls |= {"vendor_terms_review", "data_residency_known"}
    if system["public_facing_output"] or "PUBLIC_RECORD" in system["data_classes"]:
        controls |= {"records_export", "output_validation"}
    if system["internet_connected"]:
        controls |= {"security_review", "incident_response"}
    if system["ai_kind"] == "OPERATIONAL":
        controls |= {"change_management", "fail_safe_or_rollback"}
    if system["can_change_operational_state"]:
        controls |= {"ot_safety_review", "human_oversight"}
    return tuple(sorted(controls))


def _evidence(raw: Any, index: int, trusted_as_of: datetime) -> dict[str, Any]:
    obj = _dict(raw, f"control_evidence[{index}]")
    _exact(obj, EVIDENCE_KEYS, f"control_evidence[{index}]")
    sid = _id(obj["system_id"], f"control_evidence[{index}].system_id")
    evidence_id = _id(obj["evidence_id"], f"control_evidence[{index}].evidence_id")
    captured = _instant(obj["captured_at"], f"control_evidence[{index}].captured_at")
    if captured > trusted_as_of:
        raise GovernanceError(f"control_evidence[{index}].captured_at: future evidence")
    controls_obj = _dict(obj["controls"], f"control_evidence[{index}].controls")
    _exact(controls_obj, CONTROL_KEYS, f"control_evidence[{index}].controls")
    controls = {key: _bool(value, f"control_evidence[{index}].controls.{key}") for key, value in controls_obj.items()}
    return {
        "system_id": sid,
        "evidence_id": evidence_id,
        "captured_at": obj["captured_at"],
        "inventory_evidence_sha256": _sha(
            obj["inventory_evidence_sha256"],
            f"control_evidence[{index}].inventory_evidence_sha256",
        ),
        "controls": controls,
    }


def assess_governance(input_raw: Any, *, trusted_as_of: str) -> dict[str, Any]:
    """Compile one deterministic governance review packet."""
    root = _dict(input_raw, "input")
    _exact(root, INPUT_KEYS, "input")
    if root["contract"] != CONTRACT:
        raise GovernanceError("input.contract: unsupported contract")
    as_of = _instant(trusted_as_of, "trusted_as_of")

    inventory_rows = _list(root["inventory"], "input.inventory")
    evidence_rows = _list(root["control_evidence"], "input.control_evidence")
    if not inventory_rows:
        raise GovernanceError("input.inventory: at least one system required")
    if len(inventory_rows) > 1000:
        raise GovernanceError("input.inventory: maximum 1000 systems")

    systems: dict[str, dict[str, Any]] = {}
    for i, raw in enumerate(inventory_rows):
        sysrow = _system(raw, i)
        sid = sysrow["system_id"]
        if sid in systems:
            raise GovernanceError(f"duplicate system_id: {sid}")
        systems[sid] = sysrow

    inventory_canonical = [systems[key] for key in sorted(systems)]
    inventory_sha = digest(inventory_canonical)

    evidences: dict[str, dict[str, Any]] = {}
    seen_evidence_ids: set[str] = set()
    for i, raw in enumerate(evidence_rows):
        row = _evidence(raw, i, as_of)
        sid = row["system_id"]
        if sid not in systems:
            raise GovernanceError(f"control evidence references unknown system: {sid}")
        if row["evidence_id"] in seen_evidence_ids:
            raise GovernanceError(f"duplicate evidence_id: {row['evidence_id']}")
        seen_evidence_ids.add(row["evidence_id"])
        if sid in evidences:
            raise GovernanceError(f"multiple control evidence rows for system: {sid}")
        if row["inventory_evidence_sha256"] != inventory_sha:
            raise GovernanceError(f"control evidence inventory digest mismatch for system: {sid}")
        evidences[sid] = row

    out_systems: list[dict[str, Any]] = []
    tier_counts = {tier: 0 for tier in TIER_ORDER}
    gap_count = 0
    missing_evidence_count = 0
    for sid in sorted(systems):
        system = systems[sid]
        tier = _inherent_tier(system)
        tier_counts[tier] += 1
        required = _required_controls(system, tier)
        ev = evidences.get(sid)
        if ev is None:
            missing = list(required)
            missing_evidence_count += 1
            evidence_id = None
            captured_at = None
        else:
            missing = [key for key in required if not ev["controls"][key]]
            evidence_id = ev["evidence_id"]
            captured_at = ev["captured_at"]
        if missing:
            gap_count += 1
        out_systems.append(
            {
                "system_id": sid,
                "ai_kind": system["ai_kind"],
                "lifecycle": system["lifecycle"],
                "inherent_risk_tier": tier,
                "required_controls": list(required),
                "missing_controls": missing,
                "control_evidence_id": evidence_id,
                "control_evidence_captured_at": captured_at,
                "review_status": "CONTROL_GAPS_PRESENT" if missing else "CONTROL_SET_EVIDENCED",
            }
        )

    state = "CONTROL_GAPS_PRESENT" if gap_count else "ASSESSMENT_COMPLETE"
    result = {
        "version": RESULT_VERSION,
        "state": state,
        "as_of": trusted_as_of,
        "inventory_sha256": inventory_sha,
        "systems": out_systems,
        "portfolio_summary": {
            "system_count": len(out_systems),
            "systems_with_control_gaps": gap_count,
            "systems_without_control_evidence": missing_evidence_count,
            "tier_counts": tier_counts,
        },
        "authority": {
            "legal_conclusion": False,
            "policy_adoption": False,
            "procurement_approval": False,
            "production_change": False,
            "system_shutdown": False,
            "incident_command": False,
            "records_disposition": False,
            "public_statement": False,
            "contract_or_revenue": False,
        },
    }
    result["result_sha256"] = digest(result)
    return result


def verify_result(result_raw: Any) -> bool:
    obj = _dict(result_raw, "result")
    _exact(obj, RESULT_KEYS, "result")
    claimed = _sha(obj["result_sha256"], "result.result_sha256")
    unsigned = dict(obj)
    unsigned.pop("result_sha256")
    return hmac.compare_digest(claimed, digest(unsigned))
