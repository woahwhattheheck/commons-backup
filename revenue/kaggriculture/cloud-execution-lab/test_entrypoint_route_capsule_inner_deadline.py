# SPDX-License-Identifier: Apache-2.0
"""Bind an inner selected fallback route before an outer entrypoint cancellation."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from titan_runtime import deadline
from test_entrypoint_route_capsule_continuity import ControlledTimer, Instance, PASS


class EntrypointRouteInnerDeadlineTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            '_route_capsule_inner_deadline_entrypoint', ROOT / 'main.py'
        )
        self.entry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.entry)
        ControlledTimer.cancel_on_exit = False
        self.timer = patch.object(deadline, '_DeadlineTimer', ControlledTimer)
        self.timer.start()
        self.addCleanup(self.timer.stop)
        self.addCleanup(setattr, ControlledTimer, 'cancel_on_exit', False)
        self.config = {'episodeSteps': 720}

    @staticmethod
    def obs(step, player=0):
        return {
            'step': step,
            'player': player,
            'farms': [{'hands': []}, {'hands': []}],
            'private': {},
        }

    def test_selected_inner_deadline_route_is_current_provenance(self):
        live = Instance('YARN')
        self.entry._INSTANCE = live
        self.assertEqual(self.entry.agent(self.obs(227), self.config), PASS)
        self.assertEqual(getattr(live, '_completed_route_step', None), 227)

        def safe_inner_fallback(*_args, **_kwargs):
            # TitanAgent's real inner-deadline path commits selected_checkpoint[1]
            # to _completed_route before returning status=deadline_fallback.
            live._completed_route = 'WOOL'
            live.controller.cur = 'WOOL'
            live.selected = deepcopy(PASS)
            live.diagnostics = {
                'status': 'deadline_fallback',
                'fallback_stage': 'market_pressure',
            }
            return deepcopy(PASS)

        ControlledTimer.cancel_on_exit = True
        with patch.object(live, 'act', side_effect=safe_inner_fallback):
            self.assertEqual(self.entry.agent(self.obs(228), self.config), PASS)
        ControlledTimer.cancel_on_exit = False

        self.assertIsNone(self.entry._INSTANCE)
        self.assertEqual(
            self.entry._ROUTE_RECOVERY,
            {
                'route_step': 228,
                'last_step': 228,
                'player': 0,
                'route': 'WOOL',
            },
        )


if __name__ == '__main__':
    unittest.main(verbosity=2)
