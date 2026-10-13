# SPDX-License-Identifier: Apache-2.0
"""Mandatory-input, real-current-class seed-prefix checks and full-engine pairs.

No full game or hosted runner is claimed. Consumer checkpoints and route rows are
constructed; the complete class, seed-budget, funding and engine code are real.
"""
from __future__ import annotations
import argparse
import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

# The incumbent owns the implementation. This file carries no repair code.
PREDECESSOR_RUNTIME_BLOB = "b952c9c228ecbde592bf3d2df01638677abb0d24"
REPAIR_BLOB = "a5c2c131fd83d83d6be822556abce5723b464a50"
REPAIRED_METHOD_SHA256 = "2aef22adfe3dd46782b71f9c6fefb4f4c38b2d8a8671766ea8e395b1adebeab6"
REPAIR = None
RUNTIME_TREE_SHA256 = '7c840c4657f83815415836b6b2649b2661c3d8e5e608db8cbc417ef2f576056e'
RUNTIME_TREE_FILES = 110


def transform(source):
    return REPAIR.repair(source.encode('utf-8')).decode('utf-8')

PINS = {
    'frozen_selected.py': 'fc7baf5c179818a55037f6a61d92984d81d1a21c',
    'mechanics.py': '044a4f9c0a4a44dde10ada57563238bcaf82075d',
    'checks/reference/evaluator/evaluate.py': '1fb6b655bb4ca1e1684be165a8ef513e2e6c2325',
    'checks/reference/evaluator/loader.py': '23948e10cfc3d32f46c9abb1321b0d8fc8db21d5',
    'reference/next-panel/vendor/arlene.py': 'bdb9cf58148a3c7961c085f4902759537decabf6',
    'reference/titan-current/deadline_adapter.py': '664aa4f8a21368c388dfa6714406519b6535ef7f',
    'titan_runtime.py': 'b952c9c228ecbde592bf3d2df01638677abb0d24',
    'reference/integrated-selected/alder/seed_budget.py': 'eaa244ba05104535f9922a5f76d623a76c187096',
    'reference/titan-current/seed_funding.py': '3d0c19cdf9f1260f56be3f6a7beb191b37b3d568',
    'plant_suffix.py': '95d05ff28aa79074d82bdc08ce4148d3ace1b13d',
    'scheduler.py': 'a483b24dd72b580d7d8811636b54d2d44f391575',
    'checks/reference/engine/kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
    'checks/reference/engine/kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
    'checks/reference/engine/utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
}
COUNTS = {'suffix_action_cells': 0, 'full_engine_suffix_pairs': 0,
          'full_engine_cash_witness_pairs': 0, 'full_interpreter_calls': 0,
          'compatibility_cells': 0, 'real_dispatch_cases': 0}
ROOT = SOURCE = CURRENT = BASELINE = BUDGET = FUNDING = EV = ENGINE = None


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f'cannot load {path}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def runtime(source, name):
    module = ModuleType(name)
    # Full source executes against the supplied real package dependencies.
    module.__file__ = str(ROOT / 'titan_runtime.py')
    sys.modules[name] = module
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    return module


def action(market=(), farmer=('PASS',), hands=()):
    return {'farmer': list(farmer), 'hands': deepcopy(list(hands)),
            'market': deepcopy(list(market))}


def fixture(seat=0, cash=8, maximum=10, step=1):
    S, e = EV.Struct, ENGINE
    cfg = S({k: v.get('default') if isinstance(v, dict) else v
             for k, v in e.specification['configuration'].items()})
    cfg.weedSpawnChance = 0
    cfg.maxMarketOrdersPerTurn = maximum
    farms = [e._new_farm(10, cash), e._new_farm(10, cash)]
    market = e._new_market()
    e._refresh_prices(market)
    town = {'unlocked_shops': []}
    state = [S(observation=S(player=i, step=step, day=step // 24,
                           hour=step % 24, farms=farms, private=e._new_private(),
                           market=market, town=town),
               action=action(), status='ACTIVE', reward=0) for i in range(2)]
    return state, S(configuration=cfg, done=False, info={'seed': 9600803})


