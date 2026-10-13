import copy
import unittest
from v233_fasting_wheat_credit import (
    V233_SITES, apply_v233_fasting_wheat_credit, observe_v233_fasting_skips,
)

CFG = {"boardSize":10,"turnsPerDay":24,"episodeSteps":720,"shedCapacity":100,"maxMarketOrdersPerTurn":10}


def tile():
    return {"kind":"PASTURE","animal":"SHEEP","placed_day":12,"yield_units":0,
            "pending_care_bonus":0,"consecutive_unfed":0,"fed_today":False,
            "cared_today":False,"fertilizer_available":False}


def obs(step=311, shed=None):
    tiles=[[None for _ in range(10)] for _ in range(10)]
    for x,y in V233_SITES: tiles[y][x]=tile()
    farm={"tiles":tiles,"farmer":[4,4],"hands":[[5,5],[5,6]],"money":9000,
          "unlocked_quadrants":["NW","NE","SW","SE"],"hires_today":2}
    return {"step":step,"player":0,"farms":[farm,copy.deepcopy(farm)],
            "private":{"shed":dict(shed or {"WHEAT":4,"WOOL":1}),"inventories":[{}, {}, {}],"seeds":{}}}


def state():
    return {"committed":True,"workers":{1:[(5,5),(6,5),(7,5)],2:[(5,6),(6,6),(7,6)]}}


def changes(two=True):
    rows=[{"actor":1,"site":[5,5],"species":"SHEEP","guaranteed_wheat_saved":1}]
    if two: rows.append({"actor":2,"site":[6,6],"species":"SHEEP","guaranteed_wheat_saved":1})
    return rows


def action(prefix=None):
    market=list(prefix or []) + [["BUY_PRODUCT","WHEAT",6],["HIRE"],["HIRE"]]
    return {"farmer":["PASS"],"hands":[["PASS"],["PASS"]],"market":market}


