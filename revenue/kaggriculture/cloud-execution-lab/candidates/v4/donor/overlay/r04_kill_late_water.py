# SPDX-License-Identifier: Apache-2.0
"""R04 lane L1 "kill-late-water": suppress WATER commands that provably cannot pay off.

Attaches in r04_full_router.v3_agent between POLICY_AGENT and the ROW_ORDER block,
behind the TITAN-CONFIG.json key r04_kill_late_water (default False). When the
r04_full_router.KILL_LATE_WATER module flag is on and 672 <= step <= 718, every worker
whose command is exactly ["WATER"] is checked against the tile that worker stands on;
the WATER becomes ["PASS"] when the watering provably cannot pay off:

  (a) non_plant      - the tile is not a dict with kind == "PLANT" and a crop set
                       (LOCKED / SOIL / WEED / None / COOP / PASTURE: WATER is a no-op);
  (b) already_watered - tile.get("watered_today") is True. Watering is day-granular:
                       replay evidence (744 second-water events across 3 real Kaggle
                       replays, both seats) shows a WATER issued on an already-watered
                       plant tile changes nothing observable: yield_units delta is
                       exactly 0 in all 744 events, the flag stays True and
                       consecutive_unwatered stays 0.
  (c) dead_or_dying  - int(tile.get("max_lifespan_step", 720)) <= step: the crop is dead
                       or dies at/before this step (replay: a tile with
                       max_lifespan_step == 672 was WEED at 673), so no future harvest
                       can collect the watered yield;
  (d) past_last      - step >= 719 (defensive; the route never acts there).

The freed hand becomes ["PASS"]. This is the correct documented outcome: the tape
route has no live worker reassignment, so there is nothing productive to redirect the
worker to; the tape issues the next step's orders normally on the following step.
No other command is touched, and HARVEST is never preferred over anything.

The layer never raises: any unexpected observation shape leaves the action unchanged.
Standard library only.
"""

from __future__ import annotations

# Suppression window. Coupled to the route's LAST_STEP: r04_full_router.LAST_STEP is
# 718, the last step the route acts on (the episode has 720 steps). LATE_START is the
# earliest step at which endgame crops begin hitting max_lifespan_step.
LATE_START = 672
LATE_END = 718

_WATER = ["WATER"]
_PASS = ["PASS"]

_REASONS = ("non_plant", "already_watered", "dead_or_dying", "past_last")

# Marker for "no tile could be read under this worker" (malformed observation or an
# out-of-range position). Distinct from a None tile, which rule (a) suppresses.
_UNKNOWN = object()


def _fresh_report():
    report = {"steps_active": 0, "productive_kept": 0}
    report.update({reason: 0 for reason in _REASONS})
    return report


# Module-level report: counts per suppression reason, steps where the layer ran, and
# WATERs kept because they could still pay off. reset() restores the zeros (for tests).
report = _fresh_report()


def reset():
    """Restore the module-level report counters to zero."""
    report.clear()
    report.update(_fresh_report())


def get_report():
    """Return a copy of the module-level report counters."""
    return dict(report)


def suppress_reason(step, tile):
    """Return the suppression reason for a WATER on this tile, or None to keep it.

    Pure function of (step, tile); reasons are (a) non_plant, (b) already_watered,
    (c) dead_or_dying, (d) past_last. Never raises.
    """
    try:
        # (a) not a planted crop: WATER is a no-op.
        if not (isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("crop")):
            return "non_plant"
        # (b) watering is day-granular: a second watering the same day is a no-op.
        if tile.get("watered_today") is True:
            return "already_watered"
        # (c) the crop is dead or dies at/before this step.
        try:
            max_lifespan_step = int(tile.get("max_lifespan_step", 720))
        except (TypeError, ValueError):
            max_lifespan_step = 720
        if max_lifespan_step <= step:
            return "dead_or_dying"
        # (d) defensive: the route never acts at step 719+.
        if step >= 719:
            return "past_last"
    except Exception:
        # An unreadable tile is not positive evidence of a no-op: keep the WATER.
        return None
    return None


def _worker_tile(farm, position):
    """Return the tile under a worker, or _UNKNOWN when it cannot be read.

    Out-of-range positions are unknowable (Python negative indices would otherwise
    silently wrap to a real tile); a worker whose tile is unknowable keeps its WATER.
    """
    try:
        x, y = position
        if isinstance(x, bool) or isinstance(y, bool):
            return _UNKNOWN
        if not isinstance(x, int) or not isinstance(y, int):
            return _UNKNOWN
        tiles = farm["tiles"]
        if y < 0 or y >= len(tiles):
            return _UNKNOWN
        row = tiles[y]
        if x < 0 or x >= len(row):
            return _UNKNOWN
        return row[x]
    except Exception:
        return _UNKNOWN


def apply_kill_late_water(observation, action):
    """Suppress provably dead WATER commands in the late window; never raises.

    Returns the action unchanged outside steps LATE_START..LATE_END, when the action
    is malformed, or when nothing is suppressed. Suppressed workers become ["PASS"].
    """
    try:
        return _apply(observation, action)
    except Exception:
        return action


def _apply(observation, action):
    try:
        step = int(observation["step"])
    except Exception:
        return action
    if step < LATE_START or step > LATE_END:
        return action
    if not isinstance(action, dict):
        return action
    try:
        farm = observation["farms"][observation["player"]]
        positions = [farm["farmer"]] + list(farm.get("hands") or [])
    except Exception:
        return action
    farmer_command = action.get("farmer")
    hand_commands = action.get("hands") or []
    commands = [farmer_command] + list(hand_commands)

    report["steps_active"] += 1
    changed = False
    new_commands = list(commands)
    for index, (command, position) in enumerate(zip(commands, positions)):
        if command != _WATER:
            continue
        try:
            tile = _worker_tile(farm, position)
        except Exception:
            continue
        if tile is _UNKNOWN:
            # Unknowable tile: not positive evidence of a no-op, keep the WATER.
            continue
        reason = suppress_reason(step, tile)
        if reason is None:
            report["productive_kept"] += 1
            continue
        report[reason] += 1
        new_commands[index] = list(_PASS)
        changed = True
    if not changed:
        return action
    new_action = dict(action)
    new_action["farmer"] = new_commands[0]
    new_action["hands"] = new_commands[1:]
    return new_action
