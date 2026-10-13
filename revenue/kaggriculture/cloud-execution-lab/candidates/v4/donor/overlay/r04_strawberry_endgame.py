# SPDX-License-Identifier: Apache-2.0
"""V3.1 lane L2 "strawberry-endgame" (r04_strawberry_endgame).

Bounded, seed-gated conversion of late ["PLANT", "WHEAT"] orders into
["PLANT", "STRAWBERRY"], attached in r04_full_router.v3_agent between POLICY_AGENT
and ROW_ORDER. WATER, HARVEST and DROP are tile-agnostic (they act on the tile the
worker stands on and never name a crop), so a converted planting keeps the tape's
existing watering / harvesting / drop cadence working on the new crop automatically;
the evening flush already sells projected shed stock of STRAWBERRY (FLUSH_ITEMS).

Replay-verified facts (31 audited Kaggle episodes, submission 56159263):

* private["seeds"]["STRAWBERRY"] is 0 at every late step (days 24-29) in every
  episode. The tape buys ~35 strawberry seeds in two early waves (steps ~130-216
  and ~264-284) and plants all 33 of them on days 5-11. There is no late seed
  stock and this module deliberately adds no BUY_SEED rows (the wheat engine's
  budget is untouched), so on the observed distribution the lane is a strict
  no-op: expected delta-margin ~ 0.
* The harvest -> DROP -> shed -> SELL pipeline for strawberry works: shed
  STRAWBERRY reaches ~21 units late from the day 5-11 plantings and is sold by
  the E184 window / evening flush (e.g. 17 units at steps 694 and 710).
* Conversion sites exist: every plan carries 10-13 ["PLANT", "WHEAT"] orders in
  the window [576, 648] (steps, i.e. days 24-27).

Fleet deconfliction: ASTRA · GPT-5.6 SOL has claimed H4 (strawberry throughput /
sale sizing) as a LIVE-R04 port lane on titan/v3.1-20260911. This module is
strictly production/staging timing: planting (+ harvest scheduling, so mature
units exist for the ~step-700 flush). It never touches sale row sizing, sale
quantities, or price-aware sale timing; those belong to ASTRA's lane and this
lane composes with it rather than overlapping it.

Engine fact that bounds the mechanism (checks/reference/engine/kaggriculture.py):
STRAWBERRY is an *ongoing* crop with first_yield_day 10. Yield accrues at dawn,
one unit every 2 days starting the dawn of day planted_day + 10. A strawberry
planted in this window (days 24-27) first yields on days 34-37, i.e. after step
718: it produces zero units before the game ends. The "matures within a couple
of waterings" premise is false; watering only prevents weed-death and enables
the fertilizer bonus. The last day a strawberry can be planted and still yield
anything is day 19 (one unit at the dawn of day 29). If strawberry seeds ever
appear late, converting in this window would *destroy* the wheat the tile would
otherwise produce (wheat is non-ongoing: first_yield_day 2, yields days
planted+2..planted+4, up to 6 units) for zero strawberry. Do not widen this
lane; re-scope any follow-up to planting days <= 19.

Bounds (all enforced here, none in the caller):

* at most r04_strawberry_max_plants (default 8) conversions TOTAL per game;
  the per-game counter is keyed on observation["player"] and resets whenever
  the step decreases (new game / new episode);
* at most 2 conversions per step, to avoid clustering;
* only exact ["PLANT", "WHEAT"] orders on farmer/hands are converted; every
  other command, every market row, and every non-WHEAT planting is untouched;
* conversion only happens while the observed strawberry seed stock at that step
  is > 0; with no seeds the action is returned unchanged (same object);
* never runs outside steps [576, 648]; with the install() flag off the module
  is never called and the action is byte-identical.

Standard library only. Never raises on malformed input: any unreadable
observation returns the action unchanged.
"""

PLANT_WINDOW_START = 576
PLANT_WINDOW_END = 648
MAX_CONVERSIONS_PER_STEP = 2
DEFAULT_MAX_PLANTS = 8

# player -> {"last_step": int, "converted": int}
_STATE = {}


def reset():
    """Clear the per-game conversion counters (used by the checks)."""
    _STATE.clear()


def _player_state(player, step):
    state = _STATE.get(player)
    if state is None or step < state["last_step"]:
        # New game (or first sighting): start the counter over.
        state = {"last_step": step, "converted": 0}
        _STATE[player] = state
    else:
        state["last_step"] = step
    return state


def _is_wheat_plant(command):
    return isinstance(command, (list, tuple)) and list(command) == ["PLANT", "WHEAT"]


def apply_strawberry_endgame(observation, action, max_plants=DEFAULT_MAX_PLANTS):
    """Convert up to MAX_CONVERSIONS_PER_STEP late wheat plantings to strawberry.

    Returns the action unchanged (the same object) unless a conversion happens.
    """
    try:
        step = int(observation["step"])
    except Exception:
        return action
    if not (PLANT_WINDOW_START <= step <= PLANT_WINDOW_END):
        return action
    try:
        max_plants = int(max_plants)
    except Exception:
        return action
    if max_plants <= 0:
        return action
    try:
        player = int(observation.get("player", 0))
    except Exception:
        player = 0
    state = _player_state(player, step)
    remaining = max_plants - state["converted"]
    if remaining <= 0:
        return action
    try:
        private = observation.get("private") or {}
        seeds = private.get("seeds") or {}
        seed_stock = int(seeds.get("STRAWBERRY", 0) or 0)
    except Exception:
        return action
    if seed_stock <= 0:
        # No strawberry seeds at this step: leave the wheat planting alone.
        return action
    budget = min(remaining, seed_stock, MAX_CONVERSIONS_PER_STEP)

    farmer = action.get("farmer")
    hands = action.get("hands") or []
    farmer_hit = _is_wheat_plant(farmer)
    hand_hits = [i for i, command in enumerate(hands) if _is_wheat_plant(command)]
    picks = ([("farmer", None)] if farmer_hit else []) + [("hands", i) for i in hand_hits]
    picks = picks[:budget]
    if not picks:
        return action

    changed = dict(action)
    if ("farmer", None) in picks:
        changed["farmer"] = ["PLANT", "STRAWBERRY"]
    hand_picks = {i for kind, i in picks if kind == "hands"}
    if hand_picks:
        new_hands = list(hands)
        for i in hand_picks:
            new_hands[i] = ["PLANT", "STRAWBERRY"]
        changed["hands"] = new_hands
    state["converted"] += len(picks)
    return changed
