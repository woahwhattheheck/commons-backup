#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Default-OFF same-callback unit-action pipeline admission for TITAN V4.

The official engine applies the main farmer first, then each hand in list order,
mutating shared tile/private state after every actor and only processing the
market afterwards.  This helper does not invent work.  It only reorders a
strictly pure, same-site DIG -> PLANT -> WATER chain that is already present in
the returned unit-action multiset.

No movement, inventory-carrying action, market row, actor count, crop quantity,
or seed demand is added.  Ambiguity fails closed.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
_PURE = {"PASS", "DIG", "PLANT", "WATER"}
_REMOVABLE = {"WEED", "COOP", "PASTURE"}
_RANK = {"DIG": 0, "PLANT": 1, "WATER": 2, "PASS": 3}


def _row_op(row: Any) -> str | None:
    if not isinstance(row, list) or not row or not isinstance(row[0], str):
        return None
    return row[0]


def _canonical_pure_row(row: Any) -> bool:
    op = _row_op(row)
    if op == "PLANT":
        return len(row) == 2 and isinstance(row[1], str) and bool(row[1])
    if op in {"PASS", "DIG", "WATER"}:
        return row == [op]
    return False


def _position(value: Any) -> tuple[int, int] | None:
    if (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and type(value[0]) is int
        and type(value[1]) is int
    ):
        return int(value[0]), int(value[1])
    return None


def reorder_unit_pipeline(observation: dict[str, Any], selected: dict[str, Any], *,
                          enabled: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a conservative same-site action reordering and machine report.

    The only admitted chains are:

    * empty tile: PLANT -> WATER;
    * WEED/empty COOP/empty PASTURE: DIG -> PLANT [-> WATER].

    Every non-PASS row at that site must belong to the chain.  Because DIG,
    PLANT and WATER do not depend on actor-local inventory and every actor is
    already co-located, moving those rows between the co-located actor slots
    preserves per-actor inventory and the raw PLANT crop-count used by the
    engine's atomic seed-collateral check.
    """
    result = deepcopy(selected)
    report: dict[str, Any] = {
        "schema": "titan.v4.unit-pipeline.v1",
        "engine_git_blob": ENGINE_GIT_BLOB,
        "enabled": bool(enabled),
        "changed": False,
        "eligible_groups": 0,
        "changed_groups": 0,
        "changes": [],
        "refusals": {},
    }

    def refuse(reason: str) -> None:
        report["refusals"][reason] = report["refusals"].get(reason, 0) + 1

    if not enabled:
        refuse("disabled")
        return result, report
    if not isinstance(observation, dict) or not isinstance(selected, dict):
        refuse("invalid_input")
        return result, report

    player = observation.get("player")
    farms = observation.get("farms")
    private = observation.get("private")
    if type(player) is not int or not isinstance(farms, list) or not (0 <= player < len(farms)):
        refuse("missing_player_farm")
        return result, report
    farm = farms[player]
    if not isinstance(farm, dict) or not isinstance(private, dict):
        refuse("missing_private_or_farm")
        return result, report
    if "farmer" not in selected or "hands" not in selected:
        refuse("missing_unit_rows")
        return result, report

    farmer_row = selected["farmer"]
    hands_rows = selected["hands"]
    if not isinstance(hands_rows, list):
        refuse("hands_not_list")
        return result, report
    rows = [farmer_row, *hands_rows]

    farmer_pos = _position(farm.get("farmer"))
    hands_pos = farm.get("hands", [])
    if farmer_pos is None or not isinstance(hands_pos, list):
        refuse("invalid_positions")
        return result, report
    positions = [farmer_pos]
    for raw in hands_pos:
        pos = _position(raw)
        if pos is None:
            refuse("invalid_positions")
            return result, report
        positions.append(pos)

    if len(rows) > len(positions):
        refuse("unrepresented_action_actor")
        return result, report

    groups: dict[tuple[int, int], list[int]] = {}
    for idx in range(len(rows)):
        groups.setdefault(positions[idx], []).append(idx)

    tiles = farm.get("tiles")
    seeds = private.get("seeds")
    if not isinstance(tiles, list) or not isinstance(seeds, dict):
        refuse("missing_tiles_or_seeds")
        return result, report

    plant_demand: dict[str, int] = {}
    for row in rows:
        if isinstance(row, list) and len(row) >= 2 and row[0] == "PLANT" and isinstance(row[1], str):
            plant_demand[row[1]] = plant_demand.get(row[1], 0) + 1

    out_rows = [deepcopy(row) for row in rows]
    for (x, y), actors in sorted(groups.items(), key=lambda item: item[0]):
        if len(actors) < 2:
            continue
        if y < 0 or y >= len(tiles) or not isinstance(tiles[y], list) or x < 0 or x >= len(tiles[y]):
            refuse("position_out_of_bounds")
            continue

        group_rows = [rows[idx] for idx in actors]
        if any(not _canonical_pure_row(row) for row in group_rows):
            refuse("noncanonical_or_impure_row")
            continue
        ops = [_row_op(row) for row in group_rows]
        if any(op not in _PURE for op in ops):
            refuse("impure_op")
            continue

        nonpass = [(idx, row) for idx, row in zip(actors, group_rows) if _row_op(row) != "PASS"]
        nonpass_ops = [_row_op(row) for _, row in nonpass]
        if nonpass_ops.count("PLANT") != 1 or nonpass_ops.count("DIG") > 1 or nonpass_ops.count("WATER") > 1:
            refuse("unsupported_chain_shape")
            continue
        if len(nonpass) < 2:
            continue

        plant_row = next(row for _, row in nonpass if _row_op(row) == "PLANT")
        crop = plant_row[1]
        available = seeds.get(crop, 0)
        if type(available) is not int or available <= 0:
            refuse("seed_not_observed_available")
            continue
        if plant_demand.get(crop, 0) > available:
            refuse("atomic_seed_collateral_unmet")
            continue

        tile = tiles[y][x]
        dig_count = nonpass_ops.count("DIG")
        if tile is None:
            if dig_count:
                refuse("dig_on_empty_tile")
                continue
        elif isinstance(tile, dict) and tile.get("kind") in _REMOVABLE and "animal" not in tile:
            if dig_count != 1:
                refuse("occupied_tile_requires_exact_dig")
                continue
        else:
            refuse("tile_not_safe_for_pipeline")
            continue

        desired_nonpass = sorted((deepcopy(row) for _, row in nonpass), key=lambda row: _RANK[_row_op(row)])
        current_nonpass = [row for _, row in nonpass]
        if desired_nonpass == current_nonpass:
            report["eligible_groups"] += 1
            continue

        report["eligible_groups"] += 1
        target_slots = [idx for idx, _ in nonpass]
        before = [deepcopy(out_rows[idx]) for idx in target_slots]
        for idx, row in zip(target_slots, desired_nonpass):
            out_rows[idx] = row
        after = [deepcopy(out_rows[idx]) for idx in target_slots]
        report["changed_groups"] += 1
        report["changes"].append({
            "position": [x, y],
            "actors": target_slots,
            "before": before,
            "after": after,
            "crop": crop,
        })

    result["farmer"] = out_rows[0]
    result["hands"] = out_rows[1:]
    report["changed"] = result != selected
    return result, report
