# SPDX-License-Identifier: Apache-2.0
"""Current-market shed-room regressions for operating-stock retention."""
from copy import deepcopy
import unittest

import mechanics as m
from operating_stock import protect_operating_stock


class OperatingStockCurrentRoomTests(unittest.TestCase):
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
                'kind': 'PLANT',
                'crop': 'STRAWBERRY',
                'planted_day': 10,
                'yield_units': 0,
                'fertilized_until_day': -1,
                'max_lifespan_step': -1,
                'consecutive_unwatered': 0,
                'watered_today': True,
            }
        # Deliberately full before the current market queue.  Current owned SELLs
        # are the only room certificate exercised by these regressions.
        self.private = {
            'inventories': [{}, {}],
            'shed': {'FERTILIZER': 9, 'WOOL': 91},
            'seeds': {},
        }
        self.obs = {
            'step': self.now,
            'player': 0,
            'day': 19,
            'market': {
                'inventory': {
                    'FERTILIZER': 10300,
                    'STRAWBERRY': 9900,
                    'WOOL': 10000,
                    'COW': 10000,
                }
            },
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
        self.checkpoints = (226, 360, 433)

    def propose(self, selected, config=None):
        return protect_operating_stock(
            m,
            self.obs,
            config or {},
            selected,
            self.farm,
            self.private,
            self.route,
            self.checkpoints,
        )

    def test_current_owned_sell_frees_room_for_retained_fertilizer(self):
        selected = {
            'farmer': ['PASS'],
            'hands': [['PASS']],
            'market': [
                ['SELL', 'WOOL', 20],
                ['SELL', 'FERTILIZER', 9],
            ],
        }
        original = deepcopy((self.farm, self.private, selected, self.route))
        result, report = self.propose(selected)

        self.assertTrue(report['changed'])
        self.assertEqual(
            result['market'],
            [['SELL', 'WOOL', 20], ['SELL', 'FERTILIZER', 7]],
        )
        self.assertEqual(report['required_stock'], 2)
        self.assertEqual((self.farm, self.private, selected, self.route), original)

    def test_current_sell_room_preserves_later_fixed_arrival(self):
        selected = {
            'farmer': ['PASS'],
            'hands': [['PASS']],
            'market': [
                ['SELL', 'WOOL', 20],
                ['SELL', 'FERTILIZER', 9],
                ['BUY_ANIMAL', 'COW', 5],
            ],
        }
        result, report = self.propose(selected)

        self.assertTrue(report['changed'])
        self.assertEqual(result['market'][0], ['SELL', 'WOOL', 20])
        self.assertEqual(result['market'][1], ['SELL', 'FERTILIZER', 7])
        self.assertEqual(result['market'][2], ['BUY_ANIMAL', 'COW', 5])
        self.assertEqual(
            report['commitment_liquidity']['required_cash'],
            5 * m.ANIMALS['COW']['cost'],
        )

    def test_future_sell_is_not_room_credit_for_future_deposit(self):
        selected = {
            'farmer': ['PASS'],
            'hands': [['PASS']],
            'market': [['SELL', 'FERTILIZER', 9]],
        }
        # The current candidate sale would leave 93 physical units.  A future
        # ten-unit PLACE therefore cannot be certified against capacity 100;
        # the same-row future SELL must not be used as room credit.
        self.route[462]['farmer'] = ['PLACE', 'WOOL', 10]
        self.route[462]['market'] = [['SELL', 'WOOL', 90]]
        result, report = self.propose(selected)

        self.assertIs(result, selected)
        self.assertFalse(report['changed'])
        self.assertEqual(report['reason'], 'retained_stock_conflicts_with_arrival_room')

    def test_configured_eleventh_market_slot_is_in_arrival_bound(self):
        selected = {
            'farmer': ['PASS'],
            'hands': [['PASS']],
            'market': [
                ['SELL', 'FERTILIZER', 9],
                *([[]] * 9),
                ['BUY_ANIMAL', 'COW', 8],
            ],
        }
        result, report = self.propose(
            selected, config={'maxMarketOrdersPerTurn': 11})

        self.assertIs(result, selected)
        self.assertFalse(report['changed'])
        self.assertEqual(
            report['reason'], 'retained_stock_conflicts_with_arrival_room')


if __name__ == '__main__':
    unittest.main(verbosity=2)
