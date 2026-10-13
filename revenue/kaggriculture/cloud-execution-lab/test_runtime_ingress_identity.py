# SPDX-License-Identifier: Apache-2.0
"""Regression coverage for exact public identity at TitanAgent.act ingress."""
from copy import deepcopy
import unittest
from unittest.mock import patch

import titan_runtime as runtime


PASS_ACTION = {'farmer': ['PASS'], 'hands': [], 'market': []}


def observation(**updates):
    value = {
        'player': 0,
        'step': 3,
        'farms': [{'tiles': []}, {'tiles': []}],
        'private': {},
    }
    value.update(updates)
    return value


class RuntimeIngressIdentityTest(unittest.TestCase):
    def _seed_agent_state(self):
        agent = runtime.TitanAgent()
        agent.selected = {'sentinel': ['selected']}
        agent.post = {'sentinel': ['post']}
        agent.diagnostics = {'sentinel': 'diagnostics'}
        agent._completed_route = 'route-sentinel'
        agent._completed_seller_state = {'sentinel': ['seller-state']}
        agent._seller_fallback_observations = [
            {
                'step': 2,
                'player': 0,
                'farms': [{'tiles': []}, {'tiles': []}],
            }
        ]
        return agent

    def _assert_rejected_atomically(self, obs, cfg=None):
        agent = self._seed_agent_state()
        before = deepcopy(agent.__dict__)
        with patch.object(runtime.deadline, 'legal_pass',
                          side_effect=AssertionError('fallback reached')) as legal, \
             patch.object(runtime.deadline, 'terminal_liquidation_fallback',
                          side_effect=AssertionError('terminal fallback reached')) as terminal:
            with self.assertRaises(ValueError):
                agent.act(obs, cfg or {})
        self.assertEqual(agent.__dict__, before)
        legal.assert_not_called()
        terminal.assert_not_called()

    def test_player_aliases_fail_before_any_runtime_mutation(self):
        for value in (None, True, 0.0, '0', -1, 2):
            with self.subTest(player=value):
                self._assert_rejected_atomically(observation(player=value))

    def test_present_step_aliases_fail_instead_of_coercing_or_falling_back(self):
        bad = (None, True, 0.0, '3', -1)
        for value in bad:
            with self.subTest(step=value):
                obs = observation(step=value, day=0, hour=3)
                self._assert_rejected_atomically(obs, {'turnsPerDay': 24})

    def test_missing_step_requires_exact_paired_day_hour(self):
        cases = [
            ({'day': 0}, {}),
            ({'hour': 3}, {}),
            ({'day': None, 'hour': 3}, {}),
            ({'day': True, 'hour': 3}, {}),
            ({'day': 0.0, 'hour': 3}, {}),
            ({'day': '0', 'hour': 3}, {}),
            ({'day': -1, 'hour': 3}, {}),
            ({'day': 0, 'hour': None}, {}),
            ({'day': 0, 'hour': True}, {}),
            ({'day': 0, 'hour': 3.0}, {}),
            ({'day': 0, 'hour': '3'}, {}),
            ({'day': 0, 'hour': -1}, {}),
            ({'day': 0, 'hour': 24}, {}),
        ]
        for patch_values, cfg in cases:
            with self.subTest(values=patch_values, cfg=cfg):
                obs = observation()
                del obs['step']
                obs.update(patch_values)
                self._assert_rejected_atomically(obs, cfg)

    def test_fallback_turns_per_day_is_plain_positive_int(self):
        for value in (None, True, 0, -1, 24.0, '24'):
            with self.subTest(turnsPerDay=value):
                obs = observation(day=0, hour=3)
                del obs['step']
                self._assert_rejected_atomically(obs, {'turnsPerDay': value})

    def test_redundant_clocks_must_be_paired_exact_and_consistent(self):
        cases = [
            observation(step=3, day=0),
            observation(step=3, hour=3),
            observation(step=3, day=None, hour=3),
            observation(step=3, day=0, hour=None),
            observation(step=3, day=0, hour=4),
            observation(step=3, day=True, hour=3),
            observation(step=3, day=0, hour='3'),
        ]
        for obs in cases:
            with self.subTest(obs=obs):
                self._assert_rejected_atomically(obs, {'turnsPerDay': 24})

    def _assert_valid_prelude_fallback(self, obs, cfg, expected_step):
        original = deepcopy(obs)
        agent = runtime.TitanAgent()
        with patch.object(runtime.deadline, 'legal_pass',
                          return_value=deepcopy(PASS_ACTION)) as legal, \
             patch.object(runtime.deadline, 'terminal_liquidation_fallback',
                          side_effect=AssertionError('unexpected terminal fallback')) as terminal:
            result = agent.act(obs, cfg, entry_started=0.0)
        self.assertEqual(result, PASS_ACTION)
        self.assertEqual(obs, original)
        self.assertEqual(agent._seller_fallback_observations[-1]['step'], expected_step)
        self.assertEqual(agent._seller_fallback_observations[-1]['player'], 0)
        legal.assert_called_once()
        terminal.assert_not_called()

    def test_canonical_step_only_stays_valid(self):
        obs = observation(step=5)
        self._assert_valid_prelude_fallback(obs, {}, 5)

    def test_exact_day_hour_fallback_stays_valid(self):
        obs = observation(day=1, hour=2)
        del obs['step']
        self._assert_valid_prelude_fallback(obs, {'turnsPerDay': 24}, 26)

    def test_agreeing_redundant_clock_stays_valid(self):
        obs = observation(step=25, day=1, hour=1)
        self._assert_valid_prelude_fallback(obs, {'turnsPerDay': 24}, 25)


if __name__ == '__main__':
    unittest.main()
