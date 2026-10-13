# SPDX-License-Identifier: Apache-2.0
"""V3.1 endgame fertilizer hand: one extra farm hand that fertilizes young annual crops.

Seen on the live ladder: senkin13 and Syed Asad Ali play our exact Shop Router tape plus one
extra HIRE on days 24-27; the extra hand picks up FERTILIZER at the shed and fertilizes the
tape's young CARROTs before their yield-bearing WATER (+1 carrot per tile; +13 carrots at
~$608 in episode 107763377).

Pinned-engine facts this relies on (kaggriculture.py): hands reset at every end of day, the
n-th hire of a day costs fib(n) (the tape already hires 12-14 a day in the endgame, so the
extra hand costs 233-610); FERTILIZE covers day..day+2; an annual crop's WATER adds 2 instead
of 1 inside [(max_yield_day+1)//2, max_yield_day] when fertilized, capped at max_yield (CARROT:
1 at planting, +1 per window WATER, cap 4, so one fertilizer before the first window WATER is
+1 unit). Units never collide; a new hand spawns on the least-occupied shed-access tile.

The wrapper keeps the parent stack blind to the extra hand: the parent sees the observation
without that hand (hands list and its inventory removed) and its commands are re-indexed
around it, so every authored route, queue and V219/V233 hand count stays the parent's. The
hire goes out only at a step where the parent hires nobody and the authored tape hires nobody
later that day, and only when today's expected carrot gain clearly beats the hire price. The
hand does one PICKUP at its spawn tile (fertilizer is bought first when the shed is short),
then leaves the shed-access tiles for the rest of the day. Everything fails closed to the
parent action.
"""

from __future__ import annotations

KEY = "r04_fert_hand"
FERT_HAND = False
DAYS = (24, 25, 26, 27, 28)
HIRE_HOUR = 3
CROPS = ("CARROT",)
PRICE_KEEP = 0.8       # extra units sell below today's quote; keep this share of it
REACH = 6              # targets one hand serves in a day (measured: 4-5 on d25, spread tiles)
MIN_GAIN = 100         # expected day gain above the hire price, at least
GAIN_RATIO = 1.2       # expected day gain at least this multiple of the hire price
MAX_ORDERS = 10
TURNS_PER_DAY = 24
DEBUG = None           # optional list; decisions are appended when set

CROP_DATA = {
    "WHEAT": (2, 4, 6),       # first_yield_day, max_yield_day, max_yield (pinned engine)
    "CARROT": (2, 3, 4),
    "MELON": (10, 12, 6),
}

_STATE = {}
REPORT = {"hires": 0, "hire_failures": 0, "pickups": 0, "fertilized": 0, "declined": 0, "bought": 0}


