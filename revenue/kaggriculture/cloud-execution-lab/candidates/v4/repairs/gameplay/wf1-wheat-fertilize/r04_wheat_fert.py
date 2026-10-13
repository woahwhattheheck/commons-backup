# SPDX-License-Identifier: Apache-2.0
"""V4 lane S1: fertilize the tape's own young wheat, with no land, no hires and no lost turn.

Measured gap (claude-77's leader study): in V3.1's losses the leaders earn +4.7k/game more on
WHEAT than we do, and the top-15 fertilize wheat 33-87 times a game while our stack fertilizes
it almost never. The published route already walks a worker onto every young wheat tile and
already carries the fertilizer its animals produce, so the units are reachable without hiring
anybody (the hired-hand version of this idea measured -672/game on the 88-game live bench).

Pinned-engine facts this relies on (kaggriculture.py):
  * an annual WATER adds 1 unit inside [(max_yield_day+1)//2, max_yield_day], or 2 while the
    tile is fertilized (FERTILIZE covers day..day+2), capped at max_yield;
  * WHEAT is (max_yield_day 4, cap 6): watered every day it reaches 1+1+1+1 = 4, and one
    fertilizer placed on its day-1 or day-2 turn reaches the cap of 6;
  * age 1 is NOT a window day, so that day's WATER adds nothing; swapping it for FERTILIZE
    costs no yield, and the tile only goes one day dry, which is safe while its
    consecutive_unwatered is 0 (a weed needs two dry days in a row);
  * a worker's whole inventory returns to the shed at every end of day, and anything that does
    not fit in the 100-unit shed at that moment is discarded;
  * FERTILIZE needs the unit in the worker's own inventory; the shed is only reachable from the
    four shed-access tiles;
  * the two farms share one market: a unit we do not sell keeps that item's price higher for
    every later sale, the rival's included (FERTILIZER moves $0.20 a unit, both ways).

Three things every fertilizer unit is worth, all priced before a swap fires:
  1. its own sale (FERT_MAX keeps the lane out of the expensive early market, where withholding
     a unit lifts the price the rival sells into);
  2. the best use another lane could make of it today (ALT_GATE: the endgame carrot hand pays
     far more per unit in a PET_CAFE town, and gets the unit if this lane leaves it alone);
  3. the shed slot its crop will need (SHED_MAX, plus CREDIT, which sells the extra wheat as it
     is harvested so the late-game shed never loses a strawberry or an egg to a wheat unit).

Four transforms, none of which delays the route by a single step (each replaces a command that
is provably yield-free, or a PASS):
  SWAP_AGE1   a WATER on a young annual whose today's water earns nothing -> FERTILIZE;
  SWAP_AGE2   a WATER on a day-2 annual -> FERTILIZE (loses that day's 1 unit, buys 2+2);
  RETAIN      a DROP / PLACE FERTILIZER at the shed keeps the fertilizer in hand instead;
  PICKUP_PASS a PASS on a shed-access tile -> PICKUP FERTILIZER.
Malformed or unexpected state fails closed to the parent action.
"""

from __future__ import annotations

import copy

KEY = "r04_wheat_fertilize"
WHEAT_FERTILIZE = False

SWAP_AGE1 = True
SWAP_AGE2 = True
RETAIN = False
PICKUP_PASS = False
ALT_GATE = True                # leave the unit alone when another tile pays more for it
CREDIT = True                  # sell the extra units as they are harvested

CROPS = ("WHEAT", "CARROT")    # MELON's window is long enough that fertilizer never pays
CROP_DATA = {"WHEAT": (4, 6), "CARROT": (3, 4), "MELON": (12, 6)}   # max_yield_day, max_yield
PRICE_KEEP = 0.8               # extra units sell below today's quote; keep this share of it
MIN_EDGE = 10                  # crop value of the extra units, above the fertilizer's own price
FERT_RATIO = 0.0               # and at least this multiple of the fertilizer's quote, when set
FERT_MAX = 30                  # only spend fertilizer this lane while its quote is this low
SHED_MAX = 85                  # shed units above which another crop unit costs a better one
HOLD_MAX = 3                   # fertilizer units a worker may carry for this lane
PICKUP_RESERVE = 2             # shed fertilizer left for the tape's own pickups
FIRST_DAY = 1
LAST_DAY = 28                  # a day-29 fertilizer has no window day left to pay for itself
LAST_STEP = 700                # never touch the endgame flush, the B9 rows or the liquidation
MAX_ORDERS = 10
TURNS_PER_DAY = 24

