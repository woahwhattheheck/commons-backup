# SPDX-License-Identifier: Apache-2.0
"""P01: bounded opening cash-turnover ordering for already-selected seed buys.

The transform never creates, removes, or resizes an order.  It permutes only
positive BUY_SEED rows among their existing BUY_SEED slots inside the executable
market prefix.  HIRE rows and every non-seed row stay at their exact indices.

A candidate is admitted only when:
* the action is in the opening window;
* all fixed-price executable rows can be parsed without private/rival input;
* the queue is not already fully funded from observed cash (SELL receipts are
  deliberately ignored, making the test conservative);
* every HIRE and every promoted target seed remains funded in the reordered
  fixed-price prefix.

This is an experiment surface, not a default-policy or playing-strength claim.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

MODES = frozenset({"wheat", "carrot", "annual"})
ANNUALS = frozenset({"WHEAT", "CARROT"})


def _whole(value: Any, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError("expected bounded whole number")
    return value


def _quantity(order: Any) -> int:
    if not isinstance(order, list) or len(order) < 3:
        raise ValueError("quantity order must contain operation, item, quantity")
    value = _whole(order[2])
    if value > 99_998:
        raise ValueError("quantity reaches engine unit-loop boundary")
    return value


def _step(observation: Mapping[str, Any], configuration: Mapping[str, Any]) -> int:
    if observation.get("step") is not None:
        return _whole(observation["step"])
    tpd = _whole(configuration.get("turnsPerDay", 24), minimum=1)
    return _whole(observation["day"]) * tpd + _whole(observation["hour"])


def _target_rank(mode: str, crop: str, original_index: int) -> tuple[int, int, int]:
    if mode == "wheat":
        group = 0 if crop == "WHEAT" else 1
        crop_rank = 0
    elif mode == "carrot":
        group = 0 if crop == "CARROT" else 1
        crop_rank = 0
    else:
        group = 0 if crop in ANNUALS else 1
        crop_rank = 0 if crop == "WHEAT" else 1 if crop == "CARROT" else 2
    return group, crop_rank, original_index


def _fixed_prefix_costs(mechanics: Any, observation: Mapping[str, Any],
                        configuration: Mapping[str, Any], orders: list[Any]) -> list[int]:
    """Return cumulative fixed own spend; reject any unresolved executable row."""
    player = _whole(observation["player"])
    farm = observation["farms"][player]
    hires = _whole(farm.get("hires_today", 0))
    unlocked = farm.get("unlocked_quadrants")
    if not isinstance(unlocked, list) or not unlocked:
        raise ValueError("missing unlocked quadrants")
    land_index = len(unlocked) - 1
    mult = _whole(configuration.get("farmHandCostMult", 1))
    cumulative: list[int] = []
    total = 0
    for order in orders:
        cost = 0
        if order == []:
            cumulative.append(total)
            continue
        if not isinstance(order, list) or not order or not isinstance(order[0], str):
            raise ValueError("unsupported market row")
        op = order[0]
        if op in ("PASS", "SELL"):
            pass
        elif op == "HIRE":
            cost = _whole(mechanics._hire_cost(hires, mult))
            hires += 1
        elif op == "BUY_LAND":
            if land_index < len(mechanics.LAND_PRICES):
                cost = _whole(mechanics.LAND_PRICES[land_index])
                land_index += 1
        elif op == "BUY_SEED":
            quantity = _quantity(order)
            crop = order[1]
            cost = quantity * _whole(mechanics.CROPS[crop]["seed"])
        elif op == "BUY_ANIMAL":
            quantity = _quantity(order)
            animal = order[1]
            cost = quantity * _whole(mechanics.ANIMALS[animal]["cost"])
        elif op == "BUY_PRODUCT":
            # Public prices are variable and rival-interleaved.  This bounded
            # P01 certificate does not guess their spend.
            raise ValueError("variable-price purchase in executable prefix")
        else:
            raise ValueError("unknown market operation")
        total += cost
        cumulative.append(total)
    return cumulative


def prioritize_opening_seeds(mechanics: Any, observation: Mapping[str, Any],
                             configuration: Mapping[str, Any], selected: Any,
                             *, mode: str = "annual", max_day: int = 10
                             ) -> tuple[Any, dict[str, Any]]:
    """Prioritize an annual seed frontier while preserving hires and row shapes.

    Positive seed rows are sorted into the seed slots already present.  The
    returned report is intentionally detailed enough to bind first-divergence
    evidence to observed cash and the exact fixed-prefix certificate.
    """
    report: dict[str, Any] = {
        "schema": 1,
        "mode": mode,
        "changed": False,
        "reason": "invalid_input",
        "controller_calls": 0,
        "rival_private_used": False,
    }
    try:
        if mode not in MODES:
            raise ValueError("unknown P01 mode")
        if not isinstance(selected, dict):
            raise ValueError("selected action must be a mapping")
        market = selected.get("market")
        if not isinstance(market, list) or not market:
            report["reason"] = "empty_market"
            return selected, report
        cfg = dict(configuration or {})
        tpd = _whole(cfg.get("turnsPerDay", 24), minimum=1)
        now = _step(observation, cfg)
        day = now // tpd
        report.update(step=now, day=day)
        if day > _whole(max_day):
            report["reason"] = "outside_opening_window"
            return selected, report
        maximum = max(1, _whole(cfg.get("maxMarketOrdersPerTurn", 10)))
        prefix_len = min(maximum, len(market))
        prefix = deepcopy(market[:prefix_len])
        seed_positions: list[int] = []
        seed_rows: list[tuple[int, list[Any]]] = []
        for index, order in enumerate(prefix):
            if not (isinstance(order, list) and len(order) >= 3 and order[0] == "BUY_SEED"):
                continue
            quantity = _quantity(order)
            crop = order[1]
            if crop not in mechanics.CROPS:
                raise ValueError("unknown seed crop")
            if quantity <= 0:
                continue
            seed_positions.append(index)
            seed_rows.append((index, order))
        targets = {"wheat": {"WHEAT"}, "carrot": {"CARROT"},
                   "annual": set(ANNUALS)}[mode]
        if len(seed_rows) < 2 or not any(row[1] in targets for _, row in seed_rows):
            report["reason"] = "no_mixed_target_seed_frontier"
            return selected, report
        ordered_rows = [row for _, row in sorted(
            seed_rows, key=lambda item: _target_rank(mode, item[1][1], item[0]))]
        before_rows = [row for _, row in seed_rows]
        if ordered_rows == before_rows:
            report["reason"] = "already_prioritized"
            return selected, report
        candidate = deepcopy(prefix)
        for position, row in zip(seed_positions, ordered_rows):
            candidate[position] = deepcopy(row)

        original_costs = _fixed_prefix_costs(mechanics, observation, cfg, prefix)
        candidate_costs = _fixed_prefix_costs(mechanics, observation, cfg, candidate)
        player = _whole(observation["player"])
        money_raw = observation["farms"][player]["money"]
        if isinstance(money_raw, float) and money_raw.is_integer():
            money_raw = int(money_raw)
        money = _whole(money_raw)
        report.update(observed_cash=money,
                      original_fixed_cost=original_costs[-1],
                      candidate_fixed_cost=candidate_costs[-1])
        if candidate_costs[-1] <= money:
            report["reason"] = "queue_already_fully_funded_without_sales"
            return selected, report

        required_positions = [i for i, order in enumerate(candidate)
                              if isinstance(order, list) and order and order[0] == "HIRE"]
        required_positions.extend(
            i for i, order in enumerate(candidate)
            if isinstance(order, list) and len(order) >= 3
            and order[0] == "BUY_SEED" and order[1] in targets and _quantity(order) > 0
        )
        if not required_positions:
            report["reason"] = "no_required_prefix"
            return selected, report
        certificate_end = max(required_positions)
        certificate_cost = candidate_costs[certificate_end]
        report.update(certificate_end=certificate_end,
                      certificate_cost=certificate_cost,
                      fixed_cash_slack=money - certificate_cost)
        if certificate_cost > money:
            report["reason"] = "target_or_hire_prefix_not_funded"
            return selected, report

        result = deepcopy(selected)
        result["market"] = candidate + deepcopy(market[prefix_len:])
        moved = [i for i, (before, after) in enumerate(zip(market, result["market"]))
                 if before != after]
        report.update(
            changed=True,
            reason="funded_target_seed_priority",
            moved_slots=moved,
            before_seed_rows=before_rows,
            after_seed_rows=ordered_rows,
            market_multiset_preserved=True,
            hires_fixed_in_place=True,
            executable_tail_preserved=True,
        )
        return result, report
    except (AttributeError, IndexError, KeyError, TypeError, ValueError, OverflowError) as error:
        report["reason"] = str(error)
        return selected, report
