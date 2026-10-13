"""Build each operator's emitted surface from REAL derivation-card states.

Every exemplar situation is rendered from a real captured card (mutated in the one
field the operator's gate turns on), and every exemplar output is checked
admissible by the pinned engine before it is allowed into a surface. An exemplar
therefore demonstrates an ENGINE GATE, never an invented "best move" label.

Derivation cards must come from seeds disjoint from the evaluation seeds; `build`
raises if they overlap.
"""

import copy

import constraints
import discriminate
import operators
from constraints import engine


class OverlapError(Exception):
    pass


def _situation(card, extra=""):
    """A one-line situation in the same shape the STATE block uses."""
    obs, cfg, seat = card["observation"], card["configuration"], card["seat"]
    farm = obs["farms"][seat]
    x, y = int(farm["farmer"][0]), int(farm["farmer"][1])
    import prompt as P
    tile = P._tile_str(farm["tiles"][y][x], int(obs["day"]))
    seeds = ",".join(f"{k}{v}" for k, v in sorted(obs["private"].get("seeds", {}).items()) if v) or "-"
    shed = obs["private"].get("shed", {})
    cap = int(cfg.get("shedCapacity", 100) or 100)
    inv = obs["private"].get("inventories", [{}])[0]
    carry = ",".join(f"{k}{v}" for k, v in sorted(inv.items()) if v) or "-"
    bits = [f"farmer on [{tile}]", f"seeds {seeds}", f"carrying {carry}",
            f"shed {sum(shed.values())}/{cap}"]
    if extra:
        bits.append(extra)
    return "; ".join(bits)


def _assert_admissible(card, action):
    adm = constraints.admissible(card["observation"], card["configuration"], card["seat"])
    verdict = __import__("codec").legality(action, adm)
    if not verdict["legal"]:
        raise AssertionError(f"exemplar action not admissible: {verdict}")
    return action


def _pairs_for(card):
    """The five engine gates instantiated on this derivation card."""
    return {p["name"]: p for p in discriminate.build_pairs(card)}


