"""Synthetic CLAIM -> Muse -> send-attempt -> accepted-result demonstration."""
from __future__ import annotations

from revenue.outbound_collision_replay_guard.engine import (
    ATTEMPT_SCHEMA,
    MUSE_SCHEMA,
    REQUEST_SCHEMA,
    RESULT_SCHEMA,
    canonical_json,
    empty_ledger,
    load_json,
    sha256,
    transition,
)

BODY = "a" * 64
SRC = "b" * 64


def req(ledger, op, *, generation=None, muse=None, attempt=None, result=None, now="2026-09-17T03:10:00Z"):
    return canonical_json({
        "schema": REQUEST_SCHEMA,
        "evaluation_time": now,
        "operation": op,
        "expected_ledger_sha256": sha256(ledger),
        "claimant_id": "demo-agent",
        "session_id": "demo-session",
        "lease_ttl_seconds": 600,
        "generation": generation,
        "intent": {
            "counterparty_key": "demo-org",
            "counterparty_resolution": "EXACT",
            "observed_aliases": ["demo-org"],
            "provider": "gmail",
            "thread_scope_key": "thread-7",
            "thread_mode": "REPLY",
            "purpose_key": "paid-scope-followup",
            "body_sha256": BODY,
        },
        "muse": muse,
        "send_attempt": attempt,
        "send_result": result,
    })


def step(ledger, request):
    after, receipt = transition(ledger, request)
    print(load_json(receipt)["decision_state"])
    return after


def main():
    ledger = canonical_json(empty_ledger())
    ledger = step(ledger, req(ledger, "CLAIM"))
    record = load_json(ledger)["records"][0]
    muse = {
        "schema": MUSE_SCHEMA,
        "receipt_id": "muse-demo-1",
        "fingerprint": record["fingerprint"],
        "claimant_id": record["claimant_id"],
        "session_id": record["session_id"],
        "generation": 1,
        "body_sha256": BODY,
        "selected": True,
        "observed_at": "2026-09-17T03:10:01Z",
        "expires_at": "2026-09-17T03:15:00Z",
        "source_uri": "slack:muse-demo/1",
        "source_sha256": SRC,
    }
    ledger = step(ledger, req(ledger, "APPLY_MUSE", generation=1, muse=muse, now="2026-09-17T03:10:02Z"))
    record = load_json(ledger)["records"][0]
    attempt = {
        "schema": ATTEMPT_SCHEMA,
        "attempt_id": "attempt-demo-1",
        "fingerprint": record["fingerprint"],
        "generation": 1,
        "body_sha256": BODY,
        "attempted_at": "2026-09-17T03:10:03Z",
        "provider_request_id": "provider-request-demo-1",
        "source_uri": "sender:demo/1",
        "source_sha256": SRC,
    }
    ledger = step(ledger, req(ledger, "RECORD_SEND_ATTEMPT", generation=1, attempt=attempt, now="2026-09-17T03:10:04Z"))
    record = load_json(ledger)["records"][0]
    result = {
        "schema": RESULT_SCHEMA,
        "result_id": "result-demo-1",
        "attempt_id": record["send_attempt"]["attempt_id"],
        "fingerprint": record["fingerprint"],
        "generation": 1,
        "body_sha256": BODY,
        "status": "ACCEPTED",
        "observed_at": "2026-09-17T03:10:05Z",
        "provider_message_id": "provider-message-demo-1",
        "source_uri": "provider:demo/1",
        "source_sha256": SRC,
    }
    step(ledger, req(ledger, "RECORD_SEND_RESULT", generation=1, result=result, now="2026-09-17T03:10:06Z"))


if __name__ == "__main__":
    main()
