# SPDX-License-Identifier: Apache-2.0
"""Action-bound evidence checks for the TITAN T01 current-carrier panel."""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from typing import Any, Callable, Mapping, Sequence

Compose = Callable[..., tuple[dict[str, Any], Mapping[str, Any]]]
_OUTCOME_RANK = {"L": 0, "T": 1, "W": 2}


def encoded(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite numeric")
    return float(value)


def _outcome(margin: float) -> str:
    return "W" if margin > 0 else "L" if margin < 0 else "T"


def _terminal_payload(game: Mapping[str, Any], label: str) -> dict[str, Any]:
    episode = game.get("episode_steps")
    steps = game.get("steps")
    terminal_step = game.get("terminal_step")
    if episode != 720 or steps != 719 or terminal_step != 718:
        raise ValueError(
            f"{label} lifecycle mismatch: episode={episode!r} actions={steps!r} terminal={terminal_step!r}"
        )
    required = (
        "terminal_candidate_observation",
        "terminal_configuration",
        "terminal_candidate_action",
        "terminal_opponent_action",
        "trace_sha256",
        "scores",
        "candidate_seat",
    )
    missing = [name for name in required if name not in game]
    if missing:
        raise ValueError(f"{label} missing terminal evidence: {', '.join(missing)}")
    if not isinstance(game["terminal_candidate_observation"], Mapping):
        raise ValueError(f"{label} terminal observation is not a mapping")
    if not isinstance(game["terminal_configuration"], Mapping):
        raise ValueError(f"{label} terminal configuration is not a mapping")
    if not isinstance(game["terminal_candidate_action"], dict):
        raise ValueError(f"{label} terminal candidate action is not an object")
    if not isinstance(game["terminal_opponent_action"], dict):
        raise ValueError(f"{label} terminal opponent action is not an object")
    scores = game["scores"]
    if not isinstance(scores, list) or len(scores) != 2:
        raise ValueError(f"{label} terminal scores are malformed")
    for index, score in enumerate(scores):
        _finite_number(score, f"{label}.scores[{index}]")
    seat = game["candidate_seat"]
    if seat not in (0, 1):
        raise ValueError(f"{label} candidate seat is invalid")
    return dict(game)


def audit_cell(
    baseline_game: Mapping[str, Any],
    candidate_game: Mapping[str, Any],
    *,
    compose: Compose,
    project_units: Callable[..., Any],
) -> dict[str, Any]:
    """Prove that one paired cell differs only by the certified step-718 action."""
    baseline = _terminal_payload(baseline_game, "baseline")
    candidate = _terminal_payload(candidate_game, "candidate")
    if baseline["candidate_seat"] != candidate["candidate_seat"]:
        raise ValueError("paired candidate seats differ")

    observation_equal = (
        baseline["terminal_candidate_observation"]
        == candidate["terminal_candidate_observation"]
    )
    configuration_equal = baseline["terminal_configuration"] == candidate["terminal_configuration"]
    opponent_action_equal = (
        baseline["terminal_opponent_action"] == candidate["terminal_opponent_action"]
    )
    if not observation_equal:
        raise ValueError("candidate drifted before the terminal action boundary")
    if not configuration_equal:
        raise ValueError("paired terminal configurations differ")
    if not opponent_action_equal:
        raise ValueError("opponent terminal action differs before candidate settlement resolves")

    observation = baseline["terminal_candidate_observation"]
    configuration = baseline["terminal_configuration"]
    baseline_action = baseline["terminal_candidate_action"]
    returned_action = candidate["terminal_candidate_action"]
    expected, raw_report = compose(
        observation,
        configuration,
        baseline_action,
        project_units=project_units,
    )
    if not isinstance(expected, dict) or not isinstance(raw_report, Mapping):
        raise ValueError("terminal settlement returned malformed evidence")
    report = dict(raw_report)
    if returned_action != expected:
        raise ValueError("candidate returned action does not equal the recomputed certificate")

    seat = int(baseline["candidate_seat"])
    baseline_own = _finite_number(baseline["scores"][seat], "baseline own score")
    baseline_rival = _finite_number(baseline["scores"][1 - seat], "baseline rival score")
    candidate_own = _finite_number(candidate["scores"][seat], "candidate own score")
    candidate_rival = _finite_number(candidate["scores"][1 - seat], "candidate rival score")
    own_delta = candidate_own - baseline_own
    rival_delta = candidate_rival - baseline_rival
    baseline_margin = baseline_own - baseline_rival
    candidate_margin = candidate_own - candidate_rival
    margin_delta = candidate_margin - baseline_margin
    baseline_outcome = _outcome(baseline_margin)
    candidate_outcome = _outcome(candidate_margin)
    outcome_regressed = _OUTCOME_RANK[candidate_outcome] < _OUTCOME_RANK[baseline_outcome]

    changed = expected != baseline_action
    trace_changed = baseline["trace_sha256"] != candidate["trace_sha256"]
    guaranteed = report.get("guaranteed_min_cash_gain", 0)
    if isinstance(guaranteed, bool) or not isinstance(guaranteed, int) or guaranteed < 0:
        raise ValueError("certificate lower bound is not a nonnegative integer")

    if changed:
        if report.get("changed") is not True or report.get("certified") is not True:
            raise ValueError("changed terminal action lacks a positive certificate")
        if guaranteed <= 0:
            raise ValueError("changed terminal action has no positive lower bound")
        if not trace_changed:
            raise ValueError("changed terminal action did not change the official trace")
        if own_delta + 1e-9 < guaranteed:
            raise ValueError(
                f"observed own delta {own_delta} is below certified minimum {guaranteed}"
            )
    else:
        if returned_action != baseline_action:
            raise ValueError("inactive certificate changed the returned action")
        if trace_changed:
            raise ValueError("inactive certificate changed the official trace")
        if abs(own_delta) > 1e-9 or abs(rival_delta) > 1e-9:
            raise ValueError("inactive certificate changed terminal scores")

    return {
        "valid": True,
        "activated": changed,
        "certified": bool(report.get("certified")),
        "reason": str(report.get("reason", "")),
        "guaranteed_min_cash_gain": guaranteed,
        "observed_own_delta": own_delta,
        "observed_rival_delta": rival_delta,
        "observed_margin_delta": margin_delta,
        "baseline_outcome": baseline_outcome,
        "candidate_outcome": candidate_outcome,
        "outcome_regressed": outcome_regressed,
        "bound_slack": own_delta - guaranteed if changed else 0.0,
        "observation_equal": observation_equal,
        "configuration_equal": configuration_equal,
        "opponent_terminal_action_equal": opponent_action_equal,
        "trace_changed": trace_changed,
        "baseline_action_sha256": digest(baseline_action),
        "expected_action_sha256": digest(expected),
        "returned_action_sha256": digest(returned_action),
        "terminal_observation_sha256": digest(observation),
        "terminal_configuration_sha256": digest(configuration),
        "added_sell_units": dict(report.get("added_sell_units") or {}),
        "dropped_actor_indices": list(report.get("dropped_actor_indices") or []),
        "baseline_sell_units": int(report.get("baseline_sell_units", 0)),
        "candidate_sell_units": int(report.get("candidate_sell_units", 0)),
        "episode_steps": 720,
        "actions_executed": 719,
        "terminal_step": 718,
    }


def opponent_seat_strata(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    groups: dict[tuple[str, int], list[Mapping[str, Any]]] = {}
    for row in rows:
        key = (str(row["opponent"]), int(row["candidate_seat"]))
        groups.setdefault(key, []).append(row)
    result: dict[str, dict[str, Any]] = {}
    for (opponent, seat), group in sorted(groups.items()):
        own = [_finite_number(row["own_delta"], "own_delta") for row in group]
        margin = [_finite_number(row["margin_delta"], "margin_delta") for row in group]
        regressions = sum(
            _OUTCOME_RANK[str(row["candidate_outcome"])]
            < _OUTCOME_RANK[str(row["baseline_outcome"])]
            for row in group
        )
        result[f"{opponent}:seat{seat}"] = {
            "cells": len(group),
            "mean_own_delta": statistics.fmean(own),
            "median_own_delta": statistics.median(own),
            "min_own_delta": min(own),
            "max_own_delta": max(own),
            "mean_margin_delta": statistics.fmean(margin),
            "median_margin_delta": statistics.median(margin),
            "min_margin_delta": min(margin),
            "max_margin_delta": max(margin),
            "outcome_regressions": regressions,
        }
    return result


def panel_verdict(
    rows: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    *,
    expected_cells: int = 32,
) -> dict[str, Any]:
    audits = [row.get("terminal_audit") for row in rows]
    if any(not isinstance(item, Mapping) or item.get("valid") is not True for item in audits):
        raise ValueError("panel contains unaudited cells")
    activated = [item for item in audits if item.get("activated") is True]
    strata = opponent_seat_strata(rows)
    outcome_regressions = sum(
        _OUTCOME_RANK[str(row["candidate_outcome"])]
        < _OUTCOME_RANK[str(row["baseline_outcome"])]
        for row in rows
    )
    checks = {
        "exact_32_cell_grid": len(rows) == expected_cells,
        "exact_720_state_719_action_lifecycle": all(
            item.get("episode_steps") == 720
            and item.get("actions_executed") == 719
            and item.get("terminal_step") == 718
            for item in audits
        ),
        "preterminal_observation_identity": all(
            item.get("observation_equal") is True and item.get("configuration_equal") is True
            for item in audits
        ),
        "opponent_terminal_action_identity": all(
            item.get("opponent_terminal_action_equal") is True for item in audits
        ),
        "returned_action_bound_activation": len(activated) > 0,
        "certificate_lower_bound_holds": all(
            float(item.get("observed_own_delta", -math.inf)) + 1e-9
            >= int(item.get("guaranteed_min_cash_gain", 0))
            for item in activated
        ),
        "positive_global_mean_own_cash": float(summary.get("mean_own_delta", 0.0)) > 0,
        "positive_global_median_own_cash": float(summary.get("median_own_delta", 0.0)) > 0,
        "no_negative_own_cash_cell": float(summary.get("min_own_delta", -math.inf)) >= 0,
        "positive_global_mean_margin": float(summary.get("mean_margin_delta", 0.0)) > 0,
        "no_negative_margin_cell": float(summary.get("min_margin_delta", -math.inf)) >= 0,
        "zero_outcome_regressions": outcome_regressions == 0,
        "no_negative_opponent_seat_own_stratum": bool(strata)
        and all(float(item["mean_own_delta"]) >= 0 for item in strata.values()),
        "no_negative_opponent_seat_margin_stratum": bool(strata)
        and all(float(item["mean_margin_delta"]) >= 0 for item in strata.values()),
    }
    return {
        "decision": "ADVANCE" if all(checks.values()) else "REJECT",
        "checks": checks,
        "scope": (
            "development evidence only; ADVANCE authorizes a separate one-tree composition "
            "experiment, not canonical promotion, merge, Kaggle upload, or leaderboard claim"
        ),
        "activated_cells": len(activated),
        "activation_rate": len(activated) / len(rows) if rows else 0.0,
        "outcome_regressions": outcome_regressions,
        "certified_min_cash_total": sum(
            int(item.get("guaranteed_min_cash_gain", 0)) for item in activated
        ),
        "observed_own_cash_total": sum(
            float(item.get("observed_own_delta", 0.0)) for item in activated
        ),
        "observed_rival_cash_total": sum(
            float(item.get("observed_rival_delta", 0.0)) for item in activated
        ),
        "observed_margin_total": sum(
            float(item.get("observed_margin_delta", 0.0)) for item in activated
        ),
        "opponent_seat_strata": strata,
    }
