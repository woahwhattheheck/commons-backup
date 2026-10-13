#!/usr/bin/env python3
"""Exact-engine oracle for simultaneous BUY_PRODUCT lockstep pricing.

Research-only. This proves quote/commit mechanics and bounded current-cost deltas;
it does not predict rival orders or authorize policy/runtime activation.
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
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def load_engine(path: str | Path):
    path = Path(path)
    data = path.read_bytes()
    actual = git_blob(data)
    if actual != ENGINE_BLOB:
        raise ValueError(f"engine Git blob mismatch: {actual}")
    try:
        import kaggle_environments.utils  # noqa: F401
    except ModuleNotFoundError:
        pkg = sys.modules.setdefault("kaggle_environments", types.ModuleType("kaggle_environments"))
        util = types.ModuleType("kaggle_environments.utils")
        util.resolve_episode_seed = lambda env: int(getattr(env, "info", {}).get("seed", 0))
        pkg.utils = util
        sys.modules["kaggle_environments.utils"] = util
    spec = importlib.util.spec_from_file_location("titan_lockstep_cobuy_engine", path)
    if spec is None or spec.loader is None:
        raise ValueError("could not load engine module")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    required = ("_new_farm", "_new_private", "_new_market", "_process_market", "market_price")
    missing = [name for name in required if not hasattr(mod, name)]
    if missing:
        raise ValueError(f"engine missing symbols: {missing}")
    return mod


def _plain_qty(value: Any, name: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be a plain int >= {minimum}")
    if value > CONFIG["shedCapacity"]:
        raise ValueError(f"{name} exceeds default physical shed capacity {CONFIG['shedCapacity']}")
    return value


def _world(engine):
    farms = [engine._new_farm(CONFIG["boardSize"], STARTING_MONEY) for _ in range(2)]
    privates = [engine._new_private() for _ in range(2)]
    market = engine._new_market()
    states = []
    for player in range(2):
        obs = SimpleNamespace(player=player, farms=farms, private=privates[player], market=market)
        states.append(SimpleNamespace(observation=obs, action={}))
    env = SimpleNamespace(configuration=dict(CONFIG), info={"seed": 0})
    return states, env


def _market_call(engine, states, env, rival_orders: list, self_orders: list) -> None:
    states[0].action = {"farmer": ["PASS"], "hands": [], "market": rival_orders}
    states[1].action = {"farmer": ["PASS"], "hands": [], "market": self_orders}
    engine._process_market(states, env)


def _buy(item: str, quantity: int) -> list:
    return ["BUY_PRODUCT", item, quantity]


def _cost(states, player: int) -> int:
    return int(round(STARTING_MONEY - states[0].observation.farms[player]["money"]))


def _snapshot(states, item: str) -> dict[str, int]:
    market = states[0].observation.market
    return {
        "market_inventory": int(market["inventory"][item]),
        "rival_shed": int(states[0].observation.private["shed"].get(item, 0)),
        "self_shed": int(states[1].observation.private["shed"].get(item, 0)),
    }


def simulate_pair(engine, *, self_item: str, self_qty: int, rival_item: str, rival_qty: int,
                  aligned: bool = True) -> dict[str, Any]:
    """Run one callback, optionally shifting our order to raw market row 1.

    A row-1 self order is preceded by an invalid zero-quantity SELL. It parses to
    None and is intentionally inert; the rival row-0 BUY therefore finishes
    before our row-1 BUY begins.
    """
    if self_item not in BUYABLE or rival_item not in BUYABLE:
        raise ValueError(f"BUY_PRODUCT item must be one of {BUYABLE}")
    self_qty = _plain_qty(self_qty, "self_qty")
    rival_qty = _plain_qty(rival_qty, "rival_qty", allow_zero=True)
    states, env = _world(engine)
    rival_orders = [_buy(rival_item, rival_qty)] if rival_qty else []
    self_orders = [_buy(self_item, self_qty)]
    if not aligned:
        self_orders.insert(0, ["SELL", "WHEAT", 0])
    before = int(states[0].observation.market["inventory"][self_item])
    _market_call(engine, states, env, rival_orders, self_orders)
    return {
        "self_cost": _cost(states, 1),
        "rival_cost": _cost(states, 0),
        "self_item": self_item,
        "rival_item": rival_item,
        "self_qty": self_qty,
        "rival_qty": rival_qty,
        "aligned": bool(aligned),
        "self_inventory_before": before,
        "snapshot": _snapshot(states, self_item),
    }


def simulate_wait(engine, *, self_item: str, self_qty: int, rival_item: str, rival_qty: int) -> dict[str, Any]:
    """Let the rival's whole BUY finish, then execute our BUY in a later callback."""
    if self_item not in BUYABLE or rival_item not in BUYABLE:
        raise ValueError(f"BUY_PRODUCT item must be one of {BUYABLE}")
    self_qty = _plain_qty(self_qty, "self_qty")
    rival_qty = _plain_qty(rival_qty, "rival_qty", allow_zero=True)
    states, env = _world(engine)
    if rival_qty:
        _market_call(engine, states, env, [_buy(rival_item, rival_qty)], [])
    _market_call(engine, states, env, [], [_buy(self_item, self_qty)])
    return {
        "self_cost": _cost(states, 1),
        "rival_cost": _cost(states, 0),
        "self_item": self_item,
        "rival_item": rival_item,
        "self_qty": self_qty,
        "rival_qty": rival_qty,
        "snapshot": _snapshot(states, self_item),
    }


