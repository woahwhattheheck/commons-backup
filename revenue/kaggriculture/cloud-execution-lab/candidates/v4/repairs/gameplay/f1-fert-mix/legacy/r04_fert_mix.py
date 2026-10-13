# SPDX-License-Identifier: Apache-2.0
"""V4 F1: reallocate idle V3.1 fertilizer-hand work to profitable WHEAT.

This lane does not hire a hand, buy fertilizer, change seed/land orders, or alter
tile occupancy.  It runs only after the shipped ``r04_fert_hand`` wrapper has
already produced the parent action.  If that existing extra hand is otherwise
PASSing while holding fertilizer, and no current or authored-later CARROT target
still reserves that fertilizer, F1 may send the hand to a WHEAT tile whose
fertilized yield window has positive value after the public fertilizer
opportunity cost.

The key ships off as ``r04_fert_mix``.  Every ambiguous state fails closed to
the exact parent action object.
"""
from __future__ import annotations

KEY = "r04_fert_mix"
PRICE_KEEP = 0.8
GAIN_RATIO = 1.2
MIN_EDGE = 25.0
REPORT = {
    "engaged": 0,
    "fertilized_wheat": 0,
    "moves_to_wheat": 0,
    "declined_carrot_reserve": 0,
    "declined_no_fertilizer": 0,
    "declined_no_roi": 0,
}


def _plain_nonnegative_int(value):
    return type(value) is int and value >= 0


def _wheat_gain(tile, day):
    """Extra WHEAT units from fertilizing today, matching pinned engine math."""
    if not isinstance(tile, dict) or tile.get("kind") != "PLANT" or tile.get("crop") != "WHEAT":
        return 0
    try:
        planted = tile.get("planted_day")
        covered = tile.get("fertilized_until_day", -1)
        have = tile.get("yield_units", 0)
        watered = tile.get("watered_today", False)
        if not (_plain_nonnegative_int(planted)
                and type(covered) is int
                and _plain_nonnegative_int(have)
                and type(watered) is bool):
            return 0
        first, last, cap = 2, 4, 6
        start = planted + (last + 1) // 2
        end = planted + last
        waters = [w for w in range(start, min(end, 29) + 1)
                  if w > day or (w == day and not watered)]
        if not waters:
            return 0
        base = min(cap, have + sum(2 if w <= covered else 1 for w in waters))
        cover = max(covered, day + 2)
        fertilized = min(cap, have + sum(2 if w <= cover else 1 for w in waters))
        return max(0, fertilized - base)
    except Exception:
        return 0


def _reserved_for_carrots(observation, tape, step, day):
    """True unless the shipped hand has no remaining CARROT obligation today."""
    try:
        import r04_fert_hand as fert
        if not isinstance(observation, dict):
            return True
        player = observation.get("player")
        if type(player) is not int:
            return True
        farm = observation["farms"][player]
        if fert._targets(farm["tiles"], day):
            return True
        if tape is None:
            return True
        return fert._future_plantings(tape, step) > 0
    except Exception:
        return True


def _prices(observation):
    try:
        prices = observation["market"]["prices"]
        wheat = prices.get("WHEAT")
        fertilizer = prices.get("FERTILIZER")
        if not _plain_nonnegative_int(wheat):
            return None
        if not _plain_nonnegative_int(fertilizer):
            return None
        return wheat, fertilizer
    except Exception:
        return None


def _targets(observation, position):
    """Positive-ROI reachable WHEAT targets as (distance, -gain, y, x, gain)."""
    try:
        if not isinstance(observation, dict):
            return []
        player = observation.get("player")
        step = observation.get("step")
        if type(player) is not int or type(step) is not int:
            return []
        day, hour = divmod(step, 24)
        farm = observation["farms"][player]
        tiles = farm["tiles"]
    except Exception:
        return []
    prices = _prices(observation)
    if prices is None:
        return []
    wheat_price, fertilizer_price = prices
    out = []
    px, py = position
    max_distance = 23 - hour
    if max_distance < 0:
        return []
    for y, row in enumerate(tiles):
        if not isinstance(row, list):
            return []
        for x, tile in enumerate(row):
            gain = _wheat_gain(tile, day)
            if gain <= 0:
                continue
            value = gain * wheat_price * PRICE_KEEP
            if value - fertilizer_price < MIN_EDGE or value < GAIN_RATIO * fertilizer_price:
                continue
            distance = abs(x - px) + abs(y - py)
            if distance <= max_distance:
                out.append((distance, -gain, y, x, gain))
    return out


def apply_fert_mix(observation, action, enabled=False):
    if not enabled:
        return action
    if not isinstance(observation, dict):
        return action
    if type(observation.get("player")) is not int or type(observation.get("step")) is not int:
        return action
    try:
        import r04_fert_hand as fert
        import r04_full_router as r04
        if not fert.FERT_HAND:
            return action
        player = observation["player"]
        step = observation["step"]
        day = step // 24
        if day not in fert.DAYS or not isinstance(action, dict):
            return action
        st = fert._STATE.get(player)
        if st is None or st.index is None or type(st.index) is not int or st.index < 0:
            return action
        hands = action.get("hands")
        farm = observation["farms"][player]
        if not isinstance(hands, list) or st.index >= len(hands):
            return action
        if st.index >= len(farm.get("hands") or []):
            return action
        command = hands[st.index]
        if command != ["PASS"]:
            return action

        inventories = observation["private"]["inventories"]
        inv_index = st.index + 1
        if inv_index >= len(inventories) or not isinstance(inventories[inv_index], dict):
            return action
        held = inventories[inv_index].get("FERTILIZER", 0)
        if not _plain_nonnegative_int(held) or held <= 0:
            REPORT["declined_no_fertilizer"] += 1
            return action

        try:
            tape = r04._policy_tape(observation)
        except Exception:
            return action
        if _reserved_for_carrots(observation, tape, step, day):
            REPORT["declined_carrot_reserve"] += 1
            return action

        position = farm["hands"][st.index]
        if (not isinstance(position, (list, tuple)) or len(position) != 2
                or type(position[0]) is not int or type(position[1]) is not int):
            return action
        wheat_targets = _targets(observation, (position[0], position[1]))
        if not wheat_targets:
            REPORT["declined_no_roi"] += 1
            return action
        _, _, ty, tx, _ = min(wheat_targets)
        REPORT["engaged"] += 1

        out = dict(action)
        out_hands = list(hands)
        if (position[0], position[1]) == (tx, ty):
            out_hands[st.index] = ["FERTILIZE"]
            REPORT["fertilized_wheat"] += 1
        else:
            board = len(farm["tiles"])
            sheds = fert._shed_tiles(board)
            out_hands[st.index] = fert._step_toward(
                (position[0], position[1]), (tx, ty), sheds)
            REPORT["moves_to_wheat"] += 1
        out["hands"] = out_hands
        return out
    except Exception:
        return action
