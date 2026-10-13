# SPDX-License-Identifier: Apache-2.0
"""Offline tests; set TITAN_RUNTIME_ROOT to the preserved canonical runtime."""
from __future__ import annotations
import copy
import itertools
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

import market_response as mr
from runtime_support import HERE, PINS, load_scheduler, load_selected_core, load_engine, replay_plan, validate_runtime

ROOT = Path(os.environ.get('TITAN_RUNTIME_ROOT', '/__missing_TITAN_RUNTIME_ROOT__'))
S, SOURCE = load_scheduler(ROOT)
ENGINE, STRUCT, ENGINE_HASHES = load_engine(ROOT)
FROZEN, FROZEN_SOURCE = load_selected_core(ROOT)
CASES = json.loads((HERE/'CASES.json').read_text())['cases']
COUNTS = {'brute_force_comparisons': 0, 'full_interpreter_pairs': 0, 'full_interpreter_callbacks': 0}


def options(i=0):
    result=copy.deepcopy(CASES[i]['input'])
    result['reference']=tuple(map(tuple,result['reference']))
    return result


def make_model(k):
    return S.MarketPath(k['item'], k['inventory'], k['params'], k['shops'], k['config'],k['now'],k['dates'][-1])


def run_audit(k, plan, **extra):
    return mr.audit_plan(make_model(k), quantity=k['quantity'],reference=k['reference'],candidate=plan,
                         rival_budget=k['rival_quantity'],
                         absorb=lambda t:S.absorption(k['item'],t,k['shops'],k['config']),
                         terminal=k['dates'][-1]==k.get('last',718), **extra)


def stream_value(model, plan, quantity, stream, terminal):
    """Straight replay; no DP, pruning, state coalescing or oracle helpers."""
    sold=sum(q for _,q in plan);orders=dict(plan);pulses={t:(q,a) for t,q,a in stream}
    inv=model.inventory;cash=0
    for step in range(model.now,model.end+1):
        rival,alignment=pulses.get(step,(0,'paired'))
        own_cash,rival_cash,inv=model.joint(inv,orders.get(step,0),rival,alignment)
        cash+=own_cash-rival_cash
        inv-=S.absorption(model.item,step,model.shops,model.config)
    if not terminal:
        cash+=model.single(inv,quantity-sold)[0]
    return cash


def brute_force(model, reference, chosen, quantity, budget, terminal):
    days=list(range(model.now,model.end+1))
    worst=math.inf
    for allocation in itertools.product(range(budget+1), repeat=len(days)):
        if sum(allocation)>budget:continue
        active=[(t,q) for t,q in zip(days,allocation) if q]
        for orientations in itertools.product(('before','paired','after'),repeat=len(active)):
            stream=tuple((t,q,a) for (t,q),a in zip(active,orientations))
            delta=stream_value(model,chosen,quantity,stream,terminal)-stream_value(model,reference,quantity,stream,terminal)
            worst=min(worst,delta)
    return float(worst)


