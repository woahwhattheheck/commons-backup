# SPDX-License-Identifier: Apache-2.0
"""Exact recorded-action replay and per-worker shed occupancy measurement."""
from __future__ import annotations

import copy
from collections import Counter, defaultdict
import hashlib
from typing import Any, Mapping

from unit_capacity_support import (
    Struct, decoded_frame_rows, encoded, load_engine, plain, structify,
)

def quantity_total(mapping: Mapping[str, Any]) -> int:
    return sum(int(value) for value in mapping.values())


def inventory_copy(private: Mapping[str, Any], index: int) -> dict[str, int]:
    inventories = private.get("inventories", [])
    if index >= len(inventories):
        return {}
    return {str(key): int(value) for key, value in inventories[index].items()}


def phase_metrics(pre_shed: int, events: list[dict[str, Any]], capacity: int) -> dict[str, Any]:
    if not events:
        raise ValueError("unit phase contains no interpreter calls")
    deltas = [event["shed_delta"] for event in events]
    end_shed = events[-1]["after_shed"]
    after_values = [event["after_shed"] for event in events]
    peak = max([pre_shed, *after_values])
    interior_peak = max(after_values)
    positive_then_negative = any(
        delta > 0 and any(later < 0 for later in deltas[index + 1 :])
        for index, delta in enumerate(deltas)
    )
    hidden_above_both = max(0, interior_peak - max(pre_shed, end_shed))
    drop_positions = [index for index, event in enumerate(events) if event["op"] == "DROP"]
    pickup_positions = [
        index for index, event in enumerate(events) if event["op"] == "PICKUP"
    ]
    return {
        "pre_shed": pre_shed,
        "peak_shed": peak,
        "interior_peak_shed": interior_peak,
        "end_unit_shed": end_shed,
        "hidden_peak_above_start_and_end": hidden_above_both,
        "positive_then_negative": positive_then_negative,
        "drop_then_pickup": any(
            pickup > drop for drop in drop_positions for pickup in pickup_positions
        ),
        "discarded_units": sum(event["discarded_units"] for event in events),
        "hit_capacity": peak >= capacity,
        "hidden_peak_hit_capacity": hidden_above_both > 0 and interior_peak >= capacity,
    }


