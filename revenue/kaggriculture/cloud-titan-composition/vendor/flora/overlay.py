"""Research-only lost-production extra-hand overlay for exact pinned Arlene."""
import math as _eh_math

_EH_RESERVATIONS = {}
_EH_HIRED_DAY = {}
_EH_CROPS = {
    "WHEAT": (10, 2), "CARROT": (20, 2), "TOMATO": (50, 8),
    "STRAWBERRY": (100, 10), "MELON": (80, 10),
}
_EH_ANIMALS = {
    "GOOSE": {"first": 4, "interval": 1, "max": 4, "product": "EGG"},
    "COW": {"first": 8, "interval": 2, "max": 6, "product": "MILK"},
    "SHEEP": {"first": 6, "interval": 3, "max": 6, "product": "WOOL"},
}
_EH_PARAMS = {
    "WHEAT": (25, 400, "sqrt", .8, "log", .2),
    "CARROT": (35, 450, "hinge", 1., "sqrt", .7),
    "TOMATO": (60, 200, "hinge", .4, "sqrt", .6),
    "STRAWBERRY": (120, 100, "sqrt", .7, "linear", 1.6),
    "MELON": (250, 300, "log", .2, "sq", 3.6),
    "EGG": (50, 332, "hinge", .4, "log", .2),
    "MILK": (160, 122, "sqrt", .6, "linear", 1.6),
    "WOOL": (200, 105, "log", .2, "sq", 3.2),
    "FERTILIZER": (100, 200, "linear", .4, "linear", .4),
}


def _eh_distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _eh_toward(pos, target):
    if pos[0] < target[0]: return ["EAST"]
    if pos[0] > target[0]: return ["WEST"]
    if pos[1] < target[1]: return ["SOUTH"]
    if pos[1] > target[1]: return ["NORTH"]
    return ["PASS"]


def _eh_spawn(farm, board):
    h = board // 2
    access = [(h - 1, h - 1), (h, h - 1), (h - 1, h), (h, h)]
    occupied = {p: 0 for p in access}
    for raw in [farm["farmer"], *farm.get("hands", [])]:
        pos = tuple(raw)
        if pos in occupied: occupied[pos] += 1
    return min(access, key=lambda p: (occupied[p], access.index(p)))


def _eh_spawn_after_base(obs, base):
    """HIRE happens after current unit moves and preceding market HIREs."""
    me = int(obs.get("player", 0)); source = obs["farms"][me]
    farm = {"farmer": list(source["farmer"]), "hands": [list(p) for p in source.get("hands", [])]}
    positions = [farm["farmer"], *farm["hands"]]
    actions = [base.get("farmer", ["PASS"]), *base.get("hands", [])]
    moves = {"NORTH": (0,-1), "SOUTH": (0,1), "EAST": (1,0), "WEST": (-1,0)}
    board = len(source["tiles"])
    for index in range(min(len(positions), len(actions))):
        action = actions[index] or ["PASS"]
        if action[0] in moves:
            dx, dy = moves[action[0]]; x, y = positions[index]
            if 0 <= x + dx < board and 0 <= y + dy < board:
                positions[index][:] = [x + dx, y + dy]
    for order in base.get("market", []):
        if order and order[0] == "HIRE": farm["hands"].append(list(_eh_spawn(farm, board)))
    return _eh_spawn(farm, board)


def _eh_shape(kind, x, threshold):
    x = max(0, x)
    if kind == "sqrt": return _eh_math.sqrt(x)
    if kind == "sq": return x * x
    if kind == "log": return _eh_math.log1p(x)
    if kind == "hinge":
        u = x / max(1, threshold)
        return u + 8 * max(0, u - 1) ** 2
    return x


def _eh_price(item, inventory, market):
    base, threshold, low, low_target, high, high_target = _EH_PARAMS[item]
    patch = market.get("params", {}).get(item, {})
    base, threshold, anchor = patch.get("base", base), patch.get("T", threshold), patch.get("I0", 10000)
    func, target = (patch.get("below_func", low), patch.get("below_target", low_target)) if inventory < anchor else (patch.get("above_func", high), patch.get("above_target", high_target))
    movement = target * base * _eh_shape(func, abs(inventory - anchor), threshold) / max(1e-9, _eh_shape(func, threshold, threshold))
    return max(1, round(base + movement if inventory < anchor else base - movement))


def _eh_sale_value(item, units, market):
    """Current-book proceeds with the engine's per-unit repricing semantics.

    A unit quoted at the price floor earns one dollar but is not admitted to
    market inventory, so it must not depress later units in this projection.
    """
    inventory = int(market["inventory"].get(item, 0))
    total = 0
    for _ in range(max(0, int(units))):
        unit = _eh_price(item, inventory, market)
        total += unit
        if unit > 1:
            inventory += 1
    return total


