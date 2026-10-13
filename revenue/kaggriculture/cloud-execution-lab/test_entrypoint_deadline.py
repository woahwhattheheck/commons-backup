# SPDX-License-Identifier: Apache-2.0
"""Whole-entrypoint deadline containment for canonical TITAN."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
if ROOT.name == 'checks':
    ROOT = ROOT.parent


def load_entrypoint():
    name = '_titan_entrypoint_deadline_test'
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, ROOT/'main.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Features:
    def __init__(self, budget_seconds=0.04, reserve_seconds=0.015):
        self.budget_seconds = budget_seconds
        self.reserve_seconds = reserve_seconds
        self.consumer = 'frozen'


class _FakeInstance:
    town_procurement_enabled = False

    def __init__(self, action, *, returned=None, publish_selected=True,
                 diagnostics=None, duration=0.08, error=None):
        self.features = _Features()
        self.action = deepcopy(action)
        self.returned = deepcopy(action if returned is None else returned)
        self.publish_selected = publish_selected
        self.selected = None
        self.diagnostics = dict(diagnostics or {})
        self.duration = duration
        self.error = error
        self.ready = True
        self.post = None
        self.fallback_observations = []

    def _remember_seller_fallback(self, observation):
        self.fallback_observations.append(deepcopy(observation))

    def act(self, _observation, _configuration=None, *, entry_started=None):
        # Match TitanAgent's stale-selection boundary.
        self.selected = None
        if self.publish_selected:
            self.selected = deepcopy(self.action)
        if self.error is not None:
            raise self.error
        end = time.perf_counter() + self.duration
        while time.perf_counter() < end:
            pass
        return deepcopy(self.returned)


class _NestedFinalizer(_FakeInstance):
    """Exercise the actual inner/outer DeadlineTimer ownership protocol."""
    def act(self, _observation, _configuration=None, *, entry_started=None):
        from titan_runtime import deadline
        self.selected = deepcopy(self.action)
        inner = deadline._DeadlineTimer(
            self.features.budget_seconds-self.features.reserve_seconds)
        try:
            with inner:
                while True:
                    pass
        except deadline.DeadlineExceeded as error:
            if error is not inner.expired:
                raise
            self.diagnostics = {
                'status': 'deadline_fallback',
                'fallback_stage': 'selected_transform',
                'elapsed_seconds': self.features.budget_seconds-self.features.reserve_seconds,
            }
        # This models the currently unguarded post-controller finalizer. The
        # entrypoint's outer budget must cancel it on both signal and trace paths.
        while True:
            pass


class _CheckpointFinalizer(_FakeInstance):
    """Publish one completed finalizer stage, then hang in the next stage."""
    def act(self, observation, _configuration=None, *, entry_started=None):
        self.selected = deepcopy(self.action)
        improved = deepcopy(self.action)
        improved['market'][0][2] = 7
        self._finalizer_checkpoint = {
            'step': int(observation['step']),
            'player': int(observation['player']),
            'stage': 'feed_stock',
            'action': deepcopy(improved),
        }
        self.diagnostics = {'status': 'completed'}
        while True:
            pass


class EntrypointDeadlineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        cls.main = load_entrypoint()
        from titan_runtime import deadline
        cls.deadline = deadline

    def setUp(self):
        self.main._INSTANCE = None
        self.observation = {
            'step': 100,
            'player': 0,
            'farms': [{'hands': [[4, 4]]}, {'hands': []}],
            'private': {},
        }
        self.configuration = {'episodeSteps': 720}
        self.selected = {
            'farmer': ['PASS'],
            'hands': [['PASS']],
            'market': [['SELL', 'CARROT', 1]],
        }

    def run_agent(self):
        started = time.perf_counter()
        output = self.main.agent(self.observation, self.configuration)
        return output, time.perf_counter()-started

    def assert_outer_fallback(self, fake, output, elapsed):
        self.assertEqual(output, self.selected)
        self.assertIsNone(self.main._INSTANCE)
        self.assertFalse(fake.ready)
        self.assertLess(elapsed, 0.5)
        self.assertEqual(fake.diagnostics['status'], 'deadline_fallback')
        self.assertEqual(fake.diagnostics['fallback_stage'], 'entrypoint_finalization')
        self.assertTrue(fake.diagnostics['entrypoint_guard'])

    def test_exhausted_cold_prelude_returns_without_constructing(self):
        fake = _FakeInstance(self.selected, duration=0)
        real_loads = __import__('json').loads

        def delayed_loads(raw, *args, **kwargs):
            feature_data = real_loads(raw, *args, **kwargs)
            feature_data.update(budget_seconds=0.02, reserve_seconds=0.005)
            end = time.perf_counter() + 0.025
            while time.perf_counter() < end:
                pass
            return feature_data

        self.observation['step'] = 0
        with patch('json.loads', side_effect=delayed_loads), \
                patch.object(
                    self.main, '_new_instance',
                    side_effect=AssertionError('constructor started after deadline'),
                ) as constructor:
            output = self.main.agent(self.observation, self.configuration)
        self.assertEqual(
            output,
            {'farmer': ['PASS'], 'hands': [['PASS']], 'market': []},
        )
        constructor.assert_not_called()
        self.assertIsNone(self.main._INSTANCE)

        # Deferring cold construction is recoverable: the next visible state
        # initializes normally instead of retaining a partial step-zero object.
        self.observation['step'] = 1
        with patch.object(self.main, '_new_instance', return_value=fake) as constructor:
            output = self.main.agent(self.observation, self.configuration)
        constructor.assert_called_once()
        self.assertEqual(output, self.selected)
        self.assertIs(self.main._INSTANCE, fake)
        self.assertTrue(fake.ready)

    def test_late_runtime_is_bounded_and_returns_current_selected(self):
        later = deepcopy(self.selected)
        later['market'][0][2] = 2
        fake = _FakeInstance(
            self.selected,
            returned=later,
            diagnostics={'status': 'completed'},
        )
        self.main._INSTANCE = fake
        output, elapsed = self.run_agent()
        self.assert_outer_fallback(fake, output, elapsed)

    def test_outer_deadline_keeps_last_completed_finalizer_checkpoint(self):
        fake = _CheckpointFinalizer(self.selected)
        self.main._INSTANCE = fake
        output, elapsed = self.run_agent()
        expected = deepcopy(self.selected)
        expected['market'][0][2] = 7
        self.assertEqual(output, expected)
        self.assertIsNone(self.main._INSTANCE)
        self.assertFalse(fake.ready)
        self.assertLess(elapsed, 0.5)
        self.assertEqual(fake.diagnostics['status'], 'deadline_fallback')
        self.assertEqual(fake.diagnostics['fallback_stage'], 'entrypoint_finalization')
        self.assertEqual(fake.diagnostics['entrypoint_checkpoint_stage'], 'feed_stock')
        self.assertTrue(fake.diagnostics['entrypoint_guard'])

    def test_nested_main_thread_timer_reserves_finalization_window(self):
        fake = _NestedFinalizer(self.selected)
        self.main._INSTANCE = fake
        output, elapsed = self.run_agent()
        self.assert_outer_fallback(fake, output, elapsed)
        self.assertEqual(fake.diagnostics['inner_fallback_stage'], 'selected_transform')

    def test_nested_worker_timer_reserves_finalization_window(self):
        fake = _NestedFinalizer(self.selected)
        self.main._INSTANCE = fake
        with ThreadPoolExecutor(1) as pool:
            output, elapsed = pool.submit(self.run_agent).result(timeout=2)
        self.assert_outer_fallback(fake, output, elapsed)
        self.assertIsNone(sys.gettrace())
        self.assertIsNone(self.deadline._ACTIVE_TIMER.get())

    def test_prior_step_selected_is_never_reused(self):
        stale = deepcopy(self.selected)
        stale['market'] = [['SELL', 'MILK', 99]]
        fake = _FakeInstance(self.selected, publish_selected=False)
        fake.selected = stale
        self.main._INSTANCE = fake
        output, _elapsed = self.run_agent()
        self.assertEqual(
            output,
            {'farmer': ['PASS'], 'hands': [['PASS']], 'market': []},
        )
        self.assertNotEqual(output, stale)
        self.assertIsNone(self.main._INSTANCE)

    def test_prior_attempt_checkpoint_is_never_reused(self):
        stale = deepcopy(self.selected)
        stale['market'] = [['SELL', 'MILK', 99]]
        fake = _FakeInstance(self.selected, publish_selected=False)
        fake._finalizer_checkpoint = {
            'step': self.observation['step'],
            'player': self.observation['player'],
            'stage': 'town_procurement',
            'action': stale,
        }
        self.main._INSTANCE = fake
        output, _elapsed = self.run_agent()
        self.assertEqual(
            output,
            {'farmer': ['PASS'], 'hands': [['PASS']], 'market': []},
        )
        self.assertNotEqual(output, stale)
        self.assertIsNone(self.main._INSTANCE)

    def test_normal_runtime_preserves_output_and_instance(self):
        fake = _FakeInstance(self.selected, duration=0)
        self.main._INSTANCE = fake
        output, _elapsed = self.run_agent()
        self.assertEqual(output, self.selected)
        self.assertIs(self.main._INSTANCE, fake)
        self.assertTrue(fake.ready)
        self.assertNotIn('entrypoint_guard', fake.diagnostics)

    def test_foreign_deadline_sentinel_propagates_by_identity(self):
        foreign = self.deadline.DeadlineExceeded('foreign deadline')
        fake = _FakeInstance(self.selected, error=foreign)
        self.main._INSTANCE = fake
        with self.assertRaises(self.deadline.DeadlineExceeded) as caught:
            self.main.agent(self.observation, self.configuration)
        self.assertIs(caught.exception, foreign)
        self.assertIs(self.main._INSTANCE, fake)
        self.assertTrue(fake.ready)

    def test_inner_deadline_receipt_is_retained(self):
        fake = _FakeInstance(
            self.selected,
            diagnostics={
                'status': 'deadline_fallback',
                'fallback_stage': 'selected_transform',
                'elapsed_seconds': 0.02,
            },
        )
        self.main._INSTANCE = fake
        output, elapsed = self.run_agent()
        self.assert_outer_fallback(fake, output, elapsed)
        self.assertEqual(fake.diagnostics['inner_fallback_stage'], 'selected_transform')
        self.assertEqual(fake.diagnostics['inner_elapsed_seconds'], 0.02)


if __name__ == '__main__':
    unittest.main()
