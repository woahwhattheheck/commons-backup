"""Kaggriculture operators: formal constraint subprograms, not exhortations.

Each operator carries TWO layers.

1. SPEC -- the eight-part semantic specification (header, definitions,
   admissible-set constraints, cost functions, priority, conditional,
   prohibitions, output contract). This is the authoring layer: it says what the
   operator MEANS, and it is derived from the pinned engine's own rules, not from
   any prior domain's catalog.

2. SURFACE -- what is actually emitted to the small-tier model: a header line
   plus contrasting input->output exemplars in the exact output shape, and
   nothing narratable. Exemplars are built from REAL engine states on derivation
   cards that are disjoint from the evaluation cards.

The operators here are derived from the engine's own gates, which is why there
are exactly these four beyond the codec: the engine rejects an op for a missing
resource, for an already-consumed daily flag, for an unmet maturity day, or for a
full shed. Each operator binds one of those gates.

Nothing here ranks moves or asserts which admissible move is best: the operator
constrains the admissible set, the model authors the choice inside it.
"""

import json

from constraints import engine

# --------------------------------------------------------------------------
# The eight-part semantic specification (authoring layer)
# --------------------------------------------------------------------------

SPEC = {
    "ADMIT": {
        "header": "Sigma:ADMIT -- output-contract binding for one Kaggriculture turn.",
        "definitions": (
            "Turn := {farmer:[op,...], hands:[[op,...],...], market:[[op,...],...]}. "
            "A := the admissible set supplied for this observation. "
            "U(i) := admissible ops for unit i. M := admissible market orders."
        ),
        "admissible_constraints": (
            "forall a in emitted turn: a in A. farmer in U(0). hands[i] in U(i+1). "
            "|hands| <= number of hands. market[j] in M. |market| <= maxMarketOrdersPerTurn."
        ),
        "cost": "min(tokens emitted); min(keys outside {farmer,hands,market}).",
        "priority": "well-formedness of the object > membership of each entry > length.",
        "conditional": "If no op advances the goal, PASS is in U(0) and is a valid emission.",
        "prohibitions": (
            "Never emit an op absent from A. Never emit an op name outside the grammar. "
            "Never emit prose, keys, or fields outside the turn object."
        ),
        "output_contract": "Output := one turn object, nothing before or after it.",
    },
    "STOCK": {
        "header": "Sigma:STOCK -- resource-precondition binding.",
        "definitions": (
            "req(op) := the engine's consumed resource: PLANT c needs seeds[c] >= 1; "
            "FEED needs unit inventory WHEAT >= 1; FERTILIZE needs unit inventory "
            "FERTILIZER >= 1; PICKUP x needs shed[x] >= 1; PLACE x needs unit inventory "
            "x >= 1; BUY_* needs money >= price."
        ),
        "admissible_constraints": (
            "forall op emitted: req(op) is satisfied in THIS observation. "
            "If req(op) is unsatisfied, op is not in A and is not emitted."
        ),
        "cost": "min(ops emitted whose resource is absent).",
        "priority": (
            "an op whose resource is present ranks above one whose resource is absent. "
            "Which present-resource op to take is not ordered here -- that is the plan's "
            "to choose."
        ),
        "conditional": (
            "If the intended op's resource is absent, that op is not admissible this "
            "turn. An acquiring order (BUY_SEED for a seed, PICKUP for a shed item) is "
            "AVAILABLE, not required: buying a seed is only worth its cost if the plan "
            "actually plants it, and a seed bought this turn cannot be planted until the "
            "next one."
        ),
        "prohibitions": (
            "Never emit an op whose resource count is zero. Never assume a resource "
            "not present in this observation."
        ),
        "output_contract": "Output := one turn object whose every op has its resource present.",
    },
    "ONCE": {
        "header": "Sigma:ONCE -- per-day idempotence binding (negation).",
        "definitions": (
            "The engine sets watered_today, fed_today, cared_today, and clears "
            "fertilizer_available on use. done(tile,op) := the flag for op is already set."
        ),
        "admissible_constraints": (
            "forall op in {WATER, FEED, CARE, COLLECT_FERTILIZER}: "
            "op emitted => not done(tile_under_unit, op)."
        ),
        "cost": "min(no-op turns).",
        "priority": "an op with an unconsumed flag > movement to a tile with one > PASS.",
        "conditional": (
            "If the op is already done on this tile today, emit a different admissible "
            "op or a move; the flag clears at the end-of-day refresh, not before."
        ),
        "prohibitions": "Never re-emit a daily op whose flag is already set on this tile.",
        "output_contract": "Output := one turn object with no already-consumed daily op.",
    },
    "RIPE": {
        "header": "Sigma:RIPE -- maturity and production-window binding.",
        "definitions": (
            "age := day - planted_day. first := CROPS[crop].first_yield_day. "
            "y := tile.yield_units. mature(tile) := age >= first and y > 0. "
            "An ongoing crop produces when (next_day - planted_day - first) is a "
            "non-negative multiple of interval, for at most max_yield events: TOMATO "
            "(first 8, interval 1) at ages 8,9,10,11 and STRAWBERRY (first 10, interval "
            "2) at ages 10,12,14,16 -- four events each, held at cap 4, after which the "
            "plant goes on a lifespan clock and decays 1 unit every 2 steps."
        ),
        "admissible_constraints": (
            "HARVEST on a PLANT emitted => mature(tile). "
            "HARVEST on an animal tile emitted => y > 0."
        ),
        "cost": "min(units lost to decay after the final production event).",
        "priority": (
            "no ordering between harvesting now and leaving a plant to keep producing. "
            "An ongoing plant with events left keeps producing whether or not it is "
            "harvested, and harvesting early is not preferred; the remaining production "
            "days and the decay step are given so the plan can choose."
        ),
        "conditional": (
            "If age < first, HARVEST is not admissible on that tile at all. If the plant "
            "has produced its last event, its yield decays from decay_starts_step onward, "
            "so units left on it are lost over time rather than held."
        ),
        "prohibitions": (
            "Never emit HARVEST on a tile below first_yield_day or with yield_units 0."
        ),
        "output_contract": "Output := one turn object whose HARVEST, if present, is on a mature tile.",
    },
    "KEEP": {
        "header": "Sigma:KEEP -- plant survival binding.",
        "definitions": (
            "u := tile.consecutive_unwatered. The daily refresh sets u := 0 if the tile "
            "was watered today, else u := u + 1, and any plant reaching u >= 2 becomes a "
            "WEED. A newly planted tile starts at u = 1, so its planting day is already "
            "one unwatered day."
        ),
        "admissible_constraints": (
            "For every owned plant: u + 1 >= 2 and not watered_today "
            "=> the plant is removed at this day's refresh. "
            "A plant planted this day and not watered this day dies at that refresh."
        ),
        "cost": "min(plants lost to the weed conversion).",
        "priority": (
            "a plant that dies at this refresh unless watered ranks above one that does "
            "not. No ordering is imposed between watering and any unrelated op."
        ),
        "conditional": (
            "A surviving ongoing plant still gains its base yield on an unwatered day; "
            "only the fertilizer bonus requires the day to have been watered. So watering "
            "is a survival precondition, not a per-day yield requirement."
        ),
        "prohibitions": (
            "Never treat watering as optional for a tile flagged dies_at_refresh_unless_watered. "
            "Never treat it as required for a tile that is not."
        ),
        "output_contract": "Output := one turn object that does not strand a dying plant unwatered.",
    },
    "VENT": {
        "header": "Sigma:VENT -- shed-capacity binding.",
        "definitions": (
            "used := sum(shed.values()). cap := shedCapacity. full := used >= cap. "
            "Seeds are NOT held in the shed: BUY_SEED bypasses cap entirely."
        ),
        "admissible_constraints": (
            "BUY_PRODUCT or BUY_ANIMAL emitted => not full. "
            "DROP / PLACE-to-shed move at most cap - used units. "
            "BUY_SEED admissibility is independent of full."
        ),
        "cost": "min(units discarded at the end-of-day drop); max(shed room before a deposit).",
        "priority": "SELL when full > deposit when full > buy into a full shed.",
        "conditional": (
            "If full and a deposit or product purchase is intended, emit an admissible "
            "SELL first; BUY_SEED remains available while full."
        ),
        "prohibitions": (
            "Never emit BUY_PRODUCT or BUY_ANIMAL while the shed is at capacity."
        ),
        "output_contract": "Output := one turn object that does not deposit into a full shed.",
    },
}

