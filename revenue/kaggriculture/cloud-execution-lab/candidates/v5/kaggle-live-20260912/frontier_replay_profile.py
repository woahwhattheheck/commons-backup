#!/usr/bin/env python3
"""Profile exact public Kaggriculture replays without pretending replay data is policy code.

The profiler is deliberately offline and fail-closed. A replay is accepted only
when its submission id belongs to the checked-in frontier opponent pack and a
separate episode identity manifest binds episode + seat + submission exactly.
It summarizes returned-action intent under pinned engine parser/cap semantics;
it does not claim orders filled, unit actions succeeded, or a replay is an
executable/counterfactual opponent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

PACK_MANIFEST = "frontier-opponent-pack.json"
SCHEMA_VERSION = 1
MARKET_QUANTITY_OPS = {"BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "SELL"}
MARKET_ATOMIC_OPS = {"HIRE", "BUY_LAND"}
PHASES = ("early", "mid", "late")


class ReplayProfileError(ValueError):
    """Raised when replay/profile provenance is incomplete or malformed."""


def _load_json_object(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReplayProfileError(f"{path.name} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ReplayProfileError(f"{path.name} must contain a JSON object")
    return value, raw


def _plain_int(value: object, *, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReplayProfileError(f"{field} must be a plain integer")
    if value < minimum:
        raise ReplayProfileError(f"{field} must be >= {minimum}")
    return value


def _aliased_plain_int(
    mapping: Mapping[str, Any],
    keys: Sequence[str],
    *,
    field: str,
    minimum: int = 0,
    required: bool,
) -> int | None:
    """Bind redundant public identity spellings to one exact integer value."""
    values: list[tuple[str, int]] = []
    for key in keys:
        if key not in mapping:
            continue
        values.append(
            (key, _plain_int(mapping[key], field=f"{field}.{key}", minimum=minimum))
        )
    if not values:
        if required:
            raise ReplayProfileError(f"{field} is missing")
        return None
    first = values[0][1]
    if any(value != first for _, value in values[1:]):
        names = ", ".join(key for key, _ in values)
        raise ReplayProfileError(f"{field} aliases disagree: {names}")
    return first


def _config_int(config: Mapping[str, Any], key: str, default: int) -> int:
    value = config.get(key, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ReplayProfileError(f"configuration.{key} is not int-coercible") from exc
    return parsed


def _phase(decision_step: int, turns_per_day: int) -> str:
    day = decision_step // turns_per_day
    if day < 10:
        return "early"
    if day < 20:
        return "mid"
    return "late"


def _episode_id_from_replay(replay: Mapping[str, Any]) -> int | None:
    return _aliased_plain_int(
        replay,
        ("episode_id", "episodeId", "id"),
        field="replay episode id",
        minimum=1,
        required=False,
    )


def _episode_agents(manifest: Mapping[str, Any]) -> tuple[int, Sequence[Any]]:
    episode = manifest.get("episode", manifest)
    if not isinstance(episode, dict):
        raise ReplayProfileError("identity manifest episode must be an object")
    episode_id = _aliased_plain_int(
        episode,
        ("id", "episode_id"),
        field="identity episode id",
        minimum=1,
        required=True,
    )
    agents = episode.get("agents")
    if not isinstance(agents, list) or not agents:
        raise ReplayProfileError("identity manifest must contain non-empty agents")
    return episode_id, agents


def _pinned_submission_ids(pack: Mapping[str, Any]) -> set[int]:
    """Return the exact rated frontier ids, rejecting ambiguous pack structure."""
    targets = pack.get("frontier_targets")
    if not isinstance(targets, list):
        raise ReplayProfileError("frontier pack missing frontier_targets")
    pinned: set[int] = set()
    for index, entry in enumerate(targets):
        if not isinstance(entry, dict):
            raise ReplayProfileError(f"frontier_targets[{index}] must be an object")
        submission_id = _plain_int(
            entry.get("rated_submission_id"),
            field=f"frontier_targets[{index}].rated_submission_id",
            minimum=1,
        )
        if submission_id in pinned:
            raise ReplayProfileError(
                f"duplicate rated_submission_id {submission_id} in frontier pack"
            )
        pinned.add(submission_id)
    return pinned


def validate_identity(
    pack: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    submission_id: int,
    seat: int,
    replay_episode_id: int | None,
) -> tuple[int, int]:
    submission_id = _plain_int(submission_id, field="submission_id", minimum=1)
    seat = _plain_int(seat, field="seat", minimum=0)

    pinned = _pinned_submission_ids(pack)
    if submission_id not in pinned:
        raise ReplayProfileError(
            f"submission {submission_id} is not a pinned rated frontier target"
        )

    episode_id, agents = _episode_agents(manifest)
    if seat >= len(agents):
        raise ReplayProfileError(f"seat {seat} not present in identity manifest")
    agent = agents[seat]
    if not isinstance(agent, dict):
        raise ReplayProfileError(f"identity manifest agent {seat} must be an object")
    actual_submission = _aliased_plain_int(
        agent,
        ("submissionId", "submission_id"),
        field=f"identity agents[{seat}] submission id",
        minimum=1,
        required=True,
    )
    if actual_submission != submission_id:
        raise ReplayProfileError(
            f"identity mismatch: seat {seat} is submission {actual_submission}, expected {submission_id}"
        )
    if replay_episode_id is not None and replay_episode_id != episode_id:
        raise ReplayProfileError(
            f"episode mismatch: replay {replay_episode_id}, identity manifest {episode_id}"
        )
    return episode_id, actual_submission


def _market_order(order: object) -> tuple[str, str | None, int | None] | None:
    """Mirror pinned engine `_parse_order` shape/quantity grammar only."""
    if not isinstance(order, list) or not order:
        return None
    op = order[0]
    if op in MARKET_ATOMIC_OPS:
        return str(op), None, None
    if op not in MARKET_QUANTITY_OPS or len(order) < 3:
        return None
    try:
        n = int(order[2])
    except (TypeError, ValueError, OverflowError):
        return None
    if n <= 0:
        return None
    return str(op), str(order[1]), n


def _unit_op(action: object) -> str | None:
    if not isinstance(action, list) or not action:
        return None
    op = action[0]
    return op if isinstance(op, str) and op else None


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def _empty_bucket() -> dict[str, Any]:
    return {
        "decision_steps": 0,
        "unit_ops": Counter(),
        "market_orders": Counter(),
        "market_quantities": Counter(),
        "malformed_unit_actions": 0,
        "malformed_market_rows": 0,
        "truncated_market_rows": 0,
        "sale_steps": [],
        "hire_steps": [],
        "land_steps": [],
        "animal_buy_steps": [],
        "seed_buy_steps": [],
        "plant_steps": [],
        "feed_steps": [],
        "fertilizer_collect_steps": [],
        "harvest_steps": [],
    }


def _record_unit(bucket: dict[str, Any], action: object, step: int) -> None:
    op = _unit_op(action)
    if op is None:
        bucket["malformed_unit_actions"] += 1
        return
    bucket["unit_ops"][op] += 1
    if op == "PLANT":
        crop = action[1] if len(action) > 1 and isinstance(action[1], str) else "?"
        bucket["unit_ops"][f"PLANT:{crop}"] += 1
        bucket["plant_steps"].append(step)
    elif op == "FEED":
        bucket["feed_steps"].append(step)
    elif op == "COLLECT_FERTILIZER":
        bucket["fertilizer_collect_steps"].append(step)
    elif op == "HARVEST":
        bucket["harvest_steps"].append(step)


def _record_market(bucket: dict[str, Any], order: object, step: int) -> None:
    parsed = _market_order(order)
    if parsed is None:
        bucket["malformed_market_rows"] += 1
        return
    op, item, quantity = parsed
    key = op if item is None else f"{op}:{item}"
    bucket["market_orders"][key] += 1
    if quantity is not None:
        bucket["market_quantities"][key] += quantity
    if op == "SELL":
        bucket["sale_steps"].append(step)
    elif op == "HIRE":
        bucket["hire_steps"].append(step)
    elif op == "BUY_LAND":
        bucket["land_steps"].append(step)
    elif op == "BUY_ANIMAL":
        bucket["animal_buy_steps"].append(step)
    elif op == "BUY_SEED":
        bucket["seed_buy_steps"].append(step)


def _gaps(steps: Sequence[int]) -> dict[str, int | float | None]:
    uniq = sorted(set(steps))
    if len(uniq) < 2:
        return {"count": 0, "min": None, "max": None, "mean": None}
    gaps = [b - a for a, b in zip(uniq, uniq[1:])]
    return {
        "count": len(gaps),
        "min": min(gaps),
        "max": max(gaps),
        "mean": sum(gaps) / len(gaps),
    }


def _finalize_bucket(bucket: Mapping[str, Any]) -> dict[str, Any]:
    sale_steps = sorted(set(bucket["sale_steps"]))
    return {
        "decision_steps": bucket["decision_steps"],
        "unit_ops": _counter_dict(bucket["unit_ops"]),
        "market_orders": _counter_dict(bucket["market_orders"]),
        "market_quantities": _counter_dict(bucket["market_quantities"]),
        "malformed_unit_actions": bucket["malformed_unit_actions"],
        "malformed_market_rows": bucket["malformed_market_rows"],
        "truncated_market_rows": bucket["truncated_market_rows"],
        "active_step_counts": {
            "sale": len(sale_steps),
            "hire": len(set(bucket["hire_steps"])),
            "buy_land": len(set(bucket["land_steps"])),
            "buy_animal": len(set(bucket["animal_buy_steps"])),
            "buy_seed": len(set(bucket["seed_buy_steps"])),
            "plant": len(set(bucket["plant_steps"])),
            "feed": len(set(bucket["feed_steps"])),
            "collect_fertilizer": len(set(bucket["fertilizer_collect_steps"])),
            "harvest": len(set(bucket["harvest_steps"])),
        },
        "first_last_sale_step": [sale_steps[0], sale_steps[-1]] if sale_steps else None,
        "sale_step_gaps": _gaps(sale_steps),
    }


def build_profile(
    replay: Mapping[str, Any],
    replay_raw: bytes,
    pack: Mapping[str, Any],
    pack_raw: bytes,
    identity_manifest: Mapping[str, Any],
    identity_raw: bytes,
    *,
    submission_id: int,
    seat: int,
) -> dict[str, Any]:
    replay_episode_id = _episode_id_from_replay(replay)
    episode_id, submission_id = validate_identity(
        pack,
        identity_manifest,
        submission_id=submission_id,
        seat=seat,
        replay_episode_id=replay_episode_id,
    )

    steps = replay.get("steps")
    if not isinstance(steps, list) or len(steps) < 2:
        raise ReplayProfileError("replay.steps must contain at least two rows")
    for row_index, row in enumerate(steps):
        if not isinstance(row, list):
            raise ReplayProfileError(f"replay.steps[{row_index}] must be a list")
        if seat >= len(row):
            raise ReplayProfileError(f"seat {seat} missing from replay row {row_index}")
        if not isinstance(row[seat], dict):
            raise ReplayProfileError(f"replay row {row_index} seat {seat} must be an object")

    config = replay.get("configuration", {})
    if not isinstance(config, dict):
        raise ReplayProfileError("replay.configuration must be an object")
    turns_per_day = max(1, _config_int(config, "turnsPerDay", 24))
    max_orders = max(1, _config_int(config, "maxMarketOrdersPerTurn", 10))

    total = _empty_bucket()
    phases = {name: _empty_bucket() for name in PHASES}

    # Kaggle replay convention used by the saved TITAN evidence: row t+1 stores
    # the action chosen from row t's observation. Thus decision step 0 is row 1.
    for row_index in range(1, len(steps)):
        decision_step = row_index - 1
        target_phase = _phase(decision_step, turns_per_day)
        buckets = (total, phases[target_phase])
        action = steps[row_index][seat].get("action")
        effective = action if isinstance(action, dict) else {}

        farmer_action = effective.get("farmer", ["PASS"])
        hands_actions = effective.get("hands", [])
        if not isinstance(hands_actions, list):
            hands_actions = []
        market = effective.get("market", [])
        if not isinstance(market, list):
            market = []

        visible_market = market[:max_orders]
        truncated = max(0, len(market) - len(visible_market))
        for bucket in buckets:
            bucket["decision_steps"] += 1
            bucket["truncated_market_rows"] += truncated
            _record_unit(bucket, farmer_action, decision_step)
            for hand_action in hands_actions:
                _record_unit(bucket, hand_action, decision_step)
            for order in visible_market:
                _record_market(bucket, order, decision_step)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "titan-v5-public-replay-behavior-profile",
        "identity": {
            "episode_id": episode_id,
            "seat": seat,
            "submission_id": submission_id,
            "replay_sha256": hashlib.sha256(replay_raw).hexdigest(),
            "identity_manifest_sha256": hashlib.sha256(identity_raw).hexdigest(),
            "frontier_pack_sha256": hashlib.sha256(pack_raw).hexdigest(),
        },
        "semantics": {
            "evidence": "recorded_returned_action_intent",
            "not_evidence_of": [
                "order_fill",
                "unit_action_success",
                "counterfactual_policy_behavior",
                "executable_opponent_source",
            ],
            "replay_action_alignment": "row_t_plus_1_action_is_decision_step_t",
            "market_prefix_cap": max_orders,
            "market_order_grammar": "pinned_engine_parse_order",
            "turns_per_day": turns_per_day,
            "phase_days": {"early": [0, 9], "mid": [10, 19], "late": [20, None]},
        },
        "totals": _finalize_bucket(total),
        "phases": {name: _finalize_bucket(phases[name]) for name in PHASES},
    }


def profile_files(
    replay_path: Path,
    pack_path: Path,
    identity_manifest_path: Path,
    *,
    submission_id: int,
    seat: int,
) -> dict[str, Any]:
    replay, replay_raw = _load_json_object(replay_path)
    pack, pack_raw = _load_json_object(pack_path)
    identity, identity_raw = _load_json_object(identity_manifest_path)
    return build_profile(
        replay,
        replay_raw,
        pack,
        pack_raw,
        identity,
        identity_raw,
        submission_id=submission_id,
        seat=seat,
    )


def canonical_json(profile: Mapping[str, Any]) -> str:
    return json.dumps(profile, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--identity-manifest", type=Path, required=True)
    parser.add_argument("--submission-id", type=int, required=True)
    parser.add_argument("--seat", type=int, required=True)
    parser.add_argument(
        "--pack",
        type=Path,
        default=Path(__file__).resolve().with_name(PACK_MANIFEST),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    profile = profile_files(
        args.replay,
        args.pack,
        args.identity_manifest,
        submission_id=args.submission_id,
        seat=args.seat,
    )
    payload = canonical_json(profile)
    if args.output is None:
        print(payload, end="")
    else:
        args.output.write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
