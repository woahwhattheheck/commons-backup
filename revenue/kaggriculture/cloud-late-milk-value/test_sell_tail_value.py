# SPDX-License-Identifier: Apache-2.0
"""Actual frozen-actor/RILL/T04 binding tests using the retained PRISM prefix.

Inputs are supplied explicitly through environment variables. Missing inputs
raise a setup error; they are not silently reported as passing integration.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import random
import sys
import unittest

from reached_case import MAIN, MILK_EXIT, load, restore_prefix
from sell_tail_value import SellRouteView, evaluate_sell_tails


def actor_state(actor):
    return {**actor.__dict__, 'controller': actor.controller.__dict__}


class SellTailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(os.environ['TITAN_SOURCE_ROOT'])
        rill = Path(os.environ['TITAN_RILL_ROOT'])
        sell = root/'cloud-titan-composition/vendor/sell'
        sys.path.insert(0, str(sell))
        cls.scheduler = load(sell/'scheduler.py', 'joint_test_scheduler')
        evaluator = load(root/'cloud-eval/evaluate.py', 'joint_test_evaluator')
        cls.engine, _ = evaluator.get_engine(Path(os.environ['TITAN_ENGINE_DIR']), prepare=False)
        cls.oracle = load(Path(os.environ['T04_ORACLE']), 'joint_test_oracle')
        cls.physical = load(rill/'physical_replay.py', 'joint_test_physical')
        cls.cfg = {k:v.get('default') if isinstance(v,dict) else v
                   for k,v in cls.engine.specification['configuration'].items()}
        cls.cfg['seed'] = None
        random.seed(20260907)
        cls.saved_actor = cls.scheduler.SellScheduler()
        cls.saved_obs, cls.prefix = restore_prefix(cls.saved_actor, Path(os.environ['PRISM_TRACE']), cls.cfg)
        reference = json.loads(Path(os.environ['PRISM_INPUT']).read_text())
        if reference['observation'] != cls.saved_obs:
            raise AssertionError('Saved input and restored observation differ')

    def setUp(self):
        self.actor = deepcopy(self.saved_actor)
        self.obs = deepcopy(self.saved_obs)
        self.before = deepcopy(actor_state(self.actor))
        self.before_obs = deepcopy(self.obs)

    def evaluate(self, **kwargs):
        options = dict(replay_routes=self.physical.replay_routes,
                       simulate_bundle=self.oracle.simulate_bundle,
                       scenarios={'observed':self.oracle.Scenario()}, end_step=577,
                       limits=self.physical.ReplayLimits(seconds=10,decisions=4))
        options.update(kwargs)
        return evaluate_sell_tails(self.actor, (MILK_EXIT,MAIN), self.obs, self.cfg,
                                   self.engine, **options)

    def test_restored_prefix_has_original433_route_and_sell_commitments(self):
        self.assertEqual(self.prefix['matched_prefix_actions'],577)
        self.assertEqual(self.prefix['engine_calls'],0)
        self.assertEqual(self.actor.controller.cur,MILK_EXIT)
        self.assertEqual(self.actor.planned['STRAWBERRY'],[(577,3),(584,9)])
        self.assertEqual(self.actor.pending['STRAWBERRY'],12)
        self.assertEqual(self.actor.previous['step'],576)

    def test_facade_owns_no_extra_controller_or_optimizer(self):
        facade = SellRouteView(self.actor,self.cfg)
        self.assertIs(facade.scheduler,self.actor)
        self.assertIs(facade.R,self.actor.controller.R)
        self.assertEqual(facade.cur,MILK_EXIT)
        self.assertTrue(facade._switch_ok(MAIN,577))

    def test_whole_fork_preserves_all_nested_actor_state_without_aliases(self):
        facade = deepcopy(SellRouteView(self.actor,self.cfg))
        self.assertEqual(actor_state(facade.scheduler),self.before)
        self.assertIsNot(facade.scheduler,self.actor)
        self.assertIsNot(facade.scheduler.controller,self.actor.controller)
        self.assertIsNot(facade.scheduler.planned,self.actor.planned)
        self.assertIsNot(facade.scheduler.previous,self.actor.previous)
        facade.scheduler.planned['STRAWBERRY'].append((600,1))
        facade.cur = MAIN
        self.assertEqual(actor_state(self.actor),self.before)

    def test_facade_act_matches_direct_whole_sell_and_state(self):
        direct = deepcopy(self.actor)
        facade = deepcopy(SellRouteView(self.actor,self.cfg))
        self.assertEqual(facade.act(deepcopy(self.obs)),direct.act(deepcopy(self.obs),self.cfg))
        self.assertEqual(actor_state(facade.scheduler),actor_state(direct))

    def test_actual_oracle_outputs_match_direct_whole_actor_for_both_routes(self):
        result = self.evaluate()
        self.assertTrue(result['complete'])
        for case in result['replay']['cases']:
            direct = deepcopy(self.actor)
            direct.controller.cur = case['offered_route']
            expected = self.oracle.simulate_bundle(self.engine,self.obs,self.cfg,
                lambda view:direct.act(view,self.cfg), end_step=577,
                scenario=self.oracle.Scenario(),record_actions=True)
            self.assertEqual(case['result'],expected)
            self.assertEqual(sum(x['cash_delta'] for x in case['market_rows']),case['cash_gain'])
        self.assertEqual(actor_state(self.actor),self.before)
        self.assertEqual(self.obs,self.before_obs)

    def test_nonterminal_results_are_not_terminal_values(self):
        result = self.evaluate()
        self.assertFalse(result['terminal_horizon'])
        self.assertTrue(all(row['terminal_own_cash_delta'] is None for row in result['comparisons']))
        self.assertEqual({row['reason'] for row in result['comparisons']},{'nonterminal_prefix'})
        self.assertIsNone(result['selection'])

    def test_zero_time_budget_preserves_unscored_incomplete_pairs(self):
        result = self.evaluate(limits=self.physical.ReplayLimits(seconds=0,decisions=4))
        self.assertFalse(result['complete'])
        self.assertEqual(result['replay']['decisions_executed'],0)
        self.assertTrue(all(row['reason']=='incomplete_pair' for row in result['comparisons']))
        self.assertEqual(actor_state(self.actor),self.before)

    def test_shared_decision_budget_does_not_score_missing_alternative(self):
        result = self.evaluate(limits=self.physical.ReplayLimits(seconds=10,decisions=1))
        self.assertFalse(result['complete'])
        self.assertEqual(result['replay']['decisions_executed'],1)
        alternative = next(x for x in result['comparisons'] if x['route']==MAIN)
        self.assertFalse(alternative['complete_pair'])
        self.assertIsNone(alternative['terminal_own_cash_delta'])

    def test_live_actor_and_shared_controller_forks_are_not_called(self):
        for fork in (lambda actor:actor,
                     lambda actor:type('Alias',(),{'controller':actor.controller})()):
            with self.subTest(fork=fork):
                result = self.evaluate(fork_scheduler=fork)
                self.assertFalse(result['complete'])
                self.assertEqual(result['replay']['decisions_executed'],0)
                self.assertEqual(actor_state(self.actor),self.before)

    def test_same_actor_and_parent_are_each_called_once_per_emitted_action(self):
        Scheduler = self.scheduler.SellScheduler
        Controller = self.scheduler.parent.Agent
        class CountController(Controller):
            def act(self,observation):
                self.parent_calls += 1
                return super().act(observation)
        class CountScheduler(Scheduler):
            def act(self,observation,configuration=None):
                self.actor_calls += 1
                return super().act(observation,configuration)
        actor = CountScheduler.__new__(CountScheduler)
        actor.__dict__ = deepcopy(self.actor.__dict__)
        controller = CountController.__new__(CountController)
        controller.__dict__ = deepcopy(actor.controller.__dict__)
        controller.parent_calls=0
        actor.controller=controller;actor.actor_calls=0
        self.actor=actor
        clones=[]
        def fork(value):
            clone=deepcopy(value);clones.append(clone);return clone
        result=self.evaluate(fork_scheduler=fork)
        self.assertTrue(result['complete'])
        self.assertEqual([(x.actor_calls,x.controller.parent_calls) for x in clones],[(1,1),(1,1)])
        self.assertEqual((actor.actor_calls,actor.controller.parent_calls),(0,0))

    def test_original_configuration_is_not_mutated_by_a_copied_facade(self):
        cfg=deepcopy(self.cfg)
        facade=SellRouteView(self.actor,cfg)
        facade.configuration['nested']={'one':1}
        self.assertEqual(cfg,self.cfg)

    def test_incumbent_omission_is_explicit_without_actor_execution(self):
        with self.assertRaises(ValueError):
            evaluate_sell_tails(self.actor,(MAIN,),self.obs,self.cfg,self.engine,
                replay_routes=self.physical.replay_routes,simulate_bundle=self.oracle.simulate_bundle,
                scenarios={'known':self.oracle.Scenario()},end_step=577,
                limits=self.physical.ReplayLimits())
        self.assertEqual(actor_state(self.actor),self.before)

    def test_external_cancellation_propagates(self):
        def cancelled(*args,**kwargs):
            raise KeyboardInterrupt('test cancellation')
        with self.assertRaises(KeyboardInterrupt):
            self.evaluate(simulate_bundle=cancelled)
        self.assertEqual(actor_state(self.actor),self.before)

    def test_scenarios_have_separate_whole_actor_copies(self):
        clones=[]
        def fork(value):
            clone=deepcopy(value);clones.append(clone);return clone
        result=self.evaluate(scenarios={'a':self.oracle.Scenario(),'b':self.oracle.Scenario()},
                             fork_scheduler=fork)
        self.assertTrue(result['complete'])
        self.assertEqual(len({id(x) for x in clones}),4)
        self.assertEqual(len({id(x.controller) for x in clones}),4)
        self.assertEqual(result['replay']['decisions_executed'],4)
        self.assertTrue(all(x['rival_cash_delta'] is None for x in result['comparisons']))
        self.assertEqual(actor_state(self.actor),self.before)


if __name__=='__main__':
    unittest.main(verbosity=2)
