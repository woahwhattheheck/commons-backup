from __future__ import annotations

from datetime import datetime
from typing import Any

from .codec import (
    CASE_SCHEMA, MAX_SOURCES, MAX_TOOLS, GateInputError,
    _ALLOWED_APPROVAL_DECISIONS, _ALLOWED_CHANGE_STATES, _bool,
    _catalog_binding, _dict, _hex64, _identifier, _keys, _reference,
    _string, _utc, digest,
)

def _parse_case(raw: Any, policy: dict[str, Any], evaluated_dt: datetime) -> dict[str, Any]:
    obj = _dict(raw, "case")
    _keys(
        obj,
        {
            "schema",
            "case_id",
            "event_id",
            "artifact",
            "source_snapshots",
            "batch_context",
            "execution",
            "actor",
            "intended_use",
            "change_control",
            "human_approval",
            "captured_at",
        },
        "case",
    )
    if obj["schema"] != CASE_SCHEMA:
        raise GateInputError("unsupported case schema")
    case_id = _identifier(obj["case_id"], "case.case_id")
    captured_dt = _utc(obj["captured_at"], "case.captured_at")
    if captured_dt > evaluated_dt:
        raise GateInputError("case captured_at cannot be after trusted evaluation time")

    artifact = _dict(obj["artifact"], "case.artifact")
    _keys(artifact, {"artifact_id", "artifact_type", "sha256"}, "case.artifact")
    parsed_artifact = {
        "artifact_id": _identifier(artifact["artifact_id"], "case.artifact.artifact_id"),
        "artifact_type": _identifier(artifact["artifact_type"], "case.artifact.artifact_type"),
        "sha256": _hex64(artifact["sha256"], "case.artifact.sha256"),
    }

    sources_raw = obj["source_snapshots"]
    if type(sources_raw) is not list or not 1 <= len(sources_raw) <= MAX_SOURCES:
        raise GateInputError("case.source_snapshots cardinality is out of bounds")
    sources: list[dict[str, Any]] = []
    source_keys: set[tuple[str, str]] = set()
    for idx, raw_source in enumerate(sources_raw):
        source = _dict(raw_source, f"case.source_snapshots[{idx}]")
        _keys(
            source,
            {"dataset", "snapshot_id", "snapshot_sha256", "captured_at", "complete"},
            f"case.source_snapshots[{idx}]",
        )
        dataset = _catalog_binding(source["dataset"], f"case.source_snapshots[{idx}].dataset")
        snapshot_id = _identifier(source["snapshot_id"], f"case.source_snapshots[{idx}].snapshot_id")
        snapshot_captured = _utc(source["captured_at"], f"case.source_snapshots[{idx}].captured_at")
        if snapshot_captured > captured_dt:
            raise GateInputError("source snapshot cannot be captured after case")
        key = (dataset["id"], snapshot_id)
        if key in source_keys:
            raise GateInputError("duplicate dataset/snapshot identity")
        source_keys.add(key)
        sources.append(
            {
                "dataset": dataset,
                "snapshot_id": snapshot_id,
                "snapshot_sha256": _hex64(source["snapshot_sha256"], f"case.source_snapshots[{idx}].snapshot_sha256"),
                "captured_at": source["captured_at"],
                "complete": _bool(source["complete"], f"case.source_snapshots[{idx}].complete"),
            }
        )
    sources.sort(key=lambda item: (item["dataset"]["id"], item["snapshot_id"]))

    batch = _dict(obj["batch_context"], "case.batch_context")
    _keys(
        batch,
        {"standard", "site_id", "process_cell_id", "unit_id", "batch_id", "material_lot_id"},
        "case.batch_context",
    )
    parsed_batch = {
        "standard": _identifier(batch["standard"], "case.batch_context.standard"),
        "site_id": _identifier(batch["site_id"], "case.batch_context.site_id"),
        "process_cell_id": _identifier(batch["process_cell_id"], "case.batch_context.process_cell_id"),
        "unit_id": _identifier(batch["unit_id"], "case.batch_context.unit_id"),
        "batch_id": _identifier(batch["batch_id"], "case.batch_context.batch_id"),
        "material_lot_id": _identifier(batch["material_lot_id"], "case.batch_context.material_lot_id"),
    }

    execution = _dict(obj["execution"], "case.execution")
    _keys(
        execution,
        {"run_id", "model", "tools", "prompt_policy", "query_sha256", "result_sha256", "started_at", "completed_at"},
        "case.execution",
    )
    started = _utc(execution["started_at"], "case.execution.started_at")
    completed = _utc(execution["completed_at"], "case.execution.completed_at")
    if started > completed or completed > captured_dt:
        raise GateInputError("execution timestamps are not monotonic")
    tools_raw = execution["tools"]
    if type(tools_raw) is not list or not 1 <= len(tools_raw) <= MAX_TOOLS:
        raise GateInputError("case.execution.tools cardinality is out of bounds")
    tools = [_catalog_binding(tool, f"case.execution.tools[{i}]") for i, tool in enumerate(tools_raw)]
    tool_ids = [tool["id"] for tool in tools]
    if len(tool_ids) != len(set(tool_ids)):
        raise GateInputError("case.execution.tools contains duplicate tool ids")
    tools.sort(key=lambda item: item["id"])
    parsed_execution = {
        "run_id": _identifier(execution["run_id"], "case.execution.run_id"),
        "model": _catalog_binding(execution["model"], "case.execution.model"),
        "tools": tools,
        "prompt_policy": _catalog_binding(execution["prompt_policy"], "case.execution.prompt_policy"),
        "query_sha256": _hex64(execution["query_sha256"], "case.execution.query_sha256"),
        "result_sha256": _hex64(execution["result_sha256"], "case.execution.result_sha256"),
        "started_at": execution["started_at"],
        "completed_at": execution["completed_at"],
    }

    actor = _dict(obj["actor"], "case.actor")
    _keys(actor, {"user_id", "role"}, "case.actor")
    parsed_actor = {
        "user_id": _identifier(actor["user_id"], "case.actor.user_id"),
        "role": _identifier(actor["role"], "case.actor.role"),
    }

    intended = _dict(obj["intended_use"], "case.intended_use")
    _keys(intended, {"risk_class", "purpose"}, "case.intended_use")
    parsed_intended = {
        "risk_class": _identifier(intended["risk_class"], "case.intended_use.risk_class"),
        "purpose": _string(intended["purpose"], "case.intended_use.purpose"),
    }

    change = _dict(obj["change_control"], "case.change_control")
    _keys(change, {"reference", "status", "approved_at"}, "case.change_control")
    change_status = _identifier(change["status"], "case.change_control.status")
    if change_status not in _ALLOWED_CHANGE_STATES:
        raise GateInputError("unsupported change-control status")
    change_approved = _utc(change["approved_at"], "case.change_control.approved_at")
    if change_approved > started:
        raise GateInputError("change-control approval cannot occur after execution start")
    parsed_change = {
        "reference": _reference(change["reference"], "case.change_control.reference"),
        "status": change_status,
        "approved_at": change["approved_at"],
    }

    approval = _dict(obj["human_approval"], "case.human_approval")
    _keys(
        approval,
        {"reviewer_id", "reviewer_role", "decision", "artifact_sha256", "approved_at"},
        "case.human_approval",
    )
    approval_decision = _identifier(approval["decision"], "case.human_approval.decision")
    if approval_decision not in _ALLOWED_APPROVAL_DECISIONS:
        raise GateInputError("unsupported human approval decision")
    approval_dt = _utc(approval["approved_at"], "case.human_approval.approved_at")
    if approval_dt < completed or approval_dt > captured_dt:
        raise GateInputError("human approval timestamp must follow execution and precede capture")
    parsed_approval = {
        "reviewer_id": _identifier(approval["reviewer_id"], "case.human_approval.reviewer_id"),
        "reviewer_role": _identifier(approval["reviewer_role"], "case.human_approval.reviewer_role"),
        "decision": approval_decision,
        "artifact_sha256": _hex64(approval["artifact_sha256"], "case.human_approval.artifact_sha256"),
        "approved_at": approval["approved_at"],
    }

    semantic = {
        "schema": CASE_SCHEMA,
        "case_id": case_id,
        "artifact": parsed_artifact,
        "source_snapshots": sources,
        "batch_context": parsed_batch,
        "execution": parsed_execution,
        "actor": parsed_actor,
        "intended_use": parsed_intended,
        "change_control": parsed_change,
        "human_approval": parsed_approval,
        "captured_at": obj["captured_at"],
    }
    expected_event_id = digest(semantic)
    supplied_event_id = _hex64(obj["event_id"], "case.event_id")
    if supplied_event_id != expected_event_id:
        raise GateInputError("case.event_id is not the content address of the canonical case")
    semantic["event_id"] = supplied_event_id
    return semantic


