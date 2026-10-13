"""Observation digest, explicit joint-turn rules, and prompt assembly.

The digest compresses the fields the engine's own gates read. It does not
pre-decide: every admissible op stays reachable and the accepted list is printed
in full with its quantity domains.

Only player-visible fields reach the model. The episode seed, the opponent's
private state, and the card wrapper's capture metadata are excluded by
construction (`constraints.visible_config`) and asserted by
`tests/test_joint_turn.py::test_no_leakage`.

The operator surface is placed FIRST, before the state: a constraint framework
shapes everything after it, so it leads the prompt.
"""

from constraints import engine


def _tile_str(tile, day):
    if tile is None:
        return "empty"
    if tile == "LOCKED":
        return "LOCKED"
    if not isinstance(tile, dict):
        return str(tile)
    K = engine()
    kind = tile.get("kind")
    if kind == "PLANT":
        crop = tile["crop"]
        cd = K.CROPS[crop]
        age = day - tile["planted_day"]
        bits = [f"PLANT {crop}", f"age{age}d", f"ripe_at{cd['first_yield_day']}d",
                f"yield{tile.get('yield_units', 0)}"]
        bits.append("watered_today" if tile.get("watered_today") else "not_watered_today")
        if tile.get("fertilized_until_day", -1) >= day:
            bits.append("fertilized")
        return " ".join(bits)
    if "animal" in tile:
        bits = [f"{tile['animal']} on {kind}", f"yield{tile.get('yield_units', 0)}"]
        bits.append("fed_today" if tile.get("fed_today") else "not_fed_today")
        bits.append("cared_today" if tile.get("cared_today") else "not_cared_today")
        if tile.get("fertilizer_available"):
            bits.append("fertilizer_ready")
        return " ".join(bits)
    return str(kind)


def digest(obs, config, seat):
    K = engine()
    day, hour = int(obs["day"]), int(obs["hour"])
    farm = obs["farms"][seat]
    priv = obs["private"]
    cap = int(config.get("shedCapacity", 100) or 100)
    shed = priv.get("shed", {})
    used = sum(shed.values())
    tiles = farm["tiles"]

    lines = [f"day {day} hour {hour} money {int(farm['money'])}"]
    units = [("farmer", farm["farmer"])] + [(f"hand{i}", p) for i, p in enumerate(farm.get("hands", []))]
    invs = priv.get("inventories", [])
    for i, (label, pos) in enumerate(units):
        x, y = int(pos[0]), int(pos[1])
        held = invs[i] if i < len(invs) else {}
        held_s = ",".join(f"{k}{v}" for k, v in sorted(held.items()) if v) or "nothing"
        # Carried goods are in the unit's hands and are NOT the tile it stands on;
        # conflating the two is what made a carried CARROT2 read as the age-0 plant.
        lines.append(f"{label} at ({x},{y}); TILE UNDER IT = [{_tile_str(tiles[y][x], day)}]; "
                     f"CARRIED IN HAND (not on the tile) = {held_s}")
    seeds = ",".join(f"{k}{v}" for k, v in sorted(priv.get("seeds", {}).items()) if v) or "-"
    lines.append(f"seeds {seeds}")
    shed_s = ",".join(f"{k}{v}" for k, v in sorted(shed.items()) if v) or "-"
    lines.append(f"shed {shed_s} ({used}/{cap} used, {max(0, cap - used)} room)")
    prices = obs["market"].get("prices") or {}
    if not prices:
        prices = {p: K.market_price(p, obs["market"]["inventory"][p], obs["market"].get("params"))
                  for p in K.PRODUCTS}
    lines.append("sell prices " + ",".join(f"{k}{int(round(v))}" for k, v in sorted(prices.items())))
    shops = obs.get("town", {}).get("unlocked_shops", [])
    lines.append("town shops " + (",".join(sorted(shops)) if shops else "none"))
    return "\n".join(lines)


