# SPDX-License-Identifier: Apache-2.0
"""Retry/reset contracts for the standalone SELL scheduler entrypoints."""
import unittest

import scheduler


class FakeScheduler:
    created = []
    fail_next = False

    def __init__(self, mode='candidate'):
        self.mode = mode
        self.serial = len(type(self).created) + 1
        type(self).created.append(self)

    def act(self, obs, configuration=None):
        if type(self).fail_next:
            type(self).fail_next = False
            raise RuntimeError('injected scheduler failure')
        return {
            'serial': self.serial,
            'mode': self.mode,
            'step': int(obs.get('step', 0)),
        }


class SchedulerStepZeroReplayTests(unittest.TestCase):
    def setUp(self):
        self.original = scheduler.SellScheduler
        scheduler.SellScheduler = FakeScheduler
        self.reset()

    def tearDown(self):
        scheduler.SellScheduler = self.original
        self.reset()

    @staticmethod
    def reset():
        FakeScheduler.created = []
        FakeScheduler.fail_next = False
        scheduler._INSTANCE = None
        scheduler._LAST_STEP = None
        scheduler._NAIVE = None
        scheduler._NAIVE_LAST_STEP = None

    def exercise_replay_and_rewind(self, fn, instance_name, last_name, mode):
        first = fn({'step': 0})
        retry_zero = fn({'step': 0})
        forward = fn({'step': 7})
        retry_forward = fn({'step': 7})
        self.assertEqual(first['serial'], retry_zero['serial'])
        self.assertEqual(first['serial'], forward['serial'])
        self.assertEqual(first['serial'], retry_forward['serial'])
        self.assertEqual(first['mode'], mode)
        self.assertEqual(len(FakeScheduler.created), 1)
        self.assertEqual(getattr(scheduler, last_name), 7)

        rewind = fn({'step': 2})
        self.assertNotEqual(first['serial'], rewind['serial'])
        self.assertEqual(rewind['mode'], mode)
        self.assertEqual(len(FakeScheduler.created), 2)
        self.assertEqual(getattr(scheduler, last_name), 2)
        self.assertIs(getattr(scheduler, instance_name), FakeScheduler.created[-1])

    def test_candidate_and_naive_reuse_same_step_and_reset_on_rewind(self):
        for fn, instance_name, last_name, mode in (
            (scheduler.agent, '_INSTANCE', '_LAST_STEP', 'candidate'),
            (scheduler.naive_agent, '_NAIVE', '_NAIVE_LAST_STEP', 'naive'),
        ):
            with self.subTest(mode=mode):
                self.reset()
                self.exercise_replay_and_rewind(fn, instance_name, last_name, mode)

    def exercise_failed_rewind(self, fn, instance_name, last_name, mode):
        original = fn({'step': 9})
        self.assertEqual(getattr(scheduler, last_name), 9)
        FakeScheduler.fail_next = True
        with self.assertRaisesRegex(RuntimeError, 'injected scheduler failure'):
            fn({'step': 0})
        failed = FakeScheduler.created[-1]
        self.assertEqual(getattr(scheduler, last_name), 9)
        self.assertIs(getattr(scheduler, instance_name), failed)

        retry = fn({'step': 0})
        self.assertNotEqual(retry['serial'], failed.serial)
        self.assertNotEqual(retry['serial'], original['serial'])
        self.assertEqual(retry['mode'], mode)
        self.assertEqual(getattr(scheduler, last_name), 0)
        self.assertIs(getattr(scheduler, instance_name), FakeScheduler.created[-1])

    def test_failed_rewind_does_not_consume_reset_boundary(self):
        for fn, instance_name, last_name, mode in (
            (scheduler.agent, '_INSTANCE', '_LAST_STEP', 'candidate'),
            (scheduler.naive_agent, '_NAIVE', '_NAIVE_LAST_STEP', 'naive'),
        ):
            with self.subTest(mode=mode):
                self.reset()
                self.exercise_failed_rewind(fn, instance_name, last_name, mode)


if __name__ == '__main__':
    unittest.main(verbosity=2)
