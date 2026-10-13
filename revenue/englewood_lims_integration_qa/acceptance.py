from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .gate import _evaluate, canonical_json, make_audit_event, sha256_json
except ImportError:
    from gate import _evaluate, canonical_json, make_audit_event, sha256_json

FIXTURE_TIME = datetime(2026, 9, 13, 9, 30, 0, tzinfo=timezone.utc)
CAPTURED = "2026-09-13T09:29:30Z"
OBSERVED = "2026-09-13T09:29:00Z"
D = "0" * 64


def build_clean_packet(seed: int = 1) -> dict[str, Any]:
    release_id = f"ENG-LIMS-REL-{seed:03d}"
    requirements = [
        {"requirement_id": "REQ-AUDIT", "category": "AUDIT_TRAIL", "mandatory": True},
        {"requirement_id": "REQ-VALID", "category": "REAL_TIME_VALIDATION", "mandatory": True},
        {"requirement_id": "REQ-ROLE", "category": "SECURE_MULTI_USER_WORKFLOW", "mandatory": True},
        {"requirement_id": "REQ-INT", "category": "INTEGRATION", "mandatory": True},
        {"requirement_id": "REQ-DEPLOY", "category": "DEPLOYMENT_TESTING", "mandatory": True},
    ]
    tests = [
        {"test_id": "T-AUDIT", "requirement_ids": ["REQ-AUDIT"], "test_kind": "SECURITY"},
        {"test_id": "T-VALID", "requirement_ids": ["REQ-VALID"], "test_kind": "VALIDATION"},
        {"test_id": "T-ROLE", "requirement_ids": ["REQ-ROLE"], "test_kind": "SECURITY"},
        {"test_id": "T-INT", "requirement_ids": ["REQ-INT"], "test_kind": "INTEGRATION"},
        {"test_id": "T-DEPLOY", "requirement_ids": ["REQ-DEPLOY"], "test_kind": "FUNCTIONAL"},
    ]
    runs = [
        {
            "run_id": f"RUN-{i}",
            "test_id": test["test_id"],
            "status": "PASS",
            "observed_at": OBSERVED,
            "evidence_sha256": sha256_json({"seed": seed, "test": test["test_id"]}),
        }
        for i, test in enumerate(tests, start=1)
    ]
    rules = [
        "AUDIT_CHAIN_INTEGRITY",
        "REAL_TIME_VALIDATION",
        "MULTI_USER_ROLE_SEPARATION",
        "INTEGRATION_REPLAY_IDEMPOTENCY",
        "REQUIREMENT_TRACEABILITY",
    ]
    validations = [
        {
            "validation_id": f"VAL-{i}",
            "rule_id": rule,
            "subject_id": release_id,
            "status": "PASS",
            "observed_at": OBSERVED,
            "input_sha256": sha256_json({"seed": seed, "rule": rule, "side": "input"}),
            "result_sha256": sha256_json({"seed": seed, "rule": rule, "side": "result"}),
        }
        for i, rule in enumerate(rules, start=1)
    ]
    workflow = [
        {
            "event_id": "WF-1",
            "object_id": release_id,
            "action": "CONFIGURE",
            "actor_id": "actor-config",
            "role": "CONFIGURATOR",
            "observed_at": OBSERVED,
            "evidence_sha256": sha256_json({"seed": seed, "action": "CONFIGURE"}),
        },
        {
            "event_id": "WF-2",
            "object_id": release_id,
            "action": "EXECUTE_TEST",
            "actor_id": "actor-test",
            "role": "TESTER",
            "observed_at": OBSERVED,
            "evidence_sha256": sha256_json({"seed": seed, "action": "EXECUTE_TEST"}),
        },
        {
            "event_id": "WF-3",
            "object_id": release_id,
            "action": "VALIDATE",
            "actor_id": "actor-valid",
            "role": "VALIDATOR",
            "observed_at": OBSERVED,
            "evidence_sha256": sha256_json({"seed": seed, "action": "VALIDATE"}),
        },
        {
            "event_id": "WF-4",
            "object_id": release_id,
            "action": "APPROVE_RELEASE",
            "actor_id": "actor-approve",
            "role": "RELEASE_APPROVER",
            "observed_at": OBSERVED,
            "evidence_sha256": sha256_json({"seed": seed, "action": "APPROVE_RELEASE"}),
        },
    ]
    payload1 = sha256_json({"seed": seed, "sample": 1})
    payload2 = sha256_json({"seed": seed, "sample": 2})
    integrations = [
        {
            "event_id": "INT-1",
            "interface_id": "SCADA-LIMS",
            "business_key": f"SAMPLE-{seed:03d}",
            "sequence": 1,
            "outcome": "APPLIED",
            "retry_of": None,
            "observed_at": OBSERVED,
            "payload_sha256": payload1,
        },
        {
            "event_id": "INT-1-RETRY",
            "interface_id": "SCADA-LIMS",
            "business_key": f"SAMPLE-{seed:03d}",
            "sequence": 1,
            "outcome": "NO_EFFECT_RETRY",
            "retry_of": "INT-1",
            "observed_at": OBSERVED,
            "payload_sha256": payload1,
        },
        {
            "event_id": "INT-2",
            "interface_id": "SCADA-LIMS",
            "business_key": f"SAMPLE-{seed:03d}",
            "sequence": 2,
            "outcome": "APPLIED",
            "retry_of": None,
            "observed_at": OBSERVED,
            "payload_sha256": payload2,
        },
    ]

    audit: list[dict[str, Any]] = []
    prev = None
    for i, wf in enumerate(workflow, start=1):
        row = make_audit_event(
            event_id=f"AUD-{i}",
            sequence=i,
            actor_id=wf["actor_id"],
            action=wf["action"],
            object_id=release_id,
            observed_at=OBSERVED,
            details_sha256=wf["evidence_sha256"],
            prev_hash=prev,
        )
        audit.append(row)
        prev = row["event_hash"]
    return {
        "schema_version": 1,
        "packet_id": f"ENG-LIMS-PACKET-{seed:03d}",
        "release_id": release_id,
        "snapshot_id": f"ENG-LIMS-SNAPSHOT-{seed:03d}",
        "captured_at": CAPTURED,
        "complete": True,
        "requirements": requirements,
        "test_cases": tests,
        "test_runs": runs,
        "validation_results": validations,
        "workflow_events": workflow,
        "integration_events": integrations,
        "audit_events": audit,
    }


