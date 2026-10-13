# SPDX-License-Identifier: Apache-2.0
"""Run actual SellScheduler.act and pinned official market-phase regressions.

Usage: python test_act_sale_prefix.py --package-tree /path/to/verified/package
Repeat with python -O. Only the existing package is read, never modified.
Projection/optimizer stubs isolate the five sale consumers; separate tests run
real optimize_lot and the unchanged official _process_market implementation.
This is not a full-match or economic promotion gate.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import importlib.util
import io
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

import act_sale_prefix as repair

PACKAGE = None
SOURCE = None
FIXED = None
ENGINE = None
MODULES = {}
COUNTS = {'incap_parity_cases': 0, 'official_market_cases': 0}
SOURCE_BLOBS = {
    'a483b24dd72b580d7d8811636b54d2d44f391575',
    'da1b6fb571e79ba7dab54c8d816e45afb934e4d2',
    # Exact output of #12643 projection transformer 563d08df... on da1b6fb...
    '349524020b2b7f925c93382abf0b0655ffc8c90d',
    # Exact current-main projection output; its materializer is f1028f7d...
    '1da9934ec45f485a16244bcbc78af26d9109b97e',
}


class Struct(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc
    __setattr__ = dict.__setitem__


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def load_scheduler(source):
    module = types.ModuleType('sale_prefix_fixture_' + repair.sha256(source)[:12])
    module.__file__ = str(PACKAGE / 'scheduler.py')
    with mock.patch.object(sys, 'path', [str(PACKAGE), *sys.path]):
        exec(compile(source, module.__file__, 'exec'), module.__dict__)
    # Keep the mechanism fixture independent of the controller decision tape.
    module.parent.DECISIONS = []
    return module


def fixture(stock=5, seat=0, step=1, inventory=10000):
    farms = [ENGINE._new_farm(10, 1000), ENGINE._new_farm(10, 1000)]
    market = ENGINE._new_market()
    market['inventory']['MILK'] = inventory
    ENGINE._refresh_prices(market)
    states = []
    for player in (0, 1):
        private = ENGINE._new_private()
        private['shed']['MILK'] = stock if player == seat else 2
        obs = Struct(player=player, step=step, day=step // 24, hour=step % 24,
                     farms=farms, private=private, market=market,
                     town={'unlocked_shops': []})
        states.append(Struct(observation=obs, action={'market': []}))
    return states


def call(raw, cap=1, *, source=None, step=1, future=None, stock=5,
         seat=0, budget=0, planned=None, chosen=None, real_optimizer=False,
         inventory=10000):
    source = FIXED if source is None else source
    key = repair.sha256(source)
    if key not in MODULES:
        MODULES[key] = load_scheduler(source)
    module = MODULES[key]
    states = fixture(stock=stock, seat=seat, step=step, inventory=inventory)
    obs = states[seat].observation
    original_obs = copy.deepcopy(obs)
    base = {'farmer': ['PASS'], 'hands': [], 'market': copy.deepcopy(raw)}
    original_base = copy.deepcopy(base)
    route = [{'farmer': ['PASS'], 'hands': [], 'market': []} for _ in range(720)]
    route[step] = base
    for when, orders in (future or {}).items():
        route[when] = {'farmer': ['PASS'], 'hands': [], 'market': copy.deepcopy(orders)}
    scheduler = module.SellScheduler.__new__(module.SellScheduler)
    scheduler.controller = types.SimpleNamespace(R=[route], cur=0, act=lambda _obs: base)
    scheduler.pending = {}
    scheduler.planned = copy.deepcopy(planned or {})
    scheduler.mode = 'candidate'
    scheduler.previous = None
    scheduler.observe = lambda _obs: None
    scheduler.rival_supply = lambda *_args: 0
    # Existing projection consumers have a different owner. These stubs isolate
    # act's sale-prefix logic; post_units and official market are not stubbed.
    scheduler.cash_reserve = lambda *_args: budget
    scheduler.receipt_profile = lambda *_args: lambda _plan: True
    seen = []

    def optimizer(**kwargs):
        cap_ok = kwargs['capacity_ok']
        seen.append({'reference': kwargs['reference'], 'minimum_now': kwargs['minimum_now'],
                     'now_one': cap_ok(((step, 1),)),
                     'future_one': cap_ok(((step + 1, 1),)),
                     'now_stock': cap_ok(((step, stock),))})
        plan = chosen if chosen is not None else kwargs['reference']
        info = {'worst_relative_gain': 1 if chosen is not None else 0,
                'forced_feasibility': False, 'plan': plan}
        return plan, info

    cfg = {'maxMarketOrdersPerTurn': cap, 'shedCapacity': 100}
    if real_optimizer:
        output = scheduler.act(obs, cfg)
    else:
        with mock.patch.object(module, 'optimize_lot', optimizer):
            output = scheduler.act(obs, cfg)
    if obs != original_obs or base != original_base:
        raise AssertionError('scheduler mutated its input')
    return output, scheduler, seen, states, cfg


class SourceContracts(unittest.TestCase):
    def test_exact_preimage_and_postimage(self):
        result, receipt = repair.rewrite_source(SOURCE)
        self.assertEqual(result, FIXED)
        self.assertEqual(receipt['replacement_count'], 6)
        self.assertEqual(receipt['act_before_sha256'], repair.ACT_BEFORE_SHA256)
        self.assertFalse(receipt['production_activation'])

    def test_idempotent(self):
        again, receipt = repair.rewrite_source(FIXED)
        self.assertEqual(again, FIXED)
        self.assertFalse(receipt['changed'])

    def test_unknown_or_partial_method_fails_closed(self):
        old, new = repair.REPLACEMENTS[0]
        cls, method, lines, before = repair._method(SOURCE)[1:]
        offset = sum(map(len, lines[:method.lineno - 1]))
        partial = SOURCE[:offset] + SOURCE[offset:].replace(old, new, 1)
        for changed in (partial, SOURCE.replace('baseline_q={}', 'baseline_q=dict()', 1)):
            with self.subTest(digest=repair.sha256(changed)):
                with self.assertRaises(ValueError):
                    repair.rewrite_source(changed)

    def test_duplicate_class_decorated_method_and_name_collision_rejected(self):
        variants = [SOURCE + '\nclass SellScheduler: pass\n',
                    SOURCE.replace('    def act(self, obs, config=None):',
                                   '    @staticmethod\n    def act(self, obs, config=None):'),
                    SOURCE + '\n_v4_sale_market_prefix = None\n']
        for changed in variants:
            with self.subTest(digest=repair.sha256(changed)):
                with self.assertRaises(ValueError):
                    repair.rewrite_source(changed)

    def test_modified_or_missing_postimage_helper_rejected(self):
        for changed in (FIXED.replace(repair.HELPERS, ''),
                        FIXED.replace('return max(1, int(config.get', 'return max(0, int(config.get')):
            with self.assertRaises(ValueError):
                repair.rewrite_source(changed)

    def test_unrelated_methods_and_terminal_branch_unchanged(self):
        def methods(source):
            cls = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == 'SellScheduler')
            return {n.name: ast.get_source_segment(source, n) for n in cls.body
                    if isinstance(n, ast.FunctionDef) and n.name != 'act'}
        self.assertEqual(methods(SOURCE), methods(FIXED))
        def terminal(source):
            method = repair._method(source)[2]
            node = next(n for n in method.body if isinstance(n, ast.If))
            return ast.get_source_segment(source, node)
        self.assertEqual(terminal(SOURCE), terminal(FIXED))
        # The verified artifact's later receipt-profile and post_units repairs
        # are carried byte-for-byte, not overwritten with the older donor.
        for name in ('post_units', 'optimize_lot', 'MarketPath'):
            def segment(source):
                n = next(n for n in ast.parse(source).body if getattr(n, 'name', None) == name)
                return ast.get_source_segment(source, n)
            self.assertEqual(segment(SOURCE), segment(FIXED))

    def test_unrelated_method_edit_is_preserved(self):
        # Act anchoring is independent of edits inside other methods. Actual
        # projection composition is separately run on pinned source 3495240.
        marker = '    def cash_reserve(self, obs, config, base, end):\n'
        changed = SOURCE.replace(marker, marker + '        # preserved peer projection repair\n', 1)
        after, _ = repair.rewrite_source(changed)
        self.assertEqual(after, FIXED.replace(marker, marker + '        # preserved peer projection repair\n', 1))

    def test_cli_does_not_overwrite_existing_file_or_edit_input(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / 'source.py'
            out = Path(d) / 'result.py'
            source.write_text(SOURCE)
            out.write_text('existing peer content')
            proc = subprocess.run([sys.executable, str(Path(repair.__file__)),
                                   '--source', str(source), '--output', str(out)],
                                  capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(out.read_text(), 'existing peer content')
            self.assertEqual(source.read_text(), SOURCE)


class SaleMechanism(unittest.TestCase):
    def test_current_suffix_not_baseline_or_cash_minimum(self):
        _, _, seen, _, _ = call([[], ['SELL', 'MILK', 5]], budget=1001)
        self.assertEqual(seen[0]['reference'], ((1, 0),))
        self.assertEqual(seen[0]['minimum_now'], 0)
        self.assertFalse(seen[0]['now_one'])

    def test_future_suffix_not_reference_or_slot_capacity(self):
        _, _, seen, _, _ = call([], future={2: [[], ['SELL', 'MILK', 5]]})
        self.assertEqual(seen[0]['reference'], ((1, 0),))
        self.assertFalse(seen[0]['future_one'])

    def test_pending_matches_only_executable_sales(self):
        output, state, _, _, _ = call([['SELL', 'MILK', 2], ['SELL', 'MILK', 3]])
        self.assertEqual(output['market'], [['SELL', 'MILK', 2], ['SELL', 'MILK', 3]])
        self.assertEqual(state.pending['MILK'], 3)

    def test_suffix_never_spends_remaining_or_erases_future_plan(self):
        planned = {'MILK': [(4, 5)]}
        output, state, _, _, _ = call([[], ['SELL', 'MILK', 50]], planned=planned)
        self.assertEqual(output['market'], [[], ['SELL', 'MILK', 50]])
        self.assertEqual(state.pending['MILK'], 5)
        self.assertEqual(state.planned, planned)

    def test_inert_suffix_is_opaque_and_nonmutated(self):
        for tail in (None, {'not': 'an order'}, 7, 'malformed', ['SELL'], ['SELL', 'MILK', 'bad']):
            with self.subTest(tail=tail):
                raw = [[], tail]
                output, state, _, _, _ = call(raw)
                self.assertEqual(output['market'], raw)
                self.assertEqual(state.pending['MILK'], 5)

    def test_blank_slots_not_compacted(self):
        output, state, seen, _, _ = call([[], [], ['SELL', 'MILK', 5]], cap=2)
        self.assertEqual(output['market'], [[], [], ['SELL', 'MILK', 5]])
        self.assertEqual(state.pending['MILK'], 5)
        self.assertFalse(seen[0]['now_stock'])

    def test_default_tenth_and_eleventh_boundary(self):
        raw = [[] for _ in range(9)] + [['SELL', 'MILK', 2], ['SELL', 'MILK', 3]]
        output, state, seen, _, _ = call(raw, cap=10)
        self.assertEqual(output['market'], raw)
        self.assertEqual(seen[0]['reference'], ((1, 2),))
        self.assertEqual(state.pending['MILK'], 3)

    def test_zero_and_negative_caps_keep_one_active_slot(self):
        for cap in (0, -2):
            with self.subTest(cap=cap):
                output, state, seen, _, _ = call([['SELL', 'MILK', 2], ['SELL', 'MILK', 3]], cap=cap)
                self.assertEqual(seen[0]['reference'], ((1, 2),))
                self.assertEqual(state.pending['MILK'], 3)
                self.assertEqual(output['market'][1], ['SELL', 'MILK', 3])
                self.assertTrue(seen[0]['now_one'])
                self.assertFalse(seen[0]['now_stock'])

    def test_min_one_cap_allows_append_to_empty_raw_queue(self):
        for cap in (0, -2):
            with self.subTest(cap=cap):
                output, state, seen, _, _ = call([], cap=cap, chosen=((1, 3),))
                self.assertTrue(seen[0]['now_stock'])
                self.assertEqual(output['market'], [['SELL', 'MILK', 3]])
                self.assertEqual(state.pending['MILK'], 2)

    def test_incap_valid_layouts_preserve_prior_method_behavior(self):
        tokens = ([], ['SELL', 'MILK', 1], ['SELL', 'MILK', 3], ['BUY_SEED', 'WHEAT', 1])
        for width in range(4):
            for layout in itertools.product(tokens, repeat=width):
                for cap in (max(1, width), 10):
                    raw = copy.deepcopy(list(layout))
                    before = call(raw, cap=cap, source=SOURCE)
                    after = call(raw, cap=cap)
                    self.assertEqual(before[0], after[0])
                    self.assertEqual(before[1].pending, after[1].pending)
                    self.assertEqual(before[1].planned, after[1].planned)
                    self.assertEqual(before[2], after[2])
                    COUNTS['incap_parity_cases'] += 1

    def test_actual_optimizer_rejects_capped_sale_reference(self):
        raw = [[], ['SELL', 'MILK', 5]]
        future = {t: raw for t in range(2, 10)}
        out, state, _, _, _ = call(raw, future=future, real_optimizer=True)
        evaluation = state.diagnostics['evaluations'][0]
        self.assertEqual(evaluation['reference'], [(1, 0)])
        self.assertTrue(evaluation['feasible'])
        self.assertEqual(state.pending['MILK'], 5)
        self.assertEqual(out['market'], raw)

    def test_predecessor_is_killed_by_independent_witnesses(self):
        failures = []
        before = call([[], ['SELL', 'MILK', 5]], budget=1001, source=SOURCE)
        failures.append(before[2][0]['reference'] != ((1, 0),))
        failures.append(before[2][0]['minimum_now'] != 0)
        failures.append(before[1].pending['MILK'] != 5)
        before = call([], future={2: [[], ['SELL', 'MILK', 5]]}, source=SOURCE)
        failures.append(before[2][0]['reference'] != ((1, 0),))
        failures.append(before[2][0]['future_one'] is not False)
        before = call([], cap=0, chosen=((1, 3),), source=SOURCE)
        failures.append(before[0]['market'] != [['SELL', 'MILK', 3]])
        self.assertEqual(failures, [True] * 6)


class OfficialMarket(unittest.TestCase):
    def test_emitted_prefix_pending_and_suffix_erasure_against_official_market(self):
        tokens = ([], ['SELL', 'MILK', 1], ['SELL', 'MILK', 3])
        for layout in itertools.product(tokens, repeat=3):
            for cap, seat, inventory in itertools.product((-2, 0, 1, 2, 3, 10), (0, 1), (10000, 10076)):
                raw = copy.deepcopy(list(layout))
                output, scheduler, _, states, cfg = call(raw, cap=cap, seat=seat, inventory=inventory)
                prefix = output['market'][:max(1, cap)]
                self.assertEqual(output['market'][max(1, cap):], raw[max(1, cap):])
                states[seat].action = copy.deepcopy(output)
                states[1 - seat].action = {'market': [['SELL', 'MILK', 2]]}
                control = copy.deepcopy(states)
                control[seat].action['market'] = copy.deepcopy(prefix)
                env = Struct(configuration=cfg)
                ENGINE._process_market(states, env)
                ENGINE._process_market(control, env)
                # Compare actual official market poststates, not action equality.
                for a, b in zip(states, control):
                    self.assertEqual(a.observation, b.observation)
                self.assertEqual(states[seat].observation.private['shed']['MILK'], scheduler.pending['MILK'])
                COUNTS['official_market_cases'] += 1


def initialize(package, scheduler_source=None):
    global PACKAGE, SOURCE, FIXED, ENGINE
    PACKAGE = package.resolve()
    source_path = scheduler_source if scheduler_source is not None else PACKAGE / 'scheduler.py'
    engine_path = PACKAGE / 'checks/reference/engine/kaggriculture.py'
    if source_path.is_symlink() or engine_path.is_symlink():
        raise ValueError('fixture source symlinks are not accepted')
    data = source_path.read_bytes()
    if blob(data) not in SOURCE_BLOBS:
        raise ValueError('unrecognized scheduler fixture blob: ' + blob(data))
    SOURCE = data.decode('utf-8')
    FIXED, _ = repair.rewrite_source(SOURCE)
    engine_data = engine_path.read_bytes()
    if blob(engine_data) != repair.ENGINE_BLOB:
        raise ValueError('official interpreter blob mismatch')
    engine_source = engine_data.decode('utf-8')
    import_line = 'from kaggle_environments.utils import resolve_episode_seed\n'
    if engine_source.count(import_line) != 1:
        raise ValueError('unexpected seed resolver import shape')
    # The external resolver is unrelated to market processing. Fail on use so
    # these tests cannot silently replace a seeded full interpreter execution.
    def unused_seed_resolver(*_args, **_kwargs):
        raise AssertionError('seed resolution is outside this market-phase test')
    ENGINE = types.ModuleType('pinned_official_sale_prefix')
    ENGINE.__file__ = str(engine_path)
    ENGINE.resolve_episode_seed = unused_seed_resolver
    exec(compile(engine_source.replace(import_line, '', 1), str(engine_path), 'exec'), ENGINE.__dict__)


def check_mutations():
    """Require behavioral assertion failures, not just source-pin rejection."""
    global FIXED
    original = FIXED
    rows = []
    try:
        for index, (old, new) in enumerate(repair.REPLACEMENTS, 1):
            if original.count(new) != 1:
                raise ValueError('mutation anchor cardinality mismatch')
            FIXED = original.replace(new, old, 1)
            compile(FIXED, '<behavior-mutant>', 'exec')
            suite = unittest.TestSuite([
                unittest.defaultTestLoader.loadTestsFromTestCase(SaleMechanism),
                unittest.defaultTestLoader.loadTestsFromTestCase(OfficialMarket),
            ])
            result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
            row = {'mutant': index, 'assertion_failures': len(result.failures),
                   'errors': len(result.errors), 'rejected': not result.wasSuccessful()}
            if not result.failures:
                raise AssertionError('mutant lacked a behavioral assertion failure: ' + str(row))
            rows.append(row)
    finally:
        FIXED = original
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-tree', required=True, type=Path)
    parser.add_argument('--scheduler-source', type=Path,
                        help='optional exact pinned donor/projection source; dependencies stay in package-tree')
    parser.add_argument('--mutation-check', action='store_true')
    args, unittest_args = parser.parse_known_args()
    initialize(args.package_tree, args.scheduler_source)
    program = unittest.main(argv=[sys.argv[0], *unittest_args], exit=False, verbosity=2)
    counts = dict(COUNTS)
    mutations = check_mutations() if args.mutation_check and program.result.wasSuccessful() else []
    print(json.dumps({'fixture_scheduler_blob': blob(SOURCE.encode()),
                      'official_engine_blob': repair.ENGINE_BLOB,
                      'tests_run': program.result.testsRun,
                      'success': program.result.wasSuccessful(),
                      'optimized': not __debug__, 'mutations': mutations, **counts}, sort_keys=True))
    sys.exit(0 if program.result.wasSuccessful() else 1)