def _eh_hire_cost(n):
    a, b = 1, 1
    for _ in range(int(n)): a, b = b, a + b
    return a


def _eh_reserved_cash(obs, orders):
    """Reserve base commitments sequentially; same-turn sales never pre-fund buys."""
    farm, market = obs["farms"][obs["player"]], obs["market"]
    cash, hires = float(farm["money"]), int(farm.get("hires_today", 0))
    inv = dict(market["inventory"]); land_count = max(0, len(farm.get("unlocked_land", [])) - 1)
    animal_cost = {"GOOSE": 300, "COW": 400, "SHEEP": 500}
    for order in orders:
        if not order: continue
        op = order[0]
        if op == "HIRE": cash -= _eh_hire_cost(hires); hires += 1
        elif op == "BUY_LAND": cash -= (1000, 2000, 4000)[min(land_count, 2)]; land_count += 1
        elif op == "BUY_SEED" and order[1] in _EH_CROPS: cash -= _EH_CROPS[order[1]][0] * int(order[2])
        elif op == "BUY_ANIMAL" and order[1] in animal_cost: cash -= animal_cost[order[1]] * int(order[2])
        elif op == "BUY_PRODUCT" and order[1] in ("WHEAT", "FERTILIZER"):
            for _ in range(int(order[2])):
                cash -= _eh_price(order[1], inv[order[1]] - 1, market); inv[order[1]] -= 1
    return cash, hires


def _eh_next_decay(tile, now):
    mls = int(tile.get("max_lifespan_step", -1))
    if mls < 0: return None
    first = max(now + 1, mls)
    return first if (first - mls) % 2 == 0 else first + 1


def _eh_incremental_jobs(obs, work_end):
    """Only cap overflow at tonight refresh or crop units decaying this day."""
    me, day, now = int(obs.get("player", 0)), int(obs.get("day", 0)), int(obs["step"])
    jobs = []
    for y, row in enumerate(obs["farms"][me]["tiles"]):
        for x, tile in enumerate(row):
            if not isinstance(tile, dict): continue
            held = int(tile.get("yield_units", 0))
            animal = tile.get("animal")
            if animal in _EH_ANIMALS and held > 0:
                spec = _EH_ANIMALS[animal]
                since = day + 1 - int(tile.get("placed_day", day)) - spec["first"]
                escapes = not tile.get("fed_today", False) and int(tile.get("consecutive_unfed", 0)) + 1 >= 2
                if since >= 0 and since % spec["interval"] == 0 and not escapes:
                    produced = 1 + (int(tile.get("pending_care_bonus", 0)) if tile.get("fed_today", False) else 0)
                    lost = max(0, held + produced - spec["max"])
                    if lost:
                        jobs.append({"id": f"animal:{x}:{y}:{now}", "kind": "animal_overflow", "target": (x,y),
                                     "product": spec["product"], "harvest_units": held, "economic_units": lost,
                                     "deadline": work_end, "requirements": []})
            elif tile.get("kind") == "PLANT" and held > 0:
                decay = _eh_next_decay(tile, now)
                if decay is not None and decay <= work_end:
                    jobs.append({"id": f"crop:{x}:{y}:{now}", "kind": "crop_decay", "target": (x,y),
                                 "product": tile.get("crop"), "harvest_units": held, "economic_units": 1,
                                 "deadline": decay, "requirements": []})
    return jobs


def _eh_base_harvest_steps(obs, base, work_end):
    """Project current base action plus pinned route actions through this day."""
    try:
        now = int(obs["step"]); me = int(obs.get("player", 0))
        positions = [tuple(obs["farms"][me]["farmer"])] + [tuple(p) for p in obs["farms"][me].get("hands", [])]
        route = _A.R[_A.cur]; claimed = {}
        move = {"NORTH": (0,-1), "SOUTH": (0,1), "EAST": (1,0), "WEST": (-1,0)}
        for step in range(now, min(work_end, len(route) - 1) + 1):
            frame = base if step == now else route[step]
            actions = [frame.get("farmer", ["PASS"]), *frame.get("hands", [])]
            for index in range(min(len(positions), len(actions))):
                action = actions[index] or ["PASS"]
                if action[0] == "HARVEST" and positions[index] not in claimed:
                    claimed[positions[index]] = step
                elif action[0] in move:
                    dx, dy = move[action[0]]; positions[index] = (positions[index][0]+dx, positions[index][1]+dy)
        return claimed
    except Exception:
        return set()


def _eh_base_harvest_commitment(obs, base, work_end):
    """Units the intact route will add before this day's automatic deposit."""
    claimed = _eh_base_harvest_steps(obs, base, work_end)
    tiles = obs["farms"][int(obs.get("player", 0))]["tiles"]
    total = 0
    for x, y in claimed:
        tile = tiles[y][x]
        if isinstance(tile, dict):
            total += max(0, int(tile.get("yield_units", 0)))
    return total