class OracleTests(unittest.TestCase):
    def test_named_green_witnesses_are_negative(self):
        expected=[(-12,12),(-1,1),(-1,2)]
        for i,(worst,named) in enumerate(expected):
            with self.subTest(case=i):
                k=options(i);plan,info=S.optimize_lot(**k);audit=run_audit(k,plan)
                self.assertTrue(audit.complete);self.assertEqual(audit.worst_delta,worst)
                self.assertEqual(info['worst_relative_gain'],named)
                self.assertLessEqual(sum(n for _,n,_ in audit.rival_stream),k['rival_quantity'])
                m=make_model(k)
                self.assertEqual(stream_value(m,plan,k['quantity'],audit.rival_stream,False)-stream_value(m,k['reference'],k['quantity'],audit.rival_stream,False),worst)

    def test_all_seven_products_against_independent_enumeration(self):
        for item,inv,horizon,terminal in itertools.product(S.PRODUCTS,(9997,10067,10113), (1,2),(False,True)):
            for plan in (((604,1),(604+horizon,3)),((604,1),),((604+horizon,4),)):
                with self.subTest(item=item,inventory=inv,horizon=horizon,terminal=terminal,plan=plan):
                    k=options();k.update(item=item,inventory=inv,quantity=4,reference=((604,4),),rival_quantity=2,dates=[604,604+horizon],last=604+horizon if terminal else 718)
                    model=make_model(k);a=run_audit(k,plan)
                    b=brute_force(model,k['reference'],plan,4,2,terminal)
                    self.assertTrue(a.complete);self.assertEqual(a.worst_delta,b)
                    COUNTS['brute_force_comparisons']+=1

    def test_exact_zero_budget(self):
        k=options();k['rival_quantity']=0;p,_=S.optimize_lot(**k);a=run_audit(k,p)
        self.assertTrue(a.complete);self.assertEqual(a.rival_stream,())
        m=make_model(k);self.assertEqual(a.worst_delta,m.score(p,k['quantity'],0,'paired')[0]-m.score(k['reference'],k['quantity'],0,'paired')[0])

    def test_identity_requires_no_work(self):
        k=options();a=run_audit(k,k['reference'],max_transitions=0)
        self.assertTrue(a.complete);self.assertEqual(a.worst_delta,0);self.assertEqual(a.transitions,0)

    def test_partial_search_never_certifies(self):
        k=options();plan,_=S.optimize_lot(**k)
        for cap in (0,1,40):
            with self.subTest(cap=cap):
                a=run_audit(k,plan,max_transitions=cap)
                self.assertFalse(a.complete);self.assertIsNone(a.worst_delta)
                self.assertEqual(a.rival_stream,());self.assertEqual(a.transitions,cap)

    def test_deterministic_tie_witness(self):
        k=options();plan,_=S.optimize_lot(**k)
        self.assertEqual(run_audit(k,plan),run_audit(k,plan))

    def test_plan_validation(self):
        k=options()
        for plan in (((604,25),),((604,1),(604,2)),((603,1),),((606,1),),((True,1),),((604,True),),((604,-1),),((604,1,0),)):
            with self.subTest(plan=plan),self.assertRaises(ValueError):run_audit(k,plan)

    def test_numeric_bounds(self):
        k=options();plan=((605,24),)
        for field,val in (('quantity',True),('quantity',101),('rival_quantity',-1),('rival_quantity',True),('inventory',float('nan'))):
            with self.subTest(field=field,val=val),self.assertRaises(ValueError):
                bad=dict(k);bad[field]=val;run_audit(bad,plan)
        k['dates']=[604,613]
        with self.assertRaises(ValueError):run_audit(k,plan)

    def test_nonfinite_transition_rejected(self):
        model=Mock(now=1,end=1,inventory=10)
        model.joint.return_value=(float('inf'),0,11)
        with self.assertRaises(ValueError):mr.audit_plan(model,quantity=1,reference=((1,1),),candidate=(),rival_budget=0,absorb=lambda t:0)

    def test_bad_consumption_and_terminal_rejected(self):
        k=options();m=make_model(k)
        for f in (lambda t:-1,lambda t:True,lambda t:0.5):
            with self.assertRaises(ValueError):mr.audit_plan(m,quantity=24,reference=k['reference'],candidate=((605,24),),rival_budget=1,absorb=f)
        with self.assertRaises(ValueError):mr.audit_plan(m,quantity=24,reference=k['reference'],candidate=((605,24),),rival_budget=1,absorb=lambda t:0,terminal=1)


