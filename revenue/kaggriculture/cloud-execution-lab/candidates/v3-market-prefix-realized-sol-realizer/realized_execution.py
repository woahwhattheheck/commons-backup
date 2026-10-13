# SPDX-License-Identifier: Apache-2.0
"""Fail-closed action-to-state attribution for market-prefix rescue panels."""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from typing import Any, Iterable

SCHEMA = "titan-market-prefix-realized-execution/v1"
RECEIPT_KEYS = {
    "step",
    "pre_world_sha256",
    "tested_action_sha256",
    "opponent_action_sha256",
    "post_world_sha256",
    "syntactic_event",
    "diagnostic_sha256",
}


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite value in world projection")
        return value
    raise TypeError(f"unsupported world value: {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        _plain(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def world_projection(state: Iterable[Any], env: Any) -> dict[str, Any]:
    """Project engine state while deliberately excluding submitted actions.

    Including ``state.action`` would make every syntactic edit look like a state
    transition.  Only observations, status, reward, and terminality are retained.
    """

    players = []
    for item in state:
        players.append(
            {
                "status": str(item.status),
                "reward": _plain(item.reward),
                "observation": _plain(item.observation),
            }
        )
    return {"env_done": bool(env.done), "players": players}


def world_digest(state: Iterable[Any], env: Any) -> str:
    return digest(world_projection(state, env))


def action_digest(action: Any) -> str:
    return digest(action)


def _require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{label} must be a SHA-256 hex string")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{label} must be hexadecimal") from exc
    return value


def _validate_receipt(row: Any, expected_step: int, *, candidate: bool) -> dict[str, Any]:
    if not isinstance(row, dict) or set(row) != RECEIPT_KEYS:
        raise ValueError(f"step {expected_step}: malformed receipt keys")
    if type(row["step"]) is not int or row["step"] != expected_step:
        raise ValueError(f"step {expected_step}: non-canonical step")
    for key in (
        "pre_world_sha256",
        "tested_action_sha256",
        "opponent_action_sha256",
        "post_world_sha256",
    ):
        _require_sha(row[key], f"step {expected_step} {key}")
    if type(row["syntactic_event"]) is not bool:
        raise ValueError(f"step {expected_step}: syntactic_event must be bool")
    diagnostic = row["diagnostic_sha256"]
    if row["syntactic_event"]:
        _require_sha(diagnostic, f"step {expected_step} diagnostic_sha256")
        if not candidate:
            raise ValueError(f"step {expected_step}: control emitted candidate diagnostic")
    elif diagnostic is not None:
        raise ValueError(f"step {expected_step}: diagnostic hash without event")
    return row


def _score(game: dict[str, Any], seat: int) -> tuple[float, float]:
    scores = game.get("scores")
    if not isinstance(scores, list) or len(scores) != 2:
        raise ValueError("game must contain two scores")
    values = []
    for value in scores:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("game score must be finite numeric and non-boolean")
        values.append(float(value))
    return values[seat], values[1 - seat]


