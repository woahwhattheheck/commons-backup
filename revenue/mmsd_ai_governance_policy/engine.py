from __future__ import annotations

import hashlib
import json
import math
from typing import Any

INPUT_SCHEMA = "commons-ai-governance-inventory/v1"
REPORT_SCHEMA = "commons-ai-governance-report/v2"
INVENTORY_SCOPE = "CALLER_SUPPLIED_ROWS_ONLY"
INVENTORY_COMPLETENESS = "NOT_ASSERTED_BY_ENGINE"
MAX_SAFE_INTEGER = (1 << 63) - 1
SYSTEM_KEYS = {
    "system_id", "system_kind", "deployment", "data_class", "external_processing",
    "provider_training", "physical_influence", "human_override", "monitoring",
    "validation_evidence_sha256", "public_records_status", "retention_status",
    "vendor_change_notice", "incident_plan", "manual_fallback", "evidence_sha256",
}
KINDS = {"GENERATIVE", "PREDICTIVE", "AGENTIC", "OPERATIONAL_AI", "EMBEDDED_AI"}
DEPLOYMENTS = {"EMPLOYEE_SELECTED", "PROCURED_EMBEDDED", "INTERNAL", "OPERATIONAL_OT"}
DATA_CLASSES = {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "UNKNOWN"}
TRI = {"YES", "NO", "UNKNOWN"}
PHYSICAL = {"NONE", "RECOMMENDATION", "AUTOMATIC", "UNKNOWN"}
PUBLIC_RECORDS = {"APPLIES", "NOT_APPLICABLE", "UNKNOWN"}
RETENTION = {"DEFINED", "UNDEFINED", "UNKNOWN"}


class GovernanceError(ValueError):
    pass


def _pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise GovernanceError(f"duplicate key: {k}")
        out[k] = v
    return out


def strict_json_loads(raw: str | bytes) -> Any:
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GovernanceError("input must be UTF-8") from exc
    if type(raw) is not str:
        raise GovernanceError("input must be str or bytes")
    try:
        return json.loads(
            raw,
            object_pairs_hook=_pairs,
            parse_constant=lambda x: (_ for _ in ()).throw(
                GovernanceError(f"non-finite JSON number: {x}")
            ),
        )
    except GovernanceError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise GovernanceError("invalid JSON") from exc


def canonical_bytes(value: Any) -> bytes:
    def reject(v: Any, path: str = "$"):
        t = type(v)
        if v is None or t in (str, bool):
            return
        if t is int:
            if v < -MAX_SAFE_INTEGER or v > MAX_SAFE_INTEGER:
                raise GovernanceError(f"integer out of range at {path}")
            return
        if t is float:
            if not math.isfinite(v):
                raise GovernanceError(f"non-finite number at {path}")
            raise GovernanceError(f"floats are not permitted at {path}")
        if t is list:
            for i, x in enumerate(v):
                reject(x, f"{path}[{i}]")
            return
        if t is dict:
            for k, x in v.items():
                if type(k) is not str:
                    raise GovernanceError(f"non-string key at {path}")
                reject(x, f"{path}.{k}")
            return
        raise GovernanceError(f"unsupported type at {path}: {t.__name__}")

    reject(value)
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _exact_keys(obj: dict[str, Any], expected: set[str], where: str):
    if type(obj) is not dict:
        raise GovernanceError(f"{where} must be an object")
    got = set(obj)
    if got != expected:
        raise GovernanceError(
            f"{where} keys mismatch: missing={sorted(expected-got)} extra={sorted(got-expected)}"
        )


def _enum(value: Any, allowed: set[str], where: str) -> str:
    if type(value) is not str or value not in allowed:
        raise GovernanceError(f"invalid {where}")
    return value


