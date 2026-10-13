# SPDX-License-Identifier: Apache-2.0
"""Default-OFF V5 research transform for end-of-day unit-action salvage.

Pinned-engine fact used by this candidate: after the last callback of a day,
every worker inventory is dropped into the shed (up to capacity) regardless of
worker position, then farmer/hands positions are reset. Therefore a final-tick
PASS/DROP/move has no positional value after the callback. This transform only
replaces such expendable actions with an immediately productive action at the
unit's *current* tile when a conservative aggregate-capacity certificate proves
the added output cannot displace any pre-existing carried goods at EOD.

No path planning, market edits, or daytime inventory policy live here.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

SCHEMA = "titan.v5.midnight-autodrop-productivity/v1"
MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}
EXPENDABLE = MOVES | {"PASS", "DROP"}

CROP_FIRST_YIELD_DAY = {"TOMATO": 8, "STRAWBERRY": 10}
ANIMAL_PRODUCT = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}


def _plain_nonnegative_int(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _config_int(configuration: Any, name: str, default: int, *, minimum: int | None = None) -> int | None:
    if configuration is None:
        value = default
    elif isinstance(configuration, dict):
        value = configuration.get(name, default)
    else:
        value = getattr(configuration, name, default)
    try:
        out = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if minimum is not None:
        out = max(minimum, out)
    return out


def _unit_actions(action: Any) -> list[Any] | None:
    if not isinstance(action, dict):
        return None
    farmer = action.get("farmer")
    hands = action.get("hands", [])
    if not isinstance(farmer, list) or not isinstance(hands, list):
        return None
    return [farmer, *hands]


def _positions(farm: Any) -> list[tuple[int, int]] | None:
    if not isinstance(farm, dict):
        return None
    farmer = farm.get("farmer")
    hands = farm.get("hands", [])
    if not (isinstance(farmer, (list, tuple)) and len(farmer) == 2 and isinstance(hands, list)):
        return None
    raw = [farmer, *hands]
    out = []
    for pos in raw:
        if not (isinstance(pos, (list, tuple)) and len(pos) == 2
                and type(pos[0]) is int and type(pos[1]) is int):
            return None
        out.append((pos[0], pos[1]))
    return out


def _inventory_total(inventories: Any) -> int | None:
    if not isinstance(inventories, list):
        return None
    total = 0
    for inv in inventories:
        if not isinstance(inv, dict):
            return None
        for qty in inv.values():
            n = _plain_nonnegative_int(qty)
            if n is None:
                return None
            total += n
    return total


def _shed_total(shed: Any) -> int | None:
    if not isinstance(shed, dict):
        return None
    total = 0
    for qty in shed.values():
        n = _plain_nonnegative_int(qty)
        if n is None:
            return None
        total += n
    return total


def _crop_harvestable(tile: dict[str, Any], day: int) -> bool:
    if tile.get("kind") != "PLANT":
        return False
    crop = tile.get("crop")
    first = CROP_FIRST_YIELD_DAY.get(crop)
    planted = _plain_nonnegative_int(tile.get("planted_day"))
    units = _plain_nonnegative_int(tile.get("yield_units"))
    return first is not None and planted is not None and units is not None and units > 0 and day - planted >= first


def _proposal(tile: Any, inv: dict[str, Any], day: int) -> tuple[list[Any], str, int, int] | None:
    """Return (action, reason, added_inventory, consumed_inventory)."""
    if not isinstance(tile, dict):
        return None

    animal = tile.get("animal")
    if animal in ANIMAL_PRODUCT:
        fed = tile.get("fed_today") is True
        cared = tile.get("cared_today") is True
        consecutive = _plain_nonnegative_int(tile.get("consecutive_unfed"))
        wheat = _plain_nonnegative_int(inv.get("WHEAT", 0))
        yield_units = _plain_nonnegative_int(tile.get("yield_units"))

        # Prevent an EOD escape before taking optional output. The pinned engine
        # removes the animal when this counter would reach two.
        if not fed and consecutive is not None and consecutive >= 1 and wheat and wheat > 0:
            return ["FEED"], "prevent_escape", 0, 1

        if yield_units is not None and yield_units > 0:
            return ["HARVEST"], "harvest_ready_animal", yield_units, 0

        # The engine overwrites fertilizer_available=True at EOD. Collecting the
        # already-ready unit now captures value that otherwise cannot accumulate.
        if tile.get("fertilizer_available") is True:
            return ["COLLECT_FERTILIZER"], "collect_before_refresh", 1, 0

        # CARE only creates a pending bonus when FEED is already satisfied.
        if fed and not cared:
            return ["CARE"], "care_after_feed", 0, 0

        if not fed and wheat and wheat > 0:
            return ["FEED"], "reset_unfed_counter", 0, 1
        return None

    if _crop_harvestable(tile, day):
        units = _plain_nonnegative_int(tile.get("yield_units"))
        return ["HARVEST"], "harvest_ready_crop", int(units), 0
    return None


def _existing_unit_output_upper_bound(tiles: list[Any], positions: list[tuple[int, int]], acts: list[Any]) -> int:
    """Conservative inventory units existing unit actions may add this callback."""
    total = 0
    for (x, y), act in zip(positions, acts):
        if not (isinstance(act, list) and act):
            continue
        if y < 0 or y >= len(tiles) or not isinstance(tiles[y], list) or x < 0 or x >= len(tiles[y]):
            continue
        tile = tiles[y][x]
        if not isinstance(tile, dict):
            continue
        if act[0] == "HARVEST":
            units = _plain_nonnegative_int(tile.get("yield_units"))
            if units:
                total += units
        elif act[0] == "COLLECT_FERTILIZER" and tile.get("fertilizer_available") is True:
            total += 1
    return total


def _market_inflow_upper_bound(action: Any, configuration: Any) -> int | None:
    """Upper-bound shed units that the engine-executable market prefix may buy."""
    if not isinstance(action, dict):
        return None
    market = action.get("market", [])
    if not isinstance(market, list):
        return None
    limit = _config_int(configuration, "maxMarketOrdersPerTurn", 10, minimum=1)
    if limit is None:
        return None
    total = 0
    for row in market[:limit]:
        if not (isinstance(row, list) and row):
            continue
        op = row[0]
        if op not in ("BUY_PRODUCT", "BUY_ANIMAL"):
            continue
        if len(row) < 3:
            continue
        try:
            quantity = int(row[2])
        except (TypeError, ValueError, OverflowError):
            continue
        if quantity <= 0:
            continue
        if op == "BUY_PRODUCT" and len(row) >= 2 and row[1] in ("WHEAT", "FERTILIZER"):
            total += quantity
        elif op == "BUY_ANIMAL" and len(row) >= 2 and row[1] in ANIMAL_PRODUCT:
            total += quantity
    return total


def apply(observation: Any, action: Any, configuration: Any = None) -> tuple[Any, dict[str, Any]]:
    report = {
        "schema": SCHEMA,
        "status": "inactive",
        "changed": False,
        "replacements": [],
    }
    if not isinstance(observation, dict):
        report["status"] = "invalid_observation"
        return action, report

    step = _plain_nonnegative_int(observation.get("step"))
    player = observation.get("player")
    turns = _config_int(configuration, "turnsPerDay", 24, minimum=1)
    capacity = _config_int(configuration, "shedCapacity", 100)
    if step is None or type(player) is not int or player not in (0, 1) or turns is None or capacity is None or capacity < 0:
        report["status"] = "invalid_identity_or_config"
        return action, report
    if step % turns != turns - 1:
        report["status"] = "not_final_tick"
        return action, report

    farms = observation.get("farms")
    private = observation.get("private")
    if not (isinstance(farms, list) and len(farms) > player and isinstance(private, dict)):
        report["status"] = "invalid_state"
        return action, report
    farm = farms[player]
    tiles = farm.get("tiles") if isinstance(farm, dict) else None
    positions = _positions(farm)
    acts = _unit_actions(action)
    inventories = private.get("inventories")
    shed = private.get("shed")
    shed_total = _shed_total(shed)
    carried_total = _inventory_total(inventories)
    if (not isinstance(tiles, list) or positions is None or acts is None
            or not isinstance(inventories, list)
            or shed_total is None or carried_total is None
            or len(positions) != len(acts) or len(inventories) < len(acts)):
        report["status"] = "invalid_unit_state"
        return action, report
    existing_output = _existing_unit_output_upper_bound(tiles, positions, acts)
    market_inflow = _market_inflow_upper_bound(action, configuration)
    if market_inflow is None:
        report["status"] = "invalid_market_state"
        return action, report

    # If the pre-existing goods do not all fit at EOD, the order in which
    # inventories auto-drop matters. Refuse to change any action in that state.
    room = capacity - shed_total
    baseline_required = carried_total + existing_output + market_inflow
    if room < baseline_required:
        report.update(
            status="preexisting_overflow_risk",
            capacity=capacity,
            shed_total=shed_total,
            carried_total=carried_total,
            existing_output_upper_bound=existing_output,
            market_inflow_upper_bound=market_inflow,
        )
        return action, report

    out = deepcopy(action)
    out_acts = [out["farmer"], *out.get("hands", [])]
    added = 0
    consumed = 0
    used_tiles: set[tuple[int, int]] = set()
    day = step // turns

    for idx, original in enumerate(acts):
        if not (isinstance(original, list) and original and original[0] in EXPENDABLE):
            continue
        x, y = positions[idx]
        if (x, y) in used_tiles or y < 0 or y >= len(tiles):
            continue
        row = tiles[y]
        if not isinstance(row, list) or x < 0 or x >= len(row):
            continue
        tile = row[x]
        inv = inventories[idx]
        if not isinstance(inv, dict):
            continue
        proposed = _proposal(tile, inv, day)
        if proposed is None:
            continue
        replacement, reason, add_qty, consume_qty = proposed

        # Conservative global EOD certificate: enough shed room for every
        # pre-existing carried item plus all candidate-added output after any
        # candidate-consumed input. This removes dependency on dict/worker drop
        # iteration order and proves no old carried good can be displaced.
        next_added = added + add_qty
        next_consumed = consumed + consume_qty
        required = carried_total + existing_output + market_inflow - next_consumed + next_added
        if required > room:
            continue

        if idx == 0:
            out["farmer"] = replacement
        else:
            out["hands"][idx - 1] = replacement
        out_acts[idx] = replacement
        used_tiles.add((x, y))
        added = next_added
        consumed = next_consumed
        report["replacements"].append({
            "unit_index": idx,
            "position": [x, y],
            "from": deepcopy(original),
            "to": deepcopy(replacement),
            "reason": reason,
            "added_inventory": add_qty,
            "consumed_inventory": consume_qty,
        })

    if report["replacements"]:
        report.update(
            status="salvaged",
            changed=True,
            step=step,
            day=day,
            capacity=capacity,
            shed_total=shed_total,
            carried_total=carried_total,
            existing_output_upper_bound=existing_output,
            market_inflow_upper_bound=market_inflow,
            added_inventory=added,
            consumed_inventory=consumed,
            certified_eod_total=shed_total + carried_total + existing_output + market_inflow - consumed + added,
        )
        return out, report

    report.update(
        status="no_safe_opportunity",
        step=step,
        capacity=capacity,
        shed_total=shed_total,
        carried_total=carried_total,
        existing_output_upper_bound=existing_output,
        market_inflow_upper_bound=market_inflow,
    )
    return action, report
