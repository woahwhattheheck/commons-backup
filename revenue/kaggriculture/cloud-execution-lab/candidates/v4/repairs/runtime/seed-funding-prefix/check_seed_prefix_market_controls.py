# SPDX-License-Identifier: Apache-2.0
"""Pinned actual-method/actual-seed-budget/official-market regression.

Accept separately supplied, hash-pinned baseline and candidate runtime files.
No patch generator or duplicate seed helper is included.
No full TitanAgent, producer, full-game runner or promotion is claimed. The exact
current _seed_selected method is extracted without importing unrelated runtime
code. post_units is an explicit PASS-only projection double; the budget, funding
certificate, price curves, market parser and all market commits are unmodified.
"""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

# Independent evidence runner: no repair, wrapper, donor or activation code.
METHOD_BEFORE_SHA256 = 'b3bf094820b77a7b871b017c78fdfa18ef3663c94970c96c2eb572e5c693ff01'


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def method_bytes(source):
    tree = ast.parse(source.decode('utf-8'))
    roots = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'TitanAgent']
    if len(roots) != 1:
        raise ValueError('expected exactly one TitanAgent class')
    targets = [n for n in roots[0].body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == '_seed_selected']
    if len(targets) != 1 or not isinstance(targets[0], ast.FunctionDef) or targets[0].decorator_list:
        raise ValueError('expected exactly one ordinary synchronous seed method')
    node = targets[0]
    return b''.join(source.splitlines(keepends=True)[node.lineno - 1:node.end_lineno])

PINS = {
    'engine': '3c202c7ee921da239356789e266b694635103fc4',
    'budget': 'eaa244ba05104535f9922a5f76d623a76c187096',
    'funding': '3d0c19cdf9f1260f56be3f6a7beb191b37b3d568',
    'suffix': '95d05ff28aa79074d82bdc08ce4148d3ace1b13d',
}
COUNTS = {'suffix_vectors': 0, 'engine_pairs': 0, 'active_prefix_controls': 0}
INPUTS = {}
SOURCE = b''
ENGINE = BUDGET = FUNDING = None
OLD = NEW = None


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compile_method(source):
    namespace = {'deepcopy': deepcopy}
    # Source extraction, not a reimplementation of the method under test.
    exec(compile(b'class Subject:\n' + method_bytes(source), '<exact-seed-method>', 'exec'), namespace)
    return namespace['Subject']._seed_selected


def fixture(seat=0, cash=35, step=2, cap=10):
    farms = [ENGINE._new_farm(10, cash), ENGINE._new_farm(10, cash)]
    market = ENGINE._new_market()
    state = []
    for player in range(2):
        private = ENGINE._new_private()
        obs = {'player': player, 'step': step, 'day': step // 24, 'hour': step % 24,
               'farms': farms, 'private': private, 'market': market,
               'town': {'unlocked_shops': []}}
        state.append(types.SimpleNamespace(observation=types.SimpleNamespace(**obs),
                     action={'farmer': ['PASS'], 'hands': [], 'market': []},
                     status='ACTIVE', reward=0))
    cfg = {'boardSize': 10, 'shedCapacity': 100, 'maxMarketOrdersPerTurn': cap,
           'farmHandCostMult': 1, 'episodeSteps': 720, 'turnsPerDay': 24}
    return state, types.SimpleNamespace(configuration=cfg), vars(state[seat].observation)


def invoke(method, obs, cfg, action, *, funding=True, seed=True, bound=0,
           crop='WHEAT', snapshot=True, extra=0):
    rows = [{'farmer': ['PASS'], 'hands': [], 'market': []}
            for _ in range(obs['step'] + 1)]
    rows.extend({'farmer': ['PLANT', crop], 'hands': [], 'market': []} for _ in range(bound))
    budget = BUDGET.SeedBudget({'test': rows})
    calls = {'projection': 0, 'funding': 0}
    scheduler = types.ModuleType('scheduler')
    scheduler.m = ENGINE
    def post_units(current, selected, config):
        calls['projection'] += 1
        if selected['farmer'] != ['PASS'] or any(x != ['PASS'] for x in selected['hands']):
            raise AssertionError('test projection is explicitly PASS-only')
        return deepcopy(current['farms'][current['player']]), deepcopy(current['private'])
    scheduler.post_units = post_units
    def funded(*args, **kwargs):
        calls['funding'] += 1
        return FUNDING.select_seed_queue(*args, **kwargs)
    spatial = None if not extra else types.SimpleNamespace(future_seed_requests=lambda step: {crop: extra})
    agent = types.SimpleNamespace(features=types.SimpleNamespace(seed=seed, funding=funding),
        consumer=types.SimpleNamespace(selected_post_units=(deepcopy(obs['farms'][obs['player']]),
                   deepcopy(obs['private'])) if snapshot else None),
        controller=types.SimpleNamespace(cur='test'), seed_budget=budget, spatial=spatial,
        funding_module=types.SimpleNamespace(select_seed_queue=funded), diagnostics={})
    with patch.dict(sys.modules, {'scheduler': scheduler}):
        result = method(agent, obs, cfg, action)
    return result, agent, calls