def make_agent(obs, module=None, *, funding=True, seed=True, requests=1, crop='WHEAT',
               snapshot=True, extras=None):
    module = module or CURRENT
    instance = module.TitanAgent(module.Features(seed=seed, funding=funding))
    route = [action() for _ in range(int(obs['step']) + 1)]
    route += [action(farmer=('PLANT', crop)) for _ in range(requests)]
    instance.seed_budget = BUDGET.SeedBudget({'route': route})
    instance.controller = SimpleNamespace(cur='route')
    pair = (deepcopy(obs['farms'][obs['player']]), deepcopy(obs['private']))
    instance.consumer = SimpleNamespace(selected_post_units=pair if snapshot else None)
    instance.funding_module = FUNDING
    instance.spatial = None if extras is None else SimpleNamespace(
        future_seed_requests=lambda _step: deepcopy(extras))
    return instance


def select(obs, cfg, chosen, **kwargs):
    instance = make_agent(obs, **kwargs)
    return instance._seed_selected(obs, cfg, chosen), instance


def view(state, env):
    # Submitted action fields legitimately differ. Compare *all* resulting
    # observations, statuses, rewards and environment state, not selected totals.
    return {'states': [{k: deepcopy(v) for k, v in s.items() if k != 'action'}
                       for s in state], 'env': deepcopy(env)}


def run_pair(state, env, seat, left, right, rival=None):
    lstate, lenv = deepcopy((state, env))
    rstate, renv = deepcopy((state, env))
    for states, config, chosen in ((lstate, lenv, left), (rstate, renv, right)):
        states[seat].action = deepcopy(chosen)
        states[1-seat].action = action() if rival is None else deepcopy(rival)
        ENGINE.interpreter(states, config)
        COUNTS['full_interpreter_calls'] += 1
    return view(lstate, lenv), view(rstate, renv)


class SourceRepair(unittest.TestCase):
    def test_exact_predecessor_and_idempotency(self):
        self.assertEqual(blob(SOURCE.encode()), PREDECESSOR_RUNTIME_BLOB)
        repaired = transform(SOURCE)
        self.assertNotEqual(repaired, SOURCE)
        self.assertEqual(transform(repaired), repaired)
        cls = next(n for n in ast.parse(repaired).body
                   if isinstance(n, ast.ClassDef) and n.name == 'TitanAgent')
        method = next(n for n in cls.body if getattr(n, 'name', None) == '_seed_selected')
        lines = repaired.splitlines(keepends=True)
        method_text = ''.join(lines[method.lineno-1:method.end_lineno])
        self.assertEqual(hashlib.sha256(method_text.encode()).hexdigest(), REPAIRED_METHOD_SHA256)

    def test_all_other_ast_members_unchanged(self):
        def except_seed(source):
            tree = ast.parse(source)
            for cls in tree.body:
                if isinstance(cls, ast.ClassDef) and cls.name == 'TitanAgent':
                    cls.body = [n for n in cls.body if getattr(n, 'name', None) != '_seed_selected']
            return ast.dump(tree, include_attributes=False)
        self.assertEqual(except_seed(SOURCE), except_seed(transform(SOURCE)))

    def test_unrelated_peer_change_survives_byte_exact(self):
        source = SOURCE.replace('    def _operating_stock_selected',
                                '    # peer-owned prefix seam stays intact\n    def _operating_stock_selected')
        self.assertIn('# peer-owned prefix seam stays intact', transform(source))
        before = SOURCE.index('    def _seed_selected')
        after = SOURCE.index('    def _operating_stock_selected')
        repaired = transform(SOURCE)
        self.assertEqual(repaired[:before], SOURCE[:before])
        self.assertTrue(repaired.endswith(SOURCE[after:]))



