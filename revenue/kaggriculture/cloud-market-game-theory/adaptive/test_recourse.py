# SPDX-License-Identifier: Apache-2.0
"""Focused recourse economics and actual selected-action/ASH integration."""
from copy import deepcopy
import gzip
import importlib.util
import json
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from recourse import compile_policy, choose_observed, weak_choice


class RecourseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case=json.loads(gzip.decompress((HERE/'results/correlated-scan.json.gz').read_bytes()))['findings'][0]
        cls.engine=json.loads(gzip.decompress((HERE/'results/engine-recourse.json.gz').read_bytes()))['cases'][0]
        spec=importlib.util.spec_from_file_location('tested_adaptive_runtime',HERE/'runtime.py')
        cls.runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.runtime)

    def test_explicit_weak_dominance_objective(self):
        self.assertEqual(weak_choice([[0,0],[15,-20]],[0,1]),0)
        self.assertEqual(weak_choice([[0,0],[15,-20]],[0]),1)
        self.assertEqual(weak_choice([[0,0],[0,0]],[0,1]),0)
        self.assertEqual(weak_choice([[0,0],[0,1]],[0,1]),1)

    def test_actual_receipt_table_requires_observation(self):
        p=self.case['policy']
        self.assertEqual(p['static_choice'],0)
        self.assertEqual(min(p['causal_deltas']),0)
        self.assertGreater(max(p['causal_deltas']),0)
        self.assertEqual(p['choices']['10000'],3)
        self.assertEqual(p['choices']['9998'],0)

    def test_same_public_projection_and_unknown(self):
        p=self.case['policy']
        obs={'step':242,'market':{'inventory':{'EGG':10000}}}
        other=deepcopy(obs);other['farms']=[{'money':-1000},{'money':1000000}]
        self.assertEqual(choose_observed(p,obs,'EGG'),choose_observed(p,other,'EGG'))
        other['market']['inventory']['EGG']=123456
        self.assertIsNone(choose_observed(p,other,'EGG'))

    def test_different_prefix_rejected(self):
        case=self.case;src=self.runtime.math
        model=src.MarketPath('EGG',9998,None,case['shops'],{},241,249)
        plans=deepcopy(case['policy']['plans']);plans[1]['sales']=[[241,2]]
        with self.assertRaises(ValueError):
            compile_policy(model,plans,2,case['streams'],242,src.absorption)

    def fixture(self,step,column=28):
        obs=deepcopy(self.engine['seats'][0]['adaptive'][column]['branch_observation'])
        obs.update(step=step,day=step//24,hour=step%24)
        if step==241:obs['market']['inventory']['EGG']=9998
        base={'farmer':['PASS'],'hands':[],'market':[[]], 'consumer_tag':'preserved'}
        future={t:[[]] for t in range(step+1,250)}
        future[249]=[[],['SELL','EGG',2]]
        projection={'observed_step':step,'end_step':249,'stock_events':[],
                    'future_market':future}
        ledger=self.runtime.sale.ProjectionLedger(obs,{},base,{'EGG':2},projection,None,None,8)
        return obs,base,ledger

    def test_actual_ash_suffix_and_retry(self):
        policy=self.runtime.AdaptiveTransform()
        obs,base,ledger=self.fixture(241)
        offer={'tree':self.case['policy'],'item':'EGG','quantity':2,'end':249}
        self.assertEqual(policy.transform(obs,{},base,ledger=ledger,offers=[offer]),base)
        self.assertEqual(policy.counts['admissions'],1)
        obs,base,ledger=self.fixture(242)
        # The current inherited baseline has one vacant slot before the suffix.
        action=policy.transform(obs,{},base,ledger=ledger)
        self.assertEqual(action['market'],[[],['SELL','EGG',1]])
        self.assertEqual(action['consumer_tag'],'preserved')
        self.assertEqual(policy.transform(obs,{},base,ledger=ledger),action)
        self.assertEqual(policy.counts['branches'],1)
        self.assertEqual(policy.selector.draws,0)
        self.assertEqual(policy.selector.active['plan_index'],3)

    def test_unknown_and_cash_obstruction_preserve_fallback(self):
        for unknown in (True,False):
            policy=self.runtime.AdaptiveTransform()
            obs,base,ledger=self.fixture(241)
            policy.transform(obs,{},base,ledger=ledger,offers=[{'tree':self.case['policy'],'item':'EGG','quantity':2,'end':249}])
            obs,base,ledger=self.fixture(242)
            if unknown:obs['market']['inventory']['EGG']=123456
            else:ledger.cash_min[(242,'before_market')]=1000
            self.assertEqual(policy.transform(obs,{},base,ledger=ledger),base)
            self.assertIsNone(policy.selector.active)


if __name__=='__main__':unittest.main()
