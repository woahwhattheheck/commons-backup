# SPDX-License-Identifier: Apache-2.0
"""Validate retained main-thread and persistent-worker consumer results."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

EXPECTED_ARCHIVE = "7b58fa06da778b1519b81d509d28dff3481b3bbcc7a2d656e8bdfe4a22540524"
EXPECTED_AGENT = "58ea0d32db8e5f40de86f45f3709d065c3ccdb7c09ee11adcae3ebc0ee6ef9d7"
EXPECTED_DEADLINE = "c8f7c9842ba7e4eb29f6e57a8d6f9ba816140dcbea7817aea2b3efcabe2771c5"
EXPECTED_ENTRYPOINT = "760c58e532f5b0b039652bb553645f169d406436cf254e8c259437ae90aeada6"
EXPECTED_FRAMES = "809dacc7441b69fc0919e83c7021261786ba2da9e2992e610d7141ab0912c7c2"


def validate(document: dict, mode: str) -> dict:
    if document.get("schema") != "titan.current-7b58.input-budget-worker-consumer.v1":
        raise ValueError("Unexpected schema")
    expected = {
        "mode": mode,
        "archive_sha256": EXPECTED_ARCHIVE,
        "titan_agent_sha256": EXPECTED_AGENT,
        "deadline_adapter_sha256": EXPECTED_DEADLINE,
        "entrypoint_sha256": EXPECTED_ENTRYPOINT,
        "source_frames_sha256": EXPECTED_FRAMES,
        "actions": 719,
        "errors": [],
        "mismatched_steps": [],
        "fallback_count": None,
    }
    for key, value in expected.items():
        if document.get(key) != value:
            raise ValueError(f"Unexpected {mode} {key}")
    rows = document.get("rows")
    if not isinstance(rows, list) or [row.get("step") for row in rows] != list(range(719)):
        raise ValueError(f"Incomplete {mode} rows")
    if any(row.get("error") is not None or row.get("matches_expected") is not True
           for row in rows):
        raise ValueError(f"Failed {mode} row")
    if document.get("max_call_seconds", 99) >= 2.0:
        raise ValueError(f"Outer deadline exceeded in {mode}")
    return {"mode": mode, "actions": 719,
            "max_call_seconds": document["max_call_seconds"],
            "mean_call_seconds": document["mean_call_seconds"],
            "wall_seconds": document["wall_seconds"]}


def check(main_result: Path, worker_result: Path) -> dict:
    main = json.loads(main_result.read_text())
    worker = json.loads(worker_result.read_text())
    result = {
        "schema": "titan.current-7b58.input-budget-worker-consumer-check.v1",
        "main": validate(main, "main"),
        "worker": validate(worker, "worker"),
        "same_expected_actions": all(
            left["matches_expected"] == right["matches_expected"]
            for left, right in zip(main["rows"], worker["rows"])),
        "worker_to_main_mean_ratio": worker["mean_call_seconds"] / main["mean_call_seconds"],
        "game_calls": 0,
        "fallback_count": None,
    }
    if not result["same_expected_actions"]:
        raise ValueError("Main and worker correspondence differs")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-result", type=Path, required=True)
    parser.add_argument("--worker-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = check(args.main_result, args.worker_result)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
