# SPDX-License-Identifier: Apache-2.0
"""A4: second-wave melons planted on day 12 (idea-hunt A lane).

Economics (engine-verified, pinned kaggriculture.py @ 28b6d8af3):
  MELON seed $80 -> up to 6 x $250 = $1,500 (18.75x ROI). Non-ongoing crop:
  planted with yield_units=1; each WATER inside the yield window adds +1
  (window_start = (max_yield_day+1)//2 = 6, so days P+6..P+12 for planting day P),
  capped at max_yield=6. HARVEST needs age >= first_yield_day = 10 and frees the
  tile. The plant dies at step (P+13)*24 and turns to WEED after 2 consecutive
  unwatered days (the planting day itself counts as unwatered, so the planting
  day MUST be watered).

  Planted day 12: water d12 (survival), water d13+ (survival every other day is
  enough, daily is simpler), yield accrues d18-24, harvest d22-24, tile decays
  from the start of day 25. Harvested melons ride the existing sale machinery
  (evening flush sells MELON).

Mechanism: the lane hires its own crew (hired hands reset every dawn, so the
crew is re-hired daily) and drives them with a per-worker job queue, V219-style.
Day 12 hires 2 workers (plant + water N tiles); days 13-24 hire 1 worker/day
(water; harvest d22-24 with same-day PLACE to the shed). Everything is a
post-processing layer on the v3_agent() seam: parent tape commands are never
edited, only appended to (market) or extended (extra hand commands).

Safety properties:
  * Default OFF; with enabled=False the action object is returned untouched.
  * Never exceeds MAX_MARKET_ORDERS; never appends HIRE on a step where the
    parent already queues HIRE (avoids confusing parent hire accounting).
  * PLANT only on free (None) tiles with seeds actually on hand; per-step PLANT
    demand never exceeds the seed stock (the engine voids the whole crop's
    PLANTs for the turn otherwise).
  * Money floor before buying seeds/hiring.
  * New hands are *detected* (yesterday's count vs today's), never assumed, so
    a failed HIRE degrades to a retry, not a misdirected worker.
  * Tile identity is re-derived every step from planted_day == plant_day, so the
    lane survives any parent interference on its tiles.

Known interaction: the extra hires on days 18-24 can trip V219's
len(hands) != expected guard, standing the V219 tomato investment down. Per
idea-hunt A1 that investment is -EV (~$800/game), so the direction is benign,
but it is a coupling to be aware of when gating.

Python standard library only.
"""
from __future__ import annotations

from collections import deque

# --- tunable defaults (all overridable via install()/TITAN-CONFIG) ---
DEFAULT_COUNT = 6          # melon seeds to plant in the second wave
DEFAULT_PLANT_DAY = 12     # planting day; window d18-24, harvest d22-24
LAST_DAY = 24              # decay starts at the first step of day 25
HARVEST_AGE = 10           # engine first_yield_day for MELON
WINDOW_START_AGE = 6       # (max_yield_day + 1) // 2
SEED_COST = 80
MONEY_FLOOR = 2000         # buy/hire only above this cash level
MAX_ORDERS = 10
PLANT_WORKERS = 2          # crew size on planting day
TEND_WORKERS = 1           # crew size on watering/harvest days
HARVEST_PER_DAY = 3        # tiles harvested per harvest day

# Telemetry, mirroring the V219 REPORT pattern.
REPORT = {
    "enabled": False,
    "seeds_bought": 0,
    "hires": 0,
    "plants": 0,
    "waters": 0,
    "harvests": 0,
    "places": 0,
    "declines": 0,
}

# Per-player lane state. Reset at episode start by the runtime calling reset();
# unit tests call reset() directly.
_STATES = {}


def reset():
    """Clear per-player state and telemetry (episode boundary / test isolation)."""
    _STATES.clear()
    for key in REPORT:
        # NB: bool is a subclass of int; check it first so "enabled" resets to
        # False, not 0.
        REPORT[key] = False if isinstance(REPORT[key], bool) else 0


def _new_state():
    return {
        "day": -1,
        "crew": [],          # command indices (farmer=0) of this lane's workers today
        "prev_hands": 0,     # len(farm['hands']) at the previous step
        "hire_pending": False,
        "queues": {},        # cmd_idx -> deque of jobs
        "jobs_built_day": -1,
        "jobs_built_crew": (),  # crew tuple the queues were built for
    }


def _home(pos, board):
    half = board // 2
    return min(((half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half)),
               key=lambda p: abs(pos[0] - p[0]) + abs(pos[1] - p[1]))


def _shed_adjacent(pos, board):
    half = board // 2
    return tuple(pos) in {(half - 1, half - 1), (half, half - 1),
                          (half - 1, half), (half, half)}


def _walk(pos, target):
    x, y = pos
    tx, ty = target
    if x != tx:
        return ["EAST" if x < tx else "WEST"]
    if y != ty:
        return ["SOUTH" if y < ty else "NORTH"]
    return None


