# SPDX-License-Identifier: Apache-2.0
"""Route-aware reassignment of a no-op animal harvest to a useful feed.

This is an optional selected-action transform.  It changes one current unit slot
only when an exact current-day projection establishes a specific resource swap:
feeding now makes a later feed of the same animal redundant, causes one later
feed of a different non-producing animal to be skipped, and leaves one extra
WHEAT after end-of-day without any current-day output loss or animal escape.
The public current quotes and own route sale order must prefer that WHEAT before
the deferred animal product.  Unknown market purchases or route checkpoints
preserve the supplied action.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any, Iterable, Mapping


def _units(action: Mapping[str, Any]) -> list[list[Any]]:
    return [deepcopy(action.get("farmer", ["PASS"])), *deepcopy(action.get("hands", []))]


def _put_units(action: Mapping[str, Any], units: list[list[Any]]) -> dict[str, Any]:
    out = deepcopy(dict(action))
    out["farmer"], out["hands"] = units[0], units[1:]
    return out


def _apply_units(mechanics: Any, farm: dict[str, Any], private: dict[str, Any],
                 action: Mapping[str, Any], *, board: int, day: int,
                 turns_per_day: int, capacity: int) -> None:
    units = _units(action)
    demand: Counter[str] = Counter()
    for unit in units:
        if isinstance(unit, list) and len(unit) >= 2 and unit[0] == "PLANT":
            demand[str(unit[1])] += 1
    blocked = {crop for crop, count in demand.items()
               if count > int(private.get("seeds", {}).get(crop, 0))}
    for index, raw in enumerate(units):
        unit = raw if isinstance(raw, list) and raw else ["PASS"]
        if unit[0] == "PLANT" and len(unit) >= 2 and unit[1] in blocked:
            unit = ["PASS"]
        mechanics._apply_unit_action(
            farm, private, index, unit, board, day, turns_per_day, capacity)


def _fixed_market(mechanics: Any, farm: dict[str, Any], private: dict[str, Any],
                  action: Mapping[str, Any], *, board: int, capacity: int,
                  max_orders: int) -> tuple[bool, str | None]:
    """Apply only own fixed-physical market effects with a zero-sale cash floor.

    BUY_PRODUCT depends on paired flow and is rejected.  Other fixed-price orders
    must already be affordable without sale revenue; this makes the unit-route
    projection independent of the rival's sale ordering and exact quotes.
    """
    for order in action.get("market", [])[:max_orders]:
        if not isinstance(order, list) or not order:
            continue
        op = order[0]
        if op == "SELL":
            if len(order) < 3:
                return False, "malformed_sell"
            item, quantity = order[1], max(0, int(order[2]))
            take = min(quantity, max(0, int(private["shed"].get(item, 0))))
            private["shed"][item] = int(private["shed"].get(item, 0)) - take
        elif op == "HIRE":
            cost = mechanics._hire_cost(int(farm.get("hires_today", 0)), 1)
            if float(farm.get("money", 0)) < cost:
                return False, "future_hire_needs_sale_cash"
            mechanics._do_hire(farm, private, board, 1)
        elif op == "BUY_LAND":
            unlocked = len(farm.get("unlocked_quadrants", [])) - 1
            cost = (mechanics.LAND_PRICES[unlocked]
                    if 0 <= unlocked < len(mechanics.LAND_PRICES) else 0)
            if float(farm.get("money", 0)) < cost:
                return False, "future_land_needs_sale_cash"
            mechanics._do_buy_land(farm, board)
        elif op == "BUY_SEED":
            if len(order) < 3 or order[1] not in mechanics.CROPS:
                return False, "malformed_seed_buy"
            item, quantity = order[1], max(0, int(order[2]))
            cost = int(mechanics.CROPS[item]["seed"]) * quantity
            if float(farm.get("money", 0)) < cost:
                return False, "future_seed_needs_sale_cash"
            farm["money"] -= cost
            private["seeds"][item] = int(private["seeds"].get(item, 0)) + quantity
        elif op == "BUY_ANIMAL":
            if len(order) < 3 or order[1] not in mechanics.ANIMALS:
                return False, "malformed_animal_buy"
            item, quantity = order[1], max(0, int(order[2]))
            cost = int(mechanics.ANIMALS[item]["cost"]) * quantity
            if float(farm.get("money", 0)) < cost:
                return False, "future_animal_needs_sale_cash"
            room = max(0, capacity - sum(int(v) for v in private["shed"].values()))
            take = min(quantity, room)
            farm["money"] -= int(mechanics.ANIMALS[item]["cost"]) * take
            private["shed"][item] = int(private["shed"].get(item, 0)) + take
        elif op == "BUY_PRODUCT":
            return False, "future_product_purchase_unknown"
        elif op in ("PASS",):
            continue
        else:
            return False, "unsupported_future_market_order"
    return True, None


def _project_to_eod(mechanics: Any, obs: Mapping[str, Any], config: Mapping[str, Any],
                    current_action: Mapping[str, Any], route: list[Mapping[str, Any]],
                    checkpoints: Iterable[int]) -> tuple[dict[str, Any] | None, str | None]:
    cfg = dict(config or {})
    seat = int(obs["player"])
    now = int(obs["step"])
    tpd = int(cfg.get("turnsPerDay", 24))
    board = int(cfg.get("boardSize", len(obs["farms"][seat]["tiles"])))
    capacity = int(cfg.get("shedCapacity", 100))
    maximum = int(cfg.get("maxMarketOrdersPerTurn", 10))
    day = now // tpd
    end = (day + 1) * tpd - 1
    if end >= len(route):
        return None, "route_ends_before_eod"
    if any(now < int(step) <= end for step in checkpoints):
        return None, "route_checkpoint_before_eod"
    farm = deepcopy(obs["farms"][seat])
    private = deepcopy(obs["private"])
    for step in range(now, end + 1):
        action = current_action if step == now else route[step]
        _apply_units(mechanics, farm, private, action, board=board, day=day,
                     turns_per_day=tpd, capacity=capacity)
        ok, reason = _fixed_market(mechanics, farm, private, action, board=board,
                                   capacity=capacity, max_orders=maximum)
        if not ok:
            return None, reason
        mechanics._decay_plants(farm, step)
    mechanics._daily_refresh_plants(farm, day, tpd)
    mechanics._daily_refresh_animals(farm, day)
    mechanics._drop_inventories_to_shed(private, capacity)
    farm["farmer"] = list(mechanics._default_spawn(board))
    farm["hands"] = []
    farm["hires_today"] = 0
    private["inventories"] = [{}]
    return {"farm": farm, "private": private, "end_step": end}, None


def _noop(mechanics: Any, farm: dict[str, Any], private: dict[str, Any], index: int,
          action: list[Any], *, board: int, day: int, tpd: int, capacity: int) -> bool:
    later_farm, later_private = deepcopy(farm), deepcopy(private)
    mechanics._apply_unit_action(later_farm, later_private, index, action,
                                 board, day, tpd, capacity)
    return (later_farm, later_private) == (farm, private)


def _candidate_actions(mechanics: Any, obs: Mapping[str, Any], config: Mapping[str, Any],
                       selected: Mapping[str, Any]) -> list[tuple[int, dict[str, Any], dict[str, Any]]]:
    cfg = dict(config or {})
    seat = int(obs["player"])
    now = int(obs["step"])
    tpd = int(cfg.get("turnsPerDay", 24))
    board = int(cfg.get("boardSize", len(obs["farms"][seat]["tiles"])))
    capacity = int(cfg.get("shedCapacity", 100))
    day = now // tpd
    farm = deepcopy(obs["farms"][seat])
    private = deepcopy(obs["private"])
    units = _units(selected)
    candidates: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
    for index, raw in enumerate(deepcopy(units)):
        action = raw if isinstance(raw, list) and raw else ["PASS"]
        position = mechanics._farmer_position(farm, index)
        tile = (farm["tiles"][position[1]][position[0]] if position is not None else None)
        inventory = mechanics._farmer_inventory(private, index)
        eligible = (
            action[0] == "HARVEST"
            and _noop(mechanics, farm, private, index, action, board=board,
                      day=day, tpd=tpd, capacity=capacity)
            and isinstance(tile, dict) and "animal" in tile
            and not bool(tile.get("fed_today"))
            and int(inventory.get("WHEAT", 0)) > 0
        )
        if eligible:
            alternative = ["FEED"]
            if not _noop(mechanics, farm, private, index, alternative, board=board,
                         day=day, tpd=tpd, capacity=capacity):
                changed = deepcopy(units)
                changed[index] = alternative
                candidate = _put_units(selected, changed)
                candidates.append((index, candidate, {
                    "worker": index,
                    "position": list(position),
                    "animal": tile.get("animal"),
                    "before": deepcopy(action),
                    "after": alternative,
                    "worker_wheat": int(inventory.get("WHEAT", 0)),
                }))
        mechanics._apply_unit_action(farm, private, index, action,
                                     board, day, tpd, capacity)
    return candidates


def _sale_step(route: list[Mapping[str, Any]], start: int, item: str,
               checkpoints: Iterable[int], horizon: int) -> int | None:
    stop = min(len(route) - 1, start + max(1, horizon))
    checkpoint_set = {int(x) for x in checkpoints}
    for step in range(start, stop + 1):
        if step in checkpoint_set:
            return None
        for order in route[step].get("market", []):
            if (isinstance(order, list) and len(order) >= 3 and order[0] == "SELL"
                    and order[1] == item and int(order[2]) > 0):
                return step
    return None


def _exchange(base: Mapping[str, Any], candidate: Mapping[str, Any],
              mechanics: Any) -> dict[str, Any] | None:
    base_farm, alt_farm = deepcopy(base["farm"]), deepcopy(candidate["farm"])
    base_private, alt_private = deepcopy(base["private"]), deepcopy(candidate["private"])
    base_wheat = int(base_private["shed"].get("WHEAT", 0))
    alt_wheat = int(alt_private["shed"].get("WHEAT", 0))
    if alt_wheat - base_wheat != 1:
        return None
    alt_private["shed"]["WHEAT"] = base_wheat
    if alt_private != base_private:
        return None
    differences = []
    for y, row in enumerate(base_farm["tiles"]):
        for x, tile in enumerate(row):
            other = alt_farm["tiles"][y][x]
            if tile != other:
                differences.append((x, y, tile, other))
    if len(differences) != 1:
        return None
    x, y, before, after = differences[0]
    if not (isinstance(before, dict) and isinstance(after, dict)
            and before.get("animal") == after.get("animal")
            and before.get("animal") in mechanics.ANIMALS):
        return None
    left, right = deepcopy(before), deepcopy(after)
    baseline_unfed = int(left.pop("consecutive_unfed", 0))
    candidate_unfed = int(right.pop("consecutive_unfed", 0))
    baseline_bonus = int(left.pop("pending_care_bonus", 0))
    candidate_bonus = int(right.pop("pending_care_bonus", 0))
    if left != right:
        return None
    if candidate_unfed != baseline_unfed + 1 or candidate_unfed >= 2:
        return None
    if baseline_bonus != candidate_bonus + 1:
        return None
    product = mechanics.ANIMALS[before["animal"]]["product"]
    return {
        "saved_product": "WHEAT", "saved_units": 1,
        "deferred_animal": before["animal"], "deferred_product": product,
        "deferred_bonus_units": 1, "deferred_tile": [x, y],
        "baseline_consecutive_unfed": baseline_unfed,
        "candidate_consecutive_unfed": candidate_unfed,
        "baseline_pending_bonus": baseline_bonus,
        "candidate_pending_bonus": candidate_bonus,
    }


def propose_feed_reallocation(mechanics: Any, obs: Mapping[str, Any],
                              configuration: Mapping[str, Any] | None,
                              selected_action: Mapping[str, Any], *,
                              route: list[Mapping[str, Any]],
                              route_switch_steps: Iterable[int] = (),
                              sale_horizon: int = 96) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return one route-compatible feed reassignment or the original action."""
    selected = deepcopy(dict(selected_action))
    report: dict[str, Any] = {
        "status": "unchanged", "reason": "no_eligible_exchange",
        "controller_calls": 0, "candidate_count": 0,
        "current_day_projection_only": True,
    }
    try:
        now = int(obs["step"])
        prices = obs["market"]["prices"]
        candidates = _candidate_actions(mechanics, obs, dict(configuration or {}), selected)
        report["candidate_count"] = len(candidates)
        baseline, reason = _project_to_eod(
            mechanics, obs, dict(configuration or {}), selected, route, route_switch_steps)
        if baseline is None:
            report["reason"] = reason
            return selected, report
        accepted = []
        for index, action, details in candidates:
            projected, rejection = _project_to_eod(
                mechanics, obs, dict(configuration or {}), action, route, route_switch_steps)
            if projected is None:
                continue
            exchange = _exchange(baseline, projected, mechanics)
            if exchange is None:
                continue
            saved = exchange["saved_product"]
            deferred = exchange["deferred_product"]
            saved_sale = _sale_step(route, baseline["end_step"] + 1, saved,
                                    route_switch_steps, sale_horizon)
            deferred_sale = _sale_step(route, baseline["end_step"] + 1, deferred,
                                       route_switch_steps, sale_horizon)
            if saved_sale is None or deferred_sale is None or saved_sale >= deferred_sale:
                continue
            saved_price = int(prices[saved])
            deferred_price = int(prices[deferred])
            if saved_price < deferred_price:
                continue
            accepted.append((saved_price - deferred_price,
                             deferred_sale - saved_sale, -index,
                             action, details, exchange, saved_sale, deferred_sale))
        if not accepted:
            return selected, report
        _, _, _, action, details, exchange, saved_sale, deferred_sale = max(accepted)
        report.update(
            status="applied", reason="earlier_no_lower_quote_wheat_exchange",
            selected_change=details, projected_exchange=exchange,
            current_prices={"WHEAT": int(prices["WHEAT"]),
                            exchange["deferred_product"]: int(prices[exchange["deferred_product"]])},
            next_sale_steps={"WHEAT": saved_sale,
                             exchange["deferred_product"]: deferred_sale},
            projected_eod_step=baseline["end_step"],
        )
        return action, report
    except (AttributeError, IndexError, KeyError, TypeError, ValueError, OverflowError) as error:
        report["reason"] = str(error)
        return selected, report


