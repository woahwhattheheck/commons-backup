#!/usr/bin/env python3
"""Verify the source-pinned current-TITAN versus exact frozen-SELL shard."""
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
    "control_sha256": "55cd3a1ac560e12209d7d708d549efcbfff167576b181b2b45338aeb0d754633",
    "engine_ref": "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c",
    "seed": 9969055,
    "candidate_cash": 125508.0,
    "control_cash": 125268.0,
    "margin": 240.0,
    "events": 719,
    "trace_sha256": {
        0: "1c916f8173cc26524ea2acc8e9a317cd079e51a0ccfeebde05230bbf9a3e918a",
        1: "3bf88562d3a9c0644378d6d906d7ec80290903b85f8ac03352417cc1f799043c",
    },
}
EXPECTED_FEATURES = {
    "consumer": "frozen",
    "seed": False,
    "funding": False,
    "committed": False,
    "terminal_route": False,
    "redundant_hire": False,
    "terminal_history": False,
    "budget_seconds": 1.0,
    "reserve_seconds": 0.01,
}
EXPECTED_DIFFS = {
    600: {
        "candidate_order": ["BUY_SEED", "WHEAT", 2],
        "control_order": ["BUY_SEED", "WHEAT", 17],
        "slot": 2,
        "incremental_cash": 150.0,
    },
    624: {
        "candidate_order": [],
        "control_order": ["BUY_SEED", "WHEAT", 9],
        "slot": 1,
        "incremental_cash": 90.0,
    },
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_trace(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            try:
                rows.append(json.loads(line))
            except Exception as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
    return rows


def compare_candidate_control(rows: list[dict[str, Any]], candidate_seat: int) -> list[dict[str, Any]]:
    control_seat = 1 - candidate_seat
    found: list[dict[str, Any]] = []
    running_advantage = 0.0
    for row in rows:
        candidate = row["actions"][candidate_seat]
        control = row["actions"][control_seat]
        require(candidate.get("farmer") == control.get("farmer"), f"step {row['step']}: farmer differs")
        require(candidate.get("hands") == control.get("hands"), f"step {row['step']}: hands differ")
        if candidate == control:
            continue
        step = int(row["step"])
        require(step in EXPECTED_DIFFS, f"unexpected complete-action difference at step {step}")
        expected = EXPECTED_DIFFS[step]
        candidate_market = candidate.get("market")
        control_market = control.get("market")
        require(isinstance(candidate_market, list) and isinstance(control_market, list), f"step {step}: market shape")
        require(len(candidate_market) == len(control_market), f"step {step}: market slot count")
        differing_slots = [i for i, pair in enumerate(zip(candidate_market, control_market, strict=True)) if pair[0] != pair[1]]
        require(differing_slots == [expected["slot"]], f"step {step}: changed slots {differing_slots}")
        slot = expected["slot"]
        require(candidate_market[slot] == expected["candidate_order"], f"step {step}: candidate seed order")
        require(control_market[slot] == expected["control_order"], f"step {step}: control seed order")
        candidate_before = float(row["bank_before"][candidate_seat])
        control_before = float(row["bank_before"][control_seat])
        candidate_after = float(row["bank_after"][candidate_seat])
        control_after = float(row["bank_after"][control_seat])
        require(candidate_before - control_before == running_advantage, f"step {step}: prior cash advantage")
        step_gain = (candidate_after - control_after) - running_advantage
        require(step_gain == expected["incremental_cash"], f"step {step}: cash increment {step_gain}")
        running_advantage += step_gain
        found.append({
            "step": step,
            "slot": slot,
            "candidate_order": candidate_market[slot],
            "control_order": control_market[slot],
            "incremental_cash": step_gain,
            "cumulative_cash": running_advantage,
        })
    require([item["step"] for item in found] == sorted(EXPECTED_DIFFS), "exact decision-difference set")
    require(running_advantage == EXPECTED["margin"], "total causal cash increment")
    return found


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
    require(results["control"]["sha256"] == EXPECTED["control_sha256"], "control digest")
    require(results["control"]["features"] == EXPECTED_FEATURES, "control features")
    require(results["engine_ref"] == EXPECTED["engine_ref"], "engine ref")
    require(results["seed"] == EXPECTED["seed"], "seed")
    require(results["summary"]["scheduled"] == 2, "scheduled count")
    require(results["summary"]["completed"] == 2, "completed count")
    require(results["summary"]["failed"] == 0, "failure count")
    require(results["summary"]["wins"] == 2, "win count")

    games = {int(game["candidate_seat"]): game for game in results["games"]}
    require(set(games) == {0, 1}, "candidate seats")
    traces: dict[int, list[dict[str, Any]]] = {}
    files: dict[str, Any] = {}
    decisions: dict[str, Any] = {}
    for candidate_seat, game in games.items():
        require(game["seed"] == EXPECTED["seed"], f"seat {candidate_seat}: seed")
        require(game["status"] == "complete" and game["failure"] is None, f"seat {candidate_seat}: completion")
        require(game["verdict"] == "W", f"seat {candidate_seat}: verdict")
        require(game["candidate_cash"] == EXPECTED["candidate_cash"], f"seat {candidate_seat}: candidate cash")
        require(game["rival_cash"] == EXPECTED["control_cash"], f"seat {candidate_seat}: control cash")
        require(game["margin"] == EXPECTED["margin"], f"seat {candidate_seat}: margin")
        expected_scores = [EXPECTED["candidate_cash"], EXPECTED["control_cash"]]
        if candidate_seat == 1:
            expected_scores.reverse()
        require(game["scores"] == expected_scores, f"seat {candidate_seat}: score order")
        require(game["steps"] == EXPECTED["events"], f"seat {candidate_seat}: game steps")

        trace_path = args.trace_dir / game["action_trace"]["path"]
        require(trace_path.is_file(), f"missing trace {trace_path}")
        trace_hash = sha256(trace_path)
        require(trace_hash == EXPECTED["trace_sha256"][candidate_seat], f"seat {candidate_seat}: trace digest")
        rows = load_trace(trace_path)
        require(len(rows) == EXPECTED["events"], f"seat {candidate_seat}: trace rows")
        require([row["step"] for row in rows] == list(range(EXPECTED["events"])), f"seat {candidate_seat}: ordered steps")
        traces[candidate_seat] = rows
        decisions[str(candidate_seat)] = compare_candidate_control(rows, candidate_seat)
        files[trace_path.name] = {"bytes": trace_path.stat().st_size, "sha256": trace_hash}

    candidate_actions_0 = [row["actions"][0] for row in traces[0]]
    candidate_actions_1 = [row["actions"][1] for row in traces[1]]
    control_actions_0 = [row["actions"][1] for row in traces[0]]
    control_actions_1 = [row["actions"][0] for row in traces[1]]
    require(candidate_actions_0 == candidate_actions_1, "candidate action mirror")
    require(control_actions_0 == control_actions_1, "control action mirror")
    require(decisions["0"] == decisions["1"], "decision witness mirror")

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
        "daily-bank steps",
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
            "control_cash": EXPECTED["control_cash"],
            "margin": EXPECTED["margin"],
        },
        "decision_differences": decisions["0"],
        "checks": {
            "source_archive_and_control_pins": True,
            "complete_games": True,
            "candidate_action_mirror": True,
            "control_action_mirror": True,
            "only_seed_market_slots_differ": True,
            "all_worker_actions_identical": True,
            "cash_increment_150_plus_90": True,
            "public_bank_status_reward_mirror": True,
            "daily_bank_mirror": True,
        },
        "normalized_digests": {
            "candidate_actions": digest(candidate_actions_0),
            "control_actions": digest(control_actions_0),
            "candidate_bank_trajectory": digest([
                [row["bank_before"][0], row["bank_after"][0]] for row in traces[0]
            ]),
            "control_bank_trajectory": digest([
                [row["bank_before"][1], row["bank_after"][1]] for row in traces[0]
            ]),
        },
        "files": files,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(verification, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, args.output)
    print(json.dumps(verification, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