class AdapterTests(unittest.TestCase):
    def test_off_is_exact_one_call_delegation(self):
        marker=object();delegate=Mock();delegate.optimize_lot.return_value=marker
        args={'opaque':object()}
        result=mr.select_robust_lot(delegate,**args)
        self.assertIs(result,marker);delegate.optimize_lot.assert_called_once_with(**args)

    def test_off_equal_to_original_for_all_fixtures(self):
        for i in range(len(CASES)):
            k=options(i);saved=copy.deepcopy(k)
            self.assertEqual(mr.select_robust_lot(S,**k),S.optimize_lot(**k));self.assertEqual(k,saved)

    def test_reject_counterexamples(self):
        for i in range(len(CASES)):
            k=options(i);p,info=mr.select_robust_lot(S,enabled=True,**k)
            self.assertEqual(mr.normalize_plan(p,quantity=k['quantity'],now=k['now'],end=k['dates'][-1]),k['reference'])
            self.assertEqual(info['market_response_audit']['status'],'reference_preserved')
            self.assertTrue(info['feasible'])

    def test_positive_safe_candidate_survives(self):
        k=options();k['rival_quantity']=0
        p,info=mr.select_robust_lot(S,enabled=True,**k)
        self.assertNotEqual(p,k['reference']);self.assertEqual(info['market_response_audit']['status'],'finite_family_positive')
        self.assertGreater(info['market_response_audit']['worst_delta'],0)
        self.assertEqual((p,{a:b for a,b in info.items() if a!='market_response_audit'}),S.optimize_lot(**k))

    def test_global_budget_returns_safe_reference(self):
        k=options();p,info=mr.select_robust_lot(S,enabled=True,audit_transition_budget=0,**k)
        self.assertEqual(p,k['reference']);self.assertEqual(info['market_response_audit']['transitions'],0)
        self.assertGreater(info['market_response_audit']['incomplete_plans'],0)

    def test_physical_reference_infeasible_preserves_original_rescue(self):
        k=options();k['capacity_ok']=lambda p:dict(p).get(604,0)<24
        old,oldinfo=S.optimize_lot(**k);new,info=mr.select_robust_lot(S,enabled=True,audit_transition_budget=0,**k)
        self.assertTrue(oldinfo['forced_feasibility']);self.assertEqual(new,old)
        self.assertEqual({a:b for a,b in info.items() if a!='market_response_audit'},oldinfo)
        self.assertFalse(info['market_response_audit']['certified'])

    def test_minimum_now_forced_reference_preserved(self):
        k=options();k.update(reference=((605,24),),minimum_now=12)
        old,oldinfo=S.optimize_lot(**k);new,info=mr.select_robust_lot(S,enabled=True,**k)
        self.assertTrue(oldinfo['forced_feasibility']);self.assertEqual(new,old)
        self.assertEqual(info['market_response_audit']['status'],'skipped_infeasible_reference')

    def test_original_physical_gate_composes(self):
        k=options();k['rival_quantity']=0;k['capacity_ok']=lambda p:dict(p).get(604,0)>=18
        p,info=mr.select_robust_lot(S,enabled=True,**k)
        self.assertGreaterEqual(dict(p).get(604,0),18);self.assertTrue(info['feasible'])

    def test_enabled_requires_boolean(self):
        with self.assertRaises(ValueError):mr.select_robust_lot(S,enabled=1,**options())


class EngineTests(unittest.TestCase):
    def pair(self,k,plan,stream,seat):
        b=replay_plan(ENGINE,STRUCT,k,k['reference'],stream,seat)
        c=replay_plan(ENGINE,STRUCT,k,plan,stream,seat)
        COUNTS['full_interpreter_pairs']+=1
        COUNTS['full_interpreter_callbacks']+=len(b['timeline'])+len(c['timeline'])
        return b,c

    def test_counterexamples_full_interpreter_both_seats(self):
        for i,expected in enumerate(((-2,10,-12),(1,2,-1),(341,342,-1))):
            k=options(i);p,info=S.optimize_lot(**k);a=run_audit(k,p)
            for seat in (0,1):
                with self.subTest(case=i,seat=seat):
                    b,c=self.pair(k,p,a.rival_stream,seat)
                    self.assertEqual((c['own_cash']-b['own_cash'],c['rival_cash']-b['rival_cash'],c['margin']-b['margin']),expected)
                    self.assertEqual(c['market'],b['market']);self.assertEqual(c['privates'],b['privates'])
                    self.assertEqual(b['timeline'][0]['own_orders'][0],['BUY_SEED','WHEAT',1])

    def test_product_alignment_floor_matrix(self):
        for item,inventory,alignment,seat in itertools.product(S.PRODUCTS,(9997,10067,10113),('before','paired','after'),(0,1)):
            with self.subTest(item=item,inventory=inventory,alignment=alignment,seat=seat):
                k=options();k.update(item=item,inventory=inventory,quantity=4,reference=((604,4),),rival_quantity=3)
                plan=((604,1),(605,3));stream=((604,1,alignment),(605,2,alignment))
                m=make_model(k)
                expected=stream_value(m,plan,4,stream,False)-stream_value(m,k['reference'],4,stream,False)
                b,c=self.pair(k,plan,stream,seat)
                self.assertEqual(c['margin']-b['margin'],expected)
                self.assertEqual(c['privates'],b['privates'])


