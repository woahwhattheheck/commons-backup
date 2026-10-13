# SPDX-License-Identifier: Apache-2.0
"""Completion checks for the existing cooperative physical-replay budget.

Only the clock/dependency boundaries are controlled; no real waiting is needed.
Run beside physical_replay.py with python -m unittest -v test_completion_deadline.
"""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import physical_replay as replay


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class Controller:
    def __init__(self):
        self.cur = 'first'
        self.R = {'first': [{}], 'second': [{}]}
        self.calls = 0

    def _switch_ok(self, route, step):
        return True

    def act(self, view):
        self.calls += 1
        return {'farmer': ['PASS'], 'market': [['SELL', 'WHEAT', 1]]}


class Engine:
    def _process_market(self, state, env):
        state[0].observation.farms[0]['money'] += 5


class CompletionDeadline(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.controller = Controller()
        self.observation = {'step': 0, 'player': 0, 'farms': [{'money': 10}]}
        self.before_controller = deepcopy(self.controller.__dict__)
        self.before_observation = deepcopy(self.observation)
        self.simulator_calls = 0
        self.patcher = patch.object(replay, 'monotonic', self.clock)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def simulate(self, engine, observation, configuration, plan, **kwargs):
        self.simulator_calls += 1
        action = plan(observation)
        view = SimpleNamespace(step=0, farms=[{'money': 10}], private={}, market={})
        engine._process_market([SimpleNamespace(observation=view, action=action)], None)
        return {'cash_gain': 5, 'farm': {'money': 15}, 'actions': {0: action}}

    def run_replay(self, simulate=None, routes=('first',), scenarios=None, seconds=1, decisions=5):
        return replay.replay_routes(
            self.controller, routes, self.observation, {'episodeSteps': 2},
            Engine(), simulate or self.simulate,
            scenarios={'known': {}} if scenarios is None else scenarios,
            end_step=0, limits=replay.ReplayLimits(seconds=seconds, decisions=decisions))

    def assert_unscored(self, case, reason='budget:time'):
        self.assertEqual(case['status'], 'incomplete')
        self.assertEqual(case['reason'], reason)
        self.assertIsNone(case['cash_gain'])
        for name in ('final_cash', 'minimum_after_market_cash', 'action_sha256', 'active_routes', 'result'):
            self.assertNotIn(name, case)

    def assert_originals(self):
        self.assertEqual(self.controller.__dict__, self.before_controller)
        self.assertEqual(self.observation, self.before_observation)

    def test_successful_case_preserves_full_output_and_originals(self):
        result = self.run_replay()
        self.assertTrue(result['complete'])
        case = result['cases'][0]
        self.assertEqual(case['status'], 'complete')
        self.assertEqual(case['cash_gain'], 5)
        self.assertEqual(case['final_cash'], 15)
        self.assertEqual(case['minimum_after_market_cash'], 10)
        self.assertEqual(case['result']['actions'][0]['market'], [['SELL', 'WHEAT', 1]])
        self.assertEqual(len(case['market_rows']), 1)
        self.assertEqual(case['market_rows'][0]['cash_delta'], 5)
        self.assertEqual(result['decisions_executed'], 1)
        self.assert_originals()

    def test_dependency_return_at_or_after_deadline_is_not_scored(self):
        for finish in (1.0, 2.0):
            with self.subTest(finish=finish):
                self.clock.now = 0
                def late(*args, **kwargs):
                    result = self.simulate(*args, **kwargs)
                    self.clock.now = finish
                    return result
                result = self.run_replay(late)
                self.assertFalse(result['complete'])
                self.assert_unscored(result['cases'][0])
                self.assertEqual(result['cases'][0]['market_rows'][0]['cash_delta'], 5)
                self.assert_originals()

    def test_dependency_return_just_before_deadline_is_complete(self):
        def on_time(*args, **kwargs):
            result = self.simulate(*args, **kwargs)
            self.clock.now = 0.999
            return result
        self.assertTrue(self.run_replay(on_time)['complete'])

    def test_action_digest_overrun_cannot_leak_completed_fields(self):
        original_digest = replay._digest
        def digest(value):
            result = original_digest(value)
            if isinstance(value, dict) and 0 in value:
                self.clock.now = 1.0
            return result
        with patch.object(replay, '_digest', digest):
            result = self.run_replay()
        self.assertFalse(result['complete'])
        self.assert_unscored(result['cases'][0])
        self.assertEqual(len(result['cases'][0]['market_rows']), 1)

    def test_overdue_return_stops_before_result_digest(self):
        original_digest = replay._digest
        action_digests = []
        def digest(value):
            if isinstance(value, dict) and 0 in value:
                action_digests.append(value)
            return original_digest(value)
        def late(*args, **kwargs):
            result = self.simulate(*args, **kwargs)
            self.clock.now = 2
            return result
        with patch.object(replay, '_digest', digest):
            result = self.run_replay(late)
        self.assert_unscored(result['cases'][0])
        self.assertEqual(action_digests, [])

    def test_shared_grid_retains_earlier_complete_case_and_every_remaining_id(self):
        def late_second(*args, **kwargs):
            result = self.simulate(*args, **kwargs)
            if self.simulator_calls == 2:
                self.clock.now = 1
            return result
        result = self.run_replay(late_second, routes=('first', 'second'), scenarios={'a': {}, 'b': {}})
        self.assertFalse(result['complete'])
        self.assertEqual([(c['offered_route'], c['scenario_id']) for c in result['cases']],
                         [('first', 'a'), ('first', 'b'), ('second', 'a'), ('second', 'b')])
        self.assertEqual(result['cases'][0]['status'], 'complete')
        for case in result['cases'][1:]:
            self.assert_unscored(case)
        self.assertEqual(len(result['cases'][1]['market_rows']), 1)
        self.assertEqual(result['cases'][2]['market_rows'], [])
        self.assertEqual(self.simulator_calls, 2)
        self.assertEqual(result['decisions_executed'], 2)

    def test_zero_budget_never_calls_simulator_or_controller(self):
        result = self.run_replay(seconds=0)
        self.assert_unscored(result['cases'][0])
        self.assertEqual(self.simulator_calls, 0)
        self.assert_originals()

    def test_decision_budget_and_partial_market_rows_remain_intact(self):
        def twice(engine, observation, configuration, plan, **kwargs):
            result = self.simulate(engine, observation, configuration, plan, **kwargs)
            plan(observation)
            return result
        result = self.run_replay(twice, decisions=1)
        self.assert_unscored(result['cases'][0], 'budget:decisions')
        self.assertEqual(result['decisions_executed'], 1)
        self.assertEqual(len(result['cases'][0]['market_rows']), 1)

    def test_cancellation_still_propagates(self):
        def cancel(*args, **kwargs):
            raise KeyboardInterrupt('external cancellation')
        with self.assertRaisesRegex(KeyboardInterrupt, 'external cancellation'):
            self.run_replay(cancel)

    def test_ordinary_dependency_errors_remain_incomplete(self):
        def fail(*args, **kwargs):
            raise ValueError('dependency fixture')
        result = self.run_replay(fail)
        self.assert_unscored(result['cases'][0], 'ValueError: dependency fixture')

    def test_cash_binding_error_is_preserved(self):
        def inconsistent(*args, **kwargs):
            result = self.simulate(*args, **kwargs)
            result['cash_gain'] = 6
            return result
        result = self.run_replay(inconsistent)
        self.assert_unscored(result['cases'][0], 'ValueError: Observer cash does not match delegated result')


if __name__ == '__main__':
    unittest.main()