ORDER = ["ADMIT", "STOCK", "ONCE", "RIPE", "KEEP", "VENT"]


# --------------------------------------------------------------------------
# The emitted surface (small-tier deployment layer)
# --------------------------------------------------------------------------

def _j(action):
    return json.dumps(action, separators=(",", ":"))


def surface(name, exemplars):
    """Header + contrasting exemplars, in the exact output shape. Nothing to narrate.

    `exemplars` is a list of (situation_text, turn_action) pairs whose situations
    come from real derivation-card states.
    """
    lines = [f"Sigma:{name}"]
    for situation, action in exemplars:
        lines.append(f"{situation} -> {_j(action)}")
    lines.append("->")
    return "\n".join(lines)


def spec_text(name):
    """The eight-part specification rendered for the authoring/large-model layer."""
    s = SPEC[name]
    return "\n".join([
        s["header"],
        f"Definitions: {s['definitions']}",
        f"Admissible set: {s['admissible_constraints']}",
        f"Optimize: {s['cost']}",
        f"Priority: {s['priority']}",
        f"Conditional: {s['conditional']}",
        f"Prohibitions: {s['prohibitions']}",
        s["output_contract"],
    ])


BASELINE_INSTRUCTION = (
    "You are playing Kaggriculture. Read the state and the list of actions the "
    "engine will accept, then choose this turn's actions. Reply with a JSON object "
    "with keys farmer, hands and market: farmer is one action list, hands is a list "
    "of action lists (one per hand), market is a list of order lists. Only use "
    "actions from the accepted list."
)
