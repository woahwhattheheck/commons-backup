from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable

SCHEMA_VERSION = "agentic-cosmos-foundation/v1"
TICK_SECONDS = 900
PPM = 1_000_000
MAX_CANDIDATES = 128
MAX_HISTORY = 4096
MAX_HORIZON = 8
MAX_BEAM = 512
MAX_BUDGET = 10**12

SNAPSHOT_KEYS = {
    "schema_version", "episode_id", "tick_index", "timestamp_utc", "tick_seconds",
    "remaining_budget", "current_target_id", "recent_observations", "candidates",
}
CANDIDATE_KEYS = {
    "target_id", "tags", "observation_cost", "switch_cost", "now",
    "forecast",
}
NOW_KEYS = {"available", "science_value", "visibility_ppm", "weather_success_ppm"}
FORECAST_KEYS = {"offset_ticks", "available", "science_value", "visibility_ppm", "weather_success_ppm"}
HISTORY_KEYS = {"tick_index", "target_id", "tags", "success"}
POLICY_KEYS = {
    "horizon_ticks", "beam_width", "switch_penalty", "repeat_penalty",
    "revisit_bonus_per_tick", "revisit_bonus_cap", "new_tag_bonus", "idle_score",
}

class ContractError(ValueError):
    pass


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pairs_no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_json_loads(raw: str) -> Any:
    if not isinstance(raw, str):
        raise ContractError("JSON input must be text")
    try:
        return json.loads(
            raw,
            object_pairs_hook=_pairs_no_dupes,
            parse_constant=lambda token: (_ for _ in ()).throw(ContractError(f"non-finite number: {token}")),
        )
    except ContractError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ContractError(f"invalid JSON: {exc}") from exc


