# SPDX-License-Identifier: Apache-2.0
"""V4 S6: bounded idle-capacity fertilizer work for the shipped fertilizer hand.

S6 never creates a hand.  The incumbent CARROT-only fert-hand must first pass
its unchanged hire gate.  S6 may then reserve at most one additional fertilizer
unit when that unit has a current, non-overlapping, positive-ROI WHEAT/TOMATO
use whose full pickup -> incumbent CARROT service -> S6 service route fits
before EOD from every possible shed spawn.  Future authored CARROT planting
reserves the entire hand for baseline and disables the extra reserve.

At execution time CARROT remains absolute priority.  Only after current and
same/later-callback CARROT obligations clear may the already-funded spare unit
be spent on reachable WHEAT or guaranteed-watered TOMATO work.  Frozen V219's
scheduled TOMATO fertilizer gate is excluded so S6 never races that parent
worker for the same pre-action TOMATO state.
"""
from __future__ import annotations

from typing import Any

TURNS_PER_DAY = 24
EPISODE_STEPS = 720
BOARD_SIZE = 10
SHED_CAPACITY = 100
MAX_MARKET_ORDERS_PER_TURN = 10
FARM_HAND_COST_MULT = 1
FINAL_ACTION_DAY = (EPISODE_STEPS - 2) // TURNS_PER_DAY
FERT_HAND_DAYS = (24, 25, 26, 27, 28)
S6_EXTRA_FERT_CAP = 1
ANNUAL = {
    "WHEAT": (2, 4, 6),
    "CARROT": (2, 3, 4),
}
TOMATO_FIRST_YIELD_DAY = 8
TOMATO_INTERVAL = 1
TOMATO_MAX_YIELD = 4
V219_FERTILIZER_DAYS = (24, 27)
V219_FERTILIZER_MAX_PRICE = 30

REPORT = {
    "choices": 0,
    "fertilize_requests": 0,
    "reserve_requests": 0,
    "choice_by_crop": {"WHEAT": 0, "CARROT": 0, "TOMATO": 0},
}


def _plain_int(value: Any, *, minimum: int | None = None) -> bool:
    return type(value) is int and (minimum is None or value >= minimum)


def _config_value(configuration: Any, name: str, missing: Any):
    if isinstance(configuration, dict):
        return configuration.get(name, missing)
    return getattr(configuration, name, missing)


def standard_configuration(configuration: Any) -> bool:
    """Accept only the semantic engine configuration S6's proof models."""
    if configuration is None:
        return False
    missing = object()
    expected_ints = {
        "episodeSteps": EPISODE_STEPS,
        "turnsPerDay": TURNS_PER_DAY,
        "boardSize": BOARD_SIZE,
        "shedCapacity": SHED_CAPACITY,
        "maxMarketOrdersPerTurn": MAX_MARKET_ORDERS_PER_TURN,
        "farmHandCostMult": FARM_HAND_COST_MULT,
    }
    try:
        for name, value in expected_ints.items():
            actual = _config_value(configuration, name, missing)
            if type(actual) is not int or actual != value:
                return False
        market_params = _config_value(configuration, "marketParams", None)
    except (KeyError, TypeError, AttributeError):
        return False
    if market_params is None:
        return True
    return isinstance(market_params, dict) and not market_params


def _annual_gain(
    tile: dict[str, Any], day: int, crop: str, *, clip_to_episode: bool,
) -> int | None:
    first, last, cap = ANNUAL[crop]
    planted = tile.get("planted_day")
    covered = tile.get("fertilized_until_day")
    have = tile.get("yield_units")
    watered = tile.get("watered_today")
    if (
        not _plain_int(planted, minimum=0)
        or not _plain_int(covered)
        or not _plain_int(have, minimum=0)
        or have > cap
        or type(watered) is not bool
    ):
        return None
    start = planted + (last + 1) // 2
    end = planted + last
    waters = [
        w for w in range(start, end + 1)
        if (not clip_to_episode or w <= FINAL_ACTION_DAY)
        and (w > day or (w == day and not watered))
    ]
    if not waters:
        return 0
    base = min(cap, have + sum(2 if w <= covered else 1 for w in waters))
    cover = max(covered, day + 2)
    fertilized = min(cap, have + sum(2 if w <= cover else 1 for w in waters))
    return max(0, fertilized - base)