def rules_block(adm):
    """The turn-level engine rules, stated explicitly. Stated, never applied for the model."""
    r = adm["rules"]
    plant = ",".join(f"{k}{v}" for k, v in sorted(r["plant_budget"].items()) if v) or "none"
    out = [
        f"units this turn: {r['units']} (farmer" +
        (f" + {r['units'] - 1} hand(s))" if r["units"] > 1 else " only)"),
        f"PLANT budget is JOINT across farmer and hands: seeds {plant}. If PLANT requests "
        f"for one crop exceed its seed count, the engine turns ALL of them into PASS.",
        "ORDER: every unit action resolves BEFORE any market order. So goods dropped "
        "into the shed this turn CAN be sold this turn; a seed bought this turn CANNOT "
        "be planted until the next turn.",
        f"market orders run in sequence sharing one cash balance and {r['shed_room']} "
        f"shed room, repricing after each unit; at most {r['max_market_orders']} orders.",
    ]
    if r["end_of_day_this_turn"]:
        out.append("END OF DAY fires after this turn: carried goods drop to the shed and "
                   "ANY OVERFLOW ABOVE CAPACITY IS DISCARDED, hired hands are removed, and "
                   "the farmer respawns at the default tile.")
    else:
        out.append(f"end of day is not this turn (hour {r['hour']} of {r['turns_per_day']}).")
    if r["last_turn_of_episode"]:
        out.append("LAST TURN: the score is cash only. Stock left in the shed is worth nothing.")
    return "\n".join(out)


TILE_OPS = {"WATER", "HARVEST", "DIG", "FERTILIZE", "FEED", "CARE",
            "COLLECT_FERTILIZER", "BUILD_COOP", "BUILD_PASTURE", "PLANT"}

# What each op actually does, where the engine's behaviour is easy to misread.
OP_NOTE = {
    "CARE": ("sets cared_today only; the care bonus is granted at the daily refresh "
             "ONLY if this animal was ALSO fed today"),
    "FEED": "consumes 1 WHEAT carried by THIS unit; feeds the animal on its tile",
    "COLLECT_FERTILIZER": "takes the fertilizer this animal has ready",
    "DIG": "removes a plant, a weed, or an EMPTY coop/pasture; it does NOT remove an installed animal",
}


MOVES = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0)}


def _move_dest(op, obs, seat, unit_idx):
    """The tile a move lands on. Movement was rendered as a bare compass word, so a
    worker sharing another worker's tile could not see where else it could work."""
    farm = obs["farms"][seat]
    positions = [farm["farmer"]] + list(farm.get("hands", []))
    p = positions[unit_idx] if unit_idx < len(positions) else farm["farmer"]
    dx, dy = MOVES[op]
    x, y = int(p[0]) + dx, int(p[1]) + dy
    n = len(farm["tiles"])
    if not (0 <= x < n and 0 <= y < n):
        return "off the board"
    here = [lbl for lbl, q in
            zip(["farmer"] + [f"hand{k}" for k in range(len(positions) - 1)], positions)
            if (int(q[0]), int(q[1])) == (x, y)]
    desc = _tile_str(farm["tiles"][y][x], int(obs["day"]))
    return (f"to ({x},{y}) {desc}"
            + (f", where {', '.join(here)} already stands" if here else ""))


def _place_effect(item, obs, seat, unit_idx):
    """PLACE is conditional: install an animal, or deposit into the shed.

    The engine tries the animal-install branch first -- the unit must stand on a
    matching UNOCCUPIED structure -- and only falls through to the shed deposit. A
    flat 'into the shed' label is wrong for the install case, and it is also what a
    second unit sharing the first unit's pasture actually gets.
    """
    from constraints import engine
    K = engine()
    farm = obs["farms"][seat]
    positions = [farm["farmer"]] + list(farm.get("hands", []))
    p = positions[unit_idx] if unit_idx < len(positions) else farm["farmer"]
    x, y = int(p[0]), int(p[1])
    tile = farm["tiles"][y][x]
    if item in K.ANIMALS:
        struct = K.ANIMALS[item]["structure"]
        if isinstance(tile, dict) and tile.get("kind") == struct and "animal" not in tile:
            return f"INSTALLS the {item} on this empty {struct}"
        if isinstance(tile, dict) and tile.get("kind") == struct:
            return (f"this {struct} is already occupied, so this only DEPOSITS the "
                    f"{item} into the shed as stock")
        return (f"not standing on an empty {struct}, so this DEPOSITS the {item} into "
                f"the shed as stock, not onto a pasture")
    return "deposits what this unit carries into the shed"


