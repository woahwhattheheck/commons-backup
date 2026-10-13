#!/usr/bin/env python3
"""Exact-engine research oracle for simultaneous same-item SELL lockstep pricing.

Research-only. Proves market quote/commit mechanics and cash deltas. It does not
predict rival actions and does not authorize policy/runtime activation.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
ENGINE_JSON_BLOB = "b354d06b742fe48402513792253f1a5c29366b20"
CONFIG = {
    "boardSize": 10,
    "shedCapacity": 100,
    "maxMarketOrdersPerTurn": 10,
    "farmHandCostMult": 1,
}
STARTING_MONEY = 1_000_000


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _captured_spec_reader(spec_path: Path, spec_bytes: bytes):
    """Return a fail-closed text reader for the authenticated engine JSON only."""
    wanted = spec_path.resolve()

    def guarded_open(file, mode="r", *args, **kwargs):
        try:
            candidate = Path(file).resolve()
        except (TypeError, ValueError, OSError) as error:
            raise ValueError(f"invalid engine-side open target: {file!r}") from error
        if candidate != wanted:
            raise ValueError(f"undeclared engine-side open: {candidate}")
        if mode not in {"r", "rt"}:
            raise ValueError(f"engine specification opened with unsupported mode: {mode!r}")
        if args:
            raise ValueError("engine specification open rejects positional options")
        encoding = kwargs.pop("encoding", None)
        errors = kwargs.pop("errors", None)
        newline = kwargs.pop("newline", None)
        closefd = kwargs.pop("closefd", True)
        opener = kwargs.pop("opener", None)
        buffering = kwargs.pop("buffering", -1)
        if kwargs:
            raise ValueError(f"unsupported engine specification open options: {sorted(kwargs)}")
        if encoding not in {None, "utf-8", "UTF-8"}:
            raise ValueError(f"unsupported engine specification encoding: {encoding!r}")
        if errors not in {None, "strict"}:
            raise ValueError(f"unsupported engine specification errors: {errors!r}")
        if newline not in {None, ""}:
            raise ValueError(f"unsupported engine specification newline: {newline!r}")
        if closefd is not True or opener is not None or buffering != -1:
            raise ValueError("unsupported engine specification descriptor options")
        return io.StringIO(spec_bytes.decode("utf-8", errors="strict"), newline=newline)

    return guarded_open


def _unavailable_episode_seed(*_args, **_kwargs):
    raise ValueError("resolve_episode_seed is outside COSELL market-proof scope")


def _exec_captured_engine(path: Path, source: bytes, spec_path: Path, spec_bytes: bytes):
    """Execute authenticated engine bytes with only declared proof dependencies."""
    package_name = "kaggle_environments"
    utils_name = "kaggle_environments.utils"
    previous_package = sys.modules.get(package_name)
    previous_utils = sys.modules.get(utils_name)
    had_package = package_name in sys.modules
    had_utils = utils_name in sys.modules

    package = types.ModuleType(package_name)
    package.__path__ = []
    util = types.ModuleType(utils_name)
    util.resolve_episode_seed = _unavailable_episode_seed
    package.utils = util
    sys.modules[package_name] = package
    sys.modules[utils_name] = util

    module = types.ModuleType("titan_cosell_lockstep_engine")
    module.__file__ = str(path)
    module.__package__ = ""
    # The exact pinned engine uses bare open() only for its adjacent JSON spec.
    # Providing a module-global reader leaves standard-library import machinery
    # untouched while making any other engine-side file open fail closed.
    module.__dict__["open"] = _captured_spec_reader(spec_path, spec_bytes)
    try:
        exec(compile(source, str(path), "exec"), module.__dict__)
    finally:
        if had_utils:
            sys.modules[utils_name] = previous_utils
        else:
            sys.modules.pop(utils_name, None)
        if had_package:
            sys.modules[package_name] = previous_package
        else:
            sys.modules.pop(package_name, None)
    return module


def load_engine(path: str | Path):
    """Capture/authenticate Python + adjacent JSON once, then execute snapshots."""
    path = Path(path)
    spec_path = path.with_suffix(".json")
    source = path.read_bytes()
    spec_bytes = spec_path.read_bytes()
    actual_source = git_blob(source)
    actual_spec = git_blob(spec_bytes)
    if actual_source != ENGINE_BLOB:
        raise ValueError(f"engine Git blob mismatch: {actual_source}")
    if actual_spec != ENGINE_JSON_BLOB:
        raise ValueError(f"engine JSON Git blob mismatch: {actual_spec}")

    module = _exec_captured_engine(path, source, spec_path, spec_bytes)
    required = ("PRODUCTS", "_new_farm", "_new_private", "_new_market", "_new_town",
                "_process_market", "_town_consume", "_refresh_prices")
    missing = [name for name in required if not hasattr(module, name)]
    if missing:
        raise ValueError(f"engine missing symbols: {missing}")
    module._cosell_source_identity = {"python_git_blob": actual_source, "json_git_blob": actual_spec}
    return module


def _plain_int(value: Any, name: str, *, minimum: int = 0, maximum: int | None = None) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be a plain int >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return value


def _world(engine, *, item: str, inventory: int, self_qty: int, rival_qty: int):
    if item not in tuple(engine.PRODUCTS):
        raise ValueError(f"unknown market item: {item}")
    inventory = _plain_int(inventory, "inventory", minimum=0)
    self_qty = _plain_int(self_qty, "self_qty", minimum=1, maximum=CONFIG["shedCapacity"])
    rival_qty = _plain_int(rival_qty, "rival_qty", minimum=0, maximum=CONFIG["shedCapacity"])

    farms = [engine._new_farm(CONFIG["boardSize"], STARTING_MONEY) for _ in range(2)]
    privates = [engine._new_private() for _ in range(2)]
    market = engine._new_market()
    market["inventory"][item] = inventory
    engine._refresh_prices(market)
    privates[0]["shed"][item] = rival_qty
    privates[1]["shed"][item] = self_qty
    states = []
    for player in range(2):
        obs = SimpleNamespace(player=player, farms=farms, private=privates[player], market=market)
        states.append(SimpleNamespace(observation=obs, action={}))
    env = SimpleNamespace(configuration=dict(CONFIG), info={"seed": 0})
    return states, env


def _sell(item: str, quantity: int) -> list:
    return ["SELL", item, quantity]


def _market_call(engine, states, env, rival_orders: list, self_orders: list) -> None:
    states[0].action = {"farmer": ["PASS"], "hands": [], "market": rival_orders}
    states[1].action = {"farmer": ["PASS"], "hands": [], "market": self_orders}
    engine._process_market(states, env)


def _money(states, player: int) -> int:
    return int(round(states[0].observation.farms[player]["money"]))


def simulate_pair(engine, *, item: str, inventory: int, self_qty: int, rival_qty: int,
                  aligned: bool = True) -> dict[str, Any]:
    """Execute same-callback SELLs either in one market slot or sequential slots."""
    states, env = _world(engine, item=item, inventory=inventory, self_qty=self_qty, rival_qty=rival_qty)
    rival_orders = [_sell(item, rival_qty)] if rival_qty else []
    self_orders = [_sell(item, self_qty)]
    if not aligned:
        # A zero-quantity SELL is parser-inert. The rival's row-0 SELL therefore
        # completes before our row-1 SELL starts, preserving the same callback.
        self_orders.insert(0, ["SELL", item, 0])
    _market_call(engine, states, env, rival_orders, self_orders)
    market = states[0].observation.market
    return {
        "self_revenue": _money(states, 1) - STARTING_MONEY,
        "rival_revenue": _money(states, 0) - STARTING_MONEY,
        "terminal_market_inventory": int(market["inventory"][item]),
        "terminal_self_shed": int(states[1].observation.private["shed"].get(item, 0)),
        "terminal_rival_shed": int(states[0].observation.private["shed"].get(item, 0)),
    }


def simulate_sequential_market_only(engine, *, item: str, inventory: int, self_qty: int,
                                    rival_qty: int) -> dict[str, Any]:
    """Execute two market processors back-to-back without interpreter phases.

    This is deliberately *not* a next-callback simulation: no town consumption,
    plant decay, EOD transition, or intervening unit phase runs between calls. It
    isolates only the quote effect of committing the rival sale before our sale.
    """
    states, env = _world(engine, item=item, inventory=inventory, self_qty=self_qty, rival_qty=rival_qty)
    if rival_qty:
        _market_call(engine, states, env, [_sell(item, rival_qty)], [])
    _market_call(engine, states, env, [], [_sell(item, self_qty)])
    market = states[0].observation.market
    return {
        "self_revenue": _money(states, 1) - STARTING_MONEY,
        "rival_revenue": _money(states, 0) - STARTING_MONEY,
        "terminal_market_inventory": int(market["inventory"][item]),
        "terminal_self_shed": int(states[1].observation.private["shed"].get(item, 0)),
        "terminal_rival_shed": int(states[0].observation.private["shed"].get(item, 0)),
    }


def compare(engine, *, item: str, inventory: int, self_qty: int, rival_qty: int) -> dict[str, Any]:
    paired = simulate_pair(engine, item=item, inventory=inventory, self_qty=self_qty,
                           rival_qty=rival_qty, aligned=True)
    misaligned = simulate_pair(engine, item=item, inventory=inventory, self_qty=self_qty,
                               rival_qty=rival_qty, aligned=False)
    sequential = simulate_sequential_market_only(
        engine, item=item, inventory=inventory, self_qty=self_qty, rival_qty=rival_qty
    )
    terminals = {
        (x["terminal_market_inventory"], x["terminal_self_shed"], x["terminal_rival_shed"])
        for x in (paired, misaligned, sequential)
    }
    if len(terminals) != 1:
        raise AssertionError(
            "aligned/misaligned/sequential-market-only worlds did not reach the same physical terminal state"
        )
    return {
        "kind": "titan-v4-cosell-lockstep-oracle",
        "engine_git_blob": ENGINE_BLOB,
        "engine_json_git_blob": ENGINE_JSON_BLOB,
        "item": item,
        "initial_market_inventory": inventory,
        "self_qty": self_qty,
        "rival_qty": rival_qty,
        "simultaneous_self_revenue": paired["self_revenue"],
        "misaligned_same_callback_self_revenue": misaligned["self_revenue"],
        "sequential_market_only_self_revenue": sequential["self_revenue"],
        "simultaneous_gain_vs_sequential_market_only": paired["self_revenue"] - sequential["self_revenue"],
        "misaligned_gain_vs_sequential_market_only": misaligned["self_revenue"] - sequential["self_revenue"],
        "same_terminal_state": True,
        "terminal_market_inventory": sequential["terminal_market_inventory"],
        "limits": [
            "mechanics/cash witness only; not rival-order prediction or policy authority",
            "benefit requires same-item SELL units active in the same executable market slot",
            "sequential_market_only is not a next-callback simulation; interpreter phases are intentionally omitted",
            "a real later-callback comparison requires full interpreter replay with town/decay/EOD/unit phases",
            "quantities are capped to default shed capacity for physical executability",
            "current-route/replay incidence and both-seat economics are separate gates",
        ],
    }


def collision_curve(engine, *, item: str, inventories: list[int], quantity: int = 1) -> list[dict[str, Any]]:
    quantity = _plain_int(quantity, "quantity", minimum=1, maximum=CONFIG["shedCapacity"])
    rows = []
    for inventory in inventories:
        inventory = _plain_int(inventory, "inventory", minimum=0)
        row = compare(engine, item=item, inventory=inventory, self_qty=quantity, rival_qty=quantity)
        rows.append({
            "inventory": inventory,
            "simultaneous_gain_vs_sequential_market_only": row["simultaneous_gain_vs_sequential_market_only"],
            "simultaneous_self_revenue": row["simultaneous_self_revenue"],
            "sequential_market_only_self_revenue": row["sequential_market_only_self_revenue"],
        })
    return rows


def default_engine_path() -> Path:
    here = Path(__file__).resolve()
    if len(here.parents) > 4:
        return here.parents[4] / "reference" / "engine" / "kaggriculture.py"
    # Keeps dependency-light source tests runnable outside a full checkout.
    # The exact-engine test will SKIP unless this fallback happens to exist.
    return here.parent / "reference" / "engine" / "kaggriculture.py"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", type=Path, default=default_engine_path())
    ap.add_argument("--item", default="WOOL")
    ap.add_argument("--inventory", type=int, default=10_000)
    ap.add_argument("--self-qty", type=int, default=10)
    ap.add_argument("--rival-qty", type=int, default=10)
    ns = ap.parse_args(argv)
    engine = load_engine(ns.engine)
    print(json.dumps(compare(engine, item=ns.item, inventory=ns.inventory,
                             self_qty=ns.self_qty, rival_qty=ns.rival_qty),
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