def compare(engine, *, item: str, self_qty: int, rival_qty: int) -> dict[str, Any]:
    paired = simulate_pair(engine, self_item=item, self_qty=self_qty,
                           rival_item=item, rival_qty=rival_qty, aligned=True)
    misaligned = simulate_pair(engine, self_item=item, self_qty=self_qty,
                               rival_item=item, rival_qty=rival_qty, aligned=False)
    waited = simulate_wait(engine, self_item=item, self_qty=self_qty,
                           rival_item=item, rival_qty=rival_qty)
    same_terminal_inventory = (
        paired["snapshot"]["market_inventory"]
        == misaligned["snapshot"]["market_inventory"]
        == waited["snapshot"]["market_inventory"]
    )
    if not same_terminal_inventory:
        raise AssertionError("pair/wait worlds did not consume the same public quantity")
    return {
        "kind": "titan-v4-lockstep-cobuy-oracle",
        "engine_git_blob": ENGINE_BLOB,
        "item": item,
        "self_qty": self_qty,
        "rival_qty": rival_qty,
        "simultaneous_self_cost": paired["self_cost"],
        "misaligned_same_callback_self_cost": misaligned["self_cost"],
        "wait_behind_self_cost": waited["self_cost"],
        "simultaneous_saving_vs_wait": waited["self_cost"] - paired["self_cost"],
        "misaligned_saving_vs_wait": waited["self_cost"] - misaligned["self_cost"],
        "same_terminal_inventory": same_terminal_inventory,
        "terminal_market_inventory": waited["snapshot"]["market_inventory"],
        "limits": [
            "mechanics/current-cost witness only; not rival-order prediction or field EV",
            "same-row benefit requires same BUY_PRODUCT item and simultaneous active order units",
            "quantities are capped at default shedCapacity so the witness is physically executable",
            "policy integration requires independent current-native opportunity and both-seat economics gates",
        ],
    }


def default_engine_path() -> Path:
    return Path(__file__).resolve().parents[4] / "reference" / "engine" / "kaggriculture.py"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", type=Path, default=default_engine_path())
    ap.add_argument("--item", choices=BUYABLE, default="WHEAT")
    ap.add_argument("--self-qty", type=int, default=100)
    ap.add_argument("--rival-qty", type=int, default=100)
    ns = ap.parse_args(argv)
    engine = load_engine(ns.engine)
    print(json.dumps(compare(engine, item=ns.item, self_qty=ns.self_qty, rival_qty=ns.rival_qty),
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
