# SPDX-License-Identifier: Apache-2.0
"""Exact step-zero replay semantics for the canonical TITAN entrypoint."""
from copy import deepcopy
import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
if ROOT.name == 'checks':
    ROOT = ROOT.parent


def load_entrypoint():
    name = '_titan_entrypoint_step0_replay_test'
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, ROOT/'main.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _DeadlineExceeded(Exception):
    pass


class _Timer:
    def __init__(self, _seconds):
        self.expired = _DeadlineExceeded('timer expired')

    def __enter__(self):
        return self

    def __exit__(self, _kind, _value, _traceback):
        return False


class _FakeInstance:
    town_procurement_enabled = False

    def __init__(self, action):
        self.features = SimpleNamespace(
            budget_seconds=1.0,
            reserve_seconds=0.01,
            consumer='frozen',
        )
        self.action = deepcopy(action)
        self.selected = None
        self.post = None
        self.ready = True
        self.diagnostics = {}
        self.calls = 0
        self.fallback_observations = []

    def _remember_seller_fallback(self, observation):
        self.fallback_observations.append(deepcopy(observation))

    def act(self, _observation, _configuration=None, *, entry_started=None):
        self.calls += 1
        self.selected = deepcopy(self.action)
        return deepcopy(self.action)


def fake_runtime():
    runtime = ModuleType('titan_runtime')
    runtime.deadline = SimpleNamespace(
        DeadlineExceeded=_DeadlineExceeded,
        _DeadlineTimer=_Timer,
        legal_pass=lambda obs: {
            'farmer': ['PASS'],
            'hands': [['PASS'] for _ in obs.get('farms', [{}])[int(obs['player'])].get('hands', [])],
            'market': [],
        },
        terminal_liquidation_fallback=lambda obs, cfg: {
            'farmer': ['PASS'],
            'hands': [['PASS'] for _ in obs.get('farms', [{}])[int(obs['player'])].get('hands', [])],
            'market': [],
        },
    )
    return runtime


class EntrypointStepZeroReplayTests(unittest.TestCase):
    def setUp(self):
        self.main = load_entrypoint()
        self.main._INSTANCE = None
        self.runtime = fake_runtime()
        self.observation = {
            'step': 0,
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
        self.feature_data = {
            'consumer': 'frozen',
            'budget_seconds': 1.0,
            'reserve_seconds': 0.01,
        }

    def test_exact_step_zero_retry_reuses_completed_instance(self):
        instance = _FakeInstance(self.action)
        with patch.dict(sys.modules, {'titan_runtime': self.runtime}), \
                patch('json.loads', return_value=dict(self.feature_data)), \
                patch.object(self.main, '_new_instance', return_value=instance) as constructor:
            first = self.main.agent(self.observation, self.configuration)
            second = self.main.agent(self.observation, self.configuration)

        self.assertEqual(first, self.action)
        self.assertEqual(second, self.action)
        constructor.assert_called_once()
        self.assertEqual(instance.calls, 2)
        self.assertIs(self.main._INSTANCE, instance)
        self.assertEqual(instance._entrypoint_last_step, 0)

    def test_later_step_to_zero_reconstructs_for_new_match(self):
        old = _FakeInstance(self.action)
        self.main._INSTANCE = old
        later = deepcopy(self.observation)
        later['step'] = 17
        fresh = _FakeInstance(self.action)

        with patch.dict(sys.modules, {'titan_runtime': self.runtime}), \
                patch('json.loads', return_value=dict(self.feature_data)), \
                patch.object(self.main, '_new_instance', return_value=fresh) as constructor:
            prior = self.main.agent(later, self.configuration)
            reset = self.main.agent(self.observation, self.configuration)

        self.assertEqual(prior, self.action)
        self.assertEqual(reset, self.action)
        constructor.assert_called_once()
        self.assertEqual(old.calls, 1)
        self.assertEqual(old._entrypoint_last_step, 17)
        self.assertEqual(fresh.calls, 1)
        self.assertEqual(fresh._entrypoint_last_step, 0)
        self.assertIs(self.main._INSTANCE, fresh)


if __name__ == '__main__':
    unittest.main(verbosity=2)
