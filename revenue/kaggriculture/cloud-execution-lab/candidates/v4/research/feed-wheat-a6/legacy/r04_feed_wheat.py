# SPDX-License-Identifier: Apache-2.0
"""R04 lane A6: grow the feed wheat instead of buying 156 units of product.

Idea-hunt A6 (replay forensics, 31-game corpus): we buy ~156 wheat product per
game at ~$38 ($5,928) for animal feed while selling 622 homegrown wheat at $41
VWAP. The buys are a timing artifact -- animals need feed on days 0-1 before
the first harvest, plus a mid-game buffer on days 4-12. Planting ~26 extra
wheat seeds ($260) on days 0-2 covers the deficit at $1.67/unit: each extra
plant yields 1 unit immediately and up to 6 with watering inside the wheat
yield window (days 2-4), worth $38-41/unit either as displaced bought feed or
as an extra sale.

Mechanism (three parts, all behind the r04_feed_wheat master key):
  1. Seed front-load: BUY_SEED WHEAT orders on days 0-2 (default 26 total,
     spread 9/9/8), budget- and market-slot-checked.
  2. Opportunistic crew: idle (PASS-command) units plant the extra seeds on
     empty tiles they already stand on, water the recorded plants inside the
     yield window, harvest them from day 5, and PLACE carried wheat at the
     shed. Purely additive -- a unit the tape needs is never redirected, and
     the engine's atomic PLANT check (all wheat PLANTs dropped if demand
     exceeds seeds) is guarded by counting the tape's own PLANT WHEAT first.
  3. Emergency-buy cap: the v226 topup and v234 sheep-rescue wheat buys are
     capped at r04_feed_wheat_buy_cap units/day (default 1.2), from day 5 when
     the extra harvest can plausibly cover feed. Pre-day-5 buys are untouched:
     capping them would starve animals before any extra wheat exists.

With the flag off every entry point short-circuits and behavior is
byte-identical to the pre-lane route.

Engine facts used (pinned kaggriculture.py @ 28b6d8af3):
- PLANT consumes private["seeds"] (never shed/inventory) and needs an empty
  tile; atomic per-step validation drops ALL of a crop's PLANTs if their count
  exceeds available seeds.
- Wheat: 1 yield_unit at planting, +1 per watered day in window d2-4
  (+2 if fertilized), capped at max_yield 6; HARVEST moves units to the
  worker's inventory and frees the tile; FEED takes WHEAT from inventory.
- BUY_SEED executes at end of step; seeds are plantable from the next step.
- Market queue is capped at 10 orders (MAX_ORDERS).

Python standard library only.
"""

from __future__ import annotations

# Default total extra wheat seeds bought+planted on days 0-2.
DEFAULT_EXTRA_SEEDS = 26
# Days on which the extra seeds are bought and planted.
PLANT_DAYS = (0, 1, 2)
# Wheat yield window (days 2-4): watering inside it adds +1 yield_unit.
WATER_DAYS = (2, 3, 4)
# Harvest the recorded plants once watered (or late for whatever grew).
HARVEST_START_DAY = 5
# The emergency-buy cap only binds once the extra harvest can cover feed.
BUY_CAP_START_DAY = 5
SEED_PRICE = 10
MAX_ORDERS = 10

# Telemetry: what the lane actually did. Updated on hits; cleared by reset().
REPORT = {
    "seed_orders": 0,      # BUY_SEED WHEAT orders appended
    "seed_units": 0,       # extra seeds ordered
    "plants": 0,           # extra PLANT WHEAT commands issued
    "waters": 0,           # waterings of recorded plants
    "harvests": 0,         # harvests of recorded plants
    "places": 0,           # shed PLACEs of carried wheat
    "buy_caps": 0,         # emergency buys declined/capped
    "capped_units": 0,     # wheat units not bought because of the cap
}

# Per-player lane state. "bought" tracks emergency wheat product bought today
# for the cap; "ordered" tracks extra seeds ordered; "planted" lists recorded
# extra-plant tiles (x, y). Reset on episode restart (step <= last_step).
_STATES = {}


def reset():
    """Clear telemetry and per-player lane state."""
    for key in REPORT:
        REPORT[key] = 0
    _STATES.clear()