def _fib(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def _shed_tiles(board):
    half = board // 2
    return {(half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half)}


class _Day:
    def __init__(self, day):
        self.day = day
        self.index = None          # our hand's index in farm["hands"]
        self.pending = None        # hands count when our HIRE was issued
        self.tried = False
        self.picked = False
        self.want = 0
        self.last_step = -1


def _gain(tile, day):
    """Extra units from fertilizing this PLANT tile today (0 when it cannot pay)."""
    if not isinstance(tile, dict) or tile.get("kind") != "PLANT" or tile.get("crop") not in CROPS:
        return 0
    first, last, cap = CROP_DATA[tile["crop"]]
    planted = int(tile.get("planted_day", -99))
    start = planted + (last + 1) // 2
    end = planted + last
    watered = bool(tile.get("watered_today"))
    waters = [w for w in range(start, end + 1) if w > day or (w == day and not watered)]
    if not waters:
        return 0
    covered = int(tile.get("fertilized_until_day", -1))
    have = int(tile.get("yield_units", 0))
    base = min(cap, have + sum(2 if w <= covered else 1 for w in waters))
    cover = max(covered, day + 2)
    fert = min(cap, have + sum(2 if w <= cover else 1 for w in waters))
    return max(0, fert - base)


def _targets(tiles, day):
    out = []
    for y, row in enumerate(tiles):
        for x, tile in enumerate(row):
            g = _gain(tile, day)
            if g > 0:
                out.append((x, y, g))
    return out


def _rest_of_day(tape, step):
    if tape is None:
        return []
    end = (step // TURNS_PER_DAY + 1) * TURNS_PER_DAY
    return tape[step + 1:min(end, len(tape))]


def _future_plantings(tape, step):
    """Authored PLANT commands of our crops for the rest of today."""
    n = 0
    for a in _rest_of_day(tape, step):
        for c in [a.get("farmer")] + list(a.get("hands") or []):
            if c and c[0] == "PLANT" and len(c) > 1 and c[1] in CROPS:
                n += 1
    return n


def _future_fert_pickups(tape, step):
    n = 0
    for a in _rest_of_day(tape, step):
        for c in [a.get("farmer")] + list(a.get("hands") or []):
            if c and c[0] == "PICKUP" and len(c) > 1 and c[1] == "FERTILIZER":
                n += int(c[2]) if len(c) > 2 else 1
    return n


def _future_hires(tape, step):
    return any(o and o[0] == "HIRE" for a in _rest_of_day(tape, step) for o in a.get("market", []))


def _step_toward(pos, target, avoid):
    x, y = pos
    tx, ty = target
    options = []
    if tx > x:
        options.append(("EAST", (x + 1, y)))
    if tx < x:
        options.append(("WEST", (x - 1, y)))
    if ty > y:
        options.append(("SOUTH", (x, y + 1)))
    if ty < y:
        options.append(("NORTH", (x, y - 1)))
    if not options:
        return ["PASS"]
    options.sort(key=lambda o: o[1] in avoid)
    return [options[0][0]]


def _leave_shed(pos, board, avoid):
    x, y = pos
    for name, (dx, dy) in (("NORTH", (0, -1)), ("WEST", (-1, 0)), ("SOUTH", (0, 1)), ("EAST", (1, 0))):
        nx, ny = x + dx, y + dy
        if 0 <= nx < board and 0 <= ny < board and (nx, ny) not in avoid:
            return [name]
    return ["PASS"]


def _parent_view(observation, index):
    obs = dict(observation)
    player = int(observation["player"])
    farms = list(observation["farms"])
    farm = dict(farms[player])
    hands = list(farm["hands"])
    del hands[index]
    farm["hands"] = hands
    farms[player] = farm
    obs["farms"] = farms
    private = dict(observation["private"])
    inventories = list(private["inventories"])
    if index + 1 < len(inventories):
        del inventories[index + 1]
    private["inventories"] = inventories
    obs["private"] = private
    return obs


def _upcoming(observation, action, index):
    """Tiles a parent unit plants with one of our crops this step (they become targets next step)."""
    farm = observation["farms"][int(observation["player"])]
    units = [(farm["farmer"], action.get("farmer"))]
    for k, command in enumerate(action.get("hands") or []):
        real = k if k < index else k + 1
        if real < len(farm["hands"]):
            units.append((farm["hands"][real], command))
    out = []
    for pos, command in units:
        if command and command[0] == "PLANT" and len(command) > 1 and command[1] in CROPS:
            x, y = pos
            if farm["tiles"][y][x] is None:
                out.append((x, y, 1))
    return out


def _hand_command(observation, st, tape, upcoming=()):
    player = int(observation["player"])
    farm = observation["farms"][player]
    tiles = farm["tiles"]
    board = len(tiles)
    step = int(observation["step"])
    day = step // TURNS_PER_DAY
    pos = tuple(farm["hands"][st.index])
    inventories = observation["private"]["inventories"]
    inv = inventories[st.index + 1] if st.index + 1 < len(inventories) else {}
    held = int(inv.get("FERTILIZER", 0))
    sheds = _shed_tiles(board)
    targets = _targets(tiles, day)
    if not st.picked:
        st.picked = True
        if pos in sheds:
            shed = int(observation["private"]["shed"].get("FERTILIZER", 0))
            n = min(st.want, shed - _future_fert_pickups(tape, step))
            if n > 0:
                REPORT["pickups"] += n
                return ["PICKUP", "FERTILIZER", n]
    if pos in sheds:
        return _leave_shed(pos, board, sheds)
    if held <= 0:
        return ["PASS"]
    if any((t[0], t[1]) == pos for t in targets):
        REPORT["fertilized"] += 1
        return ["FERTILIZE"]
    goals = targets + [u for u in upcoming if (u[0], u[1]) != pos]
    if not goals:
        return ["PASS"]
    tx, ty, _ = min(goals, key=lambda t: (abs(t[0] - pos[0]) + abs(t[1] - pos[1]), -t[2], t[1], t[0]))
    return _step_toward(pos, (tx, ty), sheds)


def _consider_hire(observation, action, st, tape, farm, hands, day, step):
    market = [list(o) for o in (action.get("market") or []) if o]
    if any(o[0] == "HIRE" for o in market) or len(market) >= MAX_ORDERS - 1:
        return action
    if _future_hires(tape, step):
        return action
    st.tried = True
    prices = (observation.get("market") or {}).get("prices") or {}
    fert_price = float(prices.get("FERTILIZER", 0) or 0)
    crop_price = min(float(prices.get(c, 0) or 0) for c in CROPS)
    edge = crop_price * PRICE_KEEP - fert_price
    targets = len(_targets(farm["tiles"], day)) + _future_plantings(tape, step)
    units = min(targets, REACH)
    cost = _fib(int(farm.get("hires_today", 0)))
    gain = units * edge
    ok = (units > 0 and gain - cost >= MIN_GAIN and gain >= GAIN_RATIO * cost
          and float(farm.get("money", 0)) >= cost + units * fert_price + 100)
    if DEBUG is not None:
        DEBUG.append({"step": step, "day": day, "crop_price": crop_price, "fert_price": fert_price,
                      "targets": targets, "cost": cost, "gain": round(gain), "hire": ok})
    if not ok:
        REPORT["declined"] += 1
        return action
    shed = int(observation["private"]["shed"].get("FERTILIZER", 0))
    short = units - (shed - _future_fert_pickups(tape, step))
    action = dict(action)
    extra = [["HIRE"]]
    if short > 0 and len(market) + 2 <= MAX_ORDERS:
        extra.append(["BUY_PRODUCT", "FERTILIZER", short])
        REPORT["bought"] += short
    action["market"] = market + extra
    st.pending = len(hands)
    st.want = units
    return action


def wrap(parent, tape_of=None):
    """Return an agent that runs `parent` and adds the endgame fertilizer hand.

    `tape_of(observation)` returns the authored tape the parent follows (or None); it is used to
    count today's remaining authored plantings, fertilizer pickups and hires.
    """

    def agent(observation, configuration=None):
        if not FERT_HAND:
            return parent(observation, configuration)
        try:
            player = int(observation["player"])
            step = int(observation["step"])
            farm = observation["farms"][player]
        except Exception:
            return parent(observation, configuration)
        day = step // TURNS_PER_DAY
        st = _STATE.get(player)
        if st is None or st.day != day or step <= st.last_step:
            st = _STATE[player] = _Day(day)
        st.last_step = step
        hands = farm.get("hands") or []
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
            action = parent(_parent_view(observation, st.index), configuration)
            try:
                command = _hand_command(observation, st, tape, _upcoming(observation, action, st.index))
            except Exception:
                command = ["PASS"]
            action = dict(action)
            inner = list(action.get("hands") or [])
            while len(inner) < st.index:
                inner.append(["PASS"])
            inner.insert(st.index, command)
            action["hands"] = inner
            return action
        action = parent(observation, configuration)
        if st.tried or day not in DAYS or step % TURNS_PER_DAY < HIRE_HOUR or step >= 717:
            return action
        try:
            return _consider_hire(observation, action, st, tape, farm, hands, day, step)
        except Exception:
            return action

    return agent
