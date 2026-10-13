#!/usr/bin/env python3
"""Opt-in CF1 completed-service extension: exact-source/engine differentials.

Usage: python [-O] check_completed_cow_service.py --engine kaggriculture.py
       --predecessor predecessor.py [-v]
Runs the unchanged 19-test CF1 suite as well. Synthetic evidence, not field EV.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE_BLOB = 'ef6ab6e795375cf84c5dc7d0bcd43f979bbd0af8'
PREDECESSOR_BLOB = '3f6697c7825ea39b84a00767088eb52f2ba2903f'
BASE_TEST_BLOB = 'f3167bf43a26e117a624548378f120f794417a7a'


def git_blob(path):
    raw = Path(path).read_bytes()
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def require_pin(path, expected):
    got = git_blob(path)
    if got != expected:
        raise RuntimeError(f'identity mismatch for {Path(path).name}: {got}')


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--engine', type=Path, required=True)
parser.add_argument('--predecessor', type=Path, required=True)
parser.add_argument('--receipt', type=Path)
args, unittest_args = parser.parse_known_args()
require_pin(ROOT / 'r04_cow_fert_salvage.py', SOURCE_BLOB)
require_pin(ROOT / 'check_cow_fert_salvage.py', BASE_TEST_BLOB)
require_pin(args.predecessor, PREDECESSOR_BLOB)
_saved_argv = sys.argv
try:
    sys.argv = [__file__, '--engine', str(args.engine)]
    import check_cow_fert_salvage as B
finally:
    sys.argv = _saved_argv
C = B.CF1
_spec = importlib.util.spec_from_file_location('_cf1_completed_predecessor', args.predecessor)
OLD = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(OLD)
COUNTS = {'extension_engine_pairs': 0, 'default_predecessor_cells': 0,
          'two_turn_liquidation_pairs': 0}


def fixture(op='CARE', **kwargs):
    case = B.fixture(**kwargs)
    actor = kwargs.get('actor', 0)
    action, _, _ = B.inputs(case)
    if actor:
        action['hands'][actor - 1] = [op]
    else:
        action['farmer'] = [op]
    return case


def apply(case, **kwargs):
    return C.apply_cow_fert_salvage(*B.inputs(case), enabled=True,
                                  completed_service=True, **kwargs)


def cow(case, xy=(2, 2)):
    obs = B.inputs(case)[1]
    return obs.farms[obs.player]['tiles'][xy[1]][xy[0]]


def add_hand(case, pos, command, tile=None, inventory=None):
    action, obs, _ = B.inputs(case)
    farm = obs.farms[obs.player]
    farm['hands'].append(list(pos))
    farm['hires_today'] += 1
    obs.private['inventories'].append(dict(inventory or {}))
    action['hands'].append(list(command))
    if tile is not None:
        farm['tiles'][pos[1]][pos[0]] = copy.deepcopy(tile)


class CompletedServiceTests(unittest.TestCase):
    def assert_identity(self, case):
        action, obs, config = B.inputs(case)
        before = copy.deepcopy((action, obs, config))
        self.assertIs(apply(case), action)
        self.assertEqual((action, obs, config), before)

    def assert_gain(self, case):
        states, env, seat = case
        action, obs, config = B.inputs(case)
        before = copy.deepcopy((action, obs, config))
        result = apply(case)
        self.assertIsNot(result, action)
        self.assertEqual((action, obs, config), before)
        expected = copy.deepcopy(action)
        old_rows = [action['farmer'], *action['hands']]
        new_rows = [result['farmer'], *result['hands']]
        changed = [i for i, (a, b) in enumerate(zip(old_rows, new_rows)) if a != b]
        self.assertEqual(len(changed), 1)
        self.assertIn(old_rows[changed[0]], (['CARE'], ['FEED'], ['HARVEST']))
        if changed[0]:
            expected['hands'][changed[0] - 1] = ['COLLECT_FERTILIZER']
        else:
            expected['farmer'] = ['COLLECT_FERTILIZER']
        self.assertEqual(result, expected)
        self.assertEqual((action, obs, config), before)
        left, right = copy.deepcopy(states), copy.deepcopy(states)
        right[seat].action = result
        B.E.interpreter(left, copy.deepcopy(env))
        B.E.interpreter(right, copy.deepcopy(env))
        self.assertEqual(right[seat].observation.private['shed']['FERTILIZER'],
                         left[seat].observation.private['shed']['FERTILIZER'] + 1)
        normalized = copy.deepcopy(right)
        normalized[seat].observation.private['shed']['FERTILIZER'] -= 1
        for i in (0, 1):
            self.assertEqual(left[i].observation, normalized[i].observation)
            self.assertEqual(left[i].status, normalized[i].status)
            self.assertEqual(left[i].reward, normalized[i].reward)
        return left, right

    def test_literal_opt_in_and_master_off(self):
        for op, value in itertools.product(('CARE', 'FEED'), (False, None, 0, 1, 1.0, 'true', [], {})):
            case = fixture(op)
            action, obs, cfg = B.inputs(case)
            self.assertIs(C.apply_cow_fert_salvage(action, obs, cfg, enabled=True,
                                                completed_service=value), action)
            self.assertIs(C.apply_cow_fert_salvage(action, obs, cfg,
                                                completed_service=True), action)

    def test_default_matches_exact_predecessor_3132_cells(self):
        count = 0
        for day, seat, actor, op, variant in itertools.product(
                range(29), (0, 1), (0, 1), ('HARVEST', 'CARE', 'FEED'), range(9)):
            case = fixture(op, day=day, player=seat, actor=actor)
            action, obs, cfg = B.inputs(case)
            if variant == 1: cow(case)['cared_today'] = False
            elif variant == 2: cow(case)['fed_today'] = False
            elif variant == 3: cow(case)['fertilizer_available'] = False
            elif variant == 4: cow(case)['yield_units'] = 1
            elif variant == 5: obs.private['shed']['WHEAT'] = 100
            elif variant == 6: action['market'] = [['HIRE']]
            elif variant == 7: action['market'] = [[]] * 10 + [['HIRE']]
            elif variant == 8: cfg.maxMarketOrdersPerTurn = 1
            expected = OLD.apply_cow_fert_salvage(action, obs, cfg, enabled=True)
            actual = C.apply_cow_fert_salvage(action, obs, cfg, enabled=True)
            self.assertEqual(actual, expected)
            self.assertEqual(actual is action, expected is action)
            count += 1
        self.assertEqual(count, 3132)
        COUNTS['default_predecessor_cells'] = count

    def test_full_interpreter_1392_service_pairs(self):
        count = 0
        for day, seat, actor, op, (stock, carried), bonus in itertools.product(
                range(29), (0, 1), (0, 1), ('CARE', 'FEED'),
                ((0, 0), (40, 5), (98, 1)), (0, 3)):
            with self.subTest(day=day, seat=seat, actor=actor, op=op, stock=stock, bonus=bonus):
                case = fixture(op, day=day, player=seat, actor=actor, stock=stock, carried=carried)
                cow(case)['pending_care_bonus'] = bonus
                self.assert_gain(case)
                count += 1
        self.assertEqual(count, 1392)
        COUNTS['extension_engine_pairs'] = count

    def test_productive_care_and_feed_never_removed(self):
        for op, field in (('CARE', 'cared_today'), ('FEED', 'fed_today')):
            case = fixture(op)
            cow(case)[field] = False
            B.inputs(case)[1].private['inventories'][0] = {'WHEAT': 1}
            self.assert_identity(case)

    def test_broad_care_stripping_has_real_future_production_cost(self):
        case = fixture('CARE', day=8)
        cow(case)['cared_today'] = False
        states, env, seat = case
        left, right = copy.deepcopy(states), copy.deepcopy(states)
        right[seat].action['farmer'] = ['COLLECT_FERTILIZER']
        B.E.interpreter(left, copy.deepcopy(env))
        B.E.interpreter(right, copy.deepcopy(env))
        # Today's CARE was recorded AFTER today's production check. It pays at
        # the next COW production, and must never be confused with a dead CARE.
        for arm in (left, right):
            t = arm[seat].observation.farms[seat]['tiles'][2][2]
            t['fed_today'] = True
            t['cared_today'] = False
            B.E._daily_refresh_animals(arm[seat].observation.farms[seat], 9)
        self.assertEqual(left[seat].observation.farms[seat]['tiles'][2][2]['yield_units'],
                         right[seat].observation.farms[seat]['tiles'][2][2]['yield_units'] + 1)
        self.assert_identity(case)

    def test_broad_feed_stripping_can_lose_the_cow(self):
        case = fixture('FEED')
        cow(case).update(fed_today=False, consecutive_unfed=1)
        states, env, seat = case
        states[seat].observation.private['inventories'][0] = {'WHEAT': 1}
        left, right = copy.deepcopy(states), copy.deepcopy(states)
        right[seat].action['farmer'] = ['COLLECT_FERTILIZER']
        B.E.interpreter(left, copy.deepcopy(env))
        B.E.interpreter(right, copy.deepcopy(env))
        self.assertEqual(left[seat].observation.farms[seat]['tiles'][2][2]['animal'], 'COW')
        self.assertNotIn('animal', right[seat].observation.farms[seat]['tiles'][2][2])
        self.assert_identity(case)

    def test_all_ready_fields_remain_strict(self):
        poisons = {'fed_today': (False, None, 1, 'true'),
                   'cared_today': (False, None, 1, 'true'),
                   'fertilizer_available': (False, None, 1, 'true'),
                   'yield_units': (1, -1, None, False, '0'),
                   'placed_day': (-1, 99, None, False, '0'),
                   'consecutive_unfed': (2, -1, False, None, '0'),
                   'pending_care_bonus': (-1, False, None, '0')}
        for op in ('CARE', 'FEED'):
            for field, values in poisons.items():
                for value in values:
                    case = fixture(op)
                    cow(case)[field] = value
                    self.assert_identity(case)

    def test_harvest_incumbent_keeps_priority_in_both_orders(self):
        case = fixture('CARE')
        add_hand(case, (3, 2), ['HARVEST'], cow(case))
        self.assertEqual(apply(case), C.apply_cow_fert_salvage(*B.inputs(case), enabled=True))
        self.assert_gain(case)
        case = fixture('HARVEST')
        add_hand(case, (3, 2), ['FEED'], cow(case))
        self.assertEqual(apply(case), C.apply_cow_fert_salvage(*B.inputs(case), enabled=True))
        self.assert_gain(case)

    def test_productive_or_second_harvest_retains_incumbent_veto(self):
        for units in (0, 2):
            case = fixture('HARVEST')
            other = copy.deepcopy(cow(case)); other['yield_units'] = units
            add_hand(case, (3, 2), ['HARVEST'], other)
            add_hand(case, (1, 2), ['CARE'], cow(case))
            self.assert_identity(case)

    def test_one_recovery_among_multiple_completed_services(self):
        case = fixture('CARE', stock=98)
        add_hand(case, (3, 2), ['FEED'], cow(case))
        add_hand(case, (1, 2), ['CARE'], cow(case))
        result = apply(case)
        self.assertEqual(result['farmer'], ['COLLECT_FERTILIZER'])
        self.assertEqual(result['hands'], [['FEED'], ['CARE']])
        self.assert_gain(case)

    def test_stacked_candidate_skipped_without_stealing_sibling(self):
        case = fixture('CARE')
        add_hand(case, (2, 2), ['FEED'])
        self.assert_identity(case)
        add_hand(case, (3, 2), ['CARE'], cow(case))
        result = apply(case)
        self.assertEqual(result['farmer'], ['CARE'])
        self.assertEqual(result['hands'], [['FEED'], ['COLLECT_FERTILIZER']])
        self.assert_gain(case)

    def test_productive_sibling_care_and_feed_preserved(self):
        for op, field in (('CARE', 'cared_today'), ('FEED', 'fed_today')):
            case = fixture('CARE')
            other = copy.deepcopy(cow(case)); other[field] = False
            add_hand(case, (3, 2), [op], other, {'WHEAT': 1})
            self.assertEqual(apply(case)['hands'], [[op]])
            self.assert_gain(case)

    def test_sheep_goose_pass_and_non_cow_are_not_admitted(self):
        for animal in ('SHEEP', 'GOOSE'):
            case = fixture()
            cow(case)['animal'] = animal
            self.assert_identity(case)
        for op in ('PASS', 'WATER', 'FERTILIZE', 'COLLECT_FERTILIZER'):
            self.assert_identity(fixture(op))

    def test_capacity_protects_later_actor_and_partial_final_day(self):
        for op in ('CARE', 'FEED'):
            case = fixture(op, stock=99)
            add_hand(case, (4, 4), ['PASS'], inventory={'MILK': 1})
            self.assert_identity(case)
            for step in (22, 24, 696, 718, 719):
                case = fixture(op)
                B.inputs(case)[1]['step'] = step
                self.assert_identity(case)

    def test_market_row_and_alias_guards_inherited(self):
        for op in ('CARE', 'FEED'):
            for row in (['HIRE'], ['BUY_PRODUCT', 'WHEAT', 1], ['SELL', 'MILK', True], None):
                case = fixture(op)
                B.inputs(case)[0]['market'] = [[] for _ in range(9)] + [row]
                self.assert_identity(case)
            case = fixture(op, actor=1)
            action, obs, _ = B.inputs(case)
            obs.private['inventories'][0] = obs.private['inventories'][1]
            action['farmer'] = ['DROP']
            self.assert_identity(case)

    def test_prefix_sell_and_engine_dead_tail_unchanged(self):
        for op in ('CARE', 'FEED'):
            case = fixture(op)
            action, obs, _ = B.inputs(case)
            obs.private['shed']['FERTILIZER'] = 4
            action['market'] = [[], ['SELL', 'FERTILIZER', 999]] + [[] for _ in range(8)]
            action['market'] += [['HIRE'], ['BUY_PRODUCT', 'WHEAT', 99]]
            self.assertEqual(apply(case)['market'], action['market'])
            self.assert_gain(case)

    def test_opponent_market_and_floor_do_not_change_before_eod(self):
        for op, seat in itertools.product(('CARE', 'FEED'), (0, 1)):
            case = fixture(op, player=seat)
            states, _, _ = case
            action, obs, _ = B.inputs(case)
            obs.market['inventory']['FERTILIZER'] = 20000
            obs.private['shed']['FERTILIZER'] = 5
            action['market'] = [['SELL', 'FERTILIZER', 5]]
            states[1 - seat].action['market'] = [['BUY_PRODUCT', 'FERTILIZER', 3]]
            self.assert_gain(case)

    def test_metadata_and_input_objects_unmodified(self):
        case = fixture('FEED', actor=1)
        action, _, _ = B.inputs(case)
        action['debug'] = {'opaque': [1, {'a': 2}]}
        self.assert_gain(case)

    def test_install_option_forwarded_parent_once_and_default_off(self):
        for op in ('CARE', 'FEED'):
            case = fixture(op)
            action, obs, cfg = B.inputs(case)
            calls = []
            def parent(o, c):
                calls.append((o, c)); return action
            self.assertIs(C.install(parent, enabled=True)(obs, cfg), action)
            self.assertIs(C.install(parent, completed_service=True)(obs, cfg), action)
            got = C.install(parent, enabled=True, completed_service=True)(obs, cfg)
            self.assertEqual(got['farmer'], ['COLLECT_FERTILIZER'])
            self.assertEqual(len(calls), 3)
            self.assertTrue(all(o is obs and c is cfg for o, c in calls))

    def test_telemetry_only_counts_actual_service_activation(self):
        before = C.telemetry['completed_service_activations']
        case = fixture('FEED')
        apply(case)
        self.assertEqual(C.telemetry['completed_service_activations'], before + 1)
        case = fixture('HARVEST')
        apply(case)
        self.assertEqual(C.telemetry['completed_service_activations'], before + 1)
        case = fixture('CARE'); cow(case)['cared_today'] = False
        apply(case)
        self.assertEqual(C.telemetry['completed_service_activations'], before + 1)

    def test_explicit_next_turn_liquidation_is_positive_not_field_ev(self):
        count = 0
        for op, seat in itertools.product(('CARE', 'FEED'), (0, 1)):
            case = fixture(op, player=seat, day=9)
            left, right = self.assert_gain(case)
            env = case[1]
            for arm in (left, right):
                for s in arm:
                    s.observation.step = 240
                    s.action = {'farmer': ['PASS'], 'hands': [], 'market': []}
                arm[seat].action['market'] = [['SELL', 'FERTILIZER', 1]]
                B.E.interpreter(arm, copy.deepcopy(env))
            self.assertEqual(right[seat].observation.farms[seat]['money'],
                             left[seat].observation.farms[seat]['money'] + 100)
            self.assertEqual(right[1 - seat].observation.farms[1 - seat]['money'],
                             left[1 - seat].observation.farms[1 - seat]['money'])
            self.assertEqual(right[seat].observation.private, left[seat].observation.private)
            count += 1
        COUNTS['two_turn_liquidation_pairs'] = count


def load_tests(loader, tests, pattern):
    tests.addTests(loader.loadTestsFromModule(B))
    return tests


if __name__ == '__main__':
    result = unittest.main(argv=[__file__, *unittest_args], exit=False).result
    if args.receipt:
        report = {'schema': 'cf1-completed-service-component/v1',
                  'source_blob': SOURCE_BLOB, 'predecessor_blob': PREDECESSOR_BLOB,
                  'base_test_blob': BASE_TEST_BLOB, 'engine_blob': B.ENGINE_BLOB,
                  'tests_run': result.testsRun, 'failures': len(result.failures),
                  'errors': len(result.errors), 'skipped': len(result.skipped),
                  'counts': COUNTS, 'evidence_scope': 'constructed full-interpreter EOD pairs; no natural activation or field EV',
                  'production_enabled': False, 'default_changed': False}
        args.receipt.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
