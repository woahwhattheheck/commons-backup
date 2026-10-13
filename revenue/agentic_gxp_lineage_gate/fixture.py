from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Any

from .gate import CASE_SCHEMA, POLICY_SCHEMA, BATCH_SCHEMA, digest

BASE_CAPTURE = datetime(2026, 9, 13, 9, 15, 0, tzinfo=timezone.utc)
EVALUATED_AT = "2026-09-13T09:16:00Z"


def _ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _h(label: str) -> str:
    return digest({"synthetic": label})


def build_policy() -> dict[str, Any]:
    return {
        "schema": POLICY_SCHEMA,
        "max_evidence_age_seconds": 3600,
        "allowed_artifact_types": ["batch_review", "deviation", "pqr"],
        "allowed_batch_standards": ["ISA-88-95"],
        "allowed_risk_classes": ["LOW", "MEDIUM", "HIGH"],
        "allowed_actor_roles": ["process_engineer", "quality_engineer", "qa_reviewer", "qa_manager"],
        "reviewer_roles_by_risk": {
            "LOW": ["qa_reviewer", "qa_manager"],
            "MEDIUM": ["qa_reviewer", "qa_manager"],
            "HIGH": ["qa_manager"],
        },
        "approved_datasets": {
            "historian": {"version": "schema-v4", "sha256": _h("dataset-schema-historian-v4")},
            "lims": {"version": "schema-v7", "sha256": _h("dataset-schema-lims-v7")},
        },
        "approved_models": {
            "gxp-assistant": {"version": "2026.09", "sha256": _h("model-gxp-assistant-2026.09")},
        },
        "approved_tools": {
            "lineage-query": {"version": "3.2.1", "sha256": _h("tool-lineage-query-3.2.1")},
            "report-renderer": {"version": "5.4.0", "sha256": _h("tool-report-renderer-5.4.0")},
        },
        "approved_prompt_policies": {
            "manufacturing-review": {"version": "pp-12", "sha256": _h("prompt-policy-12")},
        },
    }


def _readdress(case: dict[str, Any]) -> dict[str, Any]:
    core = copy.deepcopy(case)
    core.pop("event_id", None)
    case["event_id"] = digest(core)
    return case


