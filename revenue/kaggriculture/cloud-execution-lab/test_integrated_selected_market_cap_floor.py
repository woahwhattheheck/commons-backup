import types
import unittest

import integrated_selected as subject


class IntegratedSelectedMarketCapFloorTest(unittest.TestCase):
    def test_projection_passes_engine_minimum_one_market_slot(self):
        agent = subject.IntegratedSelectedAgent.__new__(subject.IntegratedSelectedAgent)
        agent.execution = types.SimpleNamespace(seller=types.SimpleNamespace(horizon=0))
        agent.controller = types.SimpleNamespace(
            cur='route',
            R={'route': [{'farmer': ['PASS'], 'hands': [], 'market': []}]},
        )
        agent.production = types.SimpleNamespace(A=types.SimpleNamespace(DECISIONS=()), plans={})

        captured = []
        old_market = subject.atlas._market
        old_full_market = subject.atlas._full_market
        old_decay = subject.m._decay_plants
        try:
            subject.atlas._market = lambda action, maximum: (captured.append(maximum) or [])
            subject.atlas._full_market = lambda *args, **kwargs: None
            subject.m._decay_plants = lambda *args, **kwargs: None

            obs = {'step': 0}
            farm = {
                'farmer': [0, 0], 'hands': [], 'tiles': [['EMPTY']],
                'money': 0, 'hires_today': 0, 'unlocked_quadrants': ['NW'],
            }
            private = {'shed': {}, 'inventories': [{}], 'seeds': {}}
            selected = {'farmer': ['PASS'], 'hands': [], 'market': []}
            for raw in (0, -3):
                with self.subTest(max_orders=raw):
                    captured.clear()
                    agent._projection(
                        obs,
                        {
                            'maxMarketOrdersPerTurn': raw,
                            'turnsPerDay': 24,
                            'boardSize': 1,
                            'shedCapacity': 100,
                            'episodeSteps': 720,
                        },
                        selected,
                        farm.copy(),
                        private.copy(),
                        {},
                    )
                    self.assertTrue(captured)
                    self.assertTrue(all(value == 1 for value in captured))
        finally:
            subject.atlas._market = old_market
            subject.atlas._full_market = old_full_market
            subject.m._decay_plants = old_decay


if __name__ == '__main__':
    unittest.main()
