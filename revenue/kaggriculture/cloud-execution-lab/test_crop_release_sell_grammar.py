# SPDX-License-Identifier: Apache-2.0
"""Pinned-engine CARROT SELL grammar contracts for crop release."""
from copy import deepcopy
import unittest

from crop_release import commit_crop_sale, offer_crop


class CropReleaseSellGrammarContracts(unittest.TestCase):
    def fixture(self, units=3):
        tiles = [[None for _ in range(10)] for _ in range(10)]
        farm = {'farmer': [4, 4], 'hands': [], 'tiles': tiles, 'money': 0}
        observation = {
            'step': 457,
            'player': 0,
            'farms': [farm, deepcopy(farm)],
            'private': {'shed': {'CARROT': units}, 'inventories': [{}]},
        }
        intent = {
            'status': 'deposited',
            'player': 0,
            'last_observed_step': 457,
            'outlet_step': 457,
            'sale_quantity_remaining': units,
            'offered_to_seller': False,
            'crop_receipts': [],
        }
        return intent, observation

    def test_malformed_inherited_rows_are_inert_and_never_raise(self):
        intent, observation = self.fixture(3)
        selected = {
            'farmer': ['PASS'],
            'hands': [],
            'market': [
                ('SELL', 'CARROT', 2),
                ['SELL'],
                ['SELL', 'CARROT', 'x'],
                {'op': 'SELL', 'item': 'CARROT', 'qty': 3},
                ('BUY_PRODUCT', 'CARROT', 1),
            ],
        }
        original = deepcopy(selected)
        offered, accepted = offer_crop(intent, observation, selected)
        self.assertTrue(accepted)
        self.assertEqual(selected, original)
        self.assertEqual(offered['market'][:-1], original['market'])
        self.assertEqual(offered['market'][-1], ['SELL', 'CARROT', 3])

        committed = commit_crop_sale(intent, observation, selected, observation)
        self.assertEqual(committed['status'], 'deposited')
        self.assertNotIn('sale_orders', committed)
        self.assertEqual(selected, original)

    def test_engine_coercible_trailing_sell_rows_keep_original_slots_and_bytes(self):
        intent, observation = self.fixture(5)
        returned = {
            'farmer': ['PASS'],
            'hands': [],
            'market': [
                ('SELL', 'CARROT', 99),
                ['SELL', 'CARROT', '2', 'metadata'],
                ['SELL', 'CARROT', 2.9],
                ['SELL', 'CARROT', True, 'ignored'],
            ],
        }
        original = deepcopy(returned)
        offered, accepted = offer_crop(intent, observation, returned)
        self.assertTrue(accepted)
        self.assertIs(offered, returned)
        self.assertEqual(returned, original)

        committed = commit_crop_sale(intent, observation, returned, observation)
        self.assertEqual(committed['status'], 'awaiting_observed_sale')
        self.assertEqual(committed['sale_orders'], [(1, 2), (2, 2), (3, 1)])
        self.assertEqual(returned, original)

    def test_list_buy_product_conflicts_but_non_list_alias_is_inert(self):
        intent, observation = self.fixture(3)
        inert = {'farmer': ['PASS'], 'hands': [],
                 'market': [('BUY_PRODUCT', 'CARROT', 1)]}
        offered, accepted = offer_crop(intent, observation, inert)
        self.assertTrue(accepted)
        self.assertEqual(offered['market'][-1], ['SELL', 'CARROT', 3])

        conflict = {'farmer': ['PASS'], 'hands': [],
                    'market': [['BUY_PRODUCT', 'CARROT', 1]]}
        self.assertEqual(offer_crop(intent, observation, conflict), (conflict, False))
        committed = commit_crop_sale(intent, observation, conflict, observation)
        self.assertEqual(committed['status'], 'sale_attribution_unknown')
        self.assertEqual(committed['receipt_failure'], 'carrot_purchase_in_sale_queue')


if __name__ == '__main__':
    unittest.main()