def action(rows):
    return {'farmer': ['PASS'], 'hands': [], 'market': deepcopy(rows), 'userdata': {'untouched': [1, 2]}}


def market_result(state, env, seat, own, rival=()):
    copied = deepcopy(state)
    copied[seat].action = deepcopy(own)
    copied[1-seat].action['market'] = deepcopy(list(rival))
    ENGINE._process_market(copied, env)
    return {'farms': copied[0].observation.farms,
            'private': [x.observation.private for x in copied],
            'market': copied[0].observation.market}


class SeedMarketControls(unittest.TestCase):
    def setUp(self):
        self.state, self.env, self.obs = fixture()
        self.cfg = self.env.configuration


    def test_09_disabled_identity_and_no_config_read(self):
        a = action([['BUY_SEED', 'WHEAT', 50]])
        r, _, c = invoke(NEW, self.obs, {'maxMarketOrdersPerTurn': object()}, a, seed=False)
        self.assertIs(r, a)
        self.assertEqual(c, {'projection': 0, 'funding': 0})

    def test_10_dead_seed_suffix_identity_no_projection(self):
        a = action([[]] * 10 + [['BUY_SEED', 'WHEAT', 50]])
        r, _, c = invoke(NEW, self.obs, self.cfg, a, snapshot=False)
        self.assertIs(r, a)
        self.assertEqual(c, {'projection': 0, 'funding': 0})

    def test_11_dead_capital_no_veto_funding_off(self):
        a = action([['BUY_SEED', 'WHEAT', 50]] + [[]] * 9 + [['HIRE']])
        r, _, c = invoke(NEW, self.obs, self.cfg, a, funding=False)
        self.assertEqual(r['market'][0], [])
        self.assertEqual(r['market'][10:], a['market'][10:])
        self.assertEqual(c['funding'], 0)

    def test_12_dead_capital_no_veto_funding_on(self):
        a = action([['BUY_SEED', 'WHEAT', 50]] + [[]] * 9 + [['BUY_LAND']])
        r, _, c = invoke(NEW, self.obs, self.cfg, a)
        self.assertEqual(r['market'][0], [])
        self.assertEqual(c['funding'], 0)

    def test_13_live_hire_still_vetoes_without_funding(self):
        a = action([['BUY_SEED', 'WHEAT', 50], ['HIRE']])
        r, _, _ = invoke(NEW, self.obs, self.cfg, a, funding=False)
        self.assertIs(r, a)

    def test_14_live_hire_still_needs_certificate(self):
        a = action([['BUY_SEED', 'WHEAT', 50], ['HIRE']])
        r, obj, c = invoke(NEW, self.obs, self.cfg, a)
        self.assertEqual(r, a)
        self.assertEqual(c['funding'], 1)
        self.assertEqual(obj.diagnostics['seed_funding']['reason'], 'original_queue_needs_additional_cash')

    def test_15_funded_live_hire_remains_certified(self):
        state, env, obs = fixture(cash=1000)
        a = action([['BUY_SEED', 'WHEAT', 50], ['HIRE']])
        r, obj, c = invoke(NEW, obs, env.configuration, a)
        self.assertEqual(r['market'], [[], ['HIRE']])
        self.assertEqual(c['funding'], 1)
        self.assertEqual(obj.diagnostics['seed_funding']['status'], 'certified')

    def test_16_seed_only_at_last_raw_slot(self):
        a = action([[]] * 9 + [['BUY_SEED', 'WHEAT', 50], ['HIRE']])
        r, _, _ = invoke(NEW, self.obs, self.cfg, a)
        self.assertEqual(r['market'][:10], [[]] * 10)
        self.assertEqual(r['market'][10:], [['HIRE']])

    def test_17_raw_empty_slots_are_not_compacted(self):
        a = action([[]] * 10 + [['BUY_SEED', 'WHEAT', 50], ['HIRE']])
        r, _, _ = invoke(NEW, self.obs, self.cfg, a)
        self.assertIs(r, a)
        result = market_result(self.state, self.env, 0, r)
        self.assertEqual(result['farms'][0]['money'], 35)
        self.assertEqual(result['private'][0]['seeds']['WHEAT'], 0)

    def test_18_engine_zero_cap_normalizes_to_one(self):
        a = action([['BUY_SEED', 'WHEAT', 50], ['HIRE']])
        state, env, obs = fixture(cap=0)
        r, _, _ = invoke(NEW, obs, env.configuration, a)
        self.assertEqual(r['market'], [[], ['HIRE']])
        base = market_result(state, env, 0, a)
        changed = market_result(state, env, 0, r)
        self.assertEqual(base['farms'][0]['money'], 5)
        self.assertEqual(changed['farms'][0]['money'], 35)
        self.assertEqual(changed['farms'][0]['hands'], [])

    def test_19_larger_config_executes_beyond_default_ten(self):
        state, env, obs = fixture(cap=12)
        a = action([[]] * 10 + [['BUY_SEED', 'WHEAT', 50], ['HIRE']])
        r, _, c = invoke(NEW, obs, env.configuration, a)
        self.assertEqual(r, a)
        self.assertEqual(c['funding'], 1)

    def test_20_future_demand_retained(self):
        a = action([['BUY_SEED', 'WHEAT', 50]] + [[]] * 9 + [['HIRE']])
        r, _, _ = invoke(NEW, self.obs, self.cfg, a, bound=2)
        self.assertEqual(r['market'][0], ['BUY_SEED', 'WHEAT', 2])

    def test_21_current_seed_stock_respected(self):
        self.obs['private']['seeds']['WHEAT'] = 1
        a = action([['BUY_SEED', 'WHEAT', 50]] + [[]] * 9 + [['HIRE']])
        r, _, _ = invoke(NEW, self.obs, self.cfg, a, bound=2)
        self.assertEqual(r['market'][0], ['BUY_SEED', 'WHEAT', 1])

    def test_22_extra_spatial_demand_respected(self):
        a = action([['BUY_SEED', 'WHEAT', 50]] + [[]] * 9 + [['HIRE']])
        r, _, _ = invoke(NEW, self.obs, self.cfg, a, bound=1, extra=2)
        self.assertEqual(r['market'][0], ['BUY_SEED', 'WHEAT', 3])

    def test_23_input_nonmutation_all_surfaces(self):
        a = action([['BUY_SEED', 'WHEAT', 50]] + [[]] * 9 + [['HIRE'], {'dead': [1, 2]}])
        saved = deepcopy((self.obs, self.cfg, a))
        invoke(NEW, self.obs, self.cfg, a)
        self.assertEqual((self.obs, self.cfg, a), saved)

    def test_24_dead_suffix_not_reinterpreted(self):
        a = action([['BUY_SEED', 'WHEAT', 50]] + [[]] * 9 + [None, 17, {'opaque': 4}, 'x'])
        r, _, _ = invoke(NEW, self.obs, self.cfg, a)
        self.assertEqual(r['market'][0], [])
        self.assertEqual(r['market'][10:], a['market'][10:])

    def test_25_suffix_equivalence_matrix(self):
        tails = [[['HIRE']], [['BUY_LAND']], [['BUY_PRODUCT', 'WHEAT', 1]],
                 [['BUY_ANIMAL', 'GOOSE', 1]], [['BUY_SEED', 'TOMATO', 99]],
                 [[], ['SELL', 'MILK', 2], ['HIRE']]]
        for seat, cap, crop, funded in itertools.product(range(2), (0, 1, 2, 3, 10, 12),
                                                         ('WHEAT', 'CARROT', 'TOMATO'), (False, True)):
            state, env, obs = fixture(seat=seat, cap=cap)
            n = max(1, cap)
            prefix = [['BUY_SEED', crop, 50]] + [[]] * (n - 1)
            reference, _, _ = invoke(NEW, obs, env.configuration, action(prefix), funding=funded, crop=crop)
            for tail in tails:
                with self.subTest(seat=seat, cap=cap, crop=crop, funding=funded, tail=tail):
                    a = action(prefix + tail)
                    result, obj, calls = invoke(NEW, obs, env.configuration, a, funding=funded, crop=crop)
                    self.assertEqual(result['market'][:n], reference['market'])
                    self.assertEqual(result['market'][n:], tail)
                    self.assertEqual(calls['funding'], 0)
                    for k in a:
                        if k != 'market':
                            self.assertEqual(result[k], a[k])
                    COUNTS['suffix_vectors'] += 1

    def test_26_positive_cap_live_prefix_compatibility_matrix(self):
        for seat, cap, cash, funded, bound in itertools.product(range(2), (1, 2, 3, 10, 12),
                                                               (0, 35, 1000), (False, True), (0, 1, 3)):
            state, env, obs = fixture(seat=seat, cap=cap, cash=cash)
            for rows in ([['BUY_SEED', 'WHEAT', 5]],
                         [['BUY_SEED', 'WHEAT', 5], ['HIRE']],
                         [['HIRE'], ['BUY_SEED', 'WHEAT', 5]],
                         [['BUY_SEED', 'WHEAT', 5], ['SELL', 'MILK', 1], ['BUY_LAND']]):
                # Compare unchanged executable input, with no out-of-budget suffix.
                a = action(rows[:cap])
                before, bobj, bc = invoke(OLD, obs, env.configuration, a, funding=funded, bound=bound)
                after, aobj, ac = invoke(NEW, obs, env.configuration, a, funding=funded, bound=bound)
                self.assertEqual(after, before)
                self.assertEqual(aobj.diagnostics, bobj.diagnostics)
                self.assertEqual(ac, bc)
                COUNTS['active_prefix_controls'] += 1

    def test_27_official_market_suffix_equivalence_both_seats(self):
        tails = [[['HIRE']], [['BUY_LAND']], [['BUY_PRODUCT', 'FERTILIZER', 4]],
                 [['BUY_ANIMAL', 'COW', 2]], [['SELL', 'MILK', 20]]]
        rivals = [[], [['SELL', 'MILK', 2]], [['HIRE']], [['BUY_SEED', 'CARROT', 1]]]
        for seat, cap, tail, rival in itertools.product(range(2), (0, 1, 3, 10, 12), tails, rivals):
            state, env, obs = fixture(seat=seat, cap=cap)
            for member in state:
                member.observation.private['shed']['MILK'] = 3
            n = max(1, cap)
            prefix = [['BUY_SEED', 'WHEAT', 50]] + [[]] * (n - 1)
            a = action(prefix)
            b = action(prefix + tail)
            self.assertEqual(market_result(state, env, seat, a, rival),
                             market_result(state, env, seat, b, rival))
            ra, _, _ = invoke(NEW, obs, env.configuration, a)
            rb, _, _ = invoke(NEW, obs, env.configuration, b)
            self.assertEqual(market_result(state, env, seat, ra, rival),
                             market_result(state, env, seat, rb, rival))
            COUNTS['engine_pairs'] += 2

    def test_28_current_method_defect_witness_with_real_cash(self):
        for seat in range(2):
            state, env, obs = fixture(seat=seat)
            a = action([['BUY_SEED', 'WHEAT', 50]] + [[]] * 9 + [['HIRE']])
            before, _, _ = invoke(OLD, obs, env.configuration, a)
            after, _, _ = invoke(NEW, obs, env.configuration, a)
            br = market_result(state, env, seat, before)
            ar = market_result(state, env, seat, after)
            self.assertEqual(br['farms'][seat]['money'], 5)
            self.assertEqual(ar['farms'][seat]['money'], 35)
            self.assertEqual(br['private'][seat]['seeds']['WHEAT'], 3)
            self.assertEqual(ar['private'][seat]['seeds']['WHEAT'], 0)
            # Removed seeds have no remaining authored planting demand; non-seed
            # state and the rival are unchanged. Cash is realized, not a quote.
            br['farms'][seat]['money'] = ar['farms'][seat]['money']
            br['private'][seat]['seeds']['WHEAT'] = ar['private'][seat]['seeds']['WHEAT']
            self.assertEqual(ar, br)
            COUNTS['engine_pairs'] += 1

    def test_29_projection_fallback_agrees_with_snapshot(self):
        a = action([['BUY_SEED', 'WHEAT', 50]] + [[]] * 9 + [['HIRE']])
        yes, _, yc = invoke(NEW, self.obs, self.cfg, a, snapshot=True)
        no, _, nc = invoke(NEW, self.obs, self.cfg, a, snapshot=False)
        self.assertEqual(yes, no)
        self.assertEqual(yc['projection'], 0)
        self.assertEqual(nc['projection'], 1)

    def test_30_same_slot_no_compaction_funded_execution(self):
        state, env, obs = fixture(cash=1000)
        a = action([['BUY_SEED', 'WHEAT', 5], [], ['HIRE']])
        r, _, _ = invoke(NEW, obs, env.configuration, a)
        self.assertEqual(r['market'], [[], [], ['HIRE']])
        br = market_result(state, env, 0, a, [['HIRE']])
        ar = market_result(state, env, 0, r, [['HIRE']])
        self.assertEqual(ar['farms'][0]['hands'], br['farms'][0]['hands'])
        self.assertEqual(ar['private'][1], br['private'][1])
        self.assertEqual(ar['farms'][0]['money'] - br['farms'][0]['money'], 50)


