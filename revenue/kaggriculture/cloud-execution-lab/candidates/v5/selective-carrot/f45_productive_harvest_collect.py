# SPDX-License-Identifier: Apache-2.0
"""F45: preserve proven productive HARVEST/COLLECT unit actions at terminal time.

The factor is intentionally narrow. It may restore a producer-selected HARVEST
or COLLECT_FERTILIZER only when a later finalizer replaced that exact unit slot
with PASS or movement, only inside the terminal horizon, and only when replaying
the candidate action proves a positive commodity realization. Market orders and
DROP/PICKUP/PLACE are never changed.
"""
from __future__ import annotations

from copy import deepcopy

PRODUCTIVE_OPS = frozenset(("HARVEST", "COLLECT_FERTILIZER"))
HOUSEKEEPING_OPS = frozenset(("PASS", "NORTH", "SOUTH", "EAST", "WEST"))
DEFAULT_TERMINAL_STEPS = 72


def _unit_actions(action):
    if not isinstance(action, dict):
        return None
    farmer = action.get("farmer")
    hands = action.get("hands", [])
    if not isinstance(farmer, list) or not isinstance(hands, list):
        return None
    if any(not isinstance(row, list) for row in hands):
        return None
    return [farmer, *hands]


def _set_unit_action(action, index, value):
    if index == 0:
        action["farmer"] = deepcopy(value)
    else:
        action["hands"][index - 1] = deepcopy(value)


def _commodity_total(private, products):
    inventories = private.get("inventories", []) if isinstance(private, dict) else []
    total = 0
    for inventory in inventories:
        if not isinstance(inventory, dict):
            continue
        for item in products:
            value = inventory.get(item, 0)
            if type(value) is int and value > 0:
                total += value
    return total


def _simulate_unit_stage(mechanics, obs, action, cfg):
    """Return realized carried commodity count, or None on an unsafe shape."""
    try:
        player = obs["player"]
        if type(player) is not int or player not in (0, 1):
            return None
        farms = obs["farms"]
        private = obs["private"]
        if not isinstance(farms, list) or len(farms) <= player or not isinstance(private, dict):
            return None
        units = _unit_actions(action)
        if units is None:
            return None
        farm = deepcopy(farms[player])
        private_copy = deepcopy(private)
        board_size = int(cfg.get("boardSize", len(farm.get("tiles", []))))
        turns_per_day = int(cfg.get("turnsPerDay", 24))
        shed_capacity = int(cfg.get("shedCapacity", 100))
        step = int(obs["step"])
        day = step // turns_per_day
        if board_size <= 0 or turns_per_day <= 0 or shed_capacity < 0:
            return None
        for index, row in enumerate(units):
            mechanics._apply_unit_action(
                farm, private_copy, index, deepcopy(row), board_size, day,
                turns_per_day, shed_capacity,
            )
        return _commodity_total(private_copy, mechanics.PRODUCTS)
    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        return None


def protect_productive_units(mechanics, obs, cfg, selected, returned, *, terminal_steps=DEFAULT_TERMINAL_STEPS):
    """Restore only replay-proven productive unit work displaced by housekeeping.

    Returns ``(action, report)``. Inputs are never mutated. The report is an
    engagement receipt suitable for later paired-screen attribution.
    """
    report = {
        "factor": "F45",
        "changed": False,
        "restored_slots": [],
        "reason": "not_engaged",
    }
    if type(terminal_steps) is not int or terminal_steps < 0:
        report["reason"] = "invalid_terminal_steps"
        return deepcopy(returned), report
    if not isinstance(obs, dict) or not isinstance(cfg, dict):
        report["reason"] = "malformed_observation_or_config"
        return deepcopy(returned), report
    try:
        step = obs["step"]
        episode_steps = cfg.get("episodeSteps", 720)
        if type(step) is not int or type(episode_steps) is not int or episode_steps < 2:
            raise ValueError
        last_actionable = episode_steps - 2
        remaining = last_actionable - step
    except (KeyError, TypeError, ValueError):
        report["reason"] = "malformed_clock"
        return deepcopy(returned), report
    report["remaining_steps"] = remaining
    if remaining < 0 or remaining > terminal_steps:
        report["reason"] = "outside_terminal_horizon"
        return deepcopy(returned), report

    selected_units = _unit_actions(selected)
    returned_units = _unit_actions(returned)
    if selected_units is None or returned_units is None or len(selected_units) != len(returned_units):
        report["reason"] = "malformed_or_mismatched_units"
        return deepcopy(returned), report

    candidate = deepcopy(returned)
    baseline_total = _simulate_unit_stage(mechanics, obs, candidate, cfg)
    if baseline_total is None:
        report["reason"] = "baseline_replay_failed"
        return deepcopy(returned), report
    report["baseline_carried_commodities"] = baseline_total

    for index, (wanted, actual) in enumerate(zip(selected_units, returned_units)):
        wanted_op = wanted[0] if wanted else None
        actual_op = actual[0] if actual else None
        if wanted_op not in PRODUCTIVE_OPS or actual_op not in HOUSEKEEPING_OPS:
            continue
        proposal = deepcopy(candidate)
        _set_unit_action(proposal, index, wanted)
        proposal_total = _simulate_unit_stage(mechanics, obs, proposal, cfg)
        if proposal_total is None or proposal_total <= baseline_total:
            continue
        candidate = proposal
        gain = proposal_total - baseline_total
        baseline_total = proposal_total
        report["restored_slots"].append({
            "slot": index,
            "op": wanted_op,
            "replaced": actual_op,
            "commodity_gain": gain,
        })

    if not report["restored_slots"]:
        report["reason"] = "no_replay_proven_productive_displacement"
        return deepcopy(returned), report
    report["changed"] = True
    report["reason"] = "restored_replay_proven_productive_work"
    report["final_carried_commodities"] = baseline_total
    report["commodity_gain"] = baseline_total - report["baseline_carried_commodities"]
    return candidate, report
