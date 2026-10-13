from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from typing import Any


def h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def base_bundle(count: int = 100) -> dict[str, Any]:
    captured = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
    generated = captured + timedelta(hours=1)
    approved = generated + timedelta(minutes=10)
    components = [
        {"kind": "connector", "component_id": "aws.bedrock", "version": "2026.09", "sha256": h("connector")},
        {"kind": "model", "component_id": "model.clinical-nlp", "version": "3.2.1", "sha256": h("model")},
        {"kind": "tool", "component_id": "elain.search", "version": "2.4.0", "sha256": h("tool")},
        {"kind": "prompt_policy", "component_id": "policy.partner-ai", "version": "7", "sha256": h("policy")},
    ]
    sources = []
    events = []
    for i in range(count):
        source_id = f"source.{i:03d}"
        source_sha = h(f"source:{i}")
        result_sha = h(f"result:{i}")
        sources.append({"source_id": source_id, "sha256": source_sha, "captured_at": captured.strftime("%Y-%m-%dT%H:%M:%SZ")})
        events.append({
            "event_id": f"evt.{i:03d}",
            "source_id": source_id,
            "source_sha256": source_sha,
            "query_sha256": h(f"query:{i}"),
            "result_sha256": result_sha,
            "connector_ref": {"component_id": "aws.bedrock", "sha256": h("connector")},
            "model_ref": {"component_id": "model.clinical-nlp", "sha256": h("model")},
            "tool_ref": {"component_id": "elain.search", "sha256": h("tool")},
            "prompt_policy_ref": {"component_id": "policy.partner-ai", "sha256": h("policy")},
            "actor_ref": f"user.{i % 7}",
            "actor_role": "scientist",
            "intended_use": "research evidence triage with human review",
            "risk_class": "MODERATE",
            "change_control_ref": f"cc.{i // 10:03d}",
            "generated_at": generated.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "approval": {
                "approval_id": f"approval.{i:03d}",
                "reviewer_ref": f"reviewer.{i % 5}",
                "reviewer_role": "quality reviewer",
                "reviewer_type": "human",
                "decision": "APPROVED",
                "approved_at": approved.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "artifact_sha256": result_sha,
            },
        })
    return {"schema_version": 1, "bundle_id": "sapio.synthetic.100", "components": components, "source_snapshots": sources, "events": events}


def hostile_fixture() -> dict[str, Any]:
    """100 events: 80 clean + four isolated hostile families of five events each."""
    bundle = base_bundle(100)
    for i in range(80, 85):
        bundle["source_snapshots"][i]["captured_at"] = "2026-07-01T12:00:00Z"
    for i in range(85, 90):
        bundle["events"][i]["approval"]["artifact_sha256"] = h(f"wrong-approval:{i}")
    for i in range(90, 95):
        bundle["events"][i]["approval"]["reviewer_type"] = "agent"
    for i in range(95, 100):
        bundle["events"][i]["approval"]["decision"] = "PENDING"
    return bundle


def exact_replay(bundle: dict[str, Any], index: int = 0) -> dict[str, Any]:
    copy = deepcopy(bundle)
    copy["events"].append(deepcopy(copy["events"][index]))
    return copy