def compare_game_pair(control: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Attribute only equal-prestate, equal-rival action changes to the candidate."""

    identity = ("opponent", "seed", "candidate_seat")
    for key in identity:
        if control.get(key) != candidate.get(key):
            raise ValueError(f"pair identity mismatch for {key}")
    seat = candidate.get("candidate_seat")
    if type(seat) is not int or seat not in (0, 1):
        raise ValueError("candidate_seat must be literal integer 0 or 1")
    for label, game in (("control", control), ("candidate", candidate)):
        if game.get("status") != "complete":
            raise ValueError(f"{label} game is not complete")
        if type(game.get("episode_steps")) is not int or game["episode_steps"] < 2:
            raise ValueError(f"{label} game has invalid episode_steps")
        if type(game.get("steps")) is not int:
            raise ValueError(f"{label} game has invalid steps")
    if control["episode_steps"] != candidate["episode_steps"]:
        raise ValueError("episode configuration mismatch")
    expected_actions = candidate["episode_steps"] - 1
    if control["steps"] != expected_actions or candidate["steps"] != expected_actions:
        raise ValueError("game does not have exact official action lifecycle")

    control_rows = control.get("step_receipts")
    candidate_rows = candidate.get("step_receipts")
    if not isinstance(control_rows, list) or not isinstance(candidate_rows, list):
        raise ValueError("missing step receipts")
    if len(control_rows) != expected_actions or len(candidate_rows) != expected_actions:
        raise ValueError("step receipt cardinality mismatch")

    causal_window_open = True
    syntactic_events = 0
    causal_events = 0
    realized_events = 0
    inert_events = 0
    downstream_events = 0
    action_divergences = 0
    state_divergences = 0
    first_action_divergence = None
    first_realized = None
    details = []

    for step, (raw_control, raw_candidate) in enumerate(zip(control_rows, candidate_rows)):
        c0 = _validate_receipt(raw_control, step, candidate=False)
        c1 = _validate_receipt(raw_candidate, step, candidate=True)
        same_pre = c0["pre_world_sha256"] == c1["pre_world_sha256"]
        same_rival = c0["opponent_action_sha256"] == c1["opponent_action_sha256"]
        action_changed = c0["tested_action_sha256"] != c1["tested_action_sha256"]
        post_changed = c0["post_world_sha256"] != c1["post_world_sha256"]
        event = c1["syntactic_event"]

        syntactic_events += int(event)
        action_divergences += int(action_changed)
        state_divergences += int(post_changed)
        if action_changed and first_action_divergence is None:
            first_action_divergence = step

        if causal_window_open:
            if not same_pre:
                raise ValueError(f"step {step}: worlds diverged before a realized candidate event")
            if not same_rival:
                raise ValueError(f"step {step}: rival action diverged in equal pre-state")
            if action_changed and not event:
                raise ValueError(f"step {step}: unattributed candidate action divergence")
            if event and not action_changed:
                raise ValueError(f"step {step}: diagnostic event without candidate action divergence")
            if not action_changed and post_changed:
                raise ValueError(f"step {step}: engine state diverged under identical actions")
            if event:
                causal_events += 1
                if post_changed:
                    realized_events += 1
                    first_realized = step if first_realized is None else first_realized
                    causal_window_open = False
                    classification = "realized"
                else:
                    inert_events += 1
                    classification = "inert"
                details.append({"step": step, "classification": classification})
        else:
            if event:
                downstream_events += 1

    control_own, control_rival = _score(control, seat)
    candidate_own, candidate_rival = _score(candidate, seat)
    if syntactic_events == 0:
        if action_divergences or state_divergences or control.get("scores") != candidate.get("scores"):
            raise ValueError("zero-event candidate diverged from control")
    if realized_events == 0 and control.get("scores") != candidate.get("scores"):
        raise ValueError("score changed without a causally realized candidate event")

    return {
        "schema": SCHEMA,
        "opponent": candidate["opponent"],
        "seed": candidate["seed"],
        "candidate_seat": seat,
        "syntactic_events": syntactic_events,
        "causal_events": causal_events,
        "realized_events": realized_events,
        "inert_events": inert_events,
        "downstream_events": downstream_events,
        "action_divergence_steps": action_divergences,
        "state_divergence_steps": state_divergences,
        "first_action_divergence_step": first_action_divergence,
        "first_realized_step": first_realized,
        "causal_event_details": details,
        "control_scores": control["scores"],
        "candidate_scores": candidate["scores"],
        "own_delta": candidate_own - control_own,
        "rival_delta": candidate_rival - control_rival,
        "margin_delta": (candidate_own - candidate_rival) - (control_own - control_rival),
    }


def summarize_pairs(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    if not pairs:
        raise ValueError("no paired games")
    keys = set()
    for row in pairs:
        key = (row["opponent"], row["seed"], row["candidate_seat"])
        if key in keys:
            raise ValueError(f"duplicate pair {key}")
        keys.add(key)

    own = [float(row["own_delta"]) for row in pairs]
    rival = [float(row["rival_delta"]) for row in pairs]
    margin = [float(row["margin_delta"]) for row in pairs]
    realized_pairs = [row for row in pairs if row["realized_events"] > 0]
    syntactic_pairs = [row for row in pairs if row["syntactic_events"] > 0]

    strata: dict[str, dict[str, Any]] = {}
    for opponent in sorted({row["opponent"] for row in pairs}):
        for seat in (0, 1):
            rows = [
                row
                for row in pairs
                if row["opponent"] == opponent and row["candidate_seat"] == seat
            ]
            if not rows:
                raise ValueError(f"missing opponent-seat stratum {opponent}/{seat}")
            values = [float(row["own_delta"]) for row in rows]
            strata[f"{opponent}/seat{seat}"] = {
                "cells": len(rows),
                "mean_own_delta": statistics.mean(values),
                "minimum_own_delta": min(values),
                "realized_cells": sum(row["realized_events"] > 0 for row in rows),
            }

    if not syntactic_pairs:
        verdict = "NO_SYNTACTIC_SIGNAL"
        reasons = ["candidate never moved a structural tail order across the cap"]
    elif not realized_pairs:
        verdict = "NO_REALIZED_SIGNAL"
        reasons = ["all structural crossings were inert under the pinned interpreter"]
    else:
        reasons = []
        if statistics.mean(own) <= 0:
            reasons.append("global mean own cash is not positive")
        if statistics.median(own) < 0:
            reasons.append("global median own cash is negative")
        if statistics.mean(margin) <= 0:
            reasons.append("global mean margin is not positive")
        if sum(value > 0 for value in own) < sum(value < 0 for value in own):
            reasons.append("negative own-cash cells outnumber positive cells")
        losing_strata = [
            key for key, value in strata.items() if value["mean_own_delta"] < 0
        ]
        if losing_strata:
            reasons.append("losing opponent-seat strata: " + ", ".join(losing_strata))
        if not reasons:
            verdict = "REALIZED_UPSIDE_SCREEN"
        elif statistics.mean(own) < 0 or losing_strata:
            verdict = "REALIZED_REGRESSION"
        else:
            verdict = "REALIZED_MIXED"

    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "reasons": reasons,
        "paired_cells": len(pairs),
        "syntactic_activation_cells": len(syntactic_pairs),
        "syntactic_events": sum(row["syntactic_events"] for row in pairs),
        "causal_events": sum(row["causal_events"] for row in pairs),
        "realized_execution_cells": len(realized_pairs),
        "realized_events": sum(row["realized_events"] for row in pairs),
        "inert_events": sum(row["inert_events"] for row in pairs),
        "downstream_events": sum(row["downstream_events"] for row in pairs),
        "mean_own_delta": statistics.mean(own),
        "median_own_delta": statistics.median(own),
        "mean_rival_delta": statistics.mean(rival),
        "mean_margin_delta": statistics.mean(margin),
        "positive_zero_negative_own": [
            sum(value > 0 for value in own),
            sum(value == 0 for value in own),
            sum(value < 0 for value in own),
        ],
        "realized_mean_own_delta": (
            statistics.mean(float(row["own_delta"]) for row in realized_pairs)
            if realized_pairs
            else None
        ),
        "realized_mean_margin_delta": (
            statistics.mean(float(row["margin_delta"]) for row in realized_pairs)
            if realized_pairs
            else None
        ),
        "opponent_seat_strata": strata,
        "pairs": pairs,
    }
