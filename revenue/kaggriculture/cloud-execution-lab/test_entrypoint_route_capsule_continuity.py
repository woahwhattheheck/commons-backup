# SPDX-License-Identifier: Apache-2.0
"""Postmerge continuity predecessors for completed-route recovery."""
from copy import deepcopy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from titan_runtime import deadline

PASS = {'farmer': ['PASS'], 'hands': [], 'market': []}


class ControlledTimer:
    active = None
    cancel_on_exit = False

    def __init__(self, _seconds):
        self.expired = deadline.DeadlineExceeded('controlled outer cancellation')

    def __enter__(self):
        type(self).active = self
        return self

    def __exit__(self, kind, _error, _traceback):
        type(self).active = None
        if kind is None and type(self).cancel_on_exit:
            raise self.expired
        return False


class Instance:
    def __init__(self, route=None):
        self.features = SimpleNamespace(
            budget_seconds=1.0,
            reserve_seconds=0.01,
            consumer='frozen',
        )
        self.town_procurement_enabled = False
        self._completed_route = route
        self.controller = SimpleNamespace(cur=route)
        self.selected = None
        self.ready = True
        self.diagnostics = {}

    def act(self, _observation, _configuration=None, *, entry_started=None):
        self.selected = deepcopy(PASS)
        self.diagnostics = {'status': 'completed'}
        return deepcopy(PASS)


class InterruptedBeforeProducer(Instance):
    """Fresh runtime that never publishes a current-callback selection."""

    def act(self, _observation, _configuration=None, *, entry_started=None):
        self.controller.cur = 'UNRETURNED_NEW_ROUTE'
        raise ControlledTimer.active.expired


class EntrypointRouteCapsuleContinuityTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            '_route_capsule_continuity_entrypoint', ROOT / 'main.py'
        )
        self.entry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.entry)
        ControlledTimer.cancel_on_exit = False
        self.timer = patch.object(deadline, '_DeadlineTimer', ControlledTimer)
        self.timer.start()
        self.addCleanup(self.timer.stop)
        self.config = {'episodeSteps': 720}

    @staticmethod
    def obs(step, player=0):
        return {
            'step': step,
            'player': player,
            'farms': [{'hands': []}, {'hands': []}],
            'private': {},
        }

    def cancel(self, instance, step=227):
        self.entry._INSTANCE = instance
        ControlledTimer.cancel_on_exit = True
        self.assertEqual(self.entry.agent(self.obs(step), self.config), PASS)
        ControlledTimer.cancel_on_exit = False
        self.assertIsNone(self.entry._INSTANCE)

    def resume(self, step, player=0):
        fresh = Instance()
        with patch.object(self.entry, '_new_instance', return_value=fresh), \
                patch('json.loads', return_value={'town_procurement': False}):
            self.assertEqual(self.entry.agent(self.obs(step, player), self.config), PASS)
        return fresh

    def test_capsule_binds_completed_route_step_and_observed_watermark(self):
        old = Instance('YARN')
        old._entrypoint_last_step = 226
        self.cancel(old, 227)
        self.assertEqual(
            self.entry._ROUTE_RECOVERY,
            {
                'route_step': 227,
                'last_step': 227,
                'player': 0,
                'route': 'YARN',
            },
        )

    def test_skipped_callback_retires_stale_route(self):
        self.cancel(Instance('YARN'), 227)
        fresh = self.resume(230)
        self.assertIsNone(fresh._completed_route)
        self.assertIsNone(self.entry._ROUTE_RECOVERY)

    def test_constructor_cancellation_advances_observed_watermark(self):
        self.cancel(Instance('YARN'), 227)

        def interrupted_constructor(*_args):
            raise ControlledTimer.active.expired

        with patch.object(self.entry, '_new_instance', side_effect=interrupted_constructor), \
                patch('json.loads', return_value={'town_procurement': False}):
            self.assertEqual(self.entry.agent(self.obs(228), self.config), PASS)

        self.assertEqual(
            self.entry._ROUTE_RECOVERY,
            {
                'route_step': 227,
                'last_step': 228,
                'player': 0,
                'route': 'YARN',
            },
        )
        self.assertEqual(self.resume(229)._completed_route, 'YARN')

    def test_entrypoint_prelude_fallback_advances_observed_watermark(self):
        self.cancel(Instance('YARN'), 227)
        # The first call starts the entrypoint clock; the second makes the
        # construction prelude exhaust its one-second budget before _new_instance.
        with patch('time.perf_counter', side_effect=[0.0, 2.0]), \
                patch('json.loads', return_value={'town_procurement': False}), \
                patch.object(self.entry, '_new_instance') as constructor:
            self.assertEqual(self.entry.agent(self.obs(228), self.config), PASS)
        constructor.assert_not_called()
        self.assertEqual(
            self.entry._ROUTE_RECOVERY,
            {
                'route_step': 227,
                'last_step': 228,
                'player': 0,
                'route': 'YARN',
            },
        )
        self.assertEqual(self.resume(229)._completed_route, 'YARN')

    def test_interrupted_fresh_callback_does_not_restamp_prior_route(self):
        self.cancel(Instance('YARN'), 227)
        fresh = InterruptedBeforeProducer()
        with patch.object(self.entry, '_new_instance', return_value=fresh), \
                patch('json.loads', return_value={'town_procurement': False}):
            self.assertEqual(self.entry.agent(self.obs(228), self.config), PASS)
        self.assertEqual(fresh._completed_route, 'YARN')
        self.assertEqual(fresh.controller.cur, 'UNRETURNED_NEW_ROUTE')
        self.assertEqual(
            self.entry._ROUTE_RECOVERY,
            {
                'route_step': 227,
                'last_step': 228,
                'player': 0,
                'route': 'YARN',
            },
        )
        self.assertEqual(self.resume(229)._completed_route, 'YARN')

    def test_live_instance_preproducer_cancellation_preserves_route_origin(self):
        live = Instance('YARN')
        self.entry._INSTANCE = live
        self.assertEqual(self.entry.agent(self.obs(227), self.config), PASS)
        self.assertEqual(getattr(live, '_completed_route_step', None), 227)

        def interrupted_live_callback(*_args, **_kwargs):
            live.controller.cur = 'UNRETURNED_NEW_ROUTE'
            raise ControlledTimer.active.expired

        with patch.object(live, 'act', side_effect=interrupted_live_callback):
            self.assertEqual(self.entry.agent(self.obs(228), self.config), PASS)
        self.assertIsNone(self.entry._INSTANCE)
        self.assertEqual(live.controller.cur, 'UNRETURNED_NEW_ROUTE')
        self.assertEqual(
            self.entry._ROUTE_RECOVERY,
            {
                'route_step': 227,
                'last_step': 228,
                'player': 0,
                'route': 'YARN',
            },
        )
        self.assertEqual(self.resume(229)._completed_route, 'YARN')

    def test_malformed_capsule_retires_before_restore(self):
        self.entry._ROUTE_RECOVERY = {
            'route_step': 227,
            'last_step': 227,
            'player': 0,
            'route': 'YARN',
            'extra': True,
        }
        fresh = self.resume(228)
        self.assertIsNone(fresh._completed_route)
        self.assertIsNone(self.entry._ROUTE_RECOVERY)


if __name__ == '__main__':
    unittest.main(verbosity=2)