def replay_stream(stream: Mapping[str, Any], members: Mapping[str, bytes]) -> dict[str, Any]:
    rows, _decoded = decoded_frame_rows(
        members[stream["frame_member"]], stream["frame_member"]
    )
    result = copy.deepcopy(stream["result"])
    steps = result.get("steps")
    if type(steps) is not int or steps <= 0 or len(rows) != steps + 1:
        raise ValueError(f"frame/result length mismatch: {stream['frame_member']}")
    seat = int(result["candidate_seat"])
    module_suffix = hashlib.sha1(stream["key"].encode("utf-8")).hexdigest()[:12]
    engine = load_engine(members, f"titan_capacity_engine_{module_suffix}")
    original_apply = engine._apply_unit_action
    context: dict[str, Any] = {"seat_by_private": {}, "events": defaultdict(list)}

    def instrumented_apply(
        farm: Any,
        private: Any,
        index: int,
        action: Any,
        board_size: int,
        day: int,
        turns_per_day: int,
        shed_capacity: int = 100,
    ) -> None:
        actor_seat = context["seat_by_private"].get(id(private))
        before_shed = quantity_total(private["shed"])
        before_inventory = inventory_copy(private, index)
        original_apply(
            farm,
            private,
            index,
            action,
            board_size,
            day,
            turns_per_day,
            shed_capacity,
        )
        after_shed = quantity_total(private["shed"])
        after_inventory = inventory_copy(private, index)
        op = action[0] if isinstance(action, list) and action else None
        removed = max(
            0,
            quantity_total(before_inventory) - quantity_total(after_inventory),
        )
        added = max(0, after_shed - before_shed)
        discarded = max(0, removed - added) if op == "DROP" else 0
        context["events"][actor_seat].append(
            {
                "unit_index": index,
                "action": plain(action),
                "op": op,
                "before_shed": before_shed,
                "after_shed": after_shed,
                "shed_delta": after_shed - before_shed,
                "discarded_units": discarded,
            }
        )

    engine._apply_unit_action = instrumented_apply
    configuration = structify(copy.deepcopy(rows[0]["configuration"]))
    configuration.seed = result["seed"]
    environment = Struct(configuration=configuration, done=False, info={})
    state = [
        Struct(observation=Struct(), action={}, status="ACTIVE", reward=0)
        for _ in range(2)
    ]
    engine.interpreter(state, environment)
    if encoded(state) != encoded(rows[0]["state"]):
        raise ValueError(f"initial state differs: {stream['frame_member']}")

    counters = Counter()
    occurrences: list[dict[str, Any]] = []
    action_hash = hashlib.sha256()
    capacity = int(configuration.shedCapacity)
    for step in range(len(rows) - 1):
        context["events"] = defaultdict(list)
        context["seat_by_private"] = {
            id(state[player].observation.private): player for player in range(2)
        }
        pre_shed = quantity_total(state[seat].observation.private["shed"])
        for player in range(2):
            state[player].observation.step = step
            state[player].observation.remainingOverageTime = 0
            state[player].action = structify(
                copy.deepcopy(rows[step + 1]["state"][player]["action"])
            )
        action_hash.update(encoded(rows[step + 1]["state"][seat]["action"]) + b"\n")
        engine.interpreter(state, environment)
        if encoded(state) != encoded(rows[step + 1]["state"]):
            raise ValueError(
                f"recorded interpreter state differs at step {step}: "
                f"{stream['frame_member']}"
            )
        events = context["events"][seat]
        metrics = phase_metrics(pre_shed, events, capacity)
        counters["phases"] += 1
        counters["unit_actions"] += len(events)
        counters["drop_actions"] += sum(event["op"] == "DROP" for event in events)
        counters["valid_drop_actions"] += sum(
            event["op"] == "DROP"
            and (event["shed_delta"] > 0 or event["discarded_units"] > 0)
            for event in events
        )
        counters["place_to_shed_actions"] += sum(
            event["op"] == "PLACE" and event["shed_delta"] > 0 for event in events
        )
        counters["pickup_reductions"] += sum(
            event["op"] == "PICKUP" and event["shed_delta"] < 0 for event in events
        )
        for key in (
            "positive_then_negative",
            "drop_then_pickup",
            "hit_capacity",
            "hidden_peak_hit_capacity",
        ):
            counters[key + "_phases"] += bool(metrics[key])
        counters["interior_peak_phases"] += (
            metrics["hidden_peak_above_start_and_end"] > 0
        )
        counters["discard_phases"] += metrics["discarded_units"] > 0
        counters["discarded_units"] += metrics["discarded_units"]
        counters["near_capacity_95_phases"] += metrics["peak_shed"] >= capacity - 5
        counters["max_shed_occupancy"] = max(
            counters["max_shed_occupancy"], metrics["peak_shed"]
        )
        counters["max_hidden_peak_units"] = max(
            counters["max_hidden_peak_units"],
            metrics["hidden_peak_above_start_and_end"],
        )
        if metrics["positive_then_negative"]:
            changes = [
                {
                    "unit_index": event["unit_index"],
                    "action": event["action"],
                    "before_shed": event["before_shed"],
                    "after_shed": event["after_shed"],
                    "shed_delta": event["shed_delta"],
                    "discarded_units": event["discarded_units"],
                }
                for event in events
                if event["shed_delta"] or event["discarded_units"]
            ]
            occurrences.append(
                {
                    "step": step,
                    **metrics,
                    "shed_changes": changes,
                }
            )

    return {
        "stream_key": stream["key"],
        "frame_member": stream["frame_member"],
        "result_member": stream["result_member"],
        "aliases": copy.deepcopy(stream["aliases"]),
        "seed": result["seed"],
        "candidate_seat": seat,
        "arms": sorted(
            {alias.get("arm") for alias in stream["aliases"] if alias.get("arm") is not None}
        ),
        "scores": result.get("scores"),
        "original_trace_sha256": result.get("trace_sha256"),
        "candidate_action_jsonl_sha256": action_hash.hexdigest(),
        "counters": dict(counters),
        "occurrences": occurrences,
    }
