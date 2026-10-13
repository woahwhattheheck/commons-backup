# SPDX-License-Identifier: Apache-2.0
"""Recovery contracts for the run-only public-regime scheduler wrapper."""
import unittest

import regime_scheduler as target


class _FakeScheduler:
    made = []

    def __init__(self, mode='candidate'):
        self.mode = mode
        self.calls = []
        type(self).made.append(self)

    def act(self, obs, configuration=None):
        self.calls.append((int(obs['step']), dict(configuration or {})))
        return {'step': int(obs['step']), 'call': len(self.calls)}


class RegimeSchedulerReplayTests(unittest.TestCase):
    def setUp(self):
        self.original_scheduler = target.RegimeSellScheduler
        self.original_instance = target._INSTANCE
        self.original_last_step = target._LAST_STEP
        target.RegimeSellScheduler = _FakeScheduler
        target._INSTANCE = None
        target._LAST_STEP = None
        _FakeScheduler.made = []

    def tearDown(self):
        target.RegimeSellScheduler = self.original_scheduler
        target._INSTANCE = self.original_instance
        target._LAST_STEP = self.original_last_step

    def test_exact_step_zero_replay_reuses_completed_wrapper(self):
        first = target.agent({'step': 0}, {'tag': 'first'})
        instance = target._INSTANCE
        second = target.agent({'step': 0}, {'tag': 'retry'})

        self.assertIs(target._INSTANCE, instance)
        self.assertEqual(len(_FakeScheduler.made), 1)
        self.assertEqual(instance.calls,
                         [(0, {'tag': 'first'}), (0, {'tag': 'retry'})])
        self.assertEqual(first, {'step': 0, 'call': 1})
        self.assertEqual(second, {'step': 0, 'call': 2})
        self.assertEqual(target._LAST_STEP, 0)

    def test_genuine_backward_transition_reconstructs_wrapper(self):
        target.agent({'step': 0})
        first = target._INSTANCE
        target.agent({'step': 3})
        self.assertIs(target._INSTANCE, first)

        result = target.agent({'step': 0}, {'match': 'new'})
        second = target._INSTANCE

        self.assertIsNot(second, first)
        self.assertEqual(len(_FakeScheduler.made), 2)
        self.assertEqual(first.calls, [(0, {}), (3, {})])
        self.assertEqual(second.calls, [(0, {'match': 'new'})])
        self.assertEqual(result, {'step': 0, 'call': 1})
        self.assertEqual(target._LAST_STEP, 0)

    def test_same_nonzero_step_keeps_incumbent_behavior(self):
        target.agent({'step': 0})
        instance = target._INSTANCE
        target.agent({'step': 7})
        target.agent({'step': 7})

        self.assertIs(target._INSTANCE, instance)
        self.assertEqual(len(_FakeScheduler.made), 1)
        self.assertEqual(instance.calls, [(0, {}), (7, {}), (7, {})])
        self.assertEqual(target._LAST_STEP, 7)


if __name__ == '__main__':
    unittest.main(verbosity=2)
