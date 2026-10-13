#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline, exact-byte scheduler composition gate; full modules and interpreter.

Run with a package containing the pinned dependencies and the existing legacy
three-consumer candidate. Inputs are read-only; all imports run in a temporary
package. This is component evidence, not current TITAN runtime or field strength.
"""
from __future__ import annotations
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import sys
import tempfile
import unittest

PINS = {
    'mechanics.py': '044a4f9c0a4a44dde10ada57563238bcaf82075d',
    'observed_clone.py': 'f810d53193d3035655a36c21021e18ba1d415916',
    'reference/decision/decision.py': '2931aa55831204fbb473ab85a6f5b81ec947fcf7',
    'reference/next-panel/vendor/arlene.py': 'bdb9cf58148a3c7961c085f4902759537decabf6',
    'checks/reference/evaluator/loader.py': '23948e10cfc3d32f46c9abb1321b0d8fc8db21d5',
    'checks/reference/engine/kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
    'checks/reference/engine/kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
    'checks/reference/engine/utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
}
SOURCE = 'a483b24dd72b580d7d8811636b54d2d44f391575'
TRANSFORMER = '2958bff92c7d95d9e113b2406e7de1bb7a28de08'
CANDIDATE = '742a200e9a72e303ad18c51c104895013a7f3a4b'
LEGACY = '4dcf25f0a1a68f6842b71c6cb58ee878c06f6a08'
COUNTS = {}


def blob(data):
    return hashlib.sha1(f'blob {len(data)}\0'.encode('ascii') + data).hexdigest()


def checked(path, expected):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'input is not a regular non-symlink file: {path}')
    data = path.read_bytes()
    if blob(data) != expected:
        raise ValueError(f'Git blob mismatch: {path}: {blob(data)} != {expected}')
    return data


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def action(market=(), farmer=('PASS',), hands=()):
    return {'farmer': list(farmer), 'hands': copy.deepcopy(list(hands)),
            'market': copy.deepcopy(list(market))}


class FixedRoute:
    """Authored-route fixture only; no market/physics/optimizer substitutes."""
    def __init__(self, base, future=None):
        self.base = copy.deepcopy(base)
        self.cur = 0
        self.R = [[action() for _ in range(720)]]
        for step, row in (future or {}).items():
            self.R[0][step] = copy.deepcopy(row)

    def act(self, obs):
        return copy.deepcopy(self.base)


class Composition(unittest.TestCase):
    def fixture(self, seat=0, step=23, item='MILK', stock=4, cap=1, cash=1000):
        e, S = self.engine, self.loader.Struct
        cfg = S({k: v.get('default') if isinstance(v, dict) else v
                 for k, v in e.specification['configuration'].items()})
        cfg.weedSpawnChance = 0
        cfg.maxMarketOrdersPerTurn = cap
        farms = [e._new_farm(10, cash), e._new_farm(10, cash)]
        market = e._new_market()
        town = {'unlocked_shops': []}
        state = []
        for i in range(2):
            private = e._new_private()
            private['shed'][item] = stock if i == seat else 0
            state.append(S(observation=S(player=i, step=step, day=step // 24,
                hour=step % 24, farms=farms, private=private, market=market, town=town),
                action=action(), status='ACTIVE', reward=0))
        return state, S(configuration=cfg, done=False, info={'seed': 9600803})

    def controller(self, base, future=None, module=None):
        c = (module or self.subject).SellScheduler()
        c.controller = FixedRoute(base, future)
        return c

    def step(self, state, env):
        COUNTS['interpreter_calls'] = COUNTS.get('interpreter_calls', 0) + 1
        return self.engine.interpreter(state, env)

    def test_source_composition_is_one_current_transform(self):
        self.assertEqual(blob(self.transformer.transform(self.source_bytes)), CANDIDATE)
        for wrong in (self.source_bytes+b'\n', self.candidate_bytes, self.legacy_bytes):
            with self.assertRaises(ValueError):
                self.transformer.transform(wrong)
        tree = ast.parse(self.candidate_bytes)
        names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
        self.assertEqual(names.count('_engine_market_prefix'), 1)
        self.assertNotIn('_receipt_market_prefix', names)
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == '_engine_market_prefix']
        self.assertEqual(len(calls), 6)
        before = {n.name: ast.dump(n) for n in ast.parse(self.source_bytes).body
                  if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        after = {n.name: ast.dump(n) for n in tree.body
                 if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        for name in before.keys() - {'SellScheduler'}:
            self.assertEqual(before[name], after[name], name)
        self.assertEqual(self.candidate.m.__file__, str(self.root/'mechanics.py'))
        self.assertTrue(callable(self.candidate.parent.Agent))
        self.assertTrue(callable(self.candidate.receipt_math.sale_receipts))

    def test_capped_sells_keep_stock_and_future_plans(self):
        count = 0
        for seat in (0, 1):
            for cap in (-2, 0, 1, 2, 10):
                for item in ('MILK', 'WOOL', 'TOMATO', 'EGG'):
                    for stock in (1, 4, 7):
                        with self.subTest(seat=seat, cap=cap, item=item, stock=stock):
                            state, env = self.fixture(seat, item=item, stock=stock, cap=cap)
                            base = action([[]]*max(1, cap) + [['SELL', item, stock]])
                            c = self.controller(base)
                            c.planned = {item: [(24, stock)]}
                            obs = state[seat].observation
                            saved = copy.deepcopy(obs)
                            state[seat].action = c.act(obs, env.configuration)
                            self.assertEqual(obs, saved)
                            self.assertEqual(state[seat].action, base)
                            self.step(state, env)
                            self.assertEqual(state[seat].observation.private['shed'][item], stock)
                            self.assertEqual(c.pending[item], stock)
                            self.assertEqual(c.planned[item], [(24, stock)])
                            count += 1
        COUNTS['capped_sell_cells'] = count

    def test_ignored_malformed_suffix_is_not_parsed(self):
        for tail in ([None], [7], [{'noise': True}], [['SELL']],
                     [['BUY_ANIMAL', 'GOOSE', 100], ['SELL', 'MILK', 999]]):
            with self.subTest(tail=tail):
                state, env = self.fixture()
                base = action([[]]+tail)
                c = self.controller(base)
                c.planned = {'MILK': [(24, 4)]}
                out = c.act(state[0].observation, env.configuration)
                self.assertEqual(out, base)
                self.assertEqual(c.pending['MILK'], 4)
                self.assertEqual(c.planned['MILK'], [(24, 4)])
                state[0].action = out
                self.step(state, env)
                self.assertEqual(state[0].observation.private['shed']['MILK'], 4)

    def test_only_filled_executable_prefix_retires_stock(self):
        count = 0
        for seat in (0, 1):
            for cap in (-1, 0, 1, 2, 10):
                for qty in (1, 3):
                    with self.subTest(seat=seat, cap=cap, qty=qty):
                        state, env = self.fixture(seat, stock=7, cap=cap)
                        n = max(1, cap)
                        base = action([['SELL', 'MILK', qty]] + [[]]*(n-1)
                                      + [['SELL', 'MILK', 7-qty]])
                        c = self.controller(base)
                        c.planned = {'MILK': [(24, 7-qty)]}
                        out = c.act(state[seat].observation, env.configuration)
                        self.assertEqual(out, base)
                        self.assertEqual(c.pending['MILK'], 7-qty)
                        self.assertEqual(c.planned['MILK'], [(24, 7-qty)])
                        state[seat].action = out
                        self.step(state, env)
                        self.assertEqual(state[seat].observation.private['shed']['MILK'], 7-qty)
                        count += 1
        COUNTS['prefix_sale_cells'] = count

    def test_actual_interpreter_suffix_equivalence_both_seats(self):
        count = 0
        for seat in (0, 1):
            for cap in (-1, 0, 1, 2, 10):
                for item in ('MILK', 'WOOL', 'TOMATO', 'EGG'):
                    for empty in (True, False):
                        state, env = self.fixture(seat, item=item, stock=7, cap=cap)
                        n = max(1, cap)
                        prefix = ([[]] if empty else [['SELL', item, 2]]) + [[]]*(n-1)
                        base = action(prefix+[['HIRE'], ['BUY_ANIMAL', 'GOOSE', 1],
                                              ['SELL', item, 7]])
                        c = self.controller(base)
                        out = c.act(state[seat].observation, env.configuration)
                        state[seat].action = out
                        state[1-seat].observation.private['shed'][item] = 4
                        state[1-seat].action = action([['SELL', item, 3]])
                        other, oe = copy.deepcopy((state, env))
                        other[seat].action['market'] = copy.deepcopy(out['market'][:n])
                        self.step(state, env)
                        self.step(other, oe)
                        for i in (0, 1):
                            self.assertEqual(state[i].observation, other[i].observation)
                            self.assertEqual(state[i].status, other[i].status)
                        count += 1
        COUNTS['interpreter_suffix_pairs'] = count

    def test_actual_current_drop_overflow_cannot_be_saved_by_later_sell(self):
        for seat in (0, 1):
            state, env = self.fixture(seat, step=1, stock=0)
            obs = state[seat].observation
            obs.private['shed']['WHEAT'] = 99
            obs.private['inventories'][0]['MILK'] = 2
            base = action([['SELL', 'WHEAT', 10]], farmer=('DROP', 'MILK', 2))
            c = self.controller(base)
            farm, private = self.subject.post_units(obs, base, env.configuration)
            self.assertEqual(private['shed']['MILK'], 1)
            feasible = c.receipt_profile(obs, base, farm, private, 1, 'MILK', env.configuration)
            self.assertFalse(feasible(((1, 1),)))
            old = self.controller(base, module=self.legacy)
            f0, p0 = self.legacy.post_units(obs, base, env.configuration)
            self.assertTrue(old.receipt_profile(obs, base, f0, p0, 1, 'MILK', env.configuration)(((1, 1),)))
            state[seat].action = base
            self.step(state, env)
            self.assertEqual(state[seat].observation.private['shed']['MILK'], 1)
            self.assertEqual(state[seat].observation.private['inventories'][0].get('MILK', 0), 0)
            self.assertEqual(state[seat].observation.private['shed']['WHEAT'], 89)
        COUNTS['physical_overflow_witnesses'] = 2

    def test_no_overflow_control_keeps_receipt_admissible(self):
        for seat in (0, 1):
            state, env = self.fixture(seat, step=1, stock=0)
            obs = state[seat].observation
            obs.private['shed']['WHEAT'] = 97
            obs.private['inventories'][0]['MILK'] = 2
            base = action([['SELL', 'WHEAT', 10]], farmer=('DROP', 'MILK', 2))
            c = self.controller(base)
            f, p = self.subject.post_units(obs, base, env.configuration)
            self.assertTrue(c.receipt_profile(obs, base, f, p, 1, 'MILK', env.configuration)(((1, 1),)))
            state[seat].action = base
            self.step(state, env)
            self.assertEqual(state[seat].observation.private['shed']['MILK'], 2)

    def test_cash_current_and_future_share_raw_cap(self):
        for cap in (-2, 0, 1, 2, 10):
            for seat in (0, 1):
                with self.subTest(cap=cap, seat=seat):
                    state, env = self.fixture(seat, step=1, cap=cap)
                    row = action([[]]*max(1, cap)+[['HIRE'], ['BUY_SEED', 'TOMATO', 1]])
                    c = self.controller(row, {2: row})
                    self.assertEqual(c.cash_reserve(state[seat].observation, env.configuration, row, 2), 0)
                    visible = action([['HIRE']]+[[]]*(max(1, cap)-1)+[['BUY_SEED', 'TOMATO', 1]])
                    c = self.controller(visible)
                    self.assertEqual(c.cash_reserve(state[seat].observation, env.configuration, visible, 1), 1)

    def test_future_overcap_buy_does_not_create_phantom_stock(self):
        for seat in (0, 1):
            state, env = self.fixture(seat, step=1, stock=0)
            obs = state[seat].observation
            obs.private['shed']['WHEAT'] = 98
            base = action()
            future = action([[], ['BUY_PRODUCT', 'WHEAT', 100]])
            c = self.controller(base, {2: future})
            f, p = self.subject.post_units(obs, base, env.configuration)
            self.assertTrue(c.receipt_profile(obs, base, f, p, 2, 'MILK', env.configuration)(()))
            for row, step in ((base, 1), (future, 2)):
                for s in state:
                    s.observation.step = step
                state[seat].action = row
                self.step(state, env)
            self.assertEqual(state[seat].observation.private['shed']['WHEAT'], 98)

    def test_future_overcap_sell_is_absent_from_real_optimizer_reference(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                state, env = self.fixture(seat, step=1, stock=4)
                c = self.controller(action(), {2: action([[], ['SELL', 'MILK', 4]])})
                c.act(state[seat].observation, env.configuration)
                rows = [r for r in c.diagnostics['evaluations'] if r['item'] == 'MILK']
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['reference'], [(1, 0)])

    def test_unmodified_real_parent_opening_trace_parity(self):
        # No route fixture here: actual parent.Agent and complete schedulers.
        # Opening only, not a field-strength or modern TITAN call-path claim.
        count = 0
        for seed in (71041, 71042):
            for seat in (0, 1):
                left, le = self.fixture(seat, stock=0, cap=10)
                right, re = copy.deepcopy((left, le))
                for state, env in ((left, le), (right, re)):
                    env.configuration.seed = seed
                    env.info = {}
                    for s in state:
                        s.observation = self.loader.Struct()
                    self.step(state, env)
                a = self.current.SellScheduler()
                b = self.subject.SellScheduler()
                for step in range(24):
                    for state in (left, right):
                        for s in state:
                            s.observation.step = step
                    la = a.act(copy.deepcopy(left[seat].observation), le.configuration)
                    ra = b.act(copy.deepcopy(right[seat].observation), re.configuration)
                    self.assertEqual(la, ra, (seed, seat, step))
                    left[seat].action, right[seat].action = la, ra
                    self.step(left, le)
                    self.step(right, re)
                    for i in (0, 1):
                        self.assertEqual(left[i].observation, right[i].observation, (seed, seat, step))
                    count += 1
        COUNTS['actual_parent_paired_callbacks'] = count


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True, help='read-only pinned dependencies')
    parser.add_argument('--source', type=Path, default=Path(__file__).with_name('scheduler_before.py'))
    parser.add_argument('--transformer', type=Path, default=Path(__file__).with_name('scheduler_action_prefix.py'))
    parser.add_argument('--legacy', type=Path, required=True, help='existing scheduler/executable-prefix/scheduler_candidate.py')
    parser.add_argument('--subject', choices=('candidate', 'current', 'legacy'), default='candidate',
                        help='negative controls run identical behavioral tests, not a publication switch')
    args = parser.parse_args(argv)
    try:
        inputs = {path: checked(args.package/path, sha) for path, sha in PINS.items()}
        source = checked(args.source, SOURCE)
        transformer_data = checked(args.transformer, TRANSFORMER)
        legacy = checked(args.legacy, LEGACY)
    except (OSError, ValueError) as exc:
        print(f'composition-input-error: {exc}', file=sys.stderr)
        return 2
    COUNTS.clear()
    with tempfile.TemporaryDirectory(prefix='titan-prefix-composition-') as tmp:
        root = Path(tmp)
        for path, data in inputs.items():
            target = root/path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (root/'transformer.py').write_bytes(transformer_data)
        transformer = load('composition_transformer', root/'transformer.py')
        candidate = transformer.transform(source)
        if blob(candidate) != CANDIDATE:
            raise ValueError('derived candidate pin mismatch')
        sys.path.insert(0, str(root))
        saved = {k: sys.modules.get(k) for k in ('mechanics', 'observed_clone',
                  'kaggle_environments', 'kaggle_environments.utils')}
        for name in ('mechanics', 'observed_clone'):
            sys.modules.pop(name, None)
        try:
            modules = {}
            for name, data in (('current', source), ('candidate', candidate), ('legacy', legacy)):
                path = root/f'scheduler_{name}.py'
                path.write_bytes(data)
                modules[name] = load(f'composition_{name}', path)
            loader = load('composition_loader', root/'checks/reference/evaluator/loader.py')
            # All three engine files were mandatory and pin-checked BEFORE loading.
            # The preserved loader therefore never reaches its download branch.
            engine, engine_hashes = loader.get_engine(root/'checks/reference/engine')
            for key, value in dict(root=root, source_bytes=source, candidate_bytes=candidate,
                legacy_bytes=legacy, transformer=transformer, loader=loader, engine=engine,
                subject=modules[args.subject], **modules).items():
                setattr(Composition, key, value)
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(Composition)
            result = unittest.TextTestRunner(verbosity=2, stream=sys.stderr).run(suite)
            print(json.dumps({'schema': 'titan-scheduler-composition-evidence/v1',
                'subject': args.subject, 'python': platform.python_version(),
                'optimized': bool(sys.flags.optimize), 'source': SOURCE, 'transformer': TRANSFORMER,
                'candidate': CANDIDATE, 'legacy_control': LEGACY, 'dependencies': PINS,
                'engine_sha256': engine_hashes, 'tests': result.testsRun,
                'failures': len(result.failures), 'errors': len(result.errors),
                'skips': len(result.skipped), 'counts': COUNTS, 'pass': result.wasSuccessful(),
                'scope': 'full scheduler modules; real dependencies and full official interpreter; '
                         'FixedRoute authored-action fixtures plus real parent 24-callback openings; '
                         'no complete episodes, no current titan_runtime invocation, no production activation'},
                indent=2, sort_keys=True))
            return 0 if result.wasSuccessful() else 1
        finally:
            sys.path.remove(str(root))
            for key, value in saved.items():
                if value is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = value


if __name__ == '__main__':
    raise SystemExit(main())
