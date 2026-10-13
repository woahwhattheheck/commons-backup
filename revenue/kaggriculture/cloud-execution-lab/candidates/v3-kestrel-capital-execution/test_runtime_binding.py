import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
for source in (HERE, LAB):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from candidate_runtime import KestrelTitanAgent
from titan_runtime import Features


class RuntimeBindingContracts(unittest.TestCase):
    def test_exact_selected_snapshot_is_passed_to_guard(self):
        selected = {
            'farmer': ['PASS'],
            'hands': [],
            'market': [['BUY_LAND'], ['SELL', 'WOOL', 1]],
        }
        farm = {
            'money': 900,
            'unlocked_quadrants': ['NW'],
            'hires_today': 0,
            'tiles': [[None] * 10 for _ in range(10)],
            'farmer': [4, 4],
            'hands': [],
        }
        private = {
            'shed': {'WOOL': 1},
            'seeds': {},
            'inventories': [{}],
        }
        obs = {
            'step': 150,
            'player': 0,
            'farms': [deepcopy(farm), deepcopy(farm)],
            'private': deepcopy(private),
            'market': {'inventory': {}, 'prices': {}},
        }

        agent = KestrelTitanAgent(Features(early_capital=True))
        agent.consumer = SimpleNamespace(
            selected_post_units=(deepcopy(farm), deepcopy(private)),
            selected_post_units_binding=(
                150, 0, deepcopy(selected['farmer']),
                deepcopy(selected['hands']),
            ),
        )
        agent.controller = SimpleNamespace(
            cur=0,
            R=[[selected for _ in range(720)]],
        )
        agent.diagnostics = {}

        scheduler = ModuleType('scheduler')
        scheduler.parent = SimpleNamespace(DECISIONS=[])
        captured = {}

        def fake_guard(*args, **kwargs):
            captured['post_unit'] = kwargs.get('post_unit')
            return args[3], {'changed': False, 'reason': 'test'}

        with patch.dict(sys.modules, {'scheduler': scheduler}):
            with patch('candidate_runtime.order_early_capital',
                       side_effect=fake_guard):
                result = agent._early_capital_selected(
                    obs, {'episodeSteps': 720}, selected,
                )

        self.assertEqual(result, selected)
        self.assertIsNotNone(captured['post_unit'])
        self.assertEqual(
            captured['post_unit']['private']['shed']['WOOL'], 1,
        )
        self.assertEqual(
            agent.diagnostics['early_capital']['runtime_binding'],
            'selected_post_units',
        )

    def test_missing_snapshot_uses_atomic_replay_path(self):
        selected = {
            'farmer': ['PASS'],
            'hands': [],
            'market': [['BUY_LAND']],
        }
        farm = {
            'money': 900,
            'unlocked_quadrants': ['NW'],
            'hires_today': 0,
            'tiles': [[None] * 10 for _ in range(10)],
            'farmer': [4, 4],
            'hands': [],
        }
        obs = {
            'step': 150,
            'player': 0,
            'farms': [deepcopy(farm), deepcopy(farm)],
            'private': {'shed': {}, 'seeds': {}, 'inventories': [{}]},
            'market': {'inventory': {}, 'prices': {}},
        }
        agent = KestrelTitanAgent(Features(early_capital=True))
        agent.consumer = SimpleNamespace(
            selected_post_units=None,
            selected_post_units_binding=None,
        )
        agent.controller = SimpleNamespace(
            cur=0,
            R=[[selected for _ in range(720)]],
        )
        agent.diagnostics = {}

        scheduler = ModuleType('scheduler')
        scheduler.parent = SimpleNamespace(DECISIONS=[])
        captured = {}

        def fake_guard(*args, **kwargs):
            captured['post_unit'] = kwargs.get('post_unit')
            return args[3], {'changed': False, 'reason': 'test'}

        with patch.dict(sys.modules, {'scheduler': scheduler}):
            with patch('candidate_runtime.order_early_capital',
                       side_effect=fake_guard):
                result = agent._early_capital_selected(
                    obs, {'episodeSteps': 720}, selected,
                )

        self.assertEqual(result, selected)
        self.assertIsNone(captured['post_unit'])
        self.assertEqual(
            agent.diagnostics['early_capital']['runtime_binding'],
            'official_atomic_unit_replay',
        )


if __name__ == '__main__':
    unittest.main()
