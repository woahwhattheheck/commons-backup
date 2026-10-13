# SPDX-License-Identifier: Apache-2.0
"""V4 W1: recover provably dead WATER turns into same-tile HARVEST.

W1 is intentionally narrow. On the actual day-28 hour-23 pre-EOD callback of
the standard game it may replace an authored same-tile ["WATER"] with
["HARVEST"] only when WATER is provably wasted, the standing plant is provably
harvestable, annual future yield is not sacrificed, actor geometry is exact,
and a whole-farm capacity upper bound proves that every unit which can be
carried after this turn still fits in the 100-unit shed at the immediately
following end of day. Final day (day 29 / step >= 696) is deliberately
excluded: there is no later EOD auto-drop, so harvest legality alone does not
prove that new cargo is ever delivered or monetized.

Unexpected or malformed state returns the exact parent action object.
"""
from __future__ import annotations

LATE_START = 672
LATE_END = 695

FIRST_YIELD_DAY = {
    "WHEAT": 2,
    "CARROT": 2,
    "TOMATO": 8,
    "STRAWBERRY": 10,
    "MELON": 10,
}

ONGOING_CROPS = {"TOMATO", "STRAWBERRY"}
ANNUAL_MAX_YIELD_DAY = {
    "WHEAT": 4,
    "CARROT": 3,
    "MELON": 12,
}

_STANDARD_CONFIGURATION = {
    "episodeSteps": 720,
    "turnsPerDay": 24,
    "boardSize": 10,
    "shedCapacity": 100,
}

_MARKET_SHED_INFLOW = {"BUY_PRODUCT", "BUY_ANIMAL"}
_MARKET_KNOWN_SAFE = {"SELL", "HIRE", "BUY_LAND", "BUY_SEED"}
_KNOWN_UNIT_OPS = {
    "PASS", "NORTH", "SOUTH", "EAST", "WEST",
    "WATER", "DIG", "FERTILIZE", "PLANT", "HARVEST",
    "PICKUP", "PLACE", "FEED", "CARE", "COLLECT_FERTILIZER",
    "BUILD_COOP", "BUILD_PASTURE",
}

_WATER = ["WATER"]
_HARVEST = ["HARVEST"]
_UNKNOWN = object()

report = {
    "steps_active": 0,
    "already_watered": 0,
    "expiring": 0,
    "not_harvestable": 0,
    "future_yield_block": 0,
    "capacity_block": 0,
    "terminal_day_block": 0,
    "recovered": 0,
}


def reset():
    for key in report:
        report[key] = 0


def get_report():
    return dict(report)


def _plain_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _cfg(configuration, key):
    try:
        if isinstance(configuration, dict):
            return configuration.get(key, _UNKNOWN)
        return getattr(configuration, key, _UNKNOWN)
    except Exception:
        return _UNKNOWN


def _standard_configuration(configuration):
    if configuration is None:
        return False
    for key, expected in _STANDARD_CONFIGURATION.items():
        value = _cfg(configuration, key)
        if not _plain_int(value) or value != expected:
            return False
    return True


def _position_key(position):
    try:
        if not isinstance(position, (list, tuple)) or len(position) != 2:
            return _UNKNOWN
        x, y = position
        if not _plain_int(x) or not _plain_int(y):
            return _UNKNOWN
        return (x, y)
    except Exception:
        return _UNKNOWN


def _valid_board(tiles):
    return (
        isinstance(tiles, list)
        and len(tiles) == 10
        and all(isinstance(row, list) and len(row) == 10 for row in tiles)
    )


def _worker_tile(tiles, position):
    key = _position_key(position)
    if key is _UNKNOWN:
        return _UNKNOWN
    x, y = key
    if not (0 <= x < 10 and 0 <= y < 10):
        return _UNKNOWN
    return tiles[y][x]


def _strict_inventory_total(mapping):
    if not isinstance(mapping, dict):
        return None
    total = 0
    for item, quantity in mapping.items():
        if not isinstance(item, str) or not _plain_int(quantity) or quantity < 0:
            return None
        total += quantity
    return total


def _wasted_water_reason(step, tile):
    try:
        if not (isinstance(tile, dict) and tile.get("kind") == "PLANT"):
            return None
        if tile.get("watered_today") is True:
            return "already_watered"
        max_lifespan_step = tile.get("max_lifespan_step")
        if (
            _plain_int(max_lifespan_step)
            and max_lifespan_step >= 0
            and max_lifespan_step <= step
        ):
            return "expiring"
    except Exception:
        return None
    return None


