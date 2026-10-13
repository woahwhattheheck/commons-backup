"""Exercise executor cleanup with the real recorder and timing observer.

The environment and engine namespace are deterministic integration fixtures,
not simulated Kaggriculture games. Both actual recorder wrappers execute.
TITAN_EXECUTOR_SOURCE selects exact comparison bytes; the canonical module
location resolves its unchanged sibling timing dependency.
"""
from collections import Counter
from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


LAB = Path(__file__).resolve().parents[1] / 'cloud-model-lab'
SOURCE = Path(os.environ.get('TITAN_EXECUTOR_SOURCE', LAB / 'execute_arm.py'))


class Observation(dict):
    def __getattr__(self, key):
        return self[key]


class RecorderCleanupTests(unittest.TestCase):
    def setUp(self):
        self.calls = Counter()
        self.failure_stage = None
        self.failure = None
        self.engine = types.ModuleType('kaggle_environments.envs.kaggriculture.kaggriculture')

        def spawn(farm, board_size, weed_chance, rng):
            for row in farm['tiles']:
                for index, tile in enumerate(row):
                    if tile is None:
                        row[index] = {'kind': 'WEED'}
                        return

        def end_of_day(state, env, day):
            observation = state[0].observation
            for farm in observation.farms:
                self.engine._spawn_weeds(farm, 2, 0.1, None)
            observation.town['unlocked_shops'].append('FIXTURE_SHOP')

        self.spawn, self.end_of_day = spawn, end_of_day
        self.engine._spawn_weeds, self.engine._end_of_day = spawn, end_of_day
        cards = types.ModuleType('cards')
        cards.make_env = self.make_env
        routes = types.ModuleType('route_cards')
        routes.load_arlene = lambda: (object(), {'label': 'fixture-arlene'})
        arms = types.ModuleType('arlene_arm')
        arms.make_opponent = self.make_opponent
        root = types.ModuleType('kaggle_environments')
        envs = types.ModuleType('kaggle_environments.envs')
        package = types.ModuleType('kaggle_environments.envs.kaggriculture')
        root.__path__ = envs.__path__ = package.__path__ = []
        root.envs, envs.kaggriculture = envs, package
        package.kaggriculture = self.engine
        modules = {
            'cards': cards, 'continuation': types.ModuleType('continuation'),
            'route_cards': routes, 'arlene_arm': arms,
            root.__name__: root, envs.__name__: envs,
            package.__name__: package, self.engine.__name__: self.engine,
        }
        context = patch.dict(sys.modules, modules)
        context.start()
        self.addCleanup(context.stop)
        spec = importlib.util.spec_from_file_location('market_path', LAB / 'market_path.py')
        self.market_path = importlib.util.module_from_spec(spec)
        sys.modules['market_path'] = self.market_path
        spec.loader.exec_module(self.market_path)
        self.subject = types.ModuleType('recorder_cleanup_executor')
        self.subject.__file__ = str(LAB / 'execute_arm.py')
        exec(compile(SOURCE.read_bytes(), str(SOURCE), 'exec'), self.subject.__dict__)

    def at(self, stage):
        self.calls[stage] += 1
        if self.failure_stage == stage:
            raise self.failure

    def make_env(self, seed):
        self.at('make_env')
        test = self
        farms = [{'money': 20, 'tiles': [[None, None]]},
                 {'money': 10, 'tiles': [[None, {'kind': 'CROP'}]]}]
        town = {'unlocked_shops': []}

        class Environment:
            done = False
            configuration = {'turnsPerDay': 24}

            def __init__(self):
                self.state = [types.SimpleNamespace(observation=Observation(
                    step=0, day=0, hour=0, player=i, farms=farms, town=town))
                    for i in range(2)]

            def reset(self, players):
                test.assertEqual(players, 2)
                test.at('reset')

            def step(self, actions):
                test.assertEqual(actions, [['candidate'], ['opponent']])
                test.engine._end_of_day(self.state, self, 1)
                test.at('step')
                self.done = True

        return Environment()

    def make_opponent(self, name, arlene):
        self.at('opponent_factory')

        def opponent(obs, configuration):
            self.at('opponent_action')
            return ['opponent']

        return opponent, {'label': 'fixture-opponent'}

    def factory(self):
        self.at('factory')

        def candidate(obs, configuration):
            self.at('candidate_action')
            return ['candidate']

        return candidate

    def run_game(self, record_path=True):
        return self.subject.game(0, 0, 'fixture', self.factory, 'candidate', record_path)

    def assert_hooks(self, spawn=None, end_of_day=None):
        self.assertIs(self.engine._spawn_weeds, spawn or self.spawn)
        self.assertIs(self.engine._end_of_day, end_of_day or self.end_of_day)

    @contextmanager
    def fresh_hooks(self):
        # Failed before-repair subtests must not contaminate the next case.
        with patch.object(self.engine, '_spawn_weeds', self.spawn), \
                patch.object(self.engine, '_end_of_day', self.end_of_day):
            yield

    def expected_path(self):
        return [{'day': 1, 'farms': [
            {'empty_tiles_drawn': 2, 'weeds_spawned': 1},
            {'empty_tiles_drawn': 1, 'weeds_spawned': 1}],
            'shop_unlocked': 'FIXTURE_SHOP', 'draws_before_shop': 3}]

    def test_success_retains_row_timing_and_actual_recorded_path(self):
        row = self.run_game()
        self.assert_hooks()
        self.assertEqual(set(row), {'seed', 'seat', 'opponent', 'arm', 'own_cash',
            'rival_cash', 'margin', 'rounds', 'wall_s', 'worst_action_s',
            'opponent_id', 'arlene', 'error', 'executor_timing', 'path'})
        self.assertEqual((row['seed'], row['seat'], row['opponent'], row['arm']),
                         (0, 0, 'fixture', 'candidate'))
        self.assertEqual((row['own_cash'], row['rival_cash'], row['margin'], row['rounds']),
                         (20.0, 10.0, 10.0, 1))
        self.assertIsNone(row['error'])
        self.assertEqual(row['path'], self.expected_path())
        self.assertEqual(row['executor_timing']['calls'], 1)
        self.assertEqual(row['executor_timing']['failures'], 0)
        self.assertIsNotNone(row['executor_timing']['first_action_s'])
        self.assertEqual(self.calls['candidate_action'], 1)

    def test_ordinary_failures_remain_captured_and_restore_hooks(self):
        for stage in ('make_env', 'reset', 'opponent_factory', 'factory',
                      'candidate_action', 'opponent_action', 'step'):
            with self.subTest(stage=stage), self.fresh_hooks():
                self.calls.clear()
                self.failure_stage, self.failure = stage, RuntimeError('fixture-' + stage)
                row = self.run_game()
                self.assert_hooks()
                self.assertEqual(row['error'], 'RuntimeError: fixture-' + stage)
                self.assertIn('fixture-' + stage, row['traceback'])
                self.assertIsNone(row['own_cash'])
                self.assertIsNone(row['rival_cash'])
                self.assertIsNone(row['margin'])
                self.assertEqual(self.calls[stage], 1)
                self.assertEqual(row['path'], self.expected_path() if stage == 'step' else [])

    def test_interruptions_at_each_boundary_restore_both_hooks_without_retry(self):
        for kind in (KeyboardInterrupt, SystemExit):
            for stage in ('make_env', 'reset', 'opponent_factory', 'factory',
                          'candidate_action', 'opponent_action', 'step'):
                with self.subTest(kind=kind.__name__, stage=stage), self.fresh_hooks():
                    self.calls.clear()
                    self.failure_stage, self.failure = stage, kind('fixture-' + stage)
                    with self.assertRaises(kind) as caught:
                        self.run_game()
                    self.assertIs(caught.exception, self.failure)
                    self.assert_hooks()
                    self.assertEqual(self.calls[stage], 1)

    def test_timing_diagnostic_failure_restores_hooks_and_propagates_identity(self):
        for kind in (RuntimeError, KeyboardInterrupt, SystemExit):
            with self.subTest(kind=kind.__name__), self.fresh_hooks():
                failure = kind('fixture-timings')
                with patch.object(self.subject.TimedFactory, 'timings', side_effect=failure), \
                        self.assertRaises(kind) as caught:
                    self.run_game()
                self.assertIs(caught.exception, failure)
                self.assert_hooks()

    def test_path_diagnostic_failure_restores_hooks_and_propagates_identity(self):
        for kind in (RuntimeError, KeyboardInterrupt, SystemExit):
            with self.subTest(kind=kind.__name__), self.fresh_hooks():
                failure = kind('fixture-path')
                with patch.object(self.market_path.PathRecorder, 'path', side_effect=failure), \
                        self.assertRaises(kind) as caught:
                    self.run_game()
                self.assertIs(caught.exception, failure)
                self.assert_hooks()

    def test_no_path_leaves_hooks_untouched_on_success_and_interruption(self):
        with patch.object(self.market_path.PathRecorder, '__enter__') as enter:
            row = self.run_game(record_path=False)
            self.assertNotIn('path', row)
            self.assertIsNone(row['error'])
            self.failure_stage, self.failure = 'candidate_action', KeyboardInterrupt('no-path')
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.run_game(record_path=False)
            self.assertIs(caught.exception, self.failure)
            enter.assert_not_called()
        self.assert_hooks()

    def test_nested_success_restores_outer_recorder_and_both_paths(self):
        with self.market_path.PathRecorder() as outer:
            outer_spawn, outer_eod = self.engine._spawn_weeds, self.engine._end_of_day
            row = self.run_game()
            self.assert_hooks(outer_spawn, outer_eod)
            self.assertEqual(row['path'], self.expected_path())
            self.assertEqual(outer.path(), self.expected_path())
        self.assert_hooks()

    def test_nested_interruption_restores_outer_recorder_before_outer_exit(self):
        for kind in (KeyboardInterrupt, SystemExit):
            with self.subTest(kind=kind.__name__), self.fresh_hooks():
                self.failure_stage, self.failure = 'step', kind('nested')
                with self.market_path.PathRecorder() as outer:
                    outer_spawn, outer_eod = self.engine._spawn_weeds, self.engine._end_of_day
                    with self.assertRaises(kind) as caught:
                        self.run_game()
                    self.assertIs(caught.exception, self.failure)
                    self.assert_hooks(outer_spawn, outer_eod)
                    self.assertEqual(outer.path(), self.expected_path())
                self.assert_hooks()

    def test_following_game_records_once_after_interruption(self):
        self.failure_stage, self.failure = 'step', KeyboardInterrupt('first-game')
        with self.assertRaises(KeyboardInterrupt) as caught:
            self.run_game()
        self.assertIs(caught.exception, self.failure)
        self.assert_hooks()
        self.failure_stage, self.failure = None, None
        row = self.run_game()
        self.assert_hooks()
        self.assertEqual(row['path'], self.expected_path())
        self.assertEqual(row['executor_timing']['calls'], 1)

    def test_observer_construction_failure_does_not_leave_engine_wrapped(self):
        for kind in (RuntimeError, KeyboardInterrupt, SystemExit):
            with self.subTest(kind=kind.__name__), self.fresh_hooks():
                failure = kind('fixture-observer-constructor')
                with patch.object(self.subject, 'TimedFactory', side_effect=failure), \
                        self.assertRaises(kind) as caught:
                    self.run_game()
                self.assertIs(caught.exception, failure)
                self.assert_hooks()


if __name__ == '__main__':
    unittest.main(verbosity=2)
