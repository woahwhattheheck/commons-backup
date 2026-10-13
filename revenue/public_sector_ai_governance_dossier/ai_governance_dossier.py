#!/usr/bin/env python3
"""Deterministic public-sector AI governance control dossier compiler.

This tool is intentionally buyer-neutral.  It inventories GenAI and Operational-AI
use cases, assigns a conservative *control tier* (not a legal risk classification),
derives mandatory control families, verifies evidence authority, and emits a
public-safe decision-support dossier.  It never authorizes deployment, publication,
procurement, legal conclusions, or policy approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = 1
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

USE_CASE_KINDS = {"generative", "operational"}
STAGES = {"discovered", "evaluation", "pilot", "production", "retired"}
DECISION_AUTHORITY = {
    "advisory": 0,
    "recommendation": 1,
    "automated_non_safety": 2,
    "automated_safety_critical": 4,
}
OPERATIONAL_IMPACT = {
    "none": 0,
    "administrative": 0,
    "service": 1,
    "infrastructure": 2,
    "safety_critical": 4,
}
RECOVERABILITY = {"easy": 0, "bounded": 0, "difficult": 1, "irreversible": 2}
DATA_CLASSES = {
    "public",
    "public_record",
    "internal",
    "sensitive_personal",
    "regulated",
    "operational_critical",
}
EVIDENCE_STATUS = {"verified", "pending", "missing", "rejected"}
EVIDENCE_AUTHORITY = {
    "public_source",
    "internal_record",
    "vendor_attested",
    "owner_approved",
    "security_approved",
    "legal_approved",
    "independent_review",
}

CONTROL_DESCRIPTIONS: dict[str, str] = {
    "INVENTORY_RECORD": "Use case has a named owner, purpose, stage, model/vendor binding, and inventory record.",
    "PURPOSE_LIMIT": "Permitted purpose and prohibited uses are explicitly bounded.",
    "DATA_CLASSIFICATION": "Input/output data classes and handling boundary are recorded.",
    "VENDOR_MODEL_PROVENANCE": "Vendor/model/version or internally controlled model provenance is evidenced.",
    "AUDIT_EVENT_LINEAGE": "Material prompts/inputs, model/tool versions, decisions, overrides, and outcomes are traceable.",
    "HUMAN_REVIEW": "A named human review point exists before consequential action.",
    "HUMAN_OVERRIDE": "Human operators can override or halt automated behavior without model cooperation.",
    "ACCESS_CONTROL": "Access is least-privilege and attributable to a human/service identity.",
    "RECORDS_RETENTION": "Retention/disposition requirements for AI records are defined and evidenced.",
    "VALIDATION_MONITORING": "Fit-for-purpose validation and ongoing performance/failure monitoring are defined.",
    "INCIDENT_RESPONSE": "AI incident triage, containment, notification, evidence preservation, and recovery are defined.",
    "CHANGE_MANAGEMENT": "Model, prompt, tool, policy, and data changes are versioned and requalified when material.",
    "AI_LITERACY_TRAINING": "Affected personnel receive role-appropriate AI use, escalation, and limitation training.",
    "SECURITY_REVIEW": "Threat, misuse, credential, tool-call, and data-exfiltration risks receive security review.",
    "FAILURE_TESTING": "Known failure modes and hostile/edge cases are tested before higher-impact use.",
    "DRIFT_MONITORING": "Operational/model/data drift has observable thresholds and an escalation path.",
    "ROLLBACK_KILLSWITCH": "A tested rollback, disable, or kill path exists for production use.",
    "PROCUREMENT_VENDOR_REVIEW": "Vendor terms, data use, subprocessors, support, change notice, and exit path are reviewed.",
    "INDEPENDENT_VALIDATION": "A reviewer independent of the implementation path validates high-impact controls.",
    "DUAL_CONTROL": "Two-person or equivalent independent approval protects high-impact release/action.",
    "FAIL_SAFE": "Failure defaults to a bounded safe state rather than silent continuation.",
    "PRODUCTION_RELEASE_GATE": "Production enablement requires an explicit recorded owner decision after controls are satisfied.",
    "LEGAL_POLICY_REVIEW": "Legal/policy interpretations are reviewed by authorized legal/policy authority.",
    "PUBLIC_RECORDS_REVIEW": "Public-record/retention/disclosure treatment is reviewed by authorized policy/legal authority.",
    "DATA_SOVEREIGNTY_PRIVACY_REVIEW": "Sensitive/regulated data location, use, retention, and privacy obligations are reviewed.",
    "EXTERNAL_PUBLICATION_APPROVAL": "Externally published AI-generated content has an explicit human/policy approval path.",
    "SHADOW_AI_DISPOSITION": "Unapproved/discovered AI is inventoried and explicitly dispositioned by an owner.",
    "OPERATIONAL_FALLBACK": "Operational AI has a documented non-AI/manual fallback and degraded-mode procedure.",
    "SAFETY_HAZARD_REVIEW": "Safety-relevant failure modes, hazard controls, and manual intervention are independently reviewed.",
}

# A verified evidence item must come from one of these authorities to satisfy a
# control.  This is an evidence-authority policy, not a legal determination.
CONTROL_AUTHORITIES: dict[str, frozenset[str]] = {
    "INVENTORY_RECORD": frozenset({"internal_record", "owner_approved"}),
    "PURPOSE_LIMIT": frozenset({"internal_record", "owner_approved"}),
    "DATA_CLASSIFICATION": frozenset({"internal_record", "security_approved", "owner_approved"}),
    "VENDOR_MODEL_PROVENANCE": frozenset({"public_source", "vendor_attested", "internal_record"}),
    "AUDIT_EVENT_LINEAGE": frozenset({"internal_record", "security_approved", "independent_review"}),
    "HUMAN_REVIEW": frozenset({"internal_record", "owner_approved"}),
    "HUMAN_OVERRIDE": frozenset({"internal_record", "owner_approved", "security_approved"}),
    "ACCESS_CONTROL": frozenset({"internal_record", "security_approved"}),
    "RECORDS_RETENTION": frozenset({"internal_record", "legal_approved"}),
    "VALIDATION_MONITORING": frozenset({"internal_record", "security_approved", "independent_review"}),
    "INCIDENT_RESPONSE": frozenset({"internal_record", "owner_approved", "security_approved"}),
    "CHANGE_MANAGEMENT": frozenset({"internal_record", "owner_approved"}),
    "AI_LITERACY_TRAINING": frozenset({"internal_record", "owner_approved"}),
    "SECURITY_REVIEW": frozenset({"security_approved", "independent_review"}),
    "FAILURE_TESTING": frozenset({"internal_record", "security_approved", "independent_review"}),
    "DRIFT_MONITORING": frozenset({"internal_record", "security_approved", "independent_review"}),
    "ROLLBACK_KILLSWITCH": frozenset({"internal_record", "security_approved", "owner_approved"}),
    "PROCUREMENT_VENDOR_REVIEW": frozenset({"internal_record", "owner_approved", "legal_approved", "security_approved"}),
    "INDEPENDENT_VALIDATION": frozenset({"independent_review"}),
    "DUAL_CONTROL": frozenset({"internal_record", "owner_approved", "independent_review"}),
    "FAIL_SAFE": frozenset({"internal_record", "security_approved", "independent_review"}),
    "PRODUCTION_RELEASE_GATE": frozenset({"owner_approved"}),
    "LEGAL_POLICY_REVIEW": frozenset({"legal_approved"}),
    "PUBLIC_RECORDS_REVIEW": frozenset({"legal_approved"}),
    "DATA_SOVEREIGNTY_PRIVACY_REVIEW": frozenset({"legal_approved", "security_approved"}),
    "EXTERNAL_PUBLICATION_APPROVAL": frozenset({"owner_approved", "legal_approved"}),
    "SHADOW_AI_DISPOSITION": frozenset({"owner_approved"}),
    "OPERATIONAL_FALLBACK": frozenset({"internal_record", "owner_approved", "security_approved"}),
    "SAFETY_HAZARD_REVIEW": frozenset({"independent_review", "security_approved"}),
}

BASE_CONTROLS = frozenset({
    "INVENTORY_RECORD",
    "PURPOSE_LIMIT",
    "DATA_CLASSIFICATION",
    "VENDOR_MODEL_PROVENANCE",
    "AUDIT_EVENT_LINEAGE",
})
TIER_CONTROLS: dict[int, frozenset[str]] = {
    1: frozenset(),
    2: frozenset({
        "HUMAN_REVIEW",
        "ACCESS_CONTROL",
        "VALIDATION_MONITORING",
        "INCIDENT_RESPONSE",
        "CHANGE_MANAGEMENT",
        "AI_LITERACY_TRAINING",
    }),
    3: frozenset({
        "HUMAN_REVIEW",
        "HUMAN_OVERRIDE",
        "ACCESS_CONTROL",
        "VALIDATION_MONITORING",
        "INCIDENT_RESPONSE",
        "CHANGE_MANAGEMENT",
        "AI_LITERACY_TRAINING",
        "SECURITY_REVIEW",
        "FAILURE_TESTING",
        "DRIFT_MONITORING",
        "ROLLBACK_KILLSWITCH",
        "PROCUREMENT_VENDOR_REVIEW",
    }),
    4: frozenset({
        "HUMAN_REVIEW",
        "HUMAN_OVERRIDE",
        "ACCESS_CONTROL",
        "VALIDATION_MONITORING",
        "INCIDENT_RESPONSE",
        "CHANGE_MANAGEMENT",
        "AI_LITERACY_TRAINING",
        "SECURITY_REVIEW",
        "FAILURE_TESTING",
        "DRIFT_MONITORING",
        "ROLLBACK_KILLSWITCH",
        "PROCUREMENT_VENDOR_REVIEW",
        "INDEPENDENT_VALIDATION",
        "DUAL_CONTROL",
        "FAIL_SAFE",
        "PRODUCTION_RELEASE_GATE",
        "LEGAL_POLICY_REVIEW",
    }),
}


@dataclass(frozen=True)
class ControlResult:
    control_id: str
    status: str
    evidence_refs: tuple[str, ...]
    accepted_evidence: tuple[str, ...]
    authority_mismatches: tuple[str, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class UseCaseResult:
    use_case_id: str
    name: str
    kind: str
    stage: str
    control_tier: int
    control_score: int
    disposition: str
    required_controls: tuple[str, ...]
    blocking_controls: tuple[str, ...]
    controls: tuple[ControlResult, ...]


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _json_safe(value: Any) -> Any:
    """Normalize tuples/dataclasses-derived containers to JSON-native values."""
    if isinstance(value, tuple):
        return [_json_safe(x) for x in value]
    if isinstance(value, list):
        return [_json_safe(x) for x in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    return value


def _require_dict(value: Any, context: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError(f"{context} must be an object")
    return value


def _require_list(value: Any, context: str) -> list[Any]:
    if type(value) is not list:
        raise ValueError(f"{context} must be a list")
    return value


def _require_bool(value: Any, context: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{context} must be boolean")
    return value


def _require_text(value: Any, context: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str:
        raise ValueError(f"{context} must be text")
    text = value.strip()
    if not allow_empty and not text:
        raise ValueError(f"{context} must be non-empty")
    return text


def _require_id(value: Any, context: str) -> str:
    text = _require_text(value, context)
    if not ID_RE.fullmatch(text):
        raise ValueError(f"{context} contains invalid characters")
    return text


def _validate_enum(value: Any, allowed: set[str] | Mapping[str, int], context: str) -> str:
    text = _require_text(value, context)
    if text not in allowed:
        raise ValueError(f"{context}: invalid value {text!r}")
    return text


def _unique_ids(items: Iterable[dict[str, Any]], context: str) -> None:
    seen: set[str] = set()
    for item in items:
        item_id = _require_id(item.get("id"), f"{context}.id")
        if item_id in seen:
            raise ValueError(f"duplicate {context} id: {item_id}")
        seen.add(item_id)


def validate_packet(packet: Any) -> dict[str, Any]:
    root = _require_dict(packet, "packet")
    if root.get("schema_version") != SCHEMA_VERSION or type(root.get("schema_version")) is not int:
        raise ValueError(f"schema_version must be integer {SCHEMA_VERSION}")

    org = _require_dict(root.get("organization"), "organization")
    _require_text(org.get("name"), "organization.name")
    _require_text(org.get("sector"), "organization.sector")

    vendors = [_require_dict(x, "vendors[]") for x in _require_list(root.get("vendors", []), "vendors")]
    models = [_require_dict(x, "models[]") for x in _require_list(root.get("models", []), "models")]
    evidence = [_require_dict(x, "evidence[]") for x in _require_list(root.get("evidence", []), "evidence")]
    use_cases = [_require_dict(x, "use_cases[]") for x in _require_list(root.get("use_cases"), "use_cases")]
    if not use_cases:
        raise ValueError("use_cases must contain at least one item")

    _unique_ids(vendors, "vendor")
    _unique_ids(models, "model")
    _unique_ids(evidence, "evidence")
    _unique_ids(use_cases, "use_case")

    vendor_ids = {_require_id(x["id"], "vendor.id") for x in vendors}
    model_ids = {_require_id(x["id"], "model.id") for x in models}
    evidence_ids = {_require_id(x["id"], "evidence.id") for x in evidence}
    use_case_ids = {_require_id(x["id"], "use_case.id") for x in use_cases}

    for vendor in vendors:
        _require_text(vendor.get("name"), f"vendor {vendor['id']}.name")
        refs = _require_list(vendor.get("evidence_refs", []), f"vendor {vendor['id']}.evidence_refs")
        for ref in refs:
            ref_id = _require_id(ref, f"vendor {vendor['id']}.evidence_ref")
            if ref_id not in evidence_ids:
                raise ValueError(f"vendor {vendor['id']}: unknown evidence ref {ref_id}")

    for model in models:
        _require_text(model.get("name"), f"model {model['id']}.name")
        vendor_id = _require_id(model.get("vendor_id"), f"model {model['id']}.vendor_id")
        if vendor_id not in vendor_ids:
            raise ValueError(f"model {model['id']}: unknown vendor_id {vendor_id}")
        version = model.get("version")
        if version is not None:
            _require_text(version, f"model {model['id']}.version")
        refs = _require_list(model.get("evidence_refs", []), f"model {model['id']}.evidence_refs")
        for ref in refs:
            ref_id = _require_id(ref, f"model {model['id']}.evidence_ref")
            if ref_id not in evidence_ids:
                raise ValueError(f"model {model['id']}: unknown evidence ref {ref_id}")

    for item in evidence:
        eid = item["id"]
        _validate_enum(item.get("status"), EVIDENCE_STATUS, f"evidence {eid}.status")
        _validate_enum(item.get("authority"), EVIDENCE_AUTHORITY, f"evidence {eid}.authority")
        _require_text(item.get("reference"), f"evidence {eid}.reference")
        digest = item.get("sha256")
        if digest is not None:
            digest = _require_text(digest, f"evidence {eid}.sha256")
            if not SHA256_RE.fullmatch(digest):
                raise ValueError(f"evidence {eid}.sha256 must be lowercase sha256 hex")
        scopes = _require_list(item.get("use_case_ids", ["*"]), f"evidence {eid}.use_case_ids")
        if not scopes:
            raise ValueError(f"evidence {eid}.use_case_ids cannot be empty")
        for scope in scopes:
            scope_id = _require_text(scope, f"evidence {eid}.use_case_id")
            if scope_id != "*" and scope_id not in use_case_ids:
                raise ValueError(f"evidence {eid}: unknown use_case_id {scope_id}")
        controls = _require_list(item.get("control_ids"), f"evidence {eid}.control_ids")
        if not controls:
            raise ValueError(f"evidence {eid}.control_ids cannot be empty")
        for control in controls:
            cid = _require_text(control, f"evidence {eid}.control_id")
            if cid not in CONTROL_DESCRIPTIONS:
                raise ValueError(f"evidence {eid}: unknown control_id {cid}")

    for use_case in use_cases:
        uid = use_case["id"]
        _require_text(use_case.get("name"), f"use_case {uid}.name")
        _validate_enum(use_case.get("kind"), USE_CASE_KINDS, f"use_case {uid}.kind")
        _validate_enum(use_case.get("stage"), STAGES, f"use_case {uid}.stage")
        _validate_enum(use_case.get("decision_authority"), DECISION_AUTHORITY, f"use_case {uid}.decision_authority")
        _validate_enum(use_case.get("operational_impact"), OPERATIONAL_IMPACT, f"use_case {uid}.operational_impact")
        _validate_enum(use_case.get("recoverability"), RECOVERABILITY, f"use_case {uid}.recoverability")
        _require_bool(use_case.get("external_publication"), f"use_case {uid}.external_publication")
        _require_bool(use_case.get("shadow_ai"), f"use_case {uid}.shadow_ai")
        classes = _require_list(use_case.get("data_classes"), f"use_case {uid}.data_classes")
        if not classes:
            raise ValueError(f"use_case {uid}.data_classes cannot be empty")
        for data_class in classes:
            _validate_enum(data_class, DATA_CLASSES, f"use_case {uid}.data_class")
        if len(classes) != len(set(classes)):
            raise ValueError(f"use_case {uid}: duplicate data_classes")
        vendor_id = _require_id(use_case.get("vendor_id"), f"use_case {uid}.vendor_id")
        model_id = _require_id(use_case.get("model_id"), f"use_case {uid}.model_id")
        if vendor_id not in vendor_ids:
            raise ValueError(f"use_case {uid}: unknown vendor_id {vendor_id}")
        if model_id not in model_ids:
            raise ValueError(f"use_case {uid}: unknown model_id {model_id}")
        model = next(x for x in models if x["id"] == model_id)
        if model["vendor_id"] != vendor_id:
            raise ValueError(f"use_case {uid}: model {model_id} belongs to a different vendor")

    return root


def control_score(use_case: Mapping[str, Any]) -> int:
    score = DECISION_AUTHORITY[str(use_case["decision_authority"])]
    score += OPERATIONAL_IMPACT[str(use_case["operational_impact"])]
    score += RECOVERABILITY[str(use_case["recoverability"])]
    classes = set(str(x) for x in use_case["data_classes"])
    if "sensitive_personal" in classes:
        score += 2
    if "regulated" in classes:
        score += 3
    if "operational_critical" in classes:
        score += 2
    if str(use_case["kind"]) == "operational":
        score += 1
    if bool(use_case["external_publication"]):
        score += 1
    if bool(use_case["shadow_ai"]):
        score += 1
    return score


def control_tier(use_case: Mapping[str, Any]) -> int:
    score = control_score(use_case)
    if score <= 2:
        return 1
    if score <= 5:
        return 2
    if score <= 8:
        return 3
    return 4


def required_controls(use_case: Mapping[str, Any]) -> tuple[str, ...]:
    tier = control_tier(use_case)
    controls = set(BASE_CONTROLS)
    controls.update(TIER_CONTROLS[tier])
    classes = set(str(x) for x in use_case["data_classes"])

    if "public_record" in classes:
        controls.update({"RECORDS_RETENTION", "PUBLIC_RECORDS_REVIEW"})
    if classes & {"sensitive_personal", "regulated"}:
        controls.add("DATA_SOVEREIGNTY_PRIVACY_REVIEW")
    if bool(use_case["external_publication"]):
        controls.add("EXTERNAL_PUBLICATION_APPROVAL")
    if bool(use_case["shadow_ai"]):
        controls.add("SHADOW_AI_DISPOSITION")
    if str(use_case["kind"]) == "operational":
        controls.update({"OPERATIONAL_FALLBACK", "VALIDATION_MONITORING"})
    if str(use_case["decision_authority"]) in {"automated_non_safety", "automated_safety_critical"}:
        controls.add("HUMAN_OVERRIDE")
    if str(use_case["operational_impact"]) == "safety_critical" or str(use_case["decision_authority"]) == "automated_safety_critical":
        controls.update({"SAFETY_HAZARD_REVIEW", "FAIL_SAFE", "OPERATIONAL_FALLBACK", "INDEPENDENT_VALIDATION"})
    if str(use_case["stage"]) == "production" and tier >= 3:
        controls.add("PRODUCTION_RELEASE_GATE")
    return tuple(sorted(controls))


def _evidence_for_control(evidence: list[dict[str, Any]], use_case_id: str, control_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in evidence:
        scopes = set(str(x) for x in item.get("use_case_ids", ["*"]))
        controls = set(str(x) for x in item.get("control_ids", []))
        if ("*" in scopes or use_case_id in scopes) and control_id in controls:
            rows.append(item)
    return sorted(rows, key=lambda x: str(x["id"]))


def evaluate_control(evidence: list[dict[str, Any]], use_case_id: str, control_id: str) -> ControlResult:
    rows = _evidence_for_control(evidence, use_case_id, control_id)
    allowed = CONTROL_AUTHORITIES[control_id]
    accepted: list[str] = []
    mismatches: list[str] = []
    pending: list[str] = []
    rejected: list[str] = []
    refs = [str(x["id"]) for x in rows]

    for item in rows:
        status = str(item["status"])
        authority = str(item["authority"])
        eid = str(item["id"])
        if status == "verified" and authority in allowed:
            accepted.append(eid)
        elif status == "verified":
            mismatches.append(eid)
        elif status == "pending":
            pending.append(eid)
        elif status == "rejected":
            rejected.append(eid)

    notes: list[str] = []
    if accepted:
        status = "SATISFIED"
    elif mismatches:
        status = "AUTHORITY_MISMATCH"
        notes.append("verified evidence exists but lacks an accepted authority for this control")
    elif pending:
        status = "PENDING"
        notes.append("evidence is pending")
    elif rejected:
        status = "REJECTED"
        notes.append("candidate evidence was rejected")
    else:
        status = "MISSING"
        notes.append("no verified evidence scoped to this control and use case")

    return ControlResult(
        control_id=control_id,
        status=status,
        evidence_refs=tuple(refs),
        accepted_evidence=tuple(accepted),
        authority_mismatches=tuple(mismatches),
        notes=tuple(notes),
    )


def evaluate_use_case(use_case: dict[str, Any], evidence: list[dict[str, Any]]) -> UseCaseResult:
    controls = required_controls(use_case)
    results = tuple(evaluate_control(evidence, str(use_case["id"]), cid) for cid in controls)
    blocking = tuple(r.control_id for r in results if r.status != "SATISFIED")
    if blocking:
        disposition = "HOLD_CONTROLS"
    elif bool(use_case["shadow_ai"]):
        # Even a dispositioned shadow-AI record is not automatically sanctioned.
        disposition = "CONTROL_READY_OWNER_DECISION"
    elif str(use_case["stage"]) == "retired":
        disposition = "RETIRED_CONTROLLED"
    else:
        disposition = "CONTROL_READY_OWNER_DECISION"
    return UseCaseResult(
        use_case_id=str(use_case["id"]),
        name=str(use_case["name"]),
        kind=str(use_case["kind"]),
        stage=str(use_case["stage"]),
        control_tier=control_tier(use_case),
        control_score=control_score(use_case),
        disposition=disposition,
        required_controls=controls,
        blocking_controls=blocking,
        controls=results,
    )


def _safe_evidence_registry(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Emit only evidence metadata; never propagate payload/private notes."""
    safe: list[dict[str, Any]] = []
    for item in sorted(evidence, key=lambda x: str(x["id"])):
        safe.append({
            "id": str(item["id"]),
            "status": str(item["status"]),
            "authority": str(item["authority"]),
            "reference": str(item["reference"]),
            "sha256": item.get("sha256"),
            "use_case_ids": sorted(str(x) for x in item.get("use_case_ids", ["*"])),
            "control_ids": sorted(str(x) for x in item.get("control_ids", [])),
        })
    return safe