def _digest(value: Any, where: str, allow_null: bool = False) -> str | None:
    if value is None and allow_null:
        return None
    if (
        type(value) is not str
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise GovernanceError(f"invalid {where}")
    return value


def _system_normalized(row: Any) -> dict[str, Any]:
    _exact_keys(row, SYSTEM_KEYS, "system")
    sid = row["system_id"]
    if (
        type(sid) is not str
        or not sid
        or len(sid) > 96
        or any(ord(c) < 33 or ord(c) > 126 for c in sid)
    ):
        raise GovernanceError("invalid system_id")
    return {
        "system_id": sid,
        "system_kind": _enum(row["system_kind"], KINDS, "system_kind"),
        "deployment": _enum(row["deployment"], DEPLOYMENTS, "deployment"),
        "data_class": _enum(row["data_class"], DATA_CLASSES, "data_class"),
        "external_processing": _enum(
            row["external_processing"], TRI, "external_processing"
        ),
        "provider_training": _enum(row["provider_training"], TRI, "provider_training"),
        "physical_influence": _enum(
            row["physical_influence"], PHYSICAL, "physical_influence"
        ),
        "human_override": _enum(row["human_override"], TRI, "human_override"),
        "monitoring": _enum(row["monitoring"], TRI, "monitoring"),
        "validation_evidence_sha256": _digest(
            row["validation_evidence_sha256"], "validation_evidence_sha256", True
        ),
        "public_records_status": _enum(
            row["public_records_status"], PUBLIC_RECORDS, "public_records_status"
        ),
        "retention_status": _enum(
            row["retention_status"], RETENTION, "retention_status"
        ),
        "vendor_change_notice": _enum(
            row["vendor_change_notice"], TRI, "vendor_change_notice"
        ),
        "incident_plan": _enum(row["incident_plan"], TRI, "incident_plan"),
        "manual_fallback": _enum(row["manual_fallback"], TRI, "manual_fallback"),
        "evidence_sha256": _digest(row["evidence_sha256"], "evidence_sha256"),
    }


def _information_risk(s: dict[str, Any]) -> int:
    risk = 1
    if s["data_class"] in {"CONFIDENTIAL", "RESTRICTED"}:
        risk = max(risk, 3)
    if s["data_class"] == "UNKNOWN":
        risk = 4
    if s["external_processing"] == "YES" and s["data_class"] != "PUBLIC":
        risk = max(risk, 3)
    if s["external_processing"] == "UNKNOWN":
        risk = max(risk, 3)
    if (
        s["provider_training"] == "YES"
        and s["data_class"] in {"CONFIDENTIAL", "RESTRICTED"}
    ):
        risk = 4
    if s["provider_training"] == "UNKNOWN" and s["external_processing"] != "NO":
        risk = max(risk, 3)
    if (
        s["public_records_status"] == "UNKNOWN"
        or s["retention_status"] == "UNKNOWN"
    ):
        risk = max(risk, 3)
    return risk


def _operational_risk(s: dict[str, Any]) -> int:
    p = s["physical_influence"]
    if p == "NONE":
        risk = 1 if s["system_kind"] != "AGENTIC" else 2
    elif p == "RECOMMENDATION":
        risk = 3
    elif p == "AUTOMATIC":
        risk = 4
    else:
        risk = 4
    if s["deployment"] == "OPERATIONAL_OT":
        risk = max(risk, 3)
    if s["system_kind"] == "AGENTIC" and p != "NONE":
        risk = max(risk, 4)
    return risk


def _controls_and_holds(
    s: dict[str, Any], info: int, ops: int
) -> tuple[list[str], list[str]]:
    controls = {"AI_INVENTORY", "NAMED_BUSINESS_OWNER", "ACCEPTABLE_USE", "CHANGE_REVIEW"}
    holds: list[str] = []
    overall = max(info, ops)
    if overall >= 2:
        controls |= {"LOGGING", "HUMAN_OVERSIGHT", "VENDOR_REVIEW"}
    if overall >= 3:
        controls |= {
            "DATA_HANDLING_REVIEW",
            "RECORDS_RETENTION_REVIEW",
            "INCIDENT_RESPONSE",
            "VALIDATION_EVIDENCE",
            "MONITORING",
        }
    if overall >= 4 or ops >= 3:
        controls |= {
            "FORMAL_APPROVAL",
            "MANUAL_FALLBACK",
            "OPERATIONAL_SAFETY_REVIEW",
            "ROLLBACK_PLAN",
            "CHANGE_NOTIFICATION",
        }
    if s["public_records_status"] == "UNKNOWN":
        holds.append("PUBLIC_RECORDS_STATUS_UNKNOWN")
    if s["retention_status"] in {"UNKNOWN", "UNDEFINED"}:
        holds.append("RETENTION_NOT_DEFINED")
    if s["external_processing"] != "NO" and s["provider_training"] == "UNKNOWN":
        holds.append("PROVIDER_TRAINING_STATUS_UNKNOWN")
    if overall >= 3 and s["validation_evidence_sha256"] is None:
        holds.append("VALIDATION_EVIDENCE_MISSING")
    if overall >= 3 and s["monitoring"] != "YES":
        holds.append("MONITORING_NOT_EVIDENCED")
    if overall >= 3 and s["incident_plan"] != "YES":
        holds.append("INCIDENT_PLAN_NOT_EVIDENCED")
    if ops >= 3 and s["human_override"] != "YES":
        holds.append("HUMAN_OVERRIDE_NOT_EVIDENCED")
    if ops >= 3 and s["manual_fallback"] != "YES":
        holds.append("MANUAL_FALLBACK_NOT_EVIDENCED")
    if (
        overall >= 3
        and s["vendor_change_notice"] != "YES"
        and s["deployment"] in {"PROCURED_EMBEDDED", "EMPLOYEE_SELECTED"}
    ):
        holds.append("VENDOR_CHANGE_NOTICE_NOT_EVIDENCED")
    if s["physical_influence"] == "UNKNOWN":
        holds.append("PHYSICAL_INFLUENCE_UNKNOWN")
    if s["data_class"] == "UNKNOWN":
        holds.append("DATA_CLASS_UNKNOWN")
    return sorted(controls), sorted(set(holds))


def compile_report(packet: Any) -> dict[str, Any]:
    """Compile evidence for exactly the rows supplied by the caller.

    The engine deliberately does not assert that the supplied rows are a complete
    enterprise/buyer inventory. A deployment that needs whole-inventory readiness
    must establish that authority outside this buyer-neutral library.
    """
    _exact_keys(
        packet, {"schema", "inventory_id", "inventory_generation", "systems"}, "packet"
    )
    if packet["schema"] != INPUT_SCHEMA:
        raise GovernanceError("unsupported input schema")
    if (
        type(packet["inventory_id"]) is not str
        or not packet["inventory_id"]
        or len(packet["inventory_id"]) > 96
    ):
        raise GovernanceError("invalid inventory_id")
    if (
        type(packet["inventory_generation"]) is not int
        or packet["inventory_generation"] < 1
        or packet["inventory_generation"] > MAX_SAFE_INTEGER
    ):
        raise GovernanceError("invalid inventory_generation")
    if type(packet["systems"]) is not list or len(packet["systems"]) > 5000:
        raise GovernanceError("systems must be a bounded array")

    groups: dict[str, dict[str, tuple[dict[str, Any], int]]] = {}
    for raw in packet["systems"]:
        row = _system_normalized(raw)
        digest = sha256(canonical_bytes(row))
        per_id = groups.setdefault(row["system_id"], {})
        if digest in per_id:
            prev, count = per_id[digest]
            per_id[digest] = (prev, count + 1)
        else:
            per_id[digest] = (row, 1)

    system_reports = []
    conflicts = []
    for sid in sorted(groups):
        generations = groups[sid]
        if len(generations) > 1:
            conflicts.append(
                {
                    "system_id": sid,
                    "generations": [
                        {
                            "system_sha256": d,
                            "occurrences": generations[d][1],
                        }
                        for d in sorted(generations)
                    ],
                }
            )
            continue
        digest = next(iter(generations))
        row, occurrences = generations[digest]
        info = _information_risk(row)
        ops = _operational_risk(row)
        controls, holds = _controls_and_holds(row, info, ops)
        system_reports.append(
            {
                "system_id": sid,
                "system_sha256": digest,
                "occurrences": occurrences,
                "information_risk": info,
                "operational_risk": ops,
                "overall_risk": max(info, ops),
                "required_controls": controls,
                "holds": holds,
                "review_state": "HOLD" if holds else "SUPPLIED_ROW_ANALYZED",
                "external_action_authorized": False,
            }
        )

    normalized_input = {
        "schema": packet["schema"],
        "inventory_id": packet["inventory_id"],
        "inventory_generation": packet["inventory_generation"],
        "inventory_scope": INVENTORY_SCOPE,
        "systems": [
            {
                "system_id": sid,
                "generations": [
                    {"sha256": d, "occurrences": groups[sid][d][1]}
                    for d in sorted(groups[sid])
                ],
            }
            for sid in sorted(groups)
        ],
    }

    if conflicts:
        state = "HOLD_CONFLICT"
    elif any(x["holds"] for x in system_reports):
        state = "HOLD_SUPPLIED_ROWS"
    elif system_reports:
        state = "SUPPLIED_ROWS_ANALYZED"
    else:
        state = "NO_SYSTEMS_SUPPLIED"

    report = {
        "schema": REPORT_SCHEMA,
        "inventory_id": packet["inventory_id"],
        "inventory_generation": packet["inventory_generation"],
        "inventory_scope": INVENTORY_SCOPE,
        "inventory_completeness": INVENTORY_COMPLETENESS,
        "normalized_input_sha256": sha256(canonical_bytes(normalized_input)),
        "systems": system_reports,
        "system_id_conflicts": conflicts,
        "state": state,
        "legal_conclusion_authorized": False,
        "vendor_approval_authorized": False,
        "operational_release_authorized": False,
        "external_action_authorized": False,
    }
    report["receipt_sha256"] = sha256(canonical_bytes(report))
    return report


def verify_report(packet: Any, report: Any) -> bool:
    if type(report) is not dict:
        return False
    try:
        candidate = dict(report)
        receipt = candidate.pop("receipt_sha256", None)
        if type(receipt) is not str or len(receipt) != 64:
            return False
        if sha256(canonical_bytes(candidate)) != receipt:
            return False
        expected = compile_report(packet)
        return canonical_bytes(expected) == canonical_bytes(report)
    except GovernanceError:
        return False
