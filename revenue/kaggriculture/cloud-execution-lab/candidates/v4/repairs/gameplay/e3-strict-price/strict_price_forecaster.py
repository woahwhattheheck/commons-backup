# SPDX-License-Identifier: Apache-2.0
"""Strict fail-closed donor for E3 price-forecaster action rewriting.

This module intentionally does not change V3 wiring or defaults.  It wraps the
existing ``r04_price_forecaster`` pure forecast helpers while tightening the
action-rewrite boundary so a later current-stack consumer can reuse the E3
idea without inheriting the stale donor's row-index and coercion bugs.

Contract:
* inspect/mutate only the exact leading contiguous SELL block;
* preserve raw market cardinality, falsey barriers, and every tail index;
* replace a fully deferred SELL with ``[]`` rather than compacting the list;
* accept only strict non-bool runtime types for evidence used by the decision;
* on malformed/ambiguous evidence, return the original action object and
  restore forecaster state/telemetry if an internal helper failed.
"""

from __future__ import annotations

import copy
import math

import r04_price_forecaster as pf


PRODUCTS = pf.PRODUCTS
ACTIVE_START = pf.ACTIVE_START
ACTIVE_END = pf.ACTIVE_END
FORECAST_HORIZON = pf.FORECAST_HORIZON


def _is_int(value):
    return type(value) is int


def _is_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _strict_qty(value):
    if not _is_int(value) or value < 0:
        raise ValueError("quantity must be a non-negative int")
    return value


def _strict_market_row(row):
    """Validate one truthy authored market row without changing its shape."""
    if not isinstance(row, list) or not row or not isinstance(row[0], str):
        raise ValueError("malformed market row")
    if row[0] in ("SELL", "BUY_PRODUCT", "BUY_SEED", "BUY_ANIMAL"):
        if len(row) < 3:
            raise ValueError("quantity-bearing market row missing quantity")
        _strict_qty(row[2])
    return row


def _leading_sell_block(market):
    """Return strict leading SELL rows; a non-SELL/falsey row is a hard barrier."""
    block = []
    for index, row in enumerate(market):
        if not row:
            break
        if not isinstance(row, list):
            raise ValueError("malformed leading market row")
        op = row[0]
        if op != "SELL":
            break
        if len(row) < 3 or row[1] not in PRODUCTS:
            raise ValueError("malformed leading SELL row")
        qty = _strict_qty(row[2])
        block.append((index, row[1], qty))
    return block


def _validate_all_consumed_market_rows(market):
    """Fail closed on malformed rows that telemetry would otherwise coerce."""
    if not isinstance(market, list):
        raise ValueError("market must be a list")
    for row in market:
        if not row:
            # Raw falsey slots are legal barriers and must be preserved.
            continue
        _strict_market_row(row)


def _strict_observation(observation):
    if not isinstance(observation, dict):
        raise ValueError("observation must be a dict")
    step = observation.get("step")
    if not _is_int(step):
        raise ValueError("step must be an int")
    player = observation.get("player")
    if not _is_int(player) or player < 0:
        raise ValueError("player must be a non-negative int")

    market_state = observation.get("market")
    if not isinstance(market_state, dict):
        raise ValueError("market state must be a dict")
    inventory = market_state.get("inventory")
    prices = market_state.get("prices")
    if not isinstance(inventory, dict) or not isinstance(prices, dict):
        raise ValueError("market inventory/prices must be dicts")
    for item in PRODUCTS:
        if item not in inventory or not _is_int(inventory[item]) or inventory[item] < 0:
            raise ValueError("market inventory must contain non-negative strict integer product entries")
        if item not in prices or not _is_number(prices[item]) or prices[item] < 0:
            raise ValueError("market prices must contain finite non-negative product entries")

    town = observation.get("town")
    if not isinstance(town, dict):
        raise ValueError("town must be a dict")
    shops = town.get("unlocked_shops")
    if not isinstance(shops, list) or any(not isinstance(shop, str) for shop in shops):
        raise ValueError("unlocked_shops must be a list of strings")

    farms = observation.get("farms")
    if not isinstance(farms, list) or player >= len(farms) or not isinstance(farms[player], dict):
        raise ValueError("farms/player mismatch")
    cash = farms[player].get("money")
    if not _is_number(cash):
        raise ValueError("cash must be a finite non-bool number")

    return step, player, inventory, prices, shops, float(cash)


def _strict_flow_state():
    flow = getattr(pf, "_FLOW", None)
    if not isinstance(flow, dict):
        raise ValueError("forecaster flow state malformed")
    step = flow.get("step")
    if step is not None and not _is_int(step):
        raise ValueError("forecaster flow step malformed")
    inv = flow.get("inv")
    rate = flow.get("rate")
    our_net = flow.get("our_net")
    if not isinstance(inv, dict) or not isinstance(rate, dict) or not isinstance(our_net, dict):
        raise ValueError("forecaster flow maps malformed")
    for value in inv.values():
        if not _is_int(value):
            raise ValueError("forecaster inventory state malformed")
    for mapping in (rate, our_net):
        for value in mapping.values():
            if not _is_number(value):
                raise ValueError("forecaster numeric state malformed")
    for value in rate.values():
        if value < 0:
            raise ValueError("forecaster rival rate must be non-negative")


