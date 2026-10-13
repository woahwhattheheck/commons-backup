from __future__ import annotations

from typing import Any

try:
    from .contract import Fill, Order, Trader, sha256_value
except ImportError:
    from contract import Fill, Order, Trader, sha256_value

def _behavioral_metrics(orders: list[Order], fills: list[Fill], news: list[dict[str, Any]], reference_price: int) -> dict[str, Any]:
    total_qty = sum(o.quantity for o in orders)
    buy_qty = sum(o.quantity for o in orders if o.side == "BUY")
    sell_qty = total_qty - buy_qty
    fill_qty = sum(f.quantity for f in fills)
    prices = [o.price for o in orders]
    post_news_orders = 0
    if news:
        first_news_step = min(n["step"] for n in news)
        post_news_orders = sum(1 for o in orders if o.action_step >= first_news_step)
    return {
        "orders": len(orders),
        "submitted_quantity": total_qty,
        "buy_quantity": buy_qty,
        "sell_quantity": sell_qty,
        "filled_quantity": fill_qty,
        "participation_basis_points": (fill_qty * 10000 // total_qty) if total_qty else 0,
        "min_order_price": min(prices) if prices else None,
        "max_order_price": max(prices) if prices else None,
        "reference_price": reference_price,
        "public_news_events": len(news),
        "orders_at_or_after_first_news": post_news_orders,
    }


def _market_receipt(mechanism: str, scenario: dict[str, Any], observations: list[dict[str, Any]], orders: list[Order], fills: list[Fill]) -> dict[str, Any]:
    order_rows = [
        {
            "order_id": o.order_id,
            "trader_id": o.trader_id,
            "side": o.side,
            "price": o.price,
            "quantity": o.quantity,
            "action_step": o.action_step,
            "observation_sha256": o.observation_sha256,
            "action_sha256": o.action_sha256,
        }
        for o in orders
    ]
    fill_rows = [
        {
            "fill_id": f.fill_id,
            "buyer_id": f.buyer_id,
            "seller_id": f.seller_id,
            "quantity": f.quantity,
            "price": f.price,
            "buyer_private_value": f.buyer_private_value,
            "seller_private_cost": f.seller_private_cost,
            "surplus": f.surplus,
        }
        for f in fills
    ]
    ledger = []
    pre_state = sha256_value({"mechanism": mechanism, "scenario_id": scenario["scenario_id"], "state": "GENESIS"})
    for index, (obs, order) in enumerate(zip(observations, orders), 1):
        post_state = sha256_value({"previous": pre_state, "observation": obs, "action": order_rows[index - 1]})
        ledger.append(
            {
                "event_seq": index,
                "observation_sha256": order.observation_sha256,
                "action_sha256": order.action_sha256,
                "pre_state_sha256": pre_state,
                "post_state_sha256": post_state,
            }
        )
        pre_state = post_state
    final_state = sha256_value({"action_state": pre_state, "fills": fill_rows})
    return {
        "orders_sha256": sha256_value(order_rows),
        "fills_sha256": sha256_value(fill_rows),
        "ledger_sha256": sha256_value(ledger),
        "final_state_sha256": final_state,
        "orders": order_rows,
        "fills": fill_rows,
        "ledger": ledger,
    }


