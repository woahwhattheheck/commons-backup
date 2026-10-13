# SPDX-License-Identifier: Apache-2.0
"""Actual frozen-actor binding against the existing saved577 input."""
from __future__ import annotations

from copy import deepcopy
import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from state_copy import scheduler_class, fork_scheduler, deepcopy_state

VALUE_ROOT = Path(os.environ.get('TITAN_VALUE_ROOT', str(Path(__file__).resolve().parent.parent/'cloud-late-milk-value')))
sys.path.insert(0,str(VALUE_ROOT))
import test_sell_tail_value as value_fixture
from test_sell_tail_value import actor_state
from reached_case import MAIN, MILK_EXIT
from sell_tail_value import evaluate_sell_tails


class SchedulerBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        value_fixture.SellTailTests.setUpClass()
        cls.fixture=value_fixture.SellTailTests
        cls.original=cls.fixture.scheduler
        cls.variant=scheduler_class(cls.original)

    def setUp(self):
        self.actor=deepcopy(self.fixture.saved_actor)
        self.obs=deepcopy(self.fixture.saved_obs)
        self.before=deepcopy(actor_state(self.actor))

    def test_function_code_objects_are_original(self):
        for name in ('act','receipt_profile'):
            with self.subTest(name=name):
                self.assertIs(getattr(self.variant,name).__code__,getattr(self.original.SellScheduler,name).__code__)
        rebound=self.variant.act.__globals__['post_units']
        self.assertIs(rebound.__code__,self.original.post_units.__code__)

    def test_globals_and_stdlib_are_unmodified(self):
        private=self.variant.act.__globals__
        self.assertIsNot(private,self.original.__dict__)
        self.assertIs(private['copy'].deepcopy,deepcopy_state)
        self.assertIs(self.original.copy,copy)
        self.assertIs(self.original.SellScheduler.act.__globals__['post_units'],self.original.post_units)
        for name in ('optimize_lot','MarketPath','parent','m','receipt_math'):
            self.assertIs(private[name],getattr(self.original,name))

    def test_same_version_factory_is_cached(self):
        self.assertIs(scheduler_class(self.original),self.variant)

    def test_new_actor_retains_original_constructor_and_mode(self):
        self.assertIs(self.variant.__init__,self.original.SellScheduler.__init__)
        actor=self.variant('naive')
        self.assertEqual(actor.mode,'naive')
        self.assertIs(type(actor.controller),self.original.parent.Agent)

    def test_fork_preserves_full_state_and_independence(self):
        actor=fork_scheduler(self.actor,self.original)
        self.assertIs(type(actor),self.variant)
        self.assertEqual(actor_state(actor),self.before)
        self.assertIsNot(actor.controller,self.actor.controller)
        self.assertIsNot(actor.previous,self.actor.previous)
        self.assertIsNot(actor.planned,self.actor.planned)
        self.assertEqual(actor_state(self.actor),self.before)

    def test_fork_does_not_call_constructor_or_parent(self):
        with patch.object(self.original.SellScheduler,'__init__',side_effect=AssertionError('constructor called')):
            actor=fork_scheduler(self.actor,self.original)
        self.assertEqual(actor_state(actor),self.before)

    def test_already_accelerated_fork_remains_independent(self):
        one=fork_scheduler(self.actor,self.original)
        two=fork_scheduler(one,self.original)
        self.assertIs(type(two),self.variant)
        self.assertIsNot(two.controller,one.controller)
        self.assertEqual(actor_state(two),self.before)

    def test_custom_subclass_is_not_silently_flattened(self):
        class Custom(self.original.SellScheduler):
            def act(self,obs,configuration=None):return {'custom':True}
        actor=Custom.__new__(Custom);actor.__dict__=deepcopy(self.actor.__dict__)
        with self.assertRaisesRegex(ValueError,'Custom actors'):
            fork_scheduler(actor,self.original)

    def test_actual577_action_and_every_actor_field_match(self):
        fast=fork_scheduler(self.actor,self.original)
        expected=self.actor.act(deepcopy(self.obs),self.fixture.cfg)
        actual=fast.act(deepcopy(self.obs),self.fixture.cfg)
        self.assertEqual(actual,expected)
        self.assertEqual(actor_state(fast),actor_state(self.actor))

    def test_both_route_short_replays_match_entire_existing_report(self):
        common=dict(replay_routes=self.fixture.physical.replay_routes,
                    simulate_bundle=self.fixture.oracle.simulate_bundle,
                    scenarios={'known':self.fixture.oracle.Scenario()},end_step=578,
                    limits=self.fixture.physical.ReplayLimits(seconds=10,decisions=4))
        old=evaluate_sell_tails(self.actor,(MILK_EXIT,MAIN),self.obs,self.fixture.cfg,self.fixture.engine,**common)
        new=evaluate_sell_tails(self.actor,(MILK_EXIT,MAIN),self.obs,self.fixture.cfg,self.fixture.engine,
                               fork_scheduler=lambda x:fork_scheduler(x,self.original),**common)
        old['replay'].pop('wall_seconds');new['replay'].pop('wall_seconds')
        self.assertEqual(new,old)
        self.assertEqual(actor_state(self.actor),self.before)

    def test_private_copy_does_not_leak_between_modules(self):
        private=self.variant.act.__globals__
        self.assertIs(private,self.variant.receipt_profile.__globals__)
        self.assertIsNot(private['copy'],copy)
        self.assertIs(private['copy'].copy,copy.copy)
        self.assertIs(self.original.post_units.__globals__['copy'],copy)

    def test_standard_deepcopy_of_variant_preserves_state(self):
        one=fork_scheduler(self.actor,self.original)
        two=deepcopy(one)
        self.assertIs(type(two),self.variant)
        self.assertEqual(actor_state(two),self.before)
        self.assertIsNot(two.planned,one.planned)


if __name__=='__main__':unittest.main(verbosity=2)
