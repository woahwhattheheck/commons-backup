#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import pathlib
import sys
from typing import Any, Iterable

from validate_arc3_trace import TraceError, load_jsonl, validate


def ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def mean(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        return 0.0
    return round(sum(values) / len(values), 6)


def action_type(action: Any) -> str:
    if isinstance(action, dict):
        value = action.get("type")
        if isinstance(value, str) and value:
            return value
    return "<unknown>"


def discover(inputs: list[pathlib.Path]) -> list[pathlib.Path]:
    paths: list[pathlib.Path] = []
    for item in inputs:
        if item.is_dir():
            paths.extend(sorted(p for p in item.glob("*.jsonl") if p.is_file()))
        else:
            paths.append(item)

    unique: list[pathlib.Path] = []
    seen: set[pathlib.Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)

    if not unique:
        raise TraceError("no .jsonl traces found")
    return unique


def profile_trace(path: pathlib.Path) -> dict[str, Any]:
    records = load_jsonl(path)
    summary = validate(records)
    meta = records[0]
    steps = records[1:]
    max_actions = meta["max_actions"]
    max_wall_ms = meta["max_wall_ms"]
    actions = summary["actions"]
    wall_ms = summary["wall_ms"]
    no_progress = sum(step["state"] == step["next_state"] for step in steps)
    types = Counter(action_type(step["action"]) for step in steps)

    return {
        "path": str(path),
        "episode_id": summary["episode_id"],
        "failure_class": summary["failure_class"],
        "success": summary["failure_class"] == "none",
        "actions": actions,
        "max_actions": max_actions,
        "action_utilization": ratio(actions, max_actions),
        "action_headroom": max_actions - actions,
        "wall_ms": wall_ms,
        "max_wall_ms": max_wall_ms,
        "wall_utilization": ratio(wall_ms, max_wall_ms),
        "wall_headroom_ms": max_wall_ms - wall_ms,
        "no_progress_actions": no_progress,
        "no_progress_rate": ratio(no_progress, actions),
        "action_types": dict(sorted(types.items())),
        "trace_digest": summary["trace_digest"],
    }


def aggregate(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    failures = [episode for episode in episodes if not episode["success"]]
    total_actions = sum(episode["actions"] for episode in episodes)
    total_wall_ms = sum(episode["wall_ms"] for episode in episodes)
    failed_actions = sum(episode["actions"] for episode in failures)
    no_progress = sum(episode["no_progress_actions"] for episode in episodes)

    failure_classes = Counter(episode["failure_class"] for episode in episodes)
    action_types: Counter[str] = Counter()
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for episode in episodes:
        action_types.update(episode["action_types"])
        clusters[episode["failure_class"]].append(episode)

    cluster_summary: dict[str, Any] = {}
    for failure_class, members in sorted(clusters.items()):
        cluster_actions = sum(member["actions"] for member in members)
        cluster_no_progress = sum(member["no_progress_actions"] for member in members)
        cluster_summary[failure_class] = {
            "episodes": len(members),
            "actions": cluster_actions,
            "mean_actions": mean(float(member["actions"]) for member in members),
            "mean_action_utilization": mean(
                member["action_utilization"] for member in members
            ),
            "wall_ms": sum(member["wall_ms"] for member in members),
            "mean_wall_ms": mean(float(member["wall_ms"]) for member in members),
            "mean_wall_utilization": mean(
                member["wall_utilization"] for member in members
            ),
            "no_progress_actions": cluster_no_progress,
            "no_progress_rate": ratio(cluster_no_progress, cluster_actions),
        }

    return {
        "episodes": len(episodes),
        "successes": len(episodes) - len(failures),
        "failures": len(failures),
        "success_rate": ratio(len(episodes) - len(failures), len(episodes)),
        "actions": {
            "total": total_actions,
            "mean_per_episode": mean(
                float(episode["actions"]) for episode in episodes
            ),
            "failed_episode_share": ratio(failed_actions, total_actions),
            "near_budget_failures": sum(
                episode["action_utilization"] >= 0.8 for episode in failures
            ),
        },
        "wall_ms": {
            "total": total_wall_ms,
            "mean_per_episode": mean(
                float(episode["wall_ms"]) for episode in episodes
            ),
            "near_budget_failures": sum(
                episode["wall_utilization"] >= 0.8 for episode in failures
            ),
        },
        "no_progress": {
            "actions": no_progress,
            "share": ratio(no_progress, total_actions),
        },
        "failure_classes": dict(sorted(failure_classes.items())),
        "action_types": dict(sorted(action_types.items())),
        "clusters": cluster_summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Profile validated ARC-AGI-3 episode traces for failure clusters "
            "and budget waste."
        )
    )
    parser.add_argument("inputs", nargs="+", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()

    try:
        paths = discover(args.inputs)
        episodes = [profile_trace(path) for path in paths]
    except (OSError, TraceError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2

    report = {
        "schema": "tj-arc3-profile/v1",
        "aggregate": aggregate(episodes),
        "episodes": episodes,
    }
    rendered = json.dumps(report, sort_keys=True, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
