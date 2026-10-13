# SPDX-License-Identifier: Apache-2.0
"""Bounded public-price-drop SELL deferral with exact future tick aggregation."""
from __future__ import annotations

from copy import deepcopy
import os
from typing import Any, Callable, Mapping, Sequence

AbsorptionFn = Callable[[str, int, Sequence[str], Mapping[str, Any]], int | float]


def enabled() -> bool:
    return os.environ.get("TITAN_E11_RIVAL_SELL", "0") in ("1", "true", "True")


def _last_action_step(config: Mapping[str, Any]) -> int:
    try:
        return max(0, int(config.get("episodeSteps", 720)) - 2)
    except (TypeError, ValueError):
        return 718


def _future_absorption(
    item: str,
    start: int,
    end: int,
    shops: Sequence[str],
    config: Mapping[str, Any],
    absorption_fn: AbsorptionFn | None,
) -> tuple[int | None, str | None]:
    """Sum the engine's per-step absorption ticks over [start, end].

    A fractional answer is rejected: official market inventory is integer and a
    heuristic multiplier must not masquerade as an engine transition.
    """
    if absorption_fn is None:
        return None, "NO_ABSORPTION_FUNCTION"
    total = 0
    for future_step in range(start, end + 1):
        try:
            value = float(absorption_fn(item, future_step, shops, config))
        except Exception as exc:  # fail closed at the candidate boundary
            return None, f"ABSORPTION_ERROR_{type(exc).__name__}"
        if value < 0 or not value.is_integer():
            return None, "NONINTEGER_OR_NEGATIVE_ABSORPTION"
        total += int(value)
    return total, None


def apply_e11(
    obs: Mapping[str, Any],
    action: Mapping[str, Any],
    price_history,
    config: Mapping[str, Any] | None = None,
    absorption_fn: AbsorptionFn | None = None,
):
    report: dict[str, Any] = {
        "enabled": enabled(),
        "reason": "NO_OP_FLAT_MARKET",
        "changed": False,
        "deferred": [],
        "future_absorption": {},
    }
    if not enabled():
        return action, report

    cfg = dict(config or {})
    step = int(obs.get("step", 0))
    last = _last_action_step(cfg)
    if step >= last:
        report["reason"] = "NO_OP_TERMINAL_STEP"
        return action, report

    market_obj = obs.get("market") or {}
    prices = dict(market_obj.get("prices") or {}) if isinstance(market_obj, Mapping) else {}
    try:
        threshold = float(cfg.get("rival_dump_price_drop", 15.0))
    except (TypeError, ValueError):
        threshold = 15.0
    try:
        lookback = max(0, int(cfg.get("rival_dump_lookback_steps", 8)))
    except (TypeError, ValueError):
        lookback = 8

    history = list(price_history or [])
    window = []
    for entry in history:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            continue
        ts, snapshot = entry
        try:
            age = step - int(ts)
        except (TypeError, ValueError):
            continue
        if 0 <= age <= lookback and isinstance(snapshot, Mapping):
            window.append((int(ts), snapshot))

    dumped: set[str] = set()
    for item, current_price in prices.items():
        for _ts, snapshot in window:
            previous = snapshot.get(item)
            if previous is None:
                continue
            try:
                if float(previous) - float(current_price) >= threshold:
                    dumped.add(str(item))
                    break
            except (TypeError, ValueError):
                continue
    if not dumped:
        return action, report

    raw_market = action.get("market", []) if isinstance(action, Mapping) else []
    if not isinstance(raw_market, list):
        report["reason"] = "NO_OP_BAD_MARKET_QUEUE"
        return action, report
    sell_items = {
        str(order[1])
        for order in raw_market
        if isinstance(order, list) and len(order) > 1 and order[0] == "SELL"
    }
    candidates = sorted(dumped & sell_items)
    if not candidates:
        report["reason"] = "PRICE_DROP_NO_MATCHING_SELL"
        return action, report

    town = obs.get("town") or {}
    shops = list(town.get("unlocked_shops") or []) if isinstance(town, Mapping) else []
    minimum = max(0, int(cfg.get("e11_min_future_absorption", 2)))
    eligible: set[str] = set()
    for item in candidates:
        total, error = _future_absorption(item, step, last, shops, cfg, absorption_fn)
        if error is not None:
            report.update(reason=f"NO_OP_{error}")
            return action, report
        assert total is not None
        report["future_absorption"][item] = total
        if total >= minimum:
            eligible.add(item)

    if not eligible:
        report["reason"] = "NO_OP_INSUFFICIENT_FUTURE_ABSORPTION"
        return action, report

    out = deepcopy(action)
    out_market = list(out.get("market") or [])
    deferred: list[str] = []
    for index, order in enumerate(out_market):
        if (
            isinstance(order, list)
            and len(order) > 1
            and order[0] == "SELL"
            and str(order[1]) in eligible
        ):
            out_market[index] = []
            deferred.append(str(order[1]))
    if not deferred:
        return action, report

    out["market"] = out_market
    report.update(
        changed=True,
        deferred=deferred,
        reason="PUBLIC_PRICE_DROP_DEFER_" + ",".join(sorted(set(deferred))),
    )
    return out, report
