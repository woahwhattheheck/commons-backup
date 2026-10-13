# SPDX-License-Identifier: Apache-2.0
"""Dated conditional market valuation for HAZEL RouteQuote offers.

Supplied trade quantities are ASSUMED to execute. This is neither a stock/route
feasibility certificate nor a forecast of unknown shops, rival actions, or cash.
The market-price function and town catalogue come from the supplied mechanics.
No controller, random future, opponent private state, or probability is created.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import time
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class Scenario:
    name: str
    rival_orders: Mapping[int, Sequence[Sequence[Any]]] = field(default_factory=dict)
    # Each tuple adds shop instances BEFORE this turn. Duplicates are meaningful.
    shop_additions: Mapping[int, Sequence[str]] = field(default_factory=dict)
    description: str = "Explicit conditional flow, not a calibrated forecast"


class BudgetExceeded(RuntimeError):
    """An incomplete route/scenario vector is not eligible for selection."""


def _int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} cannot be a boolean")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


class _Budget:
    def __init__(self, max_units: int, seconds: float | None):
        self.remaining = _int(max_units, "max_units")
        if self.remaining < 0:
            raise ValueError("max_units must be nonnegative")
        self.deadline = None
        if seconds is not None:
            duration = _number(seconds, "seconds")
            if duration < 0:
                raise ValueError("seconds must be nonnegative")
            self.deadline = time.perf_counter() + duration
        self.used = 0

    def check(self, units: int = 0) -> None:
        if units > self.remaining or (self.deadline is not None and time.perf_counter() >= self.deadline):
            raise BudgetExceeded("conditional flow budget exhausted")
        self.remaining -= units
        self.used += units


def _trade(order: Sequence[Any], mechanics: Any, *, rival: bool = False):
    if not isinstance(order, (tuple, list)) or not order:
        raise ValueError("each order must be a nonempty sequence")
    op = order[0]
    if op == "PASS":
        return None
    if op in ("HIRE", "BUY_LAND", "BUY_SEED", "BUY_ANIMAL"):
        if rival:
            raise ValueError("rival fixed-cost orders need explicit PASS slots; costs are outside this model")
        return None
    if op not in ("SELL", "BUY_PRODUCT") or len(order) != 3:
        raise ValueError(f"unsupported flow order: {op}")
    item, quantity = order[1], _int(order[2], "quantity")
    # The pinned interpreter aborts a slot before its 100,000th unit round.
    if not 0 <= quantity <= 99_999 or item not in mechanics.PRODUCTS:
        raise ValueError("invalid product or quantity")
    if op == "BUY_PRODUCT" and item not in ("WHEAT", "FERTILIZER"):
        raise ValueError("engine BUY_PRODUCT accepts WHEAT/FERTILIZER only")
    return op, item, quantity


def value_route(offer: Any, observation: Mapping[str, Any], configuration: Mapping[str, Any],
                mechanics: Any, scenario: Scenario, *, max_units: int = 100_000,
                seconds: float | None = None, retain_trace: bool = False,
                _budget: _Budget | None = None) -> dict[str, Any]:
    """Reprice a HAZEL RouteQuote's dated orders with shared market conservation.

    Preserve slot identity, simultaneous pre-commit quotes, $1 non-admission,
    post-buy prices, town consumption AFTER trades, duplicate shops, and final
    executable turn episodeSteps-2. Fixed costs are the offer's supplied deltas.
    No sale-stock, later producer repair, or purchase-funding fill is invented.
    """
    budget = _budget or _Budget(max_units, seconds)
    now = _int(observation["step"], "step")
    end = _int(configuration.get("episodeSteps", 720), "episodeSteps") - 2
    if now < 0 or now > end or end - now > 10_000:
        raise ValueError("invalid or unsupported horizon")
    slots = max(1, _int(configuration.get("maxMarketOrdersPerTurn", 10), "max orders"))
    shop_interval = max(1, _int(configuration.get("townShopSellInterval", 4), "shop interval"))
    center_interval = max(1, _int(configuration.get("townCenterSellInterval", 24), "center interval"))
    if not isinstance(scenario.name, str) or not scenario.name:
        raise ValueError("scenario needs a nonempty name")
    market = observation["market"]
    inventory = {p: _int(market["inventory"][p], "inventory") for p in mechanics.PRODUCTS}
    params = market.get("params") or mechanics._resolve_market_params(configuration.get("marketParams", {}))
    shops = list(observation["town"].get("unlocked_shops", []))
    if any(s not in mechanics.SHOPS for s in shops):
        raise ValueError("unknown current shop")
    own: dict[int, dict[int, tuple[Any, float, list[Any]]]] = {}
    for row in offer.orders:
        step, slot = _int(row["step"], "order step"), _int(row["slot"], "order slot")
        if not now <= step <= end or not 0 <= slot < slots:
            raise ValueError("order outside executable horizon or slot range")
        if slot in own.setdefault(step, {}):
            raise ValueError("duplicate step/slot")
        order = list(row["order"])
        trade = _trade(order, mechanics)
        fixed = 0.0 if trade is not None else _number(row["delta"], "fixed delta")
        if fixed > 0 or (order[0] == "PASS" and fixed != 0):
            raise ValueError("fixed-cost orders cannot create receipts")
        own[step][slot] = (trade, fixed, order)
    rivals = {}
    for step, queue in scenario.rival_orders.items():
        step = _int(step, "rival step")
        if not now <= step <= end:
            raise ValueError("rival order outside horizon")
        if len(queue) > slots:
            raise ValueError("rival queue exceeds engine slot limit")
        rivals[step] = [_trade(o, mechanics, rival=True) for o in queue]
    additions = {}
    for step, new_shops in scenario.shop_additions.items():
        step = _int(step, "shop step")
        if not now < step <= end or isinstance(new_shops, str):
            raise ValueError("shop additions must name future first-active turns")
        if any(s not in mechanics.SHOPS for s in new_shops):
            raise ValueError("unknown scenario shop")
        additions[step] = tuple(new_shops)
    cash = minimum = _number(observation["farms"][observation["player"]]["money"], "money")
    initial = cash
    first_negative = None
    own_receipts = own_buys = rival_receipts = rival_buys = fixed_costs = 0.0
    trace = []
    cash_flow_rows = []
    # Cache only within this source-bound scenario, so overrides cannot leak.
    quotes: dict[tuple[str, int], int] = {}
    def price(item: str, inv: int) -> int:
        key = item, inv
        if key not in quotes:
            quotes[key] = mechanics.market_price(item, inv, params)
            # A delegated quote may return after the cooperative deadline.
            budget.check()
        return quotes[key]
    for step in range(now, end + 1):
        budget.check()
        shops.extend(additions.get(step, ()))
        own_queue, rival_queue = own.get(step, {}), rivals.get(step, ())
        count = max(max(own_queue, default=-1) + 1, len(rival_queue))
        for slot in range(count):
            our, fixed, original = own_queue.get(slot, (None, 0.0, ["PASS"]))
            rival = rival_queue[slot] if slot < len(rival_queue) else None
            before = cash
            before_rival = rival_receipts - rival_buys
            cash = _number(cash + fixed, "running cash")
            fixed_costs -= fixed
            minimum = min(minimum, cash)
            if cash < 0 and first_negative is None:
                first_negative = [step, slot]
            rounds = max(our[2] if our else 0, rival[2] if rival else 0)
            for unit in range(rounds):
                budget.check(1)
                pending = []
                # Quote BOTH actors before either changes inventory.
                for actor, trade in enumerate((our, rival)):
                    if trade is None or unit >= trade[2]:
                        continue
                    op, item, _ = trade
                    px = price(item, inventory[item] - (op == "BUY_PRODUCT"))
                    pending.append((actor, op, item, px))
                for actor, op, item, px in pending:
                    sell = op == "SELL"
                    if actor == 0:
                        cash = _number(cash + (px if sell else -px), "running cash")
                        own_receipts += px if sell else 0
                        own_buys += px if not sell else 0
                    else:
                        rival_receipts += px if sell else 0
                        rival_buys += px if not sell else 0
                    inventory[item] += int(sell and px > 1) - int(not sell)
                minimum = min(minimum, cash)
                if cash < 0 and first_negative is None:
                    first_negative = [step, slot]
            if our is not None:
                cash_flow_rows.append({"step": step, "slot": slot,
                                      "total_own_cash_delta": cash - before,
                                      "assumed_filled_quantity": our[2]})
            if retain_trace:
                trace.append({"step": step, "slot": slot, "order": original,
                              "own_delta": cash - before, "marked_cash": cash,
                              "rival_delta": rival_receipts - rival_buys - before_rival,
                              "assumed_own_quantity": our[2] if our else 0,
                              "assumed_rival_quantity": rival[2] if rival else 0})
        if step % shop_interval == 0:
            for shop in shops:
                products = mechanics.SHOPS[shop]
                for item in products:
                    inventory[item] -= 2 if len(products) == 1 else 1
        if step % center_interval == 0:
            for item in mechanics.TOWN_CENTER_PRODUCTS:
                inventory[item] -= 1
    result = {"route_id": offer.route_id, "scenario": scenario.name, "complete": True,
            "kind": "conditional_dated_flow_not_physical_feasibility",
            "assumptions": "supplied trade quantities execute; fixed costs are offer deltas; only declared demand/rival flows",
            "initial_cash": initial, "final_marked_cash": cash,
            "minimum_marked_cash": minimum, "first_negative": first_negative,
            "own_receipts": own_receipts, "own_product_spend": own_buys,
            "fixed_costs": fixed_costs, "rival_receipts": rival_receipts,
            "rival_product_spend": rival_buys, "final_market_inventory": inventory,
            "cash_flow_rows": cash_flow_rows, "trace": trace}
    # Include final town consumption and receipt construction in completion.
    budget.check()
    return result


def evaluate_scenarios(offers: Sequence[Any], observation: Mapping[str, Any],
                       configuration: Mapping[str, Any], mechanics: Any,
                       scenarios: Sequence[Scenario], *, max_units: int = 100_000,
                       seconds: float | None = 0.2, retain_trace: bool = False) -> dict[str, Any]:
    """Produce one complete source/scenario vector; do not select a route.

    No incomplete vector is consumable. The shared cooperative budget includes
    ALL route/scenario pairs. A mechanics callback cannot be preempted. Consumers
    should retain their original route when ``complete`` is False.
    """
    report: dict[str, Any] = {"complete": False, "reason": "missing_inputs", "rows": []}
    if not offers or not scenarios:
        return report
    try:
        names = [s.name for s in scenarios]
        ids = [o.route_id for o in offers]
        if len(set(names)) != len(names) or len(set(ids)) != len(ids):
            raise ValueError("scenario and route identities must be unique")
        budget = _Budget(max_units, seconds)
        rows = [[value_route(o, observation, configuration, mechanics, s,
                             _budget=budget, retain_trace=retain_trace) for o in offers]
                for s in scenarios]
        # No partially timely vector can reach the downstream selector.
        budget.check()
        report.update(complete=True, reason="complete_conditional_flow", rows=rows,
                      unit_rounds=budget.used)
    except BudgetExceeded:
        report.update(reason="incomplete_budget", rows=[])
    except (KeyError, ValueError, TypeError, OverflowError) as exc:
        report.update(reason="invalid_flow", detail=type(exc).__name__, rows=[])
    return report


def as_cash_scenarios(report: Mapping[str, Any], scenario_factory: Any) -> tuple[Any, ...]:
    """Adapt a complete report to DATE's existing CashScenario without ranking.

    ``scenario_factory`` is DATE's CashScenario class. All supplied SELL and
    BUY_PRODUCT rows, including explicit zero quantities, are represented by
    route-specific ``(step, slot): total_own_cash_delta`` keys. Rival effects and
    conditional-fill assumptions stay in ``report`` for the next consumer.
    """
    if report.get("complete") is not True or not report.get("rows"):
        raise ValueError("incomplete conditional trajectories are not consumable")
    answer = []
    for rows in report["rows"]:
        if not rows or any(row.get("complete") is not True for row in rows):
            raise ValueError("incomplete scenario rows")
        name = rows[0]["scenario"]
        if any(row["scenario"] != name for row in rows):
            raise ValueError("mixed scenario identities")
        flows = {row["route_id"]: {(r["step"], r["slot"]): r["total_own_cash_delta"]
                                     for r in row["cash_flow_rows"]} for row in rows}
        answer.append(scenario_factory(name=name, flows=flows))
    return tuple(answer)
