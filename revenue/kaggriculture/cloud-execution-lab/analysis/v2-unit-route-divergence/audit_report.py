#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Observed-effect, actor-binding, and cross-replay report construction."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from audit_common import (
    AuditError,
    MOVES,
    Replay,
    SCHEMA_VERSION,
    _economic_state,
    _hire_count,
    _load_manifest,
    _load_replay,
    _physical_state,
    _unit_action,
    _strict_int,
    canonical_json,
    digest,
    sha256_bytes,
)

def _inventory_total(inventory: Mapping[str, int] | None) -> int:
    return 0 if inventory is None else sum(int(value) for value in inventory.values())


def _actor_effects(replay: Replay, step: int) -> list[dict[str, Any]]:
    """Return direct observed effects for row-step action on row-step-1 state."""
    previous = replay.observation(step - 1)
    current = replay.observation(step)
    pre_farm = replay.own_farm(step - 1)
    out_farm = replay.own_farm(step)
    pre_private = replay.private(step - 1)
    out_private = replay.private(step)
    actions = [replay.action(step)["farmer"], *replay.action(step)["hands"]]
    pre_positions = [pre_farm["farmer"], *pre_farm["hands"]]
    out_positions = [out_farm["farmer"], *out_farm["hands"]]
    pre_inventories = pre_private["inventories"]
    out_inventories = out_private["inventories"]
    day_changed = previous["day"] != current["day"]
    effects: list[dict[str, Any]] = []
    for actor, action in enumerate(actions):
        bound = actor < len(pre_positions)
        survives = actor < len(out_positions)
        effect: str | None = None
        before_pos = pre_positions[actor] if bound else None
        after_pos = out_positions[actor] if survives else None
        before_inventory = pre_inventories[actor] if actor < len(pre_inventories) else None
        after_inventory = out_inventories[actor] if actor < len(out_inventories) else None
        op = action[0]
        if bound and survives and not day_changed:
            if op in MOVES:
                expected = MOVES[op]
                observed = (
                    after_pos[0] - before_pos[0],
                    after_pos[1] - before_pos[1],
                )
                effect = "executed" if observed == expected else (
                    "blocked" if observed == (0, 0) else "other"
                )
            elif op == "PICKUP" and len(action) > 1:
                item = action[1]
                before = int((before_inventory or {}).get(item, 0))
                after = int((after_inventory or {}).get(item, 0))
                effect = "executed" if after > before else "no_observed_inventory_gain"
            elif op == "COLLECT_FERTILIZER":
                before = int((before_inventory or {}).get("FERTILIZER", 0))
                after = int((after_inventory or {}).get("FERTILIZER", 0))
                effect = "executed" if after > before else "no_observed_inventory_gain"
            elif op == "HARVEST":
                effect = (
                    "executed" if _inventory_total(after_inventory) > _inventory_total(before_inventory)
                    else "no_observed_inventory_gain"
                )
            elif op in ("DROP", "PLACE"):
                effect = (
                    "executed" if _inventory_total(after_inventory) < _inventory_total(before_inventory)
                    else "no_observed_inventory_reduction"
                )
        effects.append({
            "actor": actor,
            "operation": op,
            "bound_to_input_actor": bound,
            "survives_output": survives,
            "observed_effect": effect,
        })
    return effects


def _contiguous_intervals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    intervals: list[dict[str, Any]] = []
    group = [rows[0]]
    for row in rows[1:]:
        previous = group[-1]
        if (
            row["step"] == previous["step"] + 1
            and row["surplus"] == previous["surplus"]
            and row["day"] == previous["day"]
        ):
            group.append(row)
        else:
            intervals.append(_interval(group))
            group = [row]
    intervals.append(_interval(group))
    return intervals


