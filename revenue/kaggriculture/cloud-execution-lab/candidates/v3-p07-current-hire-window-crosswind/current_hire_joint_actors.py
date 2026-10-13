# SPDX-License-Identifier: Apache-2.0
"""P07 successor that admits a proved current-HIRE existing-actor prefix.

All route geometry, bundle extraction, collision checks, state-equivalence
assumptions, application, and diagnostics remain delegated to the exact pinned
P07 implementation in ``joint_actors``.  This module changes only the window
admission theorem and loops over the actors physically present in the current
observation, so a newly hired actor can never enter a candidate pair.
"""
from __future__ import annotations

import time
from itertools import combinations

import joint_actors as _base
from current_hire_window import prove_window


def reconcile(spatial, observation, selected, controller):
    """Run P07 with a current-HIRE-safe existing-worker prefix."""

    started = time.perf_counter()
    stats = _base._ensure_stats(spatial)
    now = int(observation["step"])
    if now == 0:
        stats["activation_count"] = 0
        stats["travel_saved_total"] = 0
        stats["duplicate_targets_avoided"] = 0
        stats["noop_actions"] = 0
        stats["high_value_completed"] = 0
        stats["stock_contention"] = 0
        stats["runtime_seconds_total"] = 0.0

    farm = observation["farms"][observation["player"]]
    board = len(farm["tiles"])
    existing_actor_count = 1 + len(farm.get("hands") or [])
    runtime = lambda: round(time.perf_counter() - started, 6)
    proof = None

    def finish(report, result=None):
        report["runtime_seconds"] = runtime()
        stats["runtime_seconds_total"] = round(
            stats["runtime_seconds_total"] + report["runtime_seconds"], 6
        )
        report["activation_count"] = stats["activation_count"]
        report["stats"] = {
            "activation_count": stats["activation_count"],
            "travel_saved_total": stats["travel_saved_total"],
            "duplicate_targets_avoided": stats["duplicate_targets_avoided"],
            "noop_actions": stats["noop_actions"],
            "high_value_completed": stats["high_value_completed"],
            "stock_contention": stats["stock_contention"],
            "runtime_seconds_total": stats["runtime_seconds_total"],
        }
        if proof is not None:
            report["current_hire_window"] = proof.to_dict()
        spatial.joint_report = report
        if report.get("changed") or now % 24 == 23:
            _base._log({"step": now, "player": int(observation["player"]), **report})
        return (selected if result is None else result), report

    if board != 10:
        return finish(_base._noop("board_unsupported"))
    if existing_actor_count < 2:
        return finish(_base._noop(_base.REASON_NO_ACTORS))

    route = controller.R[controller.cur]
    configuration = getattr(spatial, "configuration", {}) or {}
    turns_per_day = configuration.get("turnsPerDay", 24)
    episode_steps = configuration.get("episodeSteps", 720)
    market_cap = configuration.get("maxMarketOrdersPerTurn", 10)
    if type(turns_per_day) is not int or turns_per_day != 24:
        return finish(_base._noop(_base.REASON_HIRE, window_reason="unsupported_turns_per_day"))
    if type(episode_steps) is not int or episode_steps != 720:
        return finish(_base._noop(_base.REASON_HIRE, window_reason="unsupported_episode_steps"))
    proof = prove_window(
        observation, selected, route, now, max_market_orders=market_cap
    )
    if not proof.accepted or proof.end is None:
        return finish(
            _base._noop(
                _base.REASON_HIRE,
                window_reason=proof.reason,
                existing_actors=proof.existing_actors,
                current_hires=proof.current_hires,
            )
        )
    end = proof.end

    crop_worker = None
    intent = getattr(spatial, "crop_intent", None)
    if isinstance(intent, dict):
        crop_worker = intent.get("worker")

    bundles = []
    # This physical-prefix range is the central safety property.  HIRE appends
    # actors after current unit execution, and those new indices are excluded.
    for worker in range(existing_actor_count):
        if crop_worker is not None and worker == crop_worker:
            continue
        bundle = _base.extract_bundle(
            observation, selected, route, worker, now, end, board
        )
        if bundle is not None:
            bundles.append(bundle)

    if len(bundles) == 0:
        return finish(_base._noop(_base.REASON_NO_BUNDLES))
    if len(bundles) == 1:
        return finish(_base._noop(_base.REASON_SINGLE_BUNDLE, complete_bundles=1))

    rejects = {}
    best = None
    stock_hits = 0
    for left, right in list(combinations(bundles, 2))[: _base.MAX_PAIRS]:
        choice, reason = _base._evaluate_swap(left, right, board, now)
        if reason:
            rejects[reason] = rejects.get(reason, 0) + 1
            if reason == _base.REASON_STOCK:
                stock_hits += 1
            continue
        key = (
            choice["saved_travel"],
            -choice["nearest"],
            -min(choice["i"], choice["j"]),
        )
        if best is None or key > best[0]:
            best = (key, choice)

    stats["stock_contention"] += stock_hits
    if best is None:
        order = (
            _base.REASON_CARGO_MASK,
            _base.REASON_UNRESUMABLE,
            _base.REASON_STOCK,
            _base.REASON_COLLISION,
            _base.REASON_NO_TRAVEL,
            _base.REASON_INCOMPAT,
        )
        reason = next((code for code in order if code in rejects), _base.REASON_INCOMPAT)
        return finish(
            _base._noop(
                reason,
                rejects=rejects,
                complete_bundles=len(bundles),
                stock_contention=stock_hits,
            )
        )

    choice = best[1]
    out, noop_actions = _base._apply(
        spatial, observation, selected, controller, now, board, choice
    )
    stats["activation_count"] += 1
    stats["travel_saved_total"] += choice["saved_travel"]
    stats["noop_actions"] += noop_actions
    stats["high_value_completed"] += choice["high_value"]
    trace = {
        "step": now,
        "owner": min(choice["i"], choice["j"]),
        "pair": [choice["i"], choice["j"]],
        "saved_travel": choice["saved_travel"],
        "cargo": [
            list(choice["bundle_i"]["cargo_key"]),
            list(choice["bundle_j"]["cargo_key"]),
        ],
        "origins": [
            list(choice["bundle_i"]["origin"]),
            list(choice["bundle_j"]["origin"]),
        ],
        "goals": [
            list(choice["bundle_i"]["goal"]),
            list(choice["bundle_j"]["goal"]),
        ],
        "hits": choice["collision_trace"],
    }
    report = {
        "changed": True,
        "reason": _base.REASON_ACCEPTED,
        "pair": [choice["i"], choice["j"]],
        "saved_travel": choice["saved_travel"],
        "collision_trace": trace,
        "activation": True,
        "duplicate_targets": 0,
        "noop_actions": noop_actions,
        "high_value": choice["high_value"],
        "stock_contention": stock_hits,
        "owner": min(choice["i"], choice["j"]),
        "rejects": rejects,
        "complete_bundles": len(bundles),
        "actor_prefix_count": existing_actor_count,
    }
    return finish(report, out)
