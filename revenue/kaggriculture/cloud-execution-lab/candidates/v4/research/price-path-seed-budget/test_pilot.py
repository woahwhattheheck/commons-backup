# SPDX-License-Identifier: Apache-2.0
"""Source-input rejection and full-engine validation of conditional price scenarios."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from harness import authenticate, engine, initial, advance
from native_pilot import conditional_prices

ROOT = Path(os.environ.get('PRICESEED_NATIVE_ROOT', '/nonexistent'))
ENGINE, STRUCT = engine(ROOT)
CALLS = {'initializations': 0, 'transitions': 0, 'scenario_comparisons': 0,
         'input_rejections': 0}


class PilotTests(unittest.TestCase):
    def test_conditional_route_scenarios_equal_complete_interpreter(self):
        for start in (0, 1, 3, 23):
            for duration in (0, 1, 4, 25):
                for inventory in (9500, 10000, 10063):
                    for seat in (0, 1):
                        state, env = initial(ENGINE, STRUCT, overrides={
                            'townShopUnlockInterval': 1000, 'weedSpawnChance': 0,
                            'townCenterSellInterval': 5, 'shedCapacity': 1000})
                        CALLS['initializations'] += 1
                        obs = state[seat].observation
                        obs.step = start
                        obs.market['inventory']['STRAWBERRY'] = inventory
                        obs.market['inventory']['TOMATO'] = 9900
                        obs.town['unlocked_shops'] = ['FARMERS_MARKET', 'FARMERS_MARKET', 'PIZZA_SHOP']
                        obs.private['shed'] = {'STRAWBERRY': 500, 'TOMATO': 500}
                        ENGINE._refresh_prices(obs.market)
                        route = [{'farmer': ['PASS'], 'hands': [], 'market':
                                  [['SELL', 'STRAWBERRY', 7], [], ['SELL', 'TOMATO', 2],
                                   *([[]] * 7), ['SELL', 'STRAWBERRY', 99]]}
                                 for _ in range(start + duration + 1)]
                        before = deepcopy((obs, route))
                        projected = conditional_prices(ENGINE, obs, env.configuration, start + duration, route)
                        self.assertEqual((obs, route), before)
                        for step in range(start, start + duration):
                            actions = [dict(), dict()]
                            actions[seat] = route[step]
                            advance(ENGINE, state, env, actions, step)
                            CALLS['transitions'] += 1
                        actual = state[seat].observation.market['prices']
                        self.assertEqual(projected, {crop: actual[crop] for crop in projected})
                        CALLS['scenario_comparisons'] += 1

    def test_known_shop_only_scenarios_equal_complete_interpreter(self):
        for start in (3, 4, 23, 24):
            state, env = initial(ENGINE, STRUCT, overrides={'townShopUnlockInterval': 1000})
            CALLS['initializations'] += 1
            obs = state[0].observation
            obs.step = start
            obs.town['unlocked_shops'] = ['FARMERS_MARKET', 'FARMERS_MARKET', 'PIZZA_SHOP']
            projected = conditional_prices(ENGINE, obs, env.configuration, start + 48)
            for step in range(start, start + 48):
                advance(ENGINE, state, env, [{}, {}], step)
                CALLS['transitions'] += 1
            self.assertEqual(projected, {crop: obs.market['prices'][crop] for crop in projected})
            CALLS['scenario_comparisons'] += 1

    def test_missing_and_changed_inputs_rejected_before_import(self):
        with tempfile.TemporaryDirectory(prefix='priceseed-input-') as temporary:
            directory = Path(temporary) / 'runtime'
            shutil.copytree(ROOT, directory, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            self.assertEqual(authenticate(directory), directory)
            for name in ('SOURCE.json', 'main.py', 'titan_runtime.py', 'mechanics.py',
                         'TITAN-CONFIG.json', 'checks/reference/engine/kaggriculture.py',
                         'checks/reference/engine/kaggriculture.json',
                         'checks/reference/engine/utils.py', 'checks/reference/evaluator/loader.py'):
                path = directory / name
                before = path.read_bytes()
                path.unlink()
                with self.assertRaises((ValueError, FileNotFoundError)):
                    authenticate(directory)
                CALLS['input_rejections'] += 1
                path.write_bytes(before + b'\n')
                with self.assertRaises(ValueError):
                    authenticate(directory)
                CALLS['input_rejections'] += 1
                path.write_bytes(before)
            self.assertEqual(authenticate(directory), directory)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(PilotTests))
    print(json.dumps({'tests': result.testsRun, 'failures': len(result.failures),
                      'errors': len(result.errors), 'skipped': len(result.skipped),
                      'counts': CALLS}), flush=True)
    raise SystemExit(not result.wasSuccessful())
