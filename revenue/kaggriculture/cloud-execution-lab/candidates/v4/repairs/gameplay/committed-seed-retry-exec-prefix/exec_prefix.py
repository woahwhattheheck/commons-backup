# SPDX-License-Identifier: Apache-2.0
"""Feature-local executable-prefix helpers for committed seed retry.

Canonical V4 donor only.  Do not change shared SellScheduler.cash_reserve with
this file: committed-seed-retry is the narrower seam whose raw suffix can create
phantom BUY_PRODUCT vetoes and fixed-cost reservations.
"""
from __future__ import annotations

from typing import Any, Mapping


def market_limit(configuration: Mapping[str, Any] | None) -> int:
    cfg = dict(configuration or {})
    value = cfg.get('maxMarketOrdersPerTurn', 10)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError('order limit must be a positive integer')
    return value


def active_market(queue: Any, limit: int) -> list:
    if not isinstance(queue, list):
        raise ValueError('market must be a list')
    return queue[:limit]


def has_dynamic_product_obligation(queues: list[Any], configuration: Mapping[str, Any] | None) -> bool:
    limit = market_limit(configuration)
    return any(
        order and order[0] == 'BUY_PRODUCT'
        for queue in queues
        for order in active_market(queue, limit)
    )


def prefix_cash_reserve(runtime: Any, obs: Mapping[str, Any], configuration: Mapping[str, Any],
                        selected: Mapping[str, Any], end: int) -> int:
    """Mirror inherited reserve spend/state over engine-live market rows only."""
    from scheduler import _order_spend, m

    cfg = dict(configuration or {})
    limit = market_limit(cfg)
    now = int(obs['step'])
    player = int(obs['player'])
    farm = dict(obs['farms'][player])
    farm['unlocked_quadrants'] = list(farm['unlocked_quadrants'])
    hires = int(farm['hires_today'])
    cost = 0
    route = runtime.controller.R[runtime.controller.cur]
    inventory = obs['market']['inventory']
    params = obs['market'].get('params')
    for step in range(now, int(end) + 1):
        if step > now and step % 24 == 0:
            hires = 0
        queue = selected.get('market', []) if step == now else (
            route[step].get('market', []) if step < len(route) else [])
        for order in active_market(queue, limit):
            spend, hires = _order_spend(order, farm, inventory, params, hires, cfg)
            cost += spend
            if (order and order[0] == 'BUY_LAND'
                    and len(farm['unlocked_quadrants']) <= len(m.LAND_ORDER)):
                farm['unlocked_quadrants'].append(
                    m.LAND_ORDER[len(farm['unlocked_quadrants']) - 1])
    return cost


INTEGRATION = """In apply_committed_seed_retry(), derive limit=market_limit(cfg),
replace the raw future BUY_PRODUCT scan with has_dynamic_product_obligation(),
and replace runtime.consumer.cash_reserve(...) with prefix_cash_reserve(...).
Keep the existing hard veto when BUY_PRODUCT is inside the executable prefix.
Do not alter selected/route tapes, shared cash_reserve(), feature defaults, or
propose_seed_retry() appendix-only admission semantics."""
