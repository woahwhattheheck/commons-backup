# SPDX-License-Identifier: MIT
"""Executed real-engine composition tests. Uses a reserved DEVELOPMENT fixture."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
RUNTIME = Path(os.environ.get('TITAN_COMPOSE_RUNTIME', HERE / 'runtime')).resolve()
sys.path.insert(0, str(RUNTIME))
import boot
import arlene
import labor_capital
import service_policy
from composition import Composition


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class EngineCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ev = load(HERE.parent / 'cloud-eval/evaluate.py', 'keel_test_eval')
        cls.engine, _ = ev.get_engine(RUNTIME / 'engine')
        cls.cfg = ev.Struct({k: v.get('default') if isinstance(v, dict) else v
                            for k, v in cls.engine.specification['configuration'].items()})
        cls.cfg.seed = 9820001  # Evaluation-only development seed; removed by engine.
        env = ev.Struct(configuration=cls.cfg, done=False, info={})
        states = [ev.Struct(observation=ev.Struct(), action={}, status='ACTIVE', reward=0)
                  for _ in (0,1)]
        cls.engine.interpreter(states, env)
        cls.initial = deepcopy(states[0].observation)
        cls.initial.step = 0
        cls.fixtures = {}
        parents = [arlene.Agent(), arlene.Agent()]
        for step in range(593):
            for state in states:
                state.observation.step = step
            if step in (121, 148, 592):
                cls.fixtures[step] = (deepcopy(states[0].observation), deepcopy(parents[0]))
            for seat in (0,1):
                states[seat].action = parents[seat].act(states[seat].observation)
            cls.engine.interpreter(states, env)

    def make(self, service=True, labor=True, forecast_labor=False):
        return Composition(arlene, labor_capital, service_policy, self.engine,
                           self.cfg, service=service, labor=labor, forecast_labor=forecast_labor)

    def test_initial_parent_parity_and_one_call_all_arms(self):
        reference = arlene.Agent().act(deepcopy(self.initial))
        for service in (False, True):
            for labor in (False, True):
                policy = self.make(service,labor)
                self.assertEqual(policy.act(deepcopy(self.initial)), reference)
                self.assertEqual((policy.calls, policy.parent_calls), (1,1))

    def test_forecast_route_choice_and_cache_rebinding_are_isolated(self):
        policy = self.make(forecast_labor=True)
        policy.act(deepcopy(self.initial))
        live_values = deepcopy(policy.base.__dict__)
        fork = policy.fork_parent().__self__
        self.assertIsNot(fork.parent, policy.base)
        self.assertIs(fork.parent.R, policy.base.R)
        fork.parent.cur = next(k for k in fork.parent.R if k != policy.base.cur)
        fork.parent._fs = {'TEST': [1]}
        fork.parent._fs_for = 'TEST'
        self.assertEqual(policy.base.__dict__, live_values)

    def test_hiring_diagnostics_and_configuration_do_not_alias(self):
        policy = self.make(forecast_labor=True)
        policy.hiring.counts = Counter({'baseline':3})
        policy.hiring.last_decision = {'nested': {'cash':5}}
        fork = policy.fork_parent().__self__
        fork.counts['baseline'] += 1
        fork.last_decision['nested']['cash'] = 999
        fork.configuration['shedCapacity'] = 7
        self.assertEqual(policy.hiring.counts, {'baseline':3})
        self.assertEqual(policy.hiring.last_decision, {'nested':{'cash':5}})
        self.assertEqual(policy.hiring.configuration['shedCapacity'],100)

    def test_real_forecast_calls_leave_live_controller_unchanged(self):
        obs, base = self.fixtures[121]
        policy = self.make()
        policy.base = deepcopy(base)
        policy.hiring.parent = policy.base
        before = deepcopy(policy.base.__dict__)
        fork = policy.fork_parent()
        action = fork(deepcopy(obs))
        self.assertIsInstance(action,dict)
        self.assertEqual(policy.base.__dict__,before)
        self.assertEqual(policy.parent_calls,0)
        self.assertEqual(policy.hiring.counts,Counter())

    def test_hiring_composition_matches_original_component_at_real_event(self):
        obs, base = self.fixtures[121]
        reference = labor_capital.HiringAgent(deepcopy(base),self.engine,configuration=self.cfg)
        policy = self.make(False,True)
        policy.base = deepcopy(base)
        policy.hiring.parent = policy.base
        self.assertEqual(policy.act(deepcopy(obs)),reference.act(deepcopy(obs)))
        self.assertEqual(policy.parent_calls,1)

    def test_service_component_not_invoked_twice_on_real_event(self):
        obs, base = self.fixtures[592]
        policy = self.make(True,True)
        policy.base = deepcopy(base)
        policy.hiring.parent = policy.base
        before_obs = deepcopy(obs)
        result = policy.act(obs)
        self.assertIsInstance(result,dict)
        self.assertEqual(policy.parent_calls,1)
        self.assertEqual(obs,before_obs)
        self.assertEqual(policy.hiring.parent,policy.base)

    def test_independent_matches_and_disabled_service_fork(self):
        a,b = self.make(),self.make()
        a.act(deepcopy(self.initial))
        self.assertEqual(b.parent_calls,0)
        self.assertIsNot(a.base,b.base)
        parent_only = self.make(False,False)
        fork = parent_only.fork_parent().__self__
        self.assertIsNot(fork,parent_only.base)
        self.assertIs(fork.R,parent_only.base.R)

    def test_actual_official_file_loader_cold_calls(self):
        ev = load(HERE.parent / 'cloud-eval/evaluate.py', 'keel_cold_eval')
        actions = {}
        for name in ('parent','service','labor','both','sell','arlene','apex'):
            actor = ev.Actor(str(RUNTIME / f'{name}_adapter.py'),
                             RUNTIME / 'engine', ev.LOADER, 20260907)
            try:
                self.assertEqual(actor.ready['kind'], 'ready', actor.ready)
                answer = actor.act(deepcopy(self.initial), self.cfg, 1.0)
                self.assertEqual(answer['kind'],'action',answer)
                actions[name] = answer['action']
            finally:
                actor.close()
        self.assertEqual(actions['parent'],actions['arlene'])
        self.assertEqual(actions['parent'],actions['both'])

    def test_default_forecast_does_not_recursively_optimize_hires(self):
        policy = self.make()
        fork = policy.fork_parent().__self__
        self.assertIsInstance(fork, arlene.Agent)
        self.assertIsNot(fork, policy.base)
        obs, base = self.fixtures[148]
        policy.base = deepcopy(base)
        policy.hiring.parent = policy.base
        result = policy.act(deepcopy(obs))
        self.assertIsInstance(result,dict)
        self.assertEqual(policy.parent_calls,1)

    def test_configuration_drops_seed(self):
        policy = self.make()
        self.assertNotIn('seed', policy.configuration)
        self.assertNotIn('seed',policy.hiring.configuration)
        self.assertIsNone(self.cfg.get('seed'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
