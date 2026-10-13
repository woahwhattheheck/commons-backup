from __future__ import annotations

from typing import Any

try:
    from .contract import ContractError, Order, Trader, _ratio
    from .market import _behavioral_metrics, _market_receipt, _public_value, run_call, run_continuous, synthetic_action
except ImportError:
    from contract import ContractError, Order, Trader, _ratio
    from market import _behavioral_metrics, _market_receipt, _public_value, run_call, run_continuous, synthetic_action


def evaluate_mechanism(
    scenario: dict[str, Any],
    trader_objs: list[Trader],
    trader_map: dict[str, Trader],
    mechanism: str,
    efficient: int,
) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    orders: list[Order] = []
    for trader in sorted(trader_objs, key=lambda t: (t.action_step, t.trader_id)):
        order, observation = synthetic_action(scenario, trader, mechanism)
        observations.append(observation)
        orders.append(order)
    if len({o.order_id for o in orders}) != len(orders):
        raise ContractError("duplicate action/order identity")
    if mechanism == "CONTINUOUS_DOUBLE_AUCTION":
        fills = run_continuous(orders, trader_map)
    else:
        final_reference, _ = _public_value(scenario["reference_price"], scenario["news"], 10**9)
        fills = run_call(orders, trader_map, final_reference)
    realized = sum(fill.surplus for fill in fills)
    # Irrational agent bids are experimental evidence, not parser errors.
    efficiency = _ratio(realized, efficient)
    passes = efficient > 0 and realized * 10000 > efficient * 9000
    return {
        "mechanism": mechanism,
        "efficient_surplus": efficient,
        "realized_surplus": realized,
        "allocative_efficiency": efficiency,
        "strictly_above_90_percent": passes,
        "behavioral_metrics": _behavioral_metrics(orders, fills, scenario["news"], scenario["reference_price"]),
        "provenance": _market_receipt(mechanism, scenario, observations, orders, fills),
    }
