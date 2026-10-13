"""Regressions for the observed market-slot failure, not parent test repeats."""
import importlib.util
from pathlib import Path
import sys
import unittest

spec = importlib.util.spec_from_file_location('frontier_candidate_test', Path(__file__).with_name('candidate.py'))
candidate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = candidate
spec.loader.exec_module(candidate)


class SalesTests(unittest.TestCase):
    def observation(self):
        return {'player': 0, 'step': 300, 'farms': [{'farmer': [4, 4], 'hands': [], 'tiles': [[None]*10 for _ in range(10)]}],
                'private': {'shed': {'MILK': 8, 'WHEAT': 30}, 'inventories': [{}]},
                'market': {'prices': {'MILK': 160}, 'inventory': {'MILK': 10000}},
                'town': {'unlocked_shops': []}}

    def test_ten_hires_survive_sale_opportunity(self):
        action = {'farmer': ['PASS'], 'hands': [], 'market': [['HIRE'] for _ in range(10)]}
        self.assertEqual(candidate.sell_finished(self.observation(), action), action)

    def test_capital_feed_positions_and_units_are_unchanged(self):
        action = {'farmer': ['EAST'], 'hands': [['WATER']],
                  'market': [['BUY_PRODUCT', 'WHEAT', 12], ['HIRE'], ['BUY_LAND']]}
        result = candidate.sell_finished(self.observation(), action)
        self.assertEqual(result['market'][:3], action['market'])
        self.assertEqual(result['farmer'], action['farmer'])
        self.assertEqual(result['hands'], action['hands'])
        self.assertEqual(result['market'][3:], [['SELL', 'MILK', 8]])

    def test_same_turn_pickup_reserved_and_duplicate_sale_not_inflated(self):
        action = {'farmer': ['PICKUP', 'MILK', 3], 'hands': [],
                  'market': [['SELL', 'MILK', 2], ['SELL', 'MILK', 9], ['SELL', 'WHEAT', 4]]}
        result = candidate.sell_finished(self.observation(), action)
        self.assertEqual(result['market'], [['SELL', 'MILK', 5], ['SELL', 'MILK', 0], ['SELL', 'WHEAT', 4]])
        self.assertEqual(action['market'][0][2], 2)


if __name__ == '__main__':
    unittest.main()