def _my_tiles(tiles, plant_day):
    """Tiles holding this lane's second-wave melons (re-derived every step)."""
    found = []
    for y, row in enumerate(tiles):
        if not isinstance(row, list):
            continue
        for x, tile in enumerate(row):
            if (isinstance(tile, dict) and tile.get("kind") == "PLANT"
                    and tile.get("crop") == "MELON"
                    and tile.get("planted_day") == plant_day):
                found.append((x, y))
    return found


def _free_tiles(tiles, board, near, count):
    """Free (None) tiles, nearest to `near` first, excluding shed tiles."""
    half = board // 2
    shed = {(half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half)}
    cands = []
    for y, row in enumerate(tiles):
        if not isinstance(row, list):
            continue
        for x, tile in enumerate(row):
            if tile is None and (x, y) not in shed:
                cands.append((x, y))
    cands.sort(key=lambda p: (abs(p[0] - near[0]) + abs(p[1] - near[1]), p[1], p[0]))
    return cands[:count]


def _parent_hires(market):
    return sum(1 for o in market
               if isinstance(o, list) and o and o[0] == "HIRE")


def _room(market):
    return MAX_ORDERS - sum(1 for o in market if o)


def _hire_cost_today(farm):
    # Engine: mult * fib(hires_today); fib(0)=1, fib(1)=1, fib(2)=2, ...
    a, b = 1, 1
    for _ in range(max(0, int(farm.get("hires_today") or 0))):
        a, b = b, a + b
    return a  # FARM_HAND_COST_MULT == 1 in the pinned engine


