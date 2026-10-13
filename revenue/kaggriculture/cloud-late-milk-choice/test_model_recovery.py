# SPDX-License-Identifier: Apache-2.0
"""Recovery checks for the published model and its original panel binding.

Small boundary fixtures isolate model selection. The source-backed cases use
an actual restored frozen SELL actor, unchanged T04 and the pinned interpreter.
No previous test count is imported as execution by this file.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest

from model_choice import ModelMilkChoice, wrap_model_sell, MAIN, MILK_EXIT
from model_panel import load, source, entry_factory
import panel


class Controller:
    def __init__(self, route=MAIN):
        self.cur=route
        self.R={MAIN:[None]*720,MILK_EXIT:[None]*720}
        self.compatible=True
    def _switch_ok(self, route, now):
        return self.compatible


def result(a=100,b=120):
    return {'complete':True,'start_step':577,'end_step':718,'decisions_executed':284,
            'cases':[{'offered_route':MAIN,'status':'complete','final_cash':a},
                     {'offered_route':MILK_EXIT,'status':'complete','final_cash':b}]}


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.controller=Controller()
        self.calls=[]
        self.evaluations=[]
        self.document=result()
        def call(obs,cfg):
            self.calls.append((deepcopy(obs),deepcopy(cfg)))
            return {'farmer':['PASS'],'hands':[],'market':[['SELL','MILK',1]],'tag':'parent'}
        def evaluate(controller,obs,cfg):
            self.evaluations.append(controller)
            return deepcopy(self.document)
        self.wrapper=ModelMilkChoice(call,self.controller,evaluate)
        self.obs={'step':577,'day':24,'hour':1}

    def test_better_complete_tail_changes_same_controller(self):
        self.wrapper.act(self.obs,{})
        self.assertEqual(self.controller.cur,MILK_EXIT)
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.wrapper.last_choice['modeled_advantage'],20)

    def test_reverse_direction(self):
        self.controller.cur=MILK_EXIT
        self.document=result(130,120)
        self.wrapper.act(self.obs,{})
        self.assertEqual(self.controller.cur,MAIN)

    def test_tie_keeps_incumbent(self):
        self.document=result(120,120)
        self.wrapper.act(self.obs,{})
        self.assertEqual(self.controller.cur,MAIN)
        self.assertFalse(self.wrapper.last_choice['changed'])

    def test_before_checkpoint_retains_original_call(self):
        self.obs['step']=433
        self.wrapper.act(self.obs,{})
        self.assertEqual(len(self.evaluations),0)
        self.assertEqual(len(self.calls),1)

    def test_retry_evaluates_once_and_keeps_parent_calls(self):
        self.wrapper.act(self.obs,{})
        self.wrapper.act(self.obs,{})
        self.assertEqual(len(self.evaluations),1)
        self.assertEqual(len(self.calls),2)

    def test_disabled_does_not_model(self):
        self.wrapper.enabled=False
        self.wrapper.act(self.obs,{})
        self.assertEqual(self.evaluations,[])
        self.assertEqual(self.controller.cur,MAIN)

    def test_other_route_does_not_model(self):
        self.controller.cur='other-existing-program'
        self.wrapper.act(self.obs,{})
        self.assertEqual(self.evaluations,[])

    def test_incompatible_program_keeps_original(self):
        self.controller.compatible=False
        self.wrapper.act(self.obs,{})
        self.assertEqual(self.controller.cur,MAIN)
        self.assertEqual(self.evaluations,[])

    def test_changed_configuration_keeps_original(self):
        self.wrapper.act(self.obs,{'episodeSteps':721})
        self.assertEqual(self.controller.cur,MAIN)
        self.assertEqual(self.evaluations,[])

    def test_incomplete_keeps_original(self):
        self.document['complete']=False
        self.wrapper.act(self.obs,{})
        self.assertEqual(self.controller.cur,MAIN)
        self.assertEqual(self.wrapper.last_choice['reason'],'model_incomplete')

    def test_wrong_horizon_keeps_original(self):
        self.document['end_step']=717
        self.wrapper.act(self.obs,{})
        self.assertEqual(self.wrapper.last_choice['reason'],'model_horizon_differs')

    def test_foreign_route_keeps_original(self):
        self.document['cases'][1]['offered_route']='third'
        self.wrapper.act(self.obs,{})
        self.assertEqual(self.wrapper.last_choice['reason'],'model_routes_differ')

    def test_nonfinite_cash_keeps_original(self):
        for value in (float('nan'),float('inf'),None,True,'120'):
            with self.subTest(value=value):
                self.setUp()
                self.document['cases'][1]['final_cash']=value
                self.wrapper.act(self.obs,{})
                self.assertEqual(self.controller.cur,MAIN)
                self.assertEqual(len(self.calls),1)

    def test_exception_preserves_parent_without_exposing_text(self):
        def fail(*args):raise ValueError('PRIVATE-SENTINEL')
        self.wrapper.evaluate=fail
        self.wrapper.act(self.obs,{})
        self.assertEqual(self.controller.cur,MAIN)
        self.assertEqual(len(self.calls),1)
        self.assertNotIn('PRIVATE-SENTINEL',repr(self.wrapper.last_choice))

    def test_baseexception_not_swallowed(self):
        class Cancel(BaseException):pass
        def fail(*args):raise Cancel()
        self.wrapper.evaluate=fail
        with self.assertRaises(Cancel):self.wrapper.act(self.obs,{})
        self.assertEqual(self.calls,[])

    def test_sparse_clock_and_input_nonmutation(self):
        self.obs.pop('step')
        saved=deepcopy(self.obs)
        self.wrapper.act(self.obs,{})
        self.assertEqual(self.obs,saved)
        self.assertEqual(self.calls[0][0]['step'],577)

    def test_parent_exception_not_retried(self):
        calls=[]
        def fail(*args):
            calls.append(1)
            raise TypeError('original parent error')
        self.wrapper.call=fail
        with self.assertRaisesRegex(TypeError,'original parent error'):
            self.wrapper.act(self.obs,{})
        self.assertEqual(calls,[1])

    def test_binding_default_limits_and_single_actor(self):
        class Actor:
            controller=self.controller
            def act(inner,o,c):return {'farmer':['PASS'],'market':[]}
        seen=[]
        def replay(c, routes, obs, cfg, engine, oracle, **kw):
            seen.append((c,routes,kw))
            return result()
        class Limits:
            def __init__(self,**kw):self.__dict__.update(kw)
        bound=wrap_model_sell(Actor(),object(),object(),lambda:None,replay,Limits)
        bound.act(self.obs,{})
        self.assertIs(seen[0][0],self.controller)
        self.assertEqual(seen[0][2]['limits'].seconds,0.6)
        self.assertEqual(seen[0][2]['limits'].decisions,284)

    def test_panel_default_interface_preserved(self):
        import inspect
        parameters=inspect.signature(panel.main).parameters
        self.assertIsNone(parameters['entry_factory'].default)
        self.assertIsNone(parameters['arms'].default)
        self.assertIsNone(parameters['extra_metadata'].default)


def real_case(args):
    root=args.source_root.resolve()
    sell=root/'cloud-titan-composition/vendor/sell'
    sys.path.insert(0,str(sell))
    scheduler=load(sell/'scheduler.py','model_recovery_original_scheduler')
    evaluator=load(root/'cloud-eval/evaluate.py','model_recovery_evaluator')
    oracle=load(args.oracle,'model_recovery_oracle')
    physical=load(args.physical_replay,'model_recovery_physical')
    engine,engine_hashes=evaluator.get_engine(args.engine_dir,prepare=False)
    cfg={k:v.get('default') if isinstance(v,dict) else v for k,v in engine.specification['configuration'].items()}
    cfg['seed']=None
    actor=scheduler.SellScheduler()
    matched=0
    with gzip.open(args.trace,'rt') as f:
        previous=json.loads(next(f))
        assert previous['step']==-1
        for step in range(577):
            current=json.loads(next(f)); assert current['step']==step
            obs=deepcopy(previous['observations'][0]);obs.update(step=step,remainingOverageTime=0)
            assert actor.act(obs,cfg)==current['actions'][0],step
            matched+=1;previous=current
    obs=deepcopy(previous['observations'][0]);obs.update(step=577,remainingOverageTime=0)
    before=deepcopy({**actor.__dict__,'controller':actor.controller.__dict__})
    original_obs=deepcopy(obs)
    report=physical.replay_routes(actor.controller,[MAIN,MILK_EXIT],obs,cfg,engine,
        oracle.simulate_bundle,scenarios={'observed_shops_only':oracle.Scenario()},
        end_step=718,limits=physical.ReplayLimits(seconds=5,decisions=284))
    assert report['complete'] is True
    assert {**actor.__dict__,'controller':actor.controller.__dict__}==before
    assert obs==original_obs
    expected=deepcopy(actor)
    wrapped=ModelMilkChoice(actor.act,actor.controller,lambda *a:report)
    action=wrapped.act(obs,cfg)
    desired=wrapped.last_choice['after'];expected.controller.cur=desired
    assert action==expected.act(obs,cfg)
    assert wrapped.calls==1
    zero_actor=deepcopy(expected)
    expected_zero=deepcopy(zero_actor)
    zero=wrap_model_sell(zero_actor,engine,oracle.simulate_bundle,oracle.Scenario,
        physical.replay_routes,physical.ReplayLimits,seconds=0)
    assert zero.act(obs,cfg)==expected_zero.act(obs,cfg)
    assert zero.last_choice['reason']=='model_incomplete'
    assert zero.calls==1
    return {'matched_saved_prefix_actions':matched,'new_game_initializations':0,
            'modeled_tail_decisions':report['decisions_executed'],
            'original_actor_unchanged_by_model':True,'input_unchanged':True,
            'choice':wrapped.last_choice,'zero_budget_choice':zero.last_choice,
            'source_pins':{'scheduler':source(sell/'scheduler.py'),'oracle':source(args.oracle),
                'physical_replay':source(args.physical_replay),'model':source(Path(__file__).with_name('model_choice.py'))},
            'engine_hashes':engine_hashes,
            'scope':'retained development observation; current shops/no external flows; not paired-game outcome'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--engine-dir',type=Path,required=True)
    p.add_argument('--oracle',type=Path,required=True)
    p.add_argument('--physical-replay',type=Path,required=True)
    p.add_argument('--trace',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    args=p.parse_args()
    stream=io.StringIO()
    r=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(BoundaryTests))
    print(stream.getvalue(),end='')
    report={'boundary_methods':r.testsRun,'failures':len(r.failures),'errors':len(r.errors)}
    if r.wasSuccessful():report['actual_consumer']=real_case(args)
    args.report.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return 0 if r.wasSuccessful() else 1

if __name__=='__main__':raise SystemExit(main())
