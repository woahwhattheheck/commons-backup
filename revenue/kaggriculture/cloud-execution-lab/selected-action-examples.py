#!/usr/bin/env python3
"""Run small selected-action examples, printing exact current-phase receipts.

No game/panel is run. The rival is explicitly PASS in every market example.
The caller supplies selected actions and projections; no parent is constructed.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from time import perf_counter

from selected_action_sell import SelectedActionSell
import test_engine_semantics as semantics
from test_selected_action_sell import capacity_contract, projection, retained_669, selected

HERE = Path(__file__).resolve().parent


def market_receipt(obs, cfg, action, post_shed, engine, Struct):
    """Execute only official market against declared PASS after caller projection."""
    farms = copy.deepcopy(obs["farms"])
    market = copy.deepcopy(obs["market"])
    seat = obs["player"]
    initial = farms[seat]["money"]
    state = []
    for player in range(2):
        observation = copy.deepcopy(obs)
        observation["farms"] = farms
        observation["market"] = market
        observation["player"] = player
        observation["private"] = (copy.deepcopy(obs["private"]) if player == seat
                                  else engine._new_private())
        if player == seat:
            observation["private"]["shed"] = copy.deepcopy(post_shed)
        state.append(Struct(observation=Struct(observation),
                            action=copy.deepcopy(action) if player == seat else selected(),
                            status="ACTIVE", reward=0))
    env = Struct(configuration=Struct(dict(cfg)), done=False, info={})
    engine._process_market(state, env)
    final = state[seat].observation.farms[seat]["money"]
    return {"official_market_cash_delta": final - initial,
            "rival_action": "PASS", "only_sell_orders": True,
            "shed_after_market": {k: v for k, v in state[seat].observation.private["shed"].items() if v}}


def main():
    semantics.EngineSemantics.setUpClass()
    helper = semantics.EngineSemantics()
    rows = []
    for phase in ("before_market", "after_market"):
        state, env = helper.fixture(stock=(12, 0), step=4, cash=10000,
                                    inventory=10030, shops=["SMOOTHIE_SHOP"] * 4)
        obs = state[0].observation
        obs.private["shed"]["WHEAT"] = 88
        base = selected([["SELL", "MILK", 12]])
        shed = dict(obs.private["shed"])
        contract = capacity_contract(4, 5, phase, pending=10, total=10, incremental=2)
        tx = SelectedActionSell()
        started = perf_counter()
        output = tx.transform(obs, env.configuration, base, post_unit_shed=shed,
            projection=projection(4, 5), arrival_contract=contract)
        elapsed = perf_counter() - started
        rows.append({"example": "committed_whole_lot_" + phase,
                     "pending_capacity_units": 10, "incremental_units": 2,
                     "pending_units_are_saleable_stock": False,
                     "transform_seconds": elapsed,
                     "selected_action": base, "transformed_action": output,
                     **market_receipt(obs, env.configuration, output, shed,
                                      helper.engine, helper.ev.Struct),
                     "diagnostics": tx.diagnostics})
    obs, cfg, base, projected, contract = retained_669()
    tx = SelectedActionSell()
    shed = dict(obs["private"]["shed"])
    started = perf_counter()
    output = tx.transform(obs, cfg, base, post_unit_shed=shed,
                          projection=projected, arrival_contract=contract)
    elapsed = perf_counter() - started
    rows.append({"example": "retained_development669_committed_only",
                 "source_frame": "reference/selected-action/claude/envelope-binding-case-669.json",
                 "projection_scope": "Current observed carried79 at671 after market; committed pendingEGG4 only.",
                 "projection_is_full_future_producer_replay": False,
                 "transform_seconds": elapsed,
                 "selected_action": base, "transformed_action": output,
                 **market_receipt(obs, cfg, output, shed, helper.engine, helper.ev.Struct),
                 "diagnostics": tx.diagnostics})
    fallback = selected()
    started = perf_counter()
    output = SelectedActionSell().transform({"step": 4}, {},
                     selected([["SELL", "MILK", 12]]), fallback_action=fallback)
    elapsed = perf_counter() - started
    rows.append({"example": "caller_fallback_without_projection",
                 "transform_seconds": elapsed,
                 "supplied_fallback": fallback, "transformed_action": output})
    print(json.dumps({"kind": "focused_selected_action_examples", "games": 0,
        "timing_scope": "Transform calls only; imports and official evaluator initialization excluded.",
        "max_transform_seconds": max(row["transform_seconds"] for row in rows),
        "source_sha256": {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                          for name in ("selected_action_sell.py", "selected_sell_core.py")},
        "engine_sha256": helper.hashes, "rows": rows}, indent=2))


if __name__ == "__main__":
    main()
