from __future__ import annotations
import copy
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("skip", HERE / "uncared_eod_feed_skip.py")
skip = importlib.util.module_from_spec(spec); spec.loader.exec_module(skip)
CFG = {"boardSize":10,"turnsPerDay":24,"episodeSteps":720,"shedCapacity":100}

def animal(species="GOOSE", *, pending=0, unfed=0, fed=False, cared=False, units=0, placed=0):
    kind={"GOOSE":"COOP","COW":"PASTURE","SHEEP":"PASTURE"}[species]
    return {"kind":kind,"animal":species,"placed_day":placed,"yield_units":units,
            "pending_care_bonus":pending,"consecutive_unfed":unfed,
            "fed_today":fed,"cared_today":cared,"fertilizer_available":False}

def world(*, step=23, site=(3,4), wheat=1, shed=None, hands=None, inventories=None,
          tile=None, market=None, farmer=None):
    tiles=[[None for _ in range(10)] for _ in range(10)]
    tiles[site[1]][site[0]]=tile or animal()
    hands=copy.deepcopy(hands or [])
    farm0={"farmer":list(farmer or site),"hands":hands,"tiles":tiles}
    farm1={"farmer":[4,4],"hands":[],"tiles":[[None for _ in range(10)] for _ in range(10)]}
    inv=copy.deepcopy(inventories) if inventories is not None else [{"WHEAT":wheat}]+[{} for _ in hands]
    return {"step":step,"player":0,"farms":[farm0,farm1],
            "private":{"inventories":inv,"shed":copy.deepcopy(shed or {}),"seeds":{}},
            "market":{}}, {"farmer":["FEED"],"hands":[["PASS"] for _ in hands],"market":copy.deepcopy(market or [])}

def route(step=23, site=(3,4), *, pickup=True, feed=True, feed_step=None):
    r=[{"farmer":["PASS"],"hands":[],"market":[]} for _ in range(720)]
    if pickup: r[step+1]["farmer"]=["PICKUP","WHEAT",1]
    # spawn 4,4 -> default target 3,4
    r[step+2]["farmer"]=["WEST"]
    if feed:
        r[feed_step if feed_step is not None else step+3]["farmer"]=["FEED"]
    return r

