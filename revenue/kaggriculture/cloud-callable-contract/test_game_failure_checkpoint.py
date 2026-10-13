# SPDX-License-Identifier: Apache-2.0
"""Known game outcomes survive escaped executor diagnostics, without resuming.

Loads the complete executor, real PathRecorder and real timing observer. Only
engine/environment/opponent dependencies are one-transition fixtures. No official
games, registered development seeds, or policy-strength claims are involved.
TITAN_EXECUTOR_SOURCE selects exact before/after bytes at the canonical location.
"""
from contextlib import contextmanager, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

LAB = Path(__file__).resolve().parents[1] / 'cloud-model-lab'
SOURCE = Path(os.environ.get('TITAN_EXECUTOR_SOURCE', LAB / 'execute_arm.py'))


class Observation(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc


class Harness:
    def __init__(self, root):
        self.root, self.envs = root, []
        self.factory_calls = self.policy_calls = 0
        self.engine = types.ModuleType('kaggle_environments.envs.kaggriculture.kaggriculture')
        self.engine._spawn_weeds = lambda *a, **kw: None
        self.engine._end_of_day = lambda *a, **kw: None
        self.hooks = self.engine._spawn_weeds, self.engine._end_of_day
        self.routes = types.ModuleType('route_cards')
        self.routes.load_arlene = lambda: (object(), {'fixture': 'arlene'})
        self.opponents = types.ModuleType('arlene_arm')
        self.opponents.make_opponent = lambda *a: (lambda obs, cfg: {}, {'fixture': 'rival'})
        self.cards = types.ModuleType('cards')
        self.cards.make_env = self.make_env

    def make_env(self, seed):
        class Env:
            def __init__(self):
                self.done, self.steps = False, 0
                self.configuration = {'fixture': True}
                farms = [{'money': 10}, {'money': 7}]
                self.state = [types.SimpleNamespace(observation=Observation(
                    day=0, hour=0, farms=farms, town={'unlocked_shops': []})) for _ in range(2)]

            def reset(self, players):
                assert players == 2

            def step(self, actions):
                assert len(actions) == 2
                self.steps += 1
                self.done = True
        env = Env()
        self.envs.append(env)
        return env

    def factory(self):
        self.factory_calls += 1
        def actor(obs, cfg):
            self.policy_calls += 1
            return {}
        return actor

    def restored(self):
        return (self.engine._spawn_weeds is self.hooks[0]
                and self.engine._end_of_day is self.hooks[1])

    def invoke_main(self, *, seeds=('101',), no_path=False):
        arm, output = self.root / 'actor.py', self.root / 'result.json'
        arm.write_text('def agent(obs, cfg):\n    return {}\n', encoding='utf-8')
        argv = ['execute_arm.py', '--candidate', str(arm), '--control', str(arm),
                '--seeds', *seeds, '--seats', '0', '--opponents', 'arlene', '--out', str(output)]
        if no_path:
            argv.append('--no-path')
        with patch.object(sys, 'argv', argv), redirect_stdout(io.StringIO()):
            self.subject.main()
        return output

    def saved(self):
        return json.loads((self.root / 'result.json').read_text())


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory(prefix='titan-game-result-') as td:
        h = Harness(Path(td))
        package = types.ModuleType('kaggle_environments.envs.kaggriculture')
        package.kaggriculture = h.engine
        modules = {'cards': h.cards, 'continuation': types.ModuleType('continuation'),
                   'route_cards': h.routes, 'arlene_arm': h.opponents,
                   'kaggle_environments': types.ModuleType('kaggle_environments'),
                   'kaggle_environments.envs': types.ModuleType('kaggle_environments.envs'),
                   package.__name__: package, h.engine.__name__: h.engine}
        with patch.dict(sys.modules, modules):
            spec = importlib.util.spec_from_file_location('market_path', LAB / 'market_path.py')
            h.recorder = importlib.util.module_from_spec(spec)
            sys.modules['market_path'] = h.recorder
            spec.loader.exec_module(h.recorder)
            h.subject = types.ModuleType('_game_result_executor')
            h.subject.__file__ = str(LAB / 'execute_arm.py')
            exec(compile(SOURCE.read_bytes(), str(SOURCE), 'exec'), h.subject.__dict__)
            yield h


class GameFailureCheckpointTests(unittest.TestCase):
    def assert_cash(self, row):
        self.assertEqual((row['own_cash'], row['rival_cash'], row['margin']), (10.0, 7.0, 3.0))
        self.assertIsNone(row['error'])

    def test_direct_path_failure_keeps_exception_identity_and_known_outcome(self):
        with fixture() as h:
            failure = ValueError('path failed')
            with patch.object(h.recorder.PathRecorder, 'path', side_effect=failure):
                with self.assertRaises(ValueError) as caught:
                    h.subject.game(101, 0, 'arlene', h.factory, 'candidate')
            self.assertIs(caught.exception, failure)
            self.assert_cash(failure._titan_executor_row)
            self.assertEqual(failure._titan_executor_row['executor_error']['stage'], 'path')
            self.assertEqual(failure._titan_executor_row['executor_timing']['calls'], 1)
            self.assertNotIn('path', failure._titan_executor_row)
            self.assertTrue(h.restored())
            self.assertEqual((h.factory_calls, h.policy_calls), (1, 1))

    def test_candidate_path_failure_saves_two_results_then_stops(self):
        with fixture() as h:
            failure = ValueError('candidate path failed')
            with patch.object(h.recorder.PathRecorder, 'path', side_effect=[[], failure]):
                with self.assertRaises(ValueError) as caught:
                    h.invoke_main(seeds=('101', '102'))
            self.assertIs(caught.exception, failure)
            cp = h.saved()
            self.assertEqual(cp['checkpoint'], dict(complete=False, recorded_rows=2, expected_rows=4, failed_rows=0))
            self.assert_cash(cp['rows'][1])
            self.assertEqual(cp['rows'][1]['executor_error']['stage'], 'path')
            self.assertEqual(sum(e.steps for e in h.envs), 2)
            self.assertTrue(h.restored())

    def test_control_path_failure_saves_one_result_and_does_not_start_candidate(self):
        with fixture() as h:
            with patch.object(h.recorder.PathRecorder, 'path', side_effect=ValueError('stop')):
                with self.assertRaises(ValueError):
                    h.invoke_main()
            self.assertEqual(len(h.envs), 1)
            self.assertEqual(h.saved()['checkpoint']['recorded_rows'], 1)
            self.assertFalse(h.saved()['checkpoint']['complete'])
            self.assertEqual(h.saved()['rows'][0]['arm'], 'control')

    def test_route_setup_failure_saves_named_attempt_without_fake_scores(self):
        with fixture() as h:
            failure = RuntimeError('route source missing')
            with patch.object(h.routes, 'load_arlene', side_effect=failure):
                with self.assertRaises(RuntimeError) as caught:
                    h.invoke_main()
            self.assertIs(caught.exception, failure)
            row = h.saved()['rows'][0]
            self.assertEqual((row['seed'], row['seat'], row['opponent'], row['arm']), (101, 0, 'arlene', 'control'))
            self.assertIsNone(row['margin'])
            self.assertIsNone(row['executor_timing'])
            self.assertEqual(row['error'], 'RuntimeError: route source missing')
            self.assertEqual(h.saved()['checkpoint']['failed_rows'], 1)
            self.assertEqual(len(h.envs), 0)

    def test_candidate_route_failure_preserves_control_and_stops(self):
        with fixture() as h:
            with patch.object(h.routes, 'load_arlene', side_effect=[(object(), {}), RuntimeError('missing')]):
                with self.assertRaises(RuntimeError):
                    h.invoke_main()
            self.assertEqual(h.saved()['checkpoint'], dict(complete=False, recorded_rows=2, expected_rows=2, failed_rows=1))
            self.assert_cash(h.saved()['rows'][0])
            self.assertIsNone(h.saved()['rows'][1]['own_cash'])
            self.assertEqual(sum(e.steps for e in h.envs), 1)

    def test_recorder_constructor_failure_retains_attempt(self):
        with fixture() as h:
            with patch.object(h.recorder, 'PathRecorder', side_effect=RuntimeError('constructor')):
                with self.assertRaises(RuntimeError):
                    h.invoke_main()
            self.assertEqual(h.saved()['rows'][0]['executor_error']['stage'], 'setup')
            self.assertEqual(len(h.envs), 0)
            self.assertTrue(h.restored())

    def test_recorder_enter_failure_retains_attempt(self):
        with fixture() as h:
            with patch.object(h.recorder.PathRecorder, '__enter__', side_effect=ModuleNotFoundError('engine missing')):
                with self.assertRaises(ModuleNotFoundError):
                    h.invoke_main()
            self.assertEqual(h.saved()['rows'][0]['error'], 'ModuleNotFoundError: engine missing')
            self.assertEqual(len(h.envs), 0)
            self.assertTrue(h.restored())

    def test_timing_failure_retains_completed_cash_and_stops(self):
        with fixture() as h:
            failure = ValueError('timing report failed')
            with patch.object(h.subject.TimedFactory, 'timings', side_effect=failure):
                with self.assertRaises(ValueError) as caught:
                    h.invoke_main()
            self.assertIs(caught.exception, failure)
            row = h.saved()['rows'][0]
            self.assert_cash(row)
            self.assertEqual(row['executor_error']['stage'], 'timing')
            self.assertTrue(h.restored())

    def test_primary_policy_error_and_secondary_path_error_both_survive(self):
        with fixture() as h:
            def bad_factory():
                def actor(obs, cfg):
                    raise RuntimeError('primary actor failure')
                return actor
            failure = ValueError('secondary path failure')
            with patch.object(h.recorder.PathRecorder, 'path', side_effect=failure):
                with self.assertRaises(ValueError):
                    h.subject.game(101, 0, 'arlene', bad_factory, 'candidate')
            row = failure._titan_executor_row
            self.assertEqual(row['error'], 'RuntimeError: primary actor failure')
            self.assertEqual(row['executor_error']['error'], 'ValueError: secondary path failure')
            self.assertIsNone(row['margin'])
            self.assertEqual(row['executor_timing']['failures'], 1)
            self.assertTrue(h.restored())

    def test_cleanup_failure_saves_known_result_and_stops_before_next_game(self):
        with fixture() as h:
            failure = RuntimeError('cleanup failure')
            with patch.object(h.recorder.PathRecorder, '__exit__', side_effect=failure):
                with self.assertRaises(RuntimeError) as caught:
                    h.invoke_main()
            self.assertIs(caught.exception, failure)
            self.assertEqual(len(h.envs), 1)
            row = h.saved()['rows'][0]
            self.assert_cash(row)
            self.assertEqual(row['executor_error']['stage'], 'cleanup')
            self.assertFalse(h.saved()['checkpoint']['complete'])
            self.assertFalse(h.restored())

    def test_cancellation_from_policy_remains_unconverted(self):
        for kind in (KeyboardInterrupt, SystemExit):
            with self.subTest(kind=kind.__name__), fixture() as h:
                failure = kind('cancel')
                def factory():
                    def actor(obs, cfg):
                        raise failure
                    return actor
                with self.assertRaises(kind) as caught:
                    h.subject.game(101, 0, 'arlene', factory, 'candidate')
                self.assertIs(caught.exception, failure)
                self.assertFalse(hasattr(failure, '_titan_executor_row'))
                self.assertTrue(h.restored())

    def test_cancellation_from_diagnostic_does_not_manufacture_checkpoint(self):
        for kind in (KeyboardInterrupt, SystemExit):
            with self.subTest(kind=kind.__name__), fixture() as h:
                failure = kind('cancel diagnostic')
                with patch.object(h.recorder.PathRecorder, 'path', side_effect=failure):
                    with self.assertRaises(kind) as caught:
                        h.invoke_main()
                self.assertIs(caught.exception, failure)
                self.assertFalse((h.root / 'result.json').exists())
                self.assertTrue(h.restored())

    def test_cancellation_during_setup_remains_original_and_uncheckpointed(self):
        with fixture() as h:
            failure = KeyboardInterrupt('cancel setup')
            with patch.object(h.routes, 'load_arlene', side_effect=failure):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    h.invoke_main()
            self.assertIs(caught.exception, failure)
            self.assertFalse((h.root / 'result.json').exists())

    def test_healthy_pair_preserves_schema_and_writer_count(self):
        with fixture() as h:
            with patch.object(os, 'replace', wraps=os.replace) as replace:
                h.invoke_main(no_path=True)
            self.assertEqual(replace.call_count, 3)
            self.assertEqual(h.saved()['checkpoint'], dict(complete=True, recorded_rows=2, expected_rows=2, failed_rows=0))
            self.assertTrue(all('executor_error' not in row for row in h.saved()['rows']))
            self.assertTrue(all('path' not in row for row in h.saved()['rows']))

    def test_success_both_seats_keeps_one_factory_and_one_action(self):
        for seat, margin in ((0, 3.0), (1, -3.0)):
            with self.subTest(seat=seat), fixture() as h:
                row = h.subject.game(101, seat, 'arlene', h.factory, 'candidate')
                self.assertEqual(row['margin'], margin)
                self.assertEqual((h.factory_calls, h.policy_calls), (1, 1))
                self.assertNotIn('executor_error', row)
                self.assertTrue(h.restored())

    def test_ordinary_policy_failure_still_returns_existing_row(self):
        with fixture() as h:
            def factory():
                def actor(obs, cfg):
                    raise ValueError('policy failed')
                return actor
            row = h.subject.game(101, 0, 'arlene', factory, 'candidate')
            self.assertEqual(row['error'], 'ValueError: policy failed')
            self.assertIsNone(row['margin'])
            self.assertNotIn('executor_error', row)
            self.assertEqual(row['executor_timing']['calls'], 1)
            self.assertTrue(h.restored())

    def test_checkpoint_disk_failure_preserves_last_file_and_stops(self):
        with fixture() as h:
            failure = ValueError('candidate path failed')
            real_replace, calls = os.replace, []
            def replace(src, dst):
                calls.append((src, dst))
                if len(calls) == 2:
                    raise OSError('storage failure')
                return real_replace(src, dst)
            with patch.object(h.recorder.PathRecorder, 'path', side_effect=[[], failure]), \
                    patch.object(os, 'replace', side_effect=replace):
                with self.assertRaisesRegex(OSError, 'storage failure') as caught:
                    h.invoke_main(seeds=('101', '102'))
            self.assertIs(caught.exception.__context__, failure)
            self.assertEqual(h.saved()['checkpoint']['recorded_rows'], 1)
            self.assertEqual(len(h.envs), 2)
            self.assertEqual(list(h.root.glob('.execute-arm-*.json.tmp')), [])
            self.assertTrue(h.restored())

    def test_exception_refusing_annotation_remains_original(self):
        class RefusesMetadata(ValueError):
            def __setattr__(self, name, value):
                if name == '_titan_executor_row':
                    raise RuntimeError('metadata refused')
                return super().__setattr__(name, value)
        with fixture() as h:
            failure = RefusesMetadata('original diagnostic')
            with patch.object(h.recorder.PathRecorder, 'path', side_effect=failure):
                with self.assertRaises(RefusesMetadata) as caught:
                    h.invoke_main()
            self.assertIs(caught.exception, failure)
            self.assertFalse((h.root / 'result.json').exists())
            self.assertTrue(h.restored())

    def test_unannotated_failure_does_not_create_a_guessed_row(self):
        with fixture() as h:
            failure = RuntimeError('unannotated')
            with patch.object(h.subject, 'game', side_effect=failure):
                with self.assertRaises(RuntimeError) as caught:
                    h.invoke_main()
            self.assertIs(caught.exception, failure)
            self.assertFalse((h.root / 'result.json').exists())

    def test_mismatched_failure_identity_is_not_checkpointed(self):
        with fixture() as h:
            failure = RuntimeError('other cell')
            failure._titan_executor_row = {'seed': 102, 'seat': 0, 'opponent': 'arlene', 'arm': 'control'}
            with patch.object(h.subject, 'game', side_effect=failure):
                with self.assertRaises(RuntimeError):
                    h.invoke_main()
            self.assertFalse((h.root / 'result.json').exists())


    def test_exception_refusing_metadata_read_remains_original(self):
        class RefusesRead(ValueError):
            def __getattribute__(self, name):
                if name == '_titan_executor_row':
                    raise RuntimeError('metadata read refused')
                return super().__getattribute__(name)
        with fixture() as h:
            failure = RefusesRead('original diagnostic')
            with patch.object(h.recorder.PathRecorder, 'path', side_effect=failure):
                with self.assertRaises(RefusesRead) as caught:
                    h.invoke_main()
            self.assertIs(caught.exception, failure)
            self.assertFalse((h.root / 'result.json').exists())
            self.assertTrue(h.restored())

    def test_cleanup_error_during_cancellation_does_not_manufacture_row(self):
        with fixture() as h:
            cancellation, cleanup = KeyboardInterrupt('cancel'), RuntimeError('cleanup')
            with patch.object(h.recorder.PathRecorder, 'path', side_effect=cancellation), \
                    patch.object(h.recorder.PathRecorder, '__exit__', side_effect=cleanup):
                with self.assertRaises(RuntimeError) as caught:
                    h.invoke_main()
            self.assertIs(caught.exception, cleanup)
            self.assertIs(caught.exception.__context__, cancellation)
            self.assertFalse((h.root / 'result.json').exists())
            self.assertFalse(hasattr(cleanup, '_titan_executor_row'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
