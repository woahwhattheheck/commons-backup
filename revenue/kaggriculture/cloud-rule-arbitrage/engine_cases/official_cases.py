# SPDX-License-Identifier: Apache-2.0
"""Discriminating legal market cases using the unmodified pinned interpreter.

Rival orders/private inventories below are evaluator fixtures only. Runtime
liquidity_cycle.py never imports this module or accepts those inputs.
"""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def load_engine(directory):
    path = ROOT / "revenue/kaggriculture/cloud-eval/evaluate.py"
    spec = importlib.util.spec_from_file_location("t11_official_evaluator", path)
    ev = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = ev
    spec.loader.exec_module(ev)
    engine, hashes = ev.get_engine(directory)
    return ev, engine, hashes


def run_market(ev, engine, *, inventory=10000, item="WHEAT", own_orders=(),
               rival_orders=(), own_cash=1000, rival_cash=1000,
               own_shed=None, rival_shed=None, seat=0, capacity=100,
               consumption_step=None, shops=(), after_consumption_orders=()):
    cfg = ev.Struct({k: v.get("default") if isinstance(v, dict) else v
                     for k, v in engine.specification["configuration"].items()})
    cfg.seed, cfg.shedCapacity = 0, capacity
    env = ev.Struct(configuration=cfg, done=False, info={})
    state = [ev.Struct(observation=ev.Struct(), action={}, status="ACTIVE", reward=0)
             for _ in range(2)]
    engine.interpreter(state, env)
    farms, market = state[0].observation.farms, state[0].observation.market
    farms[seat]["money"], farms[1-seat]["money"] = own_cash, rival_cash
    state[seat].observation.private["shed"] = dict(own_shed or {})
    state[1-seat].observation.private["shed"] = dict(rival_shed or {})
    market["inventory"][item] = inventory
    engine._refresh_prices(market)
    state[seat].action = {"market": copy.deepcopy(list(own_orders))}
    state[1-seat].action = {"market": copy.deepcopy(list(rival_orders))}
    before = copy.deepcopy(state[seat].observation)
    receipts = [[], []]
    original = engine._commit_unit
    def commit(op, product, price, farm, private, market, shed_capacity=100):
        who = next(i for i, f in enumerate(farms) if f is farm)
        ok = original(op, product, price, farm, private, market, shed_capacity)
        if ok:
            receipts[who].append([op, product, price])
        return ok
    engine._commit_unit = commit
    try:
        engine._process_market(state, env)
        if consumption_step is not None:
            state[0].observation.town['unlocked_shops']=list(shops)
            engine._town_consume(env,state,consumption_step)
            state[seat].action={'market':copy.deepcopy(list(after_consumption_orders))}
            state[1-seat].action={'market':[]}
            engine._process_market(state,env)
    finally:
        engine._commit_unit = original
    return {"cash": [farms[seat]["money"], farms[1-seat]["money"]],
            "shed": [dict(state[seat].observation.private["shed"]),
                     dict(state[1-seat].observation.private["shed"])],
            "market": copy.deepcopy(market["inventory"]),
            "receipts": [receipts[seat], receipts[1-seat]], "before": before,
            "configuration": dict(cfg)}


def paired(ev, engine, **kw):
    actual = run_market(ev, engine, **kw)
    control = run_market(ev, engine, **dict(kw, own_orders=[]))
    delta = [actual["cash"][i]-control["cash"][i] for i in (0, 1)]
    return {"input": kw, "actual": actual, "control": control,
            "cash_delta": delta, "margin_delta": delta[0]-delta[1]}


