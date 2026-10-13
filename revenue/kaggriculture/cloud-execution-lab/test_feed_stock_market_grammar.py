# SPDX-License-Identifier: Apache-2.0
"""Pinned-engine market grammar at the feed-stock reservation boundary."""
from copy import deepcopy
import unittest

import mechanics as m
from operating_stock import protect_feed_stock


class FeedStockMarketGrammarTests(unittest.TestCase):
    def setUp(self):
        self.farm = {
            'farmer': [0, 0], 'hands': [[4, 4]], 'money': 50000,
            'hires_today': 1, 'unlocked_quadrants': ['NW'],
            'tiles': [[None for _ in range(10)] for _ in range(10)],
        }
        self.farm['tiles'][4][3] = m._new_animal('COW', 1)
        self.farm['tiles'][4][2] = m._new_animal('SHEEP', 1)
        self.private = {'shed': {'WHEAT': 9}, 'inventories': [{}, {}], 'seeds': {}}
        self.obs = {
            'step': 460, 'day': 19, 'player': 0,
            'market': {'inventory': {'WHEAT': 9800, 'FERTILIZER': 10000}},
            'farms': [self.farm, {}], 'private': self.private,
        }
        self.selected = {
            'farmer': ['PASS'], 'hands': [['PASS']],
            'market': [['SELL', 'WHEAT', 9]],
        }
        self.route = [
            {'farmer': ['PASS'], 'hands': [['PASS']], 'market': []}
            for _ in range(720)
        ]
        for step, action in (
            (461, ['PICKUP', 'WHEAT', 3]), (462, ['WEST']),
            (463, ['FEED']), (464, ['WEST']), (465, ['FEED']),
        ):
            self.route[step]['hands'][0] = action

    def propose(self):
        return protect_feed_stock(
            m, self.obs, {}, self.selected, self.farm,
            self.private, self.route, (),
        )

    def test_engine_valid_coercion_and_trailing_fields_are_preserved(self):
        for quantity in ('9', 9.9):
            with self.subTest(quantity=quantity):
                metadata = {'opaque': ['keep', quantity]}
                self.selected['market'] = [
                    ['SELL', 'WHEAT', quantity, 'ignored-by-engine', metadata],
                    ['SELL', 'WOOL', 1, 'also-opaque'],
                ]
                before = deepcopy(self.selected)
                result, report = self.propose()
                self.assertTrue(report['certified'])
                self.assertTrue(report['changed'])
                self.assertEqual(
                    result['market'][0],
                    ['SELL', 'WHEAT', 7, 'ignored-by-engine', metadata],
                )
                self.assertEqual(result['market'][1], before['market'][1])
                self.assertEqual(self.selected, before)

    def test_engine_valid_future_sell_is_not_misclassified_as_absent(self):
        self.route[461]['market'] = [['SELL', 'WHEAT', '1', 'opaque']]
        self.route[461]['hands'][0] = ['PASS']
        self.route[462]['hands'][0] = ['PICKUP', 'WHEAT', 3]
        self.route[463]['hands'][0] = ['WEST']
        self.route[464]['hands'][0] = ['FEED']
        self.route[465]['hands'][0] = ['WEST']
        self.route[466]['hands'][0] = ['FEED']
        result, report = self.propose()
        self.assertIs(result, self.selected)
        self.assertFalse(report['certified'])
        self.assertEqual(report['reason'], 'intervening_wheat_sale_before_protected_pickup')

    def test_uncoercible_quantity_fails_closed(self):
        self.selected['market'] = [['SELL', 'WHEAT', '9.5', 'opaque']]
        result, report = self.propose()
        self.assertIs(result, self.selected)
        self.assertFalse(report['certified'])
        self.assertEqual(report['reason'], 'expected an engine quantity order')


if __name__ == '__main__':
    unittest.main()