def accepted_block(adm, obs=None, seat=0):
    """The accepted set, with each tile op annotated by WHAT IT ACTS ON.

    Without this the model read "weeds to DIG (3,4)" on the map and emitted DIG while
    standing on its own healthy carrot at (4,4), destroying it. A tile op always acts
    on the tile the unit occupies, never on the tile the map happens to mention.
    """
    out = []
    labels = ["farmer"] + [f"hands[{i}]" for i in range(len(adm["units"]) - 1)]
    targets = []
    earlier_on_tile = {}
    if obs is not None:
        _farm = obs["farms"][seat]
        _poss = [_farm["farmer"]] + list(_farm.get("hands", []))
        _labels = ["farmer"] + [f"hands[{k}]" for k in range(len(_poss) - 1)]
        _seen = {}
        for _i, _p in enumerate(_poss):
            _key = (int(_p[0]), int(_p[1]))
            if _key in _seen:
                earlier_on_tile[_i] = _seen[_key]
            else:
                _seen[_key] = _labels[_i]
    if obs is not None:
        farm = obs["farms"][seat]
        day = int(obs["day"])
        poss = [farm["farmer"]] + list(farm.get("hands", []))
        for p in poss:
            x, y = int(p[0]), int(p[1])
            targets.append(f"({x},{y}) {_tile_str(farm['tiles'][y][x], day)}")
    for i, (label, ops) in enumerate(zip(labels, adm["units"])):
        rendered = []
        q = adm["quantities"][i]
        tgt = targets[i] if i < len(targets) else None
        for op in ops:
            if op[0] == "PICKUP":
                rendered.append(f"PICKUP {op[1]} n<={q['PICKUP'].get(op[1], 1)}")
            elif op[0] == "PLACE":
                eff = _place_effect(op[1], obs, seat, i)
                if i in earlier_on_tile and "INSTALLS" in eff:
                    eff = (f"{earlier_on_tile[i]} is on this tile and acts first; if it "
                           f"installs here, this only DEPOSITS the {op[1]} into the shed")
                rendered.append(f"PLACE {op[1]} n<={q['PLACE_to_shed'].get(op[1], 1)} ({eff})")
            elif op[0] in TILE_OPS and tgt:
                note = OP_NOTE.get(op[0])
                order = (f"; {earlier_on_tile[i]} acts on this tile first -- a DIFFERENT "
                         f"action here still applies, the same action again does not") \
                    if i in earlier_on_tile else ""
                rendered.append(" ".join(str(t) for t in op) + f" (acts on {tgt}"
                                + (f"; {note}" if note else "") + order + ")")
            elif op[0] in MOVES and obs is not None:
                rendered.append(f"{op[0]} ({_move_dest(op[0], obs, seat, i)})")
            else:
                rendered.append(" ".join(str(t) for t in op))
        suffix = f"  [standing on {tgt}]" if tgt else ""
        out.append(f"{label}:{suffix} " + " | ".join(rendered))

    def _m(entries):
        return " | ".join(
            " ".join(m["order"]) + (f" n<={m['max_n']}" if m["max_n"] > 1 else "")
            for m in entries)

    out.append("market now: " + _m(adm["market"]))
    now = {tuple(m["order"]) for m in adm["market"]}
    extra = [m for m in adm["market_after_full_deposit"] if tuple(m["order"]) not in now]
    if extra:
        out.append("market also available if this turn deposits carried goods: " + _m(extra))
    return "\n".join(out)