def _harvestable(tile, day):
    try:
        if not (isinstance(tile, dict) and tile.get("kind") == "PLANT"):
            return False
        crop = tile.get("crop")
        first_yield_day = FIRST_YIELD_DAY.get(crop)
        if first_yield_day is None:
            return False
        planted_day = tile.get("planted_day")
        yield_units = tile.get("yield_units")
        if not _plain_int(planted_day) or not _plain_int(yield_units):
            return False
        if yield_units <= 0:
            return False
        return day - planted_day >= first_yield_day
    except Exception:
        return False


def _harvest_preserves_future_yield(tile, day, reason):
    if reason == "expiring":
        return True
    try:
        crop = tile.get("crop")
        if crop in ONGOING_CROPS:
            return True
        max_yield_day = ANNUAL_MAX_YIELD_DAY.get(crop)
        planted_day = tile.get("planted_day")
        if max_yield_day is None or not _plain_int(planted_day):
            return False
        return day - planted_day >= max_yield_day
    except Exception:
        return False


def _tile_yield_upper_bound(tile):
    if not isinstance(tile, dict):
        return None
    units = tile.get("yield_units", 0)
    if not _plain_int(units) or units < 0:
        return None
    return units


def _market_preserves_capacity(action, configuration=None):
    market = action.get("market", _UNKNOWN)
    if not isinstance(market, list):
        return False
    products = {
        "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
        "EGG", "MILK", "WOOL", "FERTILIZER",
    }
    seeds = {"WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"}
    try:
        if isinstance(configuration, dict):
            cap = configuration.get("maxMarketOrdersPerTurn", 10)
        else:
            cap = getattr(configuration, "maxMarketOrdersPerTurn", 10)
    except Exception:
        return False
    if type(cap) is not int:
        return False
    # The engine caps raw slots before parsing. Do not filter placeholders or
    # consult the inert suffix; preserve all original active-row vetoes below.
    for order in market[:max(1, cap)]:
        if not isinstance(order, list) or not order or not isinstance(order[0], str):
            return False
        op = order[0]
        if op in _MARKET_SHED_INFLOW:
            return False
        if op == "SELL":
            if (
                len(order) != 3
                or order[1] not in products
                or not _plain_int(order[2])
                or order[2] <= 0
            ):
                return False
            continue
        if op == "BUY_SEED":
            if (
                len(order) != 3
                or order[1] not in seeds
                or not _plain_int(order[2])
                or order[2] <= 0
            ):
                return False
            continue
        if op in {"HIRE", "BUY_LAND"}:
            if len(order) != 1:
                return False
            continue
        return False
    return True


def _capacity_safe(private, commands, actor_tiles, candidate_indices):
    """Prove all carried inventory after unit work fits the immediate EOD shed."""
    if not isinstance(private, dict):
        return False
    inventories = private.get("inventories", _UNKNOWN)
    shed = private.get("shed", _UNKNOWN)
    if not isinstance(inventories, list) or len(inventories) != len(commands):
        return False

    shed_total = _strict_inventory_total(shed)
    if shed_total is None:
        return False
    carried_total = 0
    for inventory in inventories:
        subtotal = _strict_inventory_total(inventory)
        if subtotal is None:
            return False
        carried_total += subtotal

    inflow = 0
    candidates = set(candidate_indices)
    for index, (command, tile) in enumerate(zip(commands, actor_tiles)):
        if not command or not isinstance(command[0], str):
            return False
        op = command[0]
        if op not in _KNOWN_UNIT_OPS:
            return False
        if index in candidates or op == "HARVEST":
            gain = _tile_yield_upper_bound(tile)
            if gain is None:
                return False
            inflow += gain
        elif op == "COLLECT_FERTILIZER":
            inflow += 1

    return shed_total + carried_total + inflow <= _STANDARD_CONFIGURATION["shedCapacity"]



def _max_recovered_subset(items, room):
    """Maximize whole harvested units; equal totals prefer earlier actor indices.

    At most 101 capacity states are retained. Neither yield magnitude nor the
    powerset of workers determines allocation size. This is not a price/value
    optimizer: the existing W1 eligibility proof owns candidate admission.
    """
    if not _plain_int(room) or not 0 <= room <= _STANDARD_CONFIGURATION["shedCapacity"]:
        return []
    previous = -1
    for index, units in items:
        if (not _plain_int(index) or index <= previous
                or not _plain_int(units) or units <= 0):
            return []
        previous = index
    best = [None] * (room + 1)
    best[0] = ()
    for index, units in items:
        for total in range(room, units - 1, -1):
            prefix = best[total - units]
            if prefix is not None:
                choice = prefix + (index,)
                if best[total] is None or choice < best[total]:
                    best[total] = choice
    for choice in reversed(best):
        if choice is not None:
            return list(choice)
    return []


