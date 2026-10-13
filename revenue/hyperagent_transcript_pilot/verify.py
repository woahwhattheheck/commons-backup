"""Executable acceptance proof for the Hyperagent transcript pilot artifact."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .adapter import ProjectionLedger, load_fixture, normalize_event


def main() -> int:
    fixture_path = Path(__file__).with_name("fixture.json")
    fixture_bytes = fixture_path.read_bytes()
    events = load_fixture(fixture_path)
    backends = {normalize_event(event).backend for event in events}

    first = ProjectionLedger()
    first_result = first.project_batch(events)
    first_snapshot = first.snapshot_bytes()
    replay = first.project_batch(events)

    second = ProjectionLedger()
    second.project_batch(list(reversed(events)))
    second_snapshot = second.snapshot_bytes()

    checks = {
        "event_count": len(events) == 30,
        "backend_count": len(backends) == 3,
        "first_pass_new_messages": len(first_result.new_messages) == 30,
        "first_pass_rejections": len(first_result.rejected) == 0,
        "transcript_count": first.snapshot()["transcript_count"] == 6,
        "replay_new_messages": len(replay.new_messages) == 0,
        "replay_duplicate_events": replay.duplicate_event_count == 30,
        "byte_identical_clean_projection": first_snapshot == second_snapshot,
    }
    proof = {
        "schema": "hyperagent-transcript-pilot-proof/v1",
        "passed": all(checks.values()),
        "checks": checks,
        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "snapshot_sha256": hashlib.sha256(first_snapshot).hexdigest(),
        "transcript_count": first.snapshot()["transcript_count"],
        "message_count": first.snapshot()["message_count"],
        "replay_new_messages": len(replay.new_messages),
    }
    print(json.dumps(proof, sort_keys=True, separators=(",", ":")))
    return 0 if proof["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
