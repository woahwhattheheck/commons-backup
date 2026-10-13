from __future__ import annotations

from datetime import datetime
from typing import Any

from .codec import AUTHORITY, _catalog_ok, _utc, digest

def _hold_codes(case: dict[str, Any], policy: dict[str, Any], evaluated_dt: datetime) -> list[str]:
    codes: set[str] = set()
    captured_dt = _utc(case["captured_at"], "case.captured_at")
    if int((evaluated_dt - captured_dt).total_seconds()) > policy["age"]:
        codes.add("EVIDENCE_STALE")
    if case["artifact"]["artifact_type"] not in policy["artifacts"]:
        codes.add("ARTIFACT_TYPE_NOT_APPROVED")
    if case["batch_context"]["standard"] not in policy["standards"]:
        codes.add("BATCH_CONTEXT_STANDARD_NOT_APPROVED")
    if any(not value for key, value in case["batch_context"].items() if key != "standard"):
        codes.add("BATCH_CONTEXT_INCOMPLETE")

    for source in case["source_snapshots"]:
        if not source["complete"]:
            codes.add("SOURCE_SNAPSHOT_INCOMPLETE")
        source_captured = _utc(source["captured_at"], "source.captured_at")
        if int((evaluated_dt - source_captured).total_seconds()) > policy["age"]:
            codes.add("SOURCE_SNAPSHOT_STALE")
        if not _catalog_ok(source["dataset"], policy["datasets"]):
            codes.add("DATASET_NOT_APPROVED")

    execution = case["execution"]
    if not _catalog_ok(execution["model"], policy["models"]):
        codes.add("MODEL_NOT_APPROVED")
    if any(not _catalog_ok(tool, policy["tools"]) for tool in execution["tools"]):
        codes.add("TOOL_NOT_APPROVED")
    if not _catalog_ok(execution["prompt_policy"], policy["prompts"]):
        codes.add("PROMPT_POLICY_NOT_APPROVED")

    actor = case["actor"]
    if actor["role"] not in policy["actor_roles"]:
        codes.add("ACTOR_ROLE_NOT_APPROVED")
    risk = case["intended_use"]["risk_class"]
    if risk not in policy["risks"]:
        codes.add("RISK_CLASS_NOT_APPROVED")

    change = case["change_control"]
    if change["status"] != "APPROVED":
        codes.add("CHANGE_CONTROL_NOT_APPROVED")

    approval = case["human_approval"]
    required_roles = policy["reviewer_roles"].get(risk, ())
    if approval["decision"] != "APPROVE":
        codes.add("HUMAN_APPROVAL_NOT_APPROVED")
    if approval["reviewer_role"] not in required_roles:
        codes.add("HUMAN_APPROVER_ROLE_NOT_AUTHORIZED")
    if approval["reviewer_id"] == actor["user_id"]:
        codes.add("FOUR_EYES_VIOLATION")
    if approval["artifact_sha256"] != case["artifact"]["sha256"]:
        codes.add("HUMAN_APPROVAL_ARTIFACT_MISMATCH")
    if execution["result_sha256"] != case["artifact"]["sha256"]:
        codes.add("RESULT_ARTIFACT_HASH_MISMATCH")

    return sorted(codes)


def _manifest_row(case: dict[str, Any], policy: dict[str, Any], evaluated_dt: datetime) -> dict[str, Any]:
    codes = _hold_codes(case, policy, evaluated_dt)
    source_lineage = [
        {
            "dataset_id": source["dataset"]["id"],
            "snapshot_id": source["snapshot_id"],
            "snapshot_sha256": source["snapshot_sha256"],
        }
        for source in case["source_snapshots"]
    ]
    row = {
        "case_id": case["case_id"],
        "event_id": case["event_id"],
        "artifact_id": case["artifact"]["artifact_id"],
        "artifact_type": case["artifact"]["artifact_type"],
        "artifact_sha256": case["artifact"]["sha256"],
        "batch_id": case["batch_context"]["batch_id"],
        "risk_class": case["intended_use"]["risk_class"],
        "source_lineage": source_lineage,
        "run_id": case["execution"]["run_id"],
        "model_id": case["execution"]["model"]["id"],
        "prompt_policy_id": case["execution"]["prompt_policy"]["id"],
        "query_sha256": case["execution"]["query_sha256"],
        "result_sha256": case["execution"]["result_sha256"],
        "change_control_reference": case["change_control"]["reference"],
        "human_reviewer_id": case["human_approval"]["reviewer_id"],
        "status": AUTHORITY if not codes else "HOLD",
        "codes": codes,
    }
    row["lineage_sha256"] = digest(
        {
            "sources": source_lineage,
            "batch_context": case["batch_context"],
            "execution": case["execution"],
            "actor": case["actor"],
            "intended_use": case["intended_use"],
            "change_control": case["change_control"],
            "human_approval": case["human_approval"],
        }
    )
    return row


