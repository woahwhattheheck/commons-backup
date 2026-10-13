"""TITAN V4 research: exact-engine sale timing, not a production policy.

Use: python lockstep_scale.py --engine /path/to/kaggriculture.py --output results.json
The engine is Git-blob pinned. Only its unmodified function definitions and
uppercase constants are executed; package imports/spec loading are not needed.
This isolates real _process_market/_commit_unit behavior, NOT a full episode.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import random
from os import path as os_path
from pathlib import Path
from types import SimpleNamespace

ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
CAPACITY = 100
QUANTITIES = (1, 10, 50, 100, 500, 1000, 2000)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def load_engine(filename: str | Path) -> SimpleNamespace:
    data = Path(filename).read_bytes()
    actual = git_blob(data)
    if actual != ENGINE_BLOB:
        raise ValueError(f"Engine pin mismatch: {actual} != {ENGINE_BLOB}")
    parsed = ast.parse(data, filename=str(filename))
    selected = []
    for node in parsed.body:
        if isinstance(node, ast.FunctionDef):
            selected.append(node)
        elif isinstance(node, ast.Assign) and all(
            isinstance(t, ast.Name) and t.id.isupper() for t in node.targets
        ):
            selected.append(node)
    namespace = {"math": math, "random": random, "json": json,
                 "path": os_path, "__file__": str(filename)}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(filename), "exec"), namespace)
    return SimpleNamespace(**namespace)


def _integer(value: int, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in [{low}, {high}]")
    return value


def make_state(engine, item: str, inventory: int, held: tuple[int, int]):
    if item not in engine.PRODUCTS:
        raise ValueError(f"Unknown product {item!r}")
    _integer(inventory, "inventory", -(10 ** 15), 10 ** 15)
    if len(held) != 2:
        raise ValueError("Exactly two seats required")
    for n in held:
        _integer(n, "held", 0, 5000)
    farms = [engine._new_farm(10, 0) for _ in range(2)]
    market = engine._new_market()
    market["inventory"][item] = inventory
    engine._refresh_prices(market)
    town = engine._new_town()
    states = []
    for seat in range(2):
        private = engine._new_private()
        private["shed"][item] = held[seat]
        obs = SimpleNamespace(farms=farms, market=market, town=town,
                              private=private, player=seat)
        states.append(SimpleNamespace(observation=obs, action={}))
    env = SimpleNamespace(configuration={"shedCapacity": CAPACITY,
                                         "maxMarketOrdersPerTurn": 10})
    return states, env


def execute(engine, item: str, inventory: int, held: tuple[int, int],
            rows: tuple[list, list], town_steps: tuple[int, ...] = (),
            shops: tuple[str, ...] = ()) -> dict:
    """Execute real market commits. PASS rows retain their raw queue positions."""
    states, env = make_state(engine, item, inventory, held)
    for s, market_rows in zip(states, rows):
        s.action = {"market": market_rows}
    states[0].observation.town["unlocked_shops"] = list(shops)
    engine._process_market(states, env)
    for step in town_steps:
        engine._town_consume(env, states, step)
    return {
        "cash": [int(f["money"]) for f in states[0].observation.farms],
        "sold": [held[i] - states[i].observation.private["shed"][item] for i in range(2)],
        "final_inventory": states[0].observation.market["inventory"][item],
        "final_quote": states[0].observation.market["prices"][item],
    }


def reference(engine, item: str, inventory: int, held: tuple[int, int],
              simultaneous: bool) -> dict:
    """Independent arithmetic traversal: engine.market_price is the price oracle."""
    cash = [0, 0]
    remaining = list(held)
    while any(remaining):
        if simultaneous:
            quote = engine.market_price(item, inventory)
            for seat in range(2):
                if remaining[seat]:
                    cash[seat] += quote
                    remaining[seat] -= 1
                    inventory += int(quote > 1)
        else:
            seat = 0 if remaining[0] else 1
            quote = engine.market_price(item, inventory)
            cash[seat] += quote
            remaining[seat] -= 1
            inventory += int(quote > 1)
    return {"cash": cash, "sold": list(held), "final_inventory": inventory,
            "final_quote": engine.market_price(item, inventory)}


def compare(engine, item: str, inventory: int, quantities: tuple[int, int]) -> dict:
    a, b = quantities
    sell_a, sell_b = ["SELL", item, a], ["SELL", item, b]
    joined = execute(engine, item, inventory, quantities, ([sell_a], [sell_b]))
    first = execute(engine, item, inventory, quantities, ([sell_a], [["PASS"], sell_b]))
    other_first = execute(engine, item, inventory, quantities, ([["PASS"], sell_a], [sell_b]))
    if joined != reference(engine, item, inventory, quantities, True):
        raise RuntimeError("Simultaneous execution differs from arithmetic reference")
    if first != reference(engine, item, inventory, quantities, False):
        raise RuntimeError("Sequential execution differs from arithmetic reference")
    quote = engine.market_price(item, inventory)
    result = {
        "item": item, "inventory": inventory, "initial_quote": quote,
        "quantities": list(quantities),
        "capacity_valid": max(quantities) <= CAPACITY,
        "state_provenance": "constructed microstate; episode reachability not certified",
        "joined": joined, "p0_first": first, "p1_first": other_first,
        "p1_join_vs_follow": joined["cash"][1] - first["cash"][1],
        "p0_join_vs_lead": joined["cash"][0] - first["cash"][0],
        "total_quote_surplus": sum(joined["cash"]) - sum(first["cash"]),
    }
    if a == b:
        if joined["cash"][0] != joined["cash"][1]:
            raise RuntimeError("Equal same-product dumps lost seat symmetry")
        surplus = result["total_quote_surplus"]
        if not 0 <= surplus <= quote - engine.PRICE_FLOOR:
            raise RuntimeError("Equal-dump monotone endpoint surplus bound failed")
        if result["p1_join_vs_follow"] < 0 or result["p0_join_vs_lead"] > 0:
            raise RuntimeError("Monotone pure-sale timing ordering failed")
        if first["cash"] != list(reversed(other_first["cash"])):
            raise RuntimeError("Changing raw order positions failed to exchange advantage")
    return result


def multistep(engine, item: str, inventory: int, quantity: int, chunks: int,
              shops: tuple[str, ...] = ()) -> dict:
    """Capacity-valid repeat arrivals, not a certified production schedule.

    Each chunk begins with an exogenous equal deposit <=100 in both empty sheds.
    Joined schedule sells together at even step. Follow schedule sells p0 at that
    step and p1 at the next. Both consume the SAME town ticks and total arrivals.
    """
    _integer(quantity, "chunk quantity", 1, CAPACITY)
    _integer(chunks, "chunks", 1, 100)
    results = {}
    for schedule in ("joined", "follow"):
        states, env = make_state(engine, item, inventory, (0, 0))
        states[0].observation.town["unlocked_shops"] = list(shops)
        for chunk in range(chunks):
            for state in states:
                if sum(state.observation.private["shed"].values()) != 0:
                    raise RuntimeError("Nonempty shed before synthetic arrival")
                state.observation.private["shed"][item] = quantity
            sell = [["SELL", item, quantity]]
            for offset in range(2):
                for seat in range(2):
                    active = (offset == 0) if schedule == "joined" else (offset == seat)
                    states[seat].action = {"market": sell if active else []}
                engine._process_market(states, env)
                engine._town_consume(env, states, 101 + 2 * chunk + offset)
        results[schedule] = {
            "cash": [int(f["money"]) for f in states[0].observation.farms],
            "final_inventory": states[0].observation.market["inventory"][item],
        }
    return {"item": item, "inventory": inventory, "chunk_quantity": quantity,
            "chunks": chunks, "total_units_per_seat": quantity * chunks,
            "shops": list(shops), "capacity_valid": True,
            "arrivals": "exogenous; no farmer production or full-game EV claim",
            **results,
            "p1_join_vs_follow": results["joined"]["cash"][1] - results["follow"]["cash"][1]}


def build_report(engine) -> dict:
    cases = []
    for item in engine.PRODUCTS:
        param = engine.MARKET_PARAMS[item]
        for offset in (-5 * param["T"], -param["T"], -100, 0, param["T"], 5 * param["T"]):
            for quantity in QUANTITIES:
                cases.append(compare(engine, item, param["I0"] + offset, (quantity, quantity)))
        for a, b in ((10, 100), (100, 10), (50, 100), (100, 50)):
            cases.append(compare(engine, item, param["I0"] - 100, (a, b)))
    wheat = [compare(engine, "WHEAT", 9900, (q, q)) for q in QUANTITIES]
    repeated = [multistep(engine, item, 9900, 100, chunks, shops)
                for item in ("WHEAT", "TOMATO", "MILK")
                for chunks in (1, 10, 20)
                for shops in ((), ("FARMERS_MARKET",) * 4)]
    capped = execute(engine, "WHEAT", 9900, (100, 100),
                     ([["SELL", "WHEAT", 2000]], [["SELL", "WHEAT", 2000]]))
    if capped["sold"] != [100, 100]:
        raise RuntimeError("Oversized request violated shed stock bound")
    return {
        "schema": "titan-v4-lockstep-scale-v1", "engine_blob": ENGINE_BLOB,
        "engine_execution": "unmodified AST-selected constants/functions; real _process_market/_commit_unit",
        "scope": "deterministic microeconomics; not a full-episode strength gate",
        "case_count": len(cases), "cases": cases, "wheat_9900_scale": wheat,
        "hunt2_reproduction": compare(engine, "WHEAT", 9899, (50, 50)),
        "repeated_arrivals": repeated, "oversized_request_with_legal_stock": capped,
        "equal_dump_bound": "0 <= total_quote_surplus <= initial_quote - PRICE_FLOOR",
        "promotion": "OFF; no runtime imports, feature flags, or archive changes",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(load_engine(args.engine))
    data = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
    args.output.write_bytes(data)
    print(json.dumps({"case_count": report["case_count"],
                      "repeated_count": len(report["repeated_arrivals"]),
                      "sha256": hashlib.sha256(data).hexdigest()}, sort_keys=True))


if __name__ == "__main__":
    main()
