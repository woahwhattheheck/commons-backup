# SPDX-License-Identifier: Apache-2.0
"""Low-demand HIRE limiter that preserves literal market queue positions."""
from __future__ import annotations

from copy import deepcopy
import os
from typing import Any, Mapping


def enabled() -> bool:
    return os.environ.get("TITAN_E20_HIRE_GUARD", "0") in ("1", "true", "True")


def unwatered_crops(farm: Mapping[str, Any]) -> int:
    """Count actual engine PLANT tiles still needing today's WATER action."""
    count = 0
    for row in farm.get("tiles") or []:
        if not isinstance(row, list):
            continue
        for tile in row:
            if isinstance(tile, Mapping) and tile.get("kind") == "PLANT" and not tile.get("watered_today", False):
                count += 1
    return count


def _last_action_step(config: Mapping[str, Any]) -> int:
    try:
        return max(0, int(config.get("episodeSteps", 720)) - 2)
    except (TypeError, ValueError):
        return 718


def apply_hire_guard(
    obs: Mapping[str, Any],
    action: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
):
    report: dict[str, Any] = {
        "enabled": enabled(),
        "reason": "NO_OP",
        "changed": False,
        "dropped_indices": [],
    }
    if not enabled():
        return action, report

    cfg = dict(config or {})
    step = int(obs.get("step", 0))
    if step >= _last_action_step(cfg):
        report["reason"] = "NO_EDIT_TERMINAL_STEP"
        return action, report

    farms = obs.get("farms") or []
    player = int(obs.get("player", 0))
    if player < 0 or player >= len(farms) or not isinstance(farms[player], Mapping):
        report["reason"] = "BAD_PLAYER_OR_FARM"
        return action, report
    farm = farms[player]
    hires_today = max(0, int(farm.get("hires_today") or 0))
    max_hires = max(0, int(cfg.get("e20_max_hires_per_day", 3)))
    minimum_unwatered = max(0, int(cfg.get("e20_min_unwatered_crops", 3)))
    demand = unwatered_crops(farm)
    report.update(
        hires_today=hires_today,
        max_hires_per_day=max_hires,
        unwatered_crops=demand,
        minimum_unwatered_crops=minimum_unwatered,
    )

    # This guard is deliberately a low-demand limiter, not a universal cap.
    if demand >= minimum_unwatered:
        report["reason"] = "DEMAND_JUSTIFIES_HIRES"
        return action, report

    raw_market = action.get("market", []) if isinstance(action, Mapping) else []
    if not isinstance(raw_market, list):
        report["reason"] = "BAD_MARKET_QUEUE"
        return action, report
    hire_indices = [
        index
        for index, order in enumerate(raw_market)
        if isinstance(order, list) and order and order[0] == "HIRE"
    ]
    if not hire_indices:
        report["reason"] = "NO_HIRE"
        return action, report

    remaining_allowance = max(0, max_hires - hires_today)
    drop_indices = hire_indices[remaining_allowance:]
    if not drop_indices:
        report.update(reason="HIRES_WITHIN_LOW_DEMAND_ALLOWANCE", remaining_allowance=remaining_allowance)
        return action, report

    out = deepcopy(action)
    out_market = list(out.get("market") or [])
    for index in drop_indices:
        out_market[index] = []
    out["market"] = out_market
    report.update(
        reason="E20_DROP_EXCESS_LOW_DEMAND_HIRES",
        changed=True,
        dropped_indices=drop_indices,
        remaining_allowance=remaining_allowance,
    )
    return out, report