def _build_jobs(state, tiles, plant_day, day, count, board, crew):
    """(Re)build each crew member's job queue for the current day."""
    my = _my_tiles(tiles, plant_day)
    queues = {}
    if day == plant_day:
        # Planting day: split the target tiles across the crew; each tile gets
        # goto -> PLANT -> WATER (the planting day must be watered or the plant
        # dies at dawn: consecutive_unwatered starts at 1).
        targets = _free_tiles(tiles, board, _home((0, 0), board), count)
        targets = targets[:max(0, count - len(my))]
        for i, worker in enumerate(crew):
            q = deque()
            for (x, y) in targets[i::len(crew)]:
                q.append(("goto", x, y))
                q.append(("plant", x, y))
                q.append(("water", x, y))
            queues[worker] = q
    elif day < plant_day + HARVEST_AGE:
        # Watering days: one WATER per tile that still needs it.
        per = max(1, (len(my) + len(crew) - 1) // max(1, len(crew)))
        for i, worker in enumerate(crew):
            q = deque()
            for (x, y) in my[i * per:(i + 1) * per]:
                q.append(("goto", x, y))
                q.append(("water", x, y))
            queues[worker] = q
    else:
        # Harvest days: water everything (keeps unharvested tiles alive and
        # accruing), harvest HARVEST_PER_DAY tiles, then PLACE at the shed.
        per = max(1, (len(my) + len(crew) - 1) // max(1, len(crew)))
        for i, worker in enumerate(crew):
            q = deque()
            mine = my[i * per:(i + 1) * per]
            for n, (x, y) in enumerate(mine):
                q.append(("goto", x, y))
                q.append(("water", x, y))
                if n < HARVEST_PER_DAY:
                    q.append(("harvest", x, y))
            if any(job[0] == "harvest" for job in q):
                q.append(("place",))
            queues[worker] = q
    state["queues"] = queues
    state["jobs_built_day"] = day
    state["jobs_built_crew"] = tuple(crew)


def _crew_command(state, worker, obs, farm, board, plant_day, day, count, seeds):
    """Next command for one crew worker; drives its job queue to completion."""
    tiles = farm["tiles"]
    q = state["queues"].get(worker)
    if not q:
        return ["PASS"]
    positions = [farm["farmer"], *farm["hands"]]
    pos = tuple(positions[worker]) if worker < len(positions) else None
    if pos is None:
        return ["PASS"]
    inventories = (obs.get("private") or {}).get("inventories") or []
    inv = inventories[worker] if worker < len(inventories) else {}

    while q:
        job = q[0]
        kind = job[0]
        if kind == "goto":
            _, x, y = job
            step = _walk(pos, (x, y))
            if step is None:
                q.popleft()
                continue
            return step
        if kind == "plant":
            _, x, y = job
            tile = tiles[y][x] if y < len(tiles) and x < len(tiles[y]) else "LOCKED"
            if tile is None and seeds > 0 and len(_my_tiles(tiles, plant_day)) < count:
                q.popleft()
                REPORT["plants"] += 1
                return ["PLANT", "MELON"]
            q.popleft()  # tile taken or no seeds: abandon quietly
            continue
        if kind == "water":
            _, x, y = job
            tile = tiles[y][x] if y < len(tiles) and x < len(tiles[y]) else None
            if (isinstance(tile, dict) and tile.get("kind") == "PLANT"
                    and not tile.get("watered_today")):
                q.popleft()
                REPORT["waters"] += 1
                return ["WATER"]
            q.popleft()
            continue
        if kind == "harvest":
            _, x, y = job
            tile = tiles[y][x] if y < len(tiles) and x < len(tiles[y]) else None
            if (isinstance(tile, dict) and tile.get("kind") == "PLANT"
                    and tile.get("crop") == "MELON"
                    and tile.get("yield_units", 0) > 0
                    and day - tile.get("planted_day", day) >= HARVEST_AGE):
                q.popleft()
                REPORT["harvests"] += 1
                return ["HARVEST"]
            q.popleft()
            continue
        if kind == "place":
            qty = int(inv.get("MELON", 0))
            if qty <= 0:
                q.popleft()
                continue
            if _shed_adjacent(pos, board):
                q.popleft()
                REPORT["places"] += 1
                return ["PLACE", "MELON", qty]
            step = _walk(pos, _home(pos, board))
            return step or ["PASS"]
        q.popleft()  # unknown job: drop, never stall
    return ["PASS"]


def apply_a4(observation, action, *, enabled=False, count=DEFAULT_COUNT,
             plant_day=DEFAULT_PLANT_DAY):
    """Second-wave melon lane as a v3_agent() post-processing layer.

    Returns the (possibly modified) action. With enabled=False the input action
    object is returned untouched.
    """
    if enabled is not True:
        return action
    REPORT["enabled"] = True
    count = max(0, int(count))
    plant_day = int(plant_day)

    obs = observation or {}
    step = int(obs.get("step", 0))
    day = step // 24
    player = int(obs.get("player", 0))
    farms = obs.get("farms") or []
    if player < 0 or player >= len(farms) or count == 0:
        return action
    farm = farms[player]
    if not isinstance(farm, dict):
        return action
    if day < plant_day or day > LAST_DAY:
        return action

    board = len(farm.get("tiles") or [])
    if board == 0:
        return action

    state = _STATES.get(player)
    if state is None or state["day"] != day:
        # Dawn (or first sight): hands reset, so the crew must be re-hired.
        state = _new_state()
        state["day"] = day
        _STATES[player] = state

    hands = farm.get("hands") or []
    # Detect newly appeared hands; only hands that arrived right after our own
    # HIRE step are claimed for the crew.
    if state["hire_pending"]:
        for hand_idx in range(state["prev_hands"], len(hands)):
            state["crew"].append(hand_idx + 1)  # command index (0 == farmer)
            REPORT["hires"] += 1
        state["hire_pending"] = False
    state["prev_hands"] = len(hands)

    market = [list(o) for o in (action.get("market") or []) if o]
    seeds = int(((obs.get("private") or {}).get("seeds") or {}).get("MELON", 0))
    money = float(farm.get("money") or 0)
    my_tiles = _my_tiles(farm["tiles"], plant_day)

    changed = False

    # --- market: seeds -----------------------------------------------------
    if day == plant_day:
        need = max(0, count - seeds - len(my_tiles))
        if need > 0 and money > MONEY_FLOOR + need * SEED_COST and _room(market) > 0:
            market.append(["BUY_SEED", "MELON", need])
            REPORT["seeds_bought"] += need
            changed = True

    # --- market: crew hires --------------------------------------------------
    want = PLANT_WORKERS if day == plant_day else TEND_WORKERS
    if (len(state["crew"]) < want and not state["hire_pending"]
            and _parent_hires(market) == 0 and _room(market) > 0):
        # Hire one worker per step (keeps the per-step market legible and the
        # detection above unambiguous).
        if money > MONEY_FLOOR + _hire_cost_today(farm):
            market.append(["HIRE"])
            state["hire_pending"] = True
            changed = True
        else:
            REPORT["declines"] += 1

    if changed:
        action = dict(action)
        action["market"] = market

    # --- workers: (re)build today's job queues once the crew is known --------
    # Rebuild when the crew membership changes mid-day (e.g. the second hire
    # lands a step after the first), not just on day rollover, so a late
    # worker is never left without a queue.
    if state["crew"] and (state["jobs_built_day"] != day
                          or tuple(state["crew"]) != state["jobs_built_crew"]):
        _build_jobs(state, farm["tiles"], plant_day, day, count, board, state["crew"])

    if not state["crew"]:
        return action

    commands = [action.get("farmer") or ["PASS"], *(action.get("hands") or [])]
    while len(commands) < len(hands) + 1:
        commands.append(["PASS"])
    for worker in state["crew"]:
        if worker >= len(commands):
            continue
        commands[worker] = _crew_command(state, worker, obs, farm, board,
                                         plant_day, day, count, seeds)
    action = dict(action)
    action["farmer"], action["hands"] = commands[0], commands[1:]
    return action
