# SPDX-License-Identifier: Apache-2.0
"""Focused fail-closed configuration-custody regressions for B5."""
from __future__ import annotations

from copy import deepcopy
import unittest

from discarded_fertilizer_tomato import apply_discarded_fertilizer


REQUIRED = {
    'boardSize': 10,
    'turnsPerDay': 24,
    'episodeSteps': 720,
    'shedCapacity': 100,
    'maxMarketOrdersPerTurn': 10,
}


def packet():
    tiles = [[None for _ in range(10)] for _ in range(10)]
    tiles[0][0] = {
        'kind': 'PLANT',
        'crop': 'TOMATO',
        'planted_day': 10,
        'yield_units': 0,
        'fertilized_until_day': -1,
        'consecutive_unwatered': 0,
        'max_lifespan_step': -1,
        'watered_today': True,
    }
    rival_tiles = [[None for _ in range(10)] for _ in range(10)]
    farms = [
        {'farmer': [0, 0], 'hands': [], 'tiles': tiles},
        {'farmer': [0, 0], 'hands': [], 'tiles': rival_tiles},
    ]
    observation = {
        'step': 17 * 24 + 23,
        'player': 0,
        'farms': farms,
        'private': {
            'shed': {'WHEAT': 100},
            'inventories': [{'FERTILIZER': 1}],
        },
    }
    action = {'farmer': ['PASS'], 'hands': [], 'market': []}
    return observation, action


class B5ConfigurationCustody(unittest.TestCase):
    def test_none_and_each_missing_required_field_fail_closed_by_identity(self):
        configurations = [('none', None)]
        for missing in REQUIRED:
            cfg = dict(REQUIRED)
            del cfg[missing]
            configurations.append((missing, cfg))
        for label, cfg in configurations:
            with self.subTest(missing=label):
                observation, action = packet()
                before = deepcopy(action)
                out, report = apply_discarded_fertilizer(
                    observation, action, cfg, enabled=True)
                self.assertIs(out, action)
                self.assertEqual(action, before)
                self.assertFalse(report['changed'])
                self.assertEqual(report['reason'], 'unsupported_configuration')

    def test_complete_observed_standard_configuration_keeps_positive_path(self):
        observation, action = packet()
        out, report = apply_discarded_fertilizer(
            observation, action, dict(REQUIRED), enabled=True)
        self.assertIsNot(out, action)
        self.assertEqual(action['farmer'], ['PASS'])
        self.assertEqual(out['farmer'], ['FERTILIZE'])
        self.assertTrue(report['changed'])
        self.assertEqual(report['effective_market_cap'], 10)

    def test_observed_nonstandard_integer_cap_keeps_official_minimum_one_semantics(self):
        for cap in (-5, 0, 1, 2, 10):
            with self.subTest(cap=cap):
                observation, action = packet()
                cfg = dict(REQUIRED, maxMarketOrdersPerTurn=cap)
                out, report = apply_discarded_fertilizer(
                    observation, action, cfg, enabled=True)
                self.assertIsNot(out, action)
                self.assertTrue(report['changed'])
                self.assertEqual(report['effective_market_cap'], max(1, cap))

    def test_type_poison_required_fields_fail_closed(self):
        for key in REQUIRED:
            cfg = dict(REQUIRED)
            cfg[key] = True
            observation, action = packet()
            out, report = apply_discarded_fertilizer(
                observation, action, cfg, enabled=True)
            self.assertIs(out, action)
            self.assertFalse(report['changed'])
            expected = ('unsupported_market_cap'
                        if key == 'maxMarketOrdersPerTurn'
                        else 'unsupported_configuration')
            self.assertEqual(report['reason'], expected)


if __name__ == '__main__':
    unittest.main()