class SeedBoundary(unittest.TestCase):
    def test_seed_disabled_remains_identity_without_config_parse(self):
        state, env = fixture()
        chosen = action([['BUY_SEED', 'WHEAT', 99]])
        result, _ = select(state[0].observation, {'maxMarketOrdersPerTurn': 'invalid'}, chosen, seed=False)
        self.assertIs(result, chosen)

    def test_seed_only_in_dead_tail_skips_projection(self):
        state, env = fixture()
        chosen = action([[] for _ in range(10)] + [['BUY_SEED', 'WHEAT', 10]])
        inst = make_agent(state[0].observation, snapshot=False)
        with patch('scheduler.post_units', side_effect=AssertionError('dead tail projected')):
            self.assertIs(inst._seed_selected(state[0].observation, env.configuration, chosen), chosen)

    def test_dead_capital_tail_cannot_block_seed_reduction(self):
        for seat in (0, 1):
            for funding in (False, True):
                for operation in (['HIRE'], ['BUY_LAND'], ['BUY_PRODUCT', 'WHEAT', 1],
                                  ['BUY_ANIMAL', 'COW', 1]):
                    state, env = fixture(seat=seat)
                    selected = action([['BUY_SEED', 'WHEAT', 10]] + [[] for _ in range(9)] + [operation])
                    saved = deepcopy((state, env, selected))
                    result, inst = select(state[seat].observation, env.configuration, selected, funding=funding)
                    with self.subTest(seat=seat, funding=funding, operation=operation):
                        self.assertEqual(result['market'][0], ['BUY_SEED', 'WHEAT', 1])
                        self.assertEqual(result['market'][10:], selected['market'][10:])
                        self.assertNotIn('seed_funding', inst.diagnostics)
                        self.assertEqual((state, env, selected), saved)

    def test_active_capital_keeps_existing_funding_gate(self):
        for funding in (False, True):
            state, env = fixture(cash=1)
            selected = action([['BUY_SEED', 'WHEAT', 10], ['HIRE']])
            result, inst = select(state[0].observation, env.configuration, selected, funding=funding)
            self.assertEqual(result, selected)
            if funding:
                self.assertEqual(inst.diagnostics['seed_funding']['status'], 'not_certified')
            else:
                self.assertNotIn('seed_funding', inst.diagnostics)

    def test_funded_active_capital_uses_real_certificate(self):
        state, env = fixture(cash=10000)
        selected = action([['BUY_SEED', 'WHEAT', 10], ['HIRE']])
        result, inst = select(state[0].observation, env.configuration, selected)
        self.assertEqual(result['market'][0], ['BUY_SEED', 'WHEAT', 1])
        self.assertEqual(inst.diagnostics['seed_funding']['status'], 'certified')
        self.assertEqual(inst.diagnostics['seed_funding']['edited_slots'], [0])

    def test_prior_capital_is_not_later_dependency(self):
        state, env = fixture(cash=1)
        chosen = action([['HIRE'], ['BUY_SEED', 'WHEAT', 10]])
        result, inst = select(state[0].observation, env.configuration, chosen, funding=False)
        self.assertEqual(result['market'][1], ['BUY_SEED', 'WHEAT', 1])
        self.assertNotIn('seed_funding', inst.diagnostics)

    def test_default_order_limit(self):
        state, env = fixture()
        cfg = dict(env.configuration)
        cfg.pop('maxMarketOrdersPerTurn')
        chosen = action([['BUY_SEED', 'WHEAT', 10]] + [[]]*9 + [['HIRE']])
        result, _ = select(state[0].observation, cfg, chosen, funding=False)
        self.assertEqual(result['market'][0], ['BUY_SEED', 'WHEAT', 1])

    def test_zero_and_negative_limit_match_engine_minimum_one(self):
        for maximum in (-2, -1, 0):
            state, env = fixture(maximum=maximum)
            chosen = action([['BUY_SEED', 'WHEAT', 10], ['HIRE'], ['BUY_SEED', 'WHEAT', 20]])
            result, _ = select(state[0].observation, env.configuration, chosen, funding=False)
            with self.subTest(maximum=maximum):
                self.assertEqual(result['market'][0], ['BUY_SEED', 'WHEAT', 1])
                self.assertEqual(result['market'][1:], chosen['market'][1:])

    def test_configured_limit_above_ten_is_not_hard_capped(self):
        state, env = fixture(maximum=12)
        chosen = action([[]]*10 + [['BUY_SEED', 'WHEAT', 10], [] , ['HIRE']])
        result, _ = select(state[0].observation, env.configuration, chosen, funding=False)
        self.assertEqual(result['market'][10], ['BUY_SEED', 'WHEAT', 1])
        self.assertEqual(result['market'][12:], chosen['market'][12:])

    def test_multiple_seed_edits_preserve_raw_positions(self):
        state, env = fixture()
        chosen = action([[], ['BUY_SEED', 'WHEAT', 10], [], ['BUY_SEED', 'CARROT', 5]] + [[]]*6 + [['HIRE']])
        result, _ = select(state[0].observation, env.configuration, chosen, funding=False)
        self.assertEqual(result['market'], [[], ['BUY_SEED', 'WHEAT', 1], [], []] + [[]]*6 + [['HIRE']])

    def test_real_projection_without_completed_snapshot(self):
        state, env = fixture()
        chosen = action([['BUY_SEED', 'WHEAT', 10]] + [[]]*9 + [['HIRE']])
        result, _ = select(state[0].observation, env.configuration, chosen, snapshot=False)
        self.assertEqual(result['market'][0], ['BUY_SEED', 'WHEAT', 1])

    def test_current_seed_stock_and_spatial_extra_requests_retained(self):
        state, env = fixture()
        state[0].observation.private['seeds']['WHEAT'] = 2
        chosen = action([['BUY_SEED', 'WHEAT', 10]] + [[]]*9 + [['HIRE']])
        result, _ = select(state[0].observation, env.configuration, chosen,
                           requests=3, extras={'WHEAT': 2})
        self.assertEqual(result['market'][0], ['BUY_SEED', 'WHEAT', 3])

    def test_fully_redundant_seed_slot_remains_empty_not_removed(self):
        state, env = fixture()
        chosen = action([[], ['BUY_SEED', 'WHEAT', 10], []] + [[]]*7 + [['HIRE']])
        result, _ = select(state[0].observation, env.configuration, chosen, requests=0)
        self.assertEqual(len(result['market']), len(chosen['market']))
        self.assertEqual(result['market'][:10], [[]]*10)
        self.assertEqual(result['market'][10:], [['HIRE']])

    def test_adversarial_dead_suffix_is_unexamined_and_detached(self):
        state, env = fixture()
        suffix = [3, None, {'ignored': ['HIRE']}, ['BUY_PRODUCT'], ['BUY_SEED', 'INVALID', None]]
        chosen = action([['BUY_SEED', 'WHEAT', 10]] + [[]]*9 + suffix)
        saved = deepcopy(chosen)
        result, _ = select(state[0].observation, env.configuration, chosen)
        self.assertEqual(result['market'][0], ['BUY_SEED', 'WHEAT', 1])
        self.assertEqual(result['market'][10:], suffix)
        result['market'][12]['ignored'].append('probe')
        self.assertEqual(chosen, saved)

    def test_active_prefix_compatibility_with_predecessor(self):
        for cash in (0, 1, 8, 10000):
            for maximum in (1, 2, 5, 10, 12):
                for funding in (False, True):
                    for orders in ([], [['BUY_SEED', 'WHEAT', 8]],
                                   [['BUY_SEED', 'WHEAT', 8], ['HIRE']],
                                   [['HIRE'], ['BUY_SEED', 'WHEAT', 8]]):
                        state, env = fixture(cash=cash, maximum=maximum)
                        chosen = action(orders[:maximum])
                        left, li = select(state[0].observation, env.configuration, chosen, funding=funding)
                        right, ri = select(state[0].observation, env.configuration, chosen, module=BASELINE, funding=funding)
                        self.assertEqual(left, right)
                        self.assertEqual(li.diagnostics, ri.diagnostics)
                        COUNTS['compatibility_cells'] += 1

    def test_suffix_action_property_grid(self):
        suffixes = ([['HIRE']], [['BUY_LAND']], [['BUY_PRODUCT', 'WHEAT', 1]],
                    [['BUY_ANIMAL', 'COW', 1]], [[], ['BUY_SEED', 'WHEAT', 40]],
                    [['HIRE'], ['BUY_PRODUCT', 'WHEAT', 3], [], ['BUY_LAND']])
        for seat in (0, 1):
            for maximum in (1, 2, 5, 10, 12):
                for cash in (0, 1, 8, 10000):
                    for funding in (False, True):
                        for suffix in suffixes:
                            state, env = fixture(seat=seat, cash=cash, maximum=maximum)
                            prefix = [['BUY_SEED', 'WHEAT', 10]] + [[]]*(maximum-1)
                            chosen = action(prefix + suffix)
                            expected, ei = select(state[seat].observation, env.configuration, action(prefix), funding=funding)
                            actual, ai = select(state[seat].observation, env.configuration, chosen, funding=funding)
                            with self.subTest(seat=seat, limit=maximum, cash=cash, funding=funding, suffix=suffix):
                                self.assertEqual(actual['market'][:maximum], expected['market'])
                                self.assertEqual(actual['market'][maximum:], suffix)
                                self.assertEqual(actual['farmer'], chosen['farmer'])
                                self.assertEqual(actual['hands'], chosen['hands'])
                                self.assertEqual(ai.diagnostics, ei.diagnostics)
                            COUNTS['suffix_action_cells'] += 1

    def test_real_frozen_dispatch_and_route_bound_no_consumer_doubles(self):
        # Actual initialization, FrozenSelected.transform and own-route budget.
        # Only the public observation and explicitly supplied chosen action are
        # constructed. This is not a natural producer-action occurrence claim.
        for seat in (0, 1):
            for funding in (False, True):
                candidate = CURRENT.TitanAgent(CURRENT.Features(seed=True, funding=funding))
                original = BASELINE.TitanAgent(BASELINE.Features(seed=True, funding=funding))
                candidate._initialize()
                original._initialize()
                self.assertEqual(candidate.consumer.__class__.__name__, 'FrozenSelected')
                self.assertEqual(candidate.controller.cur, original.controller.cur)
                state, env = fixture(seat=seat, cash=35, step=1)
                obs = state[seat].observation
                reserve = candidate.seed_budget.remaining('WHEAT', 1, candidate.controller.cur)
                self.assertEqual(reserve, original.seed_budget.remaining('WHEAT', 1, original.controller.cur))
                self.assertGreater(reserve, 0)
                obs.private['seeds']['WHEAT'] = reserve
                chosen = action([['BUY_SEED', 'WHEAT', 10]] + [[]]*9 + [['HIRE']])
                before = deepcopy((state, env, chosen))
                repaired = candidate.transform_selected(obs, env.configuration, chosen)
                baseline = original.transform_selected(obs, env.configuration, chosen)
                left, right = run_pair(state, env, seat, repaired, baseline)
                with self.subTest(seat=seat, funding=funding):
                    self.assertEqual((state, env, chosen), before)
                    self.assertEqual(repaired['market'], [[]]*10 + [['HIRE']])
                    self.assertEqual(baseline['market'], chosen['market'])
                    self.assertNotIn('seed_funding', candidate.diagnostics)
                    self.assertEqual(left['states'][seat]['observation']['private']['seeds']['WHEAT'], reserve)
                    self.assertEqual(right['states'][seat]['observation']['private']['seeds']['WHEAT'], reserve+3)
                    for item in left['states']:
                        self.assertEqual(item['observation']['farms'][seat]['money'], 35)
                        item['observation']['farms'][seat]['money'] = 5
                    left['states'][seat]['observation']['private']['seeds']['WHEAT'] = reserve+3
                    self.assertEqual(left, right)
                COUNTS['real_dispatch_cases'] += 1


