#!/usr/bin/env python3
"""Bind one raw Kaggriculture replay to an immutable action-trace manifest.

Research/custody tooling only. The binder does not execute candidate code or the
Kaggriculture engine. It verifies source identity, episode identity, recorded
seat identity when requested, and the replay convention where states[i].action
is the action applied to the preceding observation at states[i-1].
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

SCHEMA = "titan.v4.raw-replay-binding.v1"


class BindError(ValueError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    _validate_json_numbers(value)
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise BindError(f"value is not canonical JSON: {exc}") from exc


def _validate_json_numbers(value: Any, path: str = "$") -> None:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise BindError(f"non-finite number at {path}")
    elif isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise BindError(f"non-string object key at {path}")
            _validate_json_numbers(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_json_numbers(child, f"{path}[{index}]")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strict_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise BindError(f"{field} must be an integer, not boolean")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        signless = text[1:] if text[:1] in "+-" else text
        if text and signless.isdigit():
            return int(text, 10)
    raise BindError(f"{field} must be an integer")


def _normalize_scalar(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise BindError("identity scalar must not be boolean")
    if isinstance(value, (int, str)):
        text = str(value).strip()
        return text or None
    raise BindError("identity scalar must be integer/string when present")


def _list_value(info: dict[str, Any], key: str, seat: int) -> Any:
    value = info.get(key)
    if value is None:
        return None
    if not isinstance(value, list):
        raise BindError(f"info.{key} must be an array when present")
    if seat >= len(value):
        raise BindError(f"info.{key} has no entry for seat {seat}")
    return value[seat]


def _identity(info: dict[str, Any], seat: int) -> dict[str, Any]:
    top_team = _normalize_scalar(_list_value(info, "TeamNames", seat))
    top_submission = _normalize_scalar(_list_value(info, "SubmissionIds", seat))

    agent_team = None
    agent_submission = None
    agents = info.get("Agents")
    if agents is not None:
        if not isinstance(agents, list) or seat >= len(agents):
            raise BindError(f"info.Agents has no entry for seat {seat}")
        agent = agents[seat]
        if not isinstance(agent, dict):
            raise BindError(f"info.Agents[{seat}] must be an object")
        for key in ("Name", "TeamName"):
            if key in agent and agent[key] is not None:
                candidate = _normalize_scalar(agent[key])
                if agent_team is not None and candidate != agent_team:
                    raise BindError(f"conflicting team identity inside info.Agents[{seat}]")
                agent_team = candidate
        for key in ("SubmissionId", "SubmissionID"):
            if key in agent and agent[key] is not None:
                candidate = _normalize_scalar(agent[key])
                if agent_submission is not None and candidate != agent_submission:
                    raise BindError(f"conflicting submission identity inside info.Agents[{seat}]")
                agent_submission = candidate

    if top_team is not None and agent_team is not None and top_team != agent_team:
        raise BindError(f"team identity disagrees across replay metadata for seat {seat}")
    if top_submission is not None and agent_submission is not None and top_submission != agent_submission:
        raise BindError(f"submission identity disagrees across replay metadata for seat {seat}")
    return {
        "team": top_team if top_team is not None else agent_team,
        "submission_id": top_submission if top_submission is not None else agent_submission,
    }


def _step_from_state(state: Any, *, index: int, seat: int) -> int:
    if not isinstance(state, dict):
        raise BindError(f"steps[{index}][{seat}] must be an object")
    obs = state.get("observation")
    if not isinstance(obs, dict):
        raise BindError(f"steps[{index}][{seat}].observation must be an object")
    if "step" not in obs:
        raise BindError(f"steps[{index}][{seat}].observation.step is required")
    step = _strict_int(obs["step"], f"steps[{index}][{seat}].observation.step")
    if step < 0:
        raise BindError("observation step must be nonnegative")
    return step


def bind_replay(
    raw_bytes: bytes,
    *,
    source_name: str,
    expected_episode: Any,
    recorded_seat: int,
    expected_team: str | None = None,
    expected_submission: Any | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(source_name, str) or not source_name:
        raise BindError("source_name must be a nonempty string")
    if type(recorded_seat) is not int or recorded_seat < 0:
        raise BindError("recorded_seat must be a nonnegative integer")
    try:
        replay = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BindError(f"replay is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(replay, dict):
        raise BindError("replay root must be an object")
    _validate_json_numbers(replay)

    info = replay.get("info")
    if not isinstance(info, dict):
        raise BindError("replay.info must be an object")
    if "EpisodeId" not in info:
        raise BindError("replay.info.EpisodeId is required")
    actual_episode = _normalize_scalar(info["EpisodeId"])
    wanted_episode = _normalize_scalar(expected_episode)
    if actual_episode != wanted_episode:
        raise BindError(f"episode mismatch: expected {wanted_episode!r}, got {actual_episode!r}")

    steps = replay.get("steps")
    if not isinstance(steps, list) or len(steps) < 2:
        raise BindError("replay.steps must contain at least two steps")
    if not isinstance(steps[0], list) or not steps[0]:
        raise BindError("replay.steps[0] must contain player states")
    player_count = len(steps[0])
    if recorded_seat >= player_count:
        raise BindError(f"recorded_seat {recorded_seat} outside player range 0..{player_count - 1}")
    for index, states in enumerate(steps):
        if not isinstance(states, list) or len(states) != player_count:
            raise BindError(f"steps[{index}] player count differs from initial step")
        if not all(isinstance(state, dict) for state in states):
            raise BindError(f"steps[{index}] contains non-object player state")

    seat_identity = _identity(info, recorded_seat)
    if expected_team is not None:
        if not isinstance(expected_team, str) or not expected_team.strip():
            raise BindError("expected_team must be nonempty when supplied")
        if seat_identity["team"] is None:
            raise BindError("expected team was supplied but replay has no team identity")
        if seat_identity["team"].casefold() != expected_team.strip().casefold():
            raise BindError(
                f"team mismatch: expected {expected_team.strip()!r}, got {seat_identity['team']!r}"
            )
    if expected_submission is not None:
        wanted_submission = _normalize_scalar(expected_submission)
        if seat_identity["submission_id"] is None:
            raise BindError("expected submission was supplied but replay has no submission identity")
        if seat_identity["submission_id"] != wanted_submission:
            raise BindError(
                f"submission mismatch: expected {wanted_submission!r}, got {seat_identity['submission_id']!r}"
            )

    trace: list[dict[str, Any]] = []
    seen_steps: set[int] = set()
    for index in range(1, len(steps)):
        source_step = _step_from_state(steps[index - 1][recorded_seat], index=index - 1, seat=recorded_seat)
        if source_step in seen_steps:
            raise BindError(f"duplicate recorded observation step {source_step}")
        seen_steps.add(source_step)
        state = steps[index][recorded_seat]
        if "action" not in state or not isinstance(state["action"], dict):
            raise BindError(f"steps[{index}][{recorded_seat}].action must be an object")
        action = state["action"]
        _canonical_bytes(action)
        trace.append({"step": source_step, "action": action})

    if not trace:
        raise BindError("replay yielded no recorded actions")
    if any(right["step"] <= left["step"] for left, right in zip(trace, trace[1:])):
        raise BindError("recorded observation steps must be strictly increasing")

    configuration = replay.get("configuration", {})
    if configuration is None:
        configuration = {}
    if not isinstance(configuration, dict):
        raise BindError("replay.configuration must be an object when present")
    config_bytes = _canonical_bytes(configuration)
    trace_bytes = _canonical_bytes(trace)

    terminal = []
    for seat, state in enumerate(steps[-1]):
        terminal.append(
            {
                "seat": seat,
                "status": _normalize_scalar(state.get("status")),
                "reward": state.get("reward"),
            }
        )
    _canonical_bytes(terminal)

    manifest = {
        "schema": SCHEMA,
        "episode_id": actual_episode,
        "recorded_seat": recorded_seat,
        "recorded_identity": seat_identity,
        "source": {
            "name": source_name,
            "bytes": len(raw_bytes),
            "sha256": _sha256_bytes(raw_bytes),
        },
        "configuration": {
            "sha256": _sha256_bytes(config_bytes),
            "value": configuration,
        },
        "trace": {
            "actions": len(trace),
            "first_step": trace[0]["step"],
            "last_step": trace[-1]["step"],
            "sha256": _sha256_bytes(trace_bytes),
            "mapping": "steps[i].action applied to steps[i-1][seat].observation.step",
        },
        "player_count": player_count,
        "recorded_steps": len(steps),
        "terminal": terminal,
        "limits": [
            "No candidate or engine code is executed.",
            "Action-trace binding is custody/provenance evidence, not a ladder-strength claim.",
            "Counterfactual replay remains open-loop after a candidate diverges from the recorded world.",
        ],
    }
    return manifest, trace


def _write_new(path: Path, payload: Any) -> None:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8") as fh:
        fh.write(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("replay", type=Path)
    parser.add_argument("--expected-episode", required=True)
    parser.add_argument("--recorded-seat", type=int, required=True)
    parser.add_argument("--expected-team")
    parser.add_argument("--expected-submission")
    parser.add_argument("--trace-output", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        raw = args.replay.read_bytes()
        manifest, trace = bind_replay(
            raw,
            source_name=args.replay.name,
            expected_episode=args.expected_episode,
            recorded_seat=args.recorded_seat,
            expected_team=args.expected_team,
            expected_submission=args.expected_submission,
        )
        if args.trace_output:
            _write_new(args.trace_output, trace)
        text = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as fh:
                fh.write(text)
        else:
            sys.stdout.write(text)
    except (BindError, OSError) as exc:
        print(f"bind_replay: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
