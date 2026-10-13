# SPDX-License-Identifier: Apache-2.0
"""Cash-backed terminal-day labor surge over the existing committed route.

This module is deliberately a transform, not a controller.  It may append HIRE
orders to the already-selected current action and write only the newly-created
workers' future actions into an existing route tape.  A hire is admitted only
when a disjoint observed harvest can be routed to a shed and sold on the DROP
turn with current-quote value strictly above the exact Fibonacci wage.

The quote is a screening certificate, not a future-price or opponent oracle.
The component is therefore suitable for source-bound experimentation and engine
countercontrols; production activation still requires measured paired EV.
"""
from __future__ import annotations

import copy
import math
from collections import Counter
from typing import Any, Mapping, Sequence

MOVES = {"NORTH": (0, -1), "SOUTH": (0, 1), "WEST": (-1, 0), "EAST": (1, 0)}
PASS = ["PASS"]


def _uint(value: Any, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _path(a: Sequence[int], b: Sequence[int]) -> list[list[str]]:
    out: list[list[str]] = []
    if b[0] > a[0]:
        out += [["EAST"]] * (b[0] - a[0])
    elif b[0] < a[0]:
        out += [["WEST"]] * (a[0] - b[0])
    if b[1] > a[1]:
        out += [["SOUTH"]] * (b[1] - a[1])
    elif b[1] < a[1]:
        out += [["NORTH"]] * (a[1] - b[1])
    return out


def _shed_tiles(board: int) -> tuple[tuple[int, int], ...]:
    half = board // 2
    return ((half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half))


def _set_unit_if_empty(row: dict, worker: int, action: list) -> bool:
    """Write only into absent/PASS capacity; never overwrite producer work."""
    if worker == 0:
        cur = row.get("farmer", PASS)
        if cur != PASS:
            return False
        row["farmer"] = list(action)
        return True
    hands = row.setdefault("hands", [])
    while len(hands) < worker:
        hands.append(list(PASS))
    cur = hands[worker - 1]
    if cur != PASS:
        return False
    hands[worker - 1] = list(action)
    return True


def _units(row: Mapping[str, Any]) -> list:
    return [row.get("farmer", PASS), *row.get("hands", [])]


def _harvest_item(mechanics: Any, tile: Any, day: int, harvest_step: int) -> tuple[str, int] | None:
    if not isinstance(tile, dict):
        return None
    quantity = tile.get("yield_units", 0)
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        return None
    if tile.get("kind") == "PLANT":
        crop = tile.get("crop")
        data = mechanics.CROPS.get(crop)
        if data is None:
            return None
        if day - int(tile.get("planted_day", day)) < int(data["first_yield_day"]):
            return None
        expiry = tile.get("max_lifespan_step", -1)
        if isinstance(expiry, int) and expiry >= 0 and expiry <= harvest_step:
            return None
        return crop, quantity
    animal = tile.get("animal")
    if animal in mechanics.ANIMALS:
        return mechanics.ANIMALS[animal]["product"], quantity
    return None


def _sale_value(mechanics: Any, observation: Mapping[str, Any], item: str, quantity: int,
                already_planned: int, parent_planned: int = 0) -> int:
    market = observation.get("market", {})
    inventory = market.get("inventory", {})
    if item not in inventory:
        return 0
    params = market.get("params")
    start = int(inventory[item]) + parent_planned + already_planned
    return sum(int(mechanics.market_price(item, start + q, params)) for q in range(quantity))


def _post_current_units(mechanics: Any, observation: Mapping[str, Any], selected: Mapping[str, Any],
                        board: int, day: int, day_len: int, cap: int) -> tuple[dict, dict]:
    player = _uint(observation.get("player"), "player")
    farms = observation.get("farms")
    if not isinstance(farms, list) or len(farms) != 2 or player not in (0, 1):
        raise ValueError("terminal labor surge requires exactly two public farm seats")
    farm = copy.deepcopy(farms[player])
    private = copy.deepcopy(observation.get("private"))
    if not isinstance(private, dict):
        raise ValueError("private observation must be a mapping")
    if len(farm.get("tiles", [])) != board or any(len(r) != board for r in farm["tiles"]):
        raise ValueError("board shape does not match configuration")
    rows = _units(selected)
    demand = Counter(
        action[1] for action in rows
        if isinstance(action, list) and len(action) >= 2 and action[0] == "PLANT"
    )
    blocked = {crop for crop, qty in demand.items()
               if qty > private.get("seeds", {}).get(crop, 0)}
    for idx, action in enumerate(rows):
        effective = action
        if (isinstance(action, list) and len(action) >= 2 and action[0] == "PLANT"
                and action[1] in blocked):
            effective = ["PASS"]
        mechanics._apply_unit_action(farm, private, idx, effective, board, day, day_len, cap)
    return farm, private


def _simulate_existing_current_hires(mechanics: Any, farm: dict, private: dict,
                                     queue: Sequence[Any], limit: int, board: int, mult: int) -> int:
    count = 0
    for order in list(queue)[:limit]:
        if not isinstance(order, list) or not order or order[0] not in ("HIRE", "SELL"):
            raise ValueError("current terminal prefix contains a cash-spending or unknown order")
        if order[0] != "HIRE":
            continue
        before = len(farm["hands"])
        mechanics._do_hire(farm, private, board, mult)
        if len(farm["hands"]) != before + 1:
            raise ValueError("existing executable HIRE is not funded by observed cash without sale financing")
        count += 1
    return count


def _trace_parent_harvests(route: Sequence[Mapping[str, Any]], positions: list[list[int]],
                           start: int, final: int, board: int, limit: int) -> set[tuple[int, int]]:
    """Reserve harvest cells already consumed by the parent route.

    Future executable HIREs are rejected because they would change worker index
    identity and require a richer market replay than this transform owns.
    """
    reserved: set[tuple[int, int]] = set()
    pos = copy.deepcopy(positions)
    for step in range(start, final + 1):
        row = route[step]
        for order in row.get("market", [])[:limit]:
            if isinstance(order, list) and order and order[0] == "HIRE":
                raise ValueError("future executable HIRE changes terminal worker identity")
        units = _units(row)
        for idx in range(min(len(pos), len(units))):
            action = units[idx]
            if not isinstance(action, list) or not action or not isinstance(action[0], str):
                continue
            op = action[0]
            x, y = pos[idx]
            if op == "HARVEST":
                reserved.add((x, y))
            elif op in MOVES:
                dx, dy = MOVES[op]
                nx, ny = x + dx, y + dy
                if 0 <= nx < board and 0 <= ny < board:
                    pos[idx] = [nx, ny]
    return reserved




def _parent_sale_volume(route: Sequence[Mapping[str, Any]], now: int, final: int, limit: int) -> dict[str, int]:
    """Conservative own-route volume: count every executable terminal SELL before pricing extras."""
    volume: dict[str, int] = {}
    for step in range(now, final + 1):
        market = route[step].get("market", [])
        if not isinstance(market, list):
            raise ValueError(f"unsupported market row at step {step}")
        for order in market[:limit]:
            if not isinstance(order, list) or not order:
                continue
            if order[0] == "SELL" and len(order) >= 3 and isinstance(order[2], int) and not isinstance(order[2], bool):
                volume[order[1]] = volume.get(order[1], 0) + max(0, order[2])
    return volume

def _snapshot_map(snapshots: Sequence[Mapping[str, Any]], now: int, final: int) -> dict[int, Mapping[str, Any]]:
    by_step: dict[int, Mapping[str, Any]] = {}
    for snap in snapshots:
        step = snap.get("step")
        if isinstance(step, int) and now <= step <= final:
            by_step[step] = snap
    if any(step not in by_step for step in range(now, final + 1)):
        raise ValueError("complete terminal before-market snapshots are required")
    for step, snap in by_step.items():
        shed = snap.get("post_unit_shed")
        if not isinstance(shed, dict) or any(
            isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in shed.values()
        ):
            raise ValueError(f"invalid post_unit_shed snapshot at step {step}")
    return by_step


def propose_terminal_labor_surge(
    mechanics: Any,
    observation: Mapping[str, Any],
    configuration: Mapping[str, Any] | None,
    selected_action: Mapping[str, Any],
    *,
    route: Sequence[Mapping[str, Any]],
    snapshots: Sequence[Mapping[str, Any]],
    route_id: str = "",
    max_extra_hires: int = 9,
    min_quote_surplus: int = 1,
) -> tuple[dict, list[dict], dict]:
    """Return (selected_action, route, report) for a conservative terminal surge.

    Only the current callback receives new HIREs.  Each accepted hand has one
    distinct observed-yield job, an explicit HARVEST->DROP route, and a same-turn
    executable SELL appended after the DROP.  No meaningful producer action or
    market order is overwritten.  The screen values sales at the current quote
    after this proposal's own same-item planned volume; rival future orders are
    intentionally not forecast.
    """
    cfg = dict(configuration or {})
    board = _uint(cfg.get("boardSize", 10), "boardSize", 2)
    day_len = _uint(cfg.get("turnsPerDay", 24), "turnsPerDay", 1)
    episode = _uint(cfg.get("episodeSteps", 720), "episodeSteps", 3)
    cap = _uint(cfg.get("shedCapacity", 100), "shedCapacity", 1)
    limit = max(1, _uint(cfg.get("maxMarketOrdersPerTurn", 10), "maxMarketOrdersPerTurn"))
    mult = _uint(cfg.get("farmHandCostMult", 1), "farmHandCostMult")
    max_extra_hires = _uint(max_extra_hires, "max_extra_hires")
    min_quote_surplus = _uint(min_quote_surplus, "min_quote_surplus")
    now = _uint(observation.get("step"), "step")
    final = episode - 2
    final_day = final // day_len
    terminal_start = final_day * day_len + 2
    day = int(observation.get("day", now // day_len))

    report = {
        "changed": False,
        "route_changed": False,
        "reason": "outside_terminal_owner_window",
        "route_id": route_id,
        "step": now,
        "terminal_start": terminal_start,
        "final_step": final,
        "cash_score_only": True,
        "jobs": [],
        "extra_hires": 0,
        "cumulative_wage": 0,
        "current_quote_value": 0,
        "current_quote_surplus": 0,
        "scope": "current-quote screening only; no rival future-price or paired-EV claim",
    }
    out = copy.deepcopy(dict(selected_action))
    new_route = [copy.deepcopy(dict(r)) for r in route]
    if not (terminal_start <= now < final):
        return out, new_route, report
    if len(new_route) <= final:
        report["reason"] = "incomplete_terminal_route"
        return out, new_route, report
    queue = out.get("market", [])
    if not isinstance(queue, list):
        report["reason"] = "unsupported_market_queue"
        return out, new_route, report
    free_current_slots = max(0, limit - len(queue))
    if free_current_slots == 0 or max_extra_hires == 0:
        report["reason"] = "no_current_raw_market_capacity"
        return out, new_route, report

    try:
        snap_by_step = _snapshot_map(snapshots, now, final)
        farm, private = _post_current_units(mechanics, observation, out, board, day, day_len, cap)
        _simulate_existing_current_hires(mechanics, farm, private, queue, limit, board, mult)
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        report["reason"] = f"fail_closed:{type(exc).__name__}:{exc}"
        return out, new_route, report

    positions = [list(farm["farmer"]), *copy.deepcopy(farm["hands"])]
    try:
        parent_reserved = _trace_parent_harvests(new_route, positions, now + 1, final, board, limit)
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        report["reason"] = f"fail_closed:{type(exc).__name__}:{exc}"
        return out, new_route, report

    reserved = set(parent_reserved)
    planned_sales: dict[str, int] = {}
    extra_deposits: dict[int, int] = {}
    try:
        parent_sales = _parent_sale_volume(new_route, now, final, limit)
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        report["reason"] = f"fail_closed:{type(exc).__name__}:{exc}"
        return out, new_route, report
    max_new = min(max_extra_hires, free_current_slots)

    for _ in range(max_new):
        wage = int(mechanics._hire_cost(farm["hires_today"], mult))
        cash = farm.get("money")
        if isinstance(cash, bool) or not isinstance(cash, (int, float)) or not math.isfinite(cash) or cash < wage:
            break

        trial_farm = copy.deepcopy(farm)
        trial_private = copy.deepcopy(private)
        before_hands = len(trial_farm["hands"])
        mechanics._do_hire(trial_farm, trial_private, board, mult)
        if len(trial_farm["hands"]) != before_hands + 1:
            break
        worker = len(trial_farm["hands"])
        spawn = list(trial_farm["hands"][-1])
        candidates: list[tuple] = []

        for y, row in enumerate(trial_farm["tiles"]):
            for x, tile in enumerate(row):
                target = (x, y)
                if target in reserved:
                    continue
                for shed in _shed_tiles(board):
                    to_target = _path(spawn, target)
                    harvest_step = now + len(to_target) + 1
                    item_qty = _harvest_item(mechanics, tile, day, harvest_step)
                    if item_qty is None:
                        continue
                    item, quantity = item_qty
                    sequence = to_target + [["HARVEST"]] + _path(target, shed) + [["DROP"]]
                    drop_step = now + len(sequence)
                    if drop_step > final:
                        continue
                    snap = snap_by_step[drop_step]
                    baseline_stock = sum(int(v) for v in snap["post_unit_shed"].values())
                    if baseline_stock + extra_deposits.get(drop_step, 0) + quantity > cap:
                        continue
                    row_market = new_route[drop_step].get("market", [])
                    if not isinstance(row_market, list):
                        continue
                    if len(row_market) >= limit:
                        continue
                    # TerminalOwner forecasts SELL-only market rows.  Keep this transform
                    # behind that ownership boundary rather than composing with buys/hires.
                    if any(not (isinstance(o, list) and o and o[0] == "SELL") for o in row_market):
                        continue
                    baseline_item = int(snap["post_unit_shed"].get(item, 0))
                    parent_same_item = sum(
                        max(0, int(o[2])) for o in row_market
                        if len(o) >= 3 and o[0] == "SELL" and o[1] == item
                        and isinstance(o[2], int) and not isinstance(o[2], bool)
                    )
                    if parent_same_item > baseline_item:
                        continue
                    # A newly created worker must not overwrite any producer-authored future action.
                    conflict = False
                    for offset, action in enumerate(sequence, 1):
                        t = now + offset
                        units = _units(new_route[t])
                        if worker < len(units) and units[worker] != PASS:
                            conflict = True
                            break
                    if conflict:
                        continue
                    value = _sale_value(
                        mechanics, observation, item, quantity, planned_sales.get(item, 0),
                        parent_sales.get(item, 0),
                    )
                    surplus = value - wage
                    if surplus < min_quote_surplus:
                        continue
                    candidates.append((surplus, value, -len(sequence), target, shed,
                                       item, quantity, drop_step, sequence))

        if not candidates:
            break
        surplus, value, _, target, shed, item, quantity, drop_step, sequence = max(
            candidates, key=lambda c: (c[0], c[1], c[2], c[3], c[4])
        )

        # Commit the exact simulated hire and route only after all gates pass.
        farm, private = trial_farm, trial_private
        out.setdefault("market", []).append(["HIRE"])
        for offset, action in enumerate(sequence, 1):
            t = now + offset
            if not _set_unit_if_empty(new_route[t], worker, action):
                raise RuntimeError("internal route admission drift after candidate certification")
        new_route[drop_step].setdefault("market", []).append(["SELL", item, quantity])
        reserved.add(target)
        planned_sales[item] = planned_sales.get(item, 0) + quantity
        extra_deposits[drop_step] = extra_deposits.get(drop_step, 0) + quantity
        report["jobs"].append({
            "worker": worker,
            "wage": wage,
            "spawn": spawn,
            "target": list(target),
            "shed": list(shed),
            "item": item,
            "quantity": quantity,
            "drop_and_sell_step": drop_step,
            "current_quote_value": value,
            "current_quote_surplus": surplus,
            "actions": len(sequence),
        })

    if not report["jobs"]:
        report["reason"] = "no_profitable_executable_job"
        return out, new_route, report

    # Keep the route's current selected row coherent with the transformed return.
    new_route[now] = copy.deepcopy(out)
    report.update(
        changed=True,
        route_changed=True,
        reason="cash_backed_terminal_jobs",
        extra_hires=len(report["jobs"]),
        cumulative_wage=sum(j["wage"] for j in report["jobs"]),
        current_quote_value=sum(j["current_quote_value"] for j in report["jobs"]),
        current_quote_surplus=sum(j["current_quote_surplus"] for j in report["jobs"]),
        parent_harvest_targets_reserved=len(parent_reserved),
        raw_market_limit=limit,
        current_market_orders=len(out.get("market", [])),
        quote_volume_by_item=dict(planned_sales),
        activation="source_ready_default_off_until_paired_engine_ev",
    )
    return out, new_route, report



def _terminal_assignment_value(terminal: Any, farm: Mapping[str, Any], private: Mapping[str, Any],
                               start: int, final: int, day: int,
                               prices: Mapping[str, Any], cap: int) -> float | None:
    positions = [farm.get("farmer"), *farm.get("hands", [])]
    inventories = private.get("inventories", [])
    if not isinstance(inventories, list) or len(inventories) < len(positions):
        return None
    safe_prices: dict[str, float] = {}
    for item, price in prices.items():
        if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price):
            return None
        safe_prices[item] = max(1.0, float(price))
    routes, evaluations = terminal.assign_routes(
        farm,
        [dict(inventories[i]) for i in range(len(positions))],
        start,
        final,
        day,
        safe_prices,
        cap,
    )
    if not isinstance(routes, list) or not isinstance(evaluations, list):
        return None
    total = 0.0
    for row in evaluations:
        if row is None:
            continue
        if not isinstance(row, (tuple, list)) or not row:
            return None
        value = row[0]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return None
        total += max(0.0, float(value))
    return total


def propose_preterminal_hire_frontier(
    mechanics: Any,
    terminal: Any,
    observation: Mapping[str, Any],
    configuration: Mapping[str, Any] | None,
    selected_action: Mapping[str, Any],
    *,
    enabled: bool = False,
    min_quote_surplus: int = 250,
    max_extra_hires: int = 10,
) -> tuple[Mapping[str, Any], dict]:
    """Use the existing terminal router to value extra hands at final-day hour 1.

    This consumes the superseded #12762 donor seam: default step 697 is exactly
    one callback before T05 starts at 698.  HIRE executes after current unit rows,
    so accepted hands are visible to the unchanged terminal router on its first
    callback.  Only an all-HIRE current market prefix is accepted; no requested
    sale or buy is treated as realized funding.
    """
    if not enabled:
        return selected_action, {"changed": False, "reason": "disabled", "frontier": []}
    try:
        cfg = dict(configuration or {})
        board = _uint(cfg.get("boardSize", 10), "boardSize", 2)
        day_len = _uint(cfg.get("turnsPerDay", 24), "turnsPerDay", 1)
        episode = _uint(cfg.get("episodeSteps", 720), "episodeSteps", 3)
        cap = _uint(cfg.get("shedCapacity", 100), "shedCapacity", 1)
        limit = max(1, _uint(cfg.get("maxMarketOrdersPerTurn", 10), "maxMarketOrdersPerTurn"))
        mult = _uint(cfg.get("farmHandCostMult", 1), "farmHandCostMult")
        max_extra_hires = _uint(max_extra_hires, "max_extra_hires")
        min_quote_surplus = _uint(min_quote_surplus, "min_quote_surplus")
        now = _uint(observation.get("step"), "step")
        final = episode - 2
        day_start = (final // day_len) * day_len
        decision = day_start + 1
        terminal_start = day_start + 2
        report = {
            "changed": False,
            "reason": "not_preterminal_hire_decision",
            "step": now,
            "decision_step": decision,
            "terminal_start": terminal_start,
            "frontier": [],
            "scope": "existing terminal.assign_routes current-quote frontier; no rival-price or EV claim",
            "donor": "superseded PR #12762 / ASTRA-FRONTIERWIDE",
        }
        if now != decision:
            return selected_action, report
        if not isinstance(selected_action, Mapping):
            report["reason"] = "unsupported_action"
            return selected_action, report
        queue = selected_action.get("market", [])
        if not isinstance(queue, list) or len(queue) > limit:
            report["reason"] = "unsupported_market_queue"
            return selected_action, report
        if any(not (isinstance(order, list) and order and order[0] == "HIRE") for order in queue):
            report["reason"] = "nonhire_market_prefix"
            return selected_action, report
        day = int(observation.get("day", now // day_len))
        farm, private = _post_current_units(mechanics, observation, selected_action,
                                            board, day, day_len, cap)
        _simulate_existing_current_hires(mechanics, farm, private, queue, limit, board, mult)
        prices = observation.get("market", {}).get("prices", {})
        if not isinstance(prices, Mapping):
            report["reason"] = "prices"
            return selected_action, report
        baseline = _terminal_assignment_value(terminal, farm, private, terminal_start,
                                              final, day, prices, cap)
        if baseline is None:
            report["reason"] = "baseline_route_failure"
            return selected_action, report
        slots = min(max_extra_hires, max(0, limit - len(queue)))
        trial_farm, trial_private = copy.deepcopy(farm), copy.deepcopy(private)
        cumulative_cost = 0
        for extra in range(1, slots + 1):
            wage = int(mechanics._hire_cost(trial_farm["hires_today"], mult))
            cash = trial_farm.get("money")
            if isinstance(cash, bool) or not isinstance(cash, (int, float)) or cash < wage:
                break
            before = float(cash)
            mechanics._do_hire(trial_farm, trial_private, board, mult)
            paid = before - float(trial_farm.get("money", before))
            if paid != wage:
                report["reason"] = "hire_cost_drift"
                report["frontier"] = []
                return selected_action, report
            cumulative_cost += wage
            gross = _terminal_assignment_value(terminal, trial_farm, trial_private,
                                               terminal_start, final, day, prices, cap)
            if gross is None:
                report["reason"] = "candidate_route_failure"
                report["frontier"] = []
                return selected_action, report
            gain = gross - baseline
            report["frontier"].append({
                "extra_hires": extra,
                "cumulative_hire_cost": cumulative_cost,
                "gross_current_quote_gain": gain,
                "net_current_quote_gain": gain - cumulative_cost,
                "hands_after": len(trial_farm.get("hands", [])),
            })
        qualified = [row for row in report["frontier"]
                     if row["net_current_quote_gain"] >= min_quote_surplus]
        if not qualified:
            report["reason"] = "no_surplus"
            return selected_action, report
        best = max(qualified, key=lambda row: (row["net_current_quote_gain"], -row["extra_hires"]))
        out = copy.deepcopy(dict(selected_action))
        out.setdefault("market", []).extend([["HIRE"] for _ in range(best["extra_hires"])])
        report.update(
            changed=True,
            reason="preterminal_frontier_selected",
            baseline_current_quote_value=baseline,
            market_slots=slots,
            chosen=best,
            activation="source_ready_default_off_until_paired_engine_ev",
        )
        return out, report
    except (KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
        return selected_action, {
            "changed": False,
            "reason": f"fail_closed:{type(exc).__name__}:{exc}",
            "frontier": [],
            "scope": "preterminal frontier fail-closed",
        }
