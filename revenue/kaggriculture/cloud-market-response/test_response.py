# SPDX-License-Identifier: MIT
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from flow import FlowHistory, FlowInterval, infer_flow
from policy import frozen_module, ResponsePolicy
from sorrel_timeline import project_sale_timeline

class FlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = frozen_module()
    def observations(self, inv, later, step=1, shops=()):
        old = {'step':step, 'market': {'inventory':{'EGG':inv}},
               'town':{'unlocked_shops':list(shops)}}
        new = copy.deepcopy(old); new['step'] += 1; new['market']['inventory']['EGG'] = later
        return old, new
    def infer(self, a, b, own):
        return infer_flow(a, b, {'EGG':own}, 'EGG', {}, self.s.m, self.s.absorption)
    def test_nonfloor_own_sales_subtracted(self):
        a,b=self.observations(10000,10011)
        r=self.infer(a,b,4)
        self.assertTrue(r.exact); self.assertEqual((r.lower,r.upper),(7,7))
    def test_old_shop_copies_used_at_draw(self):
        a,b=self.observations(10000,10003,step=0,shops=('BRUNCH_SPOT','BRUNCH_SPOT'))
        b['town']['unlocked_shops'].append('BRUNCH_SPOT')
        demand=self.s.absorption('EGG',0,a['town']['unlocked_shops'],{})
        self.assertEqual(self.infer(a,b,2).lower,3+demand-2)
    def floor_inventory(self):
        lo,hi=10000,20000
        while self.s.m.market_price('EGG',hi)>1:hi*=2
        while lo<hi:
            mid=(lo+hi)//2
            if self.s.m.market_price('EGG',mid)>1:lo=mid+1
            else:hi=mid
        return lo
    def test_floor_is_censored(self):
        inv=self.floor_inventory()
        a,b=self.observations(inv,inv)
        r=self.infer(a,b,7)
        self.assertFalse(r.exact); self.assertEqual((r.lower,r.upper),(0,100))
    def test_town_recovery_does_not_uncensor(self):
        inv=self.floor_inventory()
        a,b=self.observations(inv,inv-100,step=0)
        r=infer_flow(a,b,{'EGG':7},'EGG',{},self.s.m,lambda *args:100)
        self.assertFalse(r.exact)
    def test_operating_buys_not_mislabeled_sales(self):
        a,b=self.observations(10000,10001)
        self.assertIsNone(infer_flow(a,b,{},'WHEAT',{},self.s.m,self.s.absorption))
    def test_gap_and_negative_supply_unidentified(self):
        a,b=self.observations(10000,9999)
        self.assertIsNone(self.infer(a,b,0))
        b['step']+=1
        self.assertIsNone(self.infer(a,b,0))
    def test_causal_same_hour_window(self):
        h=FlowHistory()
        for t,n in ((2,8),(26,10),(50,12),(74,100)):
            h.add(FlowInterval(t,'EGG',n,n,n,n,'identified'))
        p=h.predict('EGG',74,now=74)
        self.assertEqual((p['lower'],p['point'],p['upper']),(8,10,12))
        self.assertLess(p['latest_training_step'],74)
    def test_censor_not_exact_training(self):
        h=FlowHistory(minimum=1)
        h.add(FlowInterval(1,'EGG',0,100,0,0,'floor_censored'))
        self.assertFalse(h.predict('EGG',25,now=25)['ready'])
        self.assertEqual(h.censored,1)
    def test_duplicate_and_stale_samples(self):
        h=FlowHistory(minimum=1)
        r=FlowInterval(1,'EGG',4,4,4,4,'identified')
        h.add(r);h.add(r)
        self.assertEqual(h.identified,1)
        self.assertFalse(h.predict('EGG',241,now=241)['ready'])
    def test_sorrel_paired_receipts_match_marketpath(self):
        for inv in (9800,10000,1000000):
            model=self.s.MarketPath('EGG',inv,None,[],{},1,4)
            plan=((1,7),(4,5)); rival=((1,6),(3,2))
            value=model.score(plan,12,rival,'paired',terminal=True)
            batches={1:{0:7,1:6},3:{1:2},4:{0:5}}
            frames,_=project_sale_timeline(inv,batches,[4],model.quote,lambda step:0)
            cash=frames[4]['conditional_cash_by_seat']
            self.assertEqual((value[1],value[2]),(cash[0],cash[1]))
    def test_isolated_optimizer_binding(self):
        a=ResponsePolicy();b=ResponsePolicy(enabled=False)
        self.assertIsNot(a.source,b.source)
        self.assertIs(a.source.optimize_lot.__self__,a)
        self.assertIs(b.source.optimize_lot.__self__,b)

class WindowTests(unittest.TestCase):
    def training(self):
        h=FlowHistory(minimum=3)
        for day, quantities in enumerate(((4,0,0),(0,4,0),(0,0,4))):
            for hour,n in enumerate(quantities):
                h.add(FlowInterval(day*24+hour,'EGG',n,n,n,n,'identified'))
        return h
    def test_joint_windows_do_not_erase_shifted_batches(self):
        h=self.training()
        self.assertEqual([h.predict('EGG',t,now=72)['point'] for t in (72,73,74)],[0,0,0])
        p=h.window_prediction('EGG',72,74)
        self.assertEqual((p['lower'],p['point'],p['upper']),(4,4,4))
        self.assertEqual([w['total'] for w in p['windows']],[4,4,4])
        self.assertTrue(all(w['training_end']<72 for w in p['windows']))
    def test_censor_excludes_entire_window(self):
        h=self.training();h.records['EGG'][25]=FlowInterval(25,'EGG',0,100,0,0,'floor_censored')
        self.assertFalse(h.window_prediction('EGG',72,74)['ready'])
    def test_conditional_streams_respect_shared_stock(self):
        h=self.training();streams,p=h.scenarios('EGG',72,74,capacity=3)
        self.assertTrue(streams)
        self.assertTrue(all(sum(n for _,n in s)<=3 for _,s,_ in streams))
    def test_future_or_missing_window_is_not_zero_evidence(self):
        h=self.training();del h.records['EGG'][1]
        self.assertEqual(h.window_prediction('EGG',72,74)['support'],2)
        self.assertEqual(h.scenarios('EGG',72,74)[0],[])
        with self.assertRaises(ValueError):h.window_prediction('EGG',72,96)
    def test_full_inventory_sorrel_guard_covers_town_phase(self):
        p=ResponsePolicy();m=p.source
        k={'item':'EGG','inventory':10000,'params':None,'shops':['BRUNCH_SPOT'],
           'config':{},'now':0,'dates':[0,4], 'quantity':12}
        baseline=((0,12),);candidate=((0,6),(4,6))
        streams=[('zero',0,'paired'),('paired',((0,5),(4,3)),'paired'),
                 ('before',((0,5),(4,3)),'before'),('after',((0,5),(4,3)),'after')]
        model=m.MarketPath('EGG',10000,None,k['shops'],{},0,4)
        a=[model.score(baseline,12,r,x,True) for _,r,x in streams]
        b=[model.score(candidate,12,r,x,True) for _,r,x in streams]
        result=p.confirm_receipts(k,baseline,candidate,streams,a,b)
        self.assertEqual(len(result),4)
        self.assertTrue(all(row['game_cash_margin_delta']==b[i][0]-a[i][0] for i,row in enumerate(result)))

if __name__=='__main__': unittest.main()
