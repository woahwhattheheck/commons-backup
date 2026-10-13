import copy
import unittest
from entrypoint import load_scheduler
from sell_backend import make_optimizer

class SellBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = load_scheduler()
    def args(self, **kw):
        d=dict(item='CARROT',quantity=12,inventory=10000,params=None,
               shops=['PET_CAFE'],config={},now=716,dates=(716,717,718),
               reference=((716,12),),rival_quantity=12,last=718)
        d.update(kw);return d
    def test_complete_vectors_match_existing_scorer(self):
        kw=self.args();before=copy.deepcopy(kw)
        p,info=make_optimizer(self.s,seconds=1,max_transitions=20000)(**kw)
        self.assertEqual(info['search']['completed_depth'],3)
        self.assertEqual(kw,before)
        model=self.s.MarketPath('CARROT',10000,None,['PET_CAFE'],{},716,718)
        for name,r,a in [('no_rival',0,'paired'),('observed_paired',12,'paired'),('observed_later_order',12,'after'),('observed_next_turn',((717,12),),'paired')]:
            exact=model.score(p,12,r,a,True)
            self.assertEqual(info['scenarios'][name]['relative_value'],exact[0])
            self.assertEqual(info['scenarios'][name]['own_receipts'],exact[1])
            self.assertEqual(info['scenarios'][name]['rival_receipts'],exact[2])
        self.assertGreaterEqual(info['worst_relative_gain'],0)
    def test_terminal_carry_zero(self):
        p,info=make_optimizer(self.s,seconds=1)(**self.args(now=718,dates=(718,),reference=((718,12),),rival_quantity=0))
        self.assertEqual(sum(q for _,q in p),12)
    def test_budget_exhaustion_preserves_reference(self):
        kw=self.args();p,info=make_optimizer(self.s,seconds=0)(**kw)
        self.assertEqual(p,self.s.optimize_lot(**kw)[0]);self.assertEqual(info['search']['status'],'unscored_fallback')
    def test_minimum_cash_release_preserved(self):
        p,info=make_optimizer(self.s,seconds=1,max_transitions=20000)(**self.args(minimum_now=12))
        self.assertEqual(dict(p)[716],12)
    def test_capacity_checker_retained(self):
        only=lambda plan:dict(plan).get(716,0)==12
        p,info=make_optimizer(self.s,seconds=1,max_transitions=20000)(**self.args(capacity_ok=only))
        self.assertTrue(only(p))
    def test_legacy_feasibility_recovery_is_explicit(self):
        p,info=make_optimizer(self.s,seconds=0)(**self.args(reference=((716,0),),minimum_now=2))
        self.assertEqual(info['search']['status'],'legacy_feasibility_recovery')
        self.assertTrue(info['feasible'])
    def test_completed_incumbent_receipt_survives_zero_budget(self):
        kw=self.args(quantity=40,reference=((716,40),))
        expected,receipt=self.s.optimize_lot(**kw)
        actual,info=make_optimizer(self.s,seconds=0)(**kw)
        self.assertEqual(expected,actual)
        for key,value in receipt.items():self.assertEqual(info[key],value)
    def test_augmented_plan_dominates_completed_incumbent(self):
        kw=self.args(quantity=16,reference=((716,16),))
        original,receipt=self.s.optimize_lot(**kw)
        plan,info=make_optimizer(self.s,seconds=10,max_transitions=50000)(**kw)
        for name,old in receipt['scenarios'].items():
            self.assertGreaterEqual(info['scenarios'][name]['relative_value'],old['relative_value'])
    def test_invalid_dates(self):
        with self.assertRaises(ValueError):make_optimizer(self.s)(**self.args(dates=(717,716)))
    def test_floor_market_has_no_false_supply(self):
        kw=self.args(item='MELON',inventory=12000,rival_quantity=100)
        p,info=make_optimizer(self.s,seconds=1,max_transitions=20000)(**kw)
        self.assertEqual(info['scenarios']['no_rival']['own_receipts'],12)
    def test_cache_ablation_identical_complete_plan(self):
        kw=self.args(quantity=8,reference=((716,8),))
        a,ai=make_optimizer(self.s,seconds=10,max_transitions=50000)(**kw)
        b,bi=make_optimizer(self.s,seconds=10,max_transitions=50000,cache=False)(**kw)
        self.assertEqual(a,b);self.assertEqual(ai['scenarios'],bi['scenarios'])
        self.assertLess(ai['search']['transitions'],bi['search']['transitions'])

if __name__=='__main__':unittest.main()