def _tomato_gain(tile: dict[str, Any], day: int) -> int | None:
    planted = tile.get("planted_day")
    covered = tile.get("fertilized_until_day")
    have = tile.get("yield_units")
    watered = tile.get("watered_today")
    if (
        not _plain_int(planted, minimum=0)
        or not _plain_int(covered)
        or not _plain_int(have, minimum=0)
        or have > TOMATO_MAX_YIELD
        or type(watered) is not bool
    ):
        return None
    if not watered or covered >= day or have > TOMATO_MAX_YIELD - 2:
        return 0
    next_day = day + 1
    days_since_first = next_day - planted - TOMATO_FIRST_YIELD_DAY
    if days_since_first < 0 or days_since_first % TOMATO_INTERVAL:
        return 0
    production_count = days_since_first // TOMATO_INTERVAL + 1
    if not (1 <= production_count <= TOMATO_MAX_YIELD):
        return 0
    return 1


def _state(observation: Any):
    if not isinstance(observation, dict):
        return None
    step = observation.get("step")
    player = observation.get("player")
    farms = observation.get("farms")
    market = observation.get("market")
    if (
        not _plain_int(step, minimum=0)
        or type(player) is not int
        or not isinstance(farms, list)
        or not (0 <= player < len(farms))
        or not isinstance(market, dict)
    ):
        return None
    farm = farms[player]
    prices = market.get("prices")
    if not isinstance(farm, dict) or not isinstance(prices, dict):
        return None
    tiles = farm.get("tiles")
    if (
        not isinstance(tiles, list)
        or len(tiles) != BOARD_SIZE
        or any(not isinstance(row, list) or len(row) != BOARD_SIZE for row in tiles)
    ):
        return None
    for product in ("WHEAT", "CARROT", "TOMATO", "FERTILIZER"):
        if not _plain_int(prices.get(product), minimum=0):
            return None
    return step // TURNS_PER_DAY, tiles, prices


def _current_targets(observation: Any):
    parsed = _state(observation)
    if parsed is None:
        return None
    day, tiles, prices = parsed
    v219_tomato_service = (
        day in V219_FERTILIZER_DAYS
        and prices["FERTILIZER"] <= V219_FERTILIZER_MAX_PRICE
    )
    targets = []
    for y, row in enumerate(tiles):
        for x, tile in enumerate(row):
            if not isinstance(tile, dict) or tile.get("kind") != "PLANT":
                continue
            crop = tile.get("crop")
            if crop == "CARROT":
                gain = _annual_gain(tile, day, crop, clip_to_episode=False)
                if gain is None:
                    return None
                if gain > 0:
                    targets.append((x, y, crop, gain, gain * prices[crop]))
                continue
            if crop == "WHEAT":
                gain = _annual_gain(tile, day, crop, clip_to_episode=True)
            elif crop == "TOMATO":
                if v219_tomato_service:
                    continue
                gain = _tomato_gain(tile, day)
            else:
                continue
            if gain is None:
                return None
            if gain <= 0:
                continue
            value = gain * prices[crop]
            if value > 0:
                targets.append((x, y, crop, gain, value))
    return targets


def _shed_tiles():
    half = BOARD_SIZE // 2
    return {(half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half)}


def _leave_shed_position(pos, sheds):
    x, y = pos
    for dx, dy in ((0, -1), (-1, 0), (0, 1), (1, 0)):
        nxt = (x + dx, y + dy)
        if 0 <= nxt[0] < BOARD_SIZE and 0 <= nxt[1] < BOARD_SIZE and nxt not in sheds:
            return nxt
    return None


def _step_position(pos, target, sheds):
    x, y = pos
    tx, ty = target
    options = []
    if tx > x:
        options.append((x + 1, y))
    if tx < x:
        options.append((x - 1, y))
    if ty > y:
        options.append((x, y + 1))
    if ty < y:
        options.append((x, y - 1))
    if not options:
        return pos
    options.sort(key=lambda nxt: nxt in sheds)
    return options[0]


def _route_callbacks(start, baseline_targets, extension):
    """Exact static callback model of pickup + incumbent routing + one extension."""
    sheds = _shed_tiles()
    pos = start
    remaining = [tuple(target) for target in baseline_targets]
    callbacks = 1
    for _ in range(128):
        if remaining:
            if pos in sheds:
                pos = _leave_shed_position(pos, sheds)
                if pos is None:
                    return None
                callbacks += 1
                continue
            at_pos = next((i for i, t in enumerate(remaining) if (t[0], t[1]) == pos), None)
            if at_pos is not None:
                remaining.pop(at_pos)
                callbacks += 1
                continue
            goal = min(
                remaining,
                key=lambda t: (
                    abs(t[0] - pos[0]) + abs(t[1] - pos[1]),
                    -t[2], t[1], t[0],
                ),
            )
            nxt = _step_position(pos, (goal[0], goal[1]), sheds)
            if nxt == pos:
                return None
            pos = nxt
            callbacks += 1
            continue

        target_pos = (extension[0], extension[1])
        if pos in sheds:
            pos = _leave_shed_position(pos, sheds)
            if pos is None:
                return None
            callbacks += 1
            continue
        if pos == target_pos:
            return callbacks + 1
        nxt = _step_position(pos, target_pos, sheds)
        if nxt == pos:
            return None
        pos = nxt
        callbacks += 1
    return None


