#!/usr/bin/env python3
"""TITAN V4 opposite-side lockstep quote oracle.

Research-only.  Proves quote/commit mechanics for already-required same-item
BUY_PRODUCT/SELL flows on WHEAT and FERTILIZER.  It does not predict rival
orders, rewrite policy, or authorize activation.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
BUYABLE = ("WHEAT", "FERTILIZER")
CONFIG = {
    "boardSize": 10,
    "shedCapacity": 100,
    "maxMarketOrdersPerTurn": 10,
    "farmHandCostMult": 1,
}
STARTING_MONEY = 1_000_000


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def load_engine(path: str | Path):
    """Load only the exact official engine revision this theorem was proved on."""
    path = Path(path)
    data = path.read_bytes()
    actual = git_blob(data)
    if actual != ENGINE_BLOB:
        raise ValueError(f"engine Git blob mismatch: expected {ENGINE_BLOB}, got {actual}")

    try:
        import kaggle_environments.utils  # noqa: F401
    except ModuleNotFoundError:
        pkg = sys.modules.setdefault("kaggle_environments", types.ModuleType("kaggle_environments"))
        util = types.ModuleType("kaggle_environments.utils")
        util.resolve_episode_seed = lambda env: int(getattr(env, "info", {}).get("seed", 0))
        pkg.utils = util
        sys.modules["kaggle_environments.utils"] = util

    spec = importlib.util.spec_from_file_location("titan_crossflow_engine", path)
    if spec is None or spec.loader is None:
        raise ValueError("could not load engine module")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    required = ("_new_farm", "_new_private", "_new_market", "_process_market", "market_price")
    missing = [name for name in required if not hasattr(mod, name)]
    if missing:
        raise ValueError(f"engine missing symbols: {missing}")
    return mod


def _plain_qty(value: Any, name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a plain int >= 1")
    if value > CONFIG["shedCapacity"]:
        raise ValueError(f"{name} exceeds default physical shed capacity {CONFIG['shedCapacity']}")
    return value


def _plain_inventory(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("inventory must be a plain nonnegative int")
    return value


def _world(engine, *, item: str, inventory: int):
    if item not in BUYABLE:
        raise ValueError(f"item must be one of {BUYABLE}")
    inventory = _plain_inventory(inventory)
    farms = [engine._new_farm(CONFIG["boardSize"], STARTING_MONEY) for _ in range(2)]
    privates = [engine._new_private() for _ in range(2)]
    market = engine._new_market()
    market["inventory"][item] = inventory
    states = []
    for player in range(2):
        obs = SimpleNamespace(player=player, farms=farms, private=privates[player], market=market)
        states.append(SimpleNamespace(observation=obs, action={}))
    env = SimpleNamespace(configuration=dict(CONFIG), info={"seed": 0})
    return states, env


def _market_call(engine, states, env, p0_orders: list, p1_orders: list) -> None:
    states[0].action = {"farmer": ["PASS"], "hands": [], "market": p0_orders}
    states[1].action = {"farmer": ["PASS"], "hands": [], "market": p1_orders}
    engine._process_market(states, env)


def _buy(item: str, quantity: int) -> list:
    return ["BUY_PRODUCT", item, quantity]


def _sell(item: str, quantity: int) -> list:
    return ["SELL", item, quantity]


def _row1(order: list) -> list[list]:
    return [["SELL", "WHEAT", 0], order]


def _money_delta(states, player: int) -> int:
    farm = states[0].observation.farms[player]
    return int(round(farm["money"] - STARTING_MONEY))


def buyer_waits_for_rival_supply(engine, *, item: str, quantity: int,
                                 inventory: int = 10_000, delayed: bool) -> dict[str, Any]:
    """Player 1 buys while player 0 sells the same item."""
    if item not in BUYABLE:
        raise ValueError(f"item must be one of {BUYABLE}")
    quantity = _plain_qty(quantity, "quantity")
    states, env = _world(engine, item=item, inventory=inventory)
    states[0].observation.private["shed"][item] = quantity
    buy = _buy(item, quantity)
    before = int(states[0].observation.market["inventory"][item])
    _market_call(engine, states, env, [_sell(item, quantity)], _row1(buy) if delayed else [buy])
    return {
        "delayed": bool(delayed),
        "buyer_cost": -_money_delta(states, 1),
        "rival_sell_revenue": _money_delta(states, 0),
        "market_inventory_before": before,
        "market_inventory_after": int(states[0].observation.market["inventory"][item]),
        "buyer_shed": int(states[1].observation.private["shed"].get(item, 0)),
        "rival_shed": int(states[0].observation.private["shed"].get(item, 0)),
    }


def seller_waits_for_rival_demand(engine, *, item: str, quantity: int,
                                  inventory: int = 10_000, delayed: bool) -> dict[str, Any]:
    """Player 1 sells while player 0 buys the same item."""
    if item not in BUYABLE:
        raise ValueError(f"item must be one of {BUYABLE}")
    quantity = _plain_qty(quantity, "quantity")
    states, env = _world(engine, item=item, inventory=inventory)
    states[1].observation.private["shed"][item] = quantity
    sell = _sell(item, quantity)
    before = int(states[0].observation.market["inventory"][item])
    _market_call(engine, states, env, [_buy(item, quantity)], _row1(sell) if delayed else [sell])
    return {
        "delayed": bool(delayed),
        "seller_revenue": _money_delta(states, 1),
        "rival_buy_cost": -_money_delta(states, 0),
        "market_inventory_before": before,
        "market_inventory_after": int(states[0].observation.market["inventory"][item]),
        "seller_shed": int(states[1].observation.private["shed"].get(item, 0)),
        "rival_shed": int(states[0].observation.private["shed"].get(item, 0)),
    }


def compare(engine, *, item: str, quantity: int = 100, inventory: int = 10_000) -> dict[str, Any]:
    """Compare aligned cross-flow against waiting exactly one raw market row."""
    if item not in BUYABLE:
        raise ValueError(f"item must be one of {BUYABLE}")
    quantity = _plain_qty(quantity, "quantity")
    inventory = _plain_inventory(inventory)

    b0 = buyer_waits_for_rival_supply(engine, item=item, quantity=quantity,
                                      inventory=inventory, delayed=False)
    b1 = buyer_waits_for_rival_supply(engine, item=item, quantity=quantity,
                                      inventory=inventory, delayed=True)
    s0 = seller_waits_for_rival_demand(engine, item=item, quantity=quantity,
                                       inventory=inventory, delayed=False)
    s1 = seller_waits_for_rival_demand(engine, item=item, quantity=quantity,
                                       inventory=inventory, delayed=True)
    buyer_same = b0["market_inventory_after"] == b1["market_inventory_after"]
    seller_same = s0["market_inventory_after"] == s1["market_inventory_after"]
    return {
        "kind": "titan-v4-crossflow-quote-oracle",
        "engine_git_blob": ENGINE_BLOB,
        "item": item,
        "quantity": quantity,
        "inventory": inventory,
        "price_at_inventory": int(engine.market_price(item, inventory)),
        "clean_same_terminal_quote_theorem": buyer_same and seller_same,
        "buyer": {
            "aligned_cost": b0["buyer_cost"],
            "delayed_cost": b1["buyer_cost"],
            "saving_by_waiting_for_supply": b0["buyer_cost"] - b1["buyer_cost"],
            "same_terminal_inventory": buyer_same,
            "aligned_terminal_inventory": b0["market_inventory_after"],
            "delayed_terminal_inventory": b1["market_inventory_after"],
        },
        "seller": {
            "aligned_revenue": s0["seller_revenue"],
            "delayed_revenue": s1["seller_revenue"],
            "gain_by_waiting_for_demand": s1["seller_revenue"] - s0["seller_revenue"],
            "same_terminal_inventory": seller_same,
            "aligned_terminal_inventory": s0["market_inventory_after"],
            "delayed_terminal_inventory": s1["market_inventory_after"],
        },
        "limits": [
            "source mechanics only; no rival-current-action prediction or field EV",
            "BUY_PRODUCT cross-flow exists only for WHEAT/FERTILIZER",
            "retiming needs an independent raw-row opportunity/cap/cash theorem",
            "PRICE_FLOOR SELL is destructive, so clean same-terminal theorem refuses there",
        ],
    }


def default_engine_path() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if parent.name == "cloud-execution-lab":
            return parent / "reference" / "engine" / "kaggriculture.py"
    raise FileNotFoundError("cloud-execution-lab ancestor not present")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", type=Path, default=None)
    parser.add_argument("--item", choices=BUYABLE, default="WHEAT")
    parser.add_argument("--quantity", type=int, default=100)
    parser.add_argument("--inventory", type=int, default=10_000)
    args = parser.parse_args(argv)
    engine = load_engine(args.engine if args.engine is not None else default_engine_path())
    print(json.dumps(compare(engine, item=args.item, quantity=args.quantity,
                             inventory=args.inventory), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
