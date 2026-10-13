# SPDX-License-Identifier: Apache-2.0
"""Official-engine counterfactuals and regression tests for the T13 callable."""
import argparse
import base64
import gzip
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE_ROOT = ROOT.parent
ENGINE_DIR = Path('engine')


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = load(ROOT / 'main.py', 't13_entry_test')
        cls.recovery = load(ROOT / 'recovery.py', 't13_recovery_test')
        cls.fixture = json.loads(gzip.decompress(base64.b64decode((HERE / 'weed-case.json.gz.b64').read_text())))
        ev = load(SOURCE_ROOT / 'cloud-eval/evaluate.py', 't13_test_engine_loader')
        cls.engine, cls.hashes = ev.get_engine(ENGINE_DIR)

    def setUp(self):
        self.obs = deepcopy(self.fixture['observation'])
        self.cfg = deepcopy(self.fixture['configuration'])
        self.run = self.entry.make_agent(ROOT, sell=False)
        self.c = self.run.controller

    def propose(self):
        return self.run(self.obs, self.cfg)

    def apply_official_units(self, obs, action):
        actions = self.recovery.units(action)
        demand = {}
        for a in actions:
            if len(a) > 1 and a[0] == 'PLANT':
                demand[a[1]] = demand.get(a[1], 0) + 1
        blocked = {c for c, n in demand.items() if n > obs['private']['seeds'].get(c, 0)}
        farm = obs['farms'][obs['player']]
        for i, a in enumerate(actions):
            if len(a) > 1 and a[0] == 'PLANT' and a[1] in blocked:
                a = ['PASS']
            self.engine._apply_unit_action(farm, obs['private'], i, a, 10,
                                           obs['step'] // 24, 24, 100)
        self.engine._decay_plants(farm, obs['step'])

    def test_actual_observation_reproduces_parent_and_plan(self):
        actual = self.propose()
        self.assertEqual(actual, self.fixture['parent_action'])
        self.assertEqual(self.c.plan['source_tile'], [9, 3])
        self.assertEqual(self.c.plan['omitted_tile'], [9, 0])
        self.assertEqual(self.c.plan['actions'][:3], [['DIG'], ['PLANT', 'STRAWBERRY'], ['WATER']])

    def test_owned_shadow_matches_official_engine(self):
        self.propose()
        plan = self.c.plan
        args = (self.obs, self.c.base.R[self.c.cur], 181, 192, 6, plan['actions'])
        extracted = self.c._simulate(*args)
        self.c.mechanics = self.engine
        official = self.c._simulate(*args)
        self.assertEqual(extracted, official)
        farm, _, _, blocked = official
        self.assertFalse(blocked)
        self.engine._daily_refresh_plants(farm, 7, 24)
        self.assertEqual(farm['tiles'][3][9]['crop'], 'STRAWBERRY')
        self.assertEqual(farm['tiles'][3][9]['consecutive_unwatered'], 0)
        self.assertIsNone(farm['tiles'][0][9])

    def test_naive_plant_without_same_day_water_dies(self):
        farm = deepcopy(self.obs['farms'][0]); private = deepcopy(self.obs['private'])
        for a in [['DIG'], ['PLANT', 'STRAWBERRY']]:
            self.engine._apply_unit_action(farm, private, 6, a, 10, 7, 24, 100)
        self.engine._daily_refresh_plants(farm, 7, 24)
        self.assertEqual(farm['tiles'][3][9], {'kind': 'WEED'})

    def test_full_day_sequence_and_market_preservation(self):
        base_calls = []
        original = self.c.base.act
        def counted(obs):
            result = original(obs)
            base_calls.append(deepcopy(result))
            return result
        self.c.base.act = counted
        for t in range(181, 192):
            self.obs['step'] = t; self.obs['hour'] = t % 24
            action = self.run(self.obs, self.cfg)
            self.assertEqual(action.get('market'), base_calls[-1].get('market'))
            for i, (a, b) in enumerate(zip(self.recovery.units(action), self.recovery.units(base_calls[-1]))):
                if i != 6:
                    self.assertEqual(a, b)
            self.apply_official_units(self.obs, action)
            self.assertFalse(self.c.plan['fallback'])
        self.assertEqual(len(base_calls), 11)
        self.assertEqual(self.c.calls, 11)
        farm = self.obs['farms'][0]
        self.engine._daily_refresh_plants(farm, 7, 24)
        self.assertEqual(farm['tiles'][3][9]['crop'], 'STRAWBERRY')
        self.assertEqual(farm['tiles'][2][9]['crop'], 'STRAWBERRY')
        self.assertEqual(farm['tiles'][1][9]['crop'], 'WHEAT')
        self.assertIsNone(farm['tiles'][0][9])

    def test_source_routes_unchanged_projection_matches_actions(self):
        encoded = lambda: json.dumps(self.c.base.R, sort_keys=True).encode()
        before = hashlib.sha256(encoded()).hexdigest()
        self.propose()
        self.assertEqual(self.c.base.R[self.c.cur][182]['hands'][5], ['WATER'])
        for t in range(181, 192):
            self.assertEqual(self.c.R[self.c.cur][t]['hands'][5], self.c.plan['actions'][t - 181])
        self.assertEqual(before, hashlib.sha256(encoded()).hexdigest())

    def test_no_weed_is_identical_to_parent(self):
        self.obs['farms'][0]['tiles'][3][9] = None
        expected = self.c.parent_module.Agent().act(deepcopy(self.obs))
        self.assertEqual(self.propose(), expected)
        self.assertIsNone(self.c.plan)

    def test_seed_scarcity_does_not_block_other_plantings(self):
        self.obs['private']['seeds']['STRAWBERRY'] = 0
        expected = self.c.parent_module.Agent().act(deepcopy(self.obs))
        self.assertEqual(self.propose(), expected)
        self.assertIsNone(self.c.plan)

    def test_unfavorable_price_proxy_rejects(self):
        self.obs['market']['prices'].update(STRAWBERRY=1, WHEAT=100)
        self.propose(); self.assertIsNone(self.c.plan)

    def test_insufficient_remaining_production_days_rejects(self):
        self.cfg['episodeSteps'] = 24 * 23
        self.propose(); self.assertIsNone(self.c.plan)

    def test_nonplanting_tail_rejects(self):
        self.c.base.R = deepcopy(self.c.base.R)
        self.c.base.R[self.c.cur][185]['hands'][5] = ['HARVEST']
        self.propose(); self.assertIsNone(self.c.plan)

    def test_acquisition_window_rejects(self):
        self.c.base.R = deepcopy(self.c.base.R)
        self.c.base.R[self.c.cur][185]['market'] = [['BUY', 'WHEAT', 1]]
        self.propose(); self.assertIsNone(self.c.plan)

    def test_missing_final_complete_bundle_rejects(self):
        self.c.base.R = deepcopy(self.c.base.R)
        self.c.base.R[self.c.cur][191]['hands'][5] = ['PASS']
        self.propose(); self.assertIsNone(self.c.plan)

    def test_position_change_holds_until_observed_reset(self):
        self.propose()
        self.obs['step'] = 182; self.obs['farms'][0]['hands'][5] = [8, 3]
        action = self.run(self.obs, self.cfg)
        self.assertTrue(self.c.plan['fallback'])
        self.assertEqual(action['hands'][5], ['PASS'])
        self.assertEqual(self.c.R[self.c.cur][185]['hands'][5], ['PASS'])
        self.obs['step'] = 192; self.obs['day'] = 8; self.obs['hour'] = 0
        self.obs['farms'][0]['farmer'] = [4,4]; self.obs['farms'][0]['hands'] = []
        self.obs['private']['inventories'] = [{}]
        self.run(self.obs, self.cfg)
        self.assertIsNone(self.c.plan)
        self.assertIs(self.c.R, self.c.base.R)

    def test_disabled_ablation_preserves_parent(self):
        run = self.entry.make_agent(ROOT, sell=False, enabled=False)
        self.assertEqual(run(self.obs, self.cfg), self.fixture['parent_action'])
        self.assertIsNone(run.controller.plan)

    def test_raw_file_loader_without_file_global(self):
        official = load(SOURCE_ROOT / 'cloud-pack/official.py', 't13_test_raw_loader')
        call = official.make_agent(ROOT / 'main.py')
        action = call(deepcopy(self.obs), deepcopy(self.cfg))
        self.assertIsInstance(action, dict)
        self.assertEqual(action['hands'][5], ['DIG'])

    def test_rival_farm_not_needed_by_unit_recovery(self):
        expected = self.propose()
        different = deepcopy(self.obs)
        different['farms'][1] = {}
        other = self.entry.make_agent(ROOT, sell=False)
        self.assertEqual(other(different, self.cfg), expected)
        self.assertEqual(other.controller.plan, self.c.plan)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, default=SOURCE_ROOT)
    parser.add_argument('--engine-dir', type=Path, default=ENGINE_DIR)
    args, remaining = parser.parse_known_args()
    SOURCE_ROOT = args.source_root; ENGINE_DIR = args.engine_dir
    unittest.main(argv=[sys.argv[0], *remaining])
