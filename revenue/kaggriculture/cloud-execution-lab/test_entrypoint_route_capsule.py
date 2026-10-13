# SPDX-License-Identifier: Apache-2.0
"""Keep completed route identity without reviving interrupted runtime state."""
from copy import deepcopy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
if ROOT.name == 'checks':
    ROOT = ROOT.parent
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
    def __init__(self, route=None, proposed=None):
        self.features = SimpleNamespace(budget_seconds=1.0, reserve_seconds=0.01,
                                        consumer='frozen')
        self.town_procurement_enabled = False
        self._completed_route = route
        self.controller = SimpleNamespace(cur=proposed or route)
        self.selected = None
        self.ready = True
        self.diagnostics = {}

    def act(self, _observation, _configuration=None, *, entry_started=None):
        self.selected = deepcopy(PASS)
        self.diagnostics = {'status': 'completed'}
        return deepcopy(PASS)


class EntrypointRouteCapsuleTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('_route_capsule_entrypoint', ROOT / 'main.py')
        self.entry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.entry)
        ControlledTimer.cancel_on_exit = False
        self.timer = patch.object(deadline, '_DeadlineTimer', ControlledTimer)
        self.timer.start()
        self.addCleanup(self.timer.stop)
        self.config = {'episodeSteps': 720}

    @staticmethod
    def obs(step, player=0):
        return {'step': step, 'player': player, 'farms': [{'hands': []}, {'hands': []}],
                'private': {}}

    def cancel(self, instance, step=227):
        self.entry._INSTANCE = instance
        ControlledTimer.cancel_on_exit = True
        self.assertEqual(self.entry.agent(self.obs(step), self.config), PASS)
        ControlledTimer.cancel_on_exit = False
        self.assertIsNone(self.entry._INSTANCE)

    def resume(self, step=228, player=0):
        fresh = Instance()
        with patch.object(self.entry, '_new_instance', return_value=fresh), \
                patch('json.loads', return_value={'town_procurement': False}):
            self.assertEqual(self.entry.agent(self.obs(step, player), self.config), PASS)
        return fresh

    def test_completed_route_survives_whole_call_cancellation(self):
        old = Instance('YARN')
        old._entrypoint_last_step = 226
        self.cancel(old)
        self.assertEqual(self.entry._ROUTE_RECOVERY,
                         {'route_step': 227, 'last_step': 227,
                          'player': 0, 'route': 'YARN'})
        fresh = self.resume()
        self.assertEqual(fresh._completed_route, 'YARN')
        self.assertIsNot(fresh, old)
        self.assertIsNone(self.entry._ROUTE_RECOVERY)

    def test_uncommitted_controller_choice_is_not_promoted(self):
        old = Instance('YARN', proposed='UNRETURNED_BRANCH')
        self.cancel(old)
        self.assertEqual(self.resume()._completed_route, 'YARN')

    def test_runtime_cancellation_before_selection_keeps_prior_route_provenance(self):
        old = Instance('YARN', proposed='UNRETURNED_BRANCH')
        old._entrypoint_last_step = 227
        old._entrypoint_last_player = 0
        old._completed_route_step = 227
        old._entrypoint_route_receipt = {
            'route_step': 227,
            'last_step': 227,
            'player': 0,
            'route': 'YARN',
        }

        def interrupted_before_selection(*_args, **_kwargs):
            raise ControlledTimer.active.expired

        old.act = interrupted_before_selection
        self.entry._INSTANCE = old
        self.assertEqual(self.entry.agent(self.obs(228), self.config), PASS)
        self.assertIsNone(self.entry._INSTANCE)
        self.assertEqual(self.entry._ROUTE_RECOVERY,
                         {'route_step': 227, 'last_step': 228,
                          'player': 0, 'route': 'YARN'})
        self.assertEqual(self.resume(229)._completed_route, 'YARN')

    def test_live_prelude_then_runtime_cancellation_keeps_original_route_step(self):
        live = Instance('YARN')
        live.post = None
        live._remember_seller_fallback = lambda _obs: None
        self.entry._INSTANCE = live
        self.assertEqual(self.entry.agent(self.obs(227), self.config), PASS)
        self.assertEqual(getattr(live, '_completed_route_step', None), 227)

        # A live-instance prelude fallback observes callback 228 but completes no
        # new producer route. It may advance the observation watermark, never
        # the immutable origin of YARN.
        with patch('time.perf_counter', side_effect=[0.0, 2.0, 2.0, 2.0]):
            self.assertEqual(self.entry.agent(self.obs(228), self.config), PASS)
        self.assertIs(self.entry._INSTANCE, live)
        self.assertEqual(live._completed_route, 'YARN')
        self.assertEqual(live._entrypoint_route_receipt,
                         {'route_step': 227, 'last_step': 228,
                          'player': 0, 'route': 'YARN'})

        def interrupted_before_selection(*_args, **_kwargs):
            live.controller.cur = 'UNRETURNED_BRANCH'
            raise ControlledTimer.active.expired

        live.act = interrupted_before_selection
        self.assertEqual(self.entry.agent(self.obs(229), self.config), PASS)
        self.assertIsNone(self.entry._INSTANCE)
        self.assertEqual(self.entry._ROUTE_RECOVERY,
                         {'route_step': 227, 'last_step': 229,
                          'player': 0, 'route': 'YARN'})
        self.assertEqual(self.resume(230)._completed_route, 'YARN')

    def test_constructor_cancellation_advances_observed_watermark(self):
        self.cancel(Instance('YARN'))
        saved = deepcopy(self.entry._ROUTE_RECOVERY)

        def interrupted_constructor(*_args):
            raise ControlledTimer.active.expired

        with patch.object(self.entry, '_new_instance', side_effect=interrupted_constructor), \
                patch('json.loads', return_value={'town_procurement': False}):
            self.assertEqual(self.entry.agent(self.obs(228), self.config), PASS)
        self.assertEqual(self.entry._ROUTE_RECOVERY,
                         {**saved, 'last_step': 228})
        self.assertEqual(self.resume(229)._completed_route, 'YARN')

    def test_prelude_budget_fallback_advances_observed_watermark(self):
        self.cancel(Instance('YARN'))
        saved = deepcopy(self.entry._ROUTE_RECOVERY)
        with patch('time.perf_counter', side_effect=[0.0, 2.0]), \
                patch('json.loads', return_value={'town_procurement': False}), \
                patch.object(self.entry, '_new_instance') as constructor:
            self.assertEqual(self.entry.agent(self.obs(228), self.config), PASS)
        constructor.assert_not_called()
        self.assertEqual(self.entry._ROUTE_RECOVERY,
                         {**saved, 'last_step': 228})
        self.assertEqual(self.resume(229)._completed_route, 'YARN')

    def test_skipped_callback_refuses_stale_route(self):
        self.cancel(Instance('YARN'))
        fresh = self.resume(230)
        self.assertIsNone(fresh._completed_route)
        self.assertIsNone(self.entry._ROUTE_RECOVERY)

    def test_new_episode_discards_old_route(self):
        self.cancel(Instance('YARN'))
        self.assertIsNone(self.resume(0)._completed_route)
        self.assertIsNone(self.entry._ROUTE_RECOVERY)

    def test_same_step_zero_retry_retains_step_zero_capsule(self):
        self.cancel(Instance('MAIN'), step=0)
        self.assertEqual(self.resume(0)._completed_route, 'MAIN')

    def test_other_player_and_rewind_do_not_reuse_route(self):
        for step, player in ((228, 1), (226, 0)):
            with self.subTest(step=step, player=player):
                self.cancel(Instance('YARN'))
                self.assertIsNone(self.resume(step, player)._completed_route)


if __name__ == '__main__':
    unittest.main(verbosity=2)
