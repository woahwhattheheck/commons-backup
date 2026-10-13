"""Prospect-safe 90-second demo of the merged offline transcript carrier.

Runs entirely offline against the checked-in synthetic fixture and a test-only
approval key generated at runtime. Nothing here is a customer result, a
deployment, or an outbound send: every artifact carries
``external_send_authorized=False``.

Run from the repository root:

    python -m revenue.hyperagent_slack_transcript.demo_90s
"""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
import secrets
import time

from .adapter import (
    ApprovalError,
    TranscriptProjector,
    canonical_bytes,
    load_strict_json,
    normalize_event,
    project_fixture,
)

FIXTURE = Path(__file__).resolve().parent / "fixture.json"


def _banner(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def _sign(approval: dict, key: bytes) -> dict:
    approval["authority_tag"] = hmac.new(
        key, canonical_bytes(approval), hashlib.sha256
    ).hexdigest()
    return approval


def _event_semantics_sha256(event: dict) -> str:
    return hashlib.sha256(
        canonical_bytes(normalize_event(event).semantics())
    ).hexdigest()


def _mutating_event() -> dict:
    return {
        "backend": "stream",
        "run_id": "demo-mut-run",
        "event_id": "m1",
        "seq": 1,
        "kind": "MUTATING_ACTION",
        "payload": {
            "thread": "demo-approvals",
            "text": "would post to a provider thread",
            "action_id": "send",
            "generation": 1,
        },
    }


def _approval_for(event: dict, key: bytes, **overrides) -> dict:
    raw = f"run\x1fstream\x1f{event['run_id']}".encode()
    approval = {
        "approval_id": "ap-demo-1",
        "run_id": "run_" + hashlib.sha256(raw).hexdigest()[:24],
        "action_id": event["payload"]["action_id"],
        "generation": event["payload"]["generation"],
        "event_semantics_sha256": _event_semantics_sha256(event),
        "decision": "APPROVE",
        "issued_at": "2020-01-01T00:00:00Z",
        "expires_at": "2099-01-01T00:00:00Z",
        "evidence_sha256": "a" * 64,
    }
    approval.update(overrides)
    return _sign(approval, key)


def main() -> int:
    started = time.monotonic()
    print("HYPERAGENT TRANSCRIPT CARRIER â€” 90-SECOND DEMO")
    print("Synthetic fixture only. Offline. external_send_authorized stays false.")

    fixture = load_strict_json(FIXTURE.read_bytes())
    backends = sorted({event["backend"] for event in fixture["events"]})
    print(f"\nInput: {len(fixture['events'])} events, backends: {', '.join(backends)}")

    _banner("SCENE 1 â€” 30 events across 3 backends -> deterministic transcripts")
    projected = project_fixture(fixture)
    print(f"transcript artifacts : {projected['artifact_count']}")
    print(f"logical messages     : {projected['message_count']}")
    for artifact in projected["artifacts"]:
        print(
            f"  {artifact['thread_ref']:<8} "
            f"{len(artifact['messages'])} msgs  sha256={artifact['artifact_sha256'][:16]}â€¦"
        )

    _banner("SCENE 2 â€” full replay -> zero duplicate logical messages")
    projector = TranscriptProjector()
    first = projector.ingest(fixture["events"], [])
    second = projector.ingest(fixture["events"], [])
    print(f"pass 1 emitted {len(first['new_message_ids'])} new messages")
    print(f"pass 2 emitted {len(second['new_message_ids'])} new messages")
    print(f"state identical      : {first['state_sha256'] == second['state_sha256']}")

    _banner("SCENE 3 â€” mutating action requires exact authenticated approval")
    event = _mutating_event()
    runtime_key = secrets.token_bytes(48)  # demo-only; never committed

    held = projector.ingest([event], [])
    print(f"no approval          : held={held['held']}")

    forged = _approval_for(event, secrets.token_bytes(48))
    try:
        TranscriptProjector(approval_auth_key=runtime_key).ingest([event], [forged])
        print("forged approval      : UNEXPECTEDLY EMITTED")
    except ApprovalError as exc:
        print(f"forged approval      : rejected ({exc})")

    ok = TranscriptProjector(approval_auth_key=runtime_key)
    emitted = ok.ingest([event], [_approval_for(event, runtime_key)])
    message = emitted["artifacts"][-1]["messages"][-1]
    print("exact approval       : emitted 1 candidate message")
    print(f"  approval_id        : {message['approval_id']}")
    print(f"  receipt bound      : {message['approval_receipt_sha256'][:24]}â€¦")

    _banner("GUARD â€” every artifact refuses outbound authority")
    artifacts = projected["artifacts"] + emitted["artifacts"]
    print(
        "all external_send_authorized=False : "
        f"{all(a['external_send_authorized'] is False for a in artifacts)}"
    )

    print(f"\nDemo completed in {time.monotonic() - started:.2f}s")
    print("Fixture is synthetic. No customer data, no network, no send authority.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
