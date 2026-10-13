from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone

if __package__:
    from .gate import compile_trace, expected_idempotency_key, make_packet, sha256_json, verify_receipt
else:
    from gate import compile_trace, expected_idempotency_key, make_packet, sha256_json, verify_receipt

NOW = datetime(2026, 9, 13, 9, 55, tzinfo=timezone.utc)


def z(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def digest(label: str) -> str:
    return sha256_json({"label": label})


def base_packet(index: int) -> dict:
    return make_packet(
        workflow_id=f"wf-{index:03d}",
        request_id=f"req-{index:03d}",
        principal_id=f"principal-{index % 7}",
        resource_scope=f"tenant-{index % 4}/system-{index % 5}",
        operation=("UPDATE", "CREATE", "PROVISION", "ASSIGN")[index % 4],
        target=f"resource/{index:03d}",
        payload_digest=digest(f"payload-{index}"),
        policy_version="sw1045-demo-1",
        policy_digest=digest("policy-v1"),
        snapshot_digest=digest(f"snapshot-{index}"),
        captured_at=z(NOW - timedelta(minutes=3)),
        max_age_seconds=900,
        approver_id=f"approver-{index % 3}",
        role="change-approver",
        approved_at=z(NOW - timedelta(minutes=2)),
        expires_at=z(NOW + timedelta(hours=1)),
    )


def success_attempt(packet: dict, index: int) -> dict:
    return {
        "attempt_id": f"attempt-{index:03d}",
        "idempotency_key": expected_idempotency_key(packet),
        "dispatched_at": z(NOW - timedelta(minutes=1)),
        "transport_result": "SUCCESS",
        "provider_effect_id": f"effect-{index:03d}",
        "provider_state_digest": digest(f"provider-state-{index}"),
        "reconciled_at": None,
        "reconciliation": "NONE",
    }


def build_corpus() -> list[dict]:
    cases: list[dict] = []
    for index in range(120):
        packet = base_packet(index)
        expected = "EXECUTION_EVIDENCE_VALID"
        family = "CONTROL"
        if index < 100:
            packet["attempts"] = [success_attempt(packet, index)]
        else:
            packet["attempts"] = [success_attempt(packet, index)]
            bucket = (index - 100) // 5
            if bucket == 0:
                packet["snapshot"]["captured_at"] = z(NOW - timedelta(hours=2))
                family = "STALE_SNAPSHOT"
            elif bucket == 1:
                packet["approval"]["action_digest"] = digest("wrong-binding")
                family = "APPROVAL_BINDING"
            elif bucket == 2:
                packet["attempts"][0].update({
                    "transport_result": "UNKNOWN",
                    "provider_effect_id": None,
                    "provider_state_digest": None,
                    "reconciled_at": None,
                    "reconciliation": "NONE",
                })
                family = "UNKNOWN_OUTCOME"
            else:
                duplicate = deepcopy(packet["attempts"][0])
                duplicate["attempt_id"] = f"attempt-{index:03d}-b"
                duplicate["dispatched_at"] = z(NOW - timedelta(seconds=30))
                duplicate["provider_effect_id"] = f"effect-{index:03d}-b"
                duplicate["provider_state_digest"] = digest(f"provider-state-{index}-b")
                packet["attempts"].append(duplicate)
                family = "DUPLICATE_EFFECT"
            expected = "HOLD"
        cases.append({"index": index, "family": family, "expected": expected, "packet": packet})
    return cases


def main() -> int:
    results = []
    counts: dict[str, int] = {}
    for case in build_corpus():
        receipt = compile_trace(case["packet"], trusted_now=z(NOW))
        if receipt["status"] != case["expected"]:
            raise AssertionError((case["index"], case["family"], receipt))
        if not verify_receipt(case["packet"], trusted_now=z(NOW), receipt=receipt):
            raise AssertionError("receipt failed verification")
        counts[case["family"]] = counts.get(case["family"], 0) + 1
        results.append({
            "index": case["index"],
            "family": case["family"],
            "status": receipt["status"],
            "receipt_digest": receipt["receipt_digest"],
        })
    output = {
        "schema": "naspo-sw1045-agent-workflow-acceptance-corpus/v1",
        "counts": counts,
        "valid": sum(row["status"] == "EXECUTION_EVIDENCE_VALID" for row in results),
        "hold": sum(row["status"] == "HOLD" for row in results),
        "results_digest": sha256_json(results),
    }
    print(json.dumps(output, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
