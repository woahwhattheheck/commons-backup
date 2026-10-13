#!/usr/bin/env python3
"""Verify the source-pinned current-TITAN versus Apex mirrored shard."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
from typing import Any

EXPECTED = {
    "archive_sha256": "87d7b8bf7c4e9467f4b6b46887abe2eb03735c42453cdbf4f2cac12c5962acc7",
    "archive_bytes": 292007,
    "candidate_sha256": "a4ecdb513b48fa51877fe509597a84dd753dfe71d2d76a406ee3dc51475a9008",
    "engine_ref": "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c",
    "seed": 9969019,
    "candidate_cash": 112839.0,
    "rival_cash": 109760.0,
    "margin": 3079.0,
    "events": 719,
    "trace_sha256": {
        0: "f7e31be143d10391a33f29df503567d292a4a5dda4e6b9ebb9de8838eed7800d",
        1: "6a78aae9dac98512daf87f5988599c4c86889aeda2ee298731918d8fff761124",
    },
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest()


def load_trace(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            try:
                rows.append(json.loads(line))
            except Exception as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
    return rows


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("results/RESULTS.json"))
    parser.add_argument("--trace-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("results/VERIFICATION.json"))
    args = parser.parse_args()

    results = json.loads(args.results.read_text())
    require(results["archive"]["sha256"] == EXPECTED["archive_sha256"], "archive digest")
    require(results["archive"]["bytes"] == EXPECTED["archive_bytes"], "archive size")
    require(results["candidate"]["sha256"] == EXPECTED["candidate_sha256"], "candidate digest")
    require(results["engine_ref"] == EXPECTED["engine_ref"], "engine ref")
    require(results["seed"] == EXPECTED["seed"], "seed")
    require(results["summary"]["scheduled"] == 2, "scheduled count")
    require(results["summary"]["completed"] == 2, "completed count")
    require(results["summary"]["failed"] == 0, "failure count")
    require(results["summary"]["wins"] == 2, "win count")

    games = {int(game["candidate_seat"]): game for game in results["games"]}
    require(set(games) == {0, 1}, "candidate seats")
    traces: dict[int, list[dict[str, Any]]] = {}
    file_receipts: dict[str, Any] = {}
    for seat, game in games.items():
        require(game["seed"] == EXPECTED["seed"], f"seat{seat} seed")
        require(game["status"] == "complete" and game["failure"] is None, f"seat{seat} completion")
        require(game["verdict"] == "W", f"seat{seat} verdict")
        require(game["candidate_cash"] == EXPECTED["candidate_cash"], f"seat{seat} candidate cash")
        require(game["rival_cash"] == EXPECTED["rival_cash"], f"seat{seat} rival cash")
        require(game["margin"] == EXPECTED["margin"], f"seat{seat} margin")
        expected_scores = [EXPECTED["candidate_cash"], EXPECTED["rival_cash"]]
        if seat == 1:
            expected_scores.reverse()
        require(game["scores"] == expected_scores, f"seat{seat} score ordering")
        require(game["steps"] == EXPECTED["events"], f"seat{seat} game steps")
        trace_path = args.trace_dir / game["action_trace"]["path"]
        require(trace_path.is_file(), f"missing trace {trace_path}")
        digest = sha256(trace_path)
        require(digest == EXPECTED["trace_sha256"][seat], f"seat{seat} trace digest")
        rows = load_trace(trace_path)
        require(len(rows) == EXPECTED["events"], f"seat{seat} trace row count")
        require([row["step"] for row in rows] == list(range(EXPECTED["events"])), f"seat{seat} steps")
        traces[seat] = rows
        file_receipts[trace_path.name] = {"bytes": trace_path.stat().st_size, "sha256": digest}

    # Swapping candidate seats must swap the complete public game stream.
    normalized_candidate_0 = [row["actions"][0] for row in traces[0]]
    normalized_candidate_1 = [row["actions"][1] for row in traces[1]]
    normalized_apex_0 = [row["actions"][1] for row in traces[0]]
    normalized_apex_1 = [row["actions"][0] for row in traces[1]]
    require(normalized_candidate_0 == normalized_candidate_1, "candidate action mirror")
    require(normalized_apex_0 == normalized_apex_1, "Apex action mirror")

    for left, right in zip(traces[0], traces[1], strict=True):
        require(left["bank_before"] == list(reversed(right["bank_before"])), "bank-before mirror")
        require(left["bank_after"] == list(reversed(right["bank_after"])), "bank-after mirror")
        require(left["status_after"] == list(reversed(right["status_after"])), "status mirror")
        require(left["reward_after"] == list(reversed(right["reward_after"])), "reward mirror")

    require(
        [row["bank"] for row in games[0]["daily_bank"]]
        == [list(reversed(row["bank"])) for row in games[1]["daily_bank"]],
        "daily-bank mirror",
    )
    require(
        [row["step"] for row in games[0]["daily_bank"]]
        == [row["step"] for row in games[1]["daily_bank"]],
        "daily-bank step mirror",
    )

    verification = {
        "schema_version": 1,
        "successful": True,
        "independent_seeds": 1,
        "mirrored_seat_records": 2,
        "seed": EXPECTED["seed"],
        "result": {
            "wins": 2,
            "ties": 0,
            "losses": 0,
            "candidate_cash": EXPECTED["candidate_cash"],
            "rival_cash": EXPECTED["rival_cash"],
            "margin": EXPECTED["margin"],
        },
        "checks": {
            "source_and_archive_pins": True,
            "complete_games": True,
            "candidate_action_mirror": True,
            "apex_action_mirror": True,
            "public_bank_status_reward_mirror": True,
            "daily_bank_mirror": True,
        },
        "normalized_digests": {
            "candidate_actions": canonical_digest(normalized_candidate_0),
            "apex_actions": canonical_digest(normalized_apex_0),
            "candidate_bank_trajectory": canonical_digest([
                [row["bank_before"][0], row["bank_after"][0]] for row in traces[0]
            ]),
            "apex_bank_trajectory": canonical_digest([
                [row["bank_before"][1], row["bank_after"][1]] for row in traces[0]
            ]),
        },
        "files": file_receipts,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix(args.output.suffix + ".tmp")
    temp.write_text(json.dumps(verification, indent=2, sort_keys=True) + "\n")
    os.replace(temp, args.output)
    print(json.dumps(verification, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
