#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reduce private reachable-probe JSONL to non-observational counts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _is_plain_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _eligible_feed(unit):
    tile = unit.get("tile")
    inventory = unit.get("inventory")
    return (
        isinstance(tile, dict)
        and isinstance(inventory, dict)
        and isinstance(unit.get("action"), list)
        and unit["action"][:1] == ["FEED"]
        and bool(tile.get("animal"))
        and tile.get("fed_today") is False
        and tile.get("cared_today") is False
        and tile.get("consecutive_unfed") == 0
        and tile.get("pending_care_bonus") == 0
        and _is_plain_int(inventory.get("WHEAT"))
        and inventory["WHEAT"] >= 1
    )


def summarize(paths, *, turns_per_day):
    if not _is_plain_int(turns_per_day) or turns_per_day <= 0:
        raise ValueError("turns_per_day must be a positive plain integer")

    paths = [Path(path) for path in paths]
    events = []
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
                if event.get("schema") != "titan-v5/animal-cadence/reachable-probe/v1":
                    raise ValueError(f"{path}:{line_number}: unexpected schema")
                if not _is_plain_int(event.get("step")) or event["step"] < 0:
                    raise ValueError(f"{path}:{line_number}: invalid step")
                if not _is_plain_int(event.get("player")) or event["player"] < 0:
                    raise ValueError(f"{path}:{line_number}: invalid player")
                events.append(event)

    cares = []
    eligible = []
    feed_actions = 0
    care_actions = 0
    for event in events:
        for unit in event.get("relevant", []):
            action = unit.get("action")
            position = unit.get("position")
            if not isinstance(action, list) or not isinstance(position, list):
                continue
            key = (event["player"], tuple(position))
            if action[:1] == ["FEED"]:
                feed_actions += 1
                if _eligible_feed(unit):
                    eligible.append((event["step"], key))
            elif action[:1] == ["CARE"]:
                care_actions += 1
                cares.append((event["step"], key))

    care_dependent = 0
    first_followups = []
    for step, key in eligible:
        day = step // turns_per_day
        later = sorted(
            care_step for care_step, care_key in cares
            if care_key == key
            and care_step > step
            and care_step // turns_per_day == day
        )
        if later:
            care_dependent += 1
            first_followups.append({"feed_step": step, "care_step": later[0]})

    completed = sum(event.get("runtime_status") == "completed" for event in events)
    single_parent = sum(event.get("parent_calls") == 1 for event in events)
    return {
        "schema": "titan-v5/animal-cadence/reachable-summary/v1",
        "turns_per_day": turns_per_day,
        "files": len(paths),
        "events": len(events),
        "completed_events": completed,
        "single_parent_events": single_parent,
        "players": sorted({event.get("player") for event in events}),
        "routes": sorted({
            event.get("route_id") for event in events
            if isinstance(event.get("route_id"), str)
        }),
        "feed_actions": feed_actions,
        "care_actions": care_actions,
        "candidate_guard_feeds": len(eligible),
        "care_dependent_guard_feeds": care_dependent,
        "care_neutral_guard_feeds": len(eligible) - care_dependent,
        "first_followups": sorted(first_followups, key=lambda row: (row["feed_step"], row["care_step"])),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--turns-per-day", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(
        summarize(args.paths, turns_per_day=args.turns_per_day),
        indent=2,
        sort_keys=True,
    ))


if __name__ == "__main__":
    main()