def _state(player, day):
    state = _STATES.get(player)
    if state is None or day < state["day"]:
        state = {"day": day, "ordered": 0, "planted": [], "bought": 0.0,
                 "bought_day": -1}
        _STATES[player] = state
    if day != state["bought_day"]:
        state["bought_day"] = day
        state["bought"] = 0.0
    return state


def seed_order(day, enabled, extra_seeds, ordered):
    """Pure: how many extra BUY_SEED WHEAT to order on this day.

    Spreads the remaining quota evenly over the plant days left. Returns 0
    when the lane is off, the day is not a plant day, or the quota is met.
    """
    if not enabled or day not in PLANT_DAYS:
        return 0
    remaining = max(0, int(extra_seeds) - int(ordered))
    if remaining <= 0:
        return 0
    days_left = sum(1 for d in PLANT_DAYS if d >= day)
    return max(1, -(-remaining // max(1, days_left)))


def buy_headroom(player, day, cap):
    """Pure-ish: emergency wheat units still buyable today under the cap."""
    if cap is None:
        return float("inf")
    state = _state(player, day)
    return max(0.0, float(cap) - state["bought"])


def note_bought(player, day, units):
    """Record emergency wheat product bought (for the cap)."""
    state = _state(player, day)
    state["bought"] += float(units)


def capped(shortage, player, day, cap):
    """Apply the emergency-buy cap to a proposed wheat buy.

    Returns the allowed units (may be 0). Only binds on/after
    BUY_CAP_START_DAY; before that the extra harvest cannot exist, so capping
    would starve animals. Records telemetry on hits.
    """
    if cap is None or day < BUY_CAP_START_DAY:
        return shortage
    headroom = buy_headroom(player, day, cap)
    allowed = max(0, min(int(shortage), int(headroom)))
    if allowed < shortage:
        REPORT["buy_caps"] += 1
        REPORT["capped_units"] += int(shortage) - allowed
    return allowed


def _walk(pos, target):
    x, y = pos
    tx, ty = target
    if x != tx:
        return ["EAST" if x < tx else "WEST"]
    if y != ty:
        return ["SOUTH" if y < ty else "NORTH"]
    return None


def _shed_adjacent(pos, size=10):
    center = size // 2
    return pos[0] in (center - 1, center) and pos[1] in (center - 1, center)


def _nearest_shed_tile(pos, size=10):
    center = size // 2
    options = [(center - 1, center - 1), (center, center - 1),
               (center - 1, center), (center, center)]
    return min(options, key=lambda t: abs(pos[0] - t[0]) + abs(pos[1] - t[1]))


def _tile(tiles, pos):
    x, y = pos
    if 0 <= y < len(tiles) and 0 <= x < len(tiles[y]):
        return tiles[y][x]
    return "LOCKED"


def apply(observation, action, enabled, extra_seeds, buy_cap):
    """The v3_agent() call-site for lane A6.

    Appends the day's extra BUY_SEED WHEAT order and opportunistically
    redirects idle (PASS) units to plant/water/harvest the extra wheat and to
    PLACE carried wheat at the shed. Returns the action unchanged when the
    lane is off.
    """
    if not enabled:
        return action
    step = int(observation["step"])
    if step >= 719:  # never touch terminal liquidation
        return action
    player = int(observation["player"])
    day = step // 24
    state = _state(player, day)

    farm = observation["farms"][player]
    tiles = farm["tiles"]
    size = len(tiles)
    money = farm.get("money", 0)
    private = observation.get("private") or {}
    seeds = (private.get("seeds") or {}).get("WHEAT", 0)
    inventories = private.get("inventories") or []

    market = action.get("market") or []
    commands = [action.get("farmer") or ["PASS"], *(action.get("hands") or [])]
    positions = [tuple(farm.get("farmer") or (0, 0)),
                 *(tuple(h) for h in (farm.get("hands") or []))]
    n_units = min(len(commands), len(positions), len(inventories) + 1)

    changed = False

    # --- 1. extra seed orders on plant days ---------------------------------
    if day in PLANT_DAYS and len(market) < MAX_ORDERS:
        want = seed_order(day, True, extra_seeds, state["ordered"])
        if want > 0 and money >= 300 + want * (SEED_PRICE + 10):
            market = list(market) + [["BUY_SEED", "WHEAT", want]]
            state["ordered"] += want
            REPORT["seed_orders"] += 1
            REPORT["seed_units"] += want
            changed = True

    # Prune recorded plants that are gone (harvested by the tape, dug, etc.).
    live = []
    for tpos in state["planted"]:
        tile = _tile(tiles, tpos)
        if isinstance(tile, dict) and tile.get("crop") == "WHEAT":
            live.append(tpos)
    state["planted"] = live

    def is_pass(i):
        return i < len(commands) and list(commands[i]) == ["PASS"]

    def carrying_wheat(i):
        if i < len(inventories):
            return int((inventories[i] or {}).get("WHEAT", 0))
        return 0

    # --- 2. place carried wheat / walk it to the shed ------------------------
    for i in range(n_units):
        if not is_pass(i) or carrying_wheat(i) <= 0:
            continue
        pos = positions[i]
        if _shed_adjacent(pos, size):
            commands[i] = ["PLACE", "WHEAT", carrying_wheat(i)]
        else:
            walk = _walk(pos, _nearest_shed_tile(pos, size))
            if walk:
                commands[i] = walk
            else:
                continue
        REPORT["places"] += 1
        changed = True

    # --- 3. planting on plant days -------------------------------------------
    if day in PLANT_DAYS and state["ordered"] > 0:
        tape_plants = sum(1 for c in commands
                          if isinstance(c, list) and c[:2] == ["PLANT", "WHEAT"])
        # Plant at most the configured extra seeds, and never more than the
        # extra seeds actually ordered (they arrive end-of-step via the market).
        quota = max(0, min(int(extra_seeds) - len(state["planted"]),
                           state["ordered"] - len(state["planted"])))
        my_plants = 0
        for i in range(n_units):
            if quota <= 0:
                break
            if not is_pass(i):
                continue
            pos = positions[i]
            if _tile(tiles, pos) is not None:
                continue
            if tape_plants + my_plants + 1 > seeds:
                # Engine drops ALL wheat PLANTs if demand exceeds seeds;
                # never risk the tape's own plantings.
                break
            commands[i] = ["PLANT", "WHEAT"]
            state["planted"].append(pos)
            my_plants += 1
            quota -= 1
            REPORT["plants"] += 1
            changed = True

    # --- 4. watering inside the yield window ---------------------------------
    if day in WATER_DAYS:
        for tpos in list(state["planted"]):
            tile = _tile(tiles, tpos)
            if not (isinstance(tile, dict) and not tile.get("watered_today")):
                continue
            # nearest idle unit
            best, best_d = None, None
            for i in range(n_units):
                if not is_pass(i):
                    continue
                d = abs(positions[i][0] - tpos[0]) + abs(positions[i][1] - tpos[1])
                if best_d is None or d < best_d:
                    best, best_d = i, d
            if best is None:
                continue
            if best_d == 0:
                commands[best] = ["WATER"]
            else:
                walk = _walk(positions[best], tpos)
                if walk:
                    commands[best] = walk
                else:
                    continue
            REPORT["waters"] += 1
            changed = True

    # --- 5. harvest from day 5 -----------------------------------------------
    if day >= HARVEST_START_DAY:
        for tpos in list(state["planted"]):
            tile = _tile(tiles, tpos)
            if not (isinstance(tile, dict)
                    and int(tile.get("yield_units", 0)) > 0):
                continue
            best, best_d = None, None
            for i in range(n_units):
                if not is_pass(i):
                    continue
                d = abs(positions[i][0] - tpos[0]) + abs(positions[i][1] - tpos[1])
                if best_d is None or d < best_d:
                    best, best_d = i, d
            if best is None:
                continue
            if best_d == 0:
                commands[best] = ["HARVEST"]
            else:
                walk = _walk(positions[best], tpos)
                if walk:
                    commands[best] = walk
                else:
                    continue
            REPORT["harvests"] += 1
            changed = True
            # the tile frees on harvest; drop it from the recorded list
            if best_d == 0:
                state["planted"].remove(tpos)

    if not changed:
        return action
    action = dict(action)
    action["market"] = market
    action["farmer"] = commands[0]
    action["hands"] = commands[1:]
    return action