def build(deriv_cards, eval_cards):
    """(surfaces, provenance). Raises OverlapError if the two card sets share a seed."""
    dseeds = {c["seed"] for c in deriv_cards}
    eseeds = {c["seed"] for c in eval_cards}
    if dseeds & eseeds:
        raise OverlapError(f"derivation and evaluation seeds overlap: {sorted(dseeds & eseeds)}")

    card = deriv_cards[0]
    pairs = _pairs_for(card)
    K = engine()
    prov = {"derivation_seeds": sorted(dseeds), "evaluation_seeds": sorted(eseeds),
            "derivation_cards": [c["card_id"] for c in deriv_cards], "exemplars": {}}
    surfaces = {}

    PLANS = {
        "ADMIT": ["one turn object, one op per unit",
                  "one turn object, an op for the farmer and each hand"],
        "STOCK": ["plant the wheat I have a seed for",
                  "no wheat seed, so PLANT WHEAT is not available this turn"],
        "ONCE":  ["water this tile today",
                  "this tile is already watered today"],
        "RIPE":  ["harvest this ripe plant",
                  "not ripe yet, HARVEST is not available on this tile"],
        "KEEP":  ["water so this plant survives the refresh",
                  "this plant is already safe for this refresh"],
        "VENT":  ["move the carried goods into the shed",
                  "the shed is full, DROP would move nothing"],
    }

    def add(name, items):
        checked = []
        for i, (src_card, situation, action) in enumerate(items):
            _assert_admissible(src_card, action)
            plans = PLANS.get(name)
            # plan FIRST: the emitted surface must show the same key order the decode
            # grammar requires, so the exemplar and the constraint agree.
            act = {}
            if plans:
                act["plan"] = plans[min(i, len(plans) - 1)]
            act.update(action)
            checked.append((situation, act))
        surfaces[name] = operators.surface(name, checked)
        prov["exemplars"][name] = [{"situation": s, "output": a} for s, a in checked]

    # ADMIT -- the OUTPUT CONTRACT only: arity and nesting, one entry per unit. Both
    # sides emit PASS, the engine's own declared default, so nothing about WHICH op to
    # prefer is taught here. The other operators supply the non-PASS demonstrations,
    # and each of those is forced by its gate rather than chosen by this code.
    admit_card = copy.deepcopy(card)
    admit_two = copy.deepcopy(card)
    seat_a = admit_two["seat"]
    farm_a = admit_two["observation"]["farms"][seat_a]
    farm_a["hands"] = [list(farm_a["farmer"])]
    admit_two["observation"]["private"].setdefault("inventories", [{}])
    while len(admit_two["observation"]["private"]["inventories"]) < 2:
        admit_two["observation"]["private"]["inventories"].append({})
    add("ADMIT", [
        (admit_card, _situation(admit_card, "1 unit"),
         {"farmer": ["PASS"], "hands": [], "market": []}),
        (admit_two, _situation(admit_two, "2 units"),
         {"farmer": ["PASS"], "hands": [["PASS"]], "market": []}),
    ])

    # STOCK -- the resource is present, or it is absent and the op is unavailable.
    # The absent side does NOT buy: whether a seed is worth its cost is a plan
    # decision, not this gate's semantics.
    p = pairs["seed_stock"]
    add("STOCK", [
        (p["a"], _situation(p["a"]), {"farmer": ["PLANT", "WHEAT"], "hands": [], "market": []}),
        (p["b"], _situation(p["b"]), {"farmer": ["PASS"], "hands": [], "market": []}),
    ])

    # ONCE -- the daily flag is unconsumed, or already consumed.
    p = pairs["watered_negation"]
    add("ONCE", [
        (p["a"], _situation(p["a"]), {"farmer": ["WATER"], "hands": [], "market": []}),
        (p["b"], _situation(p["b"]), {"farmer": ["PASS"], "hands": [], "market": []}),
    ])

    # RIPE -- the maturity deadline is met, or it is not.
    p = pairs["maturity_deadline"]
    add("RIPE", [
        (p["a"], _situation(p["a"]), {"farmer": ["HARVEST"], "hands": [], "market": []}),
        (p["b"], _situation(p["b"]), {"farmer": ["PASS"], "hands": [], "market": []}),
    ])

    # KEEP -- a plant that dies at this refresh unless watered, versus one that does not.
    K2 = engine()
    keep_card = copy.deepcopy(card)
    seat_k = keep_card["seat"]
    spots = [(x, y) for y, row in enumerate(keep_card["observation"]["farms"][seat_k]["tiles"])
             for x, t_ in enumerate(row) if t_ is None]
    kx, ky = spots[0]
    keep_card["observation"]["farms"][seat_k]["farmer"] = [kx, ky]
    day_k = int(keep_card["observation"]["day"])
    tpd_k = int(keep_card["configuration"]["turnsPerDay"])
    dying = copy.deepcopy(keep_card)
    dying["observation"]["farms"][seat_k]["tiles"][ky][kx] = K2._new_plant("WHEAT", day_k, tpd_k)
    safe = copy.deepcopy(keep_card)
    safe_tile = K2._new_plant("WHEAT", day_k, tpd_k)
    safe_tile["consecutive_unwatered"] = 0
    safe_tile["watered_today"] = True
    safe["observation"]["farms"][seat_k]["tiles"][ky][kx] = safe_tile
    add("KEEP", [
        (dying, _situation(dying, "unwatered_streak1, dies at this refresh unless watered"),
         {"farmer": ["WATER"], "hands": [], "market": []}),
        (safe, _situation(safe, "watered today, safe for this refresh"),
         {"farmer": ["PASS"], "hands": [], "market": []}),
    ])

    # VENT -- the deposit path is open, or the shed is full and DROP moves nothing.
    # This gate is about shed room, so neither side buys or sells: what to do with the
    # room is a plan decision.
    vent_room = copy.deepcopy(card)
    seat_v = vent_room["seat"]
    board_v = int(vent_room["configuration"]["boardSize"])
    cap_v = int(vent_room["configuration"]["shedCapacity"])
    vent_room["observation"]["farms"][seat_v]["farmer"] = list(K2._shed_access_tiles(board_v)[0])
    vent_room["observation"]["private"]["inventories"][0] = {"CARROT": 2}
    vent_room["observation"]["private"]["shed"] = {
        k: 0 for k in vent_room["observation"]["private"]["shed"]}
    vent_full = copy.deepcopy(vent_room)
    vent_full["observation"]["private"]["shed"]["WHEAT"] = cap_v
    add("VENT", [
        (vent_room, _situation(vent_room, "on a shed access tile, shed has room"),
         {"farmer": ["DROP"], "hands": [], "market": []}),
        (vent_full, _situation(vent_full, "on a shed access tile, shed is full"),
         {"farmer": ["PASS"], "hands": [], "market": []}),
    ])
    return surfaces, prov


def composed_pattern(surfaces):
    """The five gate surfaces stacked under one header (sigma1 || sigma2 ...)."""
    return "\n".join(surfaces[n] for n in operators.ORDER)


def composed_formal():
    """The eight-part specifications stacked, one per operator."""
    return "\n\n".join(operators.spec_text(n) for n in operators.ORDER)
