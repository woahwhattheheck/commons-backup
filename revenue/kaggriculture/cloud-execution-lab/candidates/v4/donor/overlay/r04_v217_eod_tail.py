# SPDX-License-Identifier: Apache-2.0
"""Pure additive planner for the V4 V217 final-pre-reset rescue.

The predecessor ``_v217_plan`` remains untouched.  This module is called only
when that incumbent planner returned ``None`` and the new flag is enabled.  It
repeats the incumbent admission proof and may return exactly one shortened task
whose FEED lands on the final callback before a real nightly reset.  Every
failed proof returns ``None``.
"""
from __future__ import annotations


_MISSING = object()
_STANDARD_CONFIG = {
    "episodeSteps": 720,
    "turnsPerDay": 24,
    "boardSize": 10,
    "shedCapacity": 100,
    "maxMarketOrdersPerTurn": 10,
}


def _cfg(configuration, name):
    try:
        if isinstance(configuration, dict):
            return configuration.get(name, _MISSING)
        return getattr(configuration, name, _MISSING) if configuration is not None else _MISSING
    except Exception:
        return _MISSING


def _standard_configuration(configuration):
    for name, expected in _STANDARD_CONFIG.items():
        value = _cfg(configuration, name)
        if type(value) is not int or value != expected:
            return False
    return True


def _rescue_end(step):
    """Authenticate the next real reset in the standard episode calendar.

    The engine executes callbacks 0..718. A reset follows hour 23 on days 0..28;
    the partial final day never reaches its hour 23. Negative Python indexes and
    caller-supplied pseudo-boundaries are not evidence of a nightly reset.
    """
    if type(step) is not int or not 0 <= step <= 718:
        return None
    hour = step % 24
    if not 16 <= hour <= 21:
        return None
    end = step + 24 - hour
    return end if end < 719 else None


def apply_v217_eod_tail(forward, roundtrip, *, targets, step, end,
                         farmer_rows, configuration, enabled=False):
    """Return ``(commands, eod_tail)`` without mutating either input route."""
    if not enabled:
        return roundtrip, False
    if not isinstance(forward, list) or not isinstance(roundtrip, list):
        return roundtrip, False
    expected_end = _rescue_end(step)
    if expected_end is None or type(end) is not int or end != expected_end:
        return roundtrip, False
    if not _standard_configuration(configuration):
        return roundtrip, False
    try:
        if len(targets) != 1:
            return roundtrip, False
    except TypeError:
        return roundtrip, False
    remaining = end - step
    if not (len(forward) == remaining < len(roundtrip)):
        return roundtrip, False
    if not isinstance(farmer_rows, list) or len(farmer_rows) != remaining:
        return roundtrip, False
    if any(row != ["PASS"] for row in farmer_rows):
        return roundtrip, False
    return forward, True


def plan_v217_eod_tail(view, st, step, action, pending, *, tape,
                        projected_wheat, configuration, enabled=False):
    """Build only the incumbent V217 rescue whose return leg crosses EOD.

    This mirrors predecessor ``_v217_plan`` admission until route construction.
    Unlike the predecessor, success is allowed only for the exact boundary where
    the outbound path plus FEED consumes every remaining callback and the normal
    round trip would be too long.  No predecessor state is mutated here.
    """
    if not enabled:
        return None
    if not isinstance(st, dict) or not isinstance(action, dict):
        return None
    end = _rescue_end(step)
    if end is None or not _standard_configuration(configuration):
        return None
    if st.get("v217_used", 0) >= 2:
        return None
    if action.get("farmer") != ["PASS"]:
        return None
    if not isinstance(tape, list):
        return None
    if len(tape) < end:
        return None

    # Exact predecessor reservation rules.
    try:
        reserved_wheat = sum(
            max(0, int(cmd[2]) if len(cmd) > 2 else 1)
            for cmd in pending
            if len(cmd) >= 2 and cmd[:2] == ["PICKUP", "WHEAT"]
        )
        for planned in tape[step:end]:
            for cmd in [planned.get("farmer") or []] + list(planned.get("hands") or []):
                if cmd and cmd[0] == "FEED":
                    return None
                if len(cmd) >= 2 and cmd[:2] == ["PICKUP", "WHEAT"]:
                    reserved_wheat += max(0, int(cmd[2]) if len(cmd) > 2 else 1)
    except (AttributeError, TypeError, ValueError, IndexError):
        return None

    try:
        start = tuple(view.positions[0])
        inventory = view.inventory(0)
    except (AttributeError, TypeError, IndexError):
        return None
    if not isinstance(inventory, dict):
        return None
    worker_wheat = inventory.get("WHEAT", 0)
    if type(worker_wheat) is not int or worker_wheat < 0:
        return None
    need_pickup = worker_wheat < 1
    if need_pickup:
        try:
            if any(inventory.values()) or not view.beside_shed(start):
                return None
        except (AttributeError, TypeError):
            return None
        if type(projected_wheat) is not int or projected_wheat < max(2, reserved_wheat + 1):
            return None

    try:
        targets = []
        for y, row in enumerate(view.tiles):
            for x, tile in enumerate(row):
                if (isinstance(tile, dict) and tile.get("animal")
                        and not tile.get("fed_today")
                        and tile.get("consecutive_unfed", 0) >= 1):
                    targets.append((abs(x - start[0]) + abs(y - start[1]), y, x))
    except (AttributeError, TypeError, IndexError):
        return None
    if len(targets) != 1:
        return None

    _, y, x = targets[0]
    moves = (
        ["EAST"] * max(0, x - start[0])
        + ["WEST"] * max(0, start[0] - x)
        + ["SOUTH"] * max(0, y - start[1])
        + ["NORTH"] * max(0, start[1] - y)
    )
    opposite = {"EAST": "WEST", "WEST": "EAST", "NORTH": "SOUTH", "SOUTH": "NORTH"}
    forward = ([["PICKUP", "WHEAT"]] if need_pickup else []) + [[m] for m in moves] + [["FEED"]]
    roundtrip = forward + [[opposite[m]] for m in reversed(moves)]
    try:
        farmer_rows = [list(tape[future_step].get("farmer") or ["PASS"])
                       for future_step in range(step, end)]
    except (AttributeError, TypeError, IndexError):
        return None
    commands, eod_tail = apply_v217_eod_tail(
        forward, roundtrip, targets=targets, step=step, end=end,
        farmer_rows=farmer_rows, configuration=configuration, enabled=True,
    )
    if not eod_tail:
        return None

    positions = []
    pos = start
    for cmd in commands:
        positions.append(pos)
        if cmd and cmd[0] in opposite:
            dx, dy = {"EAST": (1, 0), "WEST": (-1, 0),
                      "NORTH": (0, -1), "SOUTH": (0, 1)}[cmd[0]]
            pos = (pos[0] + dx, pos[1] + dy)
    if pos != (x, y):
        return None
    return {
        "step": step,
        "route": st.get("plan"),
        "commands": commands,
        "positions": positions,
        "target": (x, y),
    }
