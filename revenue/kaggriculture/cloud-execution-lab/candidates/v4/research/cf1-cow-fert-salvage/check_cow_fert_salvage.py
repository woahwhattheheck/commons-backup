#!/usr/bin/env python3
"""CF1 mechanism tests plus full pinned-interpreter one-callback differentials.

Run: python [-O] test_cow_fert_salvage.py --engine /path/kaggriculture.py -v
The original engine is Git-hash verified. Only its unused seed-resolution import
is replaced by a fail-on-use bootstrap shim; no gameplay function is replaced.
These are synthetic state pairs, not field games or economic-promotion evidence.
"""
from __future__ import annotations
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

import r04_cow_fert_salvage as CF1

PARSER = argparse.ArgumentParser(description=__doc__)
PARSER.add_argument('--engine', type=Path, required=True)
ARGS, UNITTEST_ARGS = PARSER.parse_known_args()
ENGINE_BLOB = '3c202c7ee921da239356789e266b694635103fc4'


def load_engine(path):
    raw = path.read_bytes()
    got = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if got != ENGINE_BLOB:
        raise RuntimeError('engine identity mismatch: ' + got)
    tree = ast.parse(raw)
    imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)
               and node.module == 'kaggle_environments.utils']
    if len(imports) != 1 or [(a.name, a.asname) for a in imports[0].names] != [('resolve_episode_seed', None)]:
        raise RuntimeError('unexpected bootstrap import')
    tree.body.remove(imports[0])
    def forbidden_seed_resolution(*args, **kwargs):
        raise RuntimeError('preinitialized-state test unexpectedly called seed resolver')
    ns = {'__name__': '_cf1_pinned_engine', '__file__': str(path),
          'resolve_episode_seed': forbidden_seed_resolution}
    exec(compile(tree, str(path), 'exec'), ns)
    return SimpleNamespace(**ns)


E = load_engine(ARGS.engine)


