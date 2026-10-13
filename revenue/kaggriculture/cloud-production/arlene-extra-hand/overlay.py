"""FLORA extra-hand economics overlay for the pinned Arlene frontier.

This file is appended to the unchanged vendored Arlene source by build.py.  It
uses only visible state, reserves the base route's current orders, and records
no concrete action beyond the current observation.
"""
import math as _eh_math

_EH_RESERVATIONS = {}
_EH_HIRED_DAY = {}
_EH_CROPS = {
    "WHEAT": (10, 2), "CARROT": (20, 2), "TOMATO": (50, 8),
    "STRAWBERRY": (100, 10), "MELON": (80, 10),
}
_EH_ANIMALS = {"GOOSE": (300, "EGG"), "COW": (400, "MILK"), "SHEEP": (500, "WOOL")}
_EH_PRODUCT = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}
_EH_SHOPS = {
    "BAKERY": ("EGG", "WHEAT"), "PIZZA_SHOP": ("MILK", "TOMATO", "WHEAT"),
    "BRUNCH_SPOT": ("EGG", "WHEAT", "STRAWBERRY"), "YARN_STORE": ("WOOL",),
    "ICE_CREAM_SHOP": ("STRAWBERRY", "MILK", "WHEAT"), "PET_CAFE": ("CARROT",),
    "SMOOTHIE_SHOP": ("STRAWBERRY", "MILK"),
    "FARMERS_MARKET": ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY"),
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
        if pos in occupied:
            occupied[pos] += 1
    return min(access, key=lambda p: (occupied[p], access.index(p)))


def _eh_spawn_after_base(obs, base):
    """Match engine order: unit moves resolve before same-turn HIRE spawning."""
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
        if order and order[0] == "HIRE":
            farm["hands"].append(list(_eh_spawn(farm, board)))
    return _eh_spawn(farm, board)


def _eh_shape(kind, x, threshold):
    x = max(0, x)
    if kind == "sqrt": return _eh_math.sqrt(x)
    if kind == "sq": return x * x
    if kind == "log": return _eh_math.log1p(x)
    if kind == "log10": return _eh_math.log10(1 + x)
    if kind == "hinge":
        u = x / max(1, threshold)
        return u + 8 * max(0, u - 1) ** 2
    return x


def _eh_price(item, inventory, market):
    base, threshold, low, low_target, high, high_target = _EH_PARAMS[item]
    patch = market.get("params", {}).get(item, {})
    base, threshold, anchor = patch.get("base", base), patch.get("T", threshold), patch.get("I0", 10000)
    low, high = patch.get("below_func", low), patch.get("above_func", high)
    low_target, high_target = patch.get("below_target", low_target), patch.get("above_target", high_target)
    below = inventory < anchor
    func, target = (low, low_target) if below else (high, high_target)
    movement = target * base * _eh_shape(func, abs(inventory - anchor), threshold) / max(1e-9, _eh_shape(func, threshold, threshold))
    return max(1, round(base + movement if below else base - movement))


def _eh_hire_cost(n):
    a, b = 1, 1
    for _ in range(int(n)):
        a, b = b, a + b
    return a


def _eh_visible_jobs(obs):
    me, day = int(obs.get("player", 0)), int(obs.get("day", 0))
    jobs = []
    for y, row in enumerate(obs["farms"][me]["tiles"]):
        for x, tile in enumerate(row):
            if not isinstance(tile, dict) or int(tile.get("yield_units", 0)) <= 0:
                continue
            if tile.get("animal") in _EH_PRODUCT:
                product = _EH_PRODUCT[tile["animal"]]
            elif tile.get("kind") == "PLANT" and tile.get("crop") in _EH_CROPS:
                if day - int(tile.get("planted_day", day)) < _EH_CROPS[tile["crop"]][1]:
                    continue
                product = tile["crop"]
            else:
                continue
            jobs.append({"target": (x, y), "product": product, "quantity": int(tile["yield_units"])})
    return jobs


def _eh_demand(obs, product, realization):
    now = int(obs["step"])
    ticks4 = max(0, (realization - 1) // 4 - (now - 1) // 4)
    ticks24 = max(0, (realization - 1) // 24 - (now - 1) // 24)
    units = 0 if product == "FERTILIZER" else ticks24
    for shop in obs.get("town", {}).get("unlocked_shops", []):
        goods = _EH_SHOPS.get(shop, ())
        if product in goods:
            units += ticks4 * (2 if len(goods) == 1 else 1)
    return units


def _eh_receipt(obs, plan, include_visible_supply):
    product, qty, step = plan["product"], plan["quantity"], plan["sale_step"]
    inventory = obs["market"]["inventory"][product] - _eh_demand(obs, product, step)
    if include_visible_supply:
        for job in _eh_visible_jobs(obs):
            if job["target"] != plan["target"] and job["product"] == product:
                for _ in range(job["quantity"]):
                    if _eh_price(product, inventory, obs["market"]) > 1:
                        inventory += 1
    total = 0
    for _ in range(qty):
        unit = _eh_price(product, inventory, obs["market"])
        total += unit
        # SORREL d93da3aa floor repair: revenue still carries at $1, but supply does not.
        if unit > 1:
            inventory += 1
    return total


def _eh_reserved_cash(obs, orders):
    """Conservatively retain all visible base-route commitments in execution order."""
    farm, market = obs["farms"][obs["player"]], obs["market"]
    cash, hires = float(farm["money"]), int(farm.get("hires_today", 0))
    inv = dict(market["inventory"])
    land_count = max(0, len(farm.get("unlocked_land", [])) - 1)
    for order in orders:
        if not order: continue
        op = order[0]
        if op == "HIRE":
            cash -= _eh_hire_cost(hires); hires += 1
        elif op == "BUY_LAND":
            cash -= (1000, 2000, 4000)[min(land_count, 2)]; land_count += 1
        elif op == "BUY_SEED" and order[1] in _EH_CROPS:
            cash -= _EH_CROPS[order[1]][0] * int(order[2])
        elif op == "BUY_ANIMAL" and order[1] in _EH_ANIMALS:
            cash -= _EH_ANIMALS[order[1]][0] * int(order[2])
        elif op == "BUY_PRODUCT" and order[1] in ("WHEAT", "FERTILIZER"):
            for _ in range(int(order[2])):
                cash -= _eh_price(order[1], inv[order[1]] - 1, market)
                inv[order[1]] -= 1
        # Do not finance commitments from same-turn sales: both seats quote before commits.
    return cash, hires


def _eh_future_market(step):
    try:
        route = _A.R[_A.cur]
        return route[step].get("market", []) if step < len(route) else []
    except Exception:
        return []


def _eh_has_future_base_hire(now, work_end):
    try:
        route = _A.R[_A.cur]
        return any(any(order and order[0] == "HIRE" for order in route[step].get("market", []))
                   for step in range(now + 1, min(work_end, len(route) - 1) + 1))
    except Exception:
        return True


def _eh_base_harvest_targets(obs, work_end):
    """Project only the pinned route's own same-day harvest claims."""
    try:
        now = int(obs["step"]); me = int(obs.get("player", 0))
        positions = [tuple(obs["farms"][me]["farmer"])] + [tuple(p) for p in obs["farms"][me].get("hands", [])]
        route = _A.R[_A.cur]
        claimed = set()
        move = {"NORTH": (0,-1), "SOUTH": (0,1), "EAST": (1,0), "WEST": (-1,0)}
        for step in range(now + 1, min(work_end, len(route) - 1) + 1):
            frame = route[step]
            actions = [frame.get("farmer", ["PASS"]), *frame.get("hands", [])]
            for index in range(min(len(positions), len(actions))):
                action = actions[index] or ["PASS"]
                if action[0] == "HARVEST":
                    claimed.add(positions[index])
                elif action[0] in move:
                    dx, dy = move[action[0]]
                    positions[index] = (positions[index][0] + dx, positions[index][1] + dy)
        return claimed
    except Exception:
        return set()


def _eh_choose(obs, base):
    now, me = int(obs["step"]), int(obs.get("player", 0))
    farm, private = obs["farms"][me], obs["private"]
    free_slots = MAX_ORDERS - len(base.get("market", []))
    cash, hires_after_base = _eh_reserved_cash(obs, base.get("market", []))
    hire_cost = _eh_hire_cost(hires_after_base)
    if free_slots < 1 or cash - 30 < hire_cost:
        return None
    board, work_end = len(farm["tiles"]), min(718, (now // 24 + 1) * 24 - 1)
    # Inserting before a later route hire would shift all recorded hand indices.
    if _eh_has_future_base_hire(now, work_end):
        return None
    claimed = _eh_base_harvest_targets(obs, work_end)
    spawn = _eh_spawn_after_base(obs, base)
    homes = [(board//2-1, board//2-1), (board//2, board//2-1),
             (board//2-1, board//2), (board//2, board//2)]
    shed_used = sum(private["shed"].values()) + sum(sum(inv.values()) for inv in private.get("inventories", []))
    best = None
    for job in _eh_visible_jobs(obs):
        if job["target"] in claimed:
            continue
        if any(tuple(pos) == job["target"] for pos in [farm["farmer"], *farm.get("hands", [])]):
            continue
        distance_out = _eh_distance(spawn, job["target"])
        existing = [_eh_distance(tuple(pos), job["target"])
                    for pos in [farm["farmer"], *farm.get("hands", [])]]
        if existing and distance_out >= min(existing):
            continue
        harvest = now + 1 + distance_out
        drop = harvest + 1 + min(_eh_distance(job["target"], home) for home in homes)
        if drop > work_end or shed_used + job["quantity"] > SHED_CAP:
            continue
        future = _eh_future_market(drop)
        if len(future) >= MAX_ORDERS and not any(o and o[0] == "SELL" and o[1] == job["product"] for o in future):
            continue
        plan = dict(job, observed_step=now, first_work_step=harvest,
                    last_work_step=drop, sale_step=drop)
        profits = [_eh_receipt(obs, plan, False) - hire_cost,
                   _eh_receipt(obs, plan, True) - hire_cost]
        score = min(profits)
        if score > 0 and (best is None or score > best[0]):
            best = (score, plan, hires_after_base)
    return best


def _eh_action(obs, hand_index):
    me, day = int(obs.get("player", 0)), int(obs.get("day", 0))
    rows = _EH_RESERVATIONS.setdefault(me, [])
    rows[:] = [row for row in rows if row["day"] == day]
    row = next((r for r in rows if r["hand_index"] == hand_index), None)
    if row is None:
        return None, None
    farm, private = obs["farms"][me], obs["private"]
    pos, inv = tuple(farm["hands"][hand_index]), private["inventories"][hand_index + 1]
    board = len(farm["tiles"]); h = board // 2
    homes = [(h-1,h-1),(h,h-1),(h-1,h),(h,h)]
    if inv.get(row["product"], 0):
        home = min(homes, key=lambda p: _eh_distance(pos, p))
        if pos == home:
            rows.remove(row)
            return ["DROP"], (row["product"], int(inv.get(row["product"], 0)))
        return _eh_toward(pos, home), None
    tile = farm["tiles"][row["target"][1]][row["target"][0]]
    if not isinstance(tile, dict) or int(tile.get("yield_units", 0)) <= 0:
        rows.remove(row)
        return None, None
    if pos == row["target"]:
        return ["HARVEST"], None
    return _eh_toward(pos, row["target"]), None


_EH_BASE_AGENT = agent


def agent(obs):
    """Run unchanged Arlene, then add only a funded, feasible extra hand."""
    base = _EH_BASE_AGENT(obs)
    try:
        me = int(obs.get("player", 0)); farm = obs["farms"][me]
        actions = [list(a) for a in base.get("hands", [])]
        while len(actions) < len(farm.get("hands", [])):
            actions.append(["PASS"])
        market = [list(o) for o in base.get("market", [])]
        sell_lot = None
        for index in range(len(farm.get("hands", []))):
            action, product = _eh_action(obs, index)
            if action is not None:
                actions[index] = action
            if product is not None:
                sell_lot = product
        if sell_lot is not None:
            sell_product, sell_quantity = sell_lot
            slot = next((i for i,o in enumerate(market) if o and o[0] == "SELL" and o[1] == sell_product), None)
            if slot is not None:
                market[slot][2] += sell_quantity
            elif len(market) < MAX_ORDERS:
                market.append(["SELL", sell_product, sell_quantity])
        day = int(obs.get("day", 0))
        if not _EH_RESERVATIONS.get(me) and _EH_HIRED_DAY.get(me) != day:
            chosen = _eh_choose(obs, {"farmer": base.get("farmer", ["PASS"]),
                                      "hands": base.get("hands", []), "market": market})
            if chosen is not None and len(market) < MAX_ORDERS:
                _, plan, hires_after_base = chosen
                hand_index = len(farm.get("hands", [])) + sum(1 for o in market if o and o[0] == "HIRE")
                market.append(["HIRE"])
                _EH_HIRED_DAY[me] = day
                _EH_RESERVATIONS.setdefault(me, []).append(dict(
                    plan, day=day, hand_index=hand_index,
                    expected_hire_ordinal=hires_after_base))
        return {"farmer": base.get("farmer", ["PASS"]), "hands": actions, "market": market[:MAX_ORDERS]}
    except Exception:
        return base
