# SPDX-License-Identifier: Apache-2.0
"""Focused prepared-packet binding contracts for ordered selected SELL."""
import unittest

from ordered_selected_sell import _binding, _configuration_binding


class OrderedSelectedSellConfigBindingTests(unittest.TestCase):
    def observation(self):
        return {
            'player': 0,
            'step': 17,
            'day': 0,
            'hour': 17,
            'farms': [{'farmer': [4, 4], 'hands': [], 'tiles': [[None]]}],
            'private': {
                'shed': {'WHEAT': 1, 'MILK': 2},
                'inventories': [{'WHEAT': 1, 'MILK': 2}, {}],
            },
            'market': {'inventory': {'WHEAT': 100, 'MILK': 100}},
            'town': {'shops': []},
        }

    def selected(self):
        return {'farmer': ['PASS'], 'hands': [], 'market': [['SELL', 'MILK', 1]]}

    def test_equivalent_config_mapping_order_reuses_same_stage(self):
        left = {
            'turnsPerDay': 24,
            'boardSize': 10,
            'nested': {'alpha': 1, 'beta': [2, 3]},
        }
        right = {
            'nested': {'beta': [2, 3], 'alpha': 1},
            'boardSize': 10,
            'turnsPerDay': 24,
        }
        self.assertEqual(_configuration_binding(left), _configuration_binding(right))
        self.assertEqual(
            _binding(self.observation(), left, self.selected()),
            _binding(self.observation(), right, self.selected()),
        )

    def test_sequence_and_scalar_type_differences_remain_distinct(self):
        base = {'turnsPerDay': 24, 'shape': [1, 2]}
        self.assertNotEqual(
            _configuration_binding(base),
            _configuration_binding({'shape': (1, 2), 'turnsPerDay': 24}),
        )
        self.assertNotEqual(
            _configuration_binding(base),
            _configuration_binding({'shape': [1, 2], 'turnsPerDay': 24.0}),
        )
        self.assertNotEqual(
            _configuration_binding(base),
            _configuration_binding({'shape': [1, 2], 'turnsPerDay': True}),
        )

    def test_order_sensitive_runtime_state_is_not_canonicalized(self):
        config = {'turnsPerDay': 24}
        left = self.observation()
        right = self.observation()
        right['private']['inventories'][0] = {'MILK': 2, 'WHEAT': 1}
        self.assertNotEqual(
            _binding(left, config, self.selected()),
            _binding(right, config, self.selected()),
        )


if __name__ == '__main__':
    unittest.main()
