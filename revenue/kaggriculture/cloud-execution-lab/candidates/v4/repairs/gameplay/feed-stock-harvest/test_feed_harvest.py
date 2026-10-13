# SPDX-License-Identifier: Apache-2.0
"""Pinned native feed repair + full official-interpreter trajectories.

TITAN_FEED_RUNTIME points to a materialized cloud-execution-lab runtime root.
Default is the canonical repository root relative to this repair package.
TITAN_FEED_PREDECESSOR=1 runs the same acceptance tests against the old helper;
it must FAIL. All fixtures are constructed, not a hosted-game corpus.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest

from repair_feed_harvest import repair_source, function_span, REASON

ROOT = (Path(os.environ['TITAN_FEED_RUNTIME']) if 'TITAN_FEED_RUNTIME' in os.environ
        else Path(__file__).resolve().parents[5])
PINS = {
    'operating_stock.py': '781aa90da0d85d0ba23c665e29d6087d182c085e',
    'mechanics.py': '044a4f9c0a4a44dde10ada57563238bcaf82075d',
    'titan_runtime.py': 'b952c9c228ecbde592bf3d2df01638677abb0d24',
    'checks/test_feed_stock.py': 'ebdefd88e59c0a0c3fce8514edf792e92664ef5d',
    'checks/test_engine_semantics.py': '5fc139742d1fb8cc757e9bf58c033794b7f8ec5f',
    'checks/reference/evaluator/evaluate.py': '1fb6b655bb4ca1e1684be165a8ef513e2e6c2325',
    'checks/reference/evaluator/loader.py': '23948e10cfc3d32f46c9abb1321b0d8fc8db21d5',
    'checks/reference/engine/kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
    'checks/reference/engine/kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
    'checks/reference/engine/utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
}


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def check_inputs(root):
    for rel, expected in PINS.items():
        actual = git_blob((root / rel).read_bytes())
        if actual != expected:
            raise ValueError(f'input mismatch: {rel}: {actual} != {expected}')


def load_text(name, source, filename):
    module = ModuleType(name)
    module.__file__ = str(filename)
    exec(compile(source, str(filename), 'exec'), module.__dict__)
    return module


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_inputs(ROOT)  # Missing/stale inputs fail before any candidate import.
sys.path.insert(0, str(ROOT))
ORIGINAL_TEXT = (ROOT / 'operating_stock.py').read_text(encoding='utf-8')
REPAIRED_TEXT = repair_source(ORIGINAL_TEXT)
ORIGINAL = load_text('feed_harvest_original', ORIGINAL_TEXT, ROOT / 'operating_stock.py')
IS_PREDECESSOR = os.environ.get('TITAN_FEED_PREDECESSOR') == '1'
CANDIDATE = load_text('operating_stock', ORIGINAL_TEXT if IS_PREDECESSOR else REPAIRED_TEXT,
                      ROOT / 'operating_stock.py')
sys.modules['operating_stock'] = CANDIDATE
import mechanics as m
from titan_runtime import TitanAgent, Features
BASELINE = load_file('feed_harvest_existing_tests', ROOT / 'checks/test_feed_stock.py')
ENGINE_TEST = load_file('feed_harvest_engine_fixture', ROOT / 'checks/test_engine_semantics.py')
ENGINE_TEST.EngineSemantics.setUpClass()
ORACLE = ENGINE_TEST.EngineSemantics()
ENGINE = ORACLE.engine
RESULTS = {'scope': 'constructed native-module/full-interpreter trajectories only',
           'predecessor_mode': IS_PREDECESSOR, 'pins': PINS,
           'interpreter_calls': 0, 'grid_cells': 0, 'mutants_rejected': [],
           'witnesses': [], 'production_changed': False, 'natural_engagement_measured': False}


def blank(hands=2):
    return {'farmer': ['PASS'], 'hands': [['PASS'] for _ in range(hands)], 'market': []}


def set_unit(action, actor, unit):
    if actor == 0:
        action['farmer'] = list(unit)
    else:
        action['hands'][actor - 1] = list(unit)


def scenario(seat=0, actor=0, spawn=(4, 4), timing='before', animal='COW',
             crop='WHEAT', harvest_units=2, initial_wheat=0, now=460):
    """A legal-shaped observed farm, then fixed authored actions through EOD."""
    state, env = ORACLE.fixture(step=now, cash=50000)
    obs = state[seat].observation
    farm, private = obs.farms[seat], obs.private
    farm['tiles'] = [[None for _ in range(10)] for _ in range(10)]
    farm['unlocked_quadrants'] = ['NW', 'NE', 'SW', 'SE']
    farm['farmer'] = [0, 0]
    farm['hands'] = [[0, 0], [0, 0]]
    farm['hires_today'] = 2
    if now % 24 == 23:
        actor, spawn = 0, (4, 4)
    if actor == 0:
        farm['farmer'] = list(spawn)
    else:
        farm['hands'][actor - 1] = list(spawn)
    x, y = spawn
    plant = ENGINE._new_plant(crop, now // 24 - max(3, ENGINE.CROPS[crop]['first_yield_day']), 24)
    plant['yield_units'] = harvest_units
    farm['tiles'][y][x] = plant
    farm['tiles'][y][x - 1] = ENGINE._new_animal(animal, now // 24 - 2)
    farm['tiles'][y][x - 2] = ENGINE._new_animal('SHEEP', now // 24 - 2)
    private['shed']['WHEAT'] = 9
    private['shed']['MILK'] = 91 if now % 24 != 23 else 0
    private['inventories'] = [{}, {}, {}]
    private['inventories'][actor] = {'WHEAT': initial_wheat} if initial_wheat else {}
    private['inventories'][(actor + 1) % 3] = {'MILK': 2}
    route = [blank() for _ in range(720)]
    first, second = (['HARVEST'], ['PICKUP', 'WHEAT', 3])
    if timing == 'after':
        first, second = second, first
    elif timing in ('none', 'late', 'other'):
        first = ['PASS']
    for dt, unit in enumerate([first, second, ['WEST'], ['FEED'], ['WEST'], ['FEED']], 1):
        set_unit(route[now + dt], actor, unit)
    if timing == 'late':
        for dt, unit in [(7, ['EAST']), (8, ['EAST']), (9, ['HARVEST'])]:
            set_unit(route[now + dt], actor, unit)
    if timing == 'other':
        other = (actor + 1) % 3
        # A separate grain source belongs to another actor, not the feeder.
        farm['tiles'][0][0] = copy.deepcopy(plant)
        set_unit(route[now + 1], other, ['HARVEST'])
    route[now + 7]['market'] = [['BUY_PRODUCT', 'FERTILIZER', 8]]
    selected = blank()
    selected['market'] = [['SELL', 'WHEAT', 9]]
    return state, env, route, selected, actor


def propose(module, fixture, seat):
    state, env, route, selected, _ = fixture
    obs = state[seat].observation
    return module.protect_feed_stock(m, obs, env.configuration, selected,
                                     obs.farms[seat], obs.private, route)


def execute(fixture, seat, selected):
    state, env, route, _, actor = copy.deepcopy(fixture)
    obs = state[seat].observation
    farm, private = obs.farms[seat], obs.private
    now = obs.step
    end = ((now // 24) + 1 + int(now % 24 == 23)) * 24 - 1
    trace = []
    for step in range(now, end + 1):
        for row in state:
            row.observation.step = step
            row.observation.day = step // 24
            row.observation.hour = step % 24
            row.action = blank()
        state[seat].action = copy.deepcopy(selected if step == now else route[step])
        ENGINE.interpreter(state, env)
        RESULTS['interpreter_calls'] += 1
        if step in (now, now + 1, now + 2, now + 4, now + 6, end - 1, end):
            trace.append({'step': step, 'cash': farm['money'],
                          'shed': copy.deepcopy(private['shed']),
                          'inventories': copy.deepcopy(private['inventories'])})
    return {'state': copy.deepcopy(state), 'trace': trace, 'actor': actor,
            'cash': farm['money'], 'shed': copy.deepcopy(private['shed']),
            'animals': [copy.deepcopy(tile) for row in farm['tiles'] for tile in row
                        if isinstance(tile, dict) and 'animal' in tile]}


class FeedHarvestRegression(unittest.TestCase):
    def test_full_interpreter_cash_and_displaced_milk_counterexample(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                fixture = scenario(seat=seat)
                parent_action = fixture[3]
                old_action, old_report = propose(ORIGINAL, fixture, seat)
                new_action, new_report = propose(CANDIDATE, fixture, seat)
                parent = execute(fixture, seat, parent_action)
                old = execute(fixture, seat, old_action)
                new = execute(fixture, seat, new_action)
                self.assertTrue(old_report['changed'])
                self.assertEqual(old['animals'], parent['animals'])
                self.assertEqual(old['cash'] - parent['cash'], -46)
                self.assertEqual(old['shed']['MILK'] - parent['shed']['MILK'], -1)
                self.assertEqual(old['shed']['WHEAT'] - parent['shed']['WHEAT'], 1)
                self.assertIs(new_action, parent_action)
                self.assertEqual(new_report['reason'], REASON)
                self.assertEqual(new['state'], parent['state'])
                RESULTS['witnesses'].append({'seat': seat, 'old_report': old_report,
                    'repair_report': new_report, 'parent_trace': parent['trace'],
                    'old_trace': old['trace'], 'repaired_trace': new['trace']})

    def test_grid_both_seats_all_actors_spawns_timings_and_animals(self):
        for seat in (0, 1):
            for actor in range(3):
                for spawn in ((4, 4), (5, 4), (4, 5), (5, 5)):
                    for timing in ('before', 'after'):
                        for animal in ('GOOSE', 'COW', 'SHEEP'):
                            with self.subTest(seat=seat, actor=actor, spawn=spawn,
                                              timing=timing, animal=animal):
                                f = scenario(seat, actor, spawn, timing, animal)
                                old_action, old_report = propose(ORIGINAL, f, seat)
                                action, report = propose(CANDIDATE, f, seat)
                                parent = execute(f, seat, f[3])
                                old = execute(f, seat, old_action)
                                new = execute(f, seat, action)
                                self.assertTrue(old_report['changed'])
                                self.assertEqual(old['animals'], parent['animals'])
                                self.assertEqual(old['cash'] - parent['cash'], -46)
                                self.assertIs(action, f[3])
                                self.assertFalse(report['certified'])
                                self.assertEqual(new['state'], parent['state'])
                                RESULTS['grid_cells'] += 1

    def test_harvest_sizes_one_through_six_decline(self):
        for units in range(1, 7):
            f = scenario(harvest_units=units)
            action, report = propose(CANDIDATE, f, 0)
            self.assertIs(action, f[3])
            self.assertEqual(report['reason'], REASON)

    def test_reset_uses_the_next_day_actor_not_dismissed_hands(self):
        for seat in (0, 1):
            f = scenario(seat=seat, now=479)
            old, old_report = propose(ORIGINAL, f, seat)
            action, report = propose(CANDIDATE, f, seat)
            self.assertTrue(old_report['changed'])
            self.assertEqual(old_report['window']['obligations'][0]['actor'], 0)
            self.assertIs(action, f[3])
            self.assertEqual(report['reason'], REASON)
            self.assertEqual(execute(f, seat, action)['state'], execute(f, seat, f[3])['state'])

    def test_non_wheat_harvest_remains_eligible(self):
        for crop in ('CARROT', 'TOMATO', 'STRAWBERRY', 'MELON'):
            f = scenario(crop=crop)
            old = propose(ORIGINAL, f, 0)
            new = propose(CANDIDATE, f, 0)
            self.assertTrue(new[1]['changed'])
            self.assertEqual(new, old)
            self.assertEqual(execute(f, 0, new[0])['state'], execute(f, 0, old[0])['state'])

    def test_independent_actor_harvest_does_not_veto_protected_feeder(self):
        for actor in range(3):
            f = scenario(actor=actor, timing='other')
            old = propose(ORIGINAL, f, 0)
            new = propose(CANDIDATE, f, 0)
            self.assertTrue(new[1]['changed'])
            self.assertEqual(new, old)
            self.assertEqual(execute(f, 0, new[0])['state'], execute(f, 0, old[0])['state'])

    def test_harvest_after_final_feed_does_not_veto(self):
        for actor in range(3):
            f = scenario(actor=actor, timing='late')
            old = propose(ORIGINAL, f, 0)
            new = propose(CANDIDATE, f, 0)
            self.assertTrue(new[1]['changed'])
            self.assertEqual(new, old)
            self.assertEqual(execute(f, 0, new[0])['state'], execute(f, 0, old[0])['state'])

    def test_no_harvest_preserves_useful_reservation_and_real_feeds(self):
        f = scenario(timing='none')
        action, report = propose(CANDIDATE, f, 0)
        self.assertEqual((action, report), propose(ORIGINAL, f, 0))
        self.assertTrue(report['changed'])
        parent = execute(f, 0, f[3])
        protected = execute(f, 0, action)
        self.assertTrue(all(a['consecutive_unfed'] == 1 for a in parent['animals']))
        self.assertTrue(all(a['consecutive_unfed'] == 0 for a in protected['animals']))
        self.assertEqual(protected['shed']['WHEAT'], 0)

    def test_observed_carried_input_is_not_reclassified_as_future_harvest(self):
        f = scenario(initial_wheat=2)
        self.assertEqual(propose(CANDIDATE, f, 0), propose(ORIGINAL, f, 0))
        self.assertIs(propose(CANDIDATE, f, 0)[0], f[3])

    def test_no_sale_and_raw_dead_suffix_are_exact_identity(self):
        f = scenario()
        f[3]['market'] = [[] for _ in range(10)] + [['SELL', 'WHEAT', 9]]
        action, report = propose(CANDIDATE, f, 0)
        self.assertIs(action, f[3])
        self.assertEqual(report['reason'], 'no_wheat_sale')

    def test_input_mutation_and_raw_slot_custody(self):
        for timing in ('before', 'none'):
            f = scenario(timing=timing)
            f[3]['market'] = [[], ['SELL', 'WHEAT', 4], [], ['SELL', 'WHEAT', 5]]
            f[3]['market'] += [[] for _ in range(6)] + [['HIRE'], ['SELL', 'WHEAT', 99]]
            before = copy.deepcopy(f)
            action, _ = propose(CANDIDATE, f, 0)
            self.assertEqual(f, before)
            self.assertEqual(action['market'][10:], f[3]['market'][10:])
            self.assertEqual(action['farmer'], f[3]['farmer'])
            self.assertEqual(action['hands'], f[3]['hands'])
            self.assertEqual(action['market'][0], [])
            self.assertEqual(action['market'][2], [])

    def test_native_final_feed_callsite_consumes_the_repaired_function(self):
        for seat in (0, 1):
            f = scenario(seat=seat)
            state, env, route, selected, _ = f
            obs = state[seat].observation
            agent = object.__new__(TitanAgent)
            agent.features = Features(operating_stock=True)
            agent.spatial = None
            agent.history = None
            agent.quadrant = None
            agent.diagnostics = {}
            agent.controller = SimpleNamespace(R={'current': route}, cur='current')
            agent.consumer = SimpleNamespace(selected_post_units=(obs.farms[seat], obs.private),
                selected_post_units_binding=(obs.step, seat, selected['farmer'], selected['hands']))
            action = agent._feed_stock_selected(obs, env.configuration, selected)
            self.assertIs(action, selected)
            self.assertEqual(agent.diagnostics['feed_stock']['reason'], REASON)
            agent.features = Features(operating_stock=False)
            agent.diagnostics = {}
            self.assertIs(agent._feed_stock_selected(obs, env.configuration, selected), selected)
            self.assertEqual(agent.diagnostics, {})

    def test_target_only_transformation_and_idempotence(self):
        a, b, _ = function_span(ORIGINAL_TEXT)
        c, d, _ = function_span(REPAIRED_TEXT)
        self.assertEqual(ORIGINAL_TEXT[:a], REPAIRED_TEXT[:c])
        self.assertEqual(ORIGINAL_TEXT[b:], REPAIRED_TEXT[d:])
        self.assertEqual(repair_source(REPAIRED_TEXT), REPAIRED_TEXT)
        peer = ORIGINAL_TEXT + '\n# A disjoint concurrent FERT-prefix addition.\nPEER_SENTINEL = 1\n'
        self.assertEqual(repair_source(peer), REPAIRED_TEXT + peer[len(ORIGINAL_TEXT):])

    def test_unknown_missing_duplicate_or_modified_target_is_rejected(self):
        start, stop, function = function_span(ORIGINAL_TEXT)
        for text in (ORIGINAL_TEXT.replace('    fertilizer_requests = 0', '    fertilizer_requests = 1', 1),
                     ORIGINAL_TEXT[:start] + ORIGINAL_TEXT[stop:], ORIGINAL_TEXT + '\n' + function,
                     REPAIRED_TEXT.replace(REASON, 'bypassed_feed_proof')):
            with self.subTest(length=len(text)):
                with self.assertRaises(ValueError):
                    repair_source(text)
        with self.assertRaises(TypeError):
            repair_source(ORIGINAL_TEXT.encode())

    def test_five_semantic_mutants_are_detected(self):
        mutations = {
            'omit_harvest_record': ('wheat_harvests.append((actor, step))', 'pass'),
            'wrong_crop': ("observed_tile.get('crop') == 'WHEAT'", "observed_tile.get('crop') == 'CARROT'"),
            'reverse_time': ('a == actor and t < last_feed', 'a == actor and t > last_feed'),
            'ignore_farmer': ('a == actor and t < last_feed', 'a == actor and actor != 0 and t < last_feed'),
            'cross_actor_veto': ('a == actor and t < last_feed', 't < last_feed'),
        }
        for name, (before, after) in mutations.items():
            self.assertEqual(REPAIRED_TEXT.count(before), 1)
            mutant = load_text('feed_mutant_' + name, REPAIRED_TEXT.replace(before, after, 1), '<mutant>')
            f = scenario(timing='other' if name == 'cross_actor_veto' else 'before')
            with self.assertRaises(AssertionError, msg=name):
                action, report = propose(mutant, f, 0)
                if name == 'cross_actor_veto':
                    self.assertTrue(report['changed'])
                else:
                    self.assertIs(action, f[3])
            RESULTS['mutants_rejected'].append(name)


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(FeedHarvestRegression))
    suite.addTests(loader.loadTestsFromTestCase(BASELINE.FeedStockTests))
    return suite


if __name__ == '__main__':
    suite = load_tests(unittest.defaultTestLoader, None, None)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    RESULTS.update(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                   success=result.wasSuccessful(), optimized=not __debug__,
                   original_blob=git_blob(ORIGINAL_TEXT.encode()),
                   repaired_blob=git_blob(REPAIRED_TEXT.encode()))
    print(json.dumps(RESULTS, indent=2, sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)