def _eh_has_future_base_hire(now, work_end):
    try:
        route = _A.R[_A.cur]
        return any(any(o and o[0] == "HIRE" for o in route[s].get("market", [])) for s in range(now+1, min(work_end, len(route)-1)+1))
    except Exception:
        return True


def _eh_choose(obs, base):
    now, me, day = int(obs["step"]), int(obs.get("player", 0)), int(obs.get("day", 0))
    farm, private = obs["farms"][me], obs["private"]
    if day >= 29 or len(base.get("market", [])) >= MAX_ORDERS: return None
    cash, hires = _eh_reserved_cash(obs, base.get("market", [])); wage = _eh_hire_cost(hires)
    if cash - 30 < wage: return None
    work_end = (now // 24 + 1) * 24 - 1
    if _eh_has_future_base_hire(now, work_end): return None
    base_harvest = _eh_base_harvest_steps(obs, base, work_end); spawn = _eh_spawn_after_base(obs, base)
    shed_claim = (sum(private["shed"].values())
                  + sum(sum(inv.values()) for inv in private.get("inventories", []))
                  + _eh_base_harvest_commitment(obs, base, work_end))
    candidates = []
    for job in _eh_incremental_jobs(obs, work_end):
        base_step = base_harvest.get(job["target"])
        if job["kind"] == "animal_overflow" and base_step is not None:
            continue
        if job["kind"] == "crop_decay":
            last_decay = min(work_end, (base_step - 1) if base_step is not None else work_end)
            if last_decay < job["deadline"]: continue
            job["economic_units"] = min(job["harvest_units"], 1 + (last_decay - job["deadline"]) // 2)
        distance = _eh_distance(spawn, job["target"]); harvest_step = now + 1 + distance
        if harvest_step > job["deadline"] or shed_claim + job["harvest_units"] > SHED_CAP: continue
        incremental_value = _eh_sale_value(job["product"], job["economic_units"], obs["market"])
        if incremental_value <= wage: continue
        candidates.append(dict(job, start_step=now+1, end_step=harvest_step,
                               value=int(incremental_value-wage), observed_step=now,
                               expected_hire_ordinal=hires))
    supplies = [(now, product, qty, "shed") for product, qty in private["shed"].items()]
    picked = select_optional_jobs(candidates, supplies, max_jobs=1)
    return picked[0] if picked else None


def _eh_action(obs, hand_index):
    me, day = int(obs.get("player", 0)), int(obs.get("day", 0))
    rows = _EH_RESERVATIONS.setdefault(me, []); rows[:] = [r for r in rows if r["day"] == day]
    row = next((r for r in rows if r["hand_index"] == hand_index), None)
    if row is None: return None
    farm, private = obs["farms"][me], obs["private"]
    pos = tuple(farm["hands"][hand_index]); inv = private["inventories"][hand_index+1]
    if inv.get(row["product"], 0): return ["PASS"]  # exact EOD auto-deposit, from any position
    tile = farm["tiles"][row["target"][1]][row["target"][0]]
    if not isinstance(tile, dict) or int(tile.get("yield_units", 0)) <= 0:
        rows.remove(row); return None
    if pos == row["target"]: return ["HARVEST"]
    return _eh_toward(pos, row["target"])


_EH_BASE_AGENT = agent


def agent(obs):
    """Run intact Arlene, adding at most one proved-incremental harvest hand/day."""
    base = _EH_BASE_AGENT(obs)
    try:
        me = int(obs.get("player", 0)); farm = obs["farms"][me]
        actions = [list(a) for a in base.get("hands", [])]
        while len(actions) < len(farm.get("hands", [])): actions.append(["PASS"])
        for index in range(len(farm.get("hands", []))):
            action = _eh_action(obs, index)
            if action is not None: actions[index] = action
        market = [list(o) for o in base.get("market", [])]; day = int(obs.get("day", 0))
        if not _EH_RESERVATIONS.get(me) and _EH_HIRED_DAY.get(me) != day:
            chosen = _eh_choose(obs, {"farmer": base.get("farmer", ["PASS"]), "hands": base.get("hands", []), "market": market})
            if chosen is not None and len(market) < MAX_ORDERS:
                hand_index = len(farm.get("hands", [])) + sum(1 for o in market if o and o[0] == "HIRE")
                market.append(["HIRE"]); _EH_HIRED_DAY[me] = day
                _EH_RESERVATIONS.setdefault(me, []).append(dict(chosen, day=day, hand_index=hand_index))
        return {"farmer": base.get("farmer", ["PASS"]), "hands": actions, "market": market[:MAX_ORDERS]}
    except Exception:
        return base
