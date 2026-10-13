# SPDX-License-Identifier: Apache-2.0
"""E11: bounded public-price-drop SELL deferral with exact future tick aggregation.

Lineage: TESSERA (Gemini) design -> G01 (Grok Build #2, PR #11371) -> ARGUS
semantic-safety repair (candidates/v3-g01-argus-safe, findings A2/A3/A9) -> V3.

V3 wiring: the deterministic package key `e11_rival_sell` in TITAN-CONFIG.json
travels to the seller as config['titan_v3'] and the caller passes `enabled`
explicitly.  There are no environment reads.  Identity when disabled.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping, Sequence

AbsorptionFn = Callable[[str, int, Sequence[str], Mapping[str, Any]], int | float]
DEFAULT_MAX_MARKET_ORDERS = 10
DEFAULT_FARM_HAND_COST_MULT = 1


def _last_action_step(config: Mapping[str, Any]) -> int:
    try:
        return max(0, int(config.get("episodeSteps", 720)) - 2)
    except (TypeError, ValueError):
        return 718


def _max_market_orders(config: Mapping[str, Any]) -> int:
    try:
        return max(1, int(config.get("maxMarketOrdersPerTurn", DEFAULT_MAX_MARKET_ORDERS)))
    except (TypeError, ValueError):
        return DEFAULT_MAX_MARKET_ORDERS


def _fib(n: int) -> int:
    """Mirror the official hire-cost sequence: 1, 1, 2, 3, 5, ..."""
    a, b = 1, 1
    for _ in range(max(0, n)):
        a, b = b, a + b
    return a


def _hire_only_suffix_is_cash_independent(
    obs: Mapping[str, Any],
    executable_market: Sequence[Any],
    sell_index: int,
    config: Mapping[str, Any],
) -> bool:
    """Prove a narrow safe case for later HIRE rows.

    Any later executable row other than HIRE makes the proof fail closed.
    Earlier BUY/unknown rows also make the proof fail closed because they can
    consume cash before a later HIRE.  SELL proceeds are deliberately excluded
    from the cash lower bound, so the proof does not rely on the sale being
    considered for deferral.
    """
    later_nonempty = False
    for later in executable_market[sell_index + 1:]:
        if not later:
            continue
        later_nonempty = True
        if not (isinstance(later, list) and later and later[0] == "HIRE"):
            return False
    if not later_nonempty:
        return True

    # When a later HIRE exists, every other executable non-empty row must be
    # either SELL or HIRE.  A BUY/unknown row before this SELL can consume cash
    # and invalidate a public-money lower bound.
    for order in executable_market:
        if not order:
            continue
        if not (isinstance(order, list) and order and order[0] in ("SELL", "HIRE")):
            return False

    farms = obs.get("farms") or []
    try:
        player = int(obs.get("player", 0))
    except (TypeError, ValueError):
        return False
    if player < 0 or player >= len(farms) or not isinstance(farms[player], Mapping):
        return False
    farm = farms[player]
    try:
        cash = float(farm.get("money", 0.0))
        hires_today = max(0, int(farm.get("hires_today") or 0))
        hire_mult = float(config.get("farmHandCostMult", DEFAULT_FARM_HAND_COST_MULT))
    except (TypeError, ValueError):
        return False
    if cash < 0 or hire_mult < 0:
        return False

    required = 0.0
    next_hire = hires_today
    for order in executable_market:
        if isinstance(order, list) and order and order[0] == "HIRE":
            required += hire_mult * _fib(next_hire)
            next_hire += 1
    return cash >= required


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
    *,
    enabled: bool = False,
):
    report: dict[str, Any] = {
        "enabled": bool(enabled),
        "reason": "NO_OP_FLAT_MARKET",
        "changed": False,
        "deferred": [],
        "protected_indices": [],
        "future_absorption": {},
    }
    if not enabled:
        report["reason"] = "OFF"
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

    max_orders = _max_market_orders(cfg)
    executable_market = raw_market[:max_orders]
    report["executable_prefix_length"] = len(executable_market)
    sell_items = {
        str(order[1])
        for order in executable_market
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
    protected_indices: list[int] = []
    for index, order in enumerate(executable_market):
        if (
            isinstance(order, list)
            and len(order) > 1
            and order[0] == "SELL"
            and str(order[1]) in eligible
        ):
            if not _hire_only_suffix_is_cash_independent(obs, executable_market, index, cfg):
                protected_indices.append(index)
                continue
            out_market[index] = []
            deferred.append(str(order[1]))
    report["protected_indices"] = protected_indices
    if not deferred:
        if protected_indices:
            report["reason"] = "NO_OP_DOWNSTREAM_MARKET_DEPENDENCY"
        return action, report

    out["market"] = out_market
    report.update(
        changed=True,
        deferred=deferred,
        reason="PUBLIC_PRICE_DROP_DEFER_" + ",".join(sorted(set(deferred))),
    )
    return out, report
