# SPDX-License-Identifier: Apache-2.0
"""R04 lane B5 "fert-daily-sweep": collect each day's free fertilizer with idle workers.

Attaches in r04_full_router.v3_agent between POLICY_AGENT and the ROW_ORDER block,
behind the TITAN-CONFIG.json key r04_fert_daily_sweep (default False). Every animal
tile sets ``fertilizer_available = True`` once per day and the flag is a boolean:
a unit not collected before the next daily transition evaporates and never stacks.
The published shop-router tapes already collect while passing through, and the V218
layer sweeps terminally at steps 712-718, but any PASS (idle) worker standing on an
animal tile whose flag is still set is a free unit the route leaves to evaporate.

When the r04_full_router.FERT_DAILY_SWEEP module flag is on, every worker whose
command is exactly ["PASS"] is considered for two rewrites; no other command is
ever touched, so higher-value tape work is never displaced:

  collect - the worker stands on a tile with an animal and
            ``fertilizer_available`` set: the PASS becomes ["COLLECT_FERTILIZER"].
            The worker does not move, so the tape's position-dependent route is
            undisturbed and the next step's orders apply normally. Two workers on
            the same tile in one step collect only once (the second collection
            would be an engine no-op); the tile is claimed per step.
  deliver - the worker is beside the shed, holds FERTILIZER, holds no animal
            items (a DROP would otherwise strand a tape-planned PLACE), and the
            tape plans no FERTILIZE or FEED for that worker for the rest of the
            day (both consume worker inventory): the PASS becomes ["DROP"], which
            moves the fertilizer into the shed the same step. This needs the
            route tape; when tape is None the deliver half is skipped and only
            collection runs. Fertilizer that is not dropped same-day still reaches
            the shed through the tape's own DROP rows or the end-of-day inventory
            sweep.

Early sale needs no new market rows: with the V3.1 default r04_sale_fertilizer on,
the E184 sale window's reserve_sales already advances the tape's planned
FERTILIZER SELL rows whenever projected shed stock exists, and fertilizer's price
curve only falls as market supply accumulates, so same-day shed delivery is what
routes the units into early sales. The lane adds no market rows itself and never
exceeds the market-order budget.

The layer never raises: any unexpected observation shape leaves the action
unchanged. Standard library only.
"""

from __future__ import annotations

_PASS = ["PASS"]
_COLLECT = ["COLLECT_FERTILIZER"]
_DROP = ["DROP"]

# Worker-inventory consumers the deliver half must not starve: FERTILIZE takes
# FERTILIZER, FEED takes WHEAT. (PLACE takes animal items; those are excluded by
# the no-animals-in-inventory rule instead.)
_INVENTORY_WORK = ("FERTILIZE", "FEED")

# Animal item keys, mirroring the engine's ANIMALS. A worker holding one of these
# beside the shed is waiting on a tape-planned PLACE, never a DROP candidate.
_ANIMALS = ("GOOSE", "COW", "SHEEP")

# Marker for "no tile could be read under this worker" (malformed observation or
# an out-of-range position). Distinct from a None tile, on which nothing happens.
_UNKNOWN = object()


def _fresh_report():
    return {
        "steps_active": 0,
        "collected": 0,
        "dropped": 0,
        "collect_skipped_claimed": 0,
        "drop_skipped_guard": 0,
    }


# Module-level report: steps where the layer ran, units collected/dropped, and
# guard skips. reset() restores the zeros (for tests).
report = _fresh_report()


def reset():
    """Restore the module-level report counters to zero."""
    report.clear()
    report.update(_fresh_report())


def get_report():
    """Return a copy of the module-level report counters."""
    return dict(report)


def _worker_tile(tiles, position):
    """Return the tile under a worker, or _UNKNOWN when it cannot be read.

    Out-of-range positions are unknowable (Python negative indices would
    otherwise silently wrap to a real tile); a worker whose tile is unknowable
    keeps its PASS.
    """
    try:
        x, y = position
        if isinstance(x, bool) or isinstance(y, bool):
            return _UNKNOWN
        if not isinstance(x, int) or not isinstance(y, int):
            return _UNKNOWN
        if y < 0 or y >= len(tiles):
            return _UNKNOWN
        row = tiles[y]
        if x < 0 or x >= len(row):
            return _UNKNOWN
        return row[x]
    except Exception:
        return _UNKNOWN


