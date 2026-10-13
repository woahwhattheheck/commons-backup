#!/usr/bin/env python3
"""Deterministic owner-internal response-pack compiler for Alcorn RFP #5588.

This module can report internal owner readiness. It cannot authorize buyer/partner
contact, pricing release, signature, certification, proposal submission, contract
acceptance, payment mutation, award, cash, or revenue recognition.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any, Iterable


class ContractError(ValueError):
    """Raised when a source or response-pack invariant is violated."""


EXPECTED_BUYER = "Alcorn State University"
EXPECTED_RFP = "5588"
EXPECTED_TITLE = "AI Proficiency Labs"
EXPECTED_DUE = "2026-09-21T14:00:00-05:00"
EXPECTED_PACKET_SHA = "107f0cc3ae880e4000ad89f0d6db6ad4908600afcdafcaf8d66ff4303170f688"
EXPECTED_ADDENDUM_SHA = "82a26f82092e9de91f3e10f985bf9811983f122127fb15d35c9b2f746da72886"
EXPECTED_ADDENDUM_EFFECT = "PROPOSAL_STRUCTURE_DISCRETION_MINIMUM_SPEC_FLOOR"

EXPECTED_MISSING_BUYER_ARTIFACTS = {
    "section_viii_cost_information",
    "section_ix_references",
    "section_vii_item_12_requirements_matrix",
}

EXPECTED_SCORING = {
    "solution_fit": 25,
    "required_services": 20,
    "value_added": 10,
    "references": 10,
    "lifecycle_cost": 35,
    "non_cost_elimination_floor_percent": 80,
}

EXPECTED_GATE_IDS = {
    "valid_nvidia_partner",
    "ai_infrastructure_track_record",
    "training_sample",
    "dgx_spark_lab_design",
    "acceptance_and_facility_training",
    "one_year_hw_sw_warranty",
    "first_year_onsite_support_in_cost",
    "reference_site_on_request",
    "certificate_of_liability_insurance",
    "everify_documentation",
    "taxpayer_id",
    "order_and_remit_address",
    "amendments_review",
    "pricing_approval",
    "blue_ink_officer_signature",
    "sealed_physical_delivery",
}

AUTHORITY_KEYS = {
    "buyer_contact_authorized",
    "partner_contact_authorized",
    "price_release_authorized",
    "signature_authorized",
    "certification_authorized",
    "proposal_submission_authorized",
    "contract_acceptance_authorized",
    "payment_mutation_authorized",
    "award_claimed",
    "cash_claimed",
    "revenue_claimed",
}

REQUIRED_ARTIFACTS = {
    "compliance_matrix.md": (
        "Current decision",
        "MISSING_BUYER_ARTIFACT",
        "80% of non-cost requirements",
    ),
    "technical_approach.md": (
        "Design objective",
        "Acceptance model",
        "Release gates",
    ),
    "implementation_training_support.md": (
        "Phase 0",
        "Training workstream",
        "No-release rule",
    ),
    "responsibility_matrix.md": (
        "Non-inheritance rules",
        "AUTHORIZED OFFICER ONLY",
        "NEVER AUTHORIZED BY THIS PACK",
    ),
    "pricing_basis.json": (),
    "risk_redline_questions.md": (
        "three buyer-controlled response artifacts are absent",
        "NVIDIA partner authority is unproven",
        "Closure rule",
    ),
    "sealed_package_checklist.md": (
        "Controlling-source gate",
        "Last-inch authority fence",
        "Current truth",
    ),
}

READY_QUALIFICATION_STATES = {"PRIME_READY", "TEAMING_READY"}
ALLOWED_QUALIFICATION_STATES = READY_QUALIFICATION_STATES | {"HOLD", "NO_BID"}
ALLOWED_ARTIFACT_STATUSES = {"PREPARED_INTERNAL", "OWNER_INPUT_REQUIRED"}

OWNER_POLICY_BOOL_KEYS = {
    "qualification_must_be_ready",
    "qualification_blockers_must_be_empty",
    "all_response_artifacts_must_be_prepared",
    "pricing_must_be_owner_approved",
    "signature_officer_must_be_ready",
    "legal_entity_evidence_must_be_bound",
    "insurance_must_be_current",
    "everify_evidence_must_be_bound",
    "taxpayer_id_confirmation_must_be_bound",
    "order_and_remit_address_must_be_bound",
    "sealed_delivery_plan_must_be_ready",
}
OWNER_GATE_STATUS_KEYS = OWNER_POLICY_BOOL_KEYS - {
    "qualification_must_be_ready",
    "qualification_blockers_must_be_empty",
    "all_response_artifacts_must_be_prepared",
}


def _pairs_no_duplicates(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_float(value: str) -> None:
    raise ContractError(f"floating-point JSON numbers are not allowed: {value}")


def _parse_int(value: str) -> int:
    if len(value.lstrip("-")) > 18:
        raise ContractError("oversized JSON integer")
    return int(value)


def _reject_constant(value: str) -> None:
    raise ContractError(f"non-finite JSON constant is not allowed: {value}")


def load_json(path: Path) -> Any:
    data = path.read_bytes()
    if len(data) > 1_000_000:
        raise ContractError(f"JSON input too large: {path}")
    if b"\x00" in data:
        raise ContractError(f"NUL byte in JSON input: {path}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError(f"non-UTF-8 JSON input: {path}") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_float=_reject_float,
            parse_int=_parse_int,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON in {path}: {exc}") from exc


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be an object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractError(f"{label} must be an array")
    return value


def _require_exact_false_map(value: Any, label: str) -> dict[str, Any]:
    obj = _require_dict(value, label)
    if set(obj) != AUTHORITY_KEYS:
        missing = sorted(AUTHORITY_KEYS - set(obj))
        extra = sorted(set(obj) - AUTHORITY_KEYS)
        raise ContractError(f"{label} authority-key drift: missing={missing} extra={extra}")
    true_keys = sorted(k for k, v in obj.items() if v is not False)
    if true_keys:
        raise ContractError(f"{label} may not grant external authority: {true_keys}")
    return obj


def validate_spec(spec: Any) -> set[str]:
    obj = _require_dict(spec, "qualification spec")
    if obj.get("schema") != "alcorn-rfp5588-qualification-spec/v1":
        raise ContractError("unexpected qualification spec schema")

    opp = _require_dict(obj.get("opportunity"), "opportunity")
    expected_opp = {
        "buyer": EXPECTED_BUYER,
        "rfp": EXPECTED_RFP,
        "title": EXPECTED_TITLE,
        "due_at": EXPECTED_DUE,
    }
    for key, expected in expected_opp.items():
        if opp.get(key) != expected:
            raise ContractError(f"opportunity {key} drift")
    if opp.get("submission_mode") != "sealed physical package plus searchable USB":
        raise ContractError("submission mode drift")

    packet = _require_dict(obj.get("source_packet"), "source_packet")
    if packet.get("sha256") != EXPECTED_PACKET_SHA:
        raise ContractError("primary buyer packet digest drift")
    if packet.get("gmail_message_id") != "1a0a0186cbd89b53":
        raise ContractError("primary buyer packet message identity drift")
    if packet.get("filename") != "RFP#5588 NVIDIA v3.pdf" or packet.get("page_count") != 41:
        raise ContractError("primary buyer packet metadata drift")

    addenda = _require_list(obj.get("buyer_addenda"), "buyer_addenda")
    matches = [a for a in addenda if isinstance(a, dict) and a.get("id") == "addendum_1"]
    if len(matches) != 1:
        raise ContractError("exactly one Addendum 1 source binding is required")
    addendum = matches[0]
    if addendum.get("sha256") != EXPECTED_ADDENDUM_SHA:
        raise ContractError("Addendum 1 digest drift")
    if addendum.get("gmail_message_id") != "1a0a703662d0e19f":
        raise ContractError("Addendum 1 message identity drift")
    if addendum.get("normalized_effect") != EXPECTED_ADDENDUM_EFFECT:
        raise ContractError("Addendum 1 semantic drift")

    received = _require_dict(obj.get("received_packet_structure"), "received_packet_structure")
    absent_rows = _require_list(received.get("referenced_but_absent"), "referenced_but_absent")
    absent_ids = {
        row.get("id")
        for row in absent_rows
        if isinstance(row, dict) and row.get("status") == "MISSING_BUYER_ARTIFACT"
    }
    if absent_ids != EXPECTED_MISSING_BUYER_ARTIFACTS:
        raise ContractError("missing buyer-artifact set drift")

    gates = _require_list(obj.get("normalized_buyer_gates"), "normalized_buyer_gates")
    gate_ids = {row.get("id") for row in gates if isinstance(row, dict)}
    if gate_ids != EXPECTED_GATE_IDS:
        raise ContractError("normalized buyer-gate set drift")

    scoring = _require_dict(obj.get("scoring"), "scoring")
    if scoring != EXPECTED_SCORING:
        raise ContractError("buyer scoring model drift")
    if sum(scoring[k] for k in ("solution_fit", "required_services", "value_added", "references", "lifecycle_cost")) != 100:
        raise ContractError("score weights must sum to 100")

    _require_exact_false_map(obj.get("authority_ceiling"), "qualification spec")
    return absent_ids


def validate_qualification_result(result: Any) -> None:
    obj = _require_dict(result, "qualification result")
    if obj.get("schema") != "alcorn-rfp5588-qualification-result/v1":
        raise ContractError("unexpected qualification-result schema")
    state = obj.get("state")
    if state not in ALLOWED_QUALIFICATION_STATES:
        raise ContractError(f"unexpected qualification state: {state!r}")
    if obj.get("due_at") != EXPECTED_DUE:
        raise ContractError("qualification due date drift")
    _require_exact_false_map(obj.get("authority"), "qualification result")

    missing = set(_require_list(obj.get("missing_buyer_artifacts"), "missing_buyer_artifacts"))
    if state in READY_QUALIFICATION_STATES and missing:
        raise ContractError("ready qualification state may not retain missing buyer artifacts")
    if state != "NO_BID" and not EXPECTED_MISSING_BUYER_ARTIFACTS.issubset(missing):
        raise ContractError("qualification result hides a known missing buyer artifact")

    blockers = _require_list(obj.get("blockers"), "qualification blockers")
    if state in READY_QUALIFICATION_STATES and blockers:
        raise ContractError("ready qualification state may not retain blockers")

    receipt = obj.get("receipt_sha256")
    if not isinstance(receipt, str) or len(receipt) != 64 or any(ch not in "0123456789abcdef" for ch in receipt):
        raise ContractError("qualification result receipt_sha256 must be lowercase SHA-256 hex")

    findings = _require_dict(obj.get("source_findings"), "source_findings")
    addendum = _require_dict(findings.get("addendum_1"), "source_findings.addendum_1")
    if addendum.get("sha256") != EXPECTED_ADDENDUM_SHA:
        raise ContractError("qualification result Addendum 1 digest drift")
    if addendum.get("normalized_effect") != EXPECTED_ADDENDUM_EFFECT:
        raise ContractError("qualification result Addendum 1 semantic drift")
    if addendum.get("vendor_proposal_structure_discretion") is not True:
        raise ContractError("Addendum 1 proposal-structure finding drift")
    if addendum.get("minimum_specifications_still_required") is not True:
        raise ContractError("Addendum 1 minimum-specification floor drift")
    if addendum.get("nvidia_oem_authority_granted") is not False:
        raise ContractError("Addendum 1 may not grant NVIDIA/OEM authority")
    if addendum.get("partner_credentials_inherited") is not False:
        raise ContractError("Addendum 1 may not inherit partner credentials")


def _evaluate_upstream(parent: Path, spec: dict[str, Any], evidence: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    parent = parent.resolve()
    qualification_path = (parent / "qualification.py").resolve()
    guarded_path = (parent / "qualification_guarded.py").resolve()
    if qualification_path.parent != parent or guarded_path.parent != parent:
        raise ContractError("upstream qualification paths escaped canonical parent")
    if not qualification_path.is_file() or not guarded_path.is_file():
        raise ContractError("canonical upstream qualification implementation is missing")

    token = sha256_bytes(str(parent).encode("utf-8"))[:16]
    package_name = f"_alcorn_rfp5588_upstream_{token}"
    base_name = f"{package_name}.qualification"
    guarded_name = f"{package_name}.qualification_guarded"
    created_names = [guarded_name, base_name, package_name]

    package = types.ModuleType(package_name)
    package.__package__ = package_name
    package.__path__ = [str(parent)]
    sys.modules[package_name] = package
    try:
        base_spec = importlib.util.spec_from_file_location(base_name, qualification_path)
        if base_spec is None or base_spec.loader is None:
            raise ContractError("cannot load canonical qualification.py")
        base = importlib.util.module_from_spec(base_spec)
        sys.modules[base_name] = base
        base_spec.loader.exec_module(base)
        if Path(base.__file__).resolve() != qualification_path:
            raise ContractError("canonical qualification module path mismatch")

        guarded_spec = importlib.util.spec_from_file_location(guarded_name, guarded_path)
        if guarded_spec is None or guarded_spec.loader is None:
            raise ContractError("cannot load canonical qualification_guarded.py")
        guarded = importlib.util.module_from_spec(guarded_spec)
        sys.modules[guarded_name] = guarded
        guarded_spec.loader.exec_module(guarded)
        if Path(guarded.__file__).resolve() != guarded_path:
            raise ContractError("canonical guarded qualification module path mismatch")

        try:
            expected = guarded.evaluate(spec, evidence)
        except Exception as exc:
            raise ContractError(f"canonical upstream qualification evaluation failed: {exc}") from exc
        if not isinstance(expected, dict):
            raise ContractError("canonical upstream qualification did not return an object")
        expected = dict(expected)
        expected["receipt_sha256"] = guarded.canonical_digest(expected)
        hashes = {
            "qualification.py": sha256_file(qualification_path),
            "qualification_guarded.py": sha256_file(guarded_path),
        }
        return expected, hashes
    finally:
        for name in created_names:
            sys.modules.pop(name, None)


def authenticate_qualification(parent: Path, spec: dict[str, Any], evidence: dict[str, Any], result: dict[str, Any]) -> dict[str, str]:
    expected, hashes = _evaluate_upstream(parent, spec, evidence)
    if result != expected:
        raise ContractError("canonical qualification result is not an authenticated replay of current evidence")
    return hashes


def validate_plan(plan: Any) -> bool:
    obj = _require_dict(plan, "response plan")
    if obj.get("schema") != "alcorn-rfp5588-response-plan/v1":
        raise ContractError("unexpected response-plan schema")
    opp = _require_dict(obj.get("opportunity"), "response-plan opportunity")
    for key, expected in {
        "buyer": EXPECTED_BUYER,
        "rfp": EXPECTED_RFP,
        "title": EXPECTED_TITLE,
        "due_at": EXPECTED_DUE,
    }.items():
        if opp.get(key) != expected:
            raise ContractError(f"response-plan opportunity {key} drift")

    bindings = _require_dict(obj.get("source_bindings"), "source_bindings")
    if bindings.get("qualification_spec") != "../qualification_spec.json":
        raise ContractError("response plan must use canonical qualification spec")
    if bindings.get("qualification_result") != "../current_result.json":
        raise ContractError("response plan must use canonical qualification result")
    if bindings.get("primary_packet_sha256") != EXPECTED_PACKET_SHA:
        raise ContractError("response-plan packet binding drift")
    if bindings.get("addendum_1_sha256") != EXPECTED_ADDENDUM_SHA:
        raise ContractError("response-plan addendum binding drift")

    rows = _require_list(obj.get("artifacts"), "response-plan artifacts")
    by_path: dict[str, str] = {}
    for row in rows:
        item = _require_dict(row, "response-plan artifact")
        path = item.get("path")
        status = item.get("status")
        if not isinstance(path, str) or path in by_path:
            raise ContractError("artifact paths must be unique strings")
        if status not in ALLOWED_ARTIFACT_STATUSES:
            raise ContractError(f"invalid artifact status for {path}: {status}")
        by_path[path] = status
    if set(by_path) != set(REQUIRED_ARTIFACTS):
        raise ContractError("required response-artifact set drift")

    policy = _require_dict(obj.get("owner_gate_policy"), "owner_gate_policy")
    expected_policy_keys = OWNER_POLICY_BOOL_KEYS | {"qualification_states_that_may_enter_owner_ready"}
    if set(policy) != expected_policy_keys:
        missing = sorted(expected_policy_keys - set(policy))
        extra = sorted(set(policy) - expected_policy_keys)
        raise ContractError(f"owner_gate_policy key drift: missing={missing} extra={extra}")
    for key in sorted(OWNER_POLICY_BOOL_KEYS):
        if policy.get(key) is not True:
            raise ContractError(f"owner_gate_policy.{key} must remain true")
    states = policy.get("qualification_states_that_may_enter_owner_ready")
    if not isinstance(states, list) or set(states) != READY_QUALIFICATION_STATES:
        raise ContractError("owner-ready qualification-state policy drift")

    _require_exact_false_map(obj.get("authority_ceiling"), "response plan")
    return all(status == "PREPARED_INTERNAL" for status in by_path.values())


def _validate_text_artifact(path: Path, anchors: tuple[str, ...]) -> None:
    data = path.read_bytes()
    if len(data) < 600:
        raise ContractError(f"response artifact too small to be substantive: {path.name}")
    if len(data) > 500_000 or b"\x00" in data:
        raise ContractError(f"invalid response artifact bytes: {path.name}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError(f"response artifact is not UTF-8: {path.name}") from exc
    missing = [anchor for anchor in anchors if anchor not in text]
    if missing:
        raise ContractError(f"response artifact {path.name} lost required anchors: {missing}")


def _walk_numbers(value: Any, prefix: str = "pricing") -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, (int, float)):
        raise ContractError(f"public pricing basis contains numeric value at {prefix}")
    if isinstance(value, list):
        for index, child in enumerate(value):
            _walk_numbers(child, f"{prefix}[{index}]")
        return
    if isinstance(value, dict):
        for key, child in value.items():
            _walk_numbers(child, f"{prefix}.{key}")
        return
    raise ContractError(f"unsupported pricing value at {prefix}")


def _evidence_id_present(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().upper() not in {"MISSING", "UNKNOWN", "UNCONFIRMED"}


def validate_pricing_basis(pricing: Any) -> dict[str, Any]:
    obj = _require_dict(pricing, "pricing basis")
    if obj.get("schema") != "alcorn-rfp5588-pricing-basis/v1":
        raise ContractError("unexpected pricing-basis schema")
    if obj.get("customer_price_amount") is not None:
        raise ContractError("public pricing basis may not contain a customer price amount")
    if obj.get("customer_price_released") is not False:
        raise ContractError("internal pricing basis may not release a customer price")
    if not isinstance(obj.get("pricing_approved"), bool):
        raise ContractError("pricing_approved must be a boolean")
    if not isinstance(obj.get("buyer_cost_form_present"), bool):
        raise ContractError("buyer_cost_form_present must be a boolean")
    evidence_id = obj.get("pricing_approval_evidence_id")
    if obj["pricing_approved"]:
        if not _evidence_id_present(evidence_id):
            raise ContractError("approved pricing basis requires a source-bound pricing approval evidence id")
        if not obj["buyer_cost_form_present"]:
            raise ContractError("approved pricing basis requires the controlling buyer cost form")
    elif evidence_id is not None:
        raise ContractError("unapproved pricing basis may not carry a pricing approval evidence id")
    buckets = _require_list(obj.get("cost_buckets"), "pricing cost_buckets")
    if len(buckets) < 8:
        raise ContractError("pricing basis must cover the major lifecycle-cost buckets")
    _walk_numbers(obj)
    return obj


def validate_artifacts(root: Path) -> tuple[bool, dict[str, str], dict[str, Any]]:
    hashes: dict[str, str] = {}
    pricing: dict[str, Any] | None = None
    for rel, anchors in REQUIRED_ARTIFACTS.items():
        path = root / rel
        if not path.is_file():
            raise ContractError(f"required response artifact missing: {rel}")
        if rel == "pricing_basis.json":
            pricing = validate_pricing_basis(load_json(path))
        else:
            _validate_text_artifact(path, anchors)
        hashes[rel] = sha256_file(path)
    if pricing is None:
        raise ContractError("pricing basis was not validated")
    return True, hashes, pricing


def _owner_entity(evidence: dict[str, Any]) -> dict[str, Any]:
    bid_model = evidence.get("bid_model")
    if bid_model == "direct_prime":
        return _require_dict(evidence.get("direct_prime"), "direct_prime")
    if bid_model == "nvidia_prime_subcontract":
        return _require_dict(evidence.get("nvidia_prime"), "nvidia_prime")
    raise ContractError(f"unsupported bid_model for owner-gate evaluation: {bid_model!r}")


def _parse_date(value: Any, label: str) -> dt.date | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def owner_gate_status(evidence: dict[str, Any], pricing: dict[str, Any]) -> dict[str, bool]:
    entity = _owner_entity(evidence)
    due = dt.datetime.fromisoformat(EXPECTED_DUE).date()
    insurance_expiry = _parse_date(entity.get("insurance_expires_date"), "insurance_expires_date")

    upstream_price_approved = entity.get("pricing_approved") is True
    upstream_price_evidence = entity.get("pricing_approval_evidence_id")
    local_price_evidence = pricing.get("pricing_approval_evidence_id")
    pricing_ready = (
        upstream_price_approved
        and _evidence_id_present(upstream_price_evidence)
        and pricing.get("pricing_approved") is True
        and pricing.get("buyer_cost_form_present") is True
        and local_price_evidence == upstream_price_evidence
    )

    status = {
        "pricing_must_be_owner_approved": pricing_ready,
        "signature_officer_must_be_ready": (
            entity.get("signature_officer_ready") is True
            and _evidence_id_present(entity.get("signature_officer_evidence_id"))
        ),
        "legal_entity_evidence_must_be_bound": _evidence_id_present(entity.get("legal_entity_evidence_id")),
        "insurance_must_be_current": (
            _evidence_id_present(entity.get("certificate_of_liability_insurance_evidence_id"))
            and insurance_expiry is not None
            and insurance_expiry >= due
        ),
        "everify_evidence_must_be_bound": _evidence_id_present(entity.get("everify_evidence_id")),
        "taxpayer_id_confirmation_must_be_bound": _evidence_id_present(entity.get("taxpayer_id_confirmation_evidence_id")),
        "order_and_remit_address_must_be_bound": _evidence_id_present(entity.get("order_remit_address_evidence_id")),
        "sealed_delivery_plan_must_be_ready": (
            entity.get("sealed_delivery_plan_ready") is True
            and _evidence_id_present(entity.get("sealed_delivery_plan_evidence_id"))
        ),
    }
    if set(status) != OWNER_GATE_STATUS_KEYS:
        raise ContractError("internal owner-gate status key drift")
    return status


def compile_pack(root: Path | None = None) -> dict[str, Any]:
    root = (root or Path(__file__).resolve().parent).resolve()
    parent = root.parent

    spec_path = parent / "qualification_spec.json"
    evidence_path = parent / "current_evidence.json"
    result_path = parent / "current_result.json"
    plan_path = root / "response_plan.json"

    spec = load_json(spec_path)
    evidence = load_json(evidence_path)
    result = load_json(result_path)
    plan = load_json(plan_path)
    source_missing = validate_spec(spec)
    validate_qualification_result(result)
    upstream_hashes = authenticate_qualification(parent, spec, evidence, result)
    all_prepared = validate_plan(plan)
    artifacts_valid, artifact_hashes, pricing = validate_artifacts(root)
    owner_status = owner_gate_status(evidence, pricing)

    blockers = list(result.get("blockers", []))
    qualification_state = result["state"]
    result_missing = set(result.get("missing_buyer_artifacts", []))
    qualification_ready = qualification_state in READY_QUALIFICATION_STATES and not blockers and not result_missing
    source_buyer_artifacts_resolved = not source_missing
    owner_gates_ready = all(owner_status.values())

    if not qualification_ready:
        state = "HOLD_QUALIFICATION"
        reason = "canonical_authenticated_qualification_not_ready"
    elif not source_buyer_artifacts_resolved:
        state = "HOLD_BUYER_ARTIFACTS"
        reason = "canonical_source_model_still_records_missing_buyer_artifacts"
    elif not (all_prepared and artifacts_valid):
        state = "HOLD_RESPONSE_ARTIFACTS"
        reason = "response_artifacts_not_prepared"
    elif not owner_gates_ready:
        state = "HOLD_OWNER_GATES"
        reason = "source_backed_owner_gates_not_ready"
    else:
        state = "OWNER_READY_FOR_SUBMIT"
        reason = "internal_response_pack_complete_and_all_authenticated_owner_gates_ready"

    receipt: dict[str, Any] = {
        "schema": "alcorn-rfp5588-response-pack-result/v2",
        "buyer": EXPECTED_BUYER,
        "rfp": EXPECTED_RFP,
        "title": EXPECTED_TITLE,
        "due_at": EXPECTED_DUE,
        "state": state,
        "reason": reason,
        "qualification_state": qualification_state,
        "qualification_blockers": blockers,
        "qualification_authenticated_replay": True,
        "source_missing_buyer_artifacts": sorted(source_missing),
        "source_buyer_artifacts_resolved": source_buyer_artifacts_resolved,
        "owner_gate_status": dict(sorted(owner_status.items())),
        "owner_gates_ready": owner_gates_ready,
        "response_artifacts_prepared": bool(all_prepared and artifacts_valid),
        "input_hashes": {
            "qualification_spec.json": sha256_file(spec_path),
            "current_evidence.json": sha256_file(evidence_path),
            "current_result.json": sha256_file(result_path),
            "response_plan.json": sha256_file(plan_path),
        },
        "upstream_implementation_hashes": dict(sorted(upstream_hashes.items())),
        "artifact_hashes": dict(sorted(artifact_hashes.items())),
        "authority": {key: False for key in sorted(AUTHORITY_KEYS)},
        "authority_note": "internal readiness only; this result never authorizes an external action",
    }
    digest_input = dict(receipt)
    receipt["receipt_sha256"] = sha256_bytes(canonical_json(digest_input).encode("ascii"))
    return receipt


def verify_receipt(path: Path, root: Path | None = None) -> dict[str, Any]:
    supplied = load_json(path)
    current = compile_pack(root)
    if supplied != current:
        raise ContractError("receipt does not exactly match current canonical response-pack inputs")
    return current


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    compile_cmd = sub.add_parser("compile", help="compile the deterministic current response-pack receipt")
    compile_cmd.add_argument("--write", type=Path, help="also write canonical pretty JSON to this file")
    verify_cmd = sub.add_parser("verify", help="verify an existing receipt against canonical inputs")
    verify_cmd.add_argument("receipt", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.command == "compile":
            receipt = compile_pack()
            rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
            if args.write:
                args.write.write_text(rendered, encoding="utf-8")
            sys.stdout.write(rendered)
            return 0
        if args.command == "verify":
            receipt = verify_receipt(args.receipt)
            sys.stdout.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
            return 0
        raise ContractError("unsupported command")
    except (ContractError, OSError) as exc:
        print(f"response-pack contract error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
