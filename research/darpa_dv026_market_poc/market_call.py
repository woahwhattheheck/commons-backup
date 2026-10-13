from __future__ import annotations

from typing import Any

try:
    from .contract import ContractError, Fill, Order, Trader
except ImportError:
    from contract import ContractError, Fill, Order, Trader

try:
    from .market_continuous import _make_fill
except ImportError:
    from market_continuous import _make_fill

def _call_clearing_price(orders: list[Order], reference_price: int) -> tuple[int | None, int]:
    candidate_prices = sorted({o.price for o in orders})
    if not candidate_prices:
        return None, 0
    scored: list[tuple[int, int, int]] = []
    for price in candidate_prices:
        demand = sum(o.quantity for o in orders if o.side == "BUY" and o.price >= price)
        supply = sum(o.quantity for o in orders if o.side == "SELL" and o.price <= price)
        volume = min(demand, supply)
        scored.append((-volume, abs(price - reference_price), price))
    neg_volume, _, price = min(scored)
    return price, -neg_volume


def run_call(orders: list[Order], trader_map: dict[str, Trader], reference_price: int) -> list[Fill]:
    price, volume = _call_clearing_price(orders, reference_price)
    if price is None or volume == 0:
        return []
    buys = [[o.action_step, o.order_id, o.quantity, o] for o in orders if o.side == "BUY" and o.price >= price]
    sells = [[o.action_step, o.order_id, o.quantity, o] for o in orders if o.side == "SELL" and o.price <= price]
    # Better price first, then time; we need price preserved for sort.
    buy_map = {o.order_id: o for o in orders}
    sell_map = buy_map
    buys.sort(key=lambda x: (-buy_map[x[1]].price, x[0], x[1]))
    sells.sort(key=lambda x: (sell_map[x[1]].price, x[0], x[1]))
    fills: list[Fill] = []
    remaining = volume
    bi = si = 0
    while remaining and bi < len(buys) and si < len(sells):
        b = buys[bi]
        s = sells[si]
        if b[3].trader_id == s[3].trader_id:
            raise ContractError("self-trade candidate detected")
        qty = min(remaining, b[2], s[2])
        fills.append(_make_fill(len(fills) + 1, b[3], s[3], qty, price, trader_map))
        remaining -= qty
        b[2] -= qty
        s[2] -= qty
        if b[2] == 0:
            bi += 1
        if s[2] == 0:
            si += 1
    return fills


