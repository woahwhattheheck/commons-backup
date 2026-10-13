"""Reversible codec between the model's emitted surface and the engine action.

The output contract IS the engine's own action object, so the codec is an
identity on well-formed output and the legality check is exact rather than
interpretive:

    {"farmer": [OP, ...], "hands": [[OP, ...], ...], "market": [[OP, ...], ...]}

Decoding is strict and REJECTS. It never repairs an invalid emission into a
plausible one and never substitutes a fallback while reporting a model decision:
a rejection is returned with its reason and counted as a rejection.
"""

import json

UNIT_OPS_0 = {
    "NORTH", "SOUTH", "EAST", "WEST", "PASS", "DROP", "WATER", "HARVEST",
    "FERTILIZE", "DIG", "BUILD_COOP", "BUILD_PASTURE", "FEED",
    "COLLECT_FERTILIZER", "CARE",
}
UNIT_OPS_ITEM = {"PLANT", "PICKUP", "PLACE"}
MARKET_OPS_0 = {"HIRE", "BUY_LAND"}
MARKET_OPS_ITEM_N = {"BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "SELL"}


class Rejected(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def encode_turn(action):
    """Canonical compact surface for a turn action. Deterministic key order."""
    return json.dumps(
        {
            "farmer": list(action.get("farmer", ["PASS"])),
            "hands": [list(h) for h in action.get("hands", [])],
            "market": [list(m) for m in action.get("market", [])],
        },
        separators=(",", ":"),
    )


def _json_objects(text):
    """Every balanced top-level {...} in the text, string/escape aware."""
    out, depth, start, in_str, esc = [], 0, None, False, False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth:
                depth -= 1
                if depth == 0:
                    out.append(text[start:i + 1])
    return out


def _single_json_object(text):
    """Exactly ONE current-turn object, or a rejection.

    Taking the first balanced object would silently accept an echoed exemplar: the
    pattern arm did emit a derivation exemplar verbatim, and its output JSON would
    have parsed cleanly while describing a different card. An emission carrying more
    than one object is ambiguous about which turn is being played, so it is rejected
    rather than resolved by a positional guess.
    """
    objs = _json_objects(text)
    if not objs:
        raise Rejected("no balanced JSON object in output")
    if len(objs) > 1:
        raise Rejected(f"{len(objs)} JSON objects emitted; expected exactly one "
                       f"current-turn object (echoed example?)")
    return objs[0]


def _norm_unit(entry, where):
    if not isinstance(entry, list) or not entry:
        raise Rejected(f"{where}: not a non-empty list")
    op = entry[0]
    if not isinstance(op, str):
        raise Rejected(f"{where}: op is not a string")
    op = op.strip().upper()
    if op in UNIT_OPS_0:
        if len(entry) != 1:
            raise Rejected(f"{where}: {op} takes no arguments, got {len(entry) - 1}")
        return [op]
    if op in UNIT_OPS_ITEM:
        if len(entry) < 2 or not isinstance(entry[1], str):
            raise Rejected(f"{where}: {op} needs an item name")
        item = entry[1].strip().upper()
        if op == "PLANT":
            if len(entry) != 2:
                raise Rejected(f"{where}: PLANT takes exactly one crop")
            return ["PLANT", item]
        n = 1
        if len(entry) >= 3:
            if not isinstance(entry[2], (int, float)) or isinstance(entry[2], bool):
                raise Rejected(f"{where}: {op} count is not a number")
            n = int(entry[2])
        if len(entry) > 3:
            raise Rejected(f"{where}: {op} takes at most item and count")
        return [op, item, n]
    raise Rejected(f"{where}: unknown unit op {op!r}")


def _norm_market(entry, where):
    if not isinstance(entry, list) or not entry:
        raise Rejected(f"{where}: not a non-empty list")
    op = entry[0]
    if not isinstance(op, str):
        raise Rejected(f"{where}: op is not a string")
    op = op.strip().upper()
    if op in MARKET_OPS_0:
        if len(entry) != 1:
            raise Rejected(f"{where}: {op} takes no arguments")
        return [op]
    if op in MARKET_OPS_ITEM_N:
        if len(entry) != 3:
            raise Rejected(f"{where}: {op} needs item and count")
        if not isinstance(entry[1], str):
            raise Rejected(f"{where}: {op} item is not a string")
        if not isinstance(entry[2], (int, float)) or isinstance(entry[2], bool):
            raise Rejected(f"{where}: {op} count is not a number")
        return [op, entry[1].strip().upper(), int(entry[2])]
    raise Rejected(f"{where}: unknown market op {op!r}")


def decode_turn(text):
    """Model text -> engine action dict. Raises Rejected with a reason."""
    if not isinstance(text, str) or not text.strip():
        raise Rejected("empty output")
    blob = _single_json_object(text)
    try:
        obj = json.loads(blob)
    except Exception as exc:
        raise Rejected(f"not valid JSON: {exc}")
    if not isinstance(obj, dict):
        raise Rejected("top level is not an object")
    unknown = set(obj) - {"farmer", "hands", "market", "plan"}
    if unknown:
        raise Rejected(f"unknown top-level keys: {sorted(unknown)}")
    if "farmer" not in obj:
        raise Rejected("missing 'farmer'")
    farmer = _norm_unit(obj["farmer"], "farmer")
    hands_raw = obj.get("hands", [])
    if not isinstance(hands_raw, list):
        raise Rejected("'hands' is not a list")
    hands = [_norm_unit(h, f"hands[{i}]") for i, h in enumerate(hands_raw)]
    market_raw = obj.get("market", [])
    if not isinstance(market_raw, list):
        raise Rejected("'market' is not a list")
    market = [_norm_market(m, f"market[{i}]") for i, m in enumerate(market_raw)]
    plan = obj.get("plan")
    if plan is not None and not isinstance(plan, str):
        raise Rejected("'plan' is not a string")
    out = {"farmer": farmer, "hands": hands, "market": market}
    if plan is not None:
        out["plan"] = plan
    return out


def _in_set(entry, admissible_set):
    """Membership ignoring the count argument (the engine clamps counts, not rejects)."""
    for cand in admissible_set:
        if cand[0] != entry[0]:
            continue
        if len(cand) == 1 and len(entry) == 1:
            return True
        if len(cand) > 1 and len(entry) > 1 and cand[1] == entry[1]:
            return True
    return False


def _market_orders(adm, key):
    return [m["order"] for m in adm[key]]


def _max_n(adm, key, order):
    for m in adm[key]:
        if m["order"][0] == order[0] and m["order"][1:] == order[1:2]:
            return m["max_n"]
    return None


def engine_action(action):
    """Strip the model's carried plan: the engine takes only the three turn keys."""
    return {"farmer": action["farmer"], "hands": action["hands"], "market": action["market"]}


def legality(action, adm):
    """Three DISTINCT results for one decoded turn -- never collapsed into one score.

      violations   the engine will not act on this entry at all (a silent no-op)
      joint_blocks turn-level drops the per-unit view cannot see (the PLANT budget)
      clamped      quantities the engine will silently reduce, which is legal but lossy

    A turn with no violations and no joint_blocks is one the engine acts on in full.
    Whether it is a GOOD turn is a separate question this function does not answer.
    """
    violations, joint_blocks, clamped = [], [], []
    units = adm["units"]
    qty = adm.get("quantities", [{}] * len(units))

    entries = [(0, action["farmer"], "farmer")]
    n_hands = len(units) - 1
    if len(action["hands"]) > n_hands:
        violations.append(f"{len(action['hands'])} hand actions but {n_hands} hands exist")
    for i, h in enumerate(action["hands"][:n_hands]):
        entries.append((i + 1, h, f"hands[{i}]"))

    for idx, entry, label in entries:
        if not _in_set(entry, units[idx]):
            violations.append(f"{label} {entry} not admissible")
            continue
        if entry[0] in ("PICKUP", "PLACE") and len(entry) >= 3:
            dom = qty[idx].get("PICKUP" if entry[0] == "PICKUP" else "PLACE_to_shed", {})
            cap = dom.get(entry[1])
            if cap is not None and entry[2] > cap:
                clamped.append(f"{label} {entry[0]} {entry[1]} {entry[2]} clamps to {cap}")

    # Atomic PLANT budget, summed across farmer and hands (interpreter 920-933).
    demand = {}
    for _idx, entry, _label in entries:
        if entry[0] == "PLANT":
            demand[entry[1]] = demand.get(entry[1], 0) + 1
    budget = adm["rules"]["plant_budget"]
    for crop, n in sorted(demand.items()):
        have = budget.get(crop, 0)
        if n > have:
            joint_blocks.append(
                f"PLANT {crop} requested {n}x across units but only {have} seed(s): "
                f"the engine drops ALL {n} to PASS")

    # Market. An order can be enabled by a deposit earlier in the SAME turn, so the
    # permissive basis is the post-deposit set; which basis carried it is recorded.
    now = _market_orders(adm, "market")
    after = _market_orders(adm, "market_after_full_deposit")
    limit = adm["max_market_orders"]
    if len(action["market"]) > limit:
        violations.append(
            f"{len(action['market'])} market orders exceeds maxMarketOrdersPerTurn={limit}; "
            f"the engine silently drops the extras")
    for i, m in enumerate(action["market"][:limit]):
        if _in_set(m, now):
            cap = _max_n(adm, "market", m)
        elif _in_set(m, after):
            cap = _max_n(adm, "market_after_full_deposit", m)
            clamped.append(f"market[{i}] {m[0]} {m[1] if len(m) > 1 else ''} "
                           f"needs a same-turn deposit to fill")
        else:
            violations.append(f"market[{i}] {m} not admissible")
            continue
        if cap is not None and len(m) >= 3 and m[2] > cap:
            clamped.append(f"market[{i}] {m[0]} {m[1]} {m[2]} fills at most {cap}")

    return {"violations": violations, "joint_blocks": joint_blocks, "clamped": clamped,
            "legal": not violations and not joint_blocks}


# --------------------------------------------------------------------------
# Grammar-level output binding for constrained decoding
# --------------------------------------------------------------------------

def _alt(names):
    return "(?:" + "|".join(sorted(names)) + ")"


def turn_regex():
    """A regex over the exact turn grammar, for ResponseFormat.REGEX.

    This binds SYNTAX only -- op names, arity, nesting. Whether an op is admissible
    on this card stays a separate check, so a constrained decode cannot manufacture
    a legality result it did not earn.
    """
    from constraints import engine
    K = engine()
    items = sorted(set(K.PRODUCTS) | set(K.ANIMALS) | set(K.CROPS))
    n = "[0-9]{1,3}"
    unit = "(?:" + "|".join([
        r'\["' + _alt(UNIT_OPS_0) + r'"\]',
        r'\["PLANT","' + _alt(K.CROPS) + r'"\]',
        r'\["(?:PICKUP|PLACE)","' + _alt(items) + r'",' + n + r'\]',
    ]) + ")"
    order = "(?:" + "|".join([
        r'\["' + _alt(MARKET_OPS_0) + r'"\]',
        r'\["' + _alt(MARKET_OPS_ITEM_N) + r'","' + _alt(items) + r'",' + n + r'\]',
    ]) + ")"
    lst = lambda e: r"\[(?:" + e + r"(?:," + e + r"){0,9})?\]"
    return r'\{"farmer":' + unit + r',"hands":' + lst(unit) + r',"market":' + lst(order) + r"\}"


TIGHT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["farmer", "hands", "market"],
    "properties": {
        "farmer": {"type": "array", "minItems": 1, "maxItems": 3,
                   "items": {"type": ["string", "integer"]}},
        "hands": {"type": "array", "maxItems": 8,
                  "items": {"type": "array", "minItems": 1, "maxItems": 3,
                            "items": {"type": ["string", "integer"]}}},
        "market": {"type": "array", "maxItems": 10,
                   "items": {"type": "array", "minItems": 1, "maxItems": 3,
                             "items": {"type": ["string", "integer"]}}},
    },
}


def card_regex(adm, max_market=3):
    """A regex over THIS card's admissible set: the applicable constraint, at decode.

    The global `turn_regex` binds only the grammar, so a constrained decode could
    still be inadmissible. Building the alternation from the engine-derived
    admissible set makes every accepted emission legal by construction, while
    leaving the CHOICE inside that set entirely to the model -- code supplies the
    constraint and decodes the output, it does not pick the op.

    PASS stays in the alternation because the engine admits it; it is never the only
    option offered when others exist.
    """
    import re as _re

    def unit_alt(ops, quantities):
        alts = []
        for op in ops:
            if len(op) == 1:
                alts.append(_re.escape(f'["{op[0]}"]'))
            elif op[0] == "PLANT":
                alts.append(_re.escape(f'["PLANT","{op[1]}"]'))
            else:
                dom = quantities.get("PICKUP" if op[0] == "PICKUP" else "PLACE_to_shed", {})
                cap = max(1, int(dom.get(op[1], 1)))
                alts.append(_re.escape(f'["{op[0]}","{op[1]}",') + _num(cap) + _re.escape("]"))
        return "(?:" + "|".join(alts) + ")"

    def _num(cap):
        return "(?:" + "|".join(str(i) for i in range(1, cap + 1)) + ")"

    orders = []
    seen = set()
    for src in ("market", "market_after_full_deposit"):
        for m in adm[src]:
            key = tuple(m["order"])
            if key in seen:
                continue
            seen.add(key)
            if len(m["order"]) == 1:
                orders.append(_re.escape(f'["{m["order"][0]}"]'))
            else:
                cap = max(1, int(m["max_n"]))
                orders.append(_re.escape(f'["{m["order"][0]}","{m["order"][1]}",')
                              + _num(cap) + _re.escape("]"))
    order_alt = "(?:" + "|".join(orders) + ")" if orders else None

    farmer = unit_alt(adm["units"][0], adm["quantities"][0])
    hands = [unit_alt(adm["units"][i + 1], adm["quantities"][i + 1])
             for i in range(len(adm["units"]) - 1)]
    hands_re = r"\[" + ",".join(hands) + r"\]" if hands else r"\[\]"
    k = min(max_market, adm["max_market_orders"])
    if order_alt:
        market_re = r"\[(?:" + order_alt + r"(?:," + order_alt + r"){0," + str(k - 1) + r"})?\]"
    else:
        market_re = r"\[\]"
    # The plan is emitted FIRST. With it last, the model had to commit to the action
    # before writing a single token of its reasoning, and it emitted PASS on 14/14
    # real turns while its plan text described the state correctly. Generating the
    # plan first lets the decode condition the action on it. The plan is
    # model-authored, carried across turns, and stripped before the engine sees the
    # action; it is bounded so it cannot eat the output budget.
    plan_re = r'"plan":"[A-Za-z][^"\\\\\\x00-\\x1f]{11,199}",'
    return (r'\{' + plan_re + r'"farmer":' + farmer + r',"hands":' + hands_re
            + r',"market":' + market_re + r"\}")


def slot_regex(adm, idle_units, max_slots=4):
    """A regex over the admissible ops of the IDLE units only.

    Over a route-replay baseline the whole turn is not the model's to author: the
    tape's working slots carry the schedule. What is genuinely open is the set of
    slots the baseline's own no-op predicate says the engine will ignore. This
    binds the decode to exactly those slots and, within each, to that unit's
    engine-derived admissible set -- so an accepted emission is legal by
    construction and the CHOICE inside the set is still entirely the model's.

    PASS stays in every alternation: declining a slot must remain expressible, or
    the grammar would be manufacturing action.
    """
    import re as _re

    def _num(cap):
        return "(?:" + "|".join(str(i) for i in range(1, cap + 1)) + ")"

    def unit_alt(ops, quantities):
        alts = []
        for op in ops:
            if len(op) == 1:
                alts.append(_re.escape(f'["{op[0]}"]'))
            elif op[0] == "PLANT":
                alts.append(_re.escape(f'["PLANT","{op[1]}"]'))
            else:
                dom = quantities.get("PICKUP" if op[0] == "PICKUP" else "PLACE_to_shed", {})
                cap = max(1, int(dom.get(op[1], 1)))
                alts.append(_re.escape(f'["{op[0]}","{op[1]}",') + _num(cap)
                            + _re.escape("]"))
        return "(?:" + "|".join(alts) + ")"

    picked = [i for i in idle_units if i < len(adm["units"])][:max_slots]
    if not picked:
        return None
    parts = []
    for i in picked:
        parts.append(_re.escape(f'{{"unit":{i},"op":')
                     + unit_alt(adm["units"][i], adm["quantities"][i])
                     + _re.escape("}"))
    plan_re = r'"plan":"[A-Za-z][^"\\\x00-\x1f]{11,199}",'
    return r'\{' + plan_re + r'"slots":\[' + ",".join(parts) + r'\]\}'


def decode_slots(raw, idle_units, max_slots=4):
    """Decode exactly one current-turn slot object; reject anything else.

    Returns {"plan": str, "slots": {unit: op}}. A malformed or off-contract
    emission raises `Rejected` with its reason and is recorded as a rejection --
    it is never quietly replaced with a claimed model decision.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise Rejected("empty output")
    blob = _single_json_object(raw)
    try:
        obj = json.loads(blob)
    except Exception as exc:
        raise Rejected(f"not valid JSON: {exc}")
    if not isinstance(obj, dict):
        raise Rejected("top level is not an object")
    unknown = set(obj) - {"plan", "slots"}
    if unknown:
        raise Rejected(f"unknown top-level keys: {sorted(unknown)}")
    if "slots" not in obj or not isinstance(obj["slots"], list):
        raise Rejected("no slots array")
    want = [i for i in idle_units][:max_slots]
    out = {}
    for entry in obj["slots"]:
        if not isinstance(entry, dict) or "unit" not in entry or "op" not in entry:
            raise Rejected("slot entry is not {unit, op}")
        u = int(entry["unit"])
        if u not in want:
            raise Rejected(f"slot {u} is not an idle slot of this turn")
        if u in out:
            raise Rejected(f"slot {u} emitted twice")
        op = entry["op"]
        if not isinstance(op, list) or not op or not isinstance(op[0], str):
            raise Rejected("op is not a token list")
        out[u] = [op[0]] + [int(t) if isinstance(t, (int, float)) else str(t)
                            for t in op[1:]]
    if not out:
        raise Rejected("no slots decoded")
    plan = obj.get("plan")
    return {"plan": str(plan) if isinstance(plan, str) else None, "slots": out}
