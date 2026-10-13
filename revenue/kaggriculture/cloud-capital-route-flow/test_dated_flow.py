# SPDX-License-Identifier: Apache-2.0
"""Conditional-market comparisons against the existing unmodified engine.

Usage: python test_dated_flow.py --engine-dir DIR --loader PATH --report result.json
The three cached engine files must already exist; this test never downloads.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys
import time
from types import SimpleNamespace
import unittest

from dated_flow import (Scenario, value_route, evaluate_scenarios, as_cash_scenarios,
                        BudgetExceeded)

ENGINE = LOADER = None
RECEIPTS = []


def offer(route_id, queues, fixed=None):
    fixed = fixed or {}
    return SimpleNamespace(route_id=route_id, orders=tuple(
        {"step": step, "slot": slot, "order": list(order),
         "delta": fixed.get((step, slot), 0)}
        for step, queue in queues.items() for slot, order in enumerate(queue)))


def initial(now=1, end=18, shops=(), seat=0, inventory=None, money=1_000_000, config=None):
    cfg = LOADER.Struct({k: v.get("default") if isinstance(v, dict) else v
                         for k, v in ENGINE.specification["configuration"].items()})
    cfg.update(config or {})
    cfg.update(seed=71, episodeSteps=end + 2, startingMoney=money, shedCapacity=1_000_000)
    env = LOADER.Struct(configuration=cfg, done=False, info={})
    state = [LOADER.Struct(observation=LOADER.Struct(), action={}, status="ACTIVE", reward=0)
             for _ in range(2)]
    ENGINE.interpreter(state, env)
    for actor in state:
        actor.observation.step = now
        # Explicit synthetic stock guarantees the conditional test queues fill.
        actor.observation.private["shed"] = {p: 1000 for p in ENGINE.PRODUCTS}
    state[0].observation.town["unlocked_shops"] = list(shops)
    if inventory:
        state[0].observation.market["inventory"].update(inventory)
    ENGINE._refresh_prices(state[0].observation.market)
    return copy.deepcopy(state[seat].observation), cfg, state, env


def reference(state, env, ours, scenario, seat=0):
    state, env = copy.deepcopy((state, env))
    obs = state[seat].observation
    now, end = obs.step, env.configuration.episodeSteps-2
    start = [f["money"] for f in obs.farms]
    minimum = start[seat]
    rows = {}
    for row in ours.orders:
        rows.setdefault(row["step"], {})[row["slot"]] = row["order"]
    for step in range(now, end+1):
        obs.town["unlocked_shops"].extend(scenario.shop_additions.get(step, ()))
        q = rows.get(step, {})
        queue = [q.get(i, ["PASS"]) for i in range(max(q, default=-1)+1)]
        state[seat].action = {"market": queue}
        state[1-seat].action = {"market": copy.deepcopy(scenario.rival_orders.get(step, []))}
        ENGINE._process_market(state, env)
        minimum = min(minimum, obs.farms[seat]["money"])
        ENGINE._town_consume(env, state, step)
    return {"own": obs.farms[seat]["money"],
            "rival_net": obs.farms[1-seat]["money"]-start[1-seat],
            "inventory": copy.deepcopy(obs.market["inventory"])}


class FlowTests(unittest.TestCase):
    def compare(self, ours, scenario=Scenario("none"), **kwargs):
        obs, cfg, state, env = initial(**kwargs)
        before = copy.deepcopy((obs, cfg, ours, scenario))
        got = value_route(ours, obs, cfg, ENGINE, scenario, retain_trace=True)
        want = reference(state, env, ours, scenario, kwargs.get("seat", 0))
        self.assertEqual(got["final_marked_cash"], want["own"])
        self.assertEqual(got["rival_receipts"]-got["rival_product_spend"], want["rival_net"])
        self.assertEqual(got["final_market_inventory"], want["inventory"])
        self.assertEqual((obs, cfg, ours, scenario), before)
        RECEIPTS.append({"name": self.id(), "seat": kwargs.get("seat", 0),
                         "conditional": got, "official_market": want})
        return got

    def test_dated_sale_self_supply(self):
        out = self.compare(offer("wool", {2:[["SELL","WOOL",30]], 5:[["SELL","WOOL",30]]}))
        self.assertLess(out["cash_flow_rows"][1]["total_own_cash_delta"],
                        out["cash_flow_rows"][0]["total_own_cash_delta"])

    def test_lockstep_identical_product_both_seats(self):
        for seat in (0,1):
            self.compare(offer("same", {2:[["SELL","WOOL",4]]}),
                         Scenario("same", {2:[["SELL","WOOL",7]]}), seat=seat)

    def test_buy_sell_postbuy_both_seats(self):
        for seat in (0,1):
            self.compare(offer("buy", {2:[["BUY_PRODUCT","WHEAT",7], ["SELL","WHEAT",7]]}),
                         Scenario("buy", {2:[["SELL","WHEAT",5],["BUY_PRODUCT","WHEAT",4]]}), seat=seat)

    def test_slot_alignment_not_compacted(self):
        self.compare(offer("slots", {2:[["PASS"],["SELL","WOOL",6],["SELL","EGG",5]]}),
                     Scenario("slots", {2:[["SELL","WOOL",7],["PASS"],["SELL","EGG",6]]}))

    def test_floor_nonadmission(self):
        got = self.compare(offer("floor", {2:[["SELL","WOOL",20]]}), end=2,
                           inventory={"WOOL":100_000})
        self.assertEqual(got["own_receipts"],20)
        self.assertEqual(got["final_market_inventory"]["WOOL"],100_000)

    def test_duplicate_shops_and_after_trade(self):
        for shops in ((), ("YARN_STORE",), ("YARN_STORE","YARN_STORE")):
            self.compare(offer("shops",{4:[["SELL","WOOL",9]],5:[["SELL","WOOL",9]]}),
                         shops=shops)

    def test_explicit_future_shop_and_absence(self):
        ours = offer("dated",{5:[["SELL","WOOL",8]],12:[["SELL","WOOL",8]]})
        a = self.compare(ours)
        b = self.compare(ours,Scenario("later_yarn",shop_additions={8:["YARN_STORE"]}))
        self.assertGreaterEqual(b["own_receipts"],a["own_receipts"])

    def test_center_and_negative_inventory(self):
        self.compare(offer("center",{24:[["SELL","EGG",4]],25:[["SELL","EGG",4]]}),
                     now=23,end=26,inventory={"EGG":-4})

    def test_custom_intervals_and_prices(self):
        self.compare(offer("params",{2:[["SELL","WOOL",7]],3:[["BUY_PRODUCT","FERTILIZER",4]]}),
                     shops=("YARN_STORE",),
                     config={"townShopSellInterval":2,"townCenterSellInterval":3,
                             "marketParams":{"WOOL":{"base":160,"above_target":0.9}}})

    def test_final_executable_turn(self):
        self.compare(offer("terminal",{718:[["SELL","MILK",9]]}),now=718,end=718)
        obs,cfg,*_ = initial(now=718,end=718)
        with self.assertRaises(ValueError):
            value_route(offer("past",{719:[["SELL","MILK",1]]}),obs,cfg,ENGINE,Scenario("x"))

    def test_fixed_costs_and_trough(self):
        fixed = {(2,0):-ENGINE.ANIMALS["SHEEP"]["cost"],
                 (2,1):-ENGINE.CROPS["WHEAT"]["seed"],
                 (2,2):-ENGINE._hire_cost(0),
                 (2,3):-ENGINE.LAND_PRICES[0]}
        self.compare(offer("fixed",{2:[["BUY_ANIMAL","SHEEP",1],["BUY_SEED","WHEAT",1],
                                      ["HIRE"],["BUY_LAND"],["SELL","WOOL",10]]},fixed))
        obs,cfg,*_=initial(money=1)
        negative=value_route(offer("under",{2:[["BUY_ANIMAL","SHEEP",1]]},{(2,0):-500}),
                             obs,cfg,ENGINE,Scenario("none"))
        self.assertLess(negative["minimum_marked_cash"],0)
        self.assertEqual(negative["first_negative"],[2,0])

    def test_complete_vector_and_zero_quantity(self):
        obs,cfg,*_=initial()
        offers=[offer("a",{2:[["SELL","WOOL",0]]}),offer("b",{2:[["SELL","WOOL",2]]})]
        report=evaluate_scenarios(offers,obs,cfg,ENGINE,[Scenario("none")],seconds=None)
        self.assertTrue(report["complete"])
        converted=as_cash_scenarios(report,SimpleNamespace)
        self.assertEqual(converted[0].flows["a"][(2,0)],0)
        self.assertGreater(converted[0].flows["b"][(2,0)],0)

    def test_all_or_none_unit_budget(self):
        obs,cfg,*_=initial()
        offers=[offer("a",{2:[["SELL","WOOL",1]]}),offer("b",{2:[["SELL","WOOL",2]]})]
        report=evaluate_scenarios(offers,obs,cfg,ENGINE,[Scenario("none")],max_units=1,seconds=None)
        self.assertFalse(report["complete"])
        self.assertEqual(report["rows"],[])
        with self.assertRaises(ValueError): as_cash_scenarios(report,SimpleNamespace)

    def test_deadline_and_no_scenarios(self):
        obs,cfg,*_=initial()
        offers=[offer("a",{2:[["SELL","WOOL",2]]})]
        self.assertEqual(evaluate_scenarios(offers,obs,cfg,ENGINE,[Scenario("none")],seconds=0)["reason"],
                         "incomplete_budget")
        self.assertFalse(evaluate_scenarios(offers,obs,cfg,ENGINE,[])["complete"])

    def test_invalid_scenario_or_order_preserves_no_rows(self):
        obs,cfg,*_=initial()
        cases=[(offer("bad",{2:[["BUY_PRODUCT","WOOL",1]]}),Scenario("x")),
               (offer("bad",{2:[["SELL","WOOL",-1]]}),Scenario("x")),
               (offer("a",{}),Scenario("x",{2:[["HIRE"]]})),
               (offer("a",{}),Scenario("x",shop_additions={1:["YARN_STORE"]})),
               (offer("a",{}),Scenario("x",shop_additions={2:["INVENTED"]}))]
        for ours,scenario in cases:
            got=evaluate_scenarios([ours],obs,cfg,ENGINE,[scenario],seconds=None)
            self.assertFalse(got["complete"])
            self.assertEqual(got["rows"],[])
        with self.assertRaises(ValueError):
            as_cash_scenarios({"complete":True,"rows":[]},SimpleNamespace)

    def test_engine_round_cap_and_finite_budget(self):
        obs,cfg,*_=initial()
        for quantity in (100_000,True):
            got=evaluate_scenarios([offer("x",{2:[["SELL","WOOL",quantity]]})],
                                   obs,cfg,ENGINE,[Scenario("none")],seconds=None)
            self.assertFalse(got["complete"])
        huge=offer("huge",{2:[["HIRE"],["HIRE"]]}, {(2,0):-1e308,(2,1):-1e308})
        got=evaluate_scenarios([huge],obs,cfg,ENGINE,[Scenario("none")],seconds=None)
        self.assertFalse(got["complete"])

    def test_duplicate_ids_and_slots(self):
        obs,cfg,*_=initial()
        ours=offer("x",{2:[["SELL","WOOL",1]]})
        self.assertFalse(evaluate_scenarios([ours,ours],obs,cfg,ENGINE,[Scenario("none")])["complete"])
        self.assertFalse(evaluate_scenarios([ours],obs,cfg,ENGINE,[Scenario("x"),Scenario("x")])["complete"])
        ours.orders=ours.orders+ours.orders
        self.assertFalse(evaluate_scenarios([ours],obs,cfg,ENGINE,[Scenario("none")])["complete"])

    def test_generated_complete_market_comparisons(self):
        rng=random.Random(490107)
        for case in range(80):
            queues=[{},{}]
            for actor in range(2):
                for step in (2,4,7,8,12,17):
                    q=[]
                    for _ in range(rng.randrange(1,5)):
                        kind=rng.randrange(4)
                        if kind==0: q.append(["PASS"])
                        elif kind==1: q.append(["BUY_PRODUCT",rng.choice(("WHEAT","FERTILIZER")),rng.randrange(6)])
                        else: q.append(["SELL",rng.choice(tuple(ENGINE.PRODUCTS)),rng.randrange(8)])
                    queues[actor][step]=q
            scenario=Scenario("generated",queues[1],{8:["YARN_STORE"]} if case%3==0 else {})
            self.compare(offer(f"generated-{case}",queues[0]),scenario,seat=case%2,
                         shops=("YARN_STORE",)*(case%3),
                         inventory={p:rng.randrange(9950,10350) for p in ENGINE.PRODUCTS})


def main():
    global ENGINE,LOADER
    parser=argparse.ArgumentParser()
    parser.add_argument("--engine-dir",required=True,type=Path)
    parser.add_argument("--loader",required=True,type=Path)
    parser.add_argument("--report",type=Path,required=True)
    args=parser.parse_args()
    for name in ("kaggriculture.py","kaggriculture.json","utils.py"):
        if not (args.engine_dir/name).is_file(): parser.error("all three existing engine files are required")
    spec=importlib.util.spec_from_file_location("existing_engine_loader",args.loader)
    LOADER=importlib.util.module_from_spec(spec);spec.loader.exec_module(LOADER)
    ENGINE,hashes=LOADER.get_engine(args.engine_dir)
    start=time.perf_counter()
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(FlowTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={"engine_ref":LOADER.ENGINE_REF,"engine_sha256":hashes,
            "runtime_sha256":hashlib.sha256(Path(__file__).with_name("dated_flow.py").read_bytes()).hexdigest(),
            "tests_run":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),
            "elapsed_seconds":time.perf_counter()-start,"official_market_cases":len(RECEIPTS),
            "scope":"conditional market phases on synthetic stocked states; not full games or policy strength",
            "cases":RECEIPTS}
    args.report.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    return 0 if result.wasSuccessful() else 1

if __name__=="__main__": raise SystemExit(main())