class FeedReallocationAgent:
    """Optional wrapper around a supplied TITAN actor, preserving one parent call."""
    def __init__(self, actor: Any, mechanics: Any, decisions: Iterable[Iterable[Any]] = ()):
        self.actor = actor
        self.mechanics = mechanics
        self.decisions = tuple(int(row[0]) for row in decisions)
        self.diagnostics: dict[str, Any] = {}

    def act(self, observation: Mapping[str, Any], configuration: Mapping[str, Any] | None = None):
        selected = self.actor.production.act(observation)
        action, report = propose_feed_reallocation(
            self.mechanics, observation, configuration, selected,
            route=self.actor.controller.R[self.actor.controller.cur],
            route_switch_steps=self.decisions,
        )
        self.diagnostics = report
        return self.actor.transform_selected(observation, dict(configuration or {}), action)

    __call__ = act


def wrap_titan_agent(base_class: type) -> type:
    """Create an optional TITAN subclass without importing the canonical runtime here."""
    class FeedReallocationTitanAgent(base_class):
        def transform_selected(self, obs, cfg, selected):
            from scheduler import m, parent
            proposed, report = propose_feed_reallocation(
                m, obs, cfg, selected,
                route=self.controller.R[self.controller.cur],
                route_switch_steps=[row[0] for row in parent.DECISIONS],
            )
            self.diagnostics["feed_reallocation"] = report
            return super().transform_selected(obs, cfg, proposed)
    FeedReallocationTitanAgent.__name__ = "FeedReallocationTitanAgent"
    return FeedReallocationTitanAgent