class SourceAndCLITests(unittest.TestCase):
    def fixture_root(self,temp):
        root=Path(temp)
        for p in ('scheduler.py',*PINS['dependencies']):
            target=root/p;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/p,target)
        return root

    def test_exact_source_authentication(self):
        self.assertTrue(validate_runtime(ROOT)['exact_predecessor_file'])

    def test_unrelated_prefix_extension_does_not_block_market_audit(self):
        with tempfile.TemporaryDirectory() as t:
            root=self.fixture_root(t);p=root/'scheduler.py';p.write_text(p.read_text()+'\ndef unrelated_prefix_probe(rows):\n    return rows[:10]\n')
            receipt=validate_runtime(root)
            self.assertFalse(receipt['exact_predecessor_file']);self.assertTrue(receipt['all_market_mechanism_ast_nodes_match'])

    def test_mechanism_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=self.fixture_root(t);p=root/'scheduler.py';p.write_text(p.read_text().replace("if alignment=='before':","if alignment=='before_CHANGED':"))
            with self.assertRaises(ValueError):validate_runtime(root)

    def test_dependency_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=self.fixture_root(t);p=root/'mechanics.py';p.write_text(p.read_text()+'\n# changed\n')
            with self.assertRaises(ValueError):validate_runtime(root)

    def test_cli_success_and_error_output_custody(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)/'result.json'
            command=[sys.executable,*(['-O'] if sys.flags.optimize else []),str(HERE/'run_audit.py'),'--runtime-root',str(ROOT),'--engine-check','--screen','--output',str(out)]
            result=subprocess.run(command,capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads(out.read_text());self.assertEqual(len(report['cases']),3)
            self.assertEqual(report['optimization_mode'],sys.flags.optimize)
            old=out.read_bytes();command[command.index('--runtime-root')+1]=t
            bad=subprocess.run(command,capture_output=True,text=True,timeout=20)
            self.assertEqual(bad.returncode,2);self.assertEqual(out.read_bytes(),old)


class FrozenConsumerTests(unittest.TestCase):
    def test_current_frozen_core_has_same_three_witnesses(self):
        for i in range(len(CASES)):
            k=options(i);standalone,baseinfo=S.optimize_lot(**k);frozen,info=FROZEN.optimize_lot(**k)
            self.assertEqual(frozen,standalone)
            self.assertEqual(info['scenarios'],baseinfo['scenarios'])
            self.assertEqual(info['worst_relative_gain'],baseinfo['worst_relative_gain'])
            model=FROZEN.MarketPath(k['item'],k['inventory'],k['params'],k['shops'],k['config'],k['now'],k['dates'][-1])
            a=mr.audit_plan(model,quantity=k['quantity'],reference=k['reference'],candidate=frozen,
                            rival_budget=k['rival_quantity'],absorb=lambda t:FROZEN.absorption(k['item'],t,k['shops'],k['config']))
            self.assertEqual(a.worst_delta,(-12,-1,-1)[i])
            selected,screen=mr.select_robust_lot(FROZEN,enabled=True,**k)
            self.assertEqual(selected,k['reference'])

    def test_frozen_off_identity_for_each_acceptance_rule(self):
        for rule in ('strict','expected_downside','minimax_regret'):
            k=options(1);k['config']['sellAcceptanceRule']=rule
            expected=FROZEN.optimize_lot(**k)
            self.assertEqual(mr.select_robust_lot(FROZEN,**k),expected)
            selected,screen=mr.select_robust_lot(FROZEN,enabled=True,**k)
            a=run_audit(k,selected)
            self.assertTrue(a.complete);self.assertGreaterEqual(a.worst_delta,0)

    def test_frozen_forced_rescue_is_unchanged(self):
        k=options(1);k['capacity_ok']=lambda p:dict(p).get(604,0)<8
        old,info=FROZEN.optimize_lot(**k);new,result=mr.select_robust_lot(FROZEN,enabled=True,**k)
        self.assertEqual(new,old);self.assertTrue(info['forced_feasibility'])
        self.assertEqual(result['market_response_audit']['status'],'skipped_infeasible_reference')

    def test_source_binding_matches_frozen_caller(self):
        self.assertTrue(FROZEN_SOURCE['frozen_caller_source_matches'])
        self.assertFalse(FROZEN_SOURCE['full_frozen_transform_executed'])


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    print('EXECUTED_CASE_COUNTS',json.dumps(COUNTS,sort_keys=True))
    raise SystemExit(not result.wasSuccessful())
