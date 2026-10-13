# SPDX-License-Identifier: Apache-2.0
import unittest
from execution import SellExecution,capped_quantity,marginal_receipt

class Mechanics(unittest.TestCase):
    def test_floor_then_consumption(self):
        q=lambda p,i:max(1,3-i)
        a=marginal_receipt('MILK',0,4,q)
        self.assertEqual((a['cash'],a['market_supply_units'],a['inventory_after']),(7,2,2))
        b=marginal_receipt('MILK',a['inventory_after']-2,1,q)
        self.assertEqual(a['cash']+b['cash'],10)
    def test_band_and_fraction(self):
        n,r=capped_quantity('MILK',0,20,20,lambda p,i:100-i,theta=.05,alpha=.5)
        self.assertEqual((n,r['depth']),(3,6))
    def fixture(self,step=1,orders=None,**extra):
        obs={'step':step,'player':0,'private':{'shed':{'MILK':20}},'farms':[{'tiles':[[None]]}], 'market':{'inventory':{'MILK':0}}}
        cfg={'turnsPerDay':24,'episodeSteps':720,'shedCapacity':100}
        action={'farmer':['PASS'],'hands':[],'market':orders if orders is not None else [['SELL','MILK',20]]}
        args=[obs,cfg,action,{'MILK':20},[],lambda p,i:100-i,lambda p,t:2 if t%4==0 else 0,[]]
        return args
    def test_split_does_not_reset_budget(self):
        e=SellExecution();a=self.fixture(orders=[['SELL','MILK',10],['SELL','MILK',10]])
        r=e.transform(*a);self.assertEqual([o[2] for o in r['market']],[3,0])
        self.assertEqual(e.lots['MILK']['remaining'],20)
        e.observe_fills(2,{'MILK':17});self.assertEqual(e.lots['MILK']['remaining'],17)
        self.assertEqual(e.receipts[-1]['actual_sale_units'],3)
        self.assertIsNone(e.receipts[-1]['market_supply_units'])
    def test_unknown_fill_not_invented(self):
        e=SellExecution();e.transform(*self.fixture());e.observe_fills(2,{'MILK':0})
        self.assertIsNone(e.receipts[-1]['actual_sale_units']);self.assertEqual(e.lots['MILK']['remaining'],20)
    def test_final_and_dayclose(self):
        for step in (22,23,718):
            e=SellExecution();r=e.transform(*self.fixture(step));self.assertEqual(r['market'][0][2],20)
    def test_dependency_preserved(self):
        e=SellExecution();a=self.fixture();a[-1]=[{'market':[['HIRE']]}]
        self.assertEqual(e.transform(*a)['market'][0][2],20)
        a=self.fixture(orders=[['SELL','MILK',20],['BUY_SEED','WHEAT',1]])
        self.assertEqual(SellExecution().transform(*a),a[2])
    def test_capacity_override(self):
        a=self.fixture();a[4]=[{'MILK':80}]
        self.assertEqual(SellExecution().transform(*a)['market'][0][2],20)
    def test_demand_release_not_sliding(self):
        e=SellExecution('demand');a=self.fixture(step=2)
        self.assertEqual(e.transform(*a)['market'][0][2],0)
        a=self.fixture(step=5)
        self.assertEqual(e.transform(*a)['market'][0][2],3)
    def test_remaining_and_stock_limits(self):
        self.assertEqual(capped_quantity('MILK',0,2,1,lambda p,i:100)[0],1)
if __name__=='__main__':unittest.main()
