# SPDX-License-Identifier: Apache-2.0
"""Shared-prefix invariants and opt-in tests against the existing pinned T04."""
from copy import deepcopy
from dataclasses import dataclass, field
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import physical_replay as replay

@dataclass
class Scenario:
    market_deltas: dict = field(default_factory=dict)
    new_shops: dict = field(default_factory=dict)
    new_weeds: dict = field(default_factory=dict)
    label: str = 'constructed'

class PrefixBoundaryTests(unittest.TestCase):
    def test_first_different_pre_market_step(self):
        self.assertEqual(replay._common_prefix_stop({'a':Scenario(),'b':Scenario(market_deltas={5:{'MILK':2}})},2,9),4)
    def test_eod_injection_not_next_observation(self):
        self.assertEqual(replay._common_prefix_stop({'a':Scenario(),'b':Scenario(new_shops={287:('YARN_STORE',)})},226,718),286)
    def test_weed_injection(self):
        self.assertEqual(replay._common_prefix_stop({'a':Scenario(),'b':Scenario(new_weeds={23:((1,2),)})},22,25),22)
    def test_identical_events_ignore_evidence_label(self):
        self.assertEqual(replay._common_prefix_stop({'a':Scenario(new_shops={23:('BAKERY',)},label='a'),'b':Scenario(new_shops={23:('BAKERY',)},label='b')},22,25),25)
    def test_current_event_has_no_reusable_prefix(self):
        self.assertEqual(replay._common_prefix_stop({'a':Scenario(),'b':Scenario(market_deltas={226:{'MILK':1}})},226,718),225)
    def test_outside_horizon_not_injected(self):
        self.assertEqual(replay._common_prefix_stop({'a':Scenario(),'b':Scenario(new_shops={23:('BAKERY',),800:('YARN_STORE',)})},226,718),718)
    def test_unknown_schema_uses_original_path(self):
        self.assertEqual(replay._common_prefix_stop({'a':{},'b':{}},226,718),225)
        @dataclass
        class Extended(Scenario):
            extra: int=1
        self.assertEqual(replay._common_prefix_stop({'a':Extended(),'b':Extended()},226,718),225)
    def test_string_event_keys_use_original_path(self):
        self.assertEqual(replay._common_prefix_stop({'a':Scenario(),'b':Scenario(new_shops={'23':('YARN_STORE',)})},22,25),21)
    def test_single_world_uses_original_path(self):
        self.assertEqual(replay._common_prefix_stop({'a':Scenario()},22,25),21)
    def test_no_common_subset_is_chosen(self):
        self.assertEqual(replay._common_prefix_stop({'a':Scenario(),'b':Scenario(new_shops={20:('YARN_STORE',)}),'c':Scenario(market_deltas={4:{'MILK':1}})},2,25),3)
    def test_join_receipts_and_counters(self):
        prefix=dict(start_step=2,end_step=3,cash_gain=7,cash_ledger=[{'step':2,'cash_delta':7}],
            actions={2:{'farmer':['PASS']},3:{}},labor_actions=2,consumed_inputs={'WHEAT':1},discarded_stock={'MILK':3})
        suffix=dict(start_step=4,end_step=5,cash_gain=-2,cash_ledger=[{'step':4,'cash_delta':-2}],
            actions={4:{},5:{}},labor_actions=3,consumed_inputs={'WHEAT':2,'FERTILIZER':1},discarded_stock={'MILK':4},farm={'money':15})
        before=deepcopy((prefix,suffix))
        out=replay._join_results(prefix,suffix)
        self.assertEqual(out['cash_gain'],5);self.assertEqual(out['labor_actions'],5)
        self.assertEqual(out['consumed_inputs'],{'WHEAT':3,'FERTILIZER':1})
        self.assertEqual(out['discarded_stock'],{'MILK':7})
        self.assertEqual((prefix,suffix),before)
        out['actions'][2]['farmer'][0]='EAST'
        self.assertEqual(prefix,before[0])
    def test_noncontiguous_join_is_error(self):
        with self.assertRaises(ValueError):replay._join_results({'end_step':3},{'start_step':5})

