from __future__ import annotations

from typing import Any

try:
    from .contract import ContractError, Fill, Order, Trader
except ImportError:
    from contract import ContractError, Fill, Order, Trader

def _make_fill(fill_index: int, buy: Order, sell: Order, qty: int, price: int, trader_map: dict[str, Trader]) -> Fill:
    if buy.trader_id == sell.trader_id:
        raise ContractError("self-trade is forbidden")
    buyer = trader_map[buy.trader_id]
    seller = trader_map[sell.trader_id]
    if buyer.side != "BUY" or seller.side != "SELL":
        raise ContractError("fill side corruption")
    return Fill(
        fill_id=f"fill:{fill_index:04d}",
        buyer_id=buyer.trader_id,
        seller_id=seller.trader_id,
        quantity=qty,
        price=price,
        buyer_private_value=buyer.private_value,
        seller_private_cost=seller.private_value,
    )


def run_continuous(orders: list[Order], trader_map: dict[str, Trader]) -> list[Fill]:
    buys: list[list[Any]] = []  # [price, step, order_id, trader_id, remaining, order]
    sells: list[list[Any]] = []
    fills: list[Fill] = []
    for order in sorted(orders, key=lambda o: (o.action_step, o.order_id)):
        row = [order.price, order.action_step, order.order_id, order.trader_id, order.quantity, order]
        (buys if order.side == "BUY" else sells).append(row)
        buys.sort(key=lambda x: (-x[0], x[1], x[2]))
        sells.sort(key=lambda x: (x[0], x[1], x[2]))
        while buys and sells and buys[0][0] >= sells[0][0]:
            b = buys[0]
            s = sells[0]
            if b[3] == s[3]:
                raise ContractError("self-trade candidate detected")
            qty = min(b[4], s[4])
            # Resting order price: earlier order sets transaction price; tie by order id.
            earlier_buy = (b[1], b[2]) < (s[1], s[2])
            price = b[0] if earlier_buy else s[0]
            fills.append(_make_fill(len(fills) + 1, b[5], s[5], qty, price, trader_map))
            b[4] -= qty
            s[4] -= qty
            if b[4] == 0:
                buys.pop(0)
            if s[4] == 0:
                sells.pop(0)
    return fills


