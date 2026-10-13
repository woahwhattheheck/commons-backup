# SPDX-License-Identifier: Apache-2.0
"""Run the existing executor's changed boundary with explicit integration fixtures.

The tiny environment below is a test double, not Kaggriculture game evidence.
The executor, file loader, signature binding, observer and failure recorder are real.
"""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

TARGET = Path(os.environ.get('TITAN_EXECUTOR',
    Path(__file__).resolve().parent.parent / 'cloud-model-lab' / 'execute_arm.py'))


class Clock:
    def __init__(self): self.now = 0.0
    def __call__(self): return self.now
    def advance(self, amount): self.now += amount


class Observation(dict):
    def __getattr__(self, key): return self[key]


class EnvironmentFixture:
    def __init__(self, rounds=3):
        self.target = rounds; self.round = 0; self.done = rounds == 0
        self.configuration = {'turnsPerDay': 24}
        self.actions = []
        self.state = [types.SimpleNamespace(observation=Observation({
            'step': 0, 'day': 0, 'hour': 0, 'player': i,
            'farms': [{'money': 20}, {'money': 10}]})) for i in (0, 1)]
    def reset(self, players): assert players == 2
    def step(self, actions):
        self.actions.append(actions); self.round += 1
        for state in self.state:
            state.observation.update(step=self.round, hour=self.round)
        self.done = self.round == self.target


class ExecutorIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.env = EnvironmentFixture()
        self.clock = Clock()
        self.cards = types.ModuleType('cards')
        self.cards.make_env = lambda seed: self.env
        self.route = types.ModuleType('route_cards')
        self.route.load_arlene = lambda: (None, {'label': 'fixture'})
        self.arm = types.ModuleType('arlene_arm')
        self.arm.make_opponent = lambda name, A: (lambda obs, cfg: ['opponent'], {'label': name})
        self.mods = {'cards': self.cards, 'route_cards': self.route, 'arlene_arm': self.arm}
        self.context = patch.dict(sys.modules, self.mods)
        self.context.start(); self.addCleanup(self.context.stop)
        spec = importlib.util.spec_from_file_location('executor_integration_subject', TARGET)
        self.subject = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.subject)
        observer = self.subject.TimedFactory
        self.subject.TimedFactory = lambda factory: observer(factory, clock=self.clock)

    def run_game(self, factory, seat=0):
        return self.subject.game(0, seat, 'fixture', factory, 'candidate', False)

    def test_initialization_and_first_are_same_actor_not_maximum(self):
        calls = []
        def factory():
            self.clock.advance(0.2)
            def act(obs, cfg):
                self.clock.advance([0.1, 0.9, 0.3][len(calls)])
                calls.append(obs['step']); return ['action', obs['step']]
            return act
        row = self.run_game(factory); t = row['executor_timing']
        self.assertIsNone(row['error']); self.assertEqual(calls, [0, 1, 2])
        self.assertAlmostEqual(t['initialization_s'], 0.2)
        self.assertAlmostEqual(t['first_action_s'], 0.1)
        self.assertAlmostEqual(t['initialization_plus_first_action_s'], 0.3)
        self.assertAlmostEqual(t['max_action_s'], 0.9)
        self.assertAlmostEqual(t['max_later_action_s'], 0.9)
        self.assertEqual((row['own_cash'], row['rival_cash'], row['rounds']), (20, 10, 3))
        self.assertIn('worst_action_s', row); self.assertIn('wall_s', row)

    def test_constructor_failure_is_recorded_without_action(self):
        def factory(): self.clock.advance(0.4); raise TypeError('constructor-body')
        row = self.run_game(factory); t = row['executor_timing']
        self.assertEqual(row['error'], 'TypeError: constructor-body')
        self.assertTrue(t['initialization_failed']); self.assertEqual(t['calls'], 0)
        self.assertIsNone(t['first_action_s']); self.assertIsNone(row['own_cash'])
        self.assertAlmostEqual(t['initialization_s'], 0.4)

    def test_first_action_failure_is_timed_and_not_retried(self):
        calls = []
        def factory():
            def act(obs, cfg):
                calls.append(1); self.clock.advance(0.7); raise TypeError('first-body')
            return act
        row = self.run_game(factory); t = row['executor_timing']
        self.assertEqual(row['error'], 'TypeError: first-body'); self.assertEqual(calls, [1])
        self.assertEqual((t['calls'], t['failures']), (1, 1))
        self.assertAlmostEqual(t['first_action_s'], 0.7)
        self.assertIsNone(t['max_later_action_s']); self.assertIn('first-body', row['traceback'])

    def test_later_failure_retains_successful_and_failed_calls(self):
        def factory():
            def act(obs, cfg):
                self.clock.advance(0.1 + obs['step'])
                if obs['step']: raise ValueError('later-body')
                return ['first']
            return act
        row = self.run_game(factory); t = row['executor_timing']
        self.assertEqual(row['error'], 'ValueError: later-body')
        self.assertEqual((t['calls'], t['failures']), (2, 1))
        self.assertAlmostEqual(t['first_action_s'], 0.1)
        self.assertAlmostEqual(t['max_later_action_s'], 1.1)
        self.assertEqual(len(self.env.actions), 1)

    def test_environment_failure_has_no_invented_actor_timing(self):
        def fail(seed): raise RuntimeError('setup-body')
        self.cards.make_env = fail
        row = self.run_game(lambda: self.fail('factory should not run'))
        self.assertEqual(row['error'], 'RuntimeError: setup-body')
        self.assertIsNone(row['executor_timing'])

    def test_opponent_failure_before_candidate_turn_has_no_first_action(self):
        def opponent(obs, cfg): raise ValueError('opponent-body')
        self.arm.make_opponent = lambda name, A: (opponent, {'label': name})
        row = self.run_game(lambda: lambda obs, cfg: self.fail('no candidate call'), seat=1)
        self.assertEqual(row['error'], 'ValueError: opponent-body')
        self.assertEqual(row['executor_timing']['calls'], 0)
        self.assertIsNone(row['executor_timing']['first_action_s'])

    def test_real_candidate_file_loader_keeps_single_invocation_fix(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'agent.py'
            path.write_text('def agent(obs, cfg=None):\n obs["calls"]=obs.get("calls",0)+1\n if cfg is not None: raise TypeError("loaded-body")\n return "masked"\n')
            factory, _ = self.subject.load_callable(str(path))
            row = self.run_game(factory)
        self.assertEqual(row['error'], 'TypeError: loaded-body')
        # normalise makes a shallow copy; timing is the retained invocation witness.
        self.assertEqual((row['executor_timing']['calls'], row['executor_timing']['failures']), (1, 1))

    def test_zero_action_episode_has_no_combined_time(self):
        self.env = EnvironmentFixture(0)
        row = self.run_game(lambda: lambda obs, cfg: None)
        t = row['executor_timing']; self.assertIsNone(row['error'])
        self.assertEqual(t['calls'], 0); self.assertIsNone(t['initialization_plus_first_action_s'])

    def test_separate_games_do_not_share_timing_records(self):
        factory = lambda: lambda obs, cfg: ['action']
        a = self.run_game(factory)
        self.env = EnvironmentFixture(1)
        b = self.run_game(factory)
        self.assertEqual(a['executor_timing']['calls'], 3)
        self.assertEqual(b['executor_timing']['calls'], 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
