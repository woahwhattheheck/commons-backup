# SPDX-License-Identifier: Apache-2.0
"""Source-bound W2 checks against the complete pinned interpreter (offline).

TITAN_NATIVE_ROOT=/path/to/extracted/b567 python -B check_dead_feed_care.py
W2_SOURCE=/path/to/candidate.py permits the same assertions against source faults.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import itertools
import json
import os
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
PINS = {
    'evaluator/evaluate.py': '1fb6b655bb4ca1e1684be165a8ef513e2e6c2325',
    'evaluator/loader.py': '23948e10cfc3d32f46c9abb1321b0d8fc8db21d5',
    'engine/kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
    'engine/kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
    'engine/utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
}
RECEIPT = {'transitions': 0, 'pairs': 0, 'rewrites': 0, 'witnesses': []}


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


SOURCE = Path(os.environ.get('W2_SOURCE', HERE / 'dead_feed_care.py')).resolve()
lane = load(SOURCE, 'w2_candidate_under_test')


def action(rows, market=()):
    return {'farmer': list(rows[0]), 'hands': [list(row) for row in rows[1:]],
            'market': copy.deepcopy(list(market))}


class W2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(os.environ['TITAN_NATIVE_ROOT']).resolve() / 'checks/reference'
        for path, expected in PINS.items():
            actual = blob((root / path).read_bytes())
            if actual != expected:
                raise ValueError(f'Untrusted reference {path}: {actual} != {expected}')
        cls.ev = load(root / 'evaluator/evaluate.py', 'w2_reference_evaluator')
        cls.engine, _ = cls.ev.get_engine(root / 'engine', root / 'evaluator/loader.py')

    def fixture(self, *, species='GOOSE', seat=0, fed=False, cared=False,
                wheat=(1, 0), step=240, placed=0, units=0, bonus=0,
                rows=(('FEED',), ('FEED',))):
        e, S = self.engine, self.ev.Struct
        cfg = S({k: v.get('default') if isinstance(v, dict) else v
                 for k, v in e.specification['configuration'].items()})
        cfg.weedSpawnChance = 0
        cfg.townShopUnlockInterval = 100
        farms = [e._new_farm(10, 1000) for _ in range(2)]
        farm = farms[seat]
        farm['farmer'], farm['hands'] = [4, 4], [[4, 4] for _ in rows[1:]]
        farm['tiles'][4][4] = {
            'kind': e.ANIMALS[species]['structure'], 'animal': species,
            'placed_day': placed, 'yield_units': units, 'consecutive_unfed': 0,
            'fed_today': fed, 'cared_today': cared, 'fertilizer_available': False,
            'pending_care_bonus': bonus}
        market, town = e._new_market(), e._new_town()
        state = []
        for player in range(2):
            private = e._new_private()
            if player == seat:
                private['inventories'] = [{'WHEAT': n} if n else {} for n in wheat]
            obs = S(player=player, step=step, day=step//24, hour=step%24,
                    farms=farms, private=private, market=market, town=town)
            state.append(S(observation=obs, action=action(rows if player == seat else [('PASS',)]),
                           status='ACTIVE', reward=0))
        return state, S(configuration=cfg, done=False, info={'seed': 17092026})

    def pair(self, state, env, seat=0):
        before = copy.deepcopy((state, env))
        parent = state[seat].action
        plan = lane.plan_dead_feed_care(parent, state[seat].observation, env.configuration)
        candidate = lane.apply_dead_feed_care(parent, state[seat].observation,
                                              env.configuration, enabled=True)
        self.assertTrue((state, env) == before, 'planner/apply mutated inputs')
        self.assertEqual(candidate['market'], parent['market'], 'market custody')
        left, le = copy.deepcopy((state, env))
        right, re = copy.deepcopy((state, env))
        right[seat].action = candidate
        self.engine.interpreter(left, le)
        self.engine.interpreter(right, re)
        RECEIPT['transitions'] += 2
        RECEIPT['pairs'] += 1
        RECEIPT['rewrites'] += len(plan)
        # Full public/private state and env, except the sole allowed CARE flag.
        expected = copy.deepcopy(left)
        for change in plan:
            x, y = change['site']
            expected[0].observation.farms[seat]['tiles'][y][x]['cared_today'] = True
        for target, actual in zip(expected, right):
            target.action = actual.action
        self.assertTrue((expected, le) == (right, re), 'unauthorized full-engine difference')
        return plan, left, right

    def test_ordered_success_all_species_seats(self):
        for species, seat in itertools.product(lane.ANIMALS, (0, 1)):
            state, env = self.fixture(species=species, seat=seat)
            plan, left, right = self.pair(state, env, seat)
            self.assertEqual([(p['actor'], p['reason']) for p in plan], [(1, 'ordered_feed')])
            self.assertEqual(left[seat].observation.private, right[seat].observation.private)
            RECEIPT['witnesses'].append({'species': species, 'seat': seat, 'plan': plan})

    def test_observed_fed_zero_wheat(self):
        for species in lane.ANIMALS:
            state, env = self.fixture(species=species, fed=True, wheat=(0, 0))
            plan, _, _ = self.pair(state, env)
            self.assertEqual([(p['actor'], p['reason']) for p in plan], [(0, 'observed_fed')])

    def test_unfunded_first_feed_is_not_success(self):
        state, env = self.fixture(wheat=(0, 1))
        plan, _, _ = self.pair(state, env)
        self.assertEqual(plan, [])
        state, env = self.fixture(wheat=(0, 1, 0), rows=[['FEED']]*3)
        plan, _, _ = self.pair(state, env)
        self.assertEqual([p['actor'] for p in plan], [2])

    def test_no_wheat_no_rewrite(self):
        state, env = self.fixture(wheat=(0, 0))
        plan, _, _ = self.pair(state, env)
        self.assertEqual(plan, [])

    def test_one_rewrite_per_site(self):
        state, env = self.fixture(wheat=(1, 1, 1, 1), rows=[['FEED']]*4)
        plan, _, _ = self.pair(state, env)
        self.assertEqual([p['actor'] for p in plan], [1])

    def test_authored_care_any_order_subsumes(self):
        for rows in ([['CARE'], ['FEED']], [['FEED'], ['FEED'], ['CARE']],
                     [['FEED'], ['CARE', 'unused'], ['FEED']]):
            state, env = self.fixture(fed=True, rows=rows, wheat=[1]*len(rows))
            plan, _, _ = self.pair(state, env)
            self.assertEqual(plan, [])

    def test_cared_tile_no_rewrite(self):
        state, env = self.fixture(fed=True, cared=True)
        self.assertEqual(self.pair(state, env)[0], [])

    def test_only_literal_target_but_real_prefix_extras(self):
        state, env = self.fixture(rows=[['FEED', 'unused'], ['FEED']])
        self.assertEqual([p['actor'] for p in self.pair(state, env)[0]], [1])
        state, env = self.fixture(fed=True, rows=[['PASS'], ['FEED', 'unused']])
        self.assertEqual(self.pair(state, env)[0], [])

    def test_different_positions_not_shared(self):
        state, env = self.fixture()
        state[0].observation.farms[0]['hands'][0] = [3, 4]
        self.assertEqual(self.pair(state, env)[0], [])

    def test_distinct_animals_are_independent(self):
        state, env = self.fixture(fed=True)
        farm = state[0].observation.farms[0]
        farm['hands'][0] = [3, 4]
        farm['tiles'][4][3] = copy.deepcopy(farm['tiles'][4][4])
        self.assertEqual(len(self.pair(state, env)[0]), 2)

    def test_movement_does_not_feed_later_actor(self):
        state, env = self.fixture(rows=[['NORTH'], ['FEED']], wheat=(1, 1))
        self.assertEqual(self.pair(state, env)[0], [])

    def test_missing_actor_bag_is_empty(self):
        state, env = self.fixture(wheat=())
        self.assertEqual(self.pair(state, env)[0], [])
        state, env = self.fixture(wheat=(1,))
        self.assertEqual([p['actor'] for p in self.pair(state, env)[0]], [1])

    def test_pre_maturity_bank_not_interval_bounded(self):
        state, env = self.fixture(species='COW', step=6*24, bonus=5, fed=True)
        self.assertEqual(len(self.pair(state, env)[0]), 1)

    def test_last_useful_production_boundary(self):
        # EOD day28 produces day29; terminal arrives before EOD day29.
        for species, day, expected in [('GOOSE', 27, 29), ('GOOSE', 28, None),
                ('COW', 26, 28), ('COW', 27, None),
                ('SHEEP', 25, 27), ('SHEEP', 26, None)]:
            state, env = self.fixture(species=species, step=day*24, fed=True)
            plan = self.pair(state, env)[0]
            self.assertEqual(plan[0]['first_usable_day'] if plan else None, expected)

    def test_placement_shifts_production_calendar(self):
        state, env = self.fixture(species='COW', placed=1, step=27*24, fed=True)
        plan = self.pair(state, env)[0]
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]['first_usable_day'], 29)

    def test_no_same_night_bonus(self):
        for species, seat in itertools.product(lane.ANIMALS, (0, 1)):
            first = self.engine.ANIMALS[species]['first_yield_day']
            state, env = self.fixture(species=species, seat=seat, step=first*24-1)
            right, re = copy.deepcopy((state, env))
            right[seat].action = lane.apply_dead_feed_care(state[seat].action,
                state[seat].observation, env.configuration, enabled=True)
            self.engine.interpreter(state, env)
            self.engine.interpreter(right, re)
            RECEIPT['transitions'] += 2
            left_tile = state[0].observation.farms[seat]['tiles'][4][4]
            right_tile = right[0].observation.farms[seat]['tiles'][4][4]
            self.assertEqual(left_tile['yield_units'], right_tile['yield_units'])
            self.assertEqual(right_tile['pending_care_bonus']-left_tile['pending_care_bonus'], 1)
            self.assertEqual(state[seat].observation.private, right[seat].observation.private)

    def test_counterfactual_corpus(self):
        for species, seat, fed, cared, w0, w1, mode in itertools.product(
                lane.ANIMALS, (0, 1), (False, True), (False, True), (0, 1), (0, 1),
                ('same', 'different', 'priorcare', 'latercare')):
            rows = [['CARE'] if mode == 'priorcare' else ['FEED'], ['FEED']]
            if mode == 'latercare':
                rows.append(['CARE'])
            state, env = self.fixture(species=species, seat=seat, fed=fed, cared=cared,
                                      wheat=(w0, w1, 0), rows=rows)
            if mode == 'different':
                state[0].observation.farms[seat]['hands'][0] = [3, 4]
            plan, _, _ = self.pair(state, env, seat)
            expected = int(not cared and mode not in ('priorcare', 'latercare')
                           and (fed or (mode == 'same' and w0 == 1)))
            self.assertEqual(len(plan), expected)

    def test_disabled_and_nomatch_identity(self):
        state, env = self.fixture()
        parent, obs = state[0].action, state[0].observation
        self.assertIs(lane.apply_dead_feed_care(parent, obs, env.configuration), parent)
        obs.farms[0]['tiles'][4][4]['cared_today'] = True
        self.assertIs(lane.apply_dead_feed_care(parent, obs, env.configuration, enabled=True), parent)

    def test_copy_isolation_and_plan_purity(self):
        state, env = self.fixture()
        parent, obs = state[0].action, state[0].observation
        parent['market'] = [['SELL', 'WOOL', 1]]
        count = dict(lane.telemetry)
        lane.plan_dead_feed_care(parent, obs, env.configuration)
        self.assertEqual(dict(lane.telemetry), count)
        out = lane.apply_dead_feed_care(parent, obs, env.configuration, enabled=True)
        out['market'][0][2] = 9
        out['farmer'].append('changed')
        self.assertEqual(parent, action([['FEED'], ['FEED']], [['SELL', 'WOOL', 1]]))

    def test_foreign_config_failclosed(self):
        for key in ('boardSize', 'turnsPerDay', 'episodeSteps'):
            for value in (None, True, '720', 721):
                state, env = self.fixture()
                env.configuration[key] = value
                self.assertIs(lane.apply_dead_feed_care(state[0].action, state[0].observation,
                    env.configuration, enabled=True), state[0].action)

    def test_non_json_aliases_failclosed(self):
        for kind in ('inventory', 'shed', 'tile'):
            state, env = self.fixture(fed=True)
            obs, private = state[0].observation, state[0].observation.private
            if kind == 'inventory':
                private['inventories'][1] = private['inventories'][0]
            elif kind == 'shed':
                private['inventories'][0] = private['shed']
            else:
                obs.farms[0]['tiles'][4][3] = obs.farms[0]['tiles'][4][4]
            self.assertEqual(lane.plan_dead_feed_care(state[0].action, obs, env.configuration), [])

    def test_phantom_missing_and_malformed_actor_rows(self):
        for rows in ([], [['FEED'], ['FEED']], [None], [[]], [['FEED'], ['PLANT', 'WHEAT']]):
            state, env = self.fixture(fed=True)
            state[0].action['hands'] = rows
            self.assertIs(lane.apply_dead_feed_care(state[0].action, state[0].observation,
                env.configuration, enabled=True), state[0].action)

    def test_bad_animal_state_failclosed(self):
        bad = {'animal': [], 'fed_today': 1, 'cared_today': None, 'placed_day': True,
               'yield_units': 500, 'consecutive_unfed': 2, 'pending_care_bonus': -1}
        for key, value in bad.items():
            state, env = self.fixture(fed=True)
            state[0].observation.farms[0]['tiles'][4][4][key] = value
            self.assertEqual(lane.plan_dead_feed_care(state[0].action,
                state[0].observation, env.configuration), [])


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(W2))
    RECEIPT.update(source_blob=blob(SOURCE.read_bytes()), tests=result.testsRun,
                   failures=len(result.failures), errors=len(result.errors),
                   skips=len(result.skipped), optimized=not __debug__, pins=PINS)
    print('W2_RECEIPT=' + json.dumps(RECEIPT, sort_keys=True))
    sys.exit(not result.wasSuccessful())
