from __future__ import annotations

from typing import Any
from datetime import datetime, timezone

from observer import ContractError, canonical_json, choose_action, sha256_hex, validate_policy, validate_snapshot

OUTCOME_KEYS = {"tick_index", "target_id", "success", "science_yield"}


def _exact_int(value: Any, label: str, lo: int, hi: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise ContractError(f"{label} invalid")
    return value


def _outcomes(rows: Any) -> dict[tuple[int, str], dict[str, Any]]:
    if not isinstance(rows, list):
        raise ContractError("outcomes must be list")
    out: dict[tuple[int, str], dict[str, Any]] = {}
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != OUTCOME_KEYS:
            raise ContractError(f"outcome[{i}] schema mismatch")
        tick = _exact_int(row["tick_index"], "tick_index", 0, 10**9)
        target = row["target_id"]
        if not isinstance(target, str) or not target:
            raise ContractError("target_id invalid")
        if not isinstance(row["success"], bool):
            raise ContractError("success must be bool")
        science = _exact_int(row["science_yield"], "science_yield", 0, 10**12)
        key = (tick, target)
        if key in out:
            raise ContractError("duplicate realized outcome key")
        out[key] = {"success": row["success"], "science_yield": science}
    return out


def run_replay(snapshots: Any, outcomes: Any, policy: Any) -> dict[str, Any]:
    clean_policy = validate_policy(policy)
    if not isinstance(snapshots, list) or not snapshots:
        raise ContractError("snapshots must be nonempty list")
    realized = _outcomes(outcomes)
    clean_snapshots = [validate_snapshot(s, clean_policy) for s in snapshots]
    episode = clean_snapshots[0]["episode_id"]
    ticks = [s["tick_index"] for s in clean_snapshots]
    if any(s["episode_id"] != episode for s in clean_snapshots):
        raise ContractError("cross-episode snapshot transplant")
    if ticks != list(range(ticks[0], ticks[0] + len(ticks))):
        raise ContractError("snapshot ticks must be contiguous")
    times = [datetime.strptime(s["timestamp_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) for s in clean_snapshots]
    if any(int((b - a).total_seconds()) != 900 for a, b in zip(times, times[1:])):
        raise ContractError("replay timestamps must advance exactly 900 seconds per tick")

    decisions = []
    total_yield = successes = failures = switches = budget_used = 0
    targets: set[str] = set()
    previous: str | None = clean_snapshots[0]["current_target_id"]
    for snapshot in clean_snapshots:
        receipt = choose_action(snapshot, clean_policy)
        action = receipt["action"]
        record = {
            "tick_index": snapshot["tick_index"],
            "action": action,
            "decision_receipt_sha256": receipt["receipt_sha256"],
            "realized_success": None,
            "realized_science_yield": 0,
        }
        if action["kind"] == "OBSERVE":
            target = action["target_id"]
            candidate = next(c for c in snapshot["candidates"] if c["target_id"] == target)
            switch_cost = candidate["switch_cost"] if previous not in (None, target) else 0
            budget_used += candidate["observation_cost"] + switch_cost
            if previous not in (None, target):
                switches += 1
            previous = target
            targets.add(target)
            key = (snapshot["tick_index"], target)
            if key not in realized:
                raise ContractError(f"missing realized outcome for chosen action {key}")
            outcome = realized[key]
            record["realized_success"] = outcome["success"]
            record["realized_science_yield"] = outcome["science_yield"] if outcome["success"] else 0
            if outcome["success"]:
                successes += 1
                total_yield += outcome["science_yield"]
            else:
                failures += 1
        decisions.append(record)

    body = {
        "foundation_evaluation_only": True,
        "official_score_claimed": False,
        "episode_id": episode,
        "ticks": len(clean_snapshots),
        "total_science_yield": total_yield,
        "successes": successes,
        "failures": failures,
        "switches": switches,
        "budget_used": budget_used,
        "unique_targets": len(targets),
        "decisions": decisions,
        "snapshot_sequence_sha256": sha256_hex(canonical_json(clean_snapshots)),
        "outcomes_sha256": sha256_hex(canonical_json(outcomes)),
        "policy_sha256": sha256_hex(canonical_json(clean_policy)),
    }
    return {**body, "receipt_sha256": sha256_hex(canonical_json(body))}
