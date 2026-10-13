# SPDX-License-Identifier: Apache-2.0
"""Driver contracts; requires the authenticated package, not network access."""
import argparse
import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import run_natural_engagement as run

ROOT = None
HELPER = Path(__file__).with_name('r04_cow_fert_salvage.py')


def fixture():
    tile = {'kind': 'PASTURE', 'animal': 'COW', 'fed_today': True,
            'cared_today': True, 'fertilizer_available': True, 'yield_units': 0,
            'placed_day': 0, 'consecutive_unfed': 0, 'pending_care_bonus': 0}
    tiles = [[None for _ in range(10)] for _ in range(10)]
    tiles[2][2] = tile
    farm = {'farmer': [2, 2], 'hands': [], 'tiles': tiles}
    obs = {'step': 23, 'player': 0, 'farms': [farm, copy.deepcopy(farm)],
           'private': {'shed': {}, 'inventories': [{}]}}
    action = {'farmer': ['HARVEST'], 'hands': [], 'market': []}
    return obs, action


def result(seed=1, seat=0):
    return {'seed': seed, 'seat': seat, 'source_manifest_sha256': run.SOURCE_SHA256,
            'helper_git_blob': run.HELPER_BLOB, 'opponent': 'official_starter',
            'mode': 'shadow_only_parent_actions_submitted', 'complete': True,
            'resolved_episode_seed': seed, 'agent_configuration_seed': None,
            'counts': {'callbacks': 719}, 'return_lines': {}, 'parent_statuses': {'completed': 719},
            'final_status': ['DONE', 'DONE'], 'final_step': 718,
            'own_cash': 20, 'rival_cash': 10, 'margin': 10, 'action_tape_sha256': 'a'*64}


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'runtime'
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns('__pycache__'))
        self.helper = Path(self.temp.name) / 'helper.py'
        shutil.copy2(HELPER, self.helper)

    def tearDown(self):
        self.temp.cleanup()

    def test_all_109_members_verified(self):
        auth = run.authenticate(self.root, self.helper)
        self.assertEqual(auth['runtime_members_checked'], 109)
        self.assertEqual(auth['members']['titan_runtime.py']['git_blob'],
                         'b952c9c228ecbde592bf3d2df01638677abb0d24')
        self.assertEqual(auth['members']['early_capital.py']['git_blob'],
                         '1161859ac5af617eca65aec3f732b5c1396cad37')

    def test_runtime_pin_alone_does_not_accept_old_dependency(self):
        (self.root / 'early_capital.py').write_text('# old source with same titan_runtime\n')
        with self.assertRaisesRegex(ValueError, 'member mismatch: early_capital'):
            run.authenticate(self.root, self.helper)

    def test_manifest_drift(self):
        with (self.root / 'SOURCE.json').open('a') as stream:
            stream.write('\n')
        with self.assertRaisesRegex(ValueError, 'manifest'):
            run.authenticate(self.root, self.helper)

    def test_helper_drift(self):
        with self.helper.open('a') as stream:
            stream.write('\n')
        with self.assertRaisesRegex(ValueError, 'canonical donor'):
            run.authenticate(self.root, self.helper)

    def test_missing_dependency(self):
        (self.root / 'mechanics.py').unlink()
        with self.assertRaises(OSError):
            run.authenticate(self.root, self.helper)

    def test_undeclared_python(self):
        (self.root / 'extra.py').write_text('raise RuntimeError("not allowed")')
        with self.assertRaisesRegex(ValueError, 'undeclared Python'):
            run.authenticate(self.root, self.helper)

    def test_member_symlink(self):
        target = self.root / 'mechanics.py'
        outside = Path(self.temp.name) / 'mechanics.py'
        target.rename(outside)
        target.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            run.authenticate(self.root, self.helper)

    def test_wrong_source_cli_does_not_create_output(self):
        (self.root / 'main.py').write_text('# altered')
        output = Path(self.temp.name) / 'evidence'
        self.assertEqual(run.main(['--runtime', str(self.root), '--output', str(output)]), 2)
        self.assertFalse(output.exists())

    def test_existing_evidence_is_not_overwritten(self):
        output = Path(self.temp.name) / 'evidence'
        output.mkdir(); (output / 'sentinel').write_text('preserve')
        self.assertEqual(run.main(['--runtime', str(self.root), '--output', str(output)]), 2)
        self.assertEqual((output / 'sentinel').read_text(), 'preserve')


class ShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helper = run.load_at('_cf1_test_helper', HELPER)

    def test_actual_positive_helper_is_not_submitted_or_mutating(self):
        obs, action = fixture(); cfg = self.helper.STANDARD.copy()
        before = copy.deepcopy([obs, action, cfg])
        out, line = run.shadow(self.helper, action, obs, cfg)
        self.assertIsNot(out, action)
        self.assertEqual(out['farmer'], ['COLLECT_FERTILIZER'])
        self.assertEqual([obs, action, cfg], before)
        self.assertIsInstance(line, int)

    def test_completed_service_remains_explicitly_off(self):
        obs, action = fixture(); action['farmer'] = ['CARE']
        cfg = self.helper.STANDARD.copy()
        self.assertIsNot(self.helper.apply_cow_fert_salvage(
            action, obs, cfg, enabled=True, completed_service=True), action)
        transformed, _ = run.shadow(self.helper, action, obs, cfg)
        self.assertIs(transformed, action)

    def test_no_match_preserves_identity(self):
        obs, action = fixture(); obs['step'] = 22
        out, _ = run.shadow(self.helper, action, obs, self.helper.STANDARD.copy())
        self.assertIs(out, action)

    def test_profile_is_restored(self):
        obs, action = fixture(); old = sys.getprofile()
        def marker(*args):
            pass
        try:
            sys.setprofile(marker)
            run.shadow(self.helper, action, obs, self.helper.STANDARD.copy())
            self.assertIs(sys.getprofile(), marker)
        finally:
            sys.setprofile(old)

    def test_bad_off_identity_rejected(self):
        def broken(action, obs, cfg, *, enabled=False, completed_service=False):
            return copy.deepcopy(action)
        with self.assertRaisesRegex(ValueError, 'default-OFF'):
            run.shadow(SimpleNamespace(apply_cow_fert_salvage=broken), {}, {}, {})

    def test_shadow_mutation_rejected(self):
        def broken(action, obs, cfg, *, enabled=False, completed_service=False):
            if enabled:
                action['bad'] = True
            return action
        with self.assertRaisesRegex(ValueError, 'mutated'):
            run.shadow(SimpleNamespace(apply_cow_fert_salvage=broken), {}, {}, {})

    def test_extra_raw_plant_is_counted_not_truncated(self):
        obs, action = fixture()
        action['hands'] = [['PLANT', 'WHEAT']]
        before = copy.deepcopy(action)
        counts = run.observation_census(self.helper, obs, action)
        self.assertEqual(counts['extra_hand_rows'], 1)
        self.assertEqual(counts['extra_hand_plant_rows'], 1)
        self.assertEqual(action, before)


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.plan = {'cells': [{'seed': 1, 'seat': 0}, {'seed': 1, 'seat': 1}]}
        self.rows = [result(1, 0), result(1, 1)]

    def test_complete_zero_parks_only_this_panel(self):
        out = run.reduce_panel(self.plan, self.rows)
        self.assertEqual(out['verdict'], 'PARK_ON_THIS_PANEL')
        self.assertEqual(out['counts']['callbacks'], 1438)

    def test_positive_requires_economics(self):
        self.rows[0]['counts']['shadow_activations'] = 1
        self.assertEqual(run.reduce_panel(self.plan, self.rows)['verdict'], 'ENGAGED_NEEDS_PAIRED_ECONOMICS')

    def test_missing_is_not_zero(self):
        self.assertEqual(run.reduce_panel(self.plan, self.rows[:1])['verdict'], 'INCOMPLETE')

    def test_duplicate_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            run.reduce_panel(self.plan, self.rows + self.rows[:1])

    def test_unexpected_rejected(self):
        self.rows[0]['seed'] = 2
        with self.assertRaisesRegex(ValueError, 'unexpected'):
            run.reduce_panel(self.plan, self.rows)

    def test_wrong_source(self):
        self.rows[0]['source_manifest_sha256'] = 'old'
        self.assertFalse(run.reduce_panel(self.plan, self.rows)['panel_complete'])

    def test_seed_leak_blocks_completion(self):
        self.rows[0]['agent_configuration_seed'] = 1
        self.assertFalse(run.reduce_panel(self.plan, self.rows)['panel_complete'])

    def test_resolved_wrong_seed_blocks_completion(self):
        self.rows[0]['resolved_episode_seed'] = 2
        self.assertFalse(run.reduce_panel(self.plan, self.rows)['panel_complete'])

    def test_short_game(self):
        self.rows[0]['counts']['callbacks'] = 718
        self.assertFalse(run.reduce_panel(self.plan, self.rows)['panel_complete'])

    def test_unfinished_state(self):
        self.rows[0]['final_status'][1] = 'ACTIVE'
        self.assertFalse(run.reduce_panel(self.plan, self.rows)['panel_complete'])

    def test_failure_retained(self):
        self.rows[0] = {'seed': 1, 'seat': 0, 'error': 'timeout'}
        out = run.reduce_panel(self.plan, self.rows)
        self.assertEqual(out['verdict'], 'INCOMPLETE')
        self.assertEqual(out['errors'][0]['error'], 'timeout')

    def test_empty_plan_rejected(self):
        with self.assertRaisesRegex(ValueError, 'empty'):
            run.reduce_panel({'cells': []}, [])


class OfficialEngineContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run.authenticate(ROOT, HELPER)
        cls.loader = run.load_at('_cf1_contract_loader', ROOT / 'checks/reference/evaluator/loader.py')
        cls.engine, _ = cls.loader.get_engine(ROOT / 'checks/reference/engine')

    def world(self, seat):
        L = self.loader
        cfg = L.Struct({key: value.get('default') if isinstance(value, dict) else value
                        for key, value in self.engine.specification['configuration'].items()})
        cfg.seed = 9172031
        env = L.Struct(configuration=cfg, done=False, info={})
        state = [L.Struct(observation=L.Struct(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
        self.engine.interpreter(state, env)
        self.assertEqual(env.info['seed'], 9172031)
        self.assertIsNone(cfg.seed)
        for s in state:
            s.observation.step = 0
            s.action = {'farmer': ['PASS'], 'hands': [], 'market': []}
        farm = state[0].observation.farms[seat]
        x, y = farm['farmer']; farm['tiles'][y][x] = None
        state[seat].observation.private['seeds'] = {'WHEAT': 1}
        return state, env, x, y

    def test_extra_raw_plant_changes_atomic_demand_both_seats(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                state, env, x, y = self.world(seat)
                state[seat].action = {'farmer': ['PLANT', 'WHEAT'],
                                     'hands': [['PLANT', 'WHEAT']], 'market': []}
                baseline = copy.deepcopy(state); base_env = copy.deepcopy(env)
                baseline[seat].action['hands'] = []
                self.engine.interpreter(state, env)
                self.engine.interpreter(baseline, base_env)
                self.assertIsNone(state[0].observation.farms[seat]['tiles'][y][x])
                self.assertEqual(baseline[0].observation.farms[seat]['tiles'][y][x]['crop'], 'WHEAT')

    def test_nonplant_extra_hand_is_accepted_both_seats(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                state, env, x, y = self.world(seat)
                state[seat].action = {'farmer': ['PLANT', 'WHEAT'],
                                     'hands': [['HARVEST']], 'market': []}
                self.engine.interpreter(state, env)
                self.assertEqual(state[0].observation.farms[seat]['tiles'][y][x]['crop'], 'WHEAT')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    args, rest = parser.parse_known_args()
    ROOT = args.runtime.resolve()
    unittest.main(argv=[sys.argv[0], *rest])
