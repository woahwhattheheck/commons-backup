# SPDX-License-Identifier: Apache-2.0
"""Validate a source-fixed current-a8af input-budget paired panel.

This reads existing reports only.  It never calls a policy, interpreter, or game.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
from statistics import fmean

SEEDS = (9852401, 9852419)
OPPONENTS = ("sell", "apex")
SEATS = (0, 1)
ARMS = ("control", "candidate")
EXPECTED_ARCHIVE = "a8af2b834bb5e1d6486245b9538c2de5a041085be38c7707d08e6d49e6149e89"
EXPECTED_AGENT = "58ea0d32db8e5f40de86f45f3709d065c3ccdb7c09ee11adcae3ebc0ee6ef9d7"
EXPECTED_CANDIDATE_BLOB = "19893f2c5d7b4835a14119d2dd489bef819f076d"
EXPECTED_CORE_BLOB = "f64e932d6c6959a95574d245ab36808a4c4a85e3"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verdict(own: float, rival: float) -> str:
    return "W" if own > rival else "L" if own < rival else "T"


def load_frames(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    if [row.get("step") for row in rows] != list(range(719)):
        raise ValueError(f"Unexpected frame steps in {path}")
    return rows


def physical_farms(observation: dict) -> list[dict]:
    farms = copy.deepcopy(observation["farms"])
    for farm in farms:
        farm.pop("money", None)
    return farms


def nonfert_private(observation: dict) -> dict:
    private = copy.deepcopy(observation["private"])
    private.get("shed", {}).pop("FERTILIZER", None)
    for inventory in private.get("inventories", []):
        inventory.pop("FERTILIZER", None)
    return private


def nonfert_market(observation: dict) -> dict:
    market = copy.deepcopy(observation["market"])
    for key in ("inventory", "prices"):
        market.get(key, {}).pop("FERTILIZER", None)
    return market


def market_shape(action: dict) -> list:
    """Preserve order/slot/op while ignoring only FERTILIZER quantity."""
    out = []
    for order in action.get("market", []):
        if (isinstance(order, list) and len(order) > 1 and
                order[1] == "FERTILIZER" and order[0] in ("BUY_PRODUCT", "SELL")):
            out.append([order[0], "FERTILIZER", "QUANTITY"])
        else:
            out.append(copy.deepcopy(order))
    return out


def fert_buy(action: dict) -> int | None:
    values = [order[2] for order in action.get("market", [])
              if isinstance(order, list) and len(order) >= 3 and
              order[0] == "BUY_PRODUCT" and order[1] == "FERTILIZER"]
    return values[0] if len(values) == 1 else None


def inspect_pair(control_dir: Path, candidate_dir: Path, opponent: str,
                 seed: int, seat: int) -> dict:
    control = json.loads((control_dir / "result.json").read_text())
    candidate = json.loads((candidate_dir / "result.json").read_text())
    for result, arm in ((control, "control"), (candidate, "candidate")):
        if result.get("arm") != arm or result.get("opponent") != opponent or result.get("seed") != seed or result.get("candidate_seat") != seat:
            raise ValueError(f"Result identity mismatch: {arm}/{opponent}/{seed}/{seat}")
        if result.get("status") != "complete" or result.get("failure") is not None:
            raise ValueError(f"Incomplete result: {arm}/{opponent}/{seed}/{seat}")
    a = load_frames(control_dir / "frames.jsonl.gz")
    b = load_frames(candidate_dir / "frames.jsonl.gz")
    exact_action_diffs = []
    own_market_diffs = []
    rival_market_diffs = []
    worker_checks = physical_checks = private_checks = market_checks = queue_checks = 0
    for left, right in zip(a, b):
        step = left["step"]
        if step != right["step"]:
            raise ValueError("Step mismatch")
        if left["actions"] != right["actions"]:
            exact_action_diffs.append(step)
        for player in (0, 1):
            la, ra = left["actions"][player], right["actions"][player]
            if (la.get("farmer"), la.get("hands")) != (ra.get("farmer"), ra.get("hands")):
                raise ValueError(f"Worker action changed at {step}, player {player}")
            worker_checks += 1
            if market_shape(la) != market_shape(ra):
                raise ValueError(f"Non-fertilizer queue/slot changed at {step}, player {player}")
            queue_checks += 1
            if la.get("market") != ra.get("market"):
                (own_market_diffs if player == seat else rival_market_diffs).append(step)
        for player in (0, 1):
            lo, ro = left["observations"][player], right["observations"][player]
            if physical_farms(lo) != physical_farms(ro):
                raise ValueError(f"Physical farm changed before step {step}, observer {player}")
            physical_checks += 1
            if nonfert_private(lo) != nonfert_private(ro):
                raise ValueError(f"Non-FERT private state changed before step {step}, observer {player}")
            private_checks += 1
            if nonfert_market(lo) != nonfert_market(ro):
                raise ValueError(f"Non-FERT market changed before step {step}, observer {player}")
            market_checks += 1
            for key in ("town", "day", "hour", "player", "step"):
                if lo.get(key) != ro.get(key):
                    raise ValueError(f"Observation metadata changed at {step}, observer {player}, {key}")
    requested = fert_buy(a[696]["actions"][seat])
    retained = fert_buy(b[696]["actions"][seat])
    active = requested is not None and retained is not None and retained < requested
    if active:
        if requested - retained != 1:
            raise ValueError("Active current candidate did not trim exactly one unit")
        if any(step < 696 for step in exact_action_diffs):
            raise ValueError("Candidate diverged before final-day opening")
    elif exact_action_diffs:
        raise ValueError("Inactive pair has action differences")
    cs, ns = control["scores"], candidate["scores"]
    own_c, rival_c = cs[seat], cs[1-seat]
    own_n, rival_n = ns[seat], ns[1-seat]
    return {
        "opponent": opponent, "seed": seed, "seat": seat, "active": active,
        "requested_fertilizer": requested, "retained_fertilizer": retained,
        "exact_action_diff_steps": exact_action_diffs,
        "own_market_diff_steps": sorted(set(own_market_diffs)),
        "rival_market_diff_steps": sorted(set(rival_market_diffs)),
        "worker_action_checks": worker_checks, "physical_farm_checks": physical_checks,
        "nonfert_private_checks": private_checks, "nonfert_market_checks": market_checks,
        "queue_shape_checks": queue_checks,
        "control_own": own_c, "control_rival": rival_c,
        "candidate_own": own_n, "candidate_rival": rival_n,
        "d_own": own_n-own_c, "d_rival": rival_n-rival_c,
        "d_margin": (own_n-rival_n)-(own_c-rival_c),
        "control_verdict": verdict(own_c, rival_c),
        "candidate_verdict": verdict(own_n, rival_n),
        "control_trace_sha256": control["trace_sha256"],
        "candidate_trace_sha256": candidate["trace_sha256"],
        "control_frames_sha256": sha(control_dir / "frames.jsonl.gz"),
        "candidate_frames_sha256": sha(candidate_dir / "frames.jsonl.gz"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--source-freeze", type=Path, required=True)
    parser.add_argument("--raw-check", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    freeze = json.loads(args.source_freeze.read_text())
    if freeze.get("archive_sha256") != EXPECTED_ARCHIVE:
        raise ValueError("Wrong canonical archive")
    if freeze["runtime/titan_runtime.py"]["sha256"] != EXPECTED_AGENT:
        raise ValueError("Wrong TitanAgent")
    if freeze["work/candidate.py"]["git_blob"] != EXPECTED_CANDIDATE_BLOB:
        raise ValueError("Wrong candidate adapter")
    if freeze["work/input_budget.py"]["git_blob"] != EXPECTED_CORE_BLOB:
        raise ValueError("Wrong input-budget core")
    raw = json.loads(args.raw_check.read_text())
    if raw.get("actions") != 719 or raw.get("mismatched_steps") != [] or raw.get("candidate_git_blob") != EXPECTED_CANDIDATE_BLOB:
        raise ValueError("Raw-file correspondence is incomplete")
    pairs = []
    for opponent in OPPONENTS:
        for seed in SEEDS:
            for seat in SEATS:
                pairs.append(inspect_pair(
                    args.panel / f"control-{opponent}-{seed}-p{seat}",
                    args.panel / f"candidate-{opponent}-{seed}-p{seat}",
                    opponent, seed, seat))
    result = {
        "schema": "titan.current-a8af.input-budget-correspondence.v1",
        "archive_sha256": EXPECTED_ARCHIVE,
        "runtime_titan_agent_sha256": EXPECTED_AGENT,
        "candidate_git_blob": EXPECTED_CANDIDATE_BLOB,
        "input_budget_git_blob": EXPECTED_CORE_BLOB,
        "games": 16, "pairs": len(pairs), "complete": True,
        "active_pairs": sum(row["active"] for row in pairs),
        "inactive_pairs": sum(not row["active"] for row in pairs),
        "worker_action_checks": sum(row["worker_action_checks"] for row in pairs),
        "physical_farm_checks": sum(row["physical_farm_checks"] for row in pairs),
        "nonfert_private_checks": sum(row["nonfert_private_checks"] for row in pairs),
        "nonfert_market_checks": sum(row["nonfert_market_checks"] for row in pairs),
        "queue_shape_checks": sum(row["queue_shape_checks"] for row in pairs),
        "mean_d_own": fmean(row["d_own"] for row in pairs),
        "mean_d_rival": fmean(row["d_rival"] for row in pairs),
        "mean_d_margin": fmean(row["d_margin"] for row in pairs),
        "flips": {},
        "raw_entrypoint": raw,
        "pairs_detail": pairs,
        "limits": [
            "Development-only two-seed bank; mirrored seats are not independent samples.",
            "No W/T/L improvement in this bank; cash effects are small.",
            "Main-thread raw-file check does not cover the separately owned a8af worker-thread deadline defect.",
            "Wrapper is not installed in the canonical archive or enabled by default."
        ],
    }
    for row in pairs:
        key = row["control_verdict"] + "->" + row["candidate_verdict"]
        if key not in ("W->W", "T->T", "L->L"):
            result["flips"][key] = result["flips"].get(key, 0) + 1
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "pairs_detail"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
