# SPDX-License-Identifier: Apache-2.0
"""L01 keys in the V3 tree: tape identity when off, the five mutations when on, and the
runtime seams.  Standard library only:

    python -m unittest -v checks/test_v3_l01.py

The cases carry PR #11459's pytest contract (candidates/v3-l01-leader-mechanics) onto
the a055fd56 canonical, which ships the same Arlene MAIN tape 7015cc00acfa4922.
"""
from __future__ import annotations

from collections import Counter
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import l01_mechanics as l01  # noqa: E402
from titan_runtime import Features, TitanAgent  # noqa: E402


def load_arlene():
    spec = importlib.util.spec_from_file_location('v3_l01_arlene_pristine', ROOT / 'reference/next-panel/vendor/arlene.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def flags(**on):
    out = {key: False for key in l01.FLAG_KEYS}
    out.update(on)
    return out


class RouteTapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        arlene = load_arlene()
        assert arlene.MAIN == l01.MAIN
        cls.routes = copy.deepcopy(arlene.routes())

    def fresh(self):
        return copy.deepcopy(self.routes)

    def test_flag_off_identity(self):
        R = self.fresh()
        before = copy.deepcopy(R[l01.MAIN])
        act = Counter()
        reasons = []
        l01.patch_routes(R, flags(), act, reasons)
        self.assertEqual(reasons, [l01.NOOP])
        self.assertEqual(act, Counter())
        self.assertEqual(R[l01.MAIN], before)

    def test_land_posts_74_98_and_keeps_150_265(self):
        R = self.fresh()
        act = Counter()
        l01.patch_routes(R, flags(LAND=True), act, [])
        main = R[l01.MAIN]
        self.assertIn(['BUY_LAND'], main[74]['market'])
        self.assertIn(['BUY_LAND'], main[98]['market'])
        self.assertIn(['BUY_LAND'], main[150]['market'])
        self.assertIn(['BUY_LAND'], main[265]['market'])
        self.assertGreaterEqual(act['LAND'], 2)
        self.assertIn(['SELL', 'WHEAT', 0], main[74]['market'])

    def test_sheep_rewrites_cows_after_step_1(self):
        R = self.fresh()
        act = Counter()
        l01.patch_routes(R, flags(SHEEP=True), act, [])
        counts, events = l01.animal_buys(R[l01.MAIN])
        self.assertIn(('COW', 2), [(a, n) for t, a, n in events if t == 1])
        self.assertTrue(all(a != 'COW' for t, a, n in events if t > 1))
        self.assertEqual(counts['COW'], 2)
        self.assertEqual(counts['SHEEP'], 12)
        self.assertEqual(counts['GOOSE'], 3)
        self.assertGreaterEqual(act['SHEEP'], 1)

    def test_day0buy_replaces_wheat_13(self):
        R = self.fresh()
        act = Counter()
        l01.patch_routes(R, flags(DAY0BUY=True), act, [])
        wanted = [['BUY_PRODUCT', item, n] for item, n in l01.DAY0_BASKET]
        self.assertEqual(R[l01.MAIN][0]['market'], wanted)
        self.assertGreaterEqual(act['DAY0BUY'], 1)

    def test_leanplant_last_92_wheat_to_pass(self):
        R = self.fresh()
        before = l01.plant_counts(self.routes[l01.MAIN])
        self.assertEqual(before['WHEAT'], 164)
        self.assertEqual(sum(before.values()), 240)
        act = Counter()
        l01.patch_routes(R, flags(LEANPLANT=True), act, [])
        after = l01.plant_counts(R[l01.MAIN])
        self.assertEqual(after['WHEAT'], 72)
        self.assertEqual(after['MELON'], before['MELON'])
        self.assertEqual(after['STRAWBERRY'], before['STRAWBERRY'])
        self.assertEqual(after['CARROT'], before['CARROT'])
        self.assertEqual(sum(after.values()), 148)
        self.assertGreaterEqual(act['LEANPLANT'], 92)


class TrancheTests(unittest.TestCase):
    def test_enlarges_wheat_carrot_and_packs_other_products(self):
        act = Counter()
        action = {'farmer': ['PASS'], 'hands': [], 'market': [['SELL', 'WHEAT', 3]]}
        obs = {'step': 696, 'day': 29, 'private': {'shed': {'WHEAT': 80, 'CARROT': 40, 'MILK': 5, 'EGG': 2}}}
        out = l01.apply_tranche(action, obs, flags(TRANCHE=True), act, shed=obs['private']['shed'])
        wheat = [o for o in out['market'] if o and o[0] == 'SELL' and o[1] == 'WHEAT'][0]
        carrot = [o for o in out['market'] if o and o[0] == 'SELL' and o[1] == 'CARROT'][0]
        self.assertEqual(wheat[2], 57)
        self.assertEqual(carrot[2], 32)
        items = [o[1] for o in out['market'] if o and o[0] == 'SELL']
        self.assertIn('MILK', items)
        self.assertIn('EGG', items)
        self.assertGreaterEqual(act['TRANCHE'], 3)
        self.assertEqual(action['market'], [['SELL', 'WHEAT', 3]])

    def test_off_is_object_identity(self):
        act = Counter()
        action = {'farmer': ['PASS'], 'hands': [], 'market': [['SELL', 'WHEAT', 3]]}
        obs = {'step': 696, 'day': 29, 'private': {'shed': {'WHEAT': 80, 'CARROT': 40}}}
        self.assertIs(l01.apply_tranche(action, obs, flags(), act), action)
        self.assertEqual(act, Counter())

    def test_skips_terminal_step_and_early_days(self):
        act = Counter()
        action = {'farmer': ['PASS'], 'hands': [], 'market': []}
        shed = {'WHEAT': 80, 'CARROT': 40}
        self.assertIs(l01.apply_tranche(action, {'step': 718, 'day': 29}, flags(TRANCHE=True), act, shed=shed), action)
        self.assertIs(l01.apply_tranche(action, {'step': 600, 'day': 25}, flags(TRANCHE=True), act, shed=shed), action)
        self.assertEqual(act, Counter())


class WiringTests(unittest.TestCase):
    def test_config_keys_parse_and_ship_off(self):
        data = json.loads((ROOT / 'TITAN-CONFIG.json').read_text(encoding='utf-8'))
        features = Features(**data)
        for key in l01.FEATURE_KEYS.values():
            self.assertIn(key, data)
            self.assertIs(getattr(features, key), False)
        self.assertEqual(l01.flags_from_features(features), flags())
        self.assertFalse(features.l01_land)

    def test_flags_from_features(self):
        self.assertEqual(l01.flags_from_features(Features(l01_land=True, l01_tranche=True)),
                         flags(LAND=True, TRANCHE=True))
        self.assertTrue(TitanAgent(Features(l01_land=True))._v3_active())
        self.assertFalse(TitanAgent(Features())._v3_active())

    def test_initialize_off_leaves_the_tape_pristine(self):
        pristine = copy.deepcopy(load_arlene().routes())
        agent = TitanAgent(Features())
        agent._initialize()
        self.assertEqual(agent.controller.R[l01.MAIN], pristine[l01.MAIN])
        self.assertEqual(agent.diagnostics['v3_l01']['reasons'], [l01.NOOP])
        self.assertEqual(agent.diagnostics['v3_l01']['activations'], {})

    def test_initialize_with_land_posts_buy_land(self):
        agent = TitanAgent(Features(l01_land=True))
        agent._initialize()
        main = agent.controller.R[l01.MAIN]
        self.assertIn(['BUY_LAND'], main[74]['market'])
        self.assertIn(['BUY_LAND'], main[98]['market'])
        self.assertIn(['BUY_LAND'], main[150]['market'])
        self.assertEqual(agent.diagnostics['v3_l01']['activations'], {'LAND': 2})

    def test_post_final_tranche_seam(self):
        action = {'farmer': ['PASS'], 'hands': [], 'market': [['SELL', 'WHEAT', 3]]}
        obs = {'step': 696, 'day': 29, 'private': {'shed': {'WHEAT': 80, 'CARROT': 40}}}
        agent = TitanAgent(Features())
        agent.diagnostics = {}
        self.assertIs(agent._v3_post_final(obs, {}, action), action)
        agent = TitanAgent(Features(l01_tranche=True))
        agent.diagnostics = {}
        out = agent._v3_post_final(obs, {}, action)
        self.assertEqual([o for o in out['market'] if o[1] == 'WHEAT'][0][2], 57)
        self.assertEqual([o for o in out['market'] if o[1] == 'CARROT'][0][2], 32)
        self.assertEqual(agent.diagnostics['v3_l01_tranche']['activations'], {'TRANCHE': 2})
        self.assertEqual(action['market'], [['SELL', 'WHEAT', 3]])


if __name__ == '__main__':
    unittest.main(verbosity=2)
