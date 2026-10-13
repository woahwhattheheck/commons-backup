# SPDX-License-Identifier: Apache-2.0
"""P02: bounded timing/funding certificate for an already represented BUY_LAND.

The helper never calls a producer and never credits future sale proceeds.  It
finds the first represented PLANT on the quadrant that the next BUY_LAND would
unlock, requires a same-day WATER, checks seed availability under native
unit-before-market ordering, and evaluates +/- a bounded shift only when the
BUY_LAND can be moved without shifting any other executable market order.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass

MOVES = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0)}
PASS = ["PASS"]
OWNED_TILE_OPS = {"PLANT", "WATER", "HARVEST", "FERTILIZE", "DIG", "BUILD_COOP", "BUILD_PASTURE",
                  "FEED", "CARE", "COLLECT_FERTILIZER", "PLACE"}


def _integer(value, name, low=0, high=1_000_000):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in {low}..{high}")
    return value


def _row(route, step):
    if not 0 <= step < len(route):
        return {"farmer": PASS, "hands": [], "market": []}
    value = route[step]
    if not isinstance(value, Mapping):
        raise ValueError("route rows must be mappings")
    return value


def _units(row):
    return [row.get("farmer", PASS), *row.get("hands", [])]


def _quadrant(pos, board):
    x, y = pos; half = board // 2
    return ("N" if y < half else "S") + ("W" if x < half else "E")


def _move(pos, action, board):
    op = action[0] if isinstance(action, list) and action else "PASS"
    delta = MOVES.get(op)
    if delta is None:
        return pos
    nxt = (pos[0] + delta[0], pos[1] + delta[1])
    return nxt if 0 <= nxt[0] < board and 0 <= nxt[1] < board else pos


def _market_prefix(row, limit):
    market = row.get("market", [])
    if not isinstance(market, list):
        raise ValueError("market queue must be a list")
    return market[:limit]


def _land_orders(row, limit):
    return [(i, o) for i, o in enumerate(_market_prefix(row, limit))
            if isinstance(o, list) and o and o[0] == "BUY_LAND"]


def _append_slot(queue, limit):
    """Trailing executable slack only; do not shift commitments or inactive tail."""
    prefix = list(queue)[:limit]
    last = max((i for i, order in enumerate(prefix) if order), default=-1)
    for slot in range(last + 1, limit):
        if slot >= len(queue) or not queue[slot]:
            return slot
    return None


def _fixed_spend(mechanics, order, unlocked_count, hires, config):
    if not order:
        return 0, unlocked_count, hires, None
    if not isinstance(order, list):
        return None, unlocked_count, hires, "unsupported_market_order"
    op = order[0]
    if op == "SELL":
        return 0, unlocked_count, hires, None  # never credit future sale cash
    if op == "HIRE":
        cost = int(mechanics._hire_cost(hires, int(config.get("farmHandCostMult", 1))))
        return cost, unlocked_count, hires + 1, None
    if op == "BUY_LAND":
        index = unlocked_count - 1
        prices = mechanics.LAND_PRICES
        if not 0 <= index < len(prices):
            return None, unlocked_count, hires, "no_remaining_land"
        return int(prices[index]), unlocked_count + 1, hires, None
    if len(order) < 3 or type(order[2]) is not int or order[2] <= 0:
        return None, unlocked_count, hires, "unsupported_market_order"
    item, count = order[1], order[2]
    if op == "BUY_SEED":
        data = mechanics.CROPS.get(item)
        if not isinstance(data, Mapping):
            return None, unlocked_count, hires, "unknown_seed"
        return int(data["seed"]) * count, unlocked_count, hires, None
    if op == "BUY_ANIMAL":
        data = mechanics.ANIMALS.get(item)
        if not isinstance(data, Mapping):
            return None, unlocked_count, hires, "unknown_animal"
        return int(data["cost"]) * count, unlocked_count, hires, None
    if op == "BUY_PRODUCT":
        return None, unlocked_count, hires, "variable_price_purchase_before_use"
    return None, unlocked_count, hires, "unsupported_market_order"


@dataclass(frozen=True)
class UnlockTiming:
    quadrant: str
    land_cost: int
    original_step: int
    original_slot: int
    first_plant_step: int
    first_water_step: int
    crop: str
    tile: tuple
    last_safe_purchase_step: int
    recommended_step: int
    recommended_slot: int
    funded_cost_through_plant: int
    cash_headroom: int
    earliest_min_sale_step: int

    def as_dict(self):
        return {"quadrant": self.quadrant, "land_cost": self.land_cost,
                "original_step": self.original_step, "original_slot": self.original_slot,
                "first_plant_step": self.first_plant_step, "first_water_step": self.first_water_step,
                "crop": self.crop, "tile": list(self.tile),
                "last_safe_purchase_step": self.last_safe_purchase_step,
                "recommended_step": self.recommended_step, "recommended_slot": self.recommended_slot,
                "funded_cost_through_plant": self.funded_cost_through_plant,
                "cash_headroom": self.cash_headroom,
                "earliest_min_sale_step": self.earliest_min_sale_step}


def _trace_positions_and_first_plant(mechanics, obs, route, quadrant, board, now, end, *, turns, limit):
    farm = obs["farms"][int(obs["player"])]
    positions = [tuple(farm["farmer"]), *[tuple(p) for p in farm.get("hands", [])]]
    seeds = {k: int(v) for k, v in obs["private"].get("seeds", {}).items()
             if type(v) is int and v >= 0}
    first = None
    water_step = None
    for step in range(now, end + 1):
        row = _row(route, step)
        actions = _units(row)
        if len(actions) > len(positions):
            return None, None, {"reason": "dynamic_worker_count_before_first_use", "step": step}
        for worker, action in enumerate(actions[:len(positions)]):
            if not isinstance(action, list) or not action:
                continue
            op = action[0]
            if op in MOVES:
                positions[worker] = _move(positions[worker], action, board)
                continue
            pos = positions[worker]
            if first is None and _quadrant(pos, board) == quadrant and op in OWNED_TILE_OPS and op != "PLANT":
                return None, None, {"reason": "earlier_target_quadrant_use_out_of_scope",
                                    "step": step, "worker": worker, "action": deepcopy(action)}
            if op == "PLANT" and len(action) > 1:
                crop = action[1]
                if seeds.get(crop, 0) <= 0:
                    # Market seed purchases at this same step happen later and cannot fund PLANT.
                    if _quadrant(pos, board) == quadrant and first is None:
                        return None, None, {"reason": "first_plant_unfunded_seed", "step": step, "crop": crop}
                    continue
                seeds[crop] -= 1
                if _quadrant(pos, board) == quadrant and first is None:
                    first = (step, worker, pos, crop)
            if op == "WATER" and first is not None and pos == first[2] and step // turns == first[0] // turns:
                water_step = step
        for order in _market_prefix(row, limit):
            if isinstance(order, list) and len(order) >= 3 and order[0] == "BUY_SEED" and type(order[2]) is int and order[2] > 0:
                seeds[order[1]] = seeds.get(order[1], 0) + order[2]
        if first is not None and water_step is not None:
            return first, water_step, None
        if first is not None and step // turns > first[0] // turns:
            return first, None, {"reason": "first_plant_missing_same_day_water", "step": first[0]}
    return first, water_step, None


def _funded_at_step(mechanics, obs, config, route, original_step, original_slot,
                    candidate_step, candidate_slot, plant_step, limit):
    cash = int(obs["farms"][int(obs["player"])]["money"])
    unlocked = len(obs["farms"][int(obs["player"])]["unlocked_quadrants"])
    hires = int(obs["farms"][int(obs["player"])].get("hires_today", 0))
    spent = 0
    now = int(obs["step"])
    for step in range(now, plant_step + 1):
        if step > now and step % int(config.get("turnsPerDay", 24)) == 0:
            hires = 0
        queue = deepcopy(list(_row(route, step).get("market", [])))
        if step == original_step and original_slot < len(queue):
            queue[original_slot] = []
        if step == candidate_step:
            while len(queue) <= candidate_slot:
                queue.append([])
            if queue[candidate_slot]:
                return None, {"reason": "candidate_slot_not_empty", "step": step, "slot": candidate_slot}
            queue[candidate_slot] = ["BUY_LAND"]
        for slot, order in enumerate(queue[:limit]):
            cost, unlocked, hires, error = _fixed_spend(mechanics, order, unlocked, hires, config)
            if error:
                return None, {"reason": error, "step": step, "slot": slot}
            spent += cost
            if spent > cash:
                return None, {"reason": "fixed_prefix_not_funded", "step": step, "slot": slot,
                              "required": spent, "cash": cash}
    return spent, {"reason": "funded", "cash_headroom": cash - spent}


def analyze_unlock_timing(mechanics, observation, configuration, route, *, max_shift=4):
    """Return the latest certified purchase step for one represented next-quadrant PLANT bundle."""
    config = dict(configuration or {})
    now = _integer(observation.get("step"), "step")
    board = _integer(config.get("boardSize", len(observation["farms"][int(observation["player"])]["tiles"])), "boardSize", 2, 100)
    turns = _integer(config.get("turnsPerDay", 24), "turnsPerDay", 1)
    last = _integer(config.get("episodeSteps", 720), "episodeSteps", 2) - 2
    limit = _integer(config.get("maxMarketOrdersPerTurn", 10), "maxMarketOrdersPerTurn", 1, 64)
    farm = observation["farms"][int(observation["player"])]
    unlocked = list(farm.get("unlocked_quadrants", []))
    extra = len(unlocked) - 1
    if extra >= len(mechanics.LAND_ORDER):
        return None, {"certified": False, "reason": "all_land_already_unlocked"}
    quadrant = mechanics.LAND_ORDER[extra]
    if quadrant in unlocked:
        return None, {"certified": False, "reason": "target_quadrant_already_unlocked"}
    purchases = []
    horizon = min(last, now + 4 * turns)
    for step in range(now, horizon + 1):
        for slot, order in _land_orders(_row(route, step), limit):
            purchases.append((step, slot))
    if len(purchases) != 1:
        return None, {"certified": False, "reason": "need_exactly_one_represented_land_purchase",
                      "purchase_count": len(purchases)}
    original_step, original_slot = purchases[0]
    first, water_step, trace_error = _trace_positions_and_first_plant(
        mechanics, observation, route, quadrant, board, now, horizon, turns=turns, limit=limit)
    if trace_error:
        return None, {"certified": False, **trace_error}
    if first is None:
        return None, {"certified": False, "reason": "no_represented_plant_use_of_next_quadrant"}
    plant_step, _, tile, crop = first
    if water_step is None:
        return None, {"certified": False, "reason": "first_plant_missing_same_day_water"}
    # BUY_LAND is a market order after units, so it must execute strictly before PLANT.
    last_safe = plant_step - 1
    if last_safe < now:
        return None, {"certified": False, "reason": "land_cannot_unlock_before_first_plant"}
    crop_data = mechanics.CROPS.get(crop)
    if not isinstance(crop_data, Mapping):
        return None, {"certified": False, "reason": "unknown_crop"}
    first_yield_day = plant_step // turns + int(crop_data["first_yield_day"])
    # Necessary physical lower bound: harvest + minimum travel to a shed access + DROP.
    half = board // 2
    access = ((half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half))
    min_return = min(abs(tile[0] - x) + abs(tile[1] - y) for x, y in access)
    earliest_sale = first_yield_day * turns + 1 + min_return
    if earliest_sale > last:
        return None, {"certified": False, "reason": "crop_has_no_minimum_terminal_sale_path",
                      "earliest_min_sale_step": earliest_sale, "last_action_step": last}
    low = max(now, original_step - _integer(max_shift, "max_shift", 0, 32))
    high = min(last_safe, original_step + max_shift)
    choices = []
    for step in range(low, high + 1):
        queue = list(_row(route, step).get("market", []))
        if step == original_step:
            slot = original_slot
        else:
            slot = _append_slot(queue, limit)
        if slot is None:
            continue
        funded, report = _funded_at_step(mechanics, observation, config, route,
                                         original_step, original_slot, step, slot, plant_step, limit)
        if funded is not None:
            choices.append((step, slot, funded, report["cash_headroom"]))
    if not choices:
        return None, {"certified": False, "reason": "no_funded_unlock_step_in_shift_window",
                      "original_step": original_step, "last_safe_purchase_step": last_safe}
    # Latest safe/funded step minimizes stranded cash while preserving the represented PLANT/WATER bundle.
    recommended_step, recommended_slot, funded_cost, headroom = max(choices)
    land_cost = int(mechanics.LAND_PRICES[extra])
    result = UnlockTiming(quadrant, land_cost, original_step, original_slot, plant_step, water_step,
                          crop, tile, last_safe, recommended_step, recommended_slot,
                          funded_cost, headroom, earliest_sale)
    return result, {"certified": True, "reason": "latest_funded_unlock_before_represented_plant",
                    "choice_count": len(choices), "choices": [list(c) for c in choices],
                    "timing": result.as_dict(),
                    "scope": "one represented BUY_LAND; existing workers; first next-quadrant PLANT plus same-day WATER; fixed-cost prefix only; no sale-credit"}