def _strict_upcoming_purchase_cost(tape, step, prices):
    if tape is None:
        return 0.0
    if not isinstance(tape, (list, tuple)):
        raise ValueError("tape must be a sequence")
    need = 0.0
    last = len(tape) - 1
    for s in range(step + 1, min(last, step + pf.CASH_LOOKAHEAD) + 1):
        entry = tape[s]
        if entry is None:
            continue
        if not isinstance(entry, dict):
            raise ValueError("malformed tape entry")
        raw_rows = entry.get("market")
        if raw_rows is None:
            rows = []
        elif not isinstance(raw_rows, list):
            raise ValueError("malformed tape market")
        else:
            rows = raw_rows
        for row in rows:
            if not row:
                continue
            _strict_market_row(row)
            op = row[0]
            if op not in ("BUY_PRODUCT", "BUY_SEED", "BUY_ANIMAL", "BUY_LAND", "HIRE"):
                continue
            if op in ("BUY_LAND", "HIRE"):
                if len(row) >= 3:
                    qty = _strict_qty(row[2])
                else:
                    qty = 1
            else:
                qty = _strict_qty(row[2])
            item = row[1] if len(row) >= 2 else None
            if op == "BUY_PRODUCT" and item in ("WHEAT", "FERTILIZER"):
                ref = max(prices[item], pf._BASE_PRICE.get(item, 0))
                need += qty * ref * 1.5
            elif op == "BUY_SEED" and item in pf._SEED_COST:
                need += qty * pf._SEED_COST[item]
            elif op == "BUY_ANIMAL" and item in pf._ANIMAL_COST:
                need += qty * pf._ANIMAL_COST[item]
            elif op == "BUY_LAND":
                need += 20000.0 * max(qty, 1)
            elif op == "HIRE":
                need += 5000.0 * max(qty, 1)
    return need


def _restore_state(flow_before, report_before):
    pf._FLOW.clear()
    pf._FLOW.update(flow_before)
    pf.REPORT.clear()
    pf.REPORT.update(report_before)


def apply_price_forecaster(observation, action, tape=None):
    """Strict E3 action rewrite. Never raises; failure returns ``action`` itself."""
    if not isinstance(action, dict):
        return action
    market = action.get("market")
    if not isinstance(market, list) or not market:
        return action

    try:
        step, _player, inventory, prices, shops, cash = _strict_observation(observation)
        if step < ACTIVE_START or step > ACTIVE_END:
            return action
        _validate_all_consumed_market_rows(market)
        leading = _leading_sell_block(market)
        if not leading:
            return action
        _strict_flow_state()
        # Validate the cash guard before mutating EMA state.
        purchase_need = _strict_upcoming_purchase_cost(tape, step, prices)
    except Exception:
        return action

    flow_before = copy.deepcopy(pf._FLOW)
    report_before = copy.deepcopy(pf.REPORT)
    try:
        rates = pf.update_rival_flow(step, inventory, shops)
        if not isinstance(rates, dict):
            raise ValueError("rival-flow result malformed")
        for value in rates.values():
            if not _is_number(value) or value < 0:
                raise ValueError("rival-flow result malformed")

        need = purchase_need - cash
        if tape is None:
            need = max(need, 3000.0 - cash)

        pf.REPORT["steps_active"] += 1
        decisions = []
        for index, item, qty in leading:
            if qty == 0:
                continue
            inv_now = inventory[item]
            rival_rate = rates.get(item, 0.0)
            if not _is_number(rival_rate) or rival_rate < 0:
                raise ValueError("rival-flow item rate malformed")
            keep = pf.keep_quantity(
                item, qty, inv_now, step, FORECAST_HORIZON, shops, rival_rate
            )
            if not _is_int(keep) or keep < 0 or keep > qty:
                raise ValueError("forecaster keep quantity malformed")
            keep_rev = float(sum(pf._unit_prices(item, inv_now, keep)))
            decisions.append((index, item, qty, keep, keep_rev))

        if not decisions:
            pf.record_our_sales(market, inventory)
            return action

        new_market = list(market)
        kept_revenue = 0.0
        changed = False
        for index, item, qty, keep, keep_rev in decisions:
            if keep < qty and kept_revenue < need:
                pf.REPORT["cash_guarded"] += 1
                keep = qty
                keep_rev = float(sum(pf._unit_prices(item, inventory[item], qty)))
            kept_revenue += keep_rev
            if keep == 0:
                pf.REPORT["rows_dropped"] += 1
                pf.REPORT["units_deferred"] += qty
                # Preserve row cardinality and the position of every tail row.
                new_market[index] = []
                changed = True
            elif keep < qty:
                pf.REPORT["rows_deferred"] += 1
                pf.REPORT["units_deferred"] += qty - keep
                rewritten = list(market[index])
                rewritten[2] = keep
                new_market[index] = rewritten
                changed = True
            else:
                pf.REPORT["rows_kept"] += 1

        if not changed:
            pf.record_our_sales(market, inventory)
            return action

        new_action = dict(action)
        new_action["market"] = new_market
        pf.record_our_sales(new_market, inventory)
        return new_action
    except Exception:
        _restore_state(flow_before, report_before)
        return action
