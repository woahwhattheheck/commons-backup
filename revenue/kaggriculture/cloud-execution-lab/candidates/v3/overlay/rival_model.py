# SPDX-License-Identifier: Apache-2.0
"""O01: public-state rival classification with queue-safe, owner-bounded edits.

Lineage: TESSERA (Gemini) rival model -> G01 (Grok Build #2, PR #11371) -> ARGUS
semantic-safety repair (candidates/v3-g01-argus-safe, findings A1/A4/A8) -> V3.

This module is intentionally conservative.  It may append one BUY_LAND order
when an early-expander signal is observed, but it never reorders or displaces an
inherited market order.  SELL ownership stays with e11_rival_sell.py.

V3 wiring: package key `rival_model`; the runtime passes `enabled` explicitly.
No environment reads.  Identity when disabled.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

DEFAULT_MAX_MARKET_ORDERS = 10
DEFAULT_LAND_PRICES = (1000, 2000, 4000)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _episode_last_action(config: Mapping[str, Any]) -> int:
    try:
        return max(0, int(config.get("episodeSteps", 720)) - 2)
    except (TypeError, ValueError):
        return 718


def classify(
    obs: Mapping[str, Any],
    prev_prices: Mapping[str, Any] | None,
    config: Mapping[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Classify using public fields only; return archetype and current prices."""
    cfg = dict(config or {})
    step = int(obs.get("step", 0))
    player = int(obs.get("player", 0))
    farms = obs.get("farms") or []
    rival = _as_mapping(farms[1 - player]) if len(farms) >= 2 else {}
    unlocked = list(rival.get("unlocked_quadrants") or [])
    prices = dict(_as_mapping(obs.get("market")).get("prices") or {})

    early_step = int(cfg.get("g01_early_expander_step", 144))
    if step <= early_step and len(unlocked) > 1:
        return "EARLY_EXPANDER", prices

    threshold = float(cfg.get("rival_dump_price_drop", 15.0))
    if prev_prices:
        for item, price in prices.items():
            try:
                previous = float(prev_prices.get(item, price))
                if previous - float(price) >= threshold:
                    return "AGGRESSIVE_MARKET_DUMPER", prices
            except (TypeError, ValueError):
                continue
    return "NO_ARCHETYPE", prices


def apply_rival_model(
    obs: Mapping[str, Any],
    action: Mapping[str, Any],
    prev_prices: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | None = None,
    *,
    enabled: bool = False,
):
    """Apply only queue-safe O01 edits.

    The engine truncates market queues to maxMarketOrdersPerTurn and executes
    atomic orders at their literal queue index.  Therefore BUY_LAND is appended
    only when a free slot exists.  It is never prepended.
    """
    report: dict[str, Any] = {
        "enabled": bool(enabled),
        "archetype": "NO_ARCHETYPE",
        "reason": "NO_ARCHETYPE",
        "changed": False,
    }
    if not enabled:
        report["reason"] = "OFF"
        return action, report

    cfg = dict(config or {})
    step = int(obs.get("step", 0))
    if step >= _episode_last_action(cfg):
        report["reason"] = "NO_EDIT_TERMINAL_STEP"
        return action, report

    archetype, _prices = classify(obs, prev_prices, cfg)
    report["archetype"] = archetype

    # E11 owns SELL deferral.  O01 may observe a dump but must not bypass E11's
    # capacity/absorption checks or edit the same queue twice.
    if archetype == "AGGRESSIVE_MARKET_DUMPER":
        report["reason"] = "DUMPER_OBSERVED_E11_OWNS_SELLS"
        return action, report

    if archetype != "EARLY_EXPANDER":
        return action, report

    farms = obs.get("farms") or []
    player = int(obs.get("player", 0))
    if player < 0 or player >= len(farms):
        report["reason"] = "EARLY_EXPANDER_BAD_PLAYER"
        return action, report
    farm = _as_mapping(farms[player])
    unlocked = list(farm.get("unlocked_quadrants") or [])
    if "NE" in unlocked or len(unlocked) != 1 or unlocked[0] != "NW":
        report["reason"] = "EARLY_EXPANDER_NO_EDIT"
        return action, report

    land_prices = cfg.get("g01_land_prices", DEFAULT_LAND_PRICES)
    try:
        next_land_cost = int(list(land_prices)[0])
    except (TypeError, ValueError, IndexError):
        next_land_cost = DEFAULT_LAND_PRICES[0]
    cash_floor = max(0.0, float(cfg.get("g01_land_cash_floor", 0.0)))
    money = float(farm.get("money", 0.0))
    if money < next_land_cost + cash_floor:
        report.update(
            reason="EARLY_EXPANDER_CASH_FLOOR",
            required_cash=next_land_cost + cash_floor,
            observed_cash=money,
        )
        return action, report

    raw_market = action.get("market", []) if isinstance(action, Mapping) else []
    if not isinstance(raw_market, list):
        report["reason"] = "EARLY_EXPANDER_BAD_MARKET_QUEUE"
        return action, report
    market = list(raw_market)
    if any(isinstance(order, list) and order and order[0] == "BUY_LAND" for order in market):
        report["reason"] = "EARLY_EXPANDER_ALREADY_QUEUED"
        return action, report

    try:
        max_orders = max(1, int(cfg.get("maxMarketOrdersPerTurn", DEFAULT_MAX_MARKET_ORDERS)))
    except (TypeError, ValueError):
        max_orders = DEFAULT_MAX_MARKET_ORDERS
    if len(market) >= max_orders:
        report.update(
            reason="EARLY_EXPANDER_NO_FREE_MARKET_SLOT",
            queue_length=len(market),
            max_market_orders=max_orders,
        )
        return action, report

    out = deepcopy(action)
    out_market = list(out.get("market") or [])
    insertion_index = len(out_market)
    out_market.append(["BUY_LAND"])
    out["market"] = out_market
    report.update(
        reason="EARLY_EXPANDER_APPEND_BUY_LAND",
        changed=True,
        insertion_index=insertion_index,
        queue_length_before=len(market),
        queue_length_after=len(out_market),
        max_market_orders=max_orders,
    )
    return out, report
