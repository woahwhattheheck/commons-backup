from __future__ import annotations

from typing import Any

from .common import (
    ALLOWED_EVIDENCE_KINDS, ALLOWED_EVIDENCE_STATUS, GateError, SCHEMA, TRUTH_CEILING,
    _bool, _dt, _exact_keys, _id, _int, _list, _obj, _parse_source, _str, _unique, _z,
    ensure_unicode_scalars,
)


def _require_generation_identity(identifier: str, generation: int, where: str) -> None:
    stem, sep, suffix = identifier.rpartition("-")
    if not sep or not stem or not suffix.isdigit() or int(suffix) != generation:
        raise GateError(f"{where}: id must end in -<generation> and bind the declared generation")


def normalize(raw: Any) -> dict[str, Any]:
    ensure_unicode_scalars(raw)
    root = _obj(raw, "root")
    allowed_root = {"schema", "engagement", "sources", "evidence", "commercial_baseline", "change_orders", "milestones", "payments", "support_findings", "gaps", "renewal_window", "expansion_hypotheses", "communication"}
    _exact_keys(root, allowed_root, "root", allowed_root)
    if root["schema"] != SCHEMA:
        raise GateError(f"schema: expected {SCHEMA}")

    eng = _obj(root["engagement"], "engagement")
    _exact_keys(eng, {"id", "organization_id", "label", "generation"}, "engagement", {"id", "organization_id", "label", "generation"})
    engagement = {"id": _id(eng["id"], "engagement.id"), "organization_id": _id(eng["organization_id"], "engagement.organization_id"), "label": _str(eng["label"], "engagement.label"), "generation": _int(eng["generation"], "engagement.generation", 1)}

    sources = [_parse_source(item, f"sources[{i}]") for i, item in enumerate(_list(root["sources"], "sources"))]
    _unique([x["id"] for x in sources], "sources")
    source_ids = {x["id"] for x in sources}

    evidence: list[dict[str, Any]] = []
    for i, item in enumerate(_list(root["evidence"], "evidence")):
        where = f"evidence[{i}]"
        obj = _obj(item, where)
        allowed = {"id", "kind", "subject_id", "source_id", "status", "observed_at", "valid_through", "summary"}
        _exact_keys(obj, allowed, where, allowed - {"valid_through"})
        kind = _str(obj["kind"], f"{where}.kind").upper()
        if kind not in ALLOWED_EVIDENCE_KINDS:
            raise GateError(f"{where}.kind: unsupported")
        status_value = _str(obj["status"], f"{where}.status").upper()
        if status_value not in ALLOWED_EVIDENCE_STATUS:
            raise GateError(f"{where}.status: unsupported")
        source_id = _id(obj["source_id"], f"{where}.source_id")
        if source_id not in source_ids:
            raise GateError(f"{where}.source_id: unknown source")
        row = {"id": _id(obj["id"], f"{where}.id"), "kind": kind, "subject_id": _id(obj["subject_id"], f"{where}.subject_id"), "source_id": source_id, "status": status_value, "observed_at": _z(_dt(obj["observed_at"], f"{where}.observed_at")), "summary": _str(obj["summary"], f"{where}.summary")}
        if obj.get("valid_through") is not None:
            row["valid_through"] = _z(_dt(obj["valid_through"], f"{where}.valid_through"))
        evidence.append(row)
    _unique([x["id"] for x in evidence], "evidence")
    evidence_ids = {x["id"] for x in evidence}

    def evidence_ref(value: Any, where: str) -> str:
        eid = _id(value, where)
        if eid not in evidence_ids:
            raise GateError(f"{where}: unknown evidence id")
        return eid

    base = _obj(root["commercial_baseline"], "commercial_baseline")
    _exact_keys(base, {"id", "generation", "acceptance_evidence_id"}, "commercial_baseline", {"id", "generation", "acceptance_evidence_id"})
    commercial_baseline = {"id": _id(base["id"], "commercial_baseline.id"), "generation": _int(base["generation"], "commercial_baseline.generation", 1), "acceptance_evidence_id": evidence_ref(base["acceptance_evidence_id"], "commercial_baseline.acceptance_evidence_id")}
    if commercial_baseline["generation"] != engagement["generation"]:
        raise GateError("commercial_baseline.generation must match engagement.generation")
    _require_generation_identity(commercial_baseline["id"], commercial_baseline["generation"], "commercial_baseline.id")

    change_orders: list[dict[str, Any]] = []
    for i, item in enumerate(_list(root["change_orders"], "change_orders")):
        where = f"change_orders[{i}]"
        obj = _obj(item, where)
        allowed = {"id", "generation", "state", "approval_evidence_id"}
        _exact_keys(obj, allowed, where, allowed)
        state_value = _str(obj["state"], f"{where}.state").upper()
        if state_value not in {"APPROVED", "PROPOSED", "REJECTED"}:
            raise GateError(f"{where}.state: unsupported")
        row = {"id": _id(obj["id"], f"{where}.id"), "generation": _int(obj["generation"], f"{where}.generation", 1), "state": state_value, "approval_evidence_id": evidence_ref(obj["approval_evidence_id"], f"{where}.approval_evidence_id")}
        _require_generation_identity(row["id"], row["generation"], f"{where}.id")
        change_orders.append(row)
    _unique([x["id"] for x in change_orders], "change_orders")

    milestones: list[dict[str, Any]] = []
    for i, item in enumerate(_list(root["milestones"], "milestones")):
        where = f"milestones[{i}]"; obj = _obj(item, where); allowed = {"id", "required", "state", "acceptance_evidence_id"}; _exact_keys(obj, allowed, where, allowed)
        state_value = _str(obj["state"], f"{where}.state").upper()
        if state_value not in {"NOT_STARTED", "IN_PROGRESS", "DELIVERED", "ACCEPTED"}: raise GateError(f"{where}.state: unsupported")
        milestones.append({"id": _id(obj["id"], f"{where}.id"), "required": _bool(obj["required"], f"{where}.required"), "state": state_value, "acceptance_evidence_id": evidence_ref(obj["acceptance_evidence_id"], f"{where}.acceptance_evidence_id")})
    _unique([x["id"] for x in milestones], "milestones")

    payments: list[dict[str, Any]] = []
    for i, item in enumerate(_list(root["payments"], "payments")):
        where = f"payments[{i}]"; obj = _obj(item, where); allowed = {"id", "required_for_renewal", "state", "settlement_evidence_id"}; _exact_keys(obj, allowed, where, allowed)
        state_value = _str(obj["state"], f"{where}.state").upper()
        if state_value not in {"NOT_INVOICED", "INVOICED", "PAYMENT_LINK_SENT", "SETTLED", "DISPUTED", "WRITTEN_OFF"}: raise GateError(f"{where}.state: unsupported")
        payments.append({"id": _id(obj["id"], f"{where}.id"), "required_for_renewal": _bool(obj["required_for_renewal"], f"{where}.required_for_renewal"), "state": state_value, "settlement_evidence_id": evidence_ref(obj["settlement_evidence_id"], f"{where}.settlement_evidence_id")})
    _unique([x["id"] for x in payments], "payments")

    findings: list[dict[str, Any]] = []
    for i, item in enumerate(_list(root["support_findings"], "support_findings")):
        where = f"support_findings[{i}]"; obj = _obj(item, where); allowed = {"id", "category", "state", "summary", "evidence_id"}; _exact_keys(obj, allowed, where, allowed)
        state_value = _str(obj["state"], f"{where}.state").upper()
        if state_value not in {"OPEN", "CLOSED", "OBSERVED"}: raise GateError(f"{where}.state: unsupported")
        findings.append({"id": _id(obj["id"], f"{where}.id"), "category": _id(obj["category"], f"{where}.category"), "state": state_value, "summary": _str(obj["summary"], f"{where}.summary"), "evidence_id": evidence_ref(obj["evidence_id"], f"{where}.evidence_id")})
    _unique([x["id"] for x in findings], "support_findings")

    gaps: list[dict[str, Any]] = []
    for i, item in enumerate(_list(root["gaps"], "gaps")):
        where = f"gaps[{i}]"; obj = _obj(item, where); allowed = {"id", "kind", "blocking", "state", "evidence_id"}; _exact_keys(obj, allowed, where, allowed)
        kind = _str(obj["kind"], f"{where}.kind").upper()
        if kind not in {"SECURITY", "DATA", "OTHER"}: raise GateError(f"{where}.kind: unsupported")
        state_value = _str(obj["state"], f"{where}.state").upper()
        if state_value not in {"OPEN", "CLOSED"}: raise GateError(f"{where}.state: unsupported")
        gaps.append({"id": _id(obj["id"], f"{where}.id"), "kind": kind, "blocking": _bool(obj["blocking"], f"{where}.blocking"), "state": state_value, "evidence_id": evidence_ref(obj["evidence_id"], f"{where}.evidence_id")})
    _unique([x["id"] for x in gaps], "gaps")

    window = _obj(root["renewal_window"], "renewal_window"); allowed_window = {"open_at", "close_at", "evidence_id"}; _exact_keys(window, allowed_window, "renewal_window", allowed_window)
    open_at = _dt(window["open_at"], "renewal_window.open_at"); close_at = _dt(window["close_at"], "renewal_window.close_at")
    if not open_at < close_at: raise GateError("renewal_window: open_at must be before close_at")
    renewal_window = {"open_at": _z(open_at), "close_at": _z(close_at), "evidence_id": evidence_ref(window["evidence_id"], "renewal_window.evidence_id")}

    hypotheses: list[dict[str, Any]] = []
    for i, item in enumerate(_list(root["expansion_hypotheses"], "expansion_hypotheses")):
        where = f"expansion_hypotheses[{i}]"; obj = _obj(item, where); allowed = {"id", "statement", "state", "supporting_evidence_ids"}; _exact_keys(obj, allowed, where, allowed)
        if obj["state"] != TRUTH_CEILING: raise GateError(f"{where}.state: must remain {TRUTH_CEILING}")
        refs = [evidence_ref(x, f"{where}.supporting_evidence_ids") for x in _list(obj["supporting_evidence_ids"], f"{where}.supporting_evidence_ids")]
        hypotheses.append({"id": _id(obj["id"], f"{where}.id"), "statement": _str(obj["statement"], f"{where}.statement"), "state": TRUTH_CEILING, "supporting_evidence_ids": sorted(refs)})
    _unique([x["id"] for x in hypotheses], "expansion_hypotheses")

    communication = _obj(root["communication"], "communication"); allowed_comm = {"muse_key", "organization_id", "route_id", "send_state"}; _exact_keys(communication, allowed_comm, "communication", allowed_comm)
    send_state = _str(communication["send_state"], "communication.send_state").upper()
    if send_state != "NOT_AUTHORIZED": raise GateError("communication.send_state must be NOT_AUTHORIZED")
    normalized_communication = {"muse_key": _id(communication["muse_key"], "communication.muse_key"), "organization_id": _id(communication["organization_id"], "communication.organization_id"), "route_id": _id(communication["route_id"], "communication.route_id"), "send_state": send_state}
    if normalized_communication["organization_id"] != engagement["organization_id"]: raise GateError("communication.organization_id must match engagement.organization_id")

    return {"schema": SCHEMA, "engagement": engagement, "sources": sorted(sources, key=lambda x: x["id"]), "evidence": sorted(evidence, key=lambda x: x["id"]), "commercial_baseline": commercial_baseline, "change_orders": sorted(change_orders, key=lambda x: x["id"]), "milestones": sorted(milestones, key=lambda x: x["id"]), "payments": sorted(payments, key=lambda x: x["id"]), "support_findings": sorted(findings, key=lambda x: x["id"]), "gaps": sorted(gaps, key=lambda x: x["id"]), "renewal_window": renewal_window, "expansion_hypotheses": sorted(hypotheses, key=lambda x: x["id"]), "communication": normalized_communication}