def compile_dossier(packet: Any) -> dict[str, Any]:
    root = validate_packet(packet)
    evidence = list(root.get("evidence", []))
    use_case_results = [evaluate_use_case(u, evidence) for u in sorted(root["use_cases"], key=lambda x: str(x["id"]))]

    tier_counts = {str(tier): 0 for tier in range(1, 5)}
    disposition_counts: dict[str, int] = {}
    blocking_total = 0
    for result in use_case_results:
        tier_counts[str(result.control_tier)] += 1
        disposition_counts[result.disposition] = disposition_counts.get(result.disposition, 0) + 1
        blocking_total += len(result.blocking_controls)

    shadow = []
    use_case_by_id = {str(x["id"]): x for x in root["use_cases"]}
    result_by_id = {x.use_case_id: x for x in use_case_results}
    for uid in sorted(use_case_by_id):
        uc = use_case_by_id[uid]
        if not bool(uc["shadow_ai"]):
            continue
        control = next((c for c in result_by_id[uid].controls if c.control_id == "SHADOW_AI_DISPOSITION"), None)
        shadow.append({
            "use_case_id": uid,
            "disposition": "DISPOSITION_RECORDED_NOT_AUTHORIZED" if control and control.status == "SATISFIED" else "UNSANCTIONED_REQUIRES_OWNER_REVIEW",
            "evidence_refs": list(control.accepted_evidence if control else ()),
        })

    vendors = []
    models_by_vendor: dict[str, list[str]] = {}
    for model in root.get("models", []):
        models_by_vendor.setdefault(str(model["vendor_id"]), []).append(str(model["id"]))
    for vendor in sorted(root.get("vendors", []), key=lambda x: str(x["id"])):
        vendors.append({
            "id": str(vendor["id"]),
            "name": str(vendor["name"]),
            "models": sorted(models_by_vendor.get(str(vendor["id"]), [])),
            "evidence_refs": sorted(str(x) for x in vendor.get("evidence_refs", [])),
        })

    core = {
        "schema_version": SCHEMA_VERSION,
        "organization": {
            "name": str(root["organization"]["name"]),
            "sector": str(root["organization"]["sector"]),
        },
        "input_sha256": _sha256(root),
        "control_model": {
            "name": "commons-public-sector-ai-governance-control-model",
            "version": 1,
            "tier_semantics": "internal control intensity; not a legal or regulatory risk classification",
        },
        "summary": {
            "use_case_count": len(use_case_results),
            "tier_counts": tier_counts,
            "disposition_counts": dict(sorted(disposition_counts.items())),
            "blocking_control_count": blocking_total,
            "all_controls_satisfied": blocking_total == 0,
            "autonomous_authority": False,
            "submission_authorized": False,
            "production_authorized": False,
            "external_publication_authorized": False,
            "legal_compliance_certified": False,
        },
        "use_cases": [_json_safe(asdict(x)) for x in use_case_results],
        "shadow_ai": shadow,
        "vendors": vendors,
        "evidence_registry": _safe_evidence_registry(evidence),
        "authority_boundary": {
            "owner_decision_required": True,
            "legal_review_not_inferred": True,
            "policy_approval_not_inferred": True,
            "production_release_not_inferred": True,
            "external_publication_not_inferred": True,
            "procurement_commitment_not_inferred": True,
        },
    }
    dossier = dict(core)
    dossier["dossier_sha256"] = _sha256(core)
    return dossier