class Struct(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc
    __setattr__ = dict.__setitem__


def fixture(day=9, player=0, actor=0, stock=0, carried=0):
    config = Struct(CF1.STANDARD, weedSpawnChance=0.035)
    farms = [E._new_farm(10, 1000), E._new_farm(10, 1000)]
    privates = [E._new_private(), E._new_private()]
    farm, private = farms[player], privates[player]
    farm['farmer'] = [2, 2] if actor == 0 else [4, 4]
    farm['hands'] = [] if actor == 0 else [[2, 2]]
    farm['hires_today'] = actor
    private['inventories'] = [{}] if actor == 0 else [{}, {}]
    private['shed']['WHEAT'] = stock
    if carried:
        private['inventories'][actor]['MILK'] = carried
    cow = E._new_animal('COW', 0)
    cow.update(fed_today=True, cared_today=True, fertilizer_available=True, yield_units=0)
    farm['tiles'][2][2] = cow
    action = {'farmer': ['HARVEST'] if actor == 0 else ['PASS'],
              'hands': [] if actor == 0 else [['HARVEST']], 'market': []}
    market, town = E._new_market(), E._new_town()
    states = []
    for seat in range(2):
        obs = Struct(step=day * 24 + 23, day=day, hour=23, player=seat,
                     farms=farms, private=privates[seat], market=market, town=town)
        own_action = action if seat == player else {'farmer': ['PASS'], 'hands': [], 'market': []}
        states.append(SimpleNamespace(observation=obs, action=own_action, status='ACTIVE', reward=None))
    env = SimpleNamespace(configuration=config, info={'seed': 912607}, done=False)
    return states, env, player


def inputs(case):
    states, env, player = case
    return states[player].action, states[player].observation, env.configuration


def run_differential(case):
    states, env, player = case
    source_action, obs, config = inputs(case)
    candidate = CF1.apply_cow_fert_salvage(source_action, obs, config, enabled=True)
    if candidate is source_action:
        raise AssertionError('expected activation')
    left, right = copy.deepcopy(states), copy.deepcopy(states)
    right[player].action = candidate
    E.interpreter(left, copy.deepcopy(env))
    E.interpreter(right, copy.deepcopy(env))
    return left, right, player


class CowFertSalvageTests(unittest.TestCase):
    def assert_identity(self, case):
        action, obs, config = inputs(case)
        self.assertIs(CF1.apply_cow_fert_salvage(action, obs, config, enabled=True), action)

    def assert_exact_fertilizer_gain(self, case):
        left, right, player = run_differential(case)
        before = left[player].observation.private['shed']['FERTILIZER']
        after = right[player].observation.private['shed']['FERTILIZER']
        self.assertEqual(after, before + 1)
        normalized = copy.deepcopy(right)
        normalized[player].observation.private['shed']['FERTILIZER'] -= 1
        for seat in range(2):
            self.assertEqual(left[seat].observation, normalized[seat].observation)
            self.assertEqual(left[seat].reward, normalized[seat].reward)
            self.assertEqual(left[seat].status, normalized[seat].status)
        return left, right

    def test_default_off_and_nonliteral_enable_preserve_identity(self):
        case = fixture()
        action, obs, config = inputs(case)
        self.assertIs(CF1.apply_cow_fert_salvage(action, obs, config), action)
        for enabled in (False, None, 1, 'true'):
            self.assertIs(CF1.apply_cow_fert_salvage(action, obs, config, enabled=enabled), action)

    def test_one_row_changed_and_inputs_untouched(self):
        for actor in (0, 1):
            case = fixture(actor=actor)
            action, obs, config = inputs(case)
            original = copy.deepcopy((action, obs, config))
            result = CF1.apply_cow_fert_salvage(action, obs, config, enabled=True)
            expected = copy.deepcopy(action)
            if actor == 0:
                expected['farmer'] = ['COLLECT_FERTILIZER']
            else:
                expected['hands'][0] = ['COLLECT_FERTILIZER']
            self.assertEqual(result, expected)
            self.assertEqual((action, obs, config), original)

    def test_full_interpreter_matrix_348_pairs(self):
        count = 0
        for day in range(29):
            for player in (0, 1):
                for actor in (0, 1):
                    for stock, carried in ((0, 0), (40, 5), (98, 1)):
                        with self.subTest(day=day, player=player, actor=actor, stock=stock):
                            self.assert_exact_fertilizer_gain(fixture(day, player, actor, stock, carried))
                            count += 1
        self.assertEqual(count, 348)

    def test_existing_sell_fills_and_quotes_identical_before_deposit(self):
        case = fixture(carried=2)
        states, _, player = case
        states[player].observation.private['shed']['FERTILIZER'] = 5
        states[player].action['market'] = [['SELL', 'FERTILIZER', 999]]
        self.assert_exact_fertilizer_gain(case)

    def test_opponent_market_activity_and_floor_sales_preserved(self):
        case = fixture()
        states, _, player = case
        states[player].observation.market['inventory']['FERTILIZER'] = 20000
        states[player].observation.private['shed']['FERTILIZER'] = 4
        states[player].action['market'] = [['SELL', 'FERTILIZER', 4]]
        states[1 - player].action['market'] = [['BUY_PRODUCT', 'FERTILIZER', 2]]
        self.assert_exact_fertilizer_gain(case)

    def test_full_shed_veto_and_forced_counterexample(self):
        case = fixture(stock=99)
        states, env, player = case
        farm = states[player].observation.farms[player]
        farm['hands'] = [[4, 4]]
        states[player].observation.private['inventories'].append({'MILK': 1})
        states[player].action['hands'] = [['PASS']]
        self.assert_identity(case)
        left, right = copy.deepcopy(states), copy.deepcopy(states)
        right[player].action['farmer'] = ['COLLECT_FERTILIZER']
        E.interpreter(left, copy.deepcopy(env))
        E.interpreter(right, copy.deepcopy(env))
        self.assertEqual(left[player].observation.private['shed']['MILK'], 1)
        self.assertEqual(right[player].observation.private['shed']['MILK'], 0)

    def test_market_raw_prefix_buy_and_hire_veto(self):
        for row in (['BUY_PRODUCT', 'WHEAT', 1], ['HIRE'], ['BUY_LAND'], ['BUY_SEED', 'WHEAT', 1], ['BUY_ANIMAL', 'COW', 1]):
            case = fixture()
            inputs(case)[0]['market'] = [[] for _ in range(9)] + [row]
            self.assert_identity(case)

    def test_dead_market_suffix_ignored_without_compaction(self):
        case = fixture()
        inputs(case)[0]['market'] = [[] for _ in range(10)] + [['BUY_PRODUCT', 'WHEAT', 99], ['HIRE']]
        self.assert_exact_fertilizer_gain(case)

    def test_other_unit_cannot_add_unbounded_cargo(self):
        for command in (['HARVEST'], ['COLLECT_FERTILIZER'], ['PLACE', 'COW'], ['PICKUP', 'WHEAT', 1]):
            case = fixture(actor=1)
            inputs(case)[0]['farmer'] = command
            self.assert_identity(case)

    def test_other_unit_drop_conserves_total_and_sale_prefix(self):
        case = fixture(actor=1, stock=96)
        action, obs, _ = inputs(case)
        action['farmer'] = ['DROP']
        obs.private['inventories'][0] = {'MILK': 3}
        action['market'] = [['SELL', 'MILK', 99]]
        self.assert_exact_fertilizer_gain(case)

    def test_productive_harvest_is_never_preempted(self):
        for units in (1, 6):
            case = fixture()
            inputs(case)[1].farms[0]['tiles'][2][2]['yield_units'] = units
            self.assert_identity(case)

    def test_cow_fields_missing_bool_and_coercion_rejected(self):
        poisons = {'yield_units': (None, False, '0', -1),
                   'placed_day': (None, False, '0', 99),
                   'pending_care_bonus': (None, False, '0', -1),
                   'consecutive_unfed': (None, False, '0', 2),
                   'fed_today': (None, False, 1, 'true'),
                   'cared_today': (None, False, 1, 'true'),
                   'fertilizer_available': (None, False, 1, 'true')}
        for key, values in poisons.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    case = fixture()
                    inputs(case)[1].farms[0]['tiles'][2][2][key] = value
                    self.assert_identity(case)

    def test_no_sheep_or_goose_service_takeover(self):
        for animal in ('SHEEP', 'GOOSE'):
            case = fixture()
            inputs(case)[1].farms[0]['tiles'][2][2]['animal'] = animal
            self.assert_identity(case)

    def test_full_actor_reconstruction_blocks_stacked_fert_hand(self):
        case = fixture(actor=1)
        action, obs, _ = inputs(case)
        obs.farms[0]['farmer'] = [2, 2]
        for command in (['PASS'], ['COLLECT_FERTILIZER'], ['FEED']):
            action['farmer'] = command
            self.assert_identity(case)

    def test_partial_actor_vectors_and_bad_geometry_rejected(self):
        case = fixture(actor=1)
        inputs(case)[0]['hands'] = []
        self.assert_identity(case)
        case = fixture(actor=1)
        inputs(case)[1].private['inventories'].pop()
        self.assert_identity(case)
        case = fixture()
        inputs(case)[1].farms[0]['farmer'] = [True, 2]
        self.assert_identity(case)
        case = fixture()
        inputs(case)[1].farms[0]['tiles'][9] = []
        self.assert_identity(case)

    def test_nonstandard_configuration_and_terminal_partial_day_rejected(self):
        for key in CF1.STANDARD:
            for bad in (None, True, str(CF1.STANDARD[key]), CF1.STANDARD[key] + 1):
                case = fixture()
                inputs(case)[2][key] = bad
                self.assert_identity(case)
        for step in (0, 22, 24, 696, 718, 719, -1, True):
            case = fixture()
            inputs(case)[1]['step'] = step
            self.assert_identity(case)

    def test_shed_and_all_cargo_types_are_counted_strictly(self):
        case = fixture(stock=98)
        inputs(case)[1].private['inventories'][0] = {'COW': 2}
        self.assert_identity(case)
        for bad in (True, '1', 1.0, -1):
            case = fixture()
            inputs(case)[1].private['shed']['MILK'] = bad
            self.assert_identity(case)

    def test_alias_cannot_expose_new_cargo_to_sibling_drop(self):
        case = fixture(actor=1)
        action, obs, _ = inputs(case)
        action['farmer'] = ['DROP']
        obs.private['inventories'][0] = obs.private['inventories'][1]
        self.assert_identity(case)

    def test_install_calls_parent_once_with_full_observation(self):
        case = fixture(actor=1)
        action, obs, config = inputs(case)
        calls = []
        def parent(o, c):
            calls.append((o, c))
            return action
        result = CF1.install(parent, enabled=True)(obs, config)
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0][0], obs)
        self.assertIs(calls[0][1], config)
        self.assertEqual(result['hands'][0], ['COLLECT_FERTILIZER'])


if __name__ == '__main__':
    unittest.main(argv=[__file__, *UNITTEST_ARGS])
