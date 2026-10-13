#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Executable native-consumer, composition, and pinned official-market checks.

Use RIDGE_LAB for exact native source plus its dependency tree and
RIDGE_ENGINE_DIR for the three pinned upstream files. No network or game loop.
"""
from __future__ import annotations
import ast
import copy
import importlib.util
import json
import os
from pathlib import Path
import random
import sys
import tempfile
import types
import unittest
from typing import Any, Callable
from unittest.mock import patch

import compose_native_scheduler_prefix as repair

HERE = Path(__file__).resolve().parent
LAB = Path(os.environ['RIDGE_LAB']) if 'RIDGE_LAB' in os.environ else HERE.parents[4]
ENGINE_DIR = Path(os.environ.get('RIDGE_ENGINE_DIR', str(LAB / 'reference/engine')))
SUPPORT = {
    'mechanics.py': '044a4f9c0a4a44dde10ada57563238bcaf82075d',
    'selected_sell_core.py': 'f23d3a8b5ee5e82029026e7f8f44eb36c143a5a3',
    'observed_clone.py': 'f810d53193d3035655a36c21021e18ba1d415916',
    'seller_snapshot.py': '58ac31dada1c35b6dbaaaeef29fd83a0e52481ab',
    'reference/decision/decision.py': '2931aa55831204fbb473ab85a6f5b81ec947fcf7',
    'reference/next-panel/vendor/arlene.py': 'bdb9cf58148a3c7961c085f4902759537decabf6',
}
ENGINE_PINS = {
    'kaggriculture.py': repair.ENGINE_BLOB,
    'kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
    'utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
}
COUNTS = {'native_suffix_cases': 0, 'in_cap_parity_cases': 0,
          'official_market_pairs': 0, 'receipt_capacity_cases': 0}


class Struct(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None
    def __setattr__(self, name, value):
        self[name] = value


def official_engine():
    for name, pin in ENGINE_PINS.items():
        repair.bind((ENGINE_DIR / name).read_bytes(), pin, name)
    parsed = ast.parse((ENGINE_DIR / 'utils.py').read_bytes())
    helper = next(n for n in parsed.body if isinstance(n, ast.FunctionDef)
                  and n.name == 'resolve_episode_seed')
    ns = {'Any': Any, 'Callable': Callable, 'random': random}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), '<official-seed>', 'exec'), ns)
    package = types.ModuleType('kaggle_environments')
    utils = types.ModuleType('kaggle_environments.utils')
    utils.resolve_episode_seed = ns['resolve_episode_seed']
    spec = importlib.util.spec_from_file_location('_ridge_official', ENGINE_DIR / 'kaggriculture.py')
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'kaggle_environments': package,
                                 'kaggle_environments.utils': utils}):
        spec.loader.exec_module(module)
    return module


def load_pair(scheduler: bytes, frozen: bytes, tag: str):
    scheduler_mod = types.ModuleType('scheduler')
    scheduler_mod.__file__ = str(LAB / 'scheduler.py')
    frozen_mod = types.ModuleType('_ridge_frozen_' + tag)
    frozen_mod.__file__ = str(LAB / 'frozen_selected.py')
    with patch.dict(sys.modules, {'scheduler': scheduler_mod}):
        exec(compile(scheduler, scheduler_mod.__file__, 'exec'), scheduler_mod.__dict__)
        exec(compile(frozen, frozen_mod.__file__, 'exec'), frozen_mod.__dict__)
    return scheduler_mod, frozen_mod


def action(market=(), farmer=('PASS',), hands=()):
    return {'farmer': list(farmer), 'hands': copy.deepcopy(list(hands)),
            'market': copy.deepcopy(list(market))}


def fixed_agent(module, base, step=1, route_rows=None, mode='candidate'):
    # Exact native methods, synthetic controller; no alternate game policy runs.
    agent = object.__new__(module.FrozenSelected)
    agent.mode = mode
    agent.pending, agent.planned = {}, {}
    agent.previous, agent.observed_harvests, agent.diagnostics = None, {}, {}
    route = [action() for _ in range(720)]
    route[step] = copy.deepcopy(base)
    for t, row in (route_rows or {}).items():
        route[t] = copy.deepcopy(row)
    agent.controller = types.SimpleNamespace(R=[route], cur=0)
    return agent


def state_signature(agent):
    return copy.deepcopy((agent.pending, agent.planned, agent.previous,
                          agent.observed_harvests, agent.diagnostics))


def top_definitions(source):
    text = source.decode()
    lines = text.splitlines(keepends=True)
    result = {}
    for node in ast.parse(text).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            result[node.name] = ''.join(lines[node.lineno - 1:node.end_lineno])
    return result


class NativePrefixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for name, pin in SUPPORT.items():
            repair.bind((LAB / name).read_bytes(), pin, name)
        sys.path.insert(0, str(LAB))
        # Do not accidentally validate an unrelated already-imported module.
        for name in ('mechanics', 'selected_sell_core', 'observed_clone', 'seller_snapshot'):
            sys.modules.pop(name, None)
        cls.source = (LAB / 'scheduler.py').read_bytes()
        cls.frozen = (LAB / 'frozen_selected.py').read_bytes()
        cls.engine_bytes = (ENGINE_DIR / 'kaggriculture.py').read_bytes()
        cls.outputs, cls.receipt = repair.compose(cls.source, cls.frozen, cls.engine_bytes)
        cls.engine = official_engine()
        cls.old_s, cls.old = load_pair(cls.source, cls.frozen, 'original')
        cls.new_s, cls.new = load_pair(cls.outputs['scheduler.py'], cls.outputs['frozen_selected.py'], 'combined')
        _, cls.act_only = load_pair(cls.outputs['scheduler.py'], cls.frozen, 'act_only')

    @classmethod
    def tearDownClass(cls):
        if str(LAB) in sys.path:
            sys.path.remove(str(LAB))

    def fixture(self, *, seat=0, stock=10, cash=10000, step=1, cap=10,
                item='MILK', inventory=10000, shops=()):
        e = self.engine
        cfg = Struct({k: v.get('default') if isinstance(v, dict) else v
                      for k, v in e.specification['configuration'].items()})
        cfg.update(maxMarketOrdersPerTurn=cap, weedSpawnChance=0)
        farms = [e._new_farm(10, cash), e._new_farm(10, cash)]
        market = e._new_market()
        market['inventory'][item] = inventory
        e._refresh_prices(market)
        states = []
        for player in (0, 1):
            private = e._new_private()
            private['shed'][item] = stock
            obs = Struct(player=player, step=step, day=step // 24, hour=step % 24,
                         farms=farms, private=private, market=market,
                         town={'unlocked_shops': list(shops)})
            states.append(Struct(observation=obs, action=action(), status='ACTIVE', reward=0))
        return states[seat].observation, cfg, states, Struct(configuration=cfg, done=False, info={'seed': 107})

    def test_exact_composition_and_existing_self_test(self):
        self.assertEqual(repair.git_blob(self.outputs['scheduler.py']), repair.SCHEDULER_AFTER)
        self.assertEqual(self.receipt['projection_intermediate_blob'], '1da9934ec45f485a16244bcbc78af26d9109b97e')
        self.assertFalse(self.receipt['production_activation'])
        projection = repair._dependency(HERE, 'materialize_scheduler_prefix.py')
        projection.self_test()

    def test_all_untouched_native_helpers_remain_byte_exact(self):
        before, after = top_definitions(self.frozen), top_definitions(self.outputs['frozen_selected.py'])
        for name in before:
            if name != 'FrozenSelected':
                self.assertEqual(before[name], after[name], name)
        before_s, after_s = top_definitions(self.source), top_definitions(self.outputs['scheduler.py'])
        for name in before_s:
            if name != 'SellScheduler':
                self.assertEqual(before_s[name], after_s[name], name)

    def test_native_dispatch_does_not_inherit_repaired_act(self):
        self.assertIn('transform', self.new.FrozenSelected.__dict__)
        self.assertNotIn('act', self.new.FrozenSelected.__dict__)
        self.assertIs(self.new.FrozenSelected.cash_reserve, self.new_s.SellScheduler.cash_reserve)
        self.assertIs(self.new.FrozenSelected.receipt_profile, self.new_s.SellScheduler.receipt_profile)
        obs, cfg, _, _ = self.fixture()
        base = action([[]] * 10 + [['SELL', 'MILK', 5]])
        old = fixed_agent(self.act_only, base, mode='naive')
        new = fixed_agent(self.new, base, mode='naive')
        self.assertEqual(old.transform(obs, cfg, base), new.transform(obs, cfg, base))
        self.assertEqual(old.pending['MILK'], 5)
        self.assertEqual(new.pending['MILK'], 10)

    def test_dead_sale_cannot_fund_live_hire(self):
        obs, cfg, _, _ = self.fixture(cash=0)
        prefix = [[], ['HIRE']] + [[]] * 8
        base = action(prefix + [['SELL', 'MILK', 5]])
        old = fixed_agent(self.act_only, base, mode='naive')
        new = fixed_agent(self.new, base, mode='naive')
        old_out, new_out = old.transform(obs, cfg, base), new.transform(obs, cfg, base)
        self.assertEqual(old_out['market'][0][0], 'SELL')
        self.assertEqual(new_out['market'][:10], prefix)
        self.assertEqual(new_out['market'][10:], base['market'][10:])

    def test_current_and_future_cash_prefix(self):
        obs, cfg, _, _ = self.fixture(cap=2)
        base = action([[], [], ['HIRE']])
        route = {2: action([[], [], ['BUY_LAND']])}
        a = fixed_agent(self.new, base, route_rows=route)
        self.assertEqual(a.cash_reserve(obs, cfg, base, 2), 0)
        a.controller.R[0][2]['market'][0] = ['HIRE']
        self.assertGreater(a.cash_reserve(obs, cfg, base, 2), 0)

    def test_suffix_equivalence_across_native_helpers(self):
        tails = [[['SELL', 'MILK', 5]], [['HIRE']], [['BUY_LAND']],
                 [['BUY_PRODUCT', 'FERTILIZER', 2]], [['BUY_ANIMAL', 'GOOSE', 1]],
                 [None, {'opaque': ['PLANT', 'WHEAT']}, 'ignored']]
        for seat in (0, 1):
            for cap in (0, 1, 2, 10):
                n = max(1, cap)
                for mode in ('candidate', 'naive'):
                    for tail in tails:
                        with self.subTest(seat=seat, cap=cap, mode=mode, tail=tail):
                            obs, cfg, _, _ = self.fixture(seat=seat, cap=cap, stock=4)
                            prefix = [[], ['SELL', 'MILK', 2]][:n]
                            prefix += [[]] * (n - len(prefix))
                            base = action(prefix)
                            extended = action(prefix + tail)
                            clean_route = {3: action([[]] * n), 10: action([[]] * n)}
                            dirty_route = {t: action(row['market'] + tail) for t, row in clean_route.items()}
                            clean = fixed_agent(self.new, base, route_rows=clean_route, mode=mode)
                            dirty = fixed_agent(self.new, extended, route_rows=dirty_route, mode=mode)
                            original = copy.deepcopy((obs, cfg, extended, dirty.controller.R))
                            left = clean.transform(obs, cfg, base)
                            right = dirty.transform(obs, cfg, extended)
                            self.assertEqual(left['market'], right['market'][:n])
                            self.assertEqual(right['market'][n:], tail)
                            self.assertEqual((right['farmer'], right['hands']), (left['farmer'], left['hands']))
                            self.assertEqual(state_signature(clean), state_signature(dirty))
                            self.assertEqual(original, (obs, cfg, extended, dirty.controller.R))
                            COUNTS['native_suffix_cases'] += 1

    def test_in_cap_parity_preserves_current_behavior(self):
        rng = random.Random(94127)
        rows = [[], ['SELL', 'MILK', 2], ['HIRE'], ['BUY_SEED', 'WHEAT', 1],
                ['BUY_PRODUCT', 'WHEAT', 1], ['SELL', 'CARROT', 1]]
        for index in range(80):
            obs, cfg, _, _ = self.fixture(seat=index % 2, stock=index % 7,
                                          step=1 + index % 20, cash=(0, 100, 10000)[index % 3])
            base = action([copy.deepcopy(rng.choice(rows)) for _ in range(index % 5)])
            routes = {int(obs['step']) + 1: action([copy.deepcopy(rng.choice(rows))])}
            old = fixed_agent(self.old, base, step=obs['step'], route_rows=routes)
            new = fixed_agent(self.new, base, step=obs['step'], route_rows=routes)
            self.assertEqual(old.transform(obs, cfg, copy.deepcopy(base)), new.transform(obs, cfg, copy.deepcopy(base)))
            self.assertEqual(state_signature(old), state_signature(new))
            COUNTS['in_cap_parity_cases'] += 1

    def test_minimum_one_cap_uses_normalized_reference(self):
        for cap in (-7, 0, 1, 2, 5, 10, 14):
            obs, cfg, _, _ = self.fixture(cap=cap, stock=4)
            norm = dict(cfg, maxMarketOrdersPerTurn=max(1, cap))
            base = action([['SELL', 'MILK', 2]] + [[]] * (max(1, cap) - 1))
            left, right = fixed_agent(self.new, base), fixed_agent(self.new, base)
            self.assertEqual(left.transform(obs, cfg, base), right.transform(obs, norm, base))
            self.assertEqual(state_signature(left), state_signature(right))

    def test_read_only_lazy_tape_view(self):
        class CountingRoute(list):
            def __getitem__(self, key):
                self.reads.append(key)
                return super().__getitem__(key)
        route = CountingRoute([action([[], ['HIRE']]) for _ in range(720)])
        route.reads = []
        view = self.new._V4NativePrefixTape(route, 1)
        self.assertEqual(len(view), 720)
        self.assertEqual(route.reads, [])
        self.assertEqual(view[6]['market'], [[]])
        self.assertEqual(route.reads, [6])
        self.assertEqual(view[-1]['market'], [[]])
        self.assertEqual(len(view[2:4]), 2)
        self.assertEqual(route[6]['market'], [[], ['HIRE']])
        with self.assertRaises(IndexError):
            _ = view[720]

    def test_engine_inert_nonlist_future_market_is_empty(self):
        obs, cfg, _, _ = self.fixture(stock=4)
        base = action()
        clean = fixed_agent(self.new, base)
        dirty = fixed_agent(self.new, base, route_rows={2: dict(action(), market='inert')})
        self.assertEqual(clean.transform(obs, cfg, base), dirty.transform(obs, cfg, base))
        self.assertEqual(state_signature(clean), state_signature(dirty))

    def test_cancellation_never_replaces_controller_tape(self):
        obs, cfg, _, _ = self.fixture(stock=4)
        base = action([[]] * 10 + [['HIRE']])
        agent = fixed_agent(self.new, base)
        original = copy.deepcopy(agent.controller.R)
        identity = agent.controller.R
        class Cancelled(BaseException):
            pass
        with patch.object(self.new, 'optimize_lot', side_effect=Cancelled):
            with self.assertRaises(Cancelled):
                agent.transform(obs, cfg, base)
        self.assertIs(agent.controller.R, identity)
        self.assertEqual(agent.controller.R, original)

    def test_terminal_path_is_byte_behavior_identical(self):
        for seat in (0, 1):
            for stock in (0, 1, 12, 100):
                for cap in (0, 1, 10):
                    obs, cfg, _, _ = self.fixture(seat=seat, stock=stock, step=718, cap=cap)
                    base = action([[]] * 10 + [['SELL', 'MILK', 1]])
                    old, new = fixed_agent(self.old, base, step=718), fixed_agent(self.new, base, step=718)
                    self.assertEqual(old.transform(obs, cfg, base), new.transform(obs, cfg, base))
                    self.assertEqual(state_signature(old), state_signature(new))

    def test_e14_unit_overflow_survives_composition(self):
        for seat in (0, 1):
            for wheat in range(88, 99):
                obs, cfg, _, _ = self.fixture(seat=seat, stock=0, step=22)
                obs.private['shed']['WHEAT'] = wheat
                obs.private['inventories'] = [{'MILK': 10}]
                base = action([['SELL', 'WHEAT', 10]], farmer=['DROP'])
                agent = fixed_agent(self.new, base, step=22)
                farm, private = self.new_s.post_units(obs, base, cfg)
                _, requested = self.new_s.post_units(obs, base, cfg, shed_capacity=10**6)
                self.assertEqual(requested['shed']['MILK'], 10)
                self.assertEqual(private['shed']['MILK'], min(10, 100 - wheat))
                feasible = agent.receipt_profile(obs, base, farm, private, 22, 'MILK', cfg)
                self.assertEqual(feasible(()), wheat <= 90)
                COUNTS['receipt_capacity_cases'] += 1

    def test_official_market_suffix_pairs(self):
        for seat in (0, 1):
            for item in ('MILK', 'TOMATO', 'WHEAT'):
                for cap in (-1, 0, 1, 2, 10):
                    for rival_qty in (0, 1, 3):
                        for inventory in (9900, 10000, 11000):
                            n = max(1, cap)
                            kwargs = dict(seat=seat, item=item, stock=4, cap=cap, inventory=inventory)
                            obs, cfg, states, env = self.fixture(**kwargs)
                            base = action([['SELL', item, 2]] + [[]] * (n - 1))
                            extended = action(base['market'] + [None, ['SELL', item, 99], ['HIRE']])
                            new = fixed_agent(self.new, extended)
                            returned = new.transform(obs, cfg, extended)
                            _, _, expected, expected_env = self.fixture(**kwargs)
                            states[seat].action = returned
                            expected[seat].action = dict(returned, market=returned['market'][:n])
                            rival = action([['SELL', item, rival_qty]])
                            states[1 - seat].action = copy.deepcopy(rival)
                            expected[1 - seat].action = copy.deepcopy(rival)
                            self.engine._process_market(states, env)
                            self.engine._process_market(expected, expected_env)
                            for player in (0, 1):
                                self.assertEqual(states[player].observation, expected[player].observation)
                            COUNTS['official_market_pairs'] += 1

    def test_future_dead_sale_does_not_extend_horizon(self):
        obs, cfg, _, _ = self.fixture(stock=4, shops=['SMOOTHIE_SHOP'])
        base = action([[]] * 10)
        clean_route = {t: action([[]] * 10) for t in range(10, 24)}
        dirty_route = copy.deepcopy(clean_route)
        dirty_route[13]['market'].append(['SELL', 'MILK', 4])
        a = fixed_agent(self.new, base, route_rows=clean_route)
        b = fixed_agent(self.new, base, route_rows=dirty_route)
        self.assertEqual(a.transform(obs, cfg, base), b.transform(obs, cfg, base))
        self.assertEqual(state_signature(a), state_signature(b))
        self.assertNotIn('MILK', b.diagnostics['horizon']['service_dates'])

    def test_semantic_mutants_are_rejected(self):
        native = self.outputs['frozen_selected.py'].decode()
        scheduler = self.outputs['scheduler.py'].decode()
        mutations = [
            ('no-current-boundary', scheduler,
             native.replace('base = _v4_native_prefix_action(base, _v4_limit)', 'base = dict(base)'),
             'test_native_dispatch_does_not_inherit_repaired_act'),
            ('no-future-boundary', scheduler,
             native.replace('_V4NativePrefixTape(self.controller.R[self.controller.cur], _v4_limit)',
                            'self.controller.R[self.controller.cur]'),
             'test_future_dead_sale_does_not_extend_horizon'),
            ('drop-opaque-tail', scheduler,
             native.replace("out['market'].extend(copy.deepcopy(_v4_raw_suffix))", 'pass'),
             'test_suffix_equivalence_across_native_helpers'),
            ('minimum-zero', scheduler,
             native.replace("_v4_limit = max(1, int(config.get('maxMarketOrdersPerTurn', 10)))",
                            "_v4_limit = max(0, int(config.get('maxMarketOrdersPerTurn', 10)))"),
             'test_minimum_one_cap_uses_normalized_reference'),
            ('uncapped-inherited-accounting',
             scheduler.replace('orders=_engine_market_prefix(market_action,config)',
                               "orders=market_action.get('market',[])"), native,
             'test_current_and_future_cash_prefix'),
            ('lose-E14-requested-arrivals',
             scheduler.replace('f,p=post_units(obs,base,config,shed_capacity=10**6)',
                               'f,p=copy.deepcopy(farm),copy.deepcopy(private)'), native,
             'test_e14_unit_overflow_survives_composition'),
        ]
        cls = type(self)
        saved_s, saved_f, saved_counts = cls.new_s, cls.new, dict(COUNTS)
        try:
            for name, source_s, source_f, test_name in mutations:
                with self.subTest(mutant=name):
                    self.assertNotEqual((source_s, source_f), (scheduler, native))
                    # Only semantic test methods run: no hash/identity rejection
                    # can be counted as a killed behavioral mutation.
                    cls.new_s, cls.new = load_pair(source_s.encode(), source_f.encode(), name)
                    result = unittest.TestResult()
                    cls(test_name).run(result)
                    self.assertFalse(result.wasSuccessful(), name + ' survived')
        finally:
            cls.new_s, cls.new = saved_s, saved_f
            COUNTS.clear()
            COUNTS.update(saved_counts)

    def test_state_isolation_between_seats_and_agents(self):
        base = action([[]] * 10 + [['SELL', 'MILK', 5]])
        obs0, cfg, _, _ = self.fixture(seat=0, stock=10)
        obs1, _, _, _ = self.fixture(seat=1, stock=4)
        a, b = fixed_agent(self.new, base), fixed_agent(self.new, base)
        a.transform(obs0, cfg, base)
        saved = state_signature(a)
        b.transform(obs1, cfg, base)
        self.assertEqual(a.pending['MILK'], 10)
        self.assertEqual(b.pending['MILK'], 4)
        self.assertEqual(state_signature(a), saved)

    def test_live_prefix_rows_remain_live(self):
        obs, cfg, _, _ = self.fixture(cap=2)
        sale = action([['SELL', 'MILK', 5], []])
        empty = action([[], []])
        a, b = fixed_agent(self.new, sale, mode='naive'), fixed_agent(self.new, empty, mode='naive')
        left, right = a.transform(obs, cfg, sale), b.transform(obs, cfg, empty)
        self.assertNotEqual(left['market'], right['market'])
        self.assertNotEqual(a.pending, b.pending)

    def test_unknown_and_double_applied_sources_fail_closed(self):
        for source, frozen, engine in (
                (self.source + b'\n', self.frozen, self.engine_bytes),
                (self.source, self.frozen + b'\n', self.engine_bytes),
                (self.source, self.frozen, self.engine_bytes + b'\n'),
                (self.outputs['scheduler.py'], self.frozen, self.engine_bytes),
                (self.source, self.outputs['frozen_selected.py'], self.engine_bytes)):
            with self.assertRaises(ValueError):
                repair.compose(source, frozen, engine)

    def test_dependency_drift_rejected_before_loading(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in repair.DEPENDENCIES:
                (root / name).write_bytes((HERE / name).read_bytes())
            path = root / 'act_sale_prefix.py'
            path.write_bytes(path.read_bytes() + b'\nraise RuntimeError("must not execute")\n')
            with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                repair.compose(self.source, self.frozen, self.engine_bytes, root)

    def test_bundle_fresh_only_and_inputs_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            lab = root / 'lab'
            lab.mkdir()
            (lab / 'scheduler.py').write_bytes(self.source)
            (lab / 'frozen_selected.py').write_bytes(self.frozen)
            engine = root / 'engine.py'
            engine.write_bytes(self.engine_bytes)
            output = root / 'out'
            report = repair.write_bundle(lab, engine, output)
            self.assertEqual(report['outputs'], self.receipt['outputs'])
            self.assertEqual((output / 'scheduler.py').read_bytes(), self.outputs['scheduler.py'])
            self.assertEqual((lab / 'scheduler.py').read_bytes(), self.source)
            self.assertEqual((lab / 'frozen_selected.py').read_bytes(), self.frozen)
            self.assertEqual(engine.read_bytes(), self.engine_bytes)
            with self.assertRaises(FileExistsError):
                repair.write_bundle(lab, engine, output)
            with self.assertRaises(FileExistsError):
                repair.write_bundle(lab, engine, lab)
            alias = root / 'alias'
            alias.symlink_to(lab, target_is_directory=True)
            with self.assertRaises(FileExistsError):
                repair.write_bundle(lab, engine, alias)

    def test_input_and_dependency_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            lab = root / 'lab'
            lab.mkdir()
            (lab / 'scheduler.py').symlink_to(LAB / 'scheduler.py')
            (lab / 'frozen_selected.py').write_bytes(self.frozen)
            with self.assertRaisesRegex(ValueError, 'non-symlink'):
                repair.write_bundle(lab, ENGINE_DIR / 'kaggriculture.py', root / 'out')
            (root / 'act_sale_prefix.py').symlink_to(HERE / 'act_sale_prefix.py')
            with self.assertRaisesRegex(ValueError, 'non-symlink'):
                repair._dependency(root, 'act_sale_prefix.py')


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NativePrefixTests))
    print(json.dumps({'counts': COUNTS, 'tests': result.testsRun, 'success': result.wasSuccessful(),
                      'failures': len(result.failures), 'errors': len(result.errors),
                      'skipped': len(result.skipped), 'python': sys.version,
                      'full_game_economics': False}, sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)