def main():
    global SOURCE, ENGINE, BUDGET, FUNDING, OLD, NEW, INPUTS
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'engine', 'budget', 'funding', 'suffix'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--candidate', required=True, type=Path)
    parser.add_argument('--candidate-git-blob', required=True, help='exact reviewed candidate runtime file SHA1')
    parser.add_argument('--predecessor', action='store_true', help='run new expectations against old method; must fail')
    args = parser.parse_args()
    try:
        SOURCE = args.runtime.read_bytes()
        if hashlib.sha256(method_bytes(SOURCE)).hexdigest() != METHOD_BEFORE_SHA256:
            raise ValueError('runtime method is not the exact reviewed preimage')
        INPUTS = {'runtime': {'git_blob': git_blob(SOURCE), 'method_sha256': METHOD_BEFORE_SHA256}}
        candidate = args.candidate.read_bytes()
        if git_blob(candidate) != args.candidate_git_blob:
            raise ValueError('candidate file pin mismatch')
        candidate_method = method_bytes(candidate)
        INPUTS['candidate'] = {'git_blob': git_blob(candidate), 'bytes': len(candidate),
                               'sha256': hashlib.sha256(candidate).hexdigest(),
                               'method_sha256': hashlib.sha256(candidate_method).hexdigest()}
        for name, expected in PINS.items():
            data = getattr(args, name).read_bytes()
            if git_blob(data) != expected:
                raise ValueError(f'{name} input pin mismatch')
            INPUTS[name] = {'git_blob': expected, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        suffix = load('plant_suffix', args.suffix)
        with patch.dict(sys.modules, {'plant_suffix': suffix}):
            BUDGET = load('_seed_prefix_budget', args.budget)
        FUNDING = load('_seed_prefix_funding', args.funding)
        kg = types.ModuleType('kaggle_environments')
        utils = types.ModuleType('kaggle_environments.utils')
        def no_rng(*args, **kwargs):
            raise AssertionError('initialized market fixtures must never resolve an episode seed')
        utils.resolve_episode_seed = no_rng
        with patch.dict(sys.modules, {'kaggle_environments': kg, 'kaggle_environments.utils': utils}):
            ENGINE = load('_seed_prefix_engine', args.engine)
        OLD = compile_method(SOURCE)
        NEW = OLD if args.predecessor else compile_method(candidate)
    except (OSError, ValueError, SyntaxError, ImportError) as error:
        parser.exit(2, f'{type(error).__name__}: {error}\n')
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SeedMarketControls))
    print(json.dumps({'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
                      'skips': len(result.skipped), 'predecessor': args.predecessor,
                      'counts': COUNTS, 'inputs': INPUTS,
                      'scope': 'exact_method_and_official_market_only',
                      'full_runtime_or_game': False}, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