class GuardTests(unittest.TestCase):
    def setUp(self):
        skip.telemetry.clear(); skip.last_guard_report={}

    def test_mechanism_api_retained(self):
        obs, act=world()
        changes=skip.plan_uncared_eod_feed_skip(act,obs,CFG)
        self.assertEqual(len(changes),1)
        self.assertEqual(changes[0]["guaranteed_wheat_saved"],1)
        out=skip.apply_uncared_eod_feed_skip(act,obs,CFG,enabled=True)
        self.assertEqual(out["farmer"],["PASS"]); self.assertEqual(act["farmer"],["FEED"])

    def test_guard_admits_only_with_pickup_and_next_feed(self):
        obs,act=world(); r=route()
        changes,rep=skip.plan_guarded_starvation_skip(act,obs,CFG,r)
        self.assertEqual(len(changes),1); self.assertEqual(rep["admitted"],1)
        self.assertEqual(changes[0]["next_feed_certificate"]["pickup_step"],24)
        self.assertEqual(changes[0]["next_feed_certificate"]["feed_step"],26)
        out=skip.apply_guarded_uncared_eod_feed_skip(act,obs,CFG,r,enabled=True)
        self.assertEqual(out["farmer"],["PASS"]); self.assertEqual(skip.telemetry["guarded_rewrites"],1)

    def test_no_pickup_or_no_feed_declines(self):
        for r in (route(pickup=False),route(feed=False)):
            with self.subTest():
                obs,act=world(); changes,rep=skip.plan_guarded_starvation_skip(act,obs,CFG,r)
                self.assertEqual(changes,[])
                self.assertEqual(rep["blocked"].get("next_feed_route_not_certified"),1)

    def test_feed_other_site_consumes_saved_unit_and_declines(self):
        obs,act=world(); r=route(feed=False)
        r[25]["farmer"]=["FEED"] # still at 4,4 after pickup; consumes lower-bound unit elsewhere
        r[26]["farmer"]=["WEST"]; r[27]["farmer"]=["FEED"]
        changes,_=skip.plan_guarded_starvation_skip(act,obs,CFG,r)
        self.assertEqual(changes,[])

    def test_sell_before_pickup_breaks_custody(self):
        obs,act=world(); r=route()
        r[24]["farmer"]=["PASS"]; r[24]["market"]=[["SELL","WHEAT",1]]
        r[25]["farmer"]=["PICKUP","WHEAT",1]; r[26]["farmer"]=["WEST"]; r[27]["farmer"]=["FEED"]
        changes,_=skip.plan_guarded_starvation_skip(act,obs,CFG,r)
        self.assertEqual(changes,[])

    def test_hand_pickup_before_farmer_breaks_custody(self):
        obs,act=world(); r=route()
        r[24]["farmer"]=["PASS"]; r[24]["hands"]=[["PICKUP","WHEAT",1]]
        r[25]["farmer"]=["PICKUP","WHEAT",1]; r[26]["farmer"]=["WEST"]; r[27]["farmer"]=["FEED"]
        changes,_=skip.plan_guarded_starvation_skip(act,obs,CFG,r)
        self.assertEqual(changes,[])

    def test_saved_wheat_redrop_fails_closed(self):
        obs,act=world(); r=route(feed=False)
        r[24]["farmer"]=["PICKUP","WHEAT",1]
        r[25]["farmer"]=["DROP"]
        r[26]["farmer"]=["PICKUP","WHEAT",1]
        r[27]["farmer"]=["WEST"]; r[28]["farmer"]=["FEED"]
        changes,rep=skip.plan_guarded_starvation_skip(act,obs,CFG,r)
        self.assertEqual(changes,[])
        self.assertEqual(rep["blocked"].get("next_feed_route_not_certified"),1)

    def test_same_callback_drop_then_sell_cannot_reuse_saved_wheat(self):
        obs,act=world(); r=route(feed=False)
        r[24]["farmer"]=["PICKUP","WHEAT",1]
        r[25]["farmer"]=["DROP"]; r[25]["market"]=[["SELL","WHEAT",1]]
        r[26]["farmer"]=["PICKUP","WHEAT",1]
        r[27]["farmer"]=["WEST"]; r[28]["farmer"]=["FEED"]
        changes,rep=skip.plan_guarded_starvation_skip(act,obs,CFG,r)
        self.assertEqual(changes,[])
        self.assertEqual(rep["blocked"].get("next_feed_route_not_certified"),1)

    def test_eod_capacity_includes_all_shed_and_carried_stock(self):
        obs,act=world(shed={"EGG":99},wheat=1)
        self.assertEqual(len(skip.plan_guarded_starvation_skip(act,obs,CFG,route())[0]),1)
        obs,act=world(shed={"EGG":100},wheat=1)
        changes,rep=skip.plan_guarded_starvation_skip(act,obs,CFG,route())
        self.assertEqual(changes,[]); self.assertEqual(rep["blocked"].get("eod_stock_not_certified"),1)

    def test_current_stock_creating_work_declines(self):
        obs,act=world(hands=[[4,4]], inventories=[{"WHEAT":1},{}])
        act["hands"]=[["HARVEST"]]
        changes,rep=skip.plan_guarded_starvation_skip(act,obs,CFG,route())
        self.assertEqual(changes,[]); self.assertEqual(rep["blocked"].get("eod_stock_not_certified"),1)

    def test_current_product_or_animal_buy_declines(self):
        for order in (["BUY_PRODUCT","WHEAT",1],["BUY_ANIMAL","GOOSE",1]):
            obs,act=world(market=[order]); changes,rep=skip.plan_guarded_starvation_skip(act,obs,CFG,route())
            self.assertEqual(changes,[]); self.assertEqual(rep["blocked"].get("eod_stock_not_certified"),1)

    def test_pending_bonus_on_current_production_boundary_blocks(self):
        # day3 EOD -> goose first production day4
        obs,act=world(step=95,tile=animal(pending=1))
        self.assertEqual(skip.plan_guarded_starvation_skip(act,obs,CFG,route(step=95))[0],[])

    def test_pending_bonus_off_boundary_can_pass_when_next_feed_certified(self):
        obs,act=world(step=23,tile=animal(pending=2))
        changes,_=skip.plan_guarded_starvation_skip(act,obs,CFG,route(step=23))
        self.assertEqual(len(changes),1)

    def test_current_care_or_repeated_feed_blocks(self):
        obs,act=world(hands=[[3,4]], inventories=[{"WHEAT":1},{}])
        act["hands"]=[["CARE"]]
        self.assertEqual(skip.plan_guarded_starvation_skip(act,obs,CFG,route())[0],[])
        obs,act=world(hands=[[3,4]], inventories=[{"WHEAT":1},{"WHEAT":1}])
        act["hands"]=[["FEED"]]
        self.assertEqual(skip.plan_guarded_starvation_skip(act,obs,CFG,route())[0],[])

    def test_consecutive_unfed_one_blocks(self):
        obs,act=world(tile=animal(unfed=1))
        self.assertEqual(skip.plan_guarded_starvation_skip(act,obs,CFG,route())[0],[])

    def test_guard_at_most_one_site(self):
        obs,act=world(hands=[[5,4]], inventories=[{"WHEAT":1},{"WHEAT":1}])
        obs["farms"][0]["tiles"][4][5]=animal("SHEEP")
        act["hands"]=[["FEED"]]
        # Existing mechanism sees two candidates. Route certifies only main site.
        self.assertEqual(len(skip.plan_uncared_eod_feed_skip(act,obs,CFG)),2)
        changes,_=skip.plan_guarded_starvation_skip(act,obs,CFG,route())
        self.assertLessEqual(len(changes),1)

    def test_disabled_is_identity(self):
        obs,act=world(); out=skip.apply_guarded_uncared_eod_feed_skip(act,obs,CFG,route(),enabled=False)
        self.assertIs(out,act); self.assertEqual(skip.last_guard_report["blocked"],{"disabled":1})

    def test_malformed_route_fails_closed(self):
        obs,act=world()
        for r in (None, [], [{} for _ in range(30)]):
            with self.subTest(r=type(r).__name__):
                self.assertEqual(skip.plan_guarded_starvation_skip(act,obs,CFG,r)[0],[])

if __name__ == "__main__": unittest.main()
