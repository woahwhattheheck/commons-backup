# SPDX-License-Identifier: Apache-2.0
"""Executable-prefix regressions for operating-stock projections."""
from copy import deepcopy
import unittest

import mechanics as m
from operating_stock import protect_operating_stock


class OperatingStockPrefixTests(unittest.TestCase):
    def setUp(self):
        self.now = 460
        self.farm = {
            'farmer': [4, 4],
            'hands': [[4, 4]],
            'money': 50000,
            'tiles': [[None for _ in range(10)] for _ in range(10)],
        }
        for x in (2, 3):
            self.farm['tiles'][4][x] = {
                'kind': 'PLANT', 'crop': 'STRAWBERRY', 'planted_day': 10,
                'yield_units': 0, 'fertilized_until_day': -1,
                'max_lifespan_step': -1, 'consecutive_unwatered': 0,
                'watered_today': True,
            }
        self.private = {
            'inventories': [{}, {}],
            'shed': {'FERTILIZER': 9},
            'seeds': {},
        }
        self.obs = {
            'step': self.now,
            'player': 0,
            'day': 19,
            'market': {
                'inventory': {'FERTILIZER': 10300, 'STRAWBERRY': 9900},
            },
        }
        self.selected = {
            'farmer': ['PASS'],
            'hands': [['PASS']],
            'market': [['SELL', 'FERTILIZER', 9]],
        }
        self.route = [
            {'farmer': ['PASS'], 'hands': [['PASS']], 'market': []}
            for _ in range(720)
        ]
        self.route[461]['hands'][0] = ['PICKUP', 'FERTILIZER', 3]
        self.route[462]['hands'][0] = ['WEST']
        self.route[463]['hands'][0] = ['FERTILIZE']
        self.route[464]['hands'][0] = ['WEST']
        self.route[465]['hands'][0] = ['FERTILIZE']

    def propose(self, config=None):
        return protect_operating_stock(
            m, self.obs, config or {}, self.selected,
            self.farm, self.private, self.route, (226, 360, 433),
        )

    def assert_baseline_reservation(self, result, report):
        self.assertTrue(report['changed'])
        self.assertEqual(result['market'][0], ['SELL', 'FERTILIZER', 7])
        self.assertEqual(report['withheld_units'], 2)

    def test_current_tail_hire_is_engine_inert(self):
        tail = ['HIRE']
        self.selected['market'] = (
            [['SELL', 'FERTILIZER', 9]] + [[] for _ in range(9)] + [tail]
        )
        before = deepcopy(self.selected['market'][10:])
        result, report = self.propose()
        self.assert_baseline_reservation(result, report)
        self.assertEqual(result['market'][10:], before)

    def test_current_tail_animal_arrival_is_engine_inert(self):
        tail = ['BUY_ANIMAL', 'COW', 100]
        self.selected['market'] = (
            [['SELL', 'FERTILIZER', 9]] + [[] for _ in range(9)] + [tail]
        )
        before = deepcopy(self.selected['market'][10:])
        result, report = self.propose()
        self.assert_baseline_reservation(result, report)
        self.assertEqual(result['market'][10:], before)

    def test_future_tail_hire_cannot_shorten_current_service_horizon(self):
        self.route[462]['market'] = [[] for _ in range(10)] + [['HIRE']]
        result, report = self.propose()
        self.assert_baseline_reservation(result, report)

    def test_future_tail_fertilizer_buy_cannot_veto_current_reservation(self):
        self.route[462]['market'] = (
            [[] for _ in range(10)] + [['BUY_PRODUCT', 'FERTILIZER', 3]]
        )
        result, report = self.propose()
        self.assert_baseline_reservation(result, report)

    def test_zero_cap_still_executes_slot_zero_hire_for_bonus_water(self):
        # Engine semantics are max(1, configured cap).  Carry one fertilizer so
        # the one-slot reservation bound reaches the later water-service gate.
        self.private['inventories'][1]['FERTILIZER'] = 1
        for x in (2, 3):
            self.farm['tiles'][4][x]['planted_day'] = 11
        self.route[480]['market'] = [['HIRE']]
        for step, action in [
            (481, ['WEST']), (482, ['WEST']), (483, ['WATER']),
            (484, ['WEST']), (485, ['WATER']),
        ]:
            self.route[step]['hands'] = [action]

        result, report = self.propose(config={'maxMarketOrdersPerTurn': 0})
        self.assertTrue(report['changed'])
        self.assertEqual(result['market'][0], ['SELL', 'FERTILIZER', 8])
        self.assertEqual(report['withheld_units'], 1)
        self.assertEqual(report['reservation_bound'], 1)
        self.assertEqual(report['bonus_day_water_service']['funded_hire_cost'], 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