class Controller:
    def __init__(self,switch=None):
        self.cur='main';self.R={v:[{} for _ in range(720)] for v in ('main','other')}
        self.trace=[];self.alias=self.trace;self.switch=switch;self.calls=0
    def _switch_ok(self,route,step):return True
    def act(self,view):
        assert self.alias is self.trace
        self.calls+=1;self.trace.append(view['step'])
        if view['step']==self.switch:self.cur='other'
        qty=1+(self.cur=='other')+("YARN_STORE" in view['town']['unlocked_shops'])
        return {'farmer':['PASS'],'hands':[],'market':[['SELL','WOOL',qty]]}

@unittest.skipUnless(os.environ.get('OSPREY_RILL_EVIDENCE'),'Set OSPREY_RILL_EVIDENCE to the existing RILL evidence root')
class NativeReuseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from check_prefix_reuse import setup
        cls.c=setup(Path(os.environ['OSPREY_RILL_EVIDENCE']))
    def setUp(self):
        self.obs=deepcopy(self.c.obs);self.obs.update(step=22,day=0,hour=22)
        self.cfg=deepcopy(self.c.cfg);self.cfg['episodeSteps']=30
        self.actor=Controller(switch=23)
        self.scenarios={'known':self.c.oracle.Scenario(label='known'),
            'future':self.c.oracle.Scenario(new_shops={23:('YARN_STORE',)},label='future')}
    def run_case(self,reuse=True,**kwargs):
        params=dict(scenarios=self.scenarios,end_step=25,limits=replay.ReplayLimits(seconds=30,decisions=100))
        params.update(kwargs)
        return replay.replay_routes(self.actor,('main','other'),self.obs,self.cfg,self.c.engine,self.c.oracle.simulate_bundle,
            reuse_scenario_prefixes=reuse,**params)
    def comparison(self):
        before=deepcopy((self.obs,self.cfg,self.actor.__dict__,self.scenarios))
        old=self.c.original.replay_routes(self.actor,('main','other'),self.obs,self.cfg,self.c.engine,self.c.oracle.simulate_bundle,
            scenarios=self.scenarios,end_step=25,limits=self.c.original.ReplayLimits(seconds=30,decisions=100))
        new=self.run_case()
        self.assertTrue(old['complete']);self.assertTrue(new['complete'])
        self.assertEqual(new['cases'],old['cases'])
        self.assertEqual((self.obs,self.cfg,self.actor.__dict__,self.scenarios),before)
        return old,new
    def test_actual_oracle_case_outputs_exact(self):
        old,new=self.comparison()
        self.assertEqual(old['decisions_executed'],16);self.assertEqual(new['decisions_executed'],14)
    def test_second_seat_private_binding(self):
        self.obs['player']=1
        self.comparison()
    def test_eod_equal_prefix_then_market_difference(self):
        self.scenarios={'a':self.c.oracle.Scenario(new_shops={23:('BAKERY',)}),
            'b':self.c.oracle.Scenario(new_shops={23:('BAKERY',)},market_deltas={24:{'WOOL':9}})}
        _,new=self.comparison()
        self.assertEqual(new['prefix_reuse']['common_through_step'],23)
        self.assertEqual(new['cases'][1]['active_routes'][2]['active_route'],'other')
    def test_labels_only_entire_horizon_reused(self):
        self.scenarios={k:self.c.oracle.Scenario(label=k) for k in ('one','two','three')}
        old,new=self.comparison()
        self.assertEqual(old['decisions_executed'],24);self.assertEqual(new['decisions_executed'],8)
        self.assertEqual(new['cases'][1]['result']['scenario'],'two')
    def test_current_event_ordinary_execution(self):
        self.scenarios['future']=self.c.oracle.Scenario(market_deltas={22:{'WOOL':1}})
        old,new=self.comparison()
        self.assertEqual(old['decisions_executed'],new['decisions_executed'])
        self.assertIsNone(new['prefix_reuse']['common_through_step'])
    def test_weed_full_world_preserved(self):
        self.scenarios['future']=self.c.oracle.Scenario(new_weeds={23:((0,0),)})
        self.comparison()
    def test_actor_local_random_generator_is_in_complete_fork(self):
        import random
        class LocalRng(Controller):
            def __init__(self):
                super().__init__(switch=23)
                self.rng=random.Random(1729)
            def act(self,view):
                action=super().act(view)
                action['market'][0][2]=self.rng.randrange(4)
                return action
        self.actor=LocalRng()
        initial=self.actor.rng.getstate()
        old=self.c.original.replay_routes(self.actor,('main','other'),self.obs,self.cfg,self.c.engine,self.c.oracle.simulate_bundle,
            scenarios=self.scenarios,end_step=25,limits=self.c.original.ReplayLimits(seconds=30,decisions=100))
        new=self.run_case()
        self.assertTrue(new['complete']);self.assertEqual(old['cases'],new['cases'])
        self.assertEqual(self.actor.rng.getstate(),initial)
        self.assertEqual(self.actor.calls,0)
    def test_default_remains_same_schema(self):
        new=self.run_case(False)
        old=self.c.original.replay_routes(self.actor,('main','other'),self.obs,self.cfg,self.c.engine,self.c.oracle.simulate_bundle,
            scenarios=self.scenarios,end_step=25,limits=self.c.original.ReplayLimits(seconds=30,decisions=100))
        new.pop('wall_seconds');old.pop('wall_seconds');self.assertEqual(new,old)
    def test_reused_case_results_are_independent(self):
        out=self.run_case();old=deepcopy(out['cases'][0])
        out['cases'][1]['market_rows'][0]['private_before']['shed']['WOOL']=999
        out['cases'][1]['result']['actions'][22]['market'][0][2]=999
        self.assertEqual(out['cases'][0],old)
    def test_decision_limit_keeps_partial_unscored(self):
        out=self.run_case(limits=replay.ReplayLimits(seconds=30,decisions=2))
        self.assertFalse(out['complete']);self.assertEqual(out['decisions_executed'],2)
        self.assertTrue(all(v['cash_gain'] is None for v in out['cases']))
    def test_late_prefix_not_cached_or_scored(self):
        now=[0.0]
        def simulate(*args,**kwargs):
            out=self.c.oracle.simulate_bundle(*args,**kwargs);now[0]=2.0;return out
        with patch.object(replay,'monotonic',lambda:now[0]):
            out=replay.replay_routes(self.actor,('main',),self.obs,self.cfg,self.c.engine,simulate,
                scenarios=self.scenarios,end_step=25,limits=replay.ReplayLimits(seconds=1),reuse_scenario_prefixes=True)
        self.assertFalse(out['complete']);self.assertEqual(out['prefix_reuse']['prefixes_computed'],0)
        self.assertTrue(all(v['cash_gain'] is None for v in out['cases']))
        self.assertEqual(len(out['cases'][0]['market_rows']),1)
    def test_late_suffix_keeps_prefix_evidence_unscored(self):
        now=[0.0];calls=[0]
        def simulate(*args,**kwargs):
            out=self.c.oracle.simulate_bundle(*args,**kwargs);calls[0]+=1
            if calls[0]==2:now[0]=2.0
            return out
        with patch.object(replay,'monotonic',lambda:now[0]):
            out=replay.replay_routes(self.actor,('main',),self.obs,self.cfg,self.c.engine,simulate,
                scenarios=self.scenarios,end_step=25,limits=replay.ReplayLimits(seconds=1),reuse_scenario_prefixes=True)
        self.assertFalse(out['complete']);self.assertEqual(len(out['cases'][0]['market_rows']),4)
        self.assertIsNone(out['cases'][0]['cash_gain'])
    def test_checkpoint_fork_cancellation_propagates(self):
        count=[0]
        def fork(actor):
            count[0]+=1
            if count[0]==2:raise KeyboardInterrupt('cancelled checkpoint')
            return deepcopy(actor)
        with self.assertRaisesRegex(KeyboardInterrupt,'cancelled checkpoint'):
            self.run_case(fork_controller=fork)
        self.assertEqual(self.actor.calls,0)
    def test_cached_controller_identity_is_rejected(self):
        calls=[0]
        def fork(actor):
            calls[0]+=1
            return actor if calls[0]==2 else deepcopy(actor)
        result=self.run_case(fork_controller=fork)
        self.assertEqual(result['cases'][0]['status'],'incomplete')
        self.assertIn('not independent',result['cases'][0]['reason'])

if __name__=='__main__':unittest.main()