def _exact_keys(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be an object")
    actual = set(value)
    if actual != keys:
        raise ContractError(f"{label} schema mismatch missing={sorted(keys-actual)} unknown={sorted(actual-keys)}")
    return dict(value)


def _int(value: Any, label: str, lo: int, hi: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise ContractError(f"{label} must be exact int in [{lo},{hi}]")
    return value


def _bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ContractError(f"{label} must be boolean")
    return value


def _token(value: Any, label: str, max_len: int = 96) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise ContractError(f"{label} must be nonempty string <= {max_len}")
    if any(ord(c) < 33 or ord(c) == 127 or c.isspace() for c in value):
        raise ContractError(f"{label} must be an opaque token without whitespace/control chars")
    lowered = value.lower()
    if "@" in value or any(x in lowered for x in ("password", "passwd", "secret=", "token=", "api_key", "bearer")):
        raise ContractError(f"{label} must not contain PII/secret-shaped material")
    return value


def _timestamp(value: Any) -> str:
    if not isinstance(value, str) or len(value) != 20 or not value.endswith("Z"):
        raise ContractError("timestamp_utc must be canonical YYYY-MM-DDTHH:MM:SSZ")
    # Lexical canonicality is enough for the foundation; organizer adapter owns clock provenance.
    try:
        import datetime as _dt
        parsed = _dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
            raise ValueError
    except ValueError as exc:
        raise ContractError("timestamp_utc must be canonical UTC") from exc
    return value


def _tags(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 32:
        raise ContractError(f"{label} must be list <=32")
    tags = [_token(x, label, 48) for x in value]
    if len(tags) != len(set(tags)):
        raise ContractError(f"{label} must be unique")
    return sorted(tags)


def _state_point(value: Any, label: str, *, forecast: bool) -> dict[str, Any]:
    row = _exact_keys(value, FORECAST_KEYS if forecast else NOW_KEYS, label)
    if forecast:
        row["offset_ticks"] = _int(row["offset_ticks"], f"{label}.offset_ticks", 1, MAX_HORIZON-1)
    row["available"] = _bool(row["available"], f"{label}.available")
    row["science_value"] = _int(row["science_value"], f"{label}.science_value", 0, 10**9)
    row["visibility_ppm"] = _int(row["visibility_ppm"], f"{label}.visibility_ppm", 0, PPM)
    row["weather_success_ppm"] = _int(row["weather_success_ppm"], f"{label}.weather_success_ppm", 0, PPM)
    return row


def validate_policy(policy: Any) -> dict[str, int]:
    row = _exact_keys(policy, POLICY_KEYS, "policy")
    row["horizon_ticks"] = _int(row["horizon_ticks"], "horizon_ticks", 1, MAX_HORIZON)
    row["beam_width"] = _int(row["beam_width"], "beam_width", 1, MAX_BEAM)
    for key in ("switch_penalty", "repeat_penalty", "revisit_bonus_per_tick", "revisit_bonus_cap", "new_tag_bonus"):
        row[key] = _int(row[key], key, 0, 10**9)
    row["idle_score"] = _int(row["idle_score"], "idle_score", -10**9, 10**9)
    return row


def validate_snapshot(snapshot: Any, policy: dict[str, int] | None = None) -> dict[str, Any]:
    row = _exact_keys(snapshot, SNAPSHOT_KEYS, "snapshot")
    if row["schema_version"] != SCHEMA_VERSION:
        raise ContractError("unsupported schema_version")
    row["episode_id"] = _token(row["episode_id"], "episode_id")
    row["tick_index"] = _int(row["tick_index"], "tick_index", 0, 10**9)
    row["timestamp_utc"] = _timestamp(row["timestamp_utc"])
    if row["tick_seconds"] != TICK_SECONDS or isinstance(row["tick_seconds"], bool):
        raise ContractError("tick_seconds must be exactly 900")
    row["remaining_budget"] = _int(row["remaining_budget"], "remaining_budget", 0, MAX_BUDGET)
    if row["current_target_id"] is not None:
        row["current_target_id"] = _token(row["current_target_id"], "current_target_id")

    hist = row["recent_observations"]
    if not isinstance(hist, list) or len(hist) > MAX_HISTORY:
        raise ContractError("recent_observations must be list within bound")
    clean_hist = []
    prev_tick = -1
    for i, item in enumerate(hist):
        item = _exact_keys(item, HISTORY_KEYS, f"history[{i}]")
        item["tick_index"] = _int(item["tick_index"], f"history[{i}].tick_index", 0, row["tick_index"] - 1 if row["tick_index"] else 0)
        if row["tick_index"] == 0:
            raise ContractError("tick 0 cannot contain prior observations")
        if item["tick_index"] <= prev_tick:
            raise ContractError("history tick_index must be strictly increasing")
        prev_tick = item["tick_index"]
        item["target_id"] = _token(item["target_id"], f"history[{i}].target_id")
        item["tags"] = _tags(item["tags"], f"history[{i}].tags")
        item["success"] = _bool(item["success"], f"history[{i}].success")
        clean_hist.append(item)
    row["recent_observations"] = clean_hist

    candidates = row["candidates"]
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= MAX_CANDIDATES:
        raise ContractError(f"candidates must have 1..{MAX_CANDIDATES} rows")
    clean = []
    seen = set()
    horizon = policy["horizon_ticks"] if policy else MAX_HORIZON
    for i, item in enumerate(candidates):
        item = _exact_keys(item, CANDIDATE_KEYS, f"candidate[{i}]")
        item["target_id"] = _token(item["target_id"], f"candidate[{i}].target_id")
        if item["target_id"] in seen:
            raise ContractError("duplicate candidate target_id")
        seen.add(item["target_id"])
        item["tags"] = _tags(item["tags"], f"candidate[{i}].tags")
        item["observation_cost"] = _int(item["observation_cost"], f"candidate[{i}].observation_cost", 0, MAX_BUDGET)
        item["switch_cost"] = _int(item["switch_cost"], f"candidate[{i}].switch_cost", 0, MAX_BUDGET)
        item["now"] = _state_point(item["now"], f"candidate[{i}].now", forecast=False)
        forecasts = item["forecast"]
        if not isinstance(forecasts, list) or len(forecasts) > MAX_HORIZON - 1:
            raise ContractError("forecast must be bounded list")
        clean_fc = [_state_point(x, f"candidate[{i}].forecast[{j}]", forecast=True) for j, x in enumerate(forecasts)]
        offsets = [x["offset_ticks"] for x in clean_fc]
        if offsets != sorted(set(offsets)):
            raise ContractError("forecast offsets must be strictly increasing and unique")
        if any(x >= horizon for x in offsets):
            raise ContractError("forecast offset exceeds policy horizon")
        item["forecast"] = clean_fc
        clean.append(item)
    row["candidates"] = sorted(clean, key=lambda x: x["target_id"])
    return row


def default_policy() -> dict[str, int]:
    return {
        "horizon_ticks": 4,
        "beam_width": 96,
        "switch_penalty": 1,
        "repeat_penalty": 25_000,
        "revisit_bonus_per_tick": 2_000,
        "revisit_bonus_cap": 40_000,
        "new_tag_bonus": 8_000,
        "idle_score": -1,
    }


def _point(candidate: dict[str, Any], offset: int) -> dict[str, Any] | None:
    if offset == 0:
        return candidate["now"]
    for point in candidate["forecast"]:
        if point["offset_ticks"] == offset:
            return point
    return None


def _history_maps(history: list[dict[str, Any]], tick: int) -> tuple[dict[str, int], set[str]]:
    last_seen: dict[str, int] = {}
    seen_tags: set[str] = set()
    for row in history:
        if row["tick_index"] >= tick:
            raise ContractError("history contains current/future tick")
        last_seen[row["target_id"]] = row["tick_index"]
        if row["success"]:
            seen_tags.update(row["tags"])
    return last_seen, seen_tags


def _reward(
    candidate: dict[str, Any], point: dict[str, Any], *, offset: int, base_tick: int,
    last_target: str | None, last_seen: dict[str, int], seen_tags: set[str],
    planned_schedule: tuple[str, ...], by_id: dict[str, dict[str, Any]], policy: dict[str, int]
) -> int:
    expected = point["science_value"] * point["visibility_ppm"] // PPM
    expected = expected * point["weather_success_ppm"] // PPM
    score = expected
    if last_target is not None and last_target != candidate["target_id"]:
        score -= policy["switch_penalty"] * candidate["switch_cost"]

    # Horizon evaluation must evolve its own planned state. A target/tag already
    # scheduled earlier in this beam is no longer "new" at a later offset.
    previous = last_seen.get(candidate["target_id"])
    planned_seen_tags = set(seen_tags)
    for planned_offset, target in enumerate(planned_schedule):
        if target == "IDLE":
            continue
        planned = by_id[target]
        planned_seen_tags.update(planned["tags"])
        if target == candidate["target_id"]:
            previous = base_tick + planned_offset
    if previous is None:
        score += policy["revisit_bonus_cap"]
    else:
        age = max(0, base_tick + offset - previous)
        score += min(policy["revisit_bonus_cap"], age * policy["revisit_bonus_per_tick"])
        if last_target == candidate["target_id"]:
            score -= policy["repeat_penalty"]
    novel = sum(1 for tag in candidate["tags"] if tag not in planned_seen_tags)
    score += novel * policy["new_tag_bonus"]
    return score


@dataclass(frozen=True)
class BeamState:
    score: int
    budget: int
    last_target: str | None
    schedule: tuple[str, ...]


def choose_action(snapshot: Any, policy: Any | None = None) -> dict[str, Any]:
    clean_policy = validate_policy(default_policy() if policy is None else policy)
    clean = validate_snapshot(snapshot, clean_policy)
    last_seen, seen_tags = _history_maps(clean["recent_observations"], clean["tick_index"])
    candidates = clean["candidates"]
    by_id = {c["target_id"]: c for c in candidates}
    states = [BeamState(score=0, budget=clean["remaining_budget"], last_target=clean["current_target_id"], schedule=())]

    for offset in range(clean_policy["horizon_ticks"]):
        expanded: list[BeamState] = []
        for state in states:
            expanded.append(BeamState(
                score=state.score + clean_policy["idle_score"],
                budget=state.budget,
                last_target=state.last_target,
                schedule=state.schedule + ("IDLE",),
            ))
            for candidate in candidates:
                point = _point(candidate, offset)
                if point is None or not point["available"]:
                    continue
                switch = candidate["switch_cost"] if state.last_target not in (None, candidate["target_id"]) else 0
                total_cost = candidate["observation_cost"] + switch
                if total_cost > state.budget:
                    continue
                score = _reward(
                    candidate, point, offset=offset, base_tick=clean["tick_index"],
                    last_target=state.last_target, last_seen=last_seen, seen_tags=seen_tags,
                    planned_schedule=state.schedule, by_id=by_id, policy=clean_policy,
                )
                expanded.append(BeamState(
                    score=state.score + score,
                    budget=state.budget - total_cost,
                    last_target=candidate["target_id"],
                    schedule=state.schedule + (candidate["target_id"],),
                ))
        # Deterministic beam. Prefer higher score, more remaining budget, lexical schedule.
        expanded.sort(key=lambda s: (-s.score, -s.budget, s.schedule, s.last_target or ""))
        states = expanded[: clean_policy["beam_width"]]
        if not states:
            raise ContractError("planner produced no states")

    best = states[0]
    first = best.schedule[0]
    if first == "IDLE":
        action = {"kind": "IDLE", "target_id": None}
    else:
        action = {"kind": "OBSERVE", "target_id": first}

    candidate_digest = sha256_hex(canonical_json(candidates))
    body = {
        "schema_version": SCHEMA_VERSION,
        "episode_id": clean["episode_id"],
        "tick_index": clean["tick_index"],
        "tick_seconds": TICK_SECONDS,
        "snapshot_sha256": sha256_hex(canonical_json(clean)),
        "candidate_set_sha256": candidate_digest,
        "policy_sha256": sha256_hex(canonical_json(clean_policy)),
        "action": action,
        "planned_schedule": list(best.schedule),
        "planned_score": best.score,
        "planned_remaining_budget": best.budget,
        "causal_boundary": "CURRENT_OBSERVATIONS_PLUS_EXPLICIT_FORECASTS_ONLY",
        "official_score_claimed": False,
        "submission_claimed": False,
    }
    return {**body, "receipt_sha256": sha256_hex(canonical_json(body))}


def verify_decision(receipt: Any, snapshot: Any, policy: Any | None = None) -> bool:
    if not isinstance(receipt, dict) or not isinstance(receipt.get("receipt_sha256"), str):
        return False
    body = dict(receipt)
    digest = body.pop("receipt_sha256", None)
    if digest != sha256_hex(canonical_json(body)):
        return False
    try:
        rebuilt = choose_action(snapshot, policy)
    except (ContractError, ValueError, TypeError, KeyError):
        return False
    return canonical_json(rebuilt) == canonical_json(receipt)
