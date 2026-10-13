# SPDX-License-Identifier: Apache-2.0
"""V4 S1: one bounded late-day hand that sweeps expiring animal fertilizer.

The pinned engine stores animal fertilizer as a boolean.  Every end-of-day refresh
sets ``fertilizer_available = True``; if a previous unit was never collected, that
older opportunity is overwritten rather than accumulated.  This lane hires one
extra hand after the parent's final authored HIRE of the day and uses it only for
COLLECT_FERTILIZER on already-available animals.  The parent is kept blind to the
extra hand with the same observation/action re-indexing pattern as r04_fert_hand.

The lane is deliberately narrow:
- days 4..23 only (no overlap with the shipped endgame fert hand or V218);
- standard 720/24/10/100/10 field with farm-hand cost multiplier 1 only;
- no current HIRE, purchase, or COLLECT_FERTILIZER row;
- no authored future cash-spending/ambiguous market row or COLLECT_FERTILIZER for the rest of the day;
- no remaining-day authored WHEAT pickup that can make V226 spend cash later;
- SE targets are excluded so V233's dedicated sheep workers keep ownership;
- a worst-case shed-corner start must reach enough collections before EOD;
- quoted fertilizer value must conservatively clear the Fibonacci hire cost.

S1 never buys/sells anything, changes no crop/animal/land decision, and never feeds,
cares, harvests, or moves a parent unit.  At EOD the engine automatically drops the
extra hand's carried fertilizer and then refreshes surviving animals' availability,
so collection does not consume the following day's fertilizer opportunity.
"""
from __future__ import annotations

import copy
import math
from typing import Any

KEY = "r04_s1_fert_sweep"
DAYS = tuple(range(4, 24))
MIN_HOUR = 14
TURNS_PER_DAY = 24
BOARD_SIZE = 10
SHED_CAPACITY = 100
MAX_ORDERS = 10
REACH = 6
PRICE_KEEP = 0.80
MIN_GAIN = 100.0
GAIN_RATIO = 1.20
CASH_RESERVE = 100.0
# F2 proves its causal WHEAT pre-buy while retaining this much cash.
# When F2 is enabled, S1 must not spend below that already-proved floor.
F2_COMPAT_CASH_RESERVE = 1000.0
HEADROOM_RESERVE = 12
MOVES = {
    "EAST": (1, 0),
    "WEST": (-1, 0),
    "NORTH": (0, -1),
    "SOUTH": (0, 1),
}

_STATE = {}
REPORT = {
    "hires": 0,
    "hire_failures": 0,
    "collections": 0,
    "declines": 0,
    "value_declines": 0,
    "capacity_declines": 0,
}


class _Day:
    def __init__(self, day: int):
        self.day = day
        self.pending = None
        self.index = None
        self.tried = False
        self.last_step = -1


def _plain_int(value: Any, *, minimum: int | None = None) -> bool:
    return type(value) is int and (minimum is None or value >= minimum)