class CreditTests(unittest.TestCase):
    def test_observe_two_v233_owned_skips(self):
        s=state(); self.assertEqual(2,observe_v233_fasting_skips(s,obs(311),changes(),CFG,enabled=True))
        self.assertEqual(12,s["v233_fasting_credit_day"]); self.assertEqual(2,s["v233_fasting_credit_pending"])

    def test_observe_default_off_identity_state(self):
        s=state(); before=copy.deepcopy(s)
        self.assertEqual(0,observe_v233_fasting_skips(s,obs(311),changes(),CFG,enabled=False)); self.assertEqual(before,s)

    def test_observe_rejects_non_eod(self):
        s=state(); self.assertEqual(0,observe_v233_fasting_skips(s,obs(310),changes(),CFG,enabled=True))

    def test_observe_ignores_non_v233_actor_site(self):
        s=state(); bad=[{"actor":1,"site":[5,6],"species":"SHEEP","guaranteed_wheat_saved":1}]
        self.assertEqual(0,observe_v233_fasting_skips(s,obs(311),bad,CFG,enabled=True))

    def test_observe_caps_duplicates(self):
        s=state(); dup=changes(False)*3
        self.assertEqual(1,observe_v233_fasting_skips(s,obs(311),dup,CFG,enabled=True)); self.assertEqual(1,s["v233_fasting_credit_pending"])

    def test_apply_reduces_exact_v233_order_same_slot(self):
        s=state(); observe_v233_fasting_skips(s,obs(311),changes(),CFG,enabled=True)
        a=action([['SELL','WOOL',1]]); out=apply_v233_fasting_wheat_credit(a,obs(312),s,CFG,enabled=True)
        self.assertIsNot(out,a); self.assertEqual([['SELL','WOOL',1],['BUY_PRODUCT','WHEAT',4],['HIRE'],['HIRE']],out['market'])
        self.assertEqual(2,s['v233_fasting_credit_applied']); self.assertEqual(0,s['v233_fasting_credit_pending'])

    def test_apply_default_off_exact_identity(self):
        s=state(); s.update(v233_fasting_credit_day=12,v233_fasting_credit_pending=1); a=action()
        self.assertIs(a,apply_v233_fasting_wheat_credit(a,obs(312),s,CFG,enabled=False))

    def test_apply_requires_immediately_prior_day(self):
        s=state(); s.update(v233_fasting_credit_day=11,v233_fasting_credit_pending=1); a=action()
        self.assertIs(a,apply_v233_fasting_wheat_credit(a,obs(312),s,CFG,enabled=True))

    def test_full_shed_fails_closed(self):
        s=state(); s.update(v233_fasting_credit_day=12,v233_fasting_credit_pending=1); a=action()
        self.assertIs(a,apply_v233_fasting_wheat_credit(a,obs(312,{"WHEAT":1,"WOOL":99}),s,CFG,enabled=True))
        self.assertEqual(0,s['v233_fasting_credit_pending'])

    def test_missing_physical_wheat_fails_closed(self):
        s=state(); s.update(v233_fasting_credit_day=12,v233_fasting_credit_pending=2); a=action()
        self.assertIs(a,apply_v233_fasting_wheat_credit(a,obs(312,{"WHEAT":1}),s,CFG,enabled=True))
        self.assertEqual(0,s['v233_fasting_credit_pending'])

    def test_other_wheat_market_row_fails_closed(self):
        s=state(); s.update(v233_fasting_credit_day=12,v233_fasting_credit_pending=1); a=action([['SELL','WHEAT',1]])
        self.assertIs(a,apply_v233_fasting_wheat_credit(a,obs(312),s,CFG,enabled=True))
        self.assertEqual(0,s['v233_fasting_credit_pending'])

    def test_current_wheat_pickup_fails_closed(self):
        s=state(); s.update(v233_fasting_credit_day=12,v233_fasting_credit_pending=1); a=action(); a['farmer']=['PICKUP','WHEAT']
        self.assertIs(a,apply_v233_fasting_wheat_credit(a,obs(312),s,CFG,enabled=True))
        self.assertEqual(0,s['v233_fasting_credit_pending'])

    def test_initial_investment_signature_fails_closed(self):
        s=state(); s.update(v233_fasting_credit_day=12,v233_fasting_credit_pending=1)
        a=action([['BUY_LAND'],['BUY_ANIMAL','SHEEP',6]])
        self.assertIs(a,apply_v233_fasting_wheat_credit(a,obs(312),s,CFG,enabled=True))

    def test_wrong_purchase_quantity_fails_closed(self):
        s=state(); s.update(v233_fasting_credit_day=12,v233_fasting_credit_pending=1); a=action(); a['market'][0][2]=5
        self.assertIs(a,apply_v233_fasting_wheat_credit(a,obs(312),s,CFG,enabled=True))

    def test_wrong_hire_suffix_fails_closed(self):
        s=state(); s.update(v233_fasting_credit_day=12,v233_fasting_credit_pending=1); a=action(); a['market'][-1]=['PASS']
        self.assertIs(a,apply_v233_fasting_wheat_credit(a,obs(312),s,CFG,enabled=True))

    def test_missing_v233_sheep_fails_closed(self):
        s=state(); s.update(v233_fasting_credit_day=12,v233_fasting_credit_pending=1); o=obs(312); o['farms'][0]['tiles'][5][5]=None; a=action()
        self.assertIs(a,apply_v233_fasting_wheat_credit(a,o,s,CFG,enabled=True))

    def test_bad_config_fails_closed(self):
        s=state(); s.update(v233_fasting_credit_day=12,v233_fasting_credit_pending=1); a=action(); cfg=dict(CFG); cfg['shedCapacity']=99
        self.assertIs(a,apply_v233_fasting_wheat_credit(a,obs(312),s,cfg,enabled=True))

    def test_non_morning_fails_closed(self):
        s=state(); s.update(v233_fasting_credit_day=12,v233_fasting_credit_pending=1); a=action()
        self.assertIs(a,apply_v233_fasting_wheat_credit(a,obs(315),s,CFG,enabled=True))
        self.assertEqual(0,s['v233_fasting_credit_pending'])

    def test_credit_max_two_keeps_positive_row_and_cardinality(self):
        s=state(); s.update(v233_fasting_credit_day=12,v233_fasting_credit_pending=2); a=action(); out=apply_v233_fasting_wheat_credit(a,obs(312),s,CFG,enabled=True)
        self.assertEqual(3,len(out['market'])); self.assertEqual(['BUY_PRODUCT','WHEAT',4],out['market'][0])

    def test_input_not_mutated(self):
        s=state(); s.update(v233_fasting_credit_day=12,v233_fasting_credit_pending=1); a=action(); before=copy.deepcopy(a)
        out=apply_v233_fasting_wheat_credit(a,obs(312),s,CFG,enabled=True)
        self.assertEqual(before,a); self.assertNotEqual(out,a)

    def test_worker_partition_poison_rejected(self):
        s=state(); s['workers'][2]=[(5,5),(6,6),(7,6)]
        self.assertEqual(0,observe_v233_fasting_skips(s,obs(311),changes(),CFG,enabled=True))

    def test_non_sheep_change_not_credited(self):
        s=state(); bad=[{"actor":1,"site":[5,5],"species":"COW","guaranteed_wheat_saved":1}]
        self.assertEqual(0,observe_v233_fasting_skips(s,obs(311),bad,CFG,enabled=True))

    def test_nonunit_saved_not_credited(self):
        s=state(); bad=[{"actor":1,"site":[5,5],"species":"SHEEP","guaranteed_wheat_saved":2}]
        self.assertEqual(0,observe_v233_fasting_skips(s,obs(311),bad,CFG,enabled=True))

    def test_credit_waits_across_clean_hour0_then_applies_hour1(self):
        s=state(); s.update(v233_fasting_credit_day=12,v233_fasting_credit_pending=1)
        clean={"farmer":["PASS"],"hands":[["PASS"],["PASS"]],"market":[["SELL","WOOL",1]]}
        self.assertIs(clean,apply_v233_fasting_wheat_credit(clean,obs(312),s,CFG,enabled=True))
        self.assertEqual(1,s['v233_fasting_credit_pending'])
        a=action(); out=apply_v233_fasting_wheat_credit(a,obs(313),s,CFG,enabled=True)
        self.assertEqual(["BUY_PRODUCT","WHEAT",5],out['market'][0])

    def test_full_shed_credit_cannot_revive_after_space_opens(self):
        s=state(); s.update(v233_fasting_credit_day=12,v233_fasting_credit_pending=1); a=action()
        self.assertIs(a,apply_v233_fasting_wheat_credit(a,obs(312,{"WHEAT":1,"WOOL":99}),s,CFG,enabled=True))
        out=apply_v233_fasting_wheat_credit(a,obs(313,{"WHEAT":1,"WOOL":50}),s,CFG,enabled=True)
        self.assertIs(out,a); self.assertEqual(6,out['market'][0][2])

    def test_intervening_wheat_touch_destroys_credit_before_v233_order(self):
        s=state(); s.update(v233_fasting_credit_day=12,v233_fasting_credit_pending=1)
        pre={"farmer":["PICKUP","WHEAT"],"hands":[["PASS"],["PASS"]],"market":[]}
        self.assertIs(pre,apply_v233_fasting_wheat_credit(pre,obs(312),s,CFG,enabled=True))
        self.assertEqual(0,s['v233_fasting_credit_pending'])
        a=action(); out=apply_v233_fasting_wheat_credit(a,obs(313),s,CFG,enabled=True)
        self.assertIs(out,a); self.assertEqual(6,out['market'][0][2])


if __name__ == '__main__': unittest.main()