def render_markdown(dossier: Mapping[str, Any]) -> str:
    summary = dossier["summary"]
    lines = [
        "# Public-sector AI governance control dossier",
        "",
        f"**Organization:** {dossier['organization']['name']}  ",
        f"**Sector:** {dossier['organization']['sector']}  ",
        f"**Input SHA-256:** `{dossier['input_sha256']}`  ",
        f"**Dossier SHA-256:** `{dossier['dossier_sha256']}`  ",
        "",
        "> Control tiers are an internal evidence/control-intensity model, not a legal or regulatory risk classification. This dossier never authorizes deployment, publication, procurement, or legal conclusions.",
        "",
        "## Summary",
        "",
        f"- Use cases: **{summary['use_case_count']}**",
        f"- Blocking controls: **{summary['blocking_control_count']}**",
        f"- All controls satisfied: **{'YES' if summary['all_controls_satisfied'] else 'NO'}**",
        "- Autonomous authority: **NO**",
        "- Production authorization: **NO**",
        "- External-publication authorization: **NO**",
        "- Legal/compliance certification: **NO**",
        "",
        "## Use-case register",
        "",
        "| Use case | Kind | Stage | Tier | Score | Disposition | Blocking controls |",
        "|---|---|---|---:|---:|---|---|",
    ]
    for uc in dossier["use_cases"]:
        blockers = ", ".join(uc["blocking_controls"]) or "—"
        lines.append(
            f"| {uc['use_case_id']} — {uc['name']} | {uc['kind']} | {uc['stage']} | {uc['control_tier']} | "
            f"{uc['control_score']} | **{uc['disposition']}** | {blockers} |"
        )

    for uc in dossier["use_cases"]:
        lines += ["", f"## {uc['use_case_id']}: {uc['name']}", ""]
        lines.append(f"Control tier **{uc['control_tier']}** · score **{uc['control_score']}** · disposition **{uc['disposition']}**")
        lines += ["", "| Control | Status | Accepted evidence | Evidence seen |", "|---|---|---|---|"]
        for control in uc["controls"]:
            accepted = ", ".join(control["accepted_evidence"]) or "—"
            seen = ", ".join(control["evidence_refs"]) or "—"
            lines.append(f"| {control['control_id']} | **{control['status']}** | {accepted} | {seen} |")

    if dossier["shadow_ai"]:
        lines += ["", "## Shadow-AI inventory", ""]
        for row in dossier["shadow_ai"]:
            refs = ", ".join(row["evidence_refs"]) or "none"
            lines.append(f"- **{row['use_case_id']}** — {row['disposition']} (evidence: {refs})")

    lines += [
        "",
        "## Authority boundary",
        "",
        "A satisfied control means only that appropriately scoped evidence exists under this control model. It does **not** convert the dossier into legal advice, policy approval, a procurement commitment, production release, or permission to publish externally.",
        "",
    ]
    return "\n".join(lines)


