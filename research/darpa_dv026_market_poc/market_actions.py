from __future__ import annotations

from typing import Any, Iterable

try:
    from .contract import ContractError, MAX_PRICE, MECHANISMS, Fill, Order, Trader, sha256_value, validate_blackbox_action
except ImportError:  # direct module execution/tests
    from contract import ContractError, MAX_PRICE, MECHANISMS, Fill, Order, Trader, sha256_value, validate_blackbox_action


def _trader(row: dict[str, Any]) -> Trader:
    return Trader(
        trader_id=row["trader_id"],
        side=row["side"],
        private_value=row["private_value"],
        quantity=row["quantity"],
        action_step=row["action_step"],
        strategy=row["strategy"],
        shade=row["shade"],
    )


def _public_value(reference_price: int, news: list[dict[str, Any]], action_step: int) -> tuple[int, list[str]]:
    value = reference_price
    applied: list[str] = []
    for event in sorted(news, key=lambda row: (row["step"], row["news_id"])):
        if event["step"] <= action_step:
            value += event["delta"]
            applied.append(event["news_id"])
    if value < 1:
        value = 1
    if value > MAX_PRICE:
        value = MAX_PRICE
    return value, applied


def blackbox_observation(scenario: dict[str, Any], trader: Trader, mechanism: str) -> dict[str, Any]:
    if mechanism not in MECHANISMS:
        raise ContractError("unsupported market mechanism")
    public_value, news_ids = _public_value(scenario["reference_price"], scenario["news"], trader.action_step)
    return {
        "schema": "darpa-dv026-blackbox-observation/v1",
        "scenario_id": scenario["scenario_id"],
        "asset_id": scenario["asset_id"],
        "mechanism": mechanism,
        "trader_id": trader.trader_id,
        "side": trader.side,
        "action_step": trader.action_step,
        "public_reference_price": public_value,
        "public_news_ids": news_ids,
        "private_value": trader.private_value,
        "max_quantity": trader.quantity,
    }


def synthetic_action(scenario: dict[str, Any], trader: Trader, mechanism: str) -> tuple[Order, dict[str, Any]]:
    observation = blackbox_observation(scenario, trader, mechanism)
    public_value = observation["public_reference_price"]
    obs_sha = sha256_value(observation)
    if trader.strategy == "TRUTHFUL":
        price = trader.private_value
    elif trader.strategy == "SHADED":
        price = trader.private_value - trader.shade if trader.side == "BUY" else trader.private_value + trader.shade
    else:  # NEWS_FOLLOWER: respect private rationality cap/floor.
        if trader.side == "BUY":
            price = min(trader.private_value, max(1, public_value + trader.shade))
        else:
            price = max(trader.private_value, min(MAX_PRICE, public_value - trader.shade))
    price = max(1, min(MAX_PRICE, price))
    envelope = {
        "schema": "darpa-dv026-blackbox-action/v1",
        "order_id": f"ord:{mechanism}:{trader.trader_id}",
        "trader_id": trader.trader_id,
        "side": trader.side,
        "price": price,
        "quantity": trader.quantity,
        "action_step": trader.action_step,
        "observation_sha256": obs_sha,
    }
    return validate_blackbox_action(envelope, trader, obs_sha, mechanism), observation


def efficient_surplus(traders: Iterable[Trader]) -> int:
    buys: list[int] = []
    sells: list[int] = []
    for trader in traders:
        bucket = buys if trader.side == "BUY" else sells
        bucket.extend([trader.private_value] * trader.quantity)
    buys.sort(reverse=True)
    sells.sort()
    total = 0
    for value, cost in zip(buys, sells):
        if value < cost:
            break
        total += value - cost
    return total
