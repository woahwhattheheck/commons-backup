# SPDX-License-Identifier: Apache-2.0
"""Observer contract tests. Engine tests require explicit --parent, never fetch.

The engine tests use seeded initialized official states, not stubbed mechanics.
The small intentionally broken delegates below test only observer error handling.
"""
import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

import shadow_input_contract as audit

PARENT = None
ENGINE = None
LOADER = None
HELPER = None


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def fixture():
    farm = {'farmer': [1, 1], 'hands': [], 'tiles': [[None]*10 for _ in range(10)]}
    farm['tiles'][1][1] = {'kind': 'PASTURE', 'animal': 'COW', 'fed_today': True,
                          'cared_today': True, 'fertilizer_available': True,
                          'yield_units': 0, 'placed_day': 0, 'consecutive_unfed': 0,
                          'pending_care_bonus': 1}
    obs = {'player': 0, 'step': 23, 'farms': [farm, deepcopy(farm)],
           'private': {'shed': {}, 'inventories': [{}], 'seeds': {'WHEAT': 1}}}
    action = {'farmer': ['HARVEST'], 'hands': [], 'market': []}
    return action, obs, dict(HELPER.STANDARD)


class ObserverContract(unittest.TestCase):
    def setUp(self):
        self.a, self.obs, self.cfg = fixture()

    def test_positive_is_shadow_only(self):
        before = deepcopy((self.a, self.obs, self.cfg))
        result = audit.probe_decision(HELPER, self.a, self.obs, self.cfg)
        self.assertTrue(result['changed'])
        self.assertEqual(result['proposal']['farmer'], ['COLLECT_FERTILIZER'])
        self.assertEqual((self.a, self.obs, self.cfg), before)
        self.assertIsNone(sys.gettrace())

    def test_actual_guard_return_line(self):
        for step in (0, 22, 24, 696, 719):
            with self.subTest(step=step):
                self.obs['step'] = step
                result = audit.probe_decision(HELPER, self.a, self.obs, self.cfg)
                self.assertFalse(result['changed'])
                self.assertEqual(result['helper_return_line'], 81)

    def test_full_vector_surplus_preserved_and_rejected(self):
        self.a['hands'] = [['WEST']]
        result = audit.probe_decision(HELPER, self.a, self.obs, self.cfg)
        self.assertFalse(result['changed'])
        self.assertEqual(self.a['hands'], [['WEST']])
        facts = audit.raw_action_facts(self.a, self.obs)
        self.assertFalse(facts['complete_vectors'])
        self.assertEqual(facts['surplus_hand_rows'], [['WEST']])

    def test_input_hash_binds_raw_suffix(self):
        one = audit.raw_action_facts(self.a, self.obs)
        self.a['hands'] = [['PASS']]
        two = audit.raw_action_facts(self.a, self.obs)
        self.assertNotEqual(one['input_sha256'], two['input_sha256'])

    def test_potential_ghost_plant_blocker(self):
        self.a.update(farmer=['PLANT', 'WHEAT'], hands=[['PLANT', 'WHEAT']])
        facts = audit.raw_action_facts(self.a, self.obs)
        self.assertEqual(facts['potential_surplus_plant_blockers'],
                         [{'crop': 'WHEAT', 'live_demand': 1, 'raw_demand': 2, 'available': 1}])

    def test_no_live_plant_no_blocker(self):
        self.a['hands'] = [['PLANT', 'WHEAT']]
        self.assertEqual(audit.raw_action_facts(self.a, self.obs)['potential_surplus_plant_blockers'], [])

    def test_existing_live_insufficiency_not_ghost_attributed(self):
        self.a.update(farmer=['PLANT', 'WHEAT'], hands=[['PLANT', 'WHEAT']])
        self.obs['private']['seeds']['WHEAT'] = 0
        self.assertEqual(audit.raw_action_facts(self.a, self.obs)['potential_surplus_plant_blockers'], [])

    def test_cross_crop_demand_not_conflated(self):
        self.a.update(farmer=['PLANT', 'WHEAT'], hands=[['PLANT', 'CARROT']])
        self.assertEqual(audit.raw_action_facts(self.a, self.obs)['potential_surplus_plant_blockers'], [])

    def test_capacity_veto_not_relaxed(self):
        self.obs['private']['shed']['MILK'] = 100
        self.assertFalse(audit.probe_decision(HELPER, self.a, self.obs, self.cfg)['changed'])

    def test_completed_service_extension_not_enabled(self):
        for op in ('CARE', 'FEED'):
            with self.subTest(op=op):
                self.a['farmer'] = [op]
                self.assertFalse(audit.probe_decision(HELPER, self.a, self.obs, self.cfg)['changed'])

    def test_trace_hook_preserved(self):
        def other(frame, event, arg): return other
        sys.settrace(other)
        try:
            with self.assertRaises(RuntimeError): audit.probe_decision(HELPER, self.a, self.obs, self.cfg)
            self.assertIs(sys.gettrace(), other)
        finally:
            sys.settrace(None)

    def test_exception_restores_trace(self):
        def broken(*args, **kwargs): raise LookupError('expected')
        module = types.SimpleNamespace(apply_cow_fert_salvage=broken)
        with self.assertRaises(LookupError): audit.probe_decision(module, self.a, self.obs, self.cfg)
        self.assertIsNone(sys.gettrace())

    def test_mutating_helper_rejected_without_parent_damage(self):
        def broken(a, obs, cfg, *, enabled):
            obs['step'] = 0
            return a
        module = types.SimpleNamespace(apply_cow_fert_salvage=broken)
        with self.assertRaises(ValueError): audit.probe_decision(module, self.a, self.obs, self.cfg)
        self.assertEqual(self.obs['step'], 23)

    def test_off_copy_rejected(self):
        def broken(a, obs, cfg, *, enabled): return deepcopy(a)
        module = types.SimpleNamespace(apply_cow_fert_salvage=broken)
        with self.assertRaises(ValueError): audit.probe_decision(module, self.a, self.obs, self.cfg)

    def test_off_mutation_rejected(self):
        def broken(a, obs, cfg, *, enabled):
            if not enabled: cfg['shedCapacity'] = 1000
            return a
        with self.assertRaises(ValueError):
            audit.probe_decision(types.SimpleNamespace(apply_cow_fert_salvage=broken), self.a, self.obs, self.cfg)
        self.assertEqual(self.cfg['shedCapacity'], 100)

    def test_helper_source_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'helper.py'
            path.write_text('def different(): pass\n')
            with self.assertRaises(ValueError): audit.verify_helper(path)
        self.assertEqual(audit.verify_helper(Path(HELPER.__file__))['git_blob'], audit.HELPER_BLOB)

    def test_bad_observation_rejected(self):
        for seat in (-1, 2, True, '0', None):
            with self.subTest(seat=seat):
                self.obs['player'] = seat
                with self.assertRaises(ValueError): audit.raw_action_facts(self.a, self.obs)

    def test_non_string_crop_rejected_not_normalized(self):
        self.a['farmer'] = ['PLANT', ['WHEAT']]
        with self.assertRaises(ValueError): audit.raw_action_facts(self.a, self.obs)