def horizon_block(hz):
    """Production dates, decay clock, survival flag, cash-realization horizon.

    Facts the engine will apply, so the plan can weigh them. No move is recommended.
    """
    lines = [f"decisions left this episode: {hz['remaining_decisions']} "
             f"(last is step {hz['last_decision_step']}); "
             f"{hz['turns_left_today']} turn(s) left today"]
    if not hz["plants"]:
        lines.append("no plants owned")
        return "\n".join(lines)
    for p in hz["plants"]:
        bits = [f"({p['at'][0]},{p['at'][1]}) {p['crop']}",
                f"age{p['age_days']}d", f"yield{p['yield_units']}/{p['max_yield']}"]
        if p["ongoing"]:
            days = ",".join(f"day{e['day']}" for e in p["remaining_production_days"][:6])
            bits.append(f"{p['events_left']} production event(s) left"
                        + (f" on {days}" if days else ""))
        else:
            bits.append(f"ripe at age{p['first_yield_day']}d")
            lo, hi = p["watering_bonus_window_days"]
            bits.append(f"watering raises yield at age{lo}-{hi}d")
        if p["decay_starts_step"] is not None:
            bits.append(("decaying now" if p["decaying"]
                         else f"decays from step{p['decay_starts_step']}"))
        bits.append(f"unwatered_streak{p['consecutive_unwatered']}")
        if p["dies_at_refresh_unless_watered"]:
            bits.append("DIES at this day's refresh unless watered today")
        lines.append("  " + " ".join(bits))
    return "\n".join(lines)


def objective_block(obs, config, seat, hz):
    """The actual scored objective, stated on EVERY turn, not only the last one."""
    money = int(obs["farms"][seat]["money"])
    other = int(obs["farms"][1 - seat]["money"])
    shed_units = sum(obs["private"].get("shed", {}).values())
    carried = sum(sum(i.values()) for i in obs["private"].get("inventories", []))
    lines = [
        f"OBJECTIVE: end the episode with more CASH than the opponent. Only cash is "
        f"scored -- goods in the shed or carried by a unit are worth 0 at the end, so "
        f"every unit you grow or buy has to be SOLD to count.",
        f"your cash {money}; opponent cash {other}; you are "
        f"{'ahead' if money > other else 'behind' if money < other else 'level'} by "
        f"{abs(money - other)}.",
        f"unsold: {shed_units} unit(s) in the shed, {carried} carried by units.",
        f"{hz['remaining_decisions']} decision(s) left (last is step "
        f"{hz['last_decision_step']}); {hz['turns_left_today']} turn(s) left today.",
    ]
    return "\n".join(lines)


def build(card, adm, head, hz=None, plan=None, static=None, farm_map=None,
          bank_block=None):
    """Static rules/economy first, then live state, then objective and plan, then the
    accepted set, and the operator surface with its output cue LAST.

    The static block is byte-identical every turn, so it is a stable reusable prefix.
    """
    obs, cfg, seat = card["observation"], card["configuration"], card["seat"]
    parts = []
    if static:
        parts.append(static)
    if bank_block:
        # Source placement (ExemplarBank call site, AgentOrchestrator.kt): the
        # demonstrations sit immediately BEFORE the live state, so continuing the
        # pattern is the action for the live state.
        parts.append(bank_block)
    parts.append(f"LIVE FARM\n{farm_map}" if farm_map else
                 f"STATE\n{digest(obs, cfg, seat)}")
    parts.append(f"HOLDINGS AND MARKET\n{digest(obs, cfg, seat)}")
    if hz is not None:
        parts.append(f"PRODUCTION AND HORIZON\n{horizon_block(hz)}")
        parts.append(objective_block(obs, cfg, seat, hz))
    parts.append(f"YOUR PLAN SO FAR: {plan}" if plan else
                 "YOUR PLAN SO FAR: none yet -- set one in the plan field.")
    parts.append(f"TURN RULES\n{rules_block(adm)}")
    parts.append("ACCEPTED (the engine acts on exactly these)\n"
                 + accepted_block(adm, obs, seat))
    if head:
        parts.append(head)
    return "\n\n".join(parts) + "\n"
