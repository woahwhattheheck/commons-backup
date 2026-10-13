# SPDX-License-Identifier: Apache-2.0
"""Cheap, conditional redundant-worker proposal over an explicit incumbent route.

This is a selected-action transform over the producer-owned route, not a second
policy or a future-price model. It first proves the landed narrow remaining-
shift physical equivalence for trailing hires. Before deleting such a hire, it
may consume otherwise idle redundant capacity with one bounded complete harvest
job: travel from the actual spawn, harvest an unshared observed receipt, deposit
it, and rejoin the exact incumbent endpoint before reset. The job is admitted
only when its current-quote deposited value strictly exceeds that hire's exact
wage. No future sale, next-day persistence, opponent response, or terminal gain
is credited.
"""
from __future__ import annotations

import copy
import math
from collections import Counter
from typing import Any, Mapping, Sequence

NO_ORDER = ["SELL", "WHEAT", 0]
MOVES = {"NORTH": (0, -1), "SOUTH": (0, 1), "WEST": (-1, 0), "EAST": (1, 0)}

def _uint(value: Any, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _units(action: Mapping[str, Any]) -> list:
    return [action.get("farmer", ["PASS"]), *action.get("hands", [])]


def _set_unit(row: dict, worker: int, action: list) -> None:
    if worker == 0:
        row["farmer"] = list(action); return
    hands = row.setdefault("hands", [])
    while len(hands) < worker:
        hands.append(["PASS"])
    hands[worker - 1] = list(action)


def _path(a: Sequence[int], b: Sequence[int]) -> list[list[str]]:
    out = []
    if b[0] > a[0]: out += [["EAST"]] * (b[0] - a[0])
    elif b[0] < a[0]: out += [["WEST"]] * (a[0] - b[0])
    if b[1] > a[1]: out += [["SOUTH"]] * (b[1] - a[1])
    elif b[1] < a[1]: out += [["NORTH"]] * (a[1] - b[1])
    return out


def _distance(a: Sequence[int], b: Sequence[int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _harvest_item(mechanics: Any, tile: Any, day: int) -> tuple[str, int] | None:
    if not isinstance(tile, dict):
        return None
    quantity = tile.get("yield_units", 0)
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        return None
    if tile.get("kind") == "PLANT":
        crop = tile.get("crop")
        data = mechanics.CROPS.get(crop)
        if data is None or day - tile.get("planted_day", day) < data["first_yield_day"]:
            return None
        return crop, quantity
    animal = tile.get("animal")
    if animal in mechanics.ANIMALS:
        return mechanics.ANIMALS[animal]["product"], quantity
    return None


def _productive_detour(
    mechanics: Any, observation: Mapping[str, Any], post_farm: Mapping[str, Any],
    post_private: Mapping[str, Any], route: Sequence[Mapping[str, Any]], events: list[tuple],
    final_positions: list[list[int]], worker: int, wage: int,
    step: int, end: int, board: int, cap: int, limit: int, reserved: set[tuple[int, int]],
) -> dict | None:
    """Return one producer-route harvest/deposit/rejoin witness, or None.

    This screen is deliberately stricter than the engine: it refuses a target
    touched by another actor, any concurrent pre-deposit DROP, shed-access PLACE,
    or product/animal buy, and any job that cannot rejoin the incumbent endpoint
    before reset.
    """
    if worker >= len(final_positions) or not hasattr(route, "__setitem__"):
        return None
    farm = post_farm
    start_event = next((e for e in events if e[1] == worker), None)
    if start_event is None:
        return None
    start = (start_event[3], start_event[4])
    goal = tuple(final_positions[worker])
    remaining = end - step
    if remaining < 3:
        return None
    stock = sum(post_private["shed"].values()) + sum(
        sum(inv.values()) for inv in post_private["inventories"])
    market = observation.get("market", {})
    inventory = market.get("inventory", {})
    params = market.get("params")
    day = step // max(1, int(observation.get("turnsPerDay", 24)))
    day = int(observation.get("day", day))
    touched = {(e[3], e[4]) for e in events
               if e[1] != worker and e[2] not in (*MOVES, "PASS")}
    candidates = []
    for y, row in enumerate(farm["tiles"]):
        for x, tile in enumerate(row):
            target = (x, y)
            if target in reserved or target in touched:
                continue
            item_qty = _harvest_item(mechanics, tile, day)
            if item_qty is None:
                continue
            item, quantity = item_qty
            if stock + quantity > cap or item not in inventory:
                continue
            half = board // 2
            sheds = ((half-1, half-1), (half, half-1), (half-1, half), (half, half))
            for shed in sheds:
                harvest_step = step + 1 + _distance(start, target)
                expiry = tile.get("max_lifespan_step", -1) if isinstance(tile, dict) else -1
                if isinstance(expiry, int) and expiry >= 0 and expiry <= harvest_step:
                    continue
                trial = (_path(start, target) + [["HARVEST"]] + _path(target, shed)
                         + [["DROP"]] + _path(shed, goal))
                if len(trial) > remaining:
                    continue
                drop_offset = (_distance(start, target) + 1 + _distance(target, shed))
                drop_step = step + 1 + drop_offset
                conflict = False
                sheds_set = set(sheds)
                for e in events:
                    if e[1] == worker or not (step < e[0] <= drop_step):
                        continue
                    if e[2] == "DROP":
                        conflict = True; break
                    if e[2] == "PLACE" and (e[3], e[4]) in sheds_set:
                        conflict = True; break
                if conflict:
                    continue
                for t in range(step + 1, min(drop_step, end) + 1):
                    for order in route[t].get("market", [])[:limit]:
                        if isinstance(order, list) and order and order[0] in ("BUY_PRODUCT", "BUY_ANIMAL"):
                            conflict = True; break
                    if conflict: break
                if conflict:
                    continue
                value = sum(mechanics.market_price(item, inventory[item] + q, params)
                            for q in range(quantity))
                if value <= wage:
                    continue
                sequence = trial + [["PASS"]] * (remaining - len(trial))
                candidates.append((value - wage, value, -len(trial), target, shed,
                                   sequence, item, quantity, drop_step))
    if not candidates:
        return None
    _, value, _, target, shed, sequence, item, quantity, drop_step = max(
        candidates, key=lambda c: c[:5])
    return {"worker": worker, "wage": wage, "current_quote_value": value,
            "wage_payback": value - wage, "item": item, "quantity": quantity,
            "target": list(target), "deposit_step": drop_step,
            "rejoin": list(goal), "useful_worker_actions": sum(
                a[0] not in (*MOVES, "PASS") for a in sequence),
            "completed_jobs": 1, "sequence": sequence}


def propose_redundant_hires(
    mechanics: Any, observation: Mapping[str, Any], configuration: Mapping[str, Any] | None,
    selected_action: Mapping[str, Any], *, route: Sequence[Mapping[str, Any]],
    route_id: str, route_switch_steps: Sequence[int], max_route_steps: int = 48,
) -> tuple[dict, dict]:
    """Return a bounded hire/route proposal and exact limits; never call a policy."""
    out = copy.deepcopy(dict(selected_action))
    report = {"changed": False, "route_changed": False, "reason": "no_hire", "route_id": route_id,
              "removed_order_indices": [], "immediate_wage_saving": 0,
              "useful_worker_actions": 0, "completed_jobs": 0, "wage_payback": 0,
              "productive_detours": [], "terminal_gain": None,
              "scope": "conditional same-day route certificate; current quote only, not future cash or win proof"}
    farms = observation.get("farms")
    player = observation.get("player")
    if (not isinstance(farms, list) or len(farms) != 2
            or type(player) is not int or player not in (0, 1)):
        report["reason"] = "unsupported_public_seat_schema"
        return out, report
    cfg = dict(configuration or {})
    board = _uint(cfg.get("boardSize", 10), "boardSize", 1)
    day_len = _uint(cfg.get("turnsPerDay", 24), "turnsPerDay", 1)
    episode = _uint(cfg.get("episodeSteps", 720), "episodeSteps", 2)
    cap = _uint(cfg.get("shedCapacity", 100), "shedCapacity", 1)
    limit = max(1, _uint(cfg.get("maxMarketOrdersPerTurn", 10), "maxMarketOrdersPerTurn"))
    mult = _uint(cfg.get("farmHandCostMult", 1), "farmHandCostMult")
    _uint(max_route_steps, "max_route_steps", 1)
    step = observation.get("step")
    if step is None:
        step = _uint(observation["day"], "day") * day_len + _uint(observation["hour"], "hour")
    step = _uint(step, "step")
    end = min((step // day_len + 1) * day_len - 1, episode - 2)
    report.update(step=step, end_step=end)
    if step > end or end - step > max_route_steps:
        report["reason"] = "outside_bounded_shift"; return out, report
    queue = out.get("market", [])
    if not isinstance(queue, list):
        report["reason"] = "unsupported_queue"; return out, report
    hires = []
    for j, order in enumerate(queue[:limit]):
        if isinstance(order, list) and order and order[0] == "HIRE":
            hires.append(j)
        elif (isinstance(order, list) and len(order) == 3 and order[0] == "SELL"
              and order[1] in mechanics.PRODUCTS and order[2] == 0):
            continue
        else:
            report["reason"] = "active_or_unknown_nonhire_order"; return out, report
    if not hires or mult == 0:
        report["reason"] = "no_positive_cost_hire"; return out, report
    if not route_id or len(route) <= end:
        report["reason"] = "incomplete_route"; return out, report
    if any(step < _uint(t, "route switch") <= end for t in route_switch_steps):
        report["reason"] = "possible_route_switch"; return out, report
    for t in range(step + 1, end + 1):
        if any(isinstance(o, list) and o and o[0] == "HIRE"
               for o in route[t].get("market", [])[:limit]):
            report["reason"] = "later_hire_changes_cost_or_spawn"; return out, report

    me = _uint(observation["player"], "player")
    farm = copy.deepcopy(observation["farms"][me])
    private = copy.deepcopy(observation["private"])
    if len(farm["tiles"]) != board or any(len(row) != board for row in farm["tiles"]):
        report["reason"] = "board_shape"; return out, report
    current = _units(out)
    demand = Counter(a[1] for a in current if isinstance(a, list) and len(a) > 1 and a[0] == "PLANT")
    blocked = {p for p, n in demand.items() if n > private.get("seeds", {}).get(p, 0)}
    for i, action in enumerate(current):
        if isinstance(action, list) and len(action) > 1 and action[0] == "PLANT" and action[1] in blocked:
            action = ["PASS"]
        mechanics._apply_unit_action(farm, private, i, action, board, step // day_len, day_len, cap)
    existing = len(farm["hands"])
    costs = [mechanics._hire_cost(farm["hires_today"] + j, mult) for j in range(len(hires))]
    cash = farm["money"]
    if isinstance(cash, bool) or not isinstance(cash, (float, int)) or not math.isfinite(cash) or cash < sum(costs):
        report["reason"] = "current_hires_not_all_funded"; return out, report
    for _ in hires:
        mechanics._do_hire(farm, private, board, mult)
    positions = [list(farm["farmer"]), *copy.deepcopy(farm["hands"])]
    events = []
    for t in range(step + 1, end + 1):
        unit_program = _units(route[t])
        for i, pos in enumerate(positions):
            explicit = i < len(unit_program)
            a = unit_program[i] if explicit else ["PASS"]
            if not isinstance(a, list) or not a or not isinstance(a[0], str):
                report["reason"] = "unsupported_unit_program"; return out, report
            op = a[0]; x, y = pos
            events.append((t, i, op, x, y, explicit))
            if op in MOVES:
                dx, dy = MOVES[op]; nx, ny = x + dx, y + dy
                if 0 <= nx < board and 0 <= ny < board:
                    pos[:] = [nx, ny]

    best = 0; best_witnesses = []; checks = 0
    for remove_count in range(1, len(hires) + 1):
        first_removed = 1 + existing + len(hires) - remove_count
        removed = [e for e in events if e[1] >= first_removed]
        valid = True; witnesses = []
        for t, i, op, x, y, explicit in removed:
            checks += 1
            if op not in (*MOVES, "WATER", "PASS"):
                valid = False; break
            tile = farm["tiles"][y][x]
            if explicit and isinstance(tile, dict):
                if tile.get("kind") == "WEED":
                    valid = False; break
                expiry = tile.get("max_lifespan_step", -1)
                if tile.get("kind") == "PLANT" and expiry >= 0 and expiry <= end:
                    valid = False; break
            if op != "WATER":
                continue
            if not isinstance(tile, dict) or tile.get("kind") != "PLANT":
                valid = False; break
            touching = [e for e in events if e[3:5] == (x, y)]
            if any(e[2] not in (*MOVES, "WATER", "PASS") for e in touching):
                valid = False; break
            kept = [e for e in touching if e[1] < first_removed and e[2] == "WATER"]
            if not tile.get("watered_today") and not kept:
                valid = False; break
            witnesses.append({"worker": i, "step": t, "position": [x, y],
                              "already_watered": bool(tile.get("watered_today")),
                              "retained_watering": [[e[0], e[1]] for e in kept]})
        if not valid:
            break
        best = remove_count; best_witnesses = witnesses
    report["route_events_checked"] = checks
    if not best:
        report["reason"] = "no_redundant_trailing_worker"; return out, report

    protected = 0; reserved: set[tuple[int, int]] = set(); detours = []
    first_removed = 1 + existing + len(hires) - best
    cost_start = len(hires) - best
    for offset in range(best):
        worker = first_removed + offset
        witness = _productive_detour(mechanics, observation, farm, private, route, events, positions,
                                      worker, costs[cost_start + offset], step, end,
                                      board, cap, limit, reserved)
        if witness is None:
            break
        detours.append(witness); reserved.add(tuple(witness["target"])); protected += 1
        break
    for witness in detours:
        for offset, action in enumerate(witness.pop("sequence")):
            t = step + 1 + offset
            row = copy.deepcopy(route[t]); _set_unit(row, witness["worker"], action); route[t] = row
    remove_count = best - protected
    omitted = hires[-remove_count:] if remove_count else []
    for j in omitted:
        out["market"][j] = list(NO_ORDER)
    report.update(
        changed=bool(omitted), route_changed=bool(detours),
        reason=("productive_detour_and_redundant_tail" if detours and omitted else
                "productive_detour_protected_hire" if detours else
                "redundant_watering_or_empty_tail"),
        removed_order_indices=omitted, removed_workers=remove_count,
        protected_workers=protected,
        immediate_wage_saving=sum(costs[-remove_count:]) if remove_count else 0,
        watering_witnesses=best_witnesses,
        productive_detours=detours,
        useful_worker_actions=sum(w["useful_worker_actions"] for w in detours),
        completed_jobs=sum(w["completed_jobs"] for w in detours),
        wage_payback=sum(w["wage_payback"] for w in detours),
        future_cash_compatibility="not established; deposited work is valued only at the current observed quote",
    )
    return out, report
