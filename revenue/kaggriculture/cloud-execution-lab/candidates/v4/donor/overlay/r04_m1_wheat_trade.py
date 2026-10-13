# SPDX-License-Identifier: Apache-2.0
"""V4 M1: pre-buy a bounded, already-authored WHEAT pickup under public scarcity.

This lane does not create feed work, animals, hands, land, seeds, or sales. V226
already owns the one-turn WHEAT shortage case. M1 only considers a literal
same-day pickup in the frozen route tape two to six steps ahead, and only while
public market inventory is moving down. The key ships off; economics are gated
separately under docs/V4.md.
"""
from __future__ import annotations

import copy
import math

MAX_ORDERS = 10
SHED_CAPACITY = 100
LOOKAHEAD_MIN = 2
LOOKAHEAD_MAX = 6
MAX_BUY = 4
MAX_DAILY_BUY = 8
CASH_RESERVE = 1000
# Standard-config proof: before M1's executable row, lockstep opponent activity
# can displace WHEAT market inventory by at most 507 units. Across that bounded
# displacement the rounded standard WHEAT curve can rise by at most $25/unit.
SAME_TURN_WHEAT_SURCHARGE = 25
_PURCHASE_OPS = {"HIRE", "BUY_LAND", "BUY_PRODUCT", "BUY_ANIMAL", "BUY_SEED"}
_SHED_INFLOW_OPS = {"DROP", "PLACE"}
_MOVES = {
    "NORTH": (0, -1),
    "SOUTH": (0, 1),
    "EAST": (1, 0),
    "WEST": (-1, 0),
}
_STANDARD_CONFIG = {
    "episodeSteps": 720,
    "turnsPerDay": 24,
    "boardSize": 10,
    "shedCapacity": 100,
    "maxMarketOrdersPerTurn": 10,
}
_MISSING = object()

_STATE = {}
REPORT = {
    "calls": 0,
    "scarcity_steps": 0,
    "future_pickups": 0,
    "buy_orders": 0,
    "buy_units": 0,
    "funding_vetoes": 0,
    "capacity_vetoes": 0,
    "schedule_vetoes": 0,
}


def reset_for_tests():
    _STATE.clear()
    for key in REPORT:
        REPORT[key] = 0


def _plain_nonnegative_int(value):
    return type(value) is int and value >= 0


def _plain_nonnegative_money(value):
    """Engine money is numeric; reject non-finite/overflowing poison safely."""
    if type(value) not in (int, float) or value < 0:
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def _cfg(configuration, name):
    if configuration is None:
        return _MISSING
    try:
        if isinstance(configuration, dict):
            return configuration.get(name, _MISSING)
        return getattr(configuration, name, _MISSING)
    except Exception:
        return _MISSING


def _standard_configuration(configuration):
    for name, expected in _STANDARD_CONFIG.items():
        actual = _cfg(configuration, name)
        if actual is _MISSING or type(actual) is not int or actual != expected:
            return False
    market_params = _cfg(configuration, "marketParams")
    return (market_params is _MISSING or market_params is None
            or (isinstance(market_params, dict) and not market_params))


def _commands(planned):
    if not isinstance(planned, dict):
        return None
    farmer = planned.get("farmer", _MISSING)
    hands = planned.get("hands", _MISSING)
    if (not isinstance(farmer, list) or not farmer
            or not isinstance(hands, list)
            or any(not isinstance(command, list) or not command for command in hands)):
        return None
    return [farmer, *hands]


def _market_rows(planned):
    if not isinstance(planned, dict):
        return None
    rows = planned.get("market", _MISSING)
    if not isinstance(rows, list) or any(row and not isinstance(row, list) for row in rows):
        return None
    return rows


def _executable_market_rows(planned):
    """Return only the official executable market prefix.

    The interpreter ignores rows after ``maxMarketOrdersPerTurn``. Those dead
    suffix carriers therefore cannot own cash or WHEAT and must not veto M1.
    Validation is likewise limited to the executable prefix.
    """
    if not isinstance(planned, dict):
        return None
    rows = planned.get("market", _MISSING)
    if not isinstance(rows, list):
        return None
    prefix = rows[:MAX_ORDERS]
    if any(row and not isinstance(row, list) for row in prefix):
        return None
    return prefix


def _parent_requests_wheat_buy(rows):
    """Whether the parent's executable raw prefix can lower public WHEAT stock.

    Quantity/fill exactness is deliberately not needed here. Any authored
    BUY_PRODUCT WHEAT in the official ten-row prefix makes the following public
    inventory transition causally ambiguous, so M1 suppresses that transition
    rather than letting another shipped controller self-certify scarcity.
    """
    if not isinstance(rows, list):
        return False
    return any(
        len(row) >= 2 and row[0] == "BUY_PRODUCT" and row[1] == "WHEAT"
        for row in rows[:MAX_ORDERS]
        if isinstance(row, list) and row
    )