def _money(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        value = float(value)
    except (OverflowError, ValueError):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return value


def _effective_cash_reserve() -> float:
    """Return S1's live cash floor without importing F2 private state.

    Missing/literal-False FEED_PREBUY preserves standalone S1's 100-unit
    reserve. Literal True protects F2's public 1000-unit composition
    covenant. A malformed flag fails closed to the stronger floor.
    """
    try:
        import r04_full_router as r04
        enabled = getattr(r04, "FEED_PREBUY", False)
    except Exception:
        return F2_COMPAT_CASH_RESERVE
    if enabled is False:
        return CASH_RESERVE
    return F2_COMPAT_CASH_RESERVE


def standard_configuration(configuration: Any) -> bool:
    if configuration is None:
        return False
    expected = {
        "episodeSteps": 720,
        "turnsPerDay": TURNS_PER_DAY,
        "boardSize": BOARD_SIZE,
        "shedCapacity": SHED_CAPACITY,
        "maxMarketOrdersPerTurn": MAX_ORDERS,
        "farmHandCostMult": 1,
    }
    try:
        for name, wanted in expected.items():
            actual = configuration.get(name) if isinstance(configuration, dict) else getattr(configuration, name)
            if type(actual) is not int or actual != wanted:
                return False
        params = configuration.get("marketParams") if isinstance(configuration, dict) else getattr(configuration, "marketParams", None)
    except (KeyError, TypeError, AttributeError):
        return False
    return params is None or (isinstance(params, dict) and not params)


def _fib(n: int) -> int:
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def _shed_tiles(board: int):
    half = board // 2
    return ((half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half))


def _rest_of_day(tape: Any, step: int):
    if not isinstance(tape, list) or not _plain_int(step, minimum=0):
        return None
    end = (step // TURNS_PER_DAY + 1) * TURNS_PER_DAY
    # Missing future evidence is not proof that parent cash is unclaimed.
    # Only this day must be complete; later episode days are irrelevant here.
    if end > len(tape):
        return None
    return tape[step + 1:end]


def _future_conflict(tape: Any, step: int) -> bool:
    remaining = _rest_of_day(tape, step)
    if remaining is None:
        return True
    try:
        for action in remaining:
            if not isinstance(action, dict):
                return True
            market = action.get("market", [])
            hands = action.get("hands", [])
            if not isinstance(market, list) or not isinstance(hands, list):
                return True
            # S1 appends a real HIRE now, so it must not consume cash needed by a
            # later authored market obligation.  SELL and empty rows cannot spend
            # our private cash; every other/unknown market opcode fails closed.
            for order in market:
                if not isinstance(order, list):
                    return True
                if not order:
                    continue
                if not isinstance(order[0], str) or order[0] != "SELL":
                    return True
            commands = [action.get("farmer")] + hands
            for command in commands:
                if command is None:
                    continue
                if not isinstance(command, list):
                    return True
                if command and command[0] == "COLLECT_FERTILIZER":
                    return True
    except Exception:
        return True
    return False


def _future_wheat_topup_risk(tape: Any, step: int, farm: dict) -> bool:
    """Fail closed if S1's HIRE cash can suppress authored V226 demand.

    V226 may append BUY_PRODUCT WHEAT one callback before a scheduled authored
    WHEAT pickup. S1 cannot safely hide the HIRE's real cash debit from the
    engine, so any remaining-day authored WHEAT pickup stays parent-owned.
    """
    remaining = _rest_of_day(tape, step)
    if remaining is None:
        return True
    try:
        for action in remaining:
            if not isinstance(action, dict):
                return True
            hands = action.get("hands", [])
            if not isinstance(hands, list):
                return True
            for command in [action.get("farmer"), *hands]:
                if command is None:
                    continue
                if not isinstance(command, list):
                    return True
                if len(command) >= 2 and command[:2] == ["PICKUP", "WHEAT"]:
                    return True
    except Exception:
        return True
    return False


def _farm(observation: Any):
    if not isinstance(observation, dict):
        return None
    step = observation.get("step")
    player = observation.get("player")
    farms = observation.get("farms")
    private = observation.get("private")
    market = observation.get("market")
    if (
        not _plain_int(step, minimum=0)
        or type(player) is not int
        or player not in (0, 1)
        or not isinstance(farms, list)
        or len(farms) != 2
        or not isinstance(private, dict)
        or not isinstance(market, dict)
    ):
        return None
    farm = farms[player]
    if not isinstance(farm, dict):
        return None
    hands = farm.get("hands")
    farmer = farm.get("farmer")
    tiles = farm.get("tiles")
    inventories = private.get("inventories")
    shed = private.get("shed")
    prices = market.get("prices")
    if (
        not isinstance(hands, list)
        or not isinstance(farmer, list)
        or len(farmer) != 2
        or not isinstance(tiles, list)
        or len(tiles) != BOARD_SIZE
        or not isinstance(inventories, list)
        or len(inventories) != len(hands) + 1
        or not isinstance(shed, dict)
        or not isinstance(prices, dict)
    ):
        return None
    for row in tiles:
        if not isinstance(row, list) or len(row) != BOARD_SIZE:
            return None
    for pos in [farmer] + hands:
        if (
            not isinstance(pos, list)
            or len(pos) != 2
            or not _plain_int(pos[0], minimum=0)
            or not _plain_int(pos[1], minimum=0)
            or pos[0] >= BOARD_SIZE
            or pos[1] >= BOARD_SIZE
        ):
            return None
    for inventory in inventories:
        if not isinstance(inventory, dict):
            return None
        for quantity in inventory.values():
            if not _plain_int(quantity, minimum=0):
                return None
    for quantity in shed.values():
        if not _plain_int(quantity, minimum=0):
            return None
    return step, player, farm, private, prices


def _targets(farm: dict):
    out = []
    for y, row in enumerate(farm["tiles"]):
        for x, tile in enumerate(row):
            if x >= BOARD_SIZE // 2 and y >= BOARD_SIZE // 2:
                continue
            if not isinstance(tile, dict) or tile.get("fertilizer_available") is not True:
                continue
            animal = tile.get("animal")
            kind = tile.get("kind")
            valid_animal_tile = (
                (animal == "GOOSE" and kind == "COOP")
                or (animal in ("COW", "SHEEP") and kind == "PASTURE")
            )
            if valid_animal_tile:
                out.append((x, y))
    return out


def _reachable_count(start, targets, callbacks: int) -> int:
    pos = tuple(start)
    remaining = list(targets)
    used = 0
    count = 0
    while remaining and count < REACH:
        target = min(
            remaining,
            key=lambda p: (abs(pos[0] - p[0]) + abs(pos[1] - p[1]), p[1], p[0]),
        )
        distance = abs(pos[0] - target[0]) + abs(pos[1] - target[1])
        cost = distance + 1
        if used + cost > callbacks:
            break
        used += cost
        count += 1
        pos = target
        remaining.remove(target)
    return count


def _current_collect(action: Any) -> bool:
    if not isinstance(action, dict):
        return True
    hands = action.get("hands", [])
    market = action.get("market", [])
    if not isinstance(hands, list) or not isinstance(market, list):
        return True
    commands = [action.get("farmer")] + hands
    for command in commands:
        if command is None:
            continue
        if not isinstance(command, list):
            return True
        if command and command[0] == "COLLECT_FERTILIZER":
            return True
    return False


def _safe_market(action: dict):
    market = action.get("market", [])
    if not isinstance(market, list) or len(market) >= MAX_ORDERS:
        return None
    copied = []
    for order in market:
        if not isinstance(order, list):
            return None
        if not order:
            copied.append([])
            continue
        if not isinstance(order[0], str):
            return None
        if order[0] == "HIRE":
            return None
        # Do not let a purchase consume cash ahead of our appended HIRE.  SELL,
        # empty rows, and unknown no-op rows do not decrease our private cash;
        # unknown rows fail closed because their engine semantics are ambiguous.
        if order[0] != "SELL":
            return None
        copied.append(list(order))
    return copied


def _inventory_total(private: dict):
    total = 0
    for quantity in private["shed"].values():
        total += quantity
    for inventory in private["inventories"]:
        for quantity in inventory.values():
            total += quantity
    return total


def _parent_view(observation: dict, index: int):
    obs = dict(observation)
    player = observation["player"]
    farms = list(observation["farms"])
    farm = dict(farms[player])
    hands = list(farm["hands"])
    del hands[index]
    farm["hands"] = hands
    farms[player] = farm
    obs["farms"] = farms

    private = dict(observation["private"])
    inventories = list(private["inventories"])
    if index + 1 >= len(inventories):
        raise IndexError("missing hidden-hand inventory")
    del inventories[index + 1]
    private["inventories"] = inventories
    obs["private"] = private
    return obs


def _step_toward(pos, target):
    x, y = pos
    tx, ty = target
    if x != tx:
        return ["EAST" if x < tx else "WEST"]
    if y != ty:
        return ["SOUTH" if y < ty else "NORTH"]
    return None


def _hand_command(observation: dict, st: _Day):
    parsed = _farm(observation)
    if parsed is None or st.index is None:
        return ["PASS"]
    step, _, farm, _, _ = parsed
    if st.index >= len(farm["hands"]):
        return ["PASS"]
    pos = tuple(farm["hands"][st.index])
    targets = _targets(farm)
    if not targets:
        return ["PASS"]
    callbacks = TURNS_PER_DAY - (step % TURNS_PER_DAY)
    reachable = []
    for target in targets:
        distance = abs(pos[0] - target[0]) + abs(pos[1] - target[1])
        if distance + 1 <= callbacks:
            reachable.append((distance, target[1], target[0], target))
    if not reachable:
        return ["PASS"]
    _, _, _, target = min(reachable)
    if target == pos:
        REPORT["collections"] += 1
        return ["COLLECT_FERTILIZER"]
    return _step_toward(pos, target) or ["PASS"]


def _consider_hire(observation: dict, action: Any, st: _Day, tape: Any, configuration: Any):
    if not standard_configuration(configuration) or _current_collect(action):
        return action
    parsed = _farm(observation)
    if parsed is None:
        return action
    step, _, farm, private, prices = parsed
    day, hour = divmod(step, TURNS_PER_DAY)
    if day not in DAYS or hour < MIN_HOUR or hour >= TURNS_PER_DAY - 1:
        return action
    market = _safe_market(action)
    if (
        market is None
        or _future_conflict(tape, step)
        or _future_wheat_topup_risk(tape, step, farm)
    ):
        return action

    targets = _targets(farm)
    if not targets:
        REPORT["declines"] += 1
        return action
    callbacks = (TURNS_PER_DAY - 1) - hour
    starts = _shed_tiles(BOARD_SIZE)
    reachable = min(_reachable_count(start, targets, callbacks) for start in starts)
    if reachable <= 0:
        REPORT["declines"] += 1
        return action

    hires_today = farm.get("hires_today")
    price = prices.get("FERTILIZER")
    money = _money(farm.get("money"))
    if (
        not _plain_int(hires_today, minimum=0)
        or hires_today > MAX_ORDERS * TURNS_PER_DAY
        or not _plain_int(price, minimum=1)
        or money is None
    ):
        return action
    units = min(reachable, REACH)
    cost = _fib(hires_today)
    try:
        quoted = units * price * PRICE_KEEP
    except (OverflowError, ValueError):
        return action
    if not math.isfinite(quoted):
        return action
    cash_reserve = _effective_cash_reserve()
    if quoted - cost < MIN_GAIN or quoted < GAIN_RATIO * cost or money < cost + cash_reserve:
        REPORT["value_declines"] += 1
        return action

    total = _inventory_total(private)
    if total + units > SHED_CAPACITY - HEADROOM_RESERVE:
        REPORT["capacity_declines"] += 1
        return action

    result = copy.deepcopy(action)
    result["market"] = market + [["HIRE"]]
    st.pending = len(farm["hands"])
    st.tried = True
    return result


def wrap(parent, tape_of=None):
    """Wrap ``parent`` with one hidden S1 worker while preserving parent indices."""

    def agent(observation, configuration=None):
        parsed = _farm(observation)
        if parsed is None or not standard_configuration(configuration):
            return parent(observation, configuration)
        step, player, farm, _, _ = parsed
        day = step // TURNS_PER_DAY
        st = _STATE.get(player)
        if st is None or st.day != day or step <= st.last_step:
            st = _STATE[player] = _Day(day)
        st.last_step = step

        hands = farm["hands"]
        if st.pending is not None:
            if len(hands) == st.pending + 1:
                st.index = st.pending
                REPORT["hires"] += 1
            else:
                REPORT["hire_failures"] += 1
            st.pending = None

        try:
            tape = tape_of(observation) if tape_of else None
        except Exception:
            tape = None

        if st.index is not None:
            if st.index >= len(hands):
                st.index = None
                return parent(observation, configuration)
            try:
                parent_observation = _parent_view(observation, st.index)
            except Exception:
                return parent(observation, configuration)
            action = parent(parent_observation, configuration)
            if not isinstance(action, dict):
                return action
            inner = action.get("hands")
            if (
                not isinstance(inner, list)
                or len(inner) != len(hands) - 1
                or any(not isinstance(item, list) for item in inner)
            ):
                return action
            try:
                command = _hand_command(observation, st)
            except Exception:
                command = ["PASS"]
            result = copy.deepcopy(action)
            inner = list(result["hands"])
            inner.insert(st.index, command)
            result["hands"] = inner
            return result

        action = parent(observation, configuration)
        if st.tried:
            return action
        try:
            return _consider_hire(observation, action, st, tape, configuration)
        except Exception:
            return action

    agent.telemetry = REPORT
    return agent