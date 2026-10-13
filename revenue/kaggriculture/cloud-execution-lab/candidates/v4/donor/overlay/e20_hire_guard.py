# SPDX-License-Identifier: Apache-2.0
"""E20: low-demand HIRE limiter that preserves literal market queue positions.

Lineage: TESSERA (Gemini) E20 -> G01 (Grok Build #2, PR #11371) -> ARGUS
semantic-safety repair (candidates/v3-g01-argus-safe, findings A5/A6/A8) -> V3.

V3 wiring: package key `e20_hire_guard`; the runtime passes `enabled` explicitly.
No environment reads.  Identity when disabled.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


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
    except (TypeError, ValueError, OverflowError):
        return 718


def _market_order_limit(config: Mapping[str, Any]) -> int:
    try:
        return max(1, int(config.get("maxMarketOrdersPerTurn", 10)))
    except (TypeError, ValueError, OverflowError):
        return 10


def apply_hire_guard(
    obs: Mapping[str, Any],
    action: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
    *,
    enabled: bool = False,
):
    report: dict[str, Any] = {
        "enabled": bool(enabled),
        "reason": "NO_OP",
        "changed": False,
        "dropped_indices": [],
    }
    if not enabled:
        report["reason"] = "OFF"
        return action, report

    # A low-demand edit needs typed observation evidence. In particular, bool
    # is an int subclass and int(True) silently selects the other player's farm;
    # coercing non-finite or container values can also abort the whole turn.
    if (not isinstance(obs, Mapping) or not isinstance(action, Mapping)
            or (config is not None and not isinstance(config, Mapping))):
        report["reason"] = "BAD_INPUT"
        return action, report
    cfg = dict(config or {})
    for key, default in (
        ("episodeSteps", 720),
        ("maxMarketOrdersPerTurn", 10),
        ("e20_max_hires_per_day", 3),
        ("e20_min_unwatered_crops", 3),
    ):
        if type(cfg.get(key, default)) is not int:
            report.update(reason="BAD_CONFIG_INTEGER", field=key)
            return action, report
    step = obs.get("step")
    if type(step) is not int or step < 0:
        report["reason"] = "BAD_STEP"
        return action, report
    if step >= _last_action_step(cfg):
        report["reason"] = "NO_EDIT_TERMINAL_STEP"
        return action, report

    farms = obs.get("farms")
    player = obs.get("player")
    if (type(player) is not int or not isinstance(farms, list)
            or player < 0 or player >= len(farms)
            or not isinstance(farms[player], Mapping)):
        report["reason"] = "BAD_PLAYER_OR_FARM"
        return action, report
    farm = farms[player]
    hires_today = farm.get("hires_today")
    if type(hires_today) is not int or hires_today < 0:
        report["reason"] = "BAD_HIRES_TODAY"
        return action, report
    tiles = farm.get("tiles")
    if not isinstance(tiles, list):
        report["reason"] = "BAD_TILES"
        return action, report
    for row in tiles:
        if not isinstance(row, list):
            report["reason"] = "BAD_TILES"
            return action, report
        for tile in row:
            # Official _initial_tile uses None for an unlocked empty cell and
            # the literal LOCKED string outside the owned quadrants.
            if tile is None or (type(tile) is str and tile == "LOCKED"):
                continue
            if (not isinstance(tile, Mapping)
                    or (tile.get("kind") == "PLANT"
                        and type(tile.get("watered_today", False)) is not bool)):
                # Unknown demand must not be counted as zero demand. An absent
                # watered_today retains the old conservative unwatered default.
                report["reason"] = "BAD_TILES"
                return action, report
    max_hires = max(0, cfg.get("e20_max_hires_per_day", 3))
    minimum_unwatered = max(0, cfg.get("e20_min_unwatered_crops", 3))
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
    market_order_limit = _market_order_limit(cfg)
    hire_indices = [
        index
        for index, order in enumerate(raw_market[:market_order_limit])
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
