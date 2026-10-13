#!/usr/bin/env python3
"""Replay exact pinned market functions for BUY_PRODUCT stock semantics.

Only the BUY_PRODUCT/SELL market closure is loaded. No copied pricing formula,
mocked market implementation, episode initialization, or whole-game claim.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import itertools
import json
import math
from pathlib import Path
from types import SimpleNamespace

ENGINE_GIT = "3c202c7ee921da239356789e266b694635103fc4"
CONSTANTS = {"CROPS", "ANIMALS", "PRODUCTS", "MARKET_I0", "PRICE_FLOOR",
             "MARKET_PARAMS", "HINGE_GAIN", "FARM_HAND_COST_MULT"}
FUNCTIONS = {"_shape", "market_price", "get", "_process_market", "_parse_order",
             "_commit_unit", "_refresh_prices"}
CONFIG = {"boardSize": 10, "maxMarketOrdersPerTurn": 10,
          "farmHandCostMult": 1, "shedCapacity": 100}


def require(value, message):
    if not value:
        raise AssertionError(message)


def load_market(engine_path):
    source = engine_path.read_bytes()
    digest = hashlib.sha1(b"blob " + str(len(source)).encode() + b"\0" + source).hexdigest()
    require(digest == ENGINE_GIT, "unexpected engine source")
    tree = ast.parse(source, filename=str(engine_path))
    body = []
    found = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS:
            body.append(node)
            found.add(node.name)
        elif isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) for t in node.targets):
            names = {target.id for target in node.targets}
            if names <= CONSTANTS:
                body.append(node)
                found.update(names)
    require(found == CONSTANTS | FUNCTIONS, "incomplete exact market closure")
    namespace = {"math": math}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(engine_path), "exec"), namespace)
    return namespace


def run_orders(engine, product, inventory, orders, money=(100000.0, 100000.0), stock=(0, 0)):
    farms = [{"money": amount} for amount in money]
    privates = [{"shed": {product: count}, "seeds": {}} for count in stock]
    market = {"inventory": {p: 10000 for p in engine["PRODUCTS"]}, "params": None, "prices": {}}
    market["inventory"][product] = inventory
    state = [SimpleNamespace(
        observation=SimpleNamespace(market=market, farms=farms, private=privates[seat]),
        action={"market": copy.deepcopy(orders[seat])}) for seat in (0, 1)]
    engine["_process_market"](state, SimpleNamespace(configuration=dict(CONFIG)))
    return farms, privates, market


def verify(engine_path):
    engine = load_market(engine_path)
    tested = 0
    negative_endings = 0
    digest = hashlib.sha256()
    # Both players buy simultaneously at the same raw order index. Quotes for
    # both seats must use the shared pre-commit inventory for each unit round.
    for product, inventory, q0, q1 in itertools.product(
            ("WHEAT", "FERTILIZER"), (-10, 0, 1, 10000), (1, 2), (1, 2)):
        orders = [[["BUY_PRODUCT", product, q0]], [["BUY_PRODUCT", product, q1]]]
        farms, privates, market = run_orders(engine, product, inventory, orders)
        require([p["shed"][product] for p in privates] == [q0, q1], "stock blocked a legal buy")
        require(market["inventory"][product] == inventory - q0 - q1, "public ledger drift")
        expected_cash = [100000.0, 100000.0]
        expected_inventory = inventory
        for unit in range(max(q0, q1)):
            quote = engine["market_price"](product, expected_inventory - 1, None)
            for seat, quantity in enumerate((q0, q1)):
                if unit < quantity:
                    expected_cash[seat] -= quote
                    expected_inventory -= 1
        require([f["money"] for f in farms] == expected_cash, "lockstep quoted cash drift")
        negative_endings += market["inventory"][product] < 0
        tested += 1
        digest.update(json.dumps([product, inventory, q0, q1, farms, privates, market],
                                 sort_keys=True, separators=(",", ":")).encode())
        digest.update(b"\n")

    constraints = 0
    for product, seat in itertools.product(("WHEAT", "FERTILIZER"), (0, 1)):
        quote = engine["market_price"](product, -1, None)
        orders = [[], []]
        orders[seat] = [["BUY_PRODUCT", product, 2]]
        # Insufficient cash prevents the first unit, independent of stock.
        cash = [100000.0, 100000.0]
        cash[seat] = quote - 1
        farms, privates, market = run_orders(engine, product, 0, orders, money=tuple(cash))
        require(privates[seat]["shed"][product] == 0 and market["inventory"][product] == 0,
                "insufficient-cash gate bypassed")
        constraints += 1
        # Total private shed capacity is the physical constraint.
        stock = [0, 0]
        stock[seat] = 99
        farms, privates, market = run_orders(engine, product, 0, orders, stock=tuple(stock))
        require(privates[seat]["shed"][product] == 100 and market["inventory"][product] == -1,
                "capacity did not truncate the second unit")
        constraints += 1
        # Raw prefix semantics: empty rows consume indices; row eleven is dead.
        orders[seat] = [[] for _ in range(10)] + [["BUY_PRODUCT", product, 2]]
        farms, privates, market = run_orders(engine, product, 0, orders)
        require(privates[seat]["shed"][product] == 0 and market["inventory"][product] == 0,
                "dead eleventh row executed")
        constraints += 1
    return {"status": "PASS", "scope": "exact_pinned_BUY_PRODUCT_market_closure_only",
            "engine_git_blob": ENGINE_GIT, "simultaneous_buy_cases": tested,
            "cases_ending_with_negative_public_inventory": negative_endings,
            "cash_capacity_raw_prefix_cases": constraints,
            "products": ["WHEAT", "FERTILIZER"], "both_seats": True,
            "trace_sha256": digest.hexdigest(),
            "conclusion": "public inventory is not a finite stock admission gate for BUY_PRODUCT"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    require(args.out.resolve() not in {args.engine.resolve(), Path(__file__).resolve()},
            "output aliases source")
    result = verify(args.engine)
    result["verifier_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