class OfficialEngine(unittest.TestCase):
    def test_full_callback_suffix_invariance_both_seats(self):
        for seat in (0, 1):
            for maximum in (1, 2, 5, 10, 12):
                for cash in (0, 1, 8, 10000):
                    for funding in (False, True):
                        for operation in (['HIRE'], ['BUY_LAND'], ['BUY_PRODUCT', 'WHEAT', 2],
                                          ['BUY_ANIMAL', 'COW', 1]):
                            state, env = fixture(seat=seat, cash=cash, maximum=maximum)
                            prefix = [['BUY_SEED', 'WHEAT', 10]] + [[]]*(maximum-1)
                            left, _ = select(state[seat].observation, env.configuration,
                                             action(prefix + [operation]), funding=funding)
                            right, _ = select(state[seat].observation, env.configuration,
                                              action(prefix), funding=funding)
                            a, b = run_pair(state, env, seat, left, right,
                                            rival=action([['BUY_SEED', 'CARROT', 2], ['HIRE']]))
                            with self.subTest(seat=seat, limit=maximum, cash=cash, funding=funding, operation=operation):
                                self.assertEqual(a, b)
                            COUNTS['full_engine_suffix_pairs'] += 1

    def test_full_callback_savings_preserve_required_seed_bound(self):
        for seat in (0, 1):
            for funding in (False, True):
                for crop in ('WHEAT', 'CARROT', 'TOMATO', 'STRAWBERRY'):
                    cost = ENGINE.CROPS[crop]['seed']
                    state, env = fixture(seat=seat, cash=cost*3)
                    chosen = action([['BUY_SEED', crop, 10]] + [[]]*9 + [['HIRE']])
                    repaired, _ = select(state[seat].observation, env.configuration, chosen,
                                         funding=funding, crop=crop, requests=1)
                    original, _ = select(state[seat].observation, env.configuration, chosen,
                                         module=BASELINE, funding=funding, crop=crop, requests=1)
                    left, right = run_pair(state, env, seat, repaired, original)
                    with self.subTest(seat=seat, funding=funding, crop=crop):
                        self.assertEqual(left['states'][seat]['observation']['private']['seeds'][crop], 1)
                        self.assertEqual(right['states'][seat]['observation']['private']['seeds'][crop], 3)
                        for item in left['states']:
                            self.assertEqual(item['observation']['farms'][seat]['money'], cost*2)
                            item['observation']['farms'][seat]['money'] = 0
                        self.assertEqual(right['states'][seat]['observation']['farms'][seat]['money'], 0)
                        left['states'][seat]['observation']['private']['seeds'][crop] = 3
                        self.assertEqual(left, right)
                    COUNTS['full_engine_cash_witness_pairs'] += 1

    def test_engine_minimum_one_and_more_than_ten_slots(self):
        for maximum in (-2, 0, 1, 12):
            for seat in (0, 1):
                state, env = fixture(seat=seat, cash=1000, maximum=maximum)
                live = max(1, maximum)
                chosen = action([[]]*(live-1) + [['BUY_SEED', 'WHEAT', 10], ['HIRE']])
                actual, _ = select(state[seat].observation, env.configuration, chosen, funding=False)
                expected = action([[]]*(live-1) + [['BUY_SEED', 'WHEAT', 1]])
                left, right = run_pair(state, env, seat, actual, expected)
                with self.subTest(seat=seat, maximum=maximum):
                    self.assertEqual(left, right)


