# SPDX-License-Identifier: Apache-2.0
"""Monotone multi-product composition for the TITAN SELL scheduler.

The incumbent scheduler evaluates every product but commits only one selected
product plan per call.  This overlay preserves that incumbent action byte-for-
byte, then appends additional *current-turn* SELL coordinates only when each
coordinate has a strictly positive all-scenario certificate, dominates its own
reference sale prefix at every checkpoint, fits the raw market-order cap, and
cannot exceed the planner's post-unit stock quantity.

The prefix-dominance rule is deliberately conservative: composing an extra plan
can only release shed capacity at least as early as its incumbent reference.
The overlay does not edit future-plan state; the incumbent replans next turn.
"""
from __future__ import annotations

import copy
import math
from typing import Any, Mapping, Sequence


def _plain_int(value: Any) -> int | None:
    """Return an exact integer or ``None``; bools are not quantities."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _normal_plan(raw: Any) -> dict[int, int] | None:
    """Normalize an internal ``[(step, quantity), ...]`` plan fail-closed."""
    if not isinstance(raw, (list, tuple)):
        return None
    out: dict[int, int] = {}
    for row in raw:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            return None
        step = _plain_int(row[0])
        quantity = _plain_int(row[1])
        if step is None or quantity is None or step < 0 or quantity < 0:
            return None
        out[step] = out.get(step, 0) + quantity
    return out


def sale_prefix_dominates(plan: Any, reference: Any) -> bool:
    """Whether ``plan`` has sold at least reference units at every checkpoint."""
    candidate = _normal_plan(plan)
    incumbent = _normal_plan(reference)
    if candidate is None or incumbent is None:
        return False
    checkpoints = sorted(set(candidate) | set(incumbent))
    candidate_total = incumbent_total = 0
    for step in checkpoints:
        candidate_total += candidate.get(step, 0)
        incumbent_total += incumbent.get(step, 0)
        if candidate_total < incumbent_total:
            return False
    return True


def _positive_gain(info: Mapping[str, Any]) -> float | None:
    raw = info.get("worst_relative_gain")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    gain = float(raw)
    if not math.isfinite(gain) or gain <= 0.0:
        return None
    return gain


def _sold_now(market: Sequence[Any], item: str) -> int | None:
    """Count valid positive SELL quantities for one item, fail-closed on its rows."""
    total = 0
    for row in market:
        if not isinstance(row, (list, tuple)) or not row:
            continue
        if row[0] != "SELL" or len(row) < 2 or row[1] != item:
            continue
        if len(row) < 3:
            return None
        quantity = _plain_int(row[2])
        if quantity is None or quantity <= 0:
            return None
        total += quantity
    return total


def augment_action(
    action: Any,
    diagnostics: Any,
    *,
    step: int,
    max_market_orders: int,
) -> tuple[Any, list[dict[str, Any]]]:
    """Append independently certified SELL coordinates without changing incumbents.

    Returned ``additions`` is an auditable certificate list.  Any malformed
    boundary causes identity behavior rather than a best-effort mutation.
    """
    if (
        isinstance(step, bool)
        or not isinstance(step, int)
        or step < 0
        or isinstance(max_market_orders, bool)
        or not isinstance(max_market_orders, int)
    ):
        return copy.deepcopy(action), []
    cap = max(1, max_market_orders)
    if not isinstance(action, Mapping) or not isinstance(action.get("market"), list):
        return copy.deepcopy(action), []
    if not isinstance(diagnostics, Mapping):
        return copy.deepcopy(action), []
    evaluations = diagnostics.get("evaluations")
    if not isinstance(evaluations, list):
        return copy.deepcopy(action), []

    out = copy.deepcopy(action)
    market = out["market"]
    if len(market) >= cap:
        return out, []

    chosen = diagnostics.get("chosen")
    chosen_item = chosen.get("item") if isinstance(chosen, Mapping) else None
    ranked: list[tuple[float, int, str, int, dict[int, int], Mapping[str, Any]]] = []
    for ordinal, info in enumerate(evaluations):
        if not isinstance(info, Mapping):
            continue
        item = info.get("item")
        if not isinstance(item, str) or not item or item == chosen_item:
            continue
        gain = _positive_gain(info)
        quantity = _plain_int(info.get("quantity"))
        plan = _normal_plan(info.get("plan"))
        reference = _normal_plan(info.get("reference"))
        if gain is None or quantity is None or quantity < 0 or plan is None or reference is None:
            continue
        if sum(plan.values()) > quantity:
            continue
        if not sale_prefix_dominates(info.get("plan"), info.get("reference")):
            continue
        ranked.append((-gain, ordinal, item, quantity, plan, info))

    ranked.sort(key=lambda row: (row[0], row[1], row[2]))
    additions: list[dict[str, Any]] = []
    seen_items: set[str] = set()
    for negative_gain, ordinal, item, quantity, plan, info in ranked:
        if item in seen_items or len(market) >= cap:
            continue
        sold = _sold_now(market, item)
        if sold is None:
            continue
        desired = plan.get(step, 0)
        extra = desired - sold
        # This overlay is deliberately action-active and monotone.  Future-only
        # plans remain with the incumbent rather than creating hidden state here.
        if extra <= 0 or sold + extra > quantity:
            continue
        market.append(["SELL", item, extra])
        seen_items.add(item)
        additions.append(
            {
                "item": item,
                "quantity": extra,
                "desired_now": desired,
                "worst_relative_gain": -negative_gain,
                "evaluation_ordinal": ordinal,
                "proof": "strict_gain+sale_prefix_dominance+raw_cap+post_unit_stock",
            }
        )
    return out, additions


class PortfolioAscent:
    """Composable wrapper around an incumbent object exposing ``act``/diagnostics."""

    def __init__(self, delegate: Any):
        if not hasattr(delegate, "act"):
            raise TypeError("delegate must expose act(obs, configuration)")
        self.delegate = delegate
        self.diagnostics: dict[str, Any] = {}

    def act(self, obs: Any, configuration: Any = None) -> Any:
        action = self.delegate.act(obs, configuration)
        try:
            step = obs.get("step") if isinstance(obs, Mapping) else None
            raw_cap = (
                configuration.get("maxMarketOrdersPerTurn", 10)
                if isinstance(configuration, Mapping)
                else 10
            )
            cap = _plain_int(raw_cap)
            if cap is None:
                raise ValueError("malformed maxMarketOrdersPerTurn")
            diagnostics = getattr(self.delegate, "diagnostics", {})
            augmented, additions = augment_action(
                action,
                diagnostics,
                step=step,
                max_market_orders=cap,
            )
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
            augmented, additions = copy.deepcopy(action), []

        base_diagnostics = getattr(self.delegate, "diagnostics", {})
        self.diagnostics = (
            copy.deepcopy(base_diagnostics) if isinstance(base_diagnostics, Mapping) else {}
        )
        self.diagnostics["portfolio_additions"] = copy.deepcopy(additions)
        return augmented


def install(delegate: Any) -> PortfolioAscent:
    """Wrap the currently selected SELL scheduler without importing a sibling copy."""
    return PortfolioAscent(delegate)
