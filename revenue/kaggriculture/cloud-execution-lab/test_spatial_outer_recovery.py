# SPDX-License-Identifier: Apache-2.0
"""Outer-deadline recovery for already committed SpatialTempo state."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
if ROOT.name == 'checks':
    ROOT = ROOT.parent


def load_entrypoint():
    name = '_titan_spatial_outer_recovery_test'
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, ROOT/'main.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Features:
    budget_seconds = 0.04
    reserve_seconds = 0.01
    consumer = 'frozen'


class _HangingInstance:
    town_procurement_enabled = False

    def __init__(self, action, recovery):
        self.features = _Features()
        self.action = deepcopy(action)
        self.recovery = deepcopy(recovery)
        self.selected = None
        self.diagnostics = {}
        self.ready = True
        self.exported = 0

    def _export_spatial_recovery(self):
        self.exported += 1
        return deepcopy(self.recovery)

    def act(self, _observation, _configuration=None, *, entry_started=None):
        self.selected = deepcopy(self.action)
        while True:
            pass


class _FreshInstance:
    town_procurement_enabled = False

    def __init__(self, action, expected):
        self.features = _Features()
        self.action = deepcopy(action)
        self.expected = deepcopy(expected)
        self.staged = 'not-called'
        self.selected = None
        self.diagnostics = {}
        self.ready = True

    def _stage_spatial_recovery(self, snapshot):
        self.staged = deepcopy(snapshot)
        return True

    def act(self, _observation, _configuration=None, *, entry_started=None):
        if self.staged != self.expected:
            raise AssertionError(('recovery was not staged before act', self.staged, self.expected))
        self.selected = deepcopy(self.action)
        self.diagnostics = {'status': 'completed'}
        return deepcopy(self.action)


class SpatialOuterRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))

    def setUp(self):
        self.main = load_entrypoint()
        self.main._INSTANCE = None
        self.main._SPATIAL_RECOVERY = None
        self.observation = {
            'step': 100,
            'player': 0,
            'farms': [{'hands': [[4, 4]]}, {'hands': []}],
            'private': {},
        }
        self.configuration = {'episodeSteps': 720}
        self.action = {
            'farmer': ['PASS'],
            'hands': [['PASS']],
            'market': [['SELL', 'CARROT', 1]],
        }
        self.recovery = {
            '_committed': {
                'plans': {1: {'kind': 'idle_fertilizer', 'end': 110}},
                'events': [{'kind': 'prior'}],
                'reserved': {(2, 3)},
                'active': {1: 110},
                'day': 4,
                'step': 99,
                'patches': {},
            },
            'sale_obligation': {
                'step': 99, 'player': 0, 'worker': 1,
                'quantity': 1, 'target': (2, 3), 'status': 'carried',
            },
            'receipt_events': [{'kind': 'prior_receipt', 'step': 99}],
            'crop_intent': {'kind': 'annual_crop_release', 'status': 'planted'},
        }

    @staticmethod
    def feature_data():
        return {
            'budget_seconds': 0.04,
            'reserve_seconds': 0.01,
            'town_procurement': False,
        }

    def test_export_restore_filters_current_call_transients(self):
        agent = self.main._new_instance(ROOT, {})
        agent.spatial = SimpleNamespace(
            **deepcopy(self.recovery),
            _pending={'unsafe': 'pending'},
            _selected={'unsafe': 'selected'},
            _sale_proposal={'unsafe': 'sale'},
            _crop_preparation={'unsafe': 'prepare'},
            _crop_repair={'unsafe': 'repair'},
            _crop_offered=True,
        )
        snapshot = agent._export_spatial_recovery()
        self.assertEqual(set(snapshot), set(self.main._SPATIAL_RECOVERY_FIELDS))
        self.assertEqual(snapshot, self.recovery)

        # The journal must be an isolated copy of already committed state.
        agent.spatial._committed['step'] = 777
        agent.spatial.receipt_events.append({'unsafe': 'later mutation'})
        self.assertEqual(snapshot['_committed']['step'], 99)
        self.assertEqual(snapshot['receipt_events'], self.recovery['receipt_events'])

        target = self.main._new_instance(ROOT, {})
        target.spatial = SimpleNamespace(
            _committed=None,
            sale_obligation=None,
            receipt_events=[],
            crop_intent=None,
            _pending={'keep': 'pending'},
            _selected={'keep': 'selected'},
            _sale_proposal={'keep': 'sale'},
            _crop_preparation={'keep': 'prepare'},
            _crop_repair={'keep': 'repair'},
            _crop_offered=True,
        )
        self.assertTrue(target._stage_spatial_recovery(snapshot))
        target._restore_spatial_recovery()
        for name, value in snapshot.items():
            self.assertEqual(getattr(target.spatial, name), value)
        self.assertEqual(target.spatial._pending, {'keep': 'pending'})
        self.assertEqual(target.spatial._selected, {'keep': 'selected'})
        self.assertEqual(target.spatial._sale_proposal, {'keep': 'sale'})
        self.assertEqual(target.spatial._crop_preparation, {'keep': 'prepare'})
        self.assertEqual(target.spatial._crop_repair, {'keep': 'repair'})
        self.assertTrue(target.spatial._crop_offered)

        malformed = dict(snapshot, _pending={'must': 'decline'})
        self.assertFalse(target._stage_spatial_recovery(malformed))
        self.assertIsNone(target._staged_spatial_recovery)

    def test_outer_timeout_hands_pre_call_journal_to_fresh_instance(self):
        old = _HangingInstance(self.action, self.recovery)
        old._entrypoint_last_step = 99
        self.main._INSTANCE = old
        started = time.perf_counter()
        output = self.main.agent(self.observation, self.configuration)
        elapsed = time.perf_counter() - started

        self.assertEqual(output, self.action)
        self.assertLess(elapsed, 0.5)
        self.assertEqual(old.exported, 1)
        self.assertIsNone(self.main._INSTANCE)
        self.assertEqual(
            self.main._SPATIAL_RECOVERY,
            {'last_step': 100, 'state': self.recovery},
        )

        # Mutating the discarded object cannot change the saved journal.
        old.recovery['_committed']['step'] = 888
        self.assertEqual(
            self.main._SPATIAL_RECOVERY['state']['_committed']['step'], 99)

        fresh = _FreshInstance(self.action, self.recovery)
        next_observation = dict(self.observation, step=101)
        with patch('json.loads', return_value=self.feature_data()), \
                patch.object(self.main, '_new_instance', return_value=fresh):
            output = self.main.agent(next_observation, self.configuration)

        self.assertEqual(output, self.action)
        self.assertEqual(fresh.staged, self.recovery)
        self.assertIs(self.main._INSTANCE, fresh)
        self.assertIsNone(self.main._SPATIAL_RECOVERY)

    def test_step_zero_clears_prior_match_journal(self):
        self.main._SPATIAL_RECOVERY = {
            'last_step': 99,
            'state': deepcopy(self.recovery),
        }
        fresh = _FreshInstance(self.action, None)
        observation = dict(self.observation, step=0)
        with patch('json.loads', return_value=self.feature_data()), \
                patch.object(self.main, '_new_instance', return_value=fresh):
            output = self.main.agent(observation, self.configuration)

        self.assertEqual(output, self.action)
        self.assertIsNone(fresh.staged)
        self.assertIsNone(self.main._SPATIAL_RECOVERY)

    def test_step_zero_retry_keeps_step_zero_journal(self):
        self.main._SPATIAL_RECOVERY = {
            'last_step': 0,
            'state': deepcopy(self.recovery),
        }
        fresh = _FreshInstance(self.action, self.recovery)
        observation = dict(self.observation, step=0)
        with patch('json.loads', return_value=self.feature_data()), \
                patch.object(self.main, '_new_instance', return_value=fresh):
            output = self.main.agent(observation, self.configuration)

        self.assertEqual(output, self.action)
        self.assertEqual(fresh.staged, self.recovery)
        self.assertIs(self.main._INSTANCE, fresh)
        self.assertIsNone(self.main._SPATIAL_RECOVERY)


if __name__ == '__main__':
    unittest.main(verbosity=2)