def reserve_extra_fertilizer(
    observation: Any,
    baseline_targets: Any,
    baseline_units: Any,
    future_carrots: Any,
    reach_limit: Any,
) -> int:
    """Return 0/1 extra units; called only after the baseline hire gate passed."""
    parsed = _state(observation)
    if parsed is None:
        return 0
    day, _, prices = parsed
    if day not in FERT_HAND_DAYS:
        return 0
    if (
        not _plain_int(baseline_units, minimum=1)
        or not _plain_int(future_carrots, minimum=0)
        or future_carrots != 0
        or not _plain_int(reach_limit, minimum=1)
        or baseline_units >= reach_limit
        or not isinstance(baseline_targets, list)
        or len(baseline_targets) != baseline_units
    ):
        return 0
    carrots = []
    for target in baseline_targets:
        if (
            not isinstance(target, (tuple, list))
            or len(target) != 3
            or not _plain_int(target[0], minimum=0)
            or not _plain_int(target[1], minimum=0)
            or target[0] >= BOARD_SIZE
            or target[1] >= BOARD_SIZE
            or not _plain_int(target[2], minimum=1)
        ):
            return 0
        carrots.append((target[0], target[1], target[2]))

    targets = _current_targets(observation)
    if targets is None:
        return 0
    sheds = _shed_tiles()
    candidates = [
        target for target in targets
        if target[2] != "CARROT"
        and (target[0], target[1]) not in sheds
        and target[4] > prices["FERTILIZER"]
    ]
    if not candidates:
        return 0

    step = observation["step"]
    callbacks_after_hire = TURNS_PER_DAY - ((step % TURNS_PER_DAY) + 1)
    if callbacks_after_hire <= 0:
        return 0
    for candidate in candidates:
        route_lengths = [_route_callbacks(spawn, carrots, candidate) for spawn in sorted(sheds)]
        if all(length is not None and length <= callbacks_after_hire for length in route_lengths):
            REPORT["reserve_requests"] += 1
            return S6_EXTRA_FERT_CAP
    return 0


def choose_fert_hand_target(observation: Any, pos: Any, upcoming=()):
    parsed = _state(observation)
    if parsed is None or not isinstance(pos, tuple) or len(pos) != 2:
        return None
    if (
        type(pos[0]) is not int
        or type(pos[1]) is not int
        or not (0 <= pos[0] < BOARD_SIZE)
        or not (0 <= pos[1] < BOARD_SIZE)
    ):
        return None
    day, _, _ = parsed
    targets = _current_targets(observation)
    if targets is None:
        return None
    if any(target[2] == "CARROT" for target in targets):
        return None
    try:
        for item in upcoming or ():
            if not isinstance(item, (tuple, list)) or len(item) < 2:
                return None
            x, y = item[0], item[1]
            gain = item[2] if len(item) >= 3 else 1
            if (
                not _plain_int(x, minimum=0)
                or not _plain_int(y, minimum=0)
                or x >= BOARD_SIZE
                or y >= BOARD_SIZE
                or not _plain_int(gain, minimum=0)
            ):
                return None
            if gain > 0:
                return None
    except Exception:
        return None

    px, py = pos
    turns_left = TURNS_PER_DAY - (observation["step"] % TURNS_PER_DAY)
    targets = [
        target for target in targets
        if target[2] != "CARROT"
        and abs(px - target[0]) + abs(py - target[1]) + 1 <= turns_left
    ]
    if not targets:
        return None

    def key(target):
        x, y, crop, gain, value = target
        distance = abs(px - x) + abs(py - y)
        return (value / float(distance + 1), value, -distance, gain, -y, -x, crop)

    x, y, crop, gain, value = max(targets, key=key)
    distance = abs(px - x) + abs(py - y)
    REPORT["choices"] += 1
    REPORT["choice_by_crop"][crop] += 1
    return {
        "position": (x, y),
        "crop": crop,
        "marginal_units": gain,
        "marginal_value": value,
        "distance": distance,
        "day": day,
    }


def record_fertilize(target: Any) -> None:
    if isinstance(target, dict) and target.get("crop") in REPORT["choice_by_crop"]:
        REPORT["fertilize_requests"] += 1
