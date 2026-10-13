# SPDX-License-Identifier: Apache-2.0
"""Productive successor admission for Gemini/Antigravity ALTWATER.

The original HYDRA theorem proves that some established TOMATO/STRAWBERRY plants
can survive one unwatered EOD.  The literal WATER->PASS rewrite is deliberately
*not* promoted here.  This module admits only a narrower two-day research pair:

    current eligible WATER -> HARVEST
    next day, same live plant -> exactly one semantic WATER

HARVEST is accepted only when the current source observation proves positive
stored yield and actor order proves that no earlier same-site actor consumes or
destroys that yield before the rewritten row executes.  The next-day observation
must prove that the same crop survived with the expected one-day missed-water
streak and the supplied recovery action must actually WATER that site without
another same-callback actor DIGging the plant.  Unit-action semantics are keyed by
row[0], so extended WATER rows count as WATER and duplicate semantic WATER rows
fail closed.  No forecast or scheduler promise is treated as execution proof.

Research/candidate-only.  No runtime/default/config key is created.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

import ongoing_water_skip as hydra

SCHEMA = "titan.v4.altwater-harvest-recovery/v1"
LAST_EXECUTABLE_STEP = 718


def _plain_step(observation: Any) -> int | None:
    if not isinstance(observation, dict):
        return None
    step = observation.get("step")
    return step if type(step) is int and 0 <= step <= LAST_EXECUTABLE_STEP else None


def _player(observation: Any) -> int | None:
    if not isinstance(observation, dict):
        return None
    player = observation.get("player")
    return player if type(player) is int and player in (0, 1) else None


def _farm(observation: Any) -> dict | None:
    player = _player(observation)
    if player is None:
        return None
    farms = observation.get("farms")
    if not isinstance(farms, list) or len(farms) != 2 or not isinstance(farms[player], dict):
        return None
    return farms[player]


def _tile(observation: Any, site: list[int]) -> Any:
    farm = _farm(observation)
    if farm is None or not isinstance(site, list) or len(site) != 2:
        return None
    x, y = site
    if type(x) is not int or type(y) is not int:
        return None
    tiles = farm.get("tiles")
    try:
        return tiles[y][x]
    except (TypeError, IndexError):
        return None


def _positions_and_rows(action: Any, observation: Any):
    farm = _farm(observation)
    if farm is None or not isinstance(action, dict):
        return None
    hands = farm.get("hands")
    rows = action.get("hands")
    if not isinstance(hands, list) or not isinstance(rows, list) or len(hands) != len(rows):
        return None
    positions = [farm.get("farmer"), *hands]
    unit_rows = [action.get("farmer"), *rows]
    if len(positions) != len(unit_rows):
        return None
    parsed = []
    for actor, (position, row) in enumerate(zip(positions, unit_rows)):
        if (not isinstance(position, list) or len(position) != 2
                or any(type(v) is not int or not 0 <= v < 10 for v in position)
                or not isinstance(row, list) or not row or type(row[0]) is not str):
            return None
        parsed.append((actor, position, row))
    return parsed


def _current_harvest_is_productive(
    action: Any,
    observation: Any,
    site: list[int],
    actor: Any,
) -> bool:
    """Prove the replacement HARVEST still has yield when this actor executes.

    The official engine executes actor 0 (main farmer) before hands in ascending
    actor order.  HYDRA intentionally reasons only about the unique exact WATER
    row, so another earlier same-site actor can still HARVEST the plant (zeroing
    ``yield_units``) or DIG it before the rewritten actor reaches the tile.
    Those cases make a pre-state positive-yield proof stale at execution time.
    """
    parsed = _positions_and_rows(action, observation)
    if (parsed is None or type(actor) is not int
            or actor < 0 or actor >= len(parsed)):
        return False
    candidate_actor, candidate_position, candidate_row = parsed[actor]
    if (candidate_actor != actor or candidate_position != site
            or candidate_row != ["WATER"]):
        return False
    for prior_actor, position, row in parsed:
        if prior_actor >= actor:
            break
        if position == site and row[0] in {"HARVEST", "DIG"}:
            return False
    return True


def _recovery_water_actor(action: Any, observation: Any, site: list[int]) -> int | None:
    """Authenticate one semantic same-site WATER and absence of destructive DIG.

    Unit rows execute in actor order and dispatch by ``row[0]``.  A DIG either
    before the WATER removes the target before recovery, or after the WATER
    destroys the supposedly recovered plant before callback end.  Both invalidate
    same-live-plant custody.  Multiple semantic WATER rows are also rejected:
    later WATER can be a no-op after the first, so selecting one exact row would
    not prove which actor performed the recovery.
    """
    parsed = _positions_and_rows(action, observation)
    if parsed is None:
        return None
    same_site = [(actor, row) for actor, position, row in parsed if position == site]
    if any(row[0] == "DIG" for _actor, row in same_site):
        return None
    matches = [actor for actor, row in same_site if row[0] == "WATER"]
    return matches[0] if len(matches) == 1 else None


def plan_water_harvest_recovery(
    current_action: Any,
    current_observation: Any,
    next_day_action: Any,
    next_day_observation: Any,
    configuration: Any,
) -> list[dict]:
    """Return exact two-day WATER->HARVEST / recovery-WATER certificates.

    The future observation/action are evidence from an already materialized
    open-loop or replay pair.  This function does not predict them and therefore
    cannot be used as a promise that a live scheduler will recover the tile.
    """
    now_step = _plain_step(current_observation)
    next_step = _plain_step(next_day_observation)
    player = _player(current_observation)
    if now_step is None or next_step is None or player is None:
        return []
    if _player(next_day_observation) != player:
        return []
    day = now_step // 24
    next_day = next_step // 24
    if next_day != day + 1:
        return []

    plans = hydra.plan_ongoing_water_skip(current_action, current_observation, configuration)
    out: list[dict] = []
    for plan in plans:
        site = plan.get("site")
        crop = plan.get("crop")
        actor = plan.get("actor")
        if not _current_harvest_is_productive(
            current_action, current_observation, site, actor
        ):
            continue
        current_tile = _tile(current_observation, site)
        if not isinstance(current_tile, dict) or current_tile.get("kind") != "PLANT":
            continue
        if current_tile.get("crop") != crop:
            continue
        yield_units = current_tile.get("yield_units")
        if type(yield_units) is not int or yield_units <= 0:
            continue

        future_tile = _tile(next_day_observation, site)
        if not isinstance(future_tile, dict) or future_tile.get("kind") != "PLANT":
            continue
        if (future_tile.get("crop") != crop
                or future_tile.get("planted_day") != current_tile.get("planted_day")
                or future_tile.get("consecutive_unwatered") != 1
                or future_tile.get("watered_today") is not False):
            continue

        recovery_actor = _recovery_water_actor(next_day_action, next_day_observation, site)
        if recovery_actor is None:
            continue
        out.append({
            "schema": SCHEMA,
            "current_step": now_step,
            "current_day": day,
            "current_actor": actor,
            "site": list(site),
            "crop": crop,
            "stored_yield_units": yield_units,
            "replacement_row": ["HARVEST"],
            "recovery_step": next_step,
            "recovery_day": next_day,
            "recovery_actor": recovery_actor,
            "recovery_op": "WATER",
            "productive_current_row_proved": True,
            "same_callback_semantic_water_count": 1,
            "same_callback_destructive_dig_absent": True,
            "same_live_plant_recovery_proved": True,
            "runtime_promise": False,
        })
    return out


def apply_water_harvest_recovery(
    current_action: Any,
    current_observation: Any,
    next_day_action: Any,
    next_day_observation: Any,
    configuration: Any,
    *,
    enabled: bool = False,
):
    """Build a research candidate only when the complete pair is certified.

    Disabled mode is exact identity.  Enabled mode changes only the currently
    certified unit row(s); the supplied next-day action is evidence and is never
    edited here.
    """
    if not enabled:
        return current_action
    certs = plan_water_harvest_recovery(
        current_action,
        current_observation,
        next_day_action,
        next_day_observation,
        configuration,
    )
    if not certs:
        return current_action
    result = deepcopy(current_action)
    seen: set[int] = set()
    for cert in certs:
        actor = cert["current_actor"]
        if type(actor) is not int or actor < 0 or actor in seen:
            return current_action
        seen.add(actor)
        if actor == 0:
            if result.get("farmer") != ["WATER"]:
                return current_action
            result["farmer"] = ["HARVEST"]
        else:
            hands = result.get("hands")
            if not isinstance(hands, list) or actor - 1 >= len(hands) or hands[actor - 1] != ["WATER"]:
                return current_action
            hands[actor - 1] = ["HARVEST"]
    return result