def main():
    global ROOT, SOURCE, CURRENT, BASELINE, BUDGET, FUNDING, EV, ENGINE, REPAIR
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--repair-source', type=Path, default=Path(__file__).with_name('repair_seed_funding_prefix.py'))
    parser.add_argument('--predecessor', action='store_true', help='negative control: unchanged current runtime')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    ROOT = args.runtime_root.resolve()
    verified = {}
    try:
        tree_rows = []
        for path in sorted(ROOT.rglob('*')):
            if not path.is_file() or '__pycache__' in path.parts or path.suffix == '.pyc':
                continue
            data = path.read_bytes()
            tree_rows.append([path.relative_to(ROOT).as_posix(), len(data), hashlib.sha256(data).hexdigest()])
        tree_sha = hashlib.sha256(json.dumps(tree_rows, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
        if len(tree_rows) != RUNTIME_TREE_FILES or tree_sha != RUNTIME_TREE_SHA256:
            raise ValueError(f'complete runtime tree drift: {len(tree_rows)} files / {tree_sha}')
        repair_bytes = args.repair_source.read_bytes()
        if blob(repair_bytes) != REPAIR_BLOB:
            raise ValueError(f'incumbent repair drift: {blob(repair_bytes)} != {REPAIR_BLOB}')
        REPAIR = load(args.repair_source, '_seed_prefix_incumbent_repair')
        for name, pin in PINS.items():
            data = (ROOT/name).read_bytes()
            if blob(data) != pin:
                raise ValueError(f'source drift: {name}: {blob(data)} != {pin}')
            verified[name] = {'git_blob': pin, 'bytes': len(data),
                              'sha256': hashlib.sha256(data).hexdigest()}
        SOURCE = (ROOT/'titan_runtime.py').read_bytes().decode('utf-8')
        sys.path.insert(0, str(ROOT))
        BASELINE = runtime(SOURCE, '_seed_prefix_baseline')
        CURRENT = BASELINE if args.predecessor else runtime(transform(SOURCE), '_seed_prefix_repaired')
        BUDGET = load(ROOT/'reference/integrated-selected/alder/seed_budget.py', '_seed_prefix_budget')
        FUNDING = load(ROOT/'reference/titan-current/seed_funding.py', '_seed_prefix_funding')
        EV = load(ROOT/'checks/reference/evaluator/evaluate.py', '_seed_prefix_evaluator')
        ENGINE, _ = EV.get_engine(ROOT/'checks/reference/engine',
                                 ROOT/'checks/reference/evaluator/loader.py', prepare=False)
        __import__('scheduler')
    except (OSError, ValueError, ImportError, SyntaxError) as error:
        parser.exit(2, f'mandatory source input: {error}\n')
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'schema': 'titan-seed-prefix-check/v1', 'python': sys.version,
              'optimized': sys.flags.optimize, 'mode': 'predecessor' if args.predecessor else 'repair',
              'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
              'skips': len(result.skipped), 'passed': result.wasSuccessful(), 'counts': COUNTS,
              'source_pins': verified, 'incumbent_repair_git_blob': REPAIR_BLOB, 'runtime_tree_sha256': tree_sha, 'runtime_tree_files': len(tree_rows), 'tested_runtime_git_blob': blob((SOURCE if args.predecessor else transform(SOURCE)).encode()),
              'full_games_run': 0, 'hosted_runner': False, 'production_modified': False,
              'limits': ['constructed route rows and consumer checkpoints',
                         'full class method with real budget/funding/scheduler collaborators',
                         'four real initialized FrozenSelected dispatcher controls with constructed selected actions',
                         'full official callbacks, not natural-route engagement or economic promotion']}
    if args.report:
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
