"""Focused regressions for the real engine's episode and storage boundaries.

Run with VARIANTS_PATH=variants_original.py to reproduce the original failures.
Reads pinned engine files from ENGINE_DIR or the existing canonical archive.
No network fetches, full games, or candidate-policy calls are needed.
"""
from __future__ import annotations
import copy
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import unittest
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent
LEAGUE = ROOT.parent
GAME_ROOT = LEAGUE.parent
ENGINE_HASHES = {
    'kaggriculture.json': 'a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867',
    'kaggriculture.py': 'bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e',
    'utils.py': '537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b',
}

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

variants = load('tested_variants', ROOT / os.environ.get('VARIANTS_PATH', '../variants.py'))
baseline = ROOT / 'variants_original.py'
if hashlib.sha256(baseline.read_bytes()).hexdigest() != '69df8c159d8f0b48377052d1637c49727ec551a8774f9f0215984fa89acd0746':
    raise AssertionError('historical baseline fixture hash mismatch')
original = load('original_variants', baseline)

class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.action = {'farmer': ['NORTH'], 'hands': [['WEST'], ['PASS']],
                       'market': [['SELL', 'WHEAT', 1], ['HIRE'], ['HIRE']]}
        self.obs = {'step': 1, 'player': 0, 'private': {'shed': {'WHEAT': 1}},
                    'town': {'unlocked_shops': ['PET_CAFE']}}
        self.shops = {'PET_CAFE': ['CARROT']}

    def apply(self, mode, cfg=None):
        return variants.transform(self.action, self.obs, mode, self.shops, cfg)

    def test_short_episode_final_sale_is_not_suppressed(self):
        self.obs['step'] = 46  # last action in the official 48-state episode
        self.assertEqual(self.apply('sale_cadence', {'episodeSteps': 48}), self.action)

    def test_short_episode_final_crop_sale_is_not_suppressed(self):
        self.obs['step'] = 46
        self.assertEqual(self.apply('crop_demand', {'episodeSteps': 48}), self.action)

    def test_engine_episode_horizon_overrides_legacy_days_alias(self):
        self.obs['step'] = 46
        self.assertEqual(self.apply('sale_cadence', {'episodeSteps': 48, 'days': 99}), self.action)

    def test_final_executable_day_math_uses_episode_steps_minus_two(self):
        for steps in (2, 3, 24, 25, 26, 48, 720, 721, 722):
            with self.subTest(episodeSteps=steps):
                self.obs['step'] = steps - 2
                day, hour, days = variants._time(self.obs, {'episodeSteps': steps, 'turnsPerDay': 24})
                self.assertEqual((day, hour, days), ((steps-2)//24, (steps-2)%24, (steps-2)//24+1))

    def test_default_shed_capacity_matches_official_engine(self):
        self.obs['private']['shed']['WHEAT'] = 80
        self.assertEqual(self.apply('sale_cadence'), self.action)
        self.assertEqual(self.apply('crop_demand'), self.action)

    def test_explicit_shed_capacity_remains_supported(self):
        self.obs['private']['shed']['WHEAT'] = 159
        self.assertNotEqual(self.apply('sale_cadence', {'shedCapacity': 200}), self.action)
        self.obs['private']['shed']['WHEAT'] = 160
        self.assertEqual(self.apply('sale_cadence', {'shedCapacity': 200}), self.action)

    def test_private_shed_capacity_override_remains_supported(self):
        self.obs['private']['shed'] = {'WHEAT': 16}
        self.obs['private']['shed_capacity'] = 20
        self.assertEqual(self.apply('sale_cadence', {'shedCapacity': 200}), self.action)

    def test_day_hour_observation_uses_same_horizon(self):
        self.obs.pop('step')
        self.obs.update(day=1, hour=22)
        self.assertEqual(self.apply('sale_cadence', {'episodeSteps': 48}), self.action)

    def test_legacy_days_alias_without_episode_horizon_is_preserved(self):
        self.obs['step'] = 25
        self.assertEqual(self.apply('sale_cadence', {'days': 2}), self.action)
        self.assertNotEqual(self.apply('sale_cadence', {'days': 3}), self.action)

    def test_real_farmer_hands_actions_are_deep_copied(self):
        before = copy.deepcopy((self.action, self.obs))
        output = self.apply('sale_cadence')
        self.assertEqual(output['farmer'], self.action['farmer'])
        self.assertEqual(output['hands'], self.action['hands'])
        output['farmer'][0] = 'PASS'
        output['hands'][0][0] = 'PASS'
        self.assertEqual((self.action, self.obs), before)

    def test_nonterminal_observation_only_sale_behavior_is_unchanged(self):
        got = self.apply('sale_cadence', {'episodeSteps': 48, 'shedCapacity': 100})
        self.assertEqual(got['market'], [['HIRE'], ['HIRE']])
        self.assertEqual(got['hands'], self.action['hands'])

    def test_default_719_action_production_configuration_is_exactly_unchanged(self):
        cfg = {'episodeSteps': 720, 'turnsPerDay': 24, 'shedCapacity': 100}
        for step in range(719):
            self.obs['step'] = step
            for mode in original.VARIANTS:
                self.assertEqual(variants.transform(self.action, self.obs, mode, self.shops, cfg),
                                 original.transform(self.action, self.obs, mode, self.shops, cfg),
                                 (step, mode))

    def test_turns_per_day_lower_bound_matches_engine(self):
        self.obs['step'] = 1
        self.assertEqual(variants._time(self.obs, {'episodeSteps': 3, 'turnsPerDay': 0}), (1, 0, 2))

    def test_invalid_action_and_unknown_variant_still_fail_closed(self):
        with self.assertRaises(ValueError):
            variants.transform([], self.obs, 'sale_cadence', self.shops)
        with self.assertRaises(ValueError):
            variants.transform(self.action, self.obs, 'unknown', self.shops)

class OfficialEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helper_path = GAME_ROOT / '20260907-offline-agent/evaluate.py'
        if hashlib.sha256(helper_path.read_bytes()).hexdigest() != 'cd113a94ae99b03492502e425bdcf09c3db17a2aa2a8fd866f0d78caec9e311e':
            raise AssertionError('official-engine helper hash mismatch')
        cls.helper = load('engine_test_driver', helper_path)
        temporary = tempfile.TemporaryDirectory(prefix='meridian-engine-')
        cls.addClassCleanup(temporary.cleanup)
        cache = Path(temporary.name)
        if os.environ.get('ENGINE_DIR'):
            source = Path(os.environ['ENGINE_DIR'])
            for name in ENGINE_HASHES:
                (cache / name).write_bytes((source / name).read_bytes())
        else:
            archive = GAME_ROOT / 'cloud-execution-lab/exports/titan-current.tar.gz'
            # Select only these regular members; never unpack the whole archive.
            with tarfile.open(archive, 'r:gz') as bundle:
                for name in ENGINE_HASHES:
                    member = bundle.getmember('checks/reference/engine/' + name)
                    if not member.isfile() or member.size > 2_000_000:
                        raise AssertionError('unexpected engine archive member')
                    stream = bundle.extractfile(member)
                    if stream is None:
                        raise AssertionError('missing engine archive member')
                    with stream:
                        (cache / name).write_bytes(stream.read())
        # Verify all bytes before get_engine, so its downloader is never entered.
        for name, expected in ENGINE_HASHES.items():
            if hashlib.sha256((cache / name).read_bytes()).hexdigest() != expected:
                raise AssertionError('official engine hash mismatch: ' + name)
        names = ('kaggle_environments', 'kaggle_environments.utils')
        saved = {name: sys.modules.get(name) for name in names}
        def restore_modules():
            for name, value in saved.items():
                if value is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = value
        cls.addClassCleanup(restore_modules)
        cls.engine, cls.hashes = cls.helper.get_engine(cache)
        if cls.hashes != ENGINE_HASHES:
            raise AssertionError('official engine hash mismatch')

    def test_final_sale_reaches_actual_terminal_reward_in_both_seats(self):
        for seat in (0, 1):
            for mode in ('sale_cadence', 'crop_demand'):
                with self.subTest(seat=seat, variant=mode):
                    h, e = self.helper, self.engine
                    cfg = h.Struct({k: v.get('default') if isinstance(v, dict) else v
                                    for k,v in e.specification['configuration'].items()})
                    cfg.update(seed=0, episodeSteps=48)
                    env = h.Struct(configuration=cfg, done=False, info={})
                    state = [h.Struct(observation=h.Struct(), action={}, status='ACTIVE', reward=0)
                             for _ in range(2)]
                    e.interpreter(state, env)
                    for s in state:
                        s.observation.step = 46
                        s.observation.day = 1
                        s.observation.hour = 22
                        s.action = {'farmer': ['PASS'], 'hands': [], 'market': []}
                    state[seat].observation.private['shed']['WHEAT'] = 1
                    state[0].observation.town['unlocked_shops'] = ['PET_CAFE']
                    parent = {'farmer': ['PASS'], 'hands': [], 'market': [['SELL', 'WHEAT', 1]]}
                    before = state[0].observation.farms[seat]['money']
                    expected_gain = e.market_price('WHEAT', state[0].observation.market['inventory']['WHEAT'])
                    state[seat].action = variants.transform(parent, copy.deepcopy(state[seat].observation), mode, e.SHOPS, cfg)
                    e.interpreter(state, env)
                    self.assertEqual(state[seat].status, 'DONE')
                    self.assertEqual(state[seat].reward, before + expected_gain)
                    self.assertEqual(state[seat].observation.private['shed'].get('WHEAT',0), 0)

if __name__ == '__main__': unittest.main(verbosity=2)