def _mutate(packet: dict[str, Any], defect: str) -> dict[str, Any]:
    p = copy.deepcopy(packet)
    if defect == "MISSING_COVERAGE":
        p["test_cases"] = [t for t in p["test_cases"] if t["test_id"] != "T-DEPLOY"]
        p["test_runs"] = [r for r in p["test_runs"] if r["test_id"] != "T-DEPLOY"]
    elif defect == "TEST_FAILURE":
        p["test_runs"][0]["status"] = "FAIL"
    elif defect == "AUDIT_CHAIN":
        p["audit_events"][2]["prev_hash"] = D
    elif defect == "VALIDATION_FAILURE":
        p["validation_results"][0]["status"] = "FAIL"
    elif defect == "ROLE_COLLISION":
        p["workflow_events"][3]["actor_id"] = p["workflow_events"][0]["actor_id"]
    elif defect == "INTEGRATION_QUARANTINE":
        p["integration_events"][2]["outcome"] = "QUARANTINED"
    elif defect == "EVENT_ID_CONFLICT":
        changed = copy.deepcopy(p["integration_events"][0])
        changed["payload_sha256"] = "f" * 64
        p["integration_events"].append(changed)
    elif defect == "INCOMPLETE":
        p["complete"] = False
    else:
        raise AssertionError(defect)
    return p


def run_acceptance() -> dict[str, Any]:
    defect_classes = [
        "MISSING_COVERAGE",
        "TEST_FAILURE",
        "AUDIT_CHAIN",
        "VALIDATION_FAILURE",
        "ROLE_COLLISION",
        "INTEGRATION_QUARANTINE",
        "EVENT_ID_CONFLICT",
        "INCOMPLETE",
    ]
    ready = 0
    hold = 0
    by_defect = {name: 0 for name in defect_classes}
    digests: list[str] = []

    for seed in range(1, 41):
        packet = build_clean_packet(seed)
        receipt = _evaluate(packet, FIXTURE_TIME)
        assert receipt["decision"] == "READY_FOR_PRIME_REVIEW", receipt
        ready += 1
        digests.append(receipt["receipt_digest"])

    for index, defect in enumerate(defect_classes):
        for offset in range(5):
            seed = 100 + index * 5 + offset
            packet = _mutate(build_clean_packet(seed), defect)
            receipt = _evaluate(packet, FIXTURE_TIME)
            assert receipt["decision"] == "HOLD", (defect, receipt)
            hold += 1
            by_defect[defect] += 1
            digests.append(receipt["receipt_digest"])

    manifest = {
        "schema_version": 1,
        "fixture_time": FIXTURE_TIME.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_packets": ready + hold,
        "ready": ready,
        "hold": hold,
        "hold_by_defect": by_defect,
        "corpus_digest": sha256_json(sorted(digests)),
    }
    return manifest


def main() -> int:
    manifest = run_acceptance()
    print(canonical_json(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