def _capacity_subset(private, commands, actor_tiles, candidate_indices):
    """Preserve the incumbent certificate; choose only a subset it can certify."""
    if _capacity_safe(private, commands, actor_tiles, candidate_indices):
        return list(candidate_indices)
    # Reserve every baseline cargo unit and authored inflow before any optional
    # WATER substitution. Failed original shape/quantity proofs cannot be cured
    # by omitting a candidate. No future SELL, pickup, feed or discard credit.
    if not _capacity_safe(private, commands, actor_tiles, []):
        return []
    occupied = _strict_inventory_total(private["shed"])
    occupied += sum(_strict_inventory_total(inv) for inv in private["inventories"])
    for command, tile in zip(commands, actor_tiles):
        if command[0] == "HARVEST":
            occupied += _tile_yield_upper_bound(tile)
        elif command[0] == "COLLECT_FERTILIZER":
            occupied += 1
    items = [(index, _tile_yield_upper_bound(actor_tiles[index]))
             for index in candidate_indices]
    chosen = _max_recovered_subset(
        items, _STANDARD_CONFIGURATION["shedCapacity"] - occupied)
    # This unchanged, independent incumbent check remains the final authority.
    if chosen and _capacity_safe(private, commands, actor_tiles, chosen):
        return chosen
    return []


def apply_dead_water_harvest(observation, action, configuration=None, enabled=True):
    """Recover same-tile HARVESTs; return the original object when unchanged."""
    if not enabled:
        return action
    try:
        if not _standard_configuration(configuration):
            return action
        if not isinstance(observation, dict) or not isinstance(action, dict):
            return action

        step = observation.get("step", _UNKNOWN)
        day = observation.get("day", _UNKNOWN)
        player = observation.get("player", _UNKNOWN)
        if not _plain_int(step) or not _plain_int(day):
            return action
        if day != step // 24:
            return action
        if not _plain_int(player) or player not in (0, 1):
            return action
        if step < LATE_START or step > 718:
            return action
        if step >= 696:
            report["terminal_day_block"] += 1
            return action
        if step % 24 != 23:
            return action

        farms = observation.get("farms", _UNKNOWN)
        if not isinstance(farms, list) or player >= len(farms):
            return action
        farm = farms[player]
        if not isinstance(farm, dict):
            return action
        tiles = farm.get("tiles", _UNKNOWN)
        if not _valid_board(tiles):
            return action

        farm_hands = farm.get("hands", _UNKNOWN)
        farmer_position = farm.get("farmer", _UNKNOWN)
        farmer_command = action.get("farmer", _UNKNOWN)
        action_hands = action.get("hands", _UNKNOWN)
        if (
            not isinstance(farm_hands, list)
            or not isinstance(farmer_command, list)
            or not isinstance(action_hands, list)
            or any(not isinstance(command, list) for command in action_hands)
        ):
            return action
        if len(farm_hands) != len(action_hands):
            return action

        positions = [farmer_position] + list(farm_hands)
        commands = [farmer_command] + list(action_hands)
        position_keys = []
        actor_tiles = []
        for position in positions:
            key = _position_key(position)
            if key is _UNKNOWN:
                return action
            tile = _worker_tile(tiles, position)
            if tile is _UNKNOWN:
                return action
            position_keys.append(key)
            actor_tiles.append(tile)

        for index, command in enumerate(commands):
            if command == _WATER and position_keys.count(position_keys[index]) > 1:
                return action

        report["steps_active"] += 1

        candidate_indices = []
        for index, (command, tile) in enumerate(zip(commands, actor_tiles)):
            if command != _WATER:
                continue
            reason = _wasted_water_reason(step, tile)
            if reason is None:
                continue
            report[reason] += 1
            if not _harvestable(tile, day):
                report["not_harvestable"] += 1
                continue
            if not _harvest_preserves_future_yield(tile, day, reason):
                report["future_yield_block"] += 1
                continue
            candidate_indices.append(index)

        if not candidate_indices:
            return action
        if not _market_preserves_capacity(action, configuration):
            report["capacity_block"] += 1
            return action
        candidate_indices = _capacity_subset(
            observation.get("private", _UNKNOWN),
            commands,
            actor_tiles,
            candidate_indices,
        )
        if not candidate_indices:
            report["capacity_block"] += 1
            return action

        new_commands = list(commands)
        for index in candidate_indices:
            new_commands[index] = list(_HARVEST)
            report["recovered"] += 1

        out = dict(action)
        out["farmer"] = new_commands[0]
        out["hands"] = new_commands[1:]
        return out
    except Exception:
        return action
