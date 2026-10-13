# SPDX-License-Identifier: Apache-2.0
"""No game panels: deterministic timing and invocation-boundary regressions."""
import unittest

from execution_timing import TimedFactory, TimingRecord, TimedAgent


def clock(*values):
    return iter(values).__next__


class ExecutionTimingTests(unittest.TestCase):
    def test_initialization_and_first_action_same_instance_not_maxima(self):
        factory = TimedFactory(lambda: lambda obs, cfg: obs, clock=clock(0, 3, 10, 12, 20, 27))
        actor = factory()
        self.assertEqual(actor(1, {}), 1)
        actor(2, {})
        row = actor.timings()
        self.assertEqual(row['initialization_s'], 3)
        self.assertEqual(row['first_action_s'], 2)
        self.assertEqual(row['initialization_plus_first_action_s'], 5)
        self.assertEqual(row['max_action_s'], 7)
        self.assertEqual(row['max_later_action_s'], 7)
        self.assertEqual(row['calls'], 2)
        self.assertEqual(row['failures'], 0)

    def test_factory_invoked_once(self):
        calls = []
        def build():
            calls.append('factory')
            return lambda obs, cfg: obs
        actor = TimedFactory(build)()
        actor({}, {})
        actor({}, {})
        self.assertEqual(calls, ['factory'])

    def test_optional_configuration_body_typeerror_not_retried(self):
        calls = []
        error = TypeError('inside producer')
        def policy(obs, cfg=None):
            calls.append(cfg)
            if cfg is not None:
                raise error
            return 'would mask error'
        actor = TimedFactory(lambda: policy)()
        with self.assertRaises(TypeError) as caught:
            actor({}, {'one': True})
        self.assertIs(caught.exception, error)
        self.assertEqual(calls, [{'one': True}])
        self.assertEqual(actor.timings()['failures'], 1)
        self.assertEqual(actor.timings()['calls'], 1)

    def test_action_identity_and_argument_identity_preserved(self):
        obs, cfg, action = {}, {}, {'market': [['SELL', 'WHEAT', 1]]}
        seen = []
        def policy(o, c):
            seen.append((o, c))
            return action
        actor = TimedFactory(lambda: policy)()
        self.assertIs(actor(obs, cfg), action)
        self.assertIs(seen[0][0], obs)
        self.assertIs(seen[0][1], cfg)

    def test_factory_arguments_forwarded_unchanged(self):
        arg, kw = object(), object()
        seen = []
        def factory(a, *, b):
            seen.append((a, b))
            return lambda obs: obs
        actor = TimedFactory(factory)(arg, b=kw)
        self.assertIs(seen[0][0], arg)
        self.assertIs(seen[0][1], kw)
        self.assertEqual(actor(4), 4)

    def test_keyword_and_one_argument_forwarding_no_arity_logic(self):
        def policy(obs, *, configuration):
            return obs, configuration
        actor = TimedFactory(lambda: policy)()
        self.assertEqual(actor(5, configuration=6), (5, 6))
        one = TimedFactory(lambda: lambda obs: obs + 1)()
        self.assertEqual(one(4), 5)

    def test_factory_failure_timing_survives(self):
        error = RuntimeError('construction')
        calls = []
        def factory():
            calls.append(1)
            raise error
        observer = TimedFactory(factory, clock=clock(2, 7))
        with self.assertRaises(RuntimeError) as caught:
            observer()
        self.assertIs(caught.exception, error)
        row = observer.timings()
        self.assertEqual(calls, [1])
        self.assertEqual(row['initialization_s'], 5)
        self.assertTrue(row['initialization_failed'])
        self.assertIsNone(row['initialization_plus_first_action_s'])
        self.assertEqual(row['calls'], 0)

    def test_failed_first_action_is_timed(self):
        def policy(obs):
            raise ValueError('action')
        observer = TimedFactory(lambda: policy, clock=clock(0, 2, 5, 8))
        actor = observer()
        with self.assertRaises(ValueError):
            actor({})
        row = actor.timings()
        self.assertEqual(row['initialization_plus_first_action_s'], 5)
        self.assertEqual(row['failures'], 1)
        self.assertEqual(row['first_action_s'], 3)

    def test_actor_records_independent_after_new_factory(self):
        observer = TimedFactory(lambda: lambda x: x, clock=clock(0, 2, 4, 7, 10, 14, 20, 25))
        first = observer()
        second = observer()
        first(1)
        second(2)
        self.assertEqual(first.timings()['initialization_plus_first_action_s'], 6)
        self.assertEqual(second.timings()['initialization_plus_first_action_s'], 8)
        self.assertIsNot(first.record, second.record)
        self.assertIs(observer.last_record, second.record)

    def test_snapshot_is_detached(self):
        observer = TimedFactory(lambda: lambda x: x)
        actor = observer()
        snapshot = actor.timings()
        snapshot['calls'] = 999
        self.assertEqual(actor.timings()['calls'], 0)
        self.assertIsNone(actor.timings()['first_action_s'])
        self.assertIsNone(actor.timings()['max_action_s'])

    def test_no_factory_attempt_has_no_timing_record(self):
        observer = TimedFactory(lambda: lambda x: x)
        self.assertIsNone(observer.timings())

    def test_later_failure_does_not_replace_first_action(self):
        def policy(x):
            if x:
                raise RuntimeError('later')
            return x
        actor = TimedFactory(lambda: policy, clock=clock(0, 1, 2, 5, 10, 18))()
        actor(False)
        with self.assertRaises(RuntimeError):
            actor(True)
        row = actor.timings()
        self.assertEqual(row['first_action_s'], 3)
        self.assertEqual(row['max_later_action_s'], 8)
        self.assertEqual(row['initialization_plus_first_action_s'], 4)
        self.assertEqual(row['failures'], 1)

    def test_generator_of_actions_is_not_executed_eagerly(self):
        seen = []
        def policy(obs):
            seen.append(obs)
            yield obs
        actor = TimedFactory(lambda: policy)()
        result = actor(2)
        self.assertEqual(seen, [])
        self.assertEqual(list(result), [2])
        # Timing is the call, not deferred generator execution; no false scope.
        self.assertEqual(actor.timings()['calls'], 1)

    def test_bound_callable_object_state_is_retained(self):
        class Policy:
            def __init__(self):
                self.n = 0
            def __call__(self, obs, cfg):
                self.n += 1
                return self.n
        actor = TimedFactory(Policy)()
        self.assertEqual([actor({}, {}) for _ in range(3)], [1, 2, 3])

    def test_baseexception_propagates_and_is_measured(self):
        error = KeyboardInterrupt('interrupt')
        def policy(obs):
            raise error
        actor = TimedFactory(lambda: policy)()
        with self.assertRaises(KeyboardInterrupt) as caught:
            actor({})
        self.assertIs(caught.exception, error)
        self.assertEqual(actor.timings()['failures'], 1)

    def test_bare_bound_actor_has_no_invented_initialization(self):
        actor = TimedAgent(lambda x: x, TimingRecord())
        actor({})
        self.assertIsNone(actor.timings()['initialization_s'])
        self.assertIsNone(actor.timings()['initialization_plus_first_action_s'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