_STATE = {}
REPORT = {"swap_age1": 0, "swap_age2": 0, "swap_units": 0, "retain": 0, "retain_units": 0,
          "pickup": 0, "pickup_units": 0, "declined_alt": 0, "declined_price": 0,
          "declined_shed": 0, "credit_units": 0, "sold_units": 0}


def _int(value):
    """Engine integers only; bool/float/string coercions are not evidence."""
    return type(value) is int


def _shed_tiles(board):
    half = board // 2
    return {(half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half)}


def _window(tile, day):
    """(yield units, remaining window days after today, today counts) or None."""
    if not isinstance(tile, dict) or tile.get("kind") != "PLANT":
        return None
    crop = tile.get("crop")
    if crop not in CROPS:
        return None
    planted = tile.get("planted_day")
    units = tile.get("yield_units")
    covered = tile.get("fertilized_until_day")
    watered = tile.get("watered_today")
    dry_days = tile.get("consecutive_unwatered")
    if not (_int(planted) and _int(units) and units >= 0 and _int(covered)
            and type(watered) is bool and _int(dry_days) and dry_days >= 0):
        return None
    if covered >= day:                       # already covered today: another unit adds nothing
        return None
    last_day, cap = CROP_DATA[crop]
    window = range(planted + (last_day + 1) // 2, planted + last_day + 1)
    later = [d for d in window if d > day]
    today = day in window and not watered
    return crop, cap, units, later, today, watered, dry_days


def swap_gain(tile, day):
    """Units gained by spending today's WATER on FERTILIZE instead, all later waters assumed."""
    state = _window(tile, day)
    if state is None:
        return 0
    crop, cap, units, later, today, watered, dry_days = state
    if not watered and dry_days != 0:        # skipping today's water would weed the tile tonight
        return 0
    base = units + (1 if today else 0) + len(later)   # covered < day, so a later water adds 1
    swapped = units + sum(2 if day + 2 >= d else 1 for d in later)
    return max(0, min(cap, swapped) - min(cap, base))


def cover_gain(tile, day):
    """Units gained by covering this tile today without giving up its water (any other lane)."""
    state = _window(tile, day)
    if state is None:
        return 0
    crop, cap, units, later, today, watered, dry_days = state
    base = units + (1 if today else 0) + len(later)
    covered = units + (2 if today else 0) + sum(2 if day + 2 >= d else 1 for d in later)
    return max(0, min(cap, covered) - min(cap, base))


def _prices(observation):
    market = observation.get("market")
    prices = market.get("prices") if isinstance(market, dict) else None
    if not isinstance(prices, dict):
        return None
    out = {}
    for item in list(CROPS) + ["FERTILIZER"]:
        value = prices.get(item)
        if not _int(value) or value < 0:
            return None
        out[item] = value
    return out


def _best_alternative(tiles, day, prices, skip):
    """Crop value one fertilizer buys on the best tile of the farm other than `skip`."""
    best = 0.0
    for y, row in enumerate(tiles):
        for x, tile in enumerate(row):
            if (x, y) == skip:
                continue
            gain = cover_gain(tile, day)
            if gain > 0:
                best = max(best, gain * prices[tile["crop"]])
    return best


def _state_of(observation, action):
    """(farm, positions, commands, inventories, shed, prices) or None when anything is off-shape."""
    player = observation.get("player")
    step = observation.get("step")
    farms = observation.get("farms")
    private = observation.get("private")
    if not (_int(player) and player >= 0 and _int(step) and step >= 0
            and isinstance(farms, list) and player < len(farms) and isinstance(private, dict)):
        return None
    farm = farms[player]
    if not isinstance(farm, dict) or not isinstance(action, dict):
        return None
    hands = farm.get("hands")
    tiles = farm.get("tiles")
    inventories = private.get("inventories")
    shed = private.get("shed")
    command_hands = action.get("hands")
    if not (isinstance(hands, list) and isinstance(tiles, list) and isinstance(inventories, list)
            and isinstance(shed, dict) and isinstance(command_hands, list)
            and "farmer" in farm and "farmer" in action):
        return None
    positions = [farm["farmer"], *hands]
    commands = [action["farmer"], *command_hands]
    if len(positions) != len(commands) or len(inventories) < len(positions):
        return None
    for position in positions:
        if not (isinstance(position, (list, tuple)) and len(position) == 2
                and _int(position[0]) and _int(position[1])):
            return None
        x, y = position
        if not (0 <= y < len(tiles) and isinstance(tiles[y], list) and 0 <= x < len(tiles[y])):
            return None
    for command in commands:
        if not (isinstance(command, list) and command and isinstance(command[0], str)):
            return None
    for inventory in inventories[:len(positions)]:
        if not isinstance(inventory, dict):
            return None
        held = inventory.get("FERTILIZER", 0)
        if not _int(held) or held < 0:
            return None
    for count in shed.values():
        if not _int(count) or count < 0:
            return None
    prices = _prices(observation)
    if prices is None:
        return None
    return farm, positions, commands, inventories, shed, prices


def _day_state(player, step):
    state = _STATE.get(player)
    if state is None or step <= state["last_step"] or step // TURNS_PER_DAY < state["day"]:
        state = _STATE[player] = {"last_step": step, "day": step // TURNS_PER_DAY,
                                  "tiles": {}, "credit": 0}
    state["last_step"] = step
    state["day"] = step // TURNS_PER_DAY
    return state


def _collect_credit(state, tiles, commands, positions, day):
    """Credit the extra units as the tiles this lane fertilized are harvested (or lost)."""
    for worker, position in enumerate(positions):
        if commands[worker][0] != "HARVEST":
            continue
        key = (position[0], position[1])
        planned = state["tiles"].get(key)
        if not planned:
            continue
        tile = tiles[position[1]][position[0]]
        if (isinstance(tile, dict) and tile.get("kind") == "PLANT"
                and tile.get("planted_day") == planned[0] and _int(tile.get("yield_units"))):
            gained = min(planned[1], max(0, tile["yield_units"]))
            state["credit"] += gained
            REPORT["credit_units"] += gained
        del state["tiles"][key]
    for key, planned in list(state["tiles"].items()):
        tile = tiles[key[1]][key[0]]
        if not (isinstance(tile, dict) and tile.get("kind") == "PLANT"
                and tile.get("crop") == planned[2] and tile.get("planted_day") == planned[0]):
            del state["tiles"][key]          # harvested by another route, dug, or weeded


def _sell_credit(state, action, shed, market):
    """Sell exactly the units this lane added, so the shed level never rises because of it."""
    credit = state["credit"]
    if credit <= 0:
        return action
    stock = int(shed.get("WHEAT", 0))
    planned = 0
    row = None
    for order in market:
        if not (isinstance(order, list) and order):
            continue
        if order[0] == "BUY_PRODUCT" and len(order) > 1 and order[1] == "WHEAT":
            return action                    # never cross a same-item purchase
        if order[:2] == ["SELL", "WHEAT"] and len(order) >= 3 and _int(order[2]):
            planned += max(0, order[2])
            row = order
    sell = min(credit, max(0, stock - planned))
    if sell <= 0:
        return action
    result = copy.deepcopy(action)
    rows = result.get("market") or []
    if row is not None:
        for order in rows:
            if order and order[:2] == ["SELL", "WHEAT"] and len(order) >= 3:
                order[2] = int(order[2]) + sell
                break
    elif len(rows) < MAX_ORDERS:
        rows.append(["SELL", "WHEAT", sell])
        result["market"] = rows
    else:
        return action
    state["credit"] -= sell
    REPORT["sold_units"] += sell
    return result


def apply_wheat_fertilize(observation, action, enabled=False):
    """Return the action with this lane's replacements applied; fails closed to `action`."""
    if not enabled or not isinstance(observation, dict) or not isinstance(action, dict):
        return action
    try:
        state = _state_of(observation, action)
    except Exception:
        return action
    if state is None:
        return action
    farm, positions, commands, inventories, shed, prices = state
    step = int(observation["step"])
    day = step // TURNS_PER_DAY
    if step >= LAST_STEP or not FIRST_DAY <= day <= LAST_DAY:
        return action
    try:
        return _apply(observation, action, state, step, day)
    except Exception:
        return action


def _apply(observation, action, state, step, day):
    farm, positions, commands, inventories, shed, prices = state
    player = int(observation["player"])
    memory = _day_state(player, step)
    tiles = farm["tiles"]
    board = len(tiles)
    sheds = _shed_tiles(board)
    shed_fertilizer = int(shed.get("FERTILIZER", 0))
    shed_total = sum(int(v) for v in shed.values())
    market = action.get("market") or []
    if not isinstance(market, list):
        return action
    if CREDIT:
        _collect_credit(memory, tiles, commands, positions, day)
    replacements = {}
    claimed = set()
    cheap = prices["FERTILIZER"] <= FERT_MAX
    roomy = shed_total <= SHED_MAX
    for worker, position in enumerate(positions):
        command = commands[worker]
        x, y = position
        tile = tiles[y][x]
        held = int(inventories[worker].get("FERTILIZER", 0))
        if command[0] == "WATER" and held > 0 and (x, y) not in claimed:
            gain = swap_gain(tile, day)
            if gain > 0:
                crop = tile["crop"]
                value = gain * prices[crop]
                age = day - tile["planted_day"]
                wanted = (age <= 1 and SWAP_AGE1) or (age >= 2 and SWAP_AGE2)
                kept = value * PRICE_KEEP
                if (not cheap or kept - prices["FERTILIZER"] < MIN_EDGE
                        or kept < FERT_RATIO * prices["FERTILIZER"]):
                    REPORT["declined_price"] += 1
                elif not roomy:
                    REPORT["declined_shed"] += 1
                elif ALT_GATE and _best_alternative(tiles, day, prices, (x, y)) > value:
                    REPORT["declined_alt"] += 1
                elif wanted:
                    replacements[worker] = ["FERTILIZE"]
                    claimed.add((x, y))
                    if crop == "WHEAT":
                        memory["tiles"][(x, y)] = (tile["planted_day"], gain, crop)
                    REPORT["swap_age1" if age <= 1 else "swap_age2"] += 1
                    REPORT["swap_units"] += gain
                    continue
        if (x, y) not in sheds or not cheap or not roomy:
            continue
        if RETAIN and 0 < held <= HOLD_MAX:
            if command == ["DROP"]:
                others = [(item, int(n)) for item, n in inventories[worker].items()
                          if item != "FERTILIZER" and _int(n) and n > 0]
                if not others:
                    replacements[worker] = ["PASS"]
                elif len(others) == 1:
                    replacements[worker] = ["PLACE", others[0][0], others[0][1]]
                else:
                    continue
                REPORT["retain"] += 1
                REPORT["retain_units"] += held
                continue
            if command[:2] == ["PLACE", "FERTILIZER"]:
                replacements[worker] = ["PASS"]
                REPORT["retain"] += 1
                REPORT["retain_units"] += held
                continue
        if (PICKUP_PASS and command == ["PASS"] and held < HOLD_MAX
                and shed_fertilizer - PICKUP_RESERVE > 0):
            want = min(HOLD_MAX - held, shed_fertilizer - PICKUP_RESERVE)
            if want > 0:
                replacements[worker] = ["PICKUP", "FERTILIZER", want]
                shed_fertilizer -= want
                REPORT["pickup"] += 1
                REPORT["pickup_units"] += want
    if replacements:
        action = copy.deepcopy(action)
        rows = [action["farmer"], *action["hands"]]
        for worker, command in replacements.items():
            rows[worker] = command
        action["farmer"], action["hands"] = rows[0], rows[1:]
    if CREDIT:
        action = _sell_credit(memory, action, shed, action.get("market") or [])
    return action