def _beside_shed(tiles, position):
    """True when the worker stands on a shed-access tile."""
    try:
        center = len(tiles) // 2
        x, y = position
        return x in (center - 1, center) and y in (center - 1, center)
    except Exception:
        return False


def _has_inventory_work(tape, worker, step):
    """True when the tape plans FERTILIZE/FEED for this worker later today.

    Both consume worker inventory, so a DROP now would starve them. Fails
    closed: an unreadable tape counts as "has work" and the DROP is skipped.
    """
    try:
        day_end = (int(step) // 24 + 1) * 24
        for future in range(int(step) + 1, min(day_end, len(tape))):
            planned = tape[future]
            commands = [planned.get("farmer")] + list(planned.get("hands") or [])
            if worker >= len(commands):
                continue
            command = commands[worker] or _PASS
            if command and command[0] in _INVENTORY_WORK:
                return True
        return False
    except Exception:
        return True


def _collectable(tile):
    """True when the engine's COLLECT_FERTILIZER would succeed on this tile."""
    return (
        isinstance(tile, dict)
        and "animal" in tile
        and bool(tile.get("fertilizer_available"))
    )


def apply_fert_daily_sweep(observation, action, tape=None):
    """Rewrite idle workers into fertilizer collection/delivery; never raises.

    Returns the action unchanged when the observation or action is malformed,
    when nothing qualifies, or when tape is None and no collection applies
    (the deliver half needs the tape for its inventory-work guard).
    """
    try:
        return _apply(observation, action, tape)
    except Exception:
        return action


def _apply(observation, action, tape):
    try:
        step = int(observation["step"])
    except Exception:
        return action
    if not isinstance(action, dict):
        return action
    try:
        farm = observation["farms"][observation["player"]]
        tiles = farm["tiles"]
        positions = [farm["farmer"]] + list(farm.get("hands") or [])
        inventories = (observation.get("private") or {}).get("inventories") or []
    except Exception:
        return action
    farmer_command = action.get("farmer")
    hand_commands = action.get("hands") or []
    commands = [farmer_command] + list(hand_commands)

    report["steps_active"] += 1
    changed = False
    claimed = set()
    new_commands = list(commands)
    for index, (command, position) in enumerate(zip(commands, positions)):
        # Budget rule: only idle workers are ever touched. Any real command,
        # including a V218 terminal task, is left exactly as the route issued it.
        if command != _PASS:
            continue
        try:
            tile = _worker_tile(tiles, position)
        except Exception:
            continue
        if tile is _UNKNOWN:
            continue
        try:
            inventory = inventories[index] if index < len(inventories) else {}
            if not isinstance(inventory, dict):
                inventory = {}
        except Exception:
            inventory = {}
        if _collectable(tile):
            x, y = position
            if (x, y) in claimed:
                # Two actors on one tile: the engine would no-op the second
                # collection, so keep the second worker's PASS.
                report["collect_skipped_claimed"] += 1
                continue
            claimed.add((x, y))
            new_commands[index] = list(_COLLECT)
            report["collected"] += 1
            changed = True
            continue
        # Deliver half: needs the tape for the inventory-work guard.
        if tape is None:
            continue
        if not _beside_shed(tiles, position):
            continue
        if int(inventory.get("FERTILIZER", 0)) <= 0:
            continue
        if any(item in _ANIMALS for item in inventory):
            # A held animal is waiting on a tape-planned PLACE; a DROP would
            # strand it in the shed.
            report["drop_skipped_guard"] += 1
            continue
        if _has_inventory_work(tape, index, step):
            report["drop_skipped_guard"] += 1
            continue
        new_commands[index] = list(_DROP)
        report["dropped"] += 1
        changed = True
    if not changed:
        return action
    new_action = dict(action)
    new_action["farmer"] = new_commands[0]
    new_action["hands"] = new_commands[1:]
    return new_action