def build_case(index: int, *, defect: str | None = None) -> dict[str, Any]:
    captured = BASE_CAPTURE - timedelta(seconds=index % 30)
    completed = captured - timedelta(seconds=20)
    started = completed - timedelta(seconds=25)
    artifact_type = ("deviation", "pqr", "batch_review")[index % 3]
    risk = ("LOW", "MEDIUM", "HIGH")[index % 3]
    reviewer_role = "qa_manager" if risk == "HIGH" else "qa_reviewer"
    artifact_sha = _h(f"artifact-{index:03d}")
    case = {
        "schema": CASE_SCHEMA,
        "case_id": f"case-{index:03d}",
        "event_id": "0" * 64,
        "artifact": {
            "artifact_id": f"artifact-{index:03d}",
            "artifact_type": artifact_type,
            "sha256": artifact_sha,
        },
        "source_snapshots": [
            {
                "dataset": {
                    "id": "historian",
                    "version": "schema-v4",
                    "sha256": _h("dataset-schema-historian-v4"),
                },
                "snapshot_id": f"hist-{index:03d}",
                "snapshot_sha256": _h(f"historian-snapshot-{index:03d}"),
                "captured_at": _ts(started - timedelta(seconds=15)),
                "complete": True,
            },
            {
                "dataset": {
                    "id": "lims",
                    "version": "schema-v7",
                    "sha256": _h("dataset-schema-lims-v7"),
                },
                "snapshot_id": f"lims-{index:03d}",
                "snapshot_sha256": _h(f"lims-snapshot-{index:03d}"),
                "captured_at": _ts(started - timedelta(seconds=10)),
                "complete": True,
            },
        ],
        "batch_context": {
            "standard": "ISA-88-95",
            "site_id": f"site-{index % 4}",
            "process_cell_id": f"cell-{index % 7}",
            "unit_id": f"unit-{index % 11}",
            "batch_id": f"batch-{index:03d}",
            "material_lot_id": f"lot-{index:03d}",
        },
        "execution": {
            "run_id": f"run-{index:03d}",
            "model": {
                "id": "gxp-assistant",
                "version": "2026.09",
                "sha256": _h("model-gxp-assistant-2026.09"),
            },
            "tools": [
                {
                    "id": "lineage-query",
                    "version": "3.2.1",
                    "sha256": _h("tool-lineage-query-3.2.1"),
                },
                {
                    "id": "report-renderer",
                    "version": "5.4.0",
                    "sha256": _h("tool-report-renderer-5.4.0"),
                },
            ],
            "prompt_policy": {
                "id": "manufacturing-review",
                "version": "pp-12",
                "sha256": _h("prompt-policy-12"),
            },
            "query_sha256": _h(f"query-{index:03d}"),
            "result_sha256": artifact_sha,
            "started_at": _ts(started),
            "completed_at": _ts(completed),
        },
        "actor": {
            "user_id": f"operator-{index % 9}",
            "role": "quality_engineer" if index % 2 else "process_engineer",
        },
        "intended_use": {
            "risk_class": risk,
            "purpose": f"Synthetic {artifact_type} QA-review evidence case {index:03d}",
        },
        "change_control": {
            "reference": f"CC-2026-{index:04d}",
            "status": "APPROVED",
            "approved_at": _ts(started - timedelta(minutes=5)),
        },
        "human_approval": {
            "reviewer_id": f"reviewer-{index % 5}",
            "reviewer_role": reviewer_role,
            "decision": "APPROVE",
            "artifact_sha256": artifact_sha,
            "approved_at": _ts(completed + timedelta(seconds=5)),
        },
        "captured_at": _ts(captured),
    }

    if defect == "SOURCE_SNAPSHOT_INCOMPLETE":
        case["source_snapshots"][0]["complete"] = False
    elif defect == "DATASET_NOT_APPROVED":
        case["source_snapshots"][0]["dataset"]["version"] = "schema-v999"
        case["source_snapshots"][0]["dataset"]["sha256"] = _h("unapproved-dataset-schema")
    elif defect == "BATCH_CONTEXT_STANDARD_NOT_APPROVED":
        case["batch_context"]["standard"] = "CUSTOM-BATCH-MODEL"
    elif defect == "MODEL_NOT_APPROVED":
        case["execution"]["model"]["version"] = "2026.10-unsigned"
        case["execution"]["model"]["sha256"] = _h("unapproved-model")
    elif defect == "TOOL_NOT_APPROVED":
        case["execution"]["tools"][0]["version"] = "4.0.0"
        case["execution"]["tools"][0]["sha256"] = _h("unapproved-tool")
    elif defect == "PROMPT_POLICY_NOT_APPROVED":
        case["execution"]["prompt_policy"]["version"] = "pp-13-draft"
        case["execution"]["prompt_policy"]["sha256"] = _h("draft-prompt-policy")
    elif defect == "CHANGE_CONTROL_NOT_APPROVED":
        case["change_control"]["status"] = "PENDING"
    elif defect == "HUMAN_APPROVAL_ARTIFACT_MISMATCH":
        case["human_approval"]["artifact_sha256"] = _h("different-artifact")
    elif defect is not None:
        raise ValueError(f"unknown synthetic defect: {defect}")

    return _readdress(case)


DEFECTS = (
    "SOURCE_SNAPSHOT_INCOMPLETE",
    "DATASET_NOT_APPROVED",
    "BATCH_CONTEXT_STANDARD_NOT_APPROVED",
    "MODEL_NOT_APPROVED",
    "TOOL_NOT_APPROVED",
    "PROMPT_POLICY_NOT_APPROVED",
    "CHANGE_CONTROL_NOT_APPROVED",
    "HUMAN_APPROVAL_ARTIFACT_MISMATCH",
)


def build_acceptance_batch() -> dict[str, Any]:
    cases = [build_case(i) for i in range(96)]
    index = 96
    for defect in DEFECTS:
        for _ in range(3):
            cases.append(build_case(index, defect=defect))
            index += 1
    if len(cases) != 120:
        raise RuntimeError("acceptance fixture construction drifted")
    return {
        "schema": BATCH_SCHEMA,
        "capture_complete": True,
        "captured_at": _ts(BASE_CAPTURE),
        "cases": cases,
    }
