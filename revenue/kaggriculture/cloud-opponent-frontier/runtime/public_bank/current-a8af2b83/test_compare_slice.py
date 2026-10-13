"""Fixed-report consumer checks; synthetic records are not additional games."""
import copy
import unittest
from compare_slice import GRID,index_report,seed_change,physical_state,verdict

def complete_report():
    return {'complete_grid':True,'games':[{'opponent':o,'seed':n,'candidate_seat':s,
        'status':'complete','failure':None,'steps':719,'retained_rows':720,'scores':[200,100]}
        for o,n,s in sorted(GRID)]}

class ComparisonTests(unittest.TestCase):
    def test_complete_grid_and_reordered_rows(self):
        r=complete_report();a=index_report(r);r['games'].reverse();self.assertEqual(a,index_report(r))
    def test_missing_cell(self):
        r=complete_report();r['games'].pop()
        with self.assertRaises(ValueError):index_report(r)
    def test_duplicate_does_not_replace_missing(self):
        r=complete_report();r['games'][-1]=copy.deepcopy(r['games'][0])
        with self.assertRaises(ValueError):index_report(r)
    def test_failure_is_not_an_economic_loss(self):
        for key,value in [('status','failed'),('failure',{'type':'timeout'}),('steps',718),('retained_rows',719)]:
            r=complete_report();r['games'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):index_report(r)
    def test_nonfinite_cash_is_not_comparable(self):
        for v in [float('nan'),float('inf'),True]:
            r=complete_report();r['games'][0]['scores'][0]=v
            with self.subTest(value=v),self.assertRaises(ValueError):index_report(r)
    def test_wrong_seed_and_missing_completion(self):
        r=complete_report();r['games'][0]['seed']=9926003
        with self.assertRaises(ValueError):index_report(r)
        r=complete_report();r['complete_grid']=False
        with self.assertRaises(ValueError):index_report(r)
    def test_seat_correct_verdict(self):
        self.assertEqual((verdict([20,10],0),verdict([20,10],1),verdict([10,10],1)),('W','L','T'))
    def test_only_seed_reductions(self):
        self.assertEqual(seed_change(['BUY_SEED','WHEAT',17],['BUY_SEED','WHEAT',2]),{'product':'WHEAT','removed_units':15})
        self.assertEqual(seed_change(['BUY_SEED','WHEAT',9],[]),{'product':'WHEAT','removed_units':9})
        for a,b in [(['SELL','WHEAT',9],[]),(['BUY_SEED','WHEAT',9],['BUY_SEED','WHEAT',10]),(['BUY_SEED','WHEAT',9],['BUY_SEED','CARROT',9])]:
            self.assertIsNone(seed_change(a,b))
    def test_only_own_money_and_seeds_are_removed_without_mutation(self):
        observations=[{'player':p,'farms':[{'money':1,'tiles':[1]},{'money':2,'tiles':[2]}],
                       'private':{'seeds':{'WHEAT':3},'shed':{'MILK':4}},'market':{'x':5}}
                       for p in (0,1)]
        original=copy.deepcopy(observations);result=physical_state(observations,1)
        self.assertEqual(observations,original)
        for obs in result:
            self.assertEqual(obs['farms'][0]['money'],1);self.assertNotIn('money',obs['farms'][1])
            self.assertEqual(obs['farms'][1]['tiles'],[2]);self.assertEqual(obs['private']['shed'],{'MILK':4})
        self.assertEqual(result[0]['private']['seeds'],{'WHEAT':3});self.assertNotIn('seeds',result[1]['private'])

if __name__=='__main__':unittest.main(verbosity=2)