def _interval(group: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    first, last = group[0], group[-1]
    return {
        "start_step": first["step"],
        "end_step": last["step"],
        "frames": len(group),
        "day": first["day"],
        "surplus_per_frame": first["surplus"],
        "unbound_commands": sum(int(row["surplus"]) for row in group),
        "input_hands": first["input_hands"],
        "planned_hand_commands": first["planned_hand_commands"],
    }


def _hire_events(replay: Replay) -> list[dict[str, Any]]:
    events = []
    for step in range(1, replay.episode_steps):
        requested = _hire_count(replay, step)
        if not requested:
            continue
        previous = replay.observation(step - 1)
        current = replay.observation(step)
        before = len(replay.own_farm(step - 1)["hands"])
        after = len(replay.own_farm(step)["hands"])
        if previous["day"] == current["day"]:
            completed = max(0, after - before)
        else:
            # Day-boundary execution order is not needed by the current corpus;
            # preserve the row without making a completion assertion.
            completed = None
        events.append({
            "step": step,
            "day": current["day"],
            "hour": current["hour"],
            "requested_executable_hires": requested,
            "completed_hires": completed,
            "shortfall": None if completed is None else requested - completed,
            "input_hands": before,
            "output_hands": after,
            "input_money": replay.own_farm(step - 1)["money"],
            "output_money": replay.own_farm(step)["money"],
            "market_length": len(replay.action(step)["market"]),
            "market_prefix_sha256": digest(
                replay.action(step)["market"][: replay.max_market_orders]
            ),
        })
    return events


def _episode_report(replay: Replay) -> dict[str, Any]:
    actions = [replay.action(step) for step in range(replay.episode_steps)]
    surplus_rows = []
    effect_counts: dict[str, int] = {}
    for step in range(1, replay.episode_steps):
        input_hands = len(replay.own_farm(step - 1)["hands"])
        planned = len(replay.action(step)["hands"])
        surplus = max(0, planned - input_hands)
        if surplus:
            obs = replay.observation(step - 1)
            surplus_rows.append({
                "step": step,
                "day": obs["day"],
                "hour": obs["hour"],
                "surplus": surplus,
                "input_hands": input_hands,
                "planned_hand_commands": planned,
            })
        for effect in _actor_effects(replay, step):
            if effect["observed_effect"] is None:
                continue
            key = f"{effect['operation']}:{effect['observed_effect']}"
            effect_counts[key] = effect_counts.get(key, 0) + 1
    hire_events = _hire_events(replay)
    shortfalls = [event for event in hire_events if (event["shortfall"] or 0) > 0]
    intervals = _contiguous_intervals(surplus_rows)
    for interval in intervals:
        candidates = [
            event for event in hire_events
            if event["day"] == interval["day"] and event["step"] < interval["start_step"]
        ]
        source = candidates[-1] if candidates else None
        interval["preceding_hire_step"] = None if source is None else source["step"]
        interval["preceding_hire_shortfall"] = None if source is None else source["shortfall"]
        interval["attribution"] = (
            "underfilled_hire" if source is not None and (source["shortfall"] or 0) > 0
            else "no_observed_hire_fill_shortfall"
        )
    return {
        "episode_id": replay.episode_id,
        "seed": replay.seed,
        "seat": replay.seat,
        "opponent": replay.opponent,
        "source_file": replay.declared_name,
        "source_bytes": replay.path.stat().st_size,
        "gzip_sha256": replay.raw_sha256,
        "inflated_json_sha256": replay.json_sha256,
        "episode_steps": replay.episode_steps,
        "reward": replay.reward,
        "rival_reward": replay.rival_reward,
        "margin": replay.reward - replay.rival_reward,
        "result": "WIN" if replay.reward > replay.rival_reward else (
            "LOSS" if replay.reward < replay.rival_reward else "TIE"
        ),
        "action_hashes": {
            "full": digest(actions),
            "farmer": digest([action["farmer"] for action in actions]),
            "hands": digest([action["hands"] for action in actions]),
            "unit": digest([_unit_action(action) for action in actions]),
            "market": digest([action["market"] for action in actions]),
        },
        "physical_state_stream_sha256": digest([
            _physical_state(replay, step) for step in range(replay.episode_steps)
        ]),
        "hire_event_count": len(hire_events),
        "hire_event_stream_sha256": digest(hire_events),
        "hire_shortfalls": shortfalls,
        "unbound_hand_command_intervals": intervals,
        "unbound_hand_commands_total": sum(row["surplus"] for row in surplus_rows),
        "unbound_hand_command_frames": len(surplus_rows),
        "direct_observed_effect_counts": dict(sorted(effect_counts.items())),
    }


def _first_false(values: Sequence[bool]) -> int | None:
    return next((index for index, value in enumerate(values) if not value), None)


def _pair_report(left: Replay, right: Replay) -> dict[str, Any]:
    if left.episode_steps != right.episode_steps:
        raise AuditError("pair has inconsistent episode length")
    frames = left.episode_steps
    farmer_equal = []
    hands_equal = []
    unit_equal = []
    market_equal = []
    full_equal = []
    physical_equal = []
    economic_equal = []
    same_unit_different_input = []
    same_unit_different_binding = []
    same_unit_different_effect = []
    effect_witnesses = []
    for step in range(frames):
        a, b = left.action(step), right.action(step)
        farmer_equal.append(a["farmer"] == b["farmer"])
        hands_equal.append(a["hands"] == b["hands"])
        unit_equal.append(_unit_action(a) == _unit_action(b))
        market_equal.append(a["market"] == b["market"])
        full_equal.append(a == b)
        physical_equal.append(_physical_state(left, step) == _physical_state(right, step))
        economic_equal.append(_economic_state(left, step) == _economic_state(right, step))
        if step == 0 or not unit_equal[step]:
            continue
        input_equal = physical_equal[step - 1]
        if not input_equal:
            same_unit_different_input.append(step)
        left_hands = len(left.own_farm(step - 1)["hands"])
        right_hands = len(right.own_farm(step - 1)["hands"])
        planned = len(a["hands"])
        left_surplus = max(0, planned - left_hands)
        right_surplus = max(0, planned - right_hands)
        if left_surplus != right_surplus:
            same_unit_different_binding.append(step)
        left_effect = [
            (row["operation"], row["bound_to_input_actor"], row["observed_effect"])
            for row in _actor_effects(left, step)
        ]
        right_effect = [
            (row["operation"], row["bound_to_input_actor"], row["observed_effect"])
            for row in _actor_effects(right, step)
        ]
        if left_effect != right_effect:
            same_unit_different_effect.append(step)
            if len(effect_witnesses) < 20:
                effect_witnesses.append({
                    "step": step,
                    "left": left_effect,
                    "right": right_effect,
                })
    return {
        "left_episode_id": left.episode_id,
        "right_episode_id": right.episode_id,
        "left_opponent": left.opponent,
        "right_opponent": right.opponent,
        "frames": frames,
        "equal_frames": {
            "farmer": sum(farmer_equal),
            "hands": sum(hands_equal),
            "unit": sum(unit_equal),
            "market": sum(market_equal),
            "full": sum(full_equal),
            "physical_state": sum(physical_equal),
            "economic_state": sum(economic_equal),
        },
        "first_divergence": {
            "farmer": _first_false(farmer_equal),
            "hands": _first_false(hands_equal),
            "unit": _first_false(unit_equal),
            "market": _first_false(market_equal),
            "full": _first_false(full_equal),
            "physical_state": _first_false(physical_equal),
            "economic_state": _first_false(economic_equal),
        },
        "same_unit_action_on_different_physical_input_frames": len(
            same_unit_different_input
        ),
        "first_same_unit_action_on_different_physical_input": (
            same_unit_different_input[0] if same_unit_different_input else None
        ),
        "same_unit_action_different_actor_binding_frames": len(
            same_unit_different_binding
        ),
        "actor_binding_steps": same_unit_different_binding,
        "same_unit_action_different_observed_effect_frames": len(
            same_unit_different_effect
        ),
        "observed_effect_steps": same_unit_different_effect,
        "observed_effect_witnesses": effect_witnesses[:3],
    }


def build_report(manifest_path: Path, replay_dir: Path | None = None) -> dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    directory = replay_dir or manifest_path.parent
    agent = manifest["agent_name"]
    expected_steps = _strict_int(
        manifest["expected_episode_steps"], "manifest.expected_episode_steps", minimum=2
    )
    replays = [
        _load_replay(row, agent_name=agent, expected_steps=expected_steps, replay_dir=directory)
        for row in manifest["replays"]
    ]
    episode_ids = [replay.episode_id for replay in replays]
    raw_hashes = [replay.raw_sha256 for replay in replays]
    # Reject copied inputs before identity labels.  Identical replay bytes also
    # necessarily carry an identical episode ID, so checking the content first
    # makes the stronger anti-cherry-pick failure observable and testable.
    if len(set(raw_hashes)) != len(raw_hashes):
        raise AuditError("duplicate replay bytes in manifest")
    if len(set(episode_ids)) != len(episode_ids):
        raise AuditError("duplicate episode_id in manifest")
    replays.sort(key=lambda replay: replay.episode_id)
    episodes = [_episode_report(replay) for replay in replays]
    pairs = [
        _pair_report(replays[left], replays[right])
        for left in range(len(replays))
        for right in range(left + 1, len(replays))
    ]
    hands_groups: dict[str, list[int]] = {}
    unit_groups: dict[str, list[int]] = {}
    for episode in episodes:
        hands_groups.setdefault(episode["action_hashes"]["hands"], []).append(
            episode["episode_id"]
        )
        unit_groups.setdefault(episode["action_hashes"]["unit"], []).append(
            episode["episode_id"]
        )
    report = {
        "schema_version": SCHEMA_VERSION,
        "tool": "unit_route_audit.py",
        "agent_name": agent,
        "manifest_sha256": sha256_bytes(canonical_json(manifest)),
        "expected_episode_steps": expected_steps,
        "replay_count": len(replays),
        "episodes": episodes,
        "pairwise": pairs,
        "summary": {
            "wins": sum(episode["result"] == "WIN" for episode in episodes),
            "losses": sum(episode["result"] == "LOSS" for episode in episodes),
            "ties": sum(episode["result"] == "TIE" for episode in episodes),
            "underfilled_hire_events": sum(
                len(episode["hire_shortfalls"]) for episode in episodes
            ),
            "episodes_with_underfilled_hires": [
                episode["episode_id"] for episode in episodes if episode["hire_shortfalls"]
            ],
            "unbound_hand_commands_total": sum(
                episode["unbound_hand_commands_total"] for episode in episodes
            ),
            "hands_action_hash_groups": [
                {"sha256": key, "episode_ids": value}
                for key, value in sorted(hands_groups.items())
            ],
            "unit_action_hash_groups": [
                {"sha256": key, "episode_ids": value}
                for key, value in sorted(unit_groups.items())
            ],
            "truth_boundary": (
                "Observed submitted-replay transitions only: no environment execution, "
                "counterfactual score, causal strength, or promotion claim."
            ),
        },
    }
    report["report_payload_sha256"] = sha256_bytes(canonical_json(report))
    return report

