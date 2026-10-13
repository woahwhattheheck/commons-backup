from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime, timezone
from typing import Any

from .model import EvidenceError, GateResult, require_list, require_object, require_text

REQUIRED_SERVICE_A_PATHWAYS = {
    "manufacturing",
    "construction",
    "logistics",
    "healthcare",
    "business_operations",
}
REQUIRED_SCOPES = REQUIRED_SERVICE_A_PATHWAYS | {"career_readiness"}
REQUIRED_MODES = {"live_remote", "in_person"}
ALLOWED_ROLES = {"prime", "teaming_partner", "subcontractor"}
ALLOWED_EVIDENCE_KINDS = {
    "partner_reply",
    "signed_letter",
    "reference_confirmation",
    "resume",
    "capability_statement",
    "policy",
    "insurance",
    "registration",
    "pricing",
    "travel_plan",
    "curriculum",
    "accessibility_plan",
    "records_plan",
    "data_security_plan",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _parse_date(value: Any, path: str) -> date:
    text = require_text(value, path)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise EvidenceError(f"{path} must be ISO date YYYY-MM-DD") from exc


def _parse_timestamp(value: Any, path: str) -> datetime:
    text = require_text(value, path)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError(f"{path} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise EvidenceError(f"{path} must include timezone")
    return parsed.astimezone(timezone.utc)


def _validate_receipt(value: Any, path: str, *, allowed_kinds: set[str] | None = None) -> dict[str, str]:
    obj = require_object(value, path)
    allowed = {"source_id", "sha256", "captured_at", "kind"}
    extra = sorted(set(obj) - allowed)
    missing = sorted(allowed - set(obj))
    if extra:
        raise EvidenceError(f"{path} contains unsupported fields: {', '.join(extra)}")
    if missing:
        raise EvidenceError(f"{path} missing fields: {', '.join(missing)}")
    source_id = require_text(obj["source_id"], f"{path}.source_id")
    digest = require_text(obj["sha256"], f"{path}.sha256").lower()
    if not SHA256_RE.fullmatch(digest):
        raise EvidenceError(f"{path}.sha256 must be 64 lowercase hex characters")
    captured = _parse_timestamp(obj["captured_at"], f"{path}.captured_at").isoformat()
    kind = require_text(obj["kind"], f"{path}.kind")
    if kind not in ALLOWED_EVIDENCE_KINDS:
        raise EvidenceError(f"{path}.kind unsupported: {kind}")
    if allowed_kinds is not None and kind not in allowed_kinds:
        raise EvidenceError(f"{path}.kind must be one of {sorted(allowed_kinds)}")
    return {"source_id": source_id, "sha256": digest, "captured_at": captured, "kind": kind}


def _five_year_cutoff(evaluated_on: date) -> date:
    try:
        return evaluated_on.replace(year=evaluated_on.year - 5)
    except ValueError:
        # February 29 has no representation in most target years.
        return evaluated_on.replace(year=evaluated_on.year - 5, day=28)


def _gate(gate: str, passed: bool, detail: str) -> GateResult:
    return GateResult(gate=gate, status="PASS" if passed else "HOLD", detail=detail)


def evaluate_bundle(bundle: dict[str, Any], *, input_sha256: str | None = None) -> dict[str, Any]:
    if not isinstance(bundle, dict):
        raise EvidenceError("bundle must be an object")
    allowed_top = {
        "opportunity_id",
        "evaluated_on",
        "partner",
        "references",
        "instructors",
        "operations",
    }
    extra_top = sorted(set(bundle) - allowed_top)
    missing_top = sorted(allowed_top - set(bundle))
    if extra_top:
        raise EvidenceError(f"bundle contains unsupported fields: {', '.join(extra_top)}")
    if missing_top:
        raise EvidenceError(f"bundle missing fields: {', '.join(missing_top)}")

    opportunity_id = require_text(bundle["opportunity_id"], "opportunity_id")
    if opportunity_id != "R-C08-KY-AI-WORKFORCE-2026":
        raise EvidenceError("opportunity_id must be R-C08-KY-AI-WORKFORCE-2026")
    evaluated_on = _parse_date(bundle["evaluated_on"], "evaluated_on")

    partner = require_object(bundle["partner"], "partner")
    partner_allowed = {
        "legal_name",
        "role",
        "commitment_status",
        "commitment_evidence",
        "relevant_experience_years",
        "experience_evidence",
    }
    if set(partner) - partner_allowed:
        raise EvidenceError("partner contains unsupported fields")
    if partner_allowed - set(partner):
        raise EvidenceError("partner missing required fields")
    legal_name = require_text(partner["legal_name"], "partner.legal_name")
    role = require_text(partner["role"], "partner.role")
    if role not in ALLOWED_ROLES:
        raise EvidenceError(f"partner.role must be one of {sorted(ALLOWED_ROLES)}")
    commitment_status = require_text(partner["commitment_status"], "partner.commitment_status")
    if commitment_status not in {"pending", "confirmed", "declined"}:
        raise EvidenceError("partner.commitment_status must be pending, confirmed, or declined")
    commitment_receipt = _validate_receipt(
        partner["commitment_evidence"],
        "partner.commitment_evidence",
        allowed_kinds={"partner_reply", "signed_letter"},
    )
    years = partner["relevant_experience_years"]
    if (
        isinstance(years, bool)
        or not isinstance(years, (int, float))
        or not math.isfinite(float(years))
        or years < 0
    ):
        raise EvidenceError("partner.relevant_experience_years must be a finite non-negative number")
    experience_receipt = _validate_receipt(
        partner["experience_evidence"],
        "partner.experience_evidence",
        allowed_kinds={"capability_statement", "resume", "signed_letter"},
    )

    references = []
    seen_reference_contacts: set[str] = set()
    for idx, raw in enumerate(require_list(bundle["references"], "references")):
        path = f"references[{idx}]"
        obj = require_object(raw, path)
        required = {
            "client_label",
            "work_summary",
            "completed_on",
            "attributable_party",
            "permission_status",
            "contact_id",
            "evidence",
        }
        if set(obj) - required:
            raise EvidenceError(f"{path} contains unsupported fields")
        if required - set(obj):
            raise EvidenceError(f"{path} missing required fields")
        completed = _parse_date(obj["completed_on"], f"{path}.completed_on")
        permission = require_text(obj["permission_status"], f"{path}.permission_status")
        if permission not in {"pending", "confirmed", "declined"}:
            raise EvidenceError(f"{path}.permission_status must be pending, confirmed, or declined")
        if completed > evaluated_on:
            raise EvidenceError(f"{path}.completed_on cannot be after evaluated_on")
        contact_id = require_text(obj["contact_id"], f"{path}.contact_id")
        if contact_id in seen_reference_contacts:
            raise EvidenceError(f"{path}.contact_id duplicates another reference")
        seen_reference_contacts.add(contact_id)
        references.append(
            {
                "client_label": require_text(obj["client_label"], f"{path}.client_label"),
                "work_summary": require_text(obj["work_summary"], f"{path}.work_summary"),
                "completed_on": completed,
                "attributable_party": require_text(obj["attributable_party"], f"{path}.attributable_party"),
                "permission_status": permission,
                "contact_id": contact_id,
                "evidence": _validate_receipt(
                    obj["evidence"],
                    f"{path}.evidence",
                    allowed_kinds={"reference_confirmation", "signed_letter"},
                ),
            }
        )

    instructors = []
    for idx, raw in enumerate(require_list(bundle["instructors"], "instructors")):
        path = f"instructors[{idx}]"
        obj = require_object(raw, path)
        required = {"name", "scopes", "modes", "availability_status", "evidence"}
        if set(obj) - required:
            raise EvidenceError(f"{path} contains unsupported fields")
        if required - set(obj):
            raise EvidenceError(f"{path} missing required fields")
        scopes = {require_text(x, f"{path}.scopes[]") for x in require_list(obj["scopes"], f"{path}.scopes")}
        modes = {require_text(x, f"{path}.modes[]") for x in require_list(obj["modes"], f"{path}.modes")}
        unknown_scopes = sorted(scopes - REQUIRED_SCOPES)
        unknown_modes = sorted(modes - REQUIRED_MODES)
        if unknown_scopes:
            raise EvidenceError(f"{path}.scopes unsupported: {', '.join(unknown_scopes)}")
        if unknown_modes:
            raise EvidenceError(f"{path}.modes unsupported: {', '.join(unknown_modes)}")
        availability = require_text(obj["availability_status"], f"{path}.availability_status")
        if availability not in {"pending", "confirmed", "unavailable"}:
            raise EvidenceError(f"{path}.availability_status must be pending, confirmed, or unavailable")
        instructors.append(
            {
                "name": require_text(obj["name"], f"{path}.name"),
                "scopes": scopes,
                "modes": modes,
                "availability_status": availability,
                "evidence": _validate_receipt(
                    obj["evidence"],
                    f"{path}.evidence",
                    allowed_kinds={"resume", "capability_statement", "signed_letter"},
                ),
            }
        )

    operations = require_object(bundle["operations"], "operations")
    required_ops = {
        "kentucky_in_person_dispatch",
        "live_remote_delivery",
        "curriculum_rights",
        "accessibility_plan",
        "records_reporting_plan",
        "data_security_plan",
        "insurance_registration",
        "pricing_model",
        "travel_model",
    }
    if set(operations) - required_ops:
        raise EvidenceError("operations contains unsupported fields")
    if required_ops - set(operations):
        raise EvidenceError("operations missing required fields")
    expected_op_kinds = {
        "kentucky_in_person_dispatch": {"travel_plan", "signed_letter"},
        "live_remote_delivery": {"capability_statement", "signed_letter"},
        "curriculum_rights": {"curriculum", "signed_letter"},
        "accessibility_plan": {"accessibility_plan", "policy"},
        "records_reporting_plan": {"records_plan", "policy"},
        "data_security_plan": {"data_security_plan", "policy"},
        "insurance_registration": {"insurance", "registration"},
        "pricing_model": {"pricing"},
        "travel_model": {"travel_plan", "pricing"},
    }
    normalized_ops: dict[str, dict[str, Any]] = {}
    for key in sorted(required_ops):
        path = f"operations.{key}"
        obj = require_object(operations[key], path)
        if set(obj) != {"status", "evidence"}:
            raise EvidenceError(f"{path} must contain exactly status and evidence")
        status = require_text(obj["status"], f"{path}.status")
        if status not in {"pending", "confirmed", "unavailable"}:
            raise EvidenceError(f"{path}.status must be pending, confirmed, or unavailable")
        normalized_ops[key] = {
            "status": status,
            "evidence": _validate_receipt(
                obj["evidence"],
                f"{path}.evidence",
                allowed_kinds=expected_op_kinds[key],
            ),
        }

    gates: list[GateResult] = []
    gates.append(
        _gate(
            "partner_commitment",
            commitment_status == "confirmed",
            f"{legal_name} commitment is {commitment_status}; role={role}",
        )
    )
    gates.append(
        _gate(
            "relevant_experience",
            float(years) >= 3,
            f"evidenced relevant experience: {years} years; minimum readiness threshold: 3",
        )
    )

    five_year_cutoff = _five_year_cutoff(evaluated_on)
    qualifying_refs = [
        item
        for item in references
        if item["permission_status"] == "confirmed"
        and item["completed_on"] >= five_year_cutoff
        and item["attributable_party"] == legal_name
    ]
    gates.append(
        _gate(
            "comparable_references",
            len(qualifying_refs) >= 3,
            f"{len(qualifying_refs)} attributable, permission-confirmed references completed on/after {five_year_cutoff.isoformat()}; need 3",
        )
    )

    confirmed_instructors = [item for item in instructors if item["availability_status"] == "confirmed"]
    scope_modes: dict[str, set[str]] = {scope: set() for scope in REQUIRED_SCOPES}
    for item in confirmed_instructors:
        for scope in item["scopes"]:
            scope_modes[scope].update(item["modes"])
    missing_coverage = {
        scope: sorted(REQUIRED_MODES - modes)
        for scope, modes in sorted(scope_modes.items())
        if not REQUIRED_MODES.issubset(modes)
    }
    gates.append(
        _gate(
            "instructor_scope_and_modality",
            not missing_coverage,
            "all six scopes have confirmed live-remote and in-person coverage"
            if not missing_coverage
            else f"missing confirmed mode coverage: {missing_coverage}",
        )
    )

    for key in sorted(required_ops):
        status = normalized_ops[key]["status"]
        gates.append(_gate(key, status == "confirmed", f"{key} status={status}"))

    missing_gates = [item.gate for item in gates if item.status != "PASS"]
    decision = "QUALIFIED_TEAMING" if not missing_gates else "HOLD_PARTNER_EVIDENCE"
    report_core = {
        "schema": "ky-ai-workforce-partner-evidence/v1",
        "opportunity_id": opportunity_id,
        "evaluated_on": evaluated_on.isoformat(),
        "partner": {"legal_name": legal_name, "role": role},
        "decision": decision,
        "gates": [item.to_dict() for item in gates],
        "missing_gates": missing_gates,
        "reference_summary": {"submitted": len(references), "qualifying": len(qualifying_refs)},
        "confirmed_instructor_count": len(confirmed_instructors),
        "authority": {
            "partner_commitment_proven_only_if_gate_passes": True,
            "proposal_authorized": False,
            "proposal_submitted": False,
            "buyer_acceptance": False,
            "contract_awarded": False,
            "payment_received": False,
            "recognized_revenue": False,
        },
        "evidence_receipt_count": (
            2
            + len(references)
            + len(instructors)
            + len(normalized_ops)
        ),
    }
    if input_sha256 is not None:
        if not SHA256_RE.fullmatch(input_sha256):
            raise EvidenceError("input_sha256 must be 64 lowercase hex characters")
        report_core["input_sha256"] = input_sha256
    report_sha256 = hashlib.sha256(_canonical_bytes(report_core)).hexdigest()
    return {**report_core, "report_sha256": report_sha256}
