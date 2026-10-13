# SPDX-License-Identifier: Apache-2.0
"""Regression coverage for same-step replay in thin integrated entrypoints."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent


class _FakeAgent:
    def __init__(self, identity, failures):
        self.identity = identity
        self.failures = failures
        self.calls = []

    def act(self, observation, configuration=None):
        step = observation.get('step')
        if step is None:
            step = (int(observation['day'])
                    * int((configuration or {}).get('turnsPerDay', 24))
                    + int(observation['hour']))
        step = int(step)
        self.calls.append(step)
        if step in self.failures:
            self.failures.remove(step)
            raise RuntimeError('synthetic act failure')
        return {'instance': self.identity, 'step': step}


def _load(filename):
    name = '_test_' + filename.replace('.', '_')
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class IntegratedWrapperReplayTest(unittest.TestCase):
    def _exercise(self, filename):
        module = _load(filename)
        created = []
        failures = set()

        def make_agent():
            instance = _FakeAgent(len(created) + 1, failures)
            created.append(instance)
            return instance

        module.make_agent = make_agent

        self.assertEqual(module.agent({'step': 0}), {'instance': 1, 'step': 0})
        self.assertEqual(module.agent({'step': 0}), {'instance': 1, 'step': 0})
        self.assertEqual(len(created), 1)

        self.assertEqual(module.agent({'step': 2}), {'instance': 1, 'step': 2})
        self.assertEqual(module.agent({'step': 2}), {'instance': 1, 'step': 2})
        self.assertEqual(len(created), 1)

        # A strict public-step rewind is a new/reordered stream boundary.
        self.assertEqual(module.agent({'step': 1}), {'instance': 2, 'step': 1})
        self.assertEqual(len(created), 2)
        self.assertEqual(
            module.agent({'day': 0, 'hour': 1}, {'turnsPerDay': 24}),
            {'instance': 2, 'step': 1},
        )
        self.assertEqual(len(created), 2)

        # The rewind marker is published only after a complete return. A failed
        # rebuilt instance must not become reusable on the next same-step retry.
        failures.add(0)
        with self.assertRaisesRegex(RuntimeError, 'synthetic act failure'):
            module.agent({'step': 0})
        self.assertEqual(module._LAST_STEP, 1)
        self.assertEqual(len(created), 3)
        self.assertEqual(module.agent({'step': 0}), {'instance': 4, 'step': 0})
        self.assertEqual(len(created), 4)

    def _exercise_cold_start_failure(self, filename):
        module = _load(filename)
        created = []
        failures = {0}

        def make_agent():
            instance = _FakeAgent(len(created) + 1, failures)
            created.append(instance)
            return instance

        module.make_agent = make_agent

        with self.assertRaisesRegex(RuntimeError, 'synthetic act failure'):
            module.agent({'step': 0})
        self.assertIsNone(module._INSTANCE)
        self.assertIsNone(module._LAST_STEP)
        self.assertEqual(len(created), 1)

        self.assertEqual(module.agent({'step': 0}), {'instance': 2, 'step': 0})
        self.assertIs(module._INSTANCE, created[1])
        self.assertEqual(module._LAST_STEP, 0)
        self.assertEqual(len(created), 2)

    def _exercise_public_clock_exactness(self, filename):
        module = _load(filename)
        created = []
        failures = set()

        def make_agent():
            instance = _FakeAgent(len(created) + 1, failures)
            created.append(instance)
            return instance

        module.make_agent = make_agent
        cfg = {'turnsPerDay': 24}

        # Redundant canonical fields agree and publish one committed wrapper.
        self.assertEqual(
            module.agent({'step': 25, 'day': 1, 'hour': 1}, cfg),
            {'instance': 1, 'step': 25},
        )
        committed = module._INSTANCE
        self.assertEqual(module._LAST_STEP, 25)
        self.assertEqual(len(committed.calls), 1)

        rejected = [
            ({}, cfg),
            ({'step': None}, cfg),
            ({'step': True}, cfg),
            ({'step': '25'}, cfg),
            ({'step': 25.0}, cfg),
            ({'step': -1}, cfg),
            ({'day': 1}, cfg),
            ({'hour': 1}, cfg),
            ({'day': True, 'hour': 1}, cfg),
            ({'day': 1, 'hour': '1'}, cfg),
            ({'day': -1, 'hour': 1}, cfg),
            ({'day': 1, 'hour': -1}, cfg),
            ({'day': 1, 'hour': 24}, cfg),
            ({'day': 1, 'hour': 1}, {'turnsPerDay': True}),
            ({'day': 1, 'hour': 1}, {'turnsPerDay': '24'}),
            ({'day': 1, 'hour': 1}, {'turnsPerDay': 0}),
            ({'step': 25, 'day': 1, 'hour': 2}, cfg),
            ({'step': 25, 'day': 1}, cfg),
        ]
        for obs, bad_cfg in rejected:
            with self.subTest(filename=filename, obs=obs, cfg=bad_cfg):
                with self.assertRaises((TypeError, ValueError)):
                    module.agent(obs, bad_cfg)
                self.assertIs(module._INSTANCE, committed)
                self.assertEqual(module._LAST_STEP, 25)
                self.assertEqual(len(created), 1)
                self.assertEqual(len(committed.calls), 1)

        # The historical day/hour fallback remains exact and uses the same live
        # wrapper when the derived step moves forward.
        self.assertEqual(
            module.agent({'day': 1, 'hour': 2}, cfg),
            {'instance': 1, 'step': 26},
        )
        self.assertIs(module._INSTANCE, committed)
        self.assertEqual(module._LAST_STEP, 26)

    def test_integrated_main_replay_and_reset(self):
        self._exercise('integrated_main.py')

    def test_integrated_parent_replay_and_reset(self):
        self._exercise('integrated_parent.py')

    def test_cold_start_failure_does_not_publish_partial_instance(self):
        for filename in ('integrated_main.py', 'integrated_parent.py'):
            with self.subTest(filename=filename):
                self._exercise_cold_start_failure(filename)

    def test_public_clock_is_exact_before_wrapper_state_changes(self):
        for filename in ('integrated_main.py', 'integrated_parent.py'):
            with self.subTest(filename=filename):
                self._exercise_public_clock_exactness(filename)


if __name__ == '__main__':
    unittest.main()