class OfficialActorSemantics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if PARENT is None:
            raise unittest.SkipTest('Official engine checks require explicit --parent')

    def initialized(self, seat, seed, step=0):
        cfg = LOADER.Struct({k: v.get('default') if isinstance(v, dict) else v
                             for k, v in ENGINE.specification['configuration'].items()})
        cfg.seed = seed
        env = LOADER.Struct(configuration=cfg, done=False, info={})
        state = [LOADER.Struct(observation=LOADER.Struct(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
        ENGINE.interpreter(state, env)
        for s in state: s.observation.step = step
        farm = state[0].observation.farms[seat]
        farm['farmer'] = [1, 1]
        farm['hands'] = []
        farm['tiles'][1][1] = None
        state[seat].observation.private['seeds'] = {'WHEAT': 1}
        state[seat].observation.private['inventories'] = [{}]
        return state, env

    def test_raw_nonexistent_plant_blocks_real_actor_both_seats(self):
        for seat in (0, 1):
            for seed in (7, 17, 101):
                for step in (0, 23):
                    with self.subTest(seat=seat, seed=seed, step=step):
                        raw, env = self.initialized(seat, seed, step)
                        raw[seat].action = {'farmer': ['PLANT', 'WHEAT'], 'hands': [['PLANT', 'WHEAT']], 'market': []}
                        trimmed, other_env = deepcopy((raw, env))
                        trimmed[seat].action['hands'] = []
                        facts = audit.raw_action_facts(raw[seat].action, raw[seat].observation)
                        self.assertEqual(len(facts['potential_surplus_plant_blockers']), 1)
                        ENGINE.interpreter(raw, env)
                        ENGINE.interpreter(trimmed, other_env)
                        # At hour 23 the planted-but-unwatered crop can immediately
                        # wither, and the empty control can grow a random weed.
                        # Seed consumption still exposes the raw atomic veto.
                        if step != 23:
                            self.assertIsNone(raw[0].observation.farms[seat]['tiles'][1][1])
                            self.assertEqual(trimmed[0].observation.farms[seat]['tiles'][1][1]['crop'], 'WHEAT')
                        self.assertEqual(raw[seat].observation.private['seeds']['WHEAT'], 1)
                        self.assertEqual(trimmed[seat].observation.private['seeds']['WHEAT'], 0)

    def test_raw_nonplant_surplus_is_accepted_and_noop(self):
        for seat in (0, 1):
            for op in ('WEST', 'PASS', 'COLLECT_FERTILIZER', 'HARVEST', 'HIRE'):
                with self.subTest(seat=seat, op=op):
                    raw, env = self.initialized(seat, 101)
                    raw[seat].action = {'farmer': ['PLANT', 'WHEAT'], 'hands': [[op]], 'market': []}
                    trimmed, other_env = deepcopy((raw, env))
                    trimmed[seat].action['hands'] = []
                    ENGINE.interpreter(raw, env)
                    ENGINE.interpreter(trimmed, other_env)
                    self.assertEqual([s.observation for s in raw], [s.observation for s in trimmed])
                    self.assertEqual([s.reward for s in raw], [s.reward for s in trimmed])

    def test_whole_parent_source_map_authenticated(self):
        self.assertEqual(audit.verify_parent(PARENT)['members_verified'], 109)

    def test_old_artifact_source_map_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'SOURCE.json').write_text('{}')
            with self.assertRaises(ValueError): audit.verify_parent(tmp)


def main():
    global PARENT, ENGINE, LOADER, HELPER
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent', type=Path, required=True)
    args, rest = parser.parse_known_args()
    helper_path = Path(__file__).with_name('r04_cow_fert_salvage.py')
    audit.verify_helper(helper_path)
    HELPER = load(helper_path, '_cf1_original_for_contract')
    if args.parent:
        PARENT = args.parent.resolve()
        audit.verify_parent(PARENT)
        LOADER = load(PARENT/'checks/reference/evaluator/loader.py', '_cf1_contract_loader')
        ENGINE, _ = LOADER.get_engine(PARENT/'checks/reference/engine')
    unittest.main(argv=[sys.argv[0], *rest])


if __name__ == '__main__': main()