def _normal_position(value, board_size):
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or type(value[0]) is not int or type(value[1]) is not int):
        return None
    x, y = value
    if not (0 <= x < board_size and 0 <= y < board_size):
        return None
    return [x, y]


def _advance_positions(positions, commands, board_size):
    """Replay exactly the official bounded literal movement semantics."""
    if not isinstance(commands, list) or len(commands) != len(positions):
        return None
    out = [list(position) for position in positions]
    for actor, command in enumerate(commands):
        if not isinstance(command, list) or not command or not isinstance(command[0], str):
            return None
        move = _MOVES.get(command[0])
        if move is None:
            continue
        x, y = out[actor]
        nx, ny = x + move[0], y + move[1]
        if 0 <= nx < board_size and 0 <= ny < board_size:
            out[actor] = [nx, ny]
    return out


def _shed_tiles(board_size):
    half = board_size // 2
    return {
        (half - 1, half - 1),
        (half, half - 1),
        (half - 1, half),
        (half, half),
    }


def _future_literal_pickup(tape, step, actor_positions, current_commands, board_size):
    """Return a funded same-day pickup executable by a current live actor.

    Besides actor cardinality, this certificate replays the already-selected
    current literal movement and subsequent bounded literal movement from live
    positions, then requires each counted WHEAT pickup to stand on a shed-access
    tile at execution. HIRE is vetoed in every active future market prefix, so
    the actor set must remain exact through the due step. Dead market suffix rows
    are intentionally ignored because the official interpreter never executes
    them. Hour-23 pickups remain fail-closed because EOD immediately resets the
    actor/inventory path they would otherwise certify.
    """
    if type(board_size) is not int or board_size < 2:
        return None, 0
    if not isinstance(actor_positions, list) or not actor_positions:
        return None, 0
    positions = []
    for value in actor_positions:
        position = _normal_position(value, board_size)
        if position is None:
            return None, 0
        positions.append(position)
    positions = _advance_positions(positions, current_commands, board_size)
    if positions is None:
        return None, 0
    if not isinstance(tape, (list, tuple)) or len(tape) <= step + LOOKAHEAD_MIN:
        return None, 0

    # Funding custody extends through the rest of this day.  A truncated frozen
    # tape cannot prove that omitted same-day steps contain no HIRE/BUY cash owner.
    expected_day_end = (step // 24 + 1) * 24 - 1
    if len(tape) <= expected_day_end:
        return None, 0
    day_end = expected_day_end
    candidate_end = min(day_end, step + LOOKAHEAD_MAX)
    candidate_due = None
    candidate_demand = 0
    shed_tiles = _shed_tiles(board_size)

    for due in range(step + 1, candidate_end + 1):
        planned = tape[due]
        if not isinstance(planned, dict):
            return None, 0
        rows = _executable_market_rows(planned)
        commands = _commands(planned)
        if rows is None or commands is None or len(commands) != len(positions):
            return None, 0
        for command in commands:
            if not isinstance(command[0], str):
                return None, 0
            if command[0] in _SHED_INFLOW_OPS:
                return None, 0
            if (due < step + LOOKAHEAD_MIN and len(command) >= 2
                    and command[:2] == ["PICKUP", "WHEAT"]):
                # A one-turn WHEAT pickup is V226 territory and also mutates the
                # shed stock used by a later M1 shortage calculation.
                return None, 0
        for row in rows:
            if not row:
                continue
            if not isinstance(row[0], str):
                return None, 0
            if row[0] in _PURCHASE_OPS:
                return None, 0
            if len(row) > 1 and row[1] == "WHEAT":
                return None, 0
        if due < step + LOOKAHEAD_MIN:
            positions = _advance_positions(positions, commands, board_size)
            if positions is None:
                return None, 0
            continue

        demand = 0
        for actor, command in enumerate(commands):
            if len(command) >= 2 and command[:2] == ["PICKUP", "WHEAT"]:
                quantity = command[2] if len(command) >= 3 else 1
                if not _plain_nonnegative_int(quantity):
                    return None, 0
                if quantity > 0 and tuple(positions[actor]) not in shed_tiles:
                    return None, 0
                demand += quantity
        if demand > 0:
            if due % 24 == 23:
                return None, 0
            candidate_due = due
            candidate_demand = demand
            break

        positions = _advance_positions(positions, commands, board_size)
        if positions is None:
            return None, 0

    if candidate_due is None:
        return None, 0

    # M1's market buy spends cash now. The certified pickup can occur before a
    # later same-day acquisition, so returning at the pickup would miss cash
    # ownership that baseline still has. Inspect only the official executable
    # market prefix after the pickup; next-day rows are outside this day's cash
    # contract and are intentionally not scanned.
    for due in range(candidate_due + 1, day_end + 1):
        planned = tape[due]
        if not isinstance(planned, dict):
            return None, 0
        rows = _executable_market_rows(planned)
        if rows is None:
            return None, 0
        for row in rows:
            if not row:
                continue
            if not isinstance(row[0], str):
                return None, 0
            if row[0] in _PURCHASE_OPS:
                return None, 0

    return candidate_due, candidate_demand


def _observe_scarcity(player, step, day, wheat_inventory):
    previous = _STATE.get(player)
    if previous is None or step <= previous["last"]:
        previous = {"last": step, "inventory": wheat_inventory, "day": day,
                    "bought_today": 0, "last_buy": -1000}
        _STATE[player] = previous
        return previous, False
    if day != previous["day"]:
        previous["day"] = day
        previous["bought_today"] = 0
    contiguous = previous["last"] == step - 1
    self_induced = previous["last_buy"] == step - 1
    scarcity = contiguous and not self_induced and wheat_inventory < previous["inventory"]
    previous["last"] = step
    previous["inventory"] = wheat_inventory
    return previous, scarcity


def apply_m1_wheat_trade(observation, action, tape, route_state=None,
                         configuration=None, enabled=False):
    """Return ``action`` or a copy with one bounded BUY_PRODUCT WHEAT row appended."""
    if not enabled:
        return action
    REPORT["calls"] += 1
    if not isinstance(observation, dict) or not isinstance(action, dict):
        return action
    if not _standard_configuration(configuration):
        return action
    step = observation.get("step")
    player = observation.get("player")
    if type(step) is not int or type(player) is not int or step < 24 or step >= 696:
        return action
    day = step // 24

    market_obs = observation.get("market")
    private = observation.get("private")
    farms = observation.get("farms")
    if (
        not isinstance(market_obs, dict)
        or not isinstance(private, dict)
        or not isinstance(farms, list)
        or len(farms) != 2
    ):
        return action
    if player not in (0, 1) or not isinstance(farms[player], dict):
        return action
    farm = farms[player]
    inventory = market_obs.get("inventory")
    prices = market_obs.get("prices")
    shed = private.get("shed")
    farm_hands = farm.get("hands")
    farmer_position = farm.get("farmer")
    if (not isinstance(inventory, dict) or not isinstance(prices, dict)
            or not isinstance(shed, dict) or not isinstance(farm_hands, list)):
        return action
    wheat_market = inventory.get("WHEAT")
    wheat_price = prices.get("WHEAT")
    if not _plain_nonnegative_int(wheat_market) or type(wheat_price) is not int or wheat_price < 1:
        return action

    # Record parent-system WHEAT demand even on callbacks where M1 itself will
    # return early. Otherwise a V226/V234 buy at this step can lower public
    # inventory and falsely certify scarcity for M1 on the next callback.
    rows = _market_rows(action)
    if rows is None:
        return action
    parent_wheat_buy = _parent_requests_wheat_buy(rows)

    tracker, scarcity = _observe_scarcity(player, step, day, wheat_market)
    if parent_wheat_buy:
        tracker["last_buy"] = step
    if not scarcity:
        return action
    REPORT["scarcity_steps"] += 1

    if route_state is not None:
        try:
            if any(queue for queue in route_state.queues.values()) or vars(route_state).get("v217_task"):
                REPORT["schedule_vetoes"] += 1
                return action
        except Exception:
            return action

    commands = _commands(action)
    if (commands is None or len(rows) >= MAX_ORDERS
            or len(commands) != len(farm_hands) + 1):
        return action
    if any(command and command[0] in ("DROP", "PLACE", "PICKUP") for command in commands):
        return action
    for row in rows:
        if not row:
            continue
        if not isinstance(row[0], str):
            return action
        if row[0] in _PURCHASE_OPS or (len(row) > 1 and row[1] == "WHEAT"):
            REPORT["funding_vetoes"] += 1
            return action

    actor_positions = [farmer_position, *farm_hands]
    due, demand = _future_literal_pickup(
        tape,
        step,
        actor_positions,
        commands,
        _cfg(configuration, "boardSize"),
    )
    if due is None:
        return action
    REPORT["future_pickups"] += 1

    if any(not _plain_nonnegative_int(value) for value in shed.values()):
        return action
    wheat_stock = shed.get("WHEAT", 0)
    if not _plain_nonnegative_int(wheat_stock):
        return action
    total_stock = sum(shed.values())
    shortage = max(0, demand - wheat_stock)
    daily_room = MAX_DAILY_BUY - tracker["bought_today"]
    quantity = min(shortage, MAX_BUY, daily_room)
    if quantity <= 0 or wheat_market < quantity:
        return action
    if total_stock + quantity > SHED_CAPACITY:
        REPORT["capacity_vetoes"] += 1
        return action

    money = farm.get("money")
    if not _plain_nonnegative_money(money):
        return action
    conservative_cost = quantity * (wheat_price + SAME_TURN_WHEAT_SURCHARGE)
    if money < CASH_RESERVE + conservative_cost:
        REPORT["funding_vetoes"] += 1
        return action

    out = copy.deepcopy(action)
    out["market"] = list(rows) + [["BUY_PRODUCT", "WHEAT", quantity]]
    tracker["bought_today"] += quantity
    tracker["last_buy"] = step
    REPORT["buy_orders"] += 1
    REPORT["buy_units"] += quantity
    return out