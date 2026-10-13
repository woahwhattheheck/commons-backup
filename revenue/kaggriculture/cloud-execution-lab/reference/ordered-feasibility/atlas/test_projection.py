# SPDX-License-Identifier: Apache-2.0
"""Deterministic official-engine and generic SELL consumer tests; no game panels."""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from projection import project_selected, ProjectionError

ENGINE = MECHANICS = SELLER = None
COUNTS = {"differential_cases": 0, "interpreter_transitions": 0}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Struct(dict):
    def __getattr__(self, key):
        try: return self[key]
        except KeyError: raise AttributeError(key) from None
    def __setattr__(self, key, value): self[key] = value


def fixture(step=100, seat=0, capacity=100):
    cfg = {k: v.get("default") if isinstance(v, dict) else v
           for k, v in ENGINE.specification["configuration"].items()}
    cfg.update(weedSpawnChance=0, townShopUnlockInterval=9999, shedCapacity=capacity)
    farm = ENGINE._new_farm(10, 100000)
    positions = ENGINE._shed_access_tiles(10)
    farm["farmer"] = list(positions[0])
    farm["hands"] = [list(positions[1]), list(positions[2])]
    private = ENGINE._new_private()
    private["shed"] = {"WHEAT":20, "FERTILIZER":5, "CARROT":10, "EGG":2}
    private["seeds"] = {p:50 for p in ENGINE.CROPS}
    private["inventories"] = [{"MILK":2}, {"WHEAT":4}, {"FERTILIZER":2}]
    farms = [copy.deepcopy(farm), copy.deepcopy(farm)]
    obs = dict(step=step, player=seat, day=step//24, hour=step%24,
               farms=farms, private=private, market=ENGINE._new_market(),
               town={"unlocked_shops":["FARMERS_MARKET"]})
    return obs, cfg


def action(farmer=None, hands=None, market=None):
    return dict(farmer=farmer or ["PASS"], hands=hands or [], market=market or [])


def truth_state(obs, cfg):
    view = copy.deepcopy(obs)
    farms, market, town = view["farms"], view["market"], view["town"]
    rows = []
    for seat in range(2):
        private = view["private"] if seat == view["player"] else ENGINE._new_private()
        rows.append(Struct(observation=Struct(farms=farms, market=market, town=town,
                                              private=private, player=seat,
                                              day=view["day"], hour=view["hour"], step=view["step"]),
                           action=action(), status="ACTIVE", reward=0))
    return rows, Struct(configuration=Struct(cfg), info={"seed":0}, done=False)


def event_totals(packet, phase=None):
    result = {}
    for event in packet["projection"]["stock_events"]:
        if phase is None or event["phase"] == phase:
            key = (event["step"], event["product"])
            result[key] = result.get(key,0) + event["quantity_delta"]
    return result


