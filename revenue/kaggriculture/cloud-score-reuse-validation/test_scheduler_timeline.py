#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Differential regressions against the original immutable SELL implementation."""
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
import unittest
from unittest.mock import patch

BASE=None
CAND=None
COUNTS={'direct_score_cases':0,'prepared_score_cases':0,'optimizer_cases':0}


def load(path: Path,name: str):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def model(mod, item='MILK', inventory=10025, now=23,end=31,shops=None,config=None):
    return mod.MarketPath(item,inventory,None,
                         list(mod.m.SHOPS) if shops is None else shops,
                         {} if config is None else config,now,end)


class TimelineTests(unittest.TestCase):
    def test_01_original_source_identity(self):
        self.assertEqual(hashlib.sha256(Path(BASE.__file__).read_bytes()).hexdigest(),
                         '32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9')

    def test_02_randomized_score_differential(self):
        rng=random.Random(20260908)
        for case in range(1800):
            item=rng.choice(BASE.m.PRODUCTS)
            now=rng.choice([0,1,3,4,22,23,24,287,710,716,718])
            end=now+rng.choice([0,1,2,3,8,24])
            inventory=rng.choice([-100,9500,9999,10000,10050,10100,10200,11000,100000])
            quantity=rng.randrange(0,61)
            shops=rng.sample(list(BASE.m.SHOPS),rng.randrange(9))
            cfg={'townShopSellInterval':rng.choice([1,3,4,7]),
                 'townCenterSellInterval':rng.choice([1,12,24])}
            dates=[rng.randrange(now,end+1) for _ in range(rng.randrange(0,5))]
            plan=tuple((d,rng.randrange(-2,quantity+4)) for d in dates)
            rival=(rng.randrange(41) if case%2 else
                   tuple((rng.randrange(now-1,end+2),rng.randrange(41)) for _ in range(4)))
            alignment=rng.choice(['paired','before','after'])
            terminal=bool(case%3==0)
            a=model(BASE,item,inventory,now,end,shops,cfg)
            b=model(CAND,item,inventory,now,end,shops,cfg)
            expected=a.score(plan,quantity,rival,alignment,terminal)
            actual=b.score(plan,quantity,rival,alignment,terminal)
            self.assertEqual(expected,actual,(case,item,plan,rival,alignment))
            COUNTS['direct_score_cases']+=1
            if hasattr(b, '_score_timeline'):
                compiled=tuple(b._score_timeline(rival))
                self.assertEqual(expected,b.score(plan,quantity,rival,alignment,terminal,_timeline=compiled))
                COUNTS['prepared_score_cases']+=1

    def test_03_optimizer_complete_reports_and_capacity_calls(self):
        rng=random.Random(829741)
        for case in range(96):
            quantity=rng.randrange(0,29)
            now=rng.choice([0,23,24,288,600,714,716,718])
            end=min(718,now+rng.choice([0,1,3,8]))
            dates=sorted({now,end,min(end,now+1),min(end,now+4)})
            reference=((now,quantity),) if case%2 else ((end,quantity),)
            kwargs=dict(item=rng.choice(BASE.PRODUCTS),quantity=quantity,
                        inventory=rng.choice([9700,9999,10050,10200,11000]),params=None,
                        shops=rng.sample(list(BASE.m.SHOPS),rng.randrange(9)),
                        config={},now=now,dates=dates,reference=reference,
                        rival_quantity=rng.randrange(31),minimum_now=rng.randrange(quantity+2),last=718)
            calls_a=[];calls_b=[]
            def capacity_a(plan):
                calls_a.append(plan)
                return sum(q for t,q in plan if t>now)<=max(0,quantity-2)
            def capacity_b(plan):
                calls_b.append(plan)
                return sum(q for t,q in plan if t>now)<=max(0,quantity-2)
            if case%3:
                expected=BASE.optimize_lot(**kwargs,capacity_ok=capacity_a)
                actual=CAND.optimize_lot(**kwargs,capacity_ok=capacity_b)
                self.assertEqual(calls_a,calls_b)
            else:
                expected=BASE.optimize_lot(**kwargs)
                actual=CAND.optimize_lot(**kwargs)
            self.assertEqual(expected,actual,(case,kwargs))
            COUNTS['optimizer_cases']+=1

    def test_04_shop_and_period_changes_between_direct_scores(self):
        for mod in (BASE,CAND):
            shops=['PIZZA_SHOP'];cfg={'townShopSellInterval':4}
            m=model(mod,shops=shops,config=cfg)
            first=m.score(((31,30),),30,0,'paired')
            shops.extend(['ICE_CREAM_SHOP','SMOOTHIE_SHOP'])
            cfg['townShopSellInterval']=1
            second=m.score(((31,30),),30,0,'paired')
            fresh=model(mod,shops=shops,config=cfg).score(((31,30),),30,0,'paired')
            self.assertEqual(second,fresh)
            self.assertNotEqual(first,second)

    def test_05_fresh_optimization_observation_has_no_reused_timeline(self):
        kwargs=dict(item='MILK',quantity=26,inventory=10050,params=None,shops=[],config={},
                    now=23,dates=[23,24,27,31],reference=((23,26),),rival_quantity=18,last=718)
        first=CAND.optimize_lot(**kwargs)
        self.assertEqual(first,BASE.optimize_lot(**kwargs))
        kwargs['shops']=['PIZZA_SHOP','ICE_CREAM_SHOP','SMOOTHIE_SHOP']
        kwargs['config']={'townShopSellInterval':1,'townCenterSellInterval':1}
        second=CAND.optimize_lot(**kwargs)
        self.assertEqual(second,BASE.optimize_lot(**kwargs))
        self.assertNotEqual(first,second)

    def test_06_floor_admission_and_scalar_tuple_parity(self):
        for mod in (BASE,CAND):
            m=model(mod,inventory=100000,shops=[])
            self.assertEqual(m.quote(100000),1)
            self.assertEqual(m._joint(100000,20,30,'paired'),(20,30,100000))
            self.assertEqual(m.score(((23,20),),20,30,'paired'),
                             m.score(((23,20),),20,((23,30),),'paired'))

    def test_07_duplicate_rival_timestamps_keep_last_value(self):
        for mod in (BASE,CAND):
            m=model(mod)
            self.assertEqual(m.score(((25,15),),15,((24,3),(24,18)),'paired'),
                             m.score(((25,15),),15,((24,18),),'paired'))

    def test_08_inputs_are_not_mutated(self):
        kwargs=dict(item='STRAWBERRY',quantity=19,inventory=10006,params=None,
                    shops=['BRUNCH_SPOT'],config={},now=23,dates=[23,24,27,31],
                    reference=((23,19),),rival_quantity=8,last=718)
        before=copy.deepcopy(kwargs)
        CAND.optimize_lot(**kwargs)
        self.assertEqual(kwargs,before)

    def test_09_capacity_exception_propagates(self):
        def stop(_):raise RuntimeError('cancelled-capacity-consumer')
        for mod in (BASE,CAND):
            with self.assertRaisesRegex(RuntimeError,'cancelled-capacity-consumer'):
                mod.optimize_lot(item='EGG',quantity=9,inventory=10000,params=None,shops=[],
                                 config={},now=23,dates=[23,24,27],reference=((23,9),),
                                 rival_quantity=3,capacity_ok=stop,last=718)

    def test_10_original_zero_interval_error_is_not_suppressed(self):
        for mod in (BASE,CAND):
            m=model(mod,config={'townShopSellInterval':0})
            with self.assertRaises(ZeroDivisionError):m.score((),0,0,'paired')

    def test_11_absorption_calls_are_bounded_by_scenarios_not_plans(self):
        counts={}
        kwargs=dict(item='STRAWBERRY',quantity=40,inventory=10008,params=None,
                    shops=['BRUNCH_SPOT','SMOOTHIE_SHOP'],config={},now=23,
                    dates=[23,24,27,31],reference=((23,40),),rival_quantity=22,last=718)
        outputs=[]
        for name,mod in [('baseline',BASE),('candidate',CAND)]:
            owner=getattr(mod,'_score_absorption_owner',mod)
            with patch.object(owner,'absorption',wraps=owner.absorption) as fn:
                outputs.append(mod.optimize_lot(**kwargs));counts[name]=fn.call_count
        self.assertEqual(*outputs)
        self.assertEqual(counts['candidate'],getattr(CAND,'_expected_absorption_calls',5*9))
        self.assertGreater(counts['baseline'],counts['candidate']*100)
        COUNTS['absorption_call_witness']=counts


def main():
    global BASE,CAND
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--existing-core',action='store_true',help='Use the already-packaged core score method, not the prototype.')
    args=parser.parse_args()
    sys.path.insert(0,str(args.baseline))
    BASE=load(args.baseline/'scheduler.py','elm_baseline_scheduler')
    CAND=load(args.candidate/'scheduler.py','elm_candidate_scheduler')
    if args.existing_core:
        core=load(args.candidate/'selected_sell_core.py','elm_existing_core')
        CAND.MarketPath.score=core.MarketPath.score
        CAND._score_absorption_owner=core
        CAND._expected_absorption_calls=9
    started=time.perf_counter()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TimelineTests))
    report={'successful':result.wasSuccessful(),'tests':result.testsRun,
            'failures':len(result.failures),'errors':len(result.errors),'skips':len(result.skipped),
            'elapsed_seconds':time.perf_counter()-started,**COUNTS,'new_full_games':0,
            'mode':'existing_core' if args.existing_core else 'private_prototype'}
    args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    raise SystemExit(0 if result.wasSuccessful() else 1)

if __name__=='__main__':main()