def verify_dossier(packet: Any, candidate: Any) -> tuple[bool, str]:
    expected = compile_dossier(packet)
    if type(candidate) is not dict:
        return False, "candidate dossier must be an object"
    if candidate != expected:
        return False, "candidate dossier does not match deterministic recomputation"
    return True, "verified"


def _load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(path: str | Path, value: Any) -> None:
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    compile_p = sub.add_parser("compile", help="compile an input packet into deterministic governance outputs")
    compile_p.add_argument("--input", required=True)
    compile_p.add_argument("--json-out", required=True)
    compile_p.add_argument("--markdown-out")
    compile_p.add_argument("--fail-on-hold", action="store_true", help="exit 2 if any required control is unsatisfied")

    verify_p = sub.add_parser("verify", help="recompute and verify an existing dossier")
    verify_p.add_argument("--input", required=True)
    verify_p.add_argument("--dossier", required=True)

    args = parser.parse_args(argv)
    if args.command == "compile":
        packet = _load_json(args.input)
        dossier = compile_dossier(packet)
        _write_json(args.json_out, dossier)
        if args.markdown_out:
            Path(args.markdown_out).write_text(render_markdown(dossier), encoding="utf-8")
        if args.fail_on_hold and not dossier["summary"]["all_controls_satisfied"]:
            return 2
        return 0

    packet = _load_json(args.input)
    candidate = _load_json(args.dossier)
    ok, message = verify_dossier(packet, candidate)
    if not ok:
        print(message)
        return 3
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