class ProjectionTests(unittest.TestCase):
    def test_current_real_capacity_and_no_second_current_event(self):
        obs,cfg=fixture();obs["private"]["shed"]={"WHEAT":100}
        packet=project_selected(MECHANICS,obs,cfg,action(["DROP"]),future_actions={},end_step=100)
        self.assertEqual(packet["post_unit_shed"],{"WHEAT":100})
        self.assertEqual(packet["post_units"]["private"]["inventories"][0],{})
        self.assertEqual(packet["projection"]["stock_events"],[])

    def test_future_drop_retains_whole_request_in_inventory_order(self):
        obs,cfg=fixture();obs["private"]["shed"]={"WHEAT":100}
        obs["private"]["inventories"][0]={"MILK":10,"EGG":7}
        packet=project_selected(MECHANICS,obs,cfg,action(),future_actions={101:action(["DROP"])},end_step=101)
        self.assertEqual([(e["product"],e["quantity_delta"]) for e in packet["projection"]["stock_events"]],[("MILK",10),("EGG",7)])
        self.assertEqual(sum(packet["phases"][-1]["private"]["shed"].values()),117)

    def test_worker_order_is_not_netted(self):
        obs,cfg=fixture();obs["private"]["inventories"][0]={"MILK":10}
        packet=project_selected(MECHANICS,obs,cfg,action(),future_actions={101:action(["DROP"],[["PICKUP","WHEAT",10]])},end_step=101)
        self.assertEqual([(e["worker_index"],e["quantity_delta"]) for e in packet["projection"]["stock_events"]],[(0,10),(1,-10)])

    def test_missing_action_and_partial_pickup_shorten_without_fabrication(self):
        obs,cfg=fixture()
        packet=project_selected(MECHANICS,obs,cfg,action(),future_actions={102:action()},end_step=104)
        self.assertEqual(packet["projection"]["end_step"],100)
        self.assertEqual(packet["diagnostics"]["end_reason"],"missing_selected_action")
        packet=project_selected(MECHANICS,obs,cfg,action(),future_actions={101:action(["PICKUP","WHEAT",21],market=[["BUY_PRODUCT","WHEAT",1]])},end_step=101)
        self.assertEqual(packet["projection"]["end_step"],100)
        self.assertEqual(packet["projection"]["stock_events"],[])
        self.assertEqual(packet["diagnostics"]["end_reason"],"stock_dependent_pickup")

    def test_future_market_effects_not_stock_events_and_no_cash_bound(self):
        obs,cfg=fixture();obs["farms"][0]["money"]=0
        packet=project_selected(MECHANICS,obs,cfg,action(market=[["BUY_PRODUCT","WHEAT",3]]),future_actions={101:action(["PICKUP","WHEAT",23])},end_step=101)
        self.assertEqual(packet["projection"]["stock_events"][0]["quantity_delta"],-23)
        self.assertNotIn("order_cost_bounds",packet)
        self.assertIsNone(packet["diagnostics"]["future_cash_forecast"])
        self.assertEqual(packet["post_units"]["farm"]["money"],0)

    def test_hire_follows_units_and_spawn_uses_actual_positions(self):
        obs,cfg=fixture();obs["farms"][0]["hands"]=[];obs["private"]["inventories"]=[{}]
        selected=action(hands=[["PICKUP","WHEAT",2]],market=[["HIRE"]])
        packet=project_selected(MECHANICS,obs,cfg,selected,future_actions={101:action(hands=[["PICKUP","WHEAT",2]])},end_step=101)
        self.assertEqual(packet["post_units"]["farm"]["hands"],[])
        self.assertEqual([(e["step"],e["worker_index"],e["quantity_delta"]) for e in packet["projection"]["stock_events"]],[(101,1,-2)])

    def test_atomic_seed_requests_include_nonexistent_hands(self):
        obs,cfg=fixture();f=obs["farms"][0];f["farmer"]=[0,0];f["hands"]=[]
        obs["private"]["seeds"]["WHEAT"]=1
        packet=project_selected(MECHANICS,obs,cfg,action(["PLANT","WHEAT"],[["PLANT","WHEAT"]]),future_actions={},end_step=100)
        self.assertIsNone(packet["post_units"]["farm"]["tiles"][0][0])
        self.assertEqual(packet["post_units"]["private"]["seeds"]["WHEAT"],1)

    def test_eod_after_market_whole_carried_and_unknown_next_day(self):
        obs,cfg=fixture(step=22)
        packet=project_selected(MECHANICS,obs,cfg,action(),future_actions={23:action(),24:action()},end_step=25)
        self.assertEqual(packet["projection"]["end_step"],23)
        self.assertEqual(packet["diagnostics"]["end_reason"],"daily_boundary")
        self.assertEqual(event_totals(packet),{(23,"MILK"):2,(23,"WHEAT"):4,(23,"FERTILIZER"):2})
        self.assertTrue(all(e["phase"]=="after_market" for e in packet["projection"]["stock_events"]))

    def test_final_decision_does_not_invent_deposit_or_liquidation(self):
        obs,cfg=fixture(step=717)
        packet=project_selected(MECHANICS,obs,cfg,action(),future_actions={718:action(),719:action(["DROP"])},end_step=722)
        self.assertEqual(packet["projection"]["end_step"],718)
        self.assertEqual(packet["diagnostics"]["end_reason"],"final_decision")
        self.assertEqual(packet["projection"]["stock_events"],[])

    def test_current_eod_and_day_hour_fallback(self):
        obs,cfg=fixture(step=23);del obs["step"]
        packet=project_selected(MECHANICS,obs,cfg,action(),future_actions={},end_step=23)
        self.assertEqual(packet["projection"]["observed_step"],23)
        self.assertTrue(all(e["step"]==23 and e["phase"]=="after_market" for e in packet["projection"]["stock_events"]))

    def test_eight_step_bound(self):
        obs,cfg=fixture(step=1)
        packet=project_selected(MECHANICS,obs,cfg,action(),future_actions={t:action() for t in range(2,15)},end_step=14)
        self.assertEqual(packet["projection"]["end_step"],9)
        self.assertEqual(packet["diagnostics"]["end_reason"],"eight_step_bound")

    def test_contingent_harvest_not_counted_twice_and_carried_retained(self):
        obs,cfg=fixture(step=21);farm=obs["farms"][0];farm["farmer"]=[0,0]
        farm["tiles"][0][0]=ENGINE._new_animal("GOOSE",0)
        farm["tiles"][0][0]["yield_units"]=4
        packet=project_selected(MECHANICS,obs,cfg,action(),future_actions={22:action(["HARVEST"]),23:action()},end_step=23,contingent_harvests=((22,0),))
        self.assertNotIn((23,"EGG"),event_totals(packet))
        self.assertEqual(event_totals(packet)[(23,"MILK")],2)
        self.assertEqual(packet["diagnostics"]["excluded_harvests"][0]["quantities"],{"EGG":4})
        ordinary=project_selected(MECHANICS,obs,cfg,action(),future_actions={22:action(["HARVEST"]),23:action()},end_step=23)
        self.assertEqual(event_totals(ordinary)[(23,"EGG")],4)

    def test_malformed_exclusion_rejected(self):
        obs,cfg=fixture()
        for excluded in (((100,0),),((101,0),(101,0)),((101,0),)):
            with self.subTest(excluded=excluded),self.assertRaises(ProjectionError):
                project_selected(MECHANICS,obs,cfg,action(),future_actions={101:action()},end_step=101,contingent_harvests=excluded)

    def test_inputs_unchanged_and_no_other_farm_read(self):
        obs,cfg=fixture(seat=1);plan={101:action(["DROP"])};before=copy.deepcopy((obs,cfg,plan))
        project_selected(MECHANICS,obs,cfg,action(),future_actions=plan,end_step=101)
        self.assertEqual((obs,cfg,plan),before)
        class OwnOnly:
            def __getitem__(self,key):
                if key != 1: raise AssertionError("rival farm access")
                return obs["farms"][1]
        own=dict(obs,farms=OwnOnly())
        packet=project_selected(MECHANICS,own,cfg,action(),future_actions={},end_step=100)
        self.assertEqual(packet["post_units"]["player"],1)

    def test_standalone_mechanics_matches_official_input_stage(self):
        for seat in (0,1):
            obs,cfg=fixture(seat=seat)
            command=action(["DROP"],[["PICKUP","MILK",1],["PASS"]],[["HIRE"]])
            a=project_selected(MECHANICS,obs,cfg,command,future_actions={},end_step=100)
            b=project_selected(ENGINE,obs,cfg,command,future_actions={},end_step=100)
            self.assertEqual(a,b)

    def test_full_interpreter_differential(self):
        templates=[action(),action(["DROP"]),action(["PICKUP","WHEAT",1]),
                   action(["PLACE","MILK",1]),action(["UP"],[["LEFT"],["DOWN"]]),
                   action(market=[["HIRE"],["BUY_PRODUCT","WHEAT",1],["SELL","CARROT",1]]),
                   action(["PLANT","WHEAT"],market=[["BUY_SEED","WHEAT",2]]),
                   action(["WATER"],[["HARVEST"]]),
                   action(["CARE"],[["FEED"],["COLLECT_FERTILIZER"]])]
        for seat in (0,1):
            for step in (0,21,22,23,240,669,716,718):
                for kind,template in enumerate(templates):
                    with self.subTest(seat=seat,step=step,kind=kind):
                        obs,cfg=fixture(step,seat)
                        if kind==6:
                            obs["farms"][seat]["farmer"]=[0,0]
                        if kind==7:
                            f=obs["farms"][seat];f["farmer"]=[0,0];f["hands"][0]=[0,0]
                            tile=ENGINE._new_plant("WHEAT",step//24-2,24)
                            tile["yield_units"]=3;f["tiles"][0][0]=tile
                        if kind==8:
                            f=obs["farms"][seat];f["farmer"]=[0,0];f["hands"]=[[0,0],[0,0]]
                            f["tiles"][0][0]=ENGINE._new_animal("GOOSE",step//24)
                            f["tiles"][0][0]["fertilizer_available"]=True
                        plans={t:copy.deepcopy(template) for t in range(step+1,step+4)}
                        packet=project_selected(MECHANICS,obs,cfg,template,future_actions=plans,end_step=step+3)
                        states,env=truth_state(obs,cfg)
                        for t in range(step,packet["projection"]["end_step"]+1):
                            for row in states:
                                row.observation.step=t;row.action=action()
                            states[seat].action=copy.deepcopy(template if t==step else plans[t])
                            ENGINE.interpreter(states,env)
                            expected=next(x["private"] for x in packet["phases"] if x["step"]==t and x["phase"]=="after_market")
                            self.assertEqual(states[seat].observation.private,expected)
                            COUNTS["interpreter_transitions"]+=1
                        COUNTS["differential_cases"]+=1


class ConsumerTests(unittest.TestCase):
    def _transfer_case(self,reverse=False):
        obs,cfg=fixture();private=obs["private"]
        private["shed"]={"WHEAT":90,"CARROT":10}
        private["inventories"]=[{"MILK":10},{}] if not reverse else [{},{"MILK":10}]
        obs["farms"][0]["hands"]=obs["farms"][0]["hands"][:1]
        selected=action(market=[["SELL","CARROT",10]])
        following=action(["DROP"],[["PICKUP","WHEAT",10]]) if not reverse else action(["PICKUP","WHEAT",10],[["DROP"]])
        packet=project_selected(MECHANICS,obs,cfg,selected,future_actions={101:following},end_step=101)
        return obs,cfg,selected,following,packet

    def test_ordered_capacity_prefix_rejects_spill_and_preserves_ten_units(self):
        obs,cfg,selected,following,packet=self._transfer_case()
        ledger=SELLER.ProjectionLedger(obs,cfg,selected,packet["post_unit_shed"],packet["projection"],None,None,8)
        self.assertFalse(ledger.feasible("CARROT",((100,0),(101,0))))
        policy=SELLER.SelectedActionSell()
        result=policy.transform(obs,cfg,selected,post_unit_shed=packet["post_unit_shed"],projection=packet["projection"])
        self.assertEqual(result["market"],[["SELL","CARROT",10]])
        state,env=truth_state(obs,cfg);state[0].action=result;ENGINE.interpreter(state,env)
        for row in state: row.observation.step=101;row.action=action()
        state[0].action=following;ENGINE.interpreter(state,env)
        self.assertEqual(state[0].observation.private["shed"].get("MILK",0),10)

    def test_pickup_then_drop_still_allows_delay(self):
        obs,cfg,selected,following,packet=self._transfer_case(reverse=True)
        ledger=SELLER.ProjectionLedger(obs,cfg,selected,packet["post_unit_shed"],packet["projection"],None,None,8)
        self.assertTrue(ledger.feasible("CARROT",((100,0),(101,0))))
        policy=SELLER.SelectedActionSell();result=policy.transform(obs,cfg,selected,post_unit_shed=packet["post_unit_shed"],projection=packet["projection"])
        self.assertNotEqual(result["market"],selected["market"])
        state,env=truth_state(obs,cfg);state[0].action=result;ENGINE.interpreter(state,env)
        for row in state: row.observation.step=101;row.action=action()
        state[0].action=following;ENGINE.interpreter(state,env)
        self.assertEqual(state[0].observation.private["shed"].get("MILK",0),10)

    def test_later_deposit_cannot_fund_earlier_withdrawal(self):
        obs,cfg=fixture();base=action()
        projection=dict(observed_step=100,end_step=101,future_market={101:[]},stock_events=[
            dict(step=101,phase="before_market",product="MILK",quantity_delta=-1),
            dict(step=101,phase="before_market",product="MILK",quantity_delta=1)])
        ledger=SELLER.ProjectionLedger(obs,cfg,base,obs["private"]["shed"],projection,None,None,8)
        self.assertFalse(ledger.feasible("CARROT",((100,0),)))
        projection["stock_events"].reverse()
        ledger=SELLER.ProjectionLedger(obs,cfg,base,obs["private"]["shed"],projection,None,None,8)
        self.assertTrue(ledger.feasible("CARROT",((100,0),)))

    def test_fallback_without_external_product_buy_funding_bound(self):
        obs,cfg=fixture();selected=action(market=[["BUY_PRODUCT","WHEAT",2],["SELL","CARROT",10]])
        packet=project_selected(MECHANICS,obs,cfg,selected,future_actions={},end_step=100)
        policy=SELLER.SelectedActionSell()
        fallback=action(["PASS"],market=[["SELL","CARROT",3]])
        result=policy.transform(obs,cfg,selected,post_unit_shed=packet["post_unit_shed"],projection=packet["projection"],fallback_action=fallback)
        self.assertEqual(result,fallback)
        self.assertIn("cash bound",policy.diagnostics["reason"])

    def test_pending_whole_lot_remains_capacity_not_sale_stock(self):
        obs,cfg=fixture(step=21);farm=obs["farms"][0];farm["farmer"]=[0,0]
        farm["tiles"][0][0]=ENGINE._new_animal("GOOSE",0);farm["tiles"][0][0]["yield_units"]=4
        selected=action(market=[["SELL","CARROT",10]])
        packet=project_selected(MECHANICS,obs,cfg,selected,future_actions={22:action(["HARVEST"]),23:action()},end_step=23,contingent_harvests=((22,0),))
        contract=dict(observed_step=21,capacity_events=[dict(owner="test-producer",errand_id="errand-1",step=23,phase="after_market",pending_capacity_units=4,units_total=4,contingent=True,guaranteed_stock_units=0)])
        ledger=SELLER.ProjectionLedger(obs,cfg,selected,packet["post_unit_shed"],packet["projection"],contract,None,8)
        self.assertEqual(ledger.pending_units(23,"after_market"),4)
        self.assertFalse(any(p=="EGG" and q>0 for t,events in ledger.events.items() for p,q in events))
        self.assertTrue(ledger.feasible("CARROT",((21,10),)))


def main():
    global ENGINE,MECHANICS,SELLER
    p=argparse.ArgumentParser(description=__doc__)
    root=HERE.parent
    p.add_argument("--evaluator",type=Path,default=root/"cloud-eval/evaluate.py")
    p.add_argument("--engine-cache",type=Path,required=True)
    p.add_argument("--engine-loader",type=Path)
    p.add_argument("--seller",type=Path,default=root/"cloud-execution-lab/selected_action_sell.py")
    p.add_argument("--report",type=Path)
    args,remaining=p.parse_known_args()
    evaluator=load(args.evaluator,"atlas_projection_evaluator")
    loader_kwargs = {"loader":args.engine_loader} if args.engine_loader else {}
    ENGINE,hashes=evaluator.get_engine(args.engine_cache,**loader_kwargs)
    sys.path.insert(0,str(args.seller.parent))
    MECHANICS=load(args.seller.parent/"mechanics.py","mechanics")
    SELLER=load(args.seller,"atlas_selected_sell")
    program=unittest.main(argv=[sys.argv[0],*remaining],exit=False)
    summary=dict(COUNTS,tests_run=program.result.testsRun,failures=len(program.result.failures),errors=len(program.result.errors),
                 engine_sha256=hashes,seller_sha256=hashlib.sha256(args.seller.read_bytes()).hexdigest(),
                 projection_sha256=hashlib.sha256((HERE/"projection.py").read_bytes()).hexdigest(),
                 scope="deterministic fixtures, not games or a held panel")
    if args.report: args.report.write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps(summary,sort_keys=True))
    raise SystemExit(0 if program.result.wasSuccessful() else 1)

if __name__=="__main__": main()
