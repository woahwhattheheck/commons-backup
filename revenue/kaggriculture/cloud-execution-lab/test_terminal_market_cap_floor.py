import importlib.util
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
MODULE = ROOT / 'reference' / 'titan-current' / 'terminal.py'
spec = importlib.util.spec_from_file_location('titan_terminal_cap_floor', MODULE)
terminal = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = terminal
spec.loader.exec_module(terminal)


def observation(step=698):
    tiles = [['EMPTY' for _ in range(10)] for _ in range(10)]
    farm = {
        'farmer': [4, 4], 'hands': [], 'tiles': tiles,
        'money': 100000, 'unlocked_quadrants': ['NW', 'NE', 'SW', 'SE'],
    }
    return {
        'step': step,
        'player': 0,
        'farms': [farm],
        'private': {'shed': {'MILK': 2, 'WOOL': 3}, 'inventories': [{}]},
        'market': {'prices': {'MILK': 7, 'WOOL': 5}},
    }


class MarketCapFloorTest(unittest.TestCase):
    def assert_one_engine_slot(self, action):
        self.assertEqual(1, len(action['market']))
        self.assertEqual('SELL', action['market'][0][0])
        self.assertIn(action['market'][0][1], {'MILK', 'WOOL'})

    def test_overlay_uses_engine_minimum_market_slot(self):
        obs = observation()
        parent = {'farmer': ['PASS'], 'hands': [], 'market': []}
        for raw in (0, -3):
            with self.subTest(max_orders=raw):
                action = terminal.overlay(obs, parent, {'maxMarketOrdersPerTurn': raw})
                self.assert_one_engine_slot(action)

    def test_planner_uses_engine_minimum_market_slot(self):
        obs = observation()
        parent = {'farmer': ['PASS'], 'hands': [], 'market': []}
        for raw in (0, -3):
            with self.subTest(max_orders=raw):
                action = terminal.Planner().act(obs, parent, {'maxMarketOrdersPerTurn': raw})
                self.assert_one_engine_slot(action)


if __name__ == '__main__':
    unittest.main()