def evidence(ev, engine):
    rows = []
    cycle = [["SELL", "WHEAT", 1], ["BUY_PRODUCT", "WHEAT", 1]]
    flows = {"solo": [], "sell": [["SELL", "WHEAT", 1]],
             "buy": [["BUY_PRODUCT", "WHEAT", 1]],
             "sell_buy": [["SELL", "WHEAT", 1], ["BUY_PRODUCT", "WHEAT", 1]],
             "fund_elsewhere_buy": [["SELL", "MILK", 1], ["BUY_PRODUCT", "WHEAT", 1]],
             "sell_both": [["SELL", "WHEAT", 1], ["SELL", "WHEAT", 1]]}
    for seat in (0, 1):
        for inventory in (10000, 10002, 10100):
            for name, rival in flows.items():
                row = paired(ev, engine, inventory=inventory, seat=seat,
                             own_orders=cycle, rival_orders=rival,
                             own_shed={"WHEAT": 1}, rival_shed={"WHEAT": 2, "MILK": 1},
                             own_cash=1000, rival_cash=0 if name == "fund_elsewhere_buy" else 1000)
                row["name"] = f"{name}:{inventory}:seat{seat}"
                rows.append(row)
    # Exact floor boundary and clipping are tested at zero/partial/full capacity.
    for inventory in (10492, 10493, 10494, 10593, 11000):
        for cash, fullness in ((0, 0), (3, 0), (100, 0), (100, 100)):
            row = paired(ev, engine, item="FERTILIZER", inventory=inventory,
                         own_orders=[["BUY_PRODUCT", "FERTILIZER", 100], ["SELL", "FERTILIZER", 100]],
                         own_shed={"MILK": fullness}, own_cash=cash)
            row["name"] = f"fert_floor:{inventory}:cash{cash}:shed{fullness}"
            rows.append(row)
    for q in (1, 2, 3, 5, 10, 25, 50, 100):
        for rival_q in (0, 1, 2, 5, 25, 100):
            for op in ("SELL", "BUY_PRODUCT"):
                row = paired(ev, engine, own_cash=100000, rival_cash=100000,
                             own_shed={"WHEAT": q}, rival_shed={"WHEAT": rival_q} if op=='SELL' else {},
                             own_orders=[["SELL", "WHEAT", q], ["BUY_PRODUCT", "WHEAT", q]],
                             rival_orders=[[op, "WHEAT", rival_q]])
                row["name"] = f"quantity:q{q}:rival{op}{rival_q}"
                rows.append(row)
    for rival_orders in ([['SELL', 'FERTILIZER', 100]],
                         [['BUY_PRODUCT', 'FERTILIZER', 100]],
                         [['SELL', 'FERTILIZER', 100], ['BUY_PRODUCT', 'FERTILIZER', 100]],
                         [['BUY_PRODUCT', 'FERTILIZER', 100], ['SELL', 'FERTILIZER', 100]]):
        row = paired(ev, engine, inventory=10500, item="FERTILIZER",
                     own_orders=[["BUY_PRODUCT", "FERTILIZER", 100], ["SELL", "FERTILIZER", 100]],
                     own_cash=10000, rival_cash=10000, rival_orders=rival_orders,
                     rival_shed={"FERTILIZER": 100} if rival_orders[0][0] == "SELL" else {})
        row["name"] = "fert_paired:" + repr(rival_orders)
        rows.append(row)
    for rival_quantity in (0,5):
        row=paired(ev,engine,own_orders=[['BUY_PRODUCT','WHEAT',1]],
                   rival_orders=[['SELL','WHEAT',rival_quantity]],rival_shed={'WHEAT':rival_quantity},
                   consumption_step=12,shops=['BAKERY']*4,
                   after_consumption_orders=[['SELL','WHEAT',1]])
        row['name']=f'temporal_consumption:rival_sell{rival_quantity}'
        rows.append(row)
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--engine-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    ev, engine, hashes = load_engine(a.engine_dir)
    rows = evidence(ev, engine)
    output = {"engine_ref": ev.ENGINE_REF, "engine_sha256": hashes,
              "source_sha256": ev.sha256(__file__), "cases": rows}
    a.output.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({"cases": len(rows), "output": str(a.output)}))


if __name__ == "__main__":
    main()
