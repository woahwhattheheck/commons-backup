# SPDX-License-Identifier: Apache-2.0
"""Independent event/lot evidence for the ONE V4 tomato-window research lane.

Executes source-pinned engine functions, not a second forecast implementation.
Constructed states and shop masks are mechanisms, not played games or game EV.
"""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import hashlib
import itertools
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
ARTIFACT_ID = 10285621024


def load_engine(path):
    """Verify source bytes; retain every engine function body unmodified.

    Only the unused Kaggle framework import and top-level specification/renderer
    I/O are omitted. No market, commit, consumption or EOD function is stubbed.
    """
    path = Path(path)
    raw = path.read_bytes()
    sha = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
    if sha != ENGINE_GIT_BLOB:
        raise ValueError(f"engine blob mismatch: {sha}")
    tree = ast.parse(raw, filename=str(path))
    tree.body = [node for node in tree.body
                 if isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.FunctionDef))
                 and not (isinstance(node, ast.ImportFrom)
                          and node.module == "kaggle_environments.utils")]
    module = ModuleType("pinned_kaggriculture")
    module.__file__ = str(path)
    exec(compile(tree, str(path), "exec"), module.__dict__)
    return module


def state_for(engine, shops=(), inventory=10000, quantity=0, configuration=None):
    market = engine._new_market()
    market["inventory"]["TOMATO"] = inventory
    engine._refresh_prices(market)
    farms = [engine._new_farm(10, 3000) for _ in range(2)]
    town = {"unlocked_shops": list(shops)}
    state = []
    for player in range(2):
        private = engine._new_private()
        private["shed"]["TOMATO"] = quantity if player == 0 else 0
        obs = SimpleNamespace(step=0, market=market, town=town, farms=farms,
                              private=private, player=player)
        state.append(SimpleNamespace(observation=obs, action={"market": []},
                                     status="ACTIVE", reward=0))
    cfg = {"episodeSteps": 720}
    cfg.update(configuration or {})
    return state, SimpleNamespace(configuration=SimpleNamespace(**cfg), info={"seed": 0}, done=False)


def natural_snapshot(engine, mask, stop=718):
    """Enumerate possible tomato/non-tomato schedules, not RNG probabilities.

    First eight unlocks occur AFTER consumption at steps71,143,...575. A newly
    unlocked shop first consumes on steps72,144,...576. The companion suite
    checks this schedule against actual _end_of_day/interpreter execution.
    """
    if len(mask) != 8 or any(type(x) is not bool for x in mask):
        raise ValueError("mask must contain exactly eight booleans")
    if type(stop) is not int or not 0 <= stop <= 718:
        raise ValueError("stop must be a valid default-engine sale step")
    state, env = state_for(engine)
    for step in range(stop):
        engine._town_consume(env, state, step)
        if (step + 1) % 72 == 0 and len(state[0].observation.town["unlocked_shops"]) < 8:
            i = len(state[0].observation.town["unlocked_shops"])
            state[0].observation.town["unlocked_shops"].append("FARMERS_MARKET" if mask[i] else "YARN_STORE")
    state[0].observation.step = stop
    state[1].observation.step = stop
    return state, env


def execute_sale(engine, state, env, quantity, extra=0, seat=0):
    """Execute real market commits; reconcile against real per-unit engine quotes.

    `extra` is constructed additional inventory supply, not a hidden-stock
    estimate. It is placed BEFORE this lot. Other actor's actions are cleared.
    """
    if type(quantity) is not int or not 1 <= quantity <= 99999:
        raise ValueError("quantity must be a positive engine-sized integer")
    if type(extra) is not int or extra < 0 or type(seat) is not int or seat not in (0, 1):
        raise ValueError("invalid extra supply or seat")
    s = deepcopy(state)
    market = s[0].observation.market
    market["inventory"]["TOMATO"] += extra
    start = market["inventory"]["TOMATO"]
    prices = []
    expected_inventory = start
    for _ in range(quantity):
        price = engine.market_price("TOMATO", expected_inventory, market.get("params"))
        prices.append(price)
        if price > 1:
            expected_inventory += 1
    for row in s:
        row.action = {"market": []}
    s[seat].observation.private["shed"]["TOMATO"] = quantity
    s[seat].action = {"market": [["SELL", "TOMATO", quantity]]}
    before = s[0].observation.farms[seat]["money"]
    engine._process_market(s, env)
    revenue = s[0].observation.farms[seat]["money"] - before
    after = market["inventory"]["TOMATO"]
    remaining = s[seat].observation.private["shed"]["TOMATO"]
    if revenue != sum(prices) or after != expected_inventory or remaining != 0:
        raise AssertionError({"actual": (revenue, after, remaining),
                              "expected": (sum(prices), expected_inventory, 0)})
    return dict(first_quote=prices[0], minimum_unit_quote=min(prices),
                total_revenue=revenue, inventory_before=start, inventory_after=after,
                filled_units=quantity, spot_times_quantity_overstatement=prices[0] * quantity - revenue)


def run_probe(engine):
    rows = []
    for n in range(9):
        state, env = natural_snapshot(engine, [True] * n + [False] * (8 - n))
        inventory = state[0].observation.market["inventory"]["TOMATO"]
        rows.append(dict(earliest_tomato_shops=n, terminal_inventory=inventory,
                         final_executable_quote=engine.market_price("TOMATO", inventory),
                         lot_25=execute_sale(engine, state, env, 25)))
    static, env = state_for(engine, ["FARMERS_MARKET"] * 4)
    first_spot = first_lot = None
    for step in range(719):
        lot = execute_sale(engine, static, env, 25)
        if first_spot is None and lot["first_quote"] >= 1470:
            first_spot = step
        if first_lot is None and lot["minimum_unit_quote"] >= 1470:
            first_lot = dict(step=step, **lot)
        if step < 718:
            engine._town_consume(env, static, step)
    cases = []
    for budget in (0, 25, 100, 200):
        spot_hits = lot_hits = 0
        for mask in itertools.product((False, True), repeat=8):
            state, env = natural_snapshot(engine, mask)
            lot = execute_sale(engine, state, env, 25, budget)
            spot_hits += lot["first_quote"] >= 1470
            lot_hits += lot["minimum_unit_quote"] >= 1470
        cases.append(dict(additional_supply_budget=budget, schedules=256,
                          spot_at_least_1470=spot_hits, all_25_units_at_least_1470=lot_hits))
    return dict(engine_git_blob=ENGINE_GIT_BLOB, source_artifact_id=ARTIFACT_ID,
                evidence_class="constructed_exact_engine_mechanism_not_game_strength",
                production_activation=False, canonical_research_lane="tomato-window",
                exhaustive_mask_liquidations=1024,
                static_four_shops_first_spot_1470=first_spot,
                static_four_shops_first_lot_25_minimum_1470=first_lot,
                static_four_shops_final_quote=static[0].observation.market["prices"]["TOMATO"],
                natural_unlocks_by_earliest_shop_count=rows,
                exhaustive_natural_shop_masks=cases,
                assumptions=["No tomato sales before the measured snapshot, except stated added-supply budget.",
                             "Natural unlocks first consume at steps72,144,...576; market precedes consumption.",
                             "All extra supply is placed before liquidation; no rival liquidation is inferred.",
                             "256 masks are not equally likely and are not a played-game/seed sample.",
                             "Static four shops at step0 are a counterfactual, not a default-engine history.",
                             "25-unit shed lots are constructed; growing, delivery, capital and routes are unproven.",
                             "No runtime configuration, action policy, production archive or submission changed."])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_probe(load_engine(args.engine))
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
