# SPDX-License-Identifier: Apache-2.0
"""Current-vs-future seed causality contracts for early-capital ordering."""
import unittest

import mechanics as m
from early_capital import order_early_capital
from test_early_capital import CFG, obs, route


class EarlyCapitalTMinusOneTests(unittest.TestCase):
    def test_current_tick_plant_does_not_reserve_too_late_seed_order(self):
        selected = {'farmer': ['PLANT', 'MELON'], 'hands': [],
                    'market': [['BUY_SEED', 'MELON', 1], ['BUY_LAND']]}
        result, report = order_early_capital(
            m, obs(150, money=1500, unlocked=['NW'], seeds={}),
            CFG, selected, route())
        self.assertTrue(report['changed'])
        self.assertEqual(result['market'],
                         [['BUY_LAND'], ['BUY_SEED', 'MELON', 1]])
        self.assertEqual(result['farmer'], selected['farmer'])

    def test_next_tick_plant_still_reserves_seed_before_capital(self):
        selected = {'farmer': ['PASS'], 'hands': [],
                    'market': [['BUY_SEED', 'MELON', 1], ['BUY_LAND']]}
        future = route()
        future[151] = {'farmer': ['PLANT', 'MELON'],
                       'hands': [], 'market': []}
        result, report = order_early_capital(
            m, obs(150, money=1500, unlocked=['NW'], seeds={}),
            CFG, selected, future)
        self.assertFalse(report['changed'])
        self.assertEqual(report['reason'], 'already_ordered')
        self.assertEqual(result['market'], selected['market'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
