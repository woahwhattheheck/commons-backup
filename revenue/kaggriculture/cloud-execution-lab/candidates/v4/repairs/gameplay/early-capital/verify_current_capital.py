# SPDX-License-Identifier: Apache-2.0
"""Pinned current-class + official-turn checks for recovered early capital.

No games, producer search, materializer, package write, network, or promotion.
The actual current TitanAgent finalizer is invoked with only its route metadata
collaborator replaced. The full official interpreter runs constructed states.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import random
import sys
import types
import unittest
from unittest.mock import patch

PINS = {
    'runtime': 'b952c9c228ecbde592bf3d2df01638677abb0d24',
    'baseline': '1161859ac5af617eca65aec3f732b5c1396cad37',
    'candidate': 'c87f1d1c9d7b416c5316837634f7e721c85811fa',
    'mechanics': '044a4f9c0a4a44dde10ada57563238bcaf82075d',
    'deadline': '664aa4f8a21368c388dfa6714406519b6535ef7f',
    'engine': '3c202c7ee921da239356789e266b694635103fc4',
}


class Box(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    def __setattr__(self, key, value):
        self[key] = value


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f'cannot load {path}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def bind(root: Path, engine_path: Path):
    paths = {
        'runtime': root / 'titan_runtime.py',
        'baseline': root / 'early_capital.py',
        'candidate': Path(__file__).resolve().parent / 'early_capital.py',
        'mechanics': root / 'mechanics.py',
        'deadline': root / 'reference/titan-current/deadline_adapter.py',
        'engine': engine_path,
    }
    sources = {}
    for key, path in paths.items():
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'{key}: ordinary source file required: {path}')
        data = path.read_bytes()
        actual = git_blob(data)
        if actual != PINS[key]:
            raise ValueError(f'{key}: expected {PINS[key]}, found {actual}')
        sources[key] = {
            'git_blob': actual, 'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest(),
        }
        compile(data, str(path), 'exec')
    # The exact initialized-state engine never needs its initialization seed API.
    # Raising here prevents a fabricated seed shim from silently being used.
    def no_initialization(_env):
        raise AssertionError('initialization outside constructed-state scope')
    env_package = types.ModuleType('kaggle_environments')
    env_package.__path__ = []
    utils = types.ModuleType('kaggle_environments.utils')
    utils.resolve_episode_seed = no_initialization
    with patch.dict(sys.modules, {
            'kaggle_environments': env_package,
            'kaggle_environments.utils': utils}):
        engine = load('_capital_engine', paths['engine'])
    runtime = load('_capital_current_runtime', paths['runtime'])
    mechanics = load('_capital_mechanics', paths['mechanics'])
    baseline = load('_capital_baseline', paths['baseline'])
    candidate = load('_capital_candidate', paths['candidate'])
    return engine, runtime, mechanics, baseline, candidate, sources


def action(market=(), farmer=('PASS',), hands=()):
    return {'farmer': list(farmer), 'hands': deepcopy(list(hands)),
            'market': deepcopy(list(market))}


def route(now=1, future=0, crop='WHEAT'):
    rows = [action() for _ in range(max(32, now + 27))]
    for index in range(future):
        rows[now + 1 + index] = action(farmer=('PLANT', crop))
    return rows


class Evidence:
    def __init__(self, engine, runtime, mechanics, baseline, candidate):
        self.e, self.r, self.m = engine, runtime, mechanics
        self.old, self.new = baseline, candidate
        self.counts = Counter()
        self.witnesses = []

    def world(self, *, seat=0, step=1, money=750, seeds=1,
              stock=None, inventory=10000, hands=0, unlocked=1):
        e = self.e
        farms = [e._new_farm(10, 0), e._new_farm(10, 0)]
        farms[seat]['money'] = float(money)
        for _ in range(unlocked - 1):
            farms[seat]['money'] = 10000.0
            e._do_buy_land(farms[seat], 10)
        farms[seat]['money'] = float(money)
        farms[seat]['hands'] = [[3, 4], [4, 3], [3, 3]][:hands]
        farms[seat]['hires_today'] = hands
        private = [e._new_private(), e._new_private()]
        private[seat]['seeds']['WHEAT'] = seeds
        private[seat]['inventories'] = [{} for _ in range(hands + 1)]
        private[seat]['shed'].update({'MELON': 1} if stock is None else stock)
        private[1-seat]['shed']['MELON'] = 4
        market = e._new_market()
        market['inventory'].update({item: inventory for item in e.PRODUCTS})
        e._refresh_prices(market)
        town = e._new_town()
        state = [Box(observation=Box(player=s, step=step, day=step//24,
                    hour=step%24, farms=farms, private=private[s], market=market,
                    town=town), action=action(), status='ACTIVE', reward=0)
                 for s in range(2)]
        cfg = Box(episodeSteps=720, turnsPerDay=24, boardSize=10,
                  maxMarketOrdersPerTurn=10, farmHandCostMult=1,
                  shedCapacity=100, weedSpawnChance=0)
        env = Box(configuration=cfg, done=False, info={'seed': 20260911})
        return state, env

    def transform(self, observation, cfg, selected, rows, *, module=None,
                  enabled=True, consumer='frozen', finish=True):
        # Full b952 class, not a reconstructed or AST-extracted method.
        features = self.r.Features(early_capital=enabled, consumer=consumer)
        agent = self.r.TitanAgent(features)
        agent.controller = types.SimpleNamespace(R=[rows], cur=0)
        scheduler = types.ModuleType('scheduler')
        scheduler.parent = types.SimpleNamespace(DECISIONS=[])
        with patch.dict(sys.modules, {'mechanics': self.m,
                'early_capital': module or self.new, 'scheduler': scheduler}):
            if finish:
                result = agent._finish_production(observation, selected, cfg)
            else:
                result = agent._early_capital_selected(observation, cfg, selected)
        self.counts['current_class_calls'] += 1
        return result, agent.diagnostics.get('early_capital', {})

    def execute(self, state, env, selected, *, seat=0, rival=None):
        state, env = deepcopy((state, env))
        state[seat].action = deepcopy(selected)
        state[1-seat].action = deepcopy(rival or action())
        result = self.e.interpreter(state, env)
        self.counts['full_interpreter_calls'] += 1
        return result

    def prove_capital(self, state, env, selected, report, seat, rival=None):
        actual = self.execute(state, env, selected, seat=seat, rival=rival)
        before = state[seat].observation
        after = actual[seat].observation
        allocations = report['capital_allocations']
        land = sum(a['units'] for a in allocations if a['op'] == 'BUY_LAND')
        if len(after.farms[seat]['unlocked_quadrants']) != (
                len(before.farms[seat]['unlocked_quadrants']) + land):
            raise AssertionError('certified LAND failed to commit')
        for animal in self.e.ANIMALS:
            units = sum(a['units'] for a in allocations
                        if a['op'] == 'BUY_ANIMAL' and a['item'] == animal)
            if after.private['shed'][animal] - before.private['shed'][animal] != units:
                raise AssertionError(f'certified {animal} failed to commit')
        self.counts['certified_full_turns'] += 1
        return actual


def suite(h: Evidence):
    class Contracts(unittest.TestCase):
        def positive(self, *, seat=0, step=1, future=0, seeds=1, money=750):
            states, env = h.world(seat=seat, step=step, seeds=seeds, money=money)
            selected = action([['BUY_LAND'], ['BUY_SEED', 'WHEAT', 1],
                               ['SELL', 'MELON', 1]], farmer=('PLANT', 'WHEAT'))
            rows = route(step, future)
            return states, env, selected, rows

        def test_runtime_finalizer_recovers_land_both_seats_all_day_phases(self):
            for seat in (0, 1):
                for step in (1, 22, 23, 24, 47):
                    for rival in (action(), action([['SELL', 'MELON', 4]])):
                        with self.subTest(seat=seat, step=step, rival=rival):
                            states, env, selected, rows = self.positive(seat=seat, step=step)
                            original = deepcopy((states, selected, rows))
                            fixed, report = h.transform(states[seat].observation,
                                env.configuration, selected, rows)
                            old, _ = h.transform(states[seat].observation,
                                env.configuration, selected, rows, module=h.old)
                            self.assertEqual(fixed['market'], [
                                ['SELL', 'MELON', 1], ['BUY_LAND'],
                                ['BUY_SEED', 'WHEAT', 1]])
                            after = h.prove_capital(states, env, fixed, report, seat, rival)
                            previous = h.execute(states, env, old, seat=seat, rival=rival)
                            self.assertEqual(after[seat].observation.farms[seat]['money'], 0)
                            self.assertEqual(previous[seat].observation.farms[seat]['money'], 990)
                            self.assertEqual(previous[seat].observation.farms[seat]['unlocked_quadrants'], ['NW'])
                            self.assertEqual(after[1-seat].observation.private,
                                             previous[1-seat].observation.private)
                            self.assertEqual(after[1-seat].observation.farms[1-seat],
                                             previous[1-seat].observation.farms[1-seat])
                            self.assertEqual(after[seat].observation.market,
                                             previous[seat].observation.market)
                            self.assertEqual((states, selected, rows), original)
                            h.counts['land_recovery_pairs'] += 1
            h.witnesses.append({'case': 'current_PLANT_land_threshold',
                'cash_before': 750, 'melon_sale': 250, 'baseline_cash_after': 990,
                'candidate_cash_after': 0, 'baseline_quadrants': 1,
                'candidate_quadrants': 2, 'full_game_value': 'NOT_MEASURED'})

        def test_future_demand_is_preserved_and_only_residual_is_counted(self):
            for seat in (0, 1):
                for seeds, future, money, land_expected in (
                        (1, 1, 750, False), (2, 1, 750, True),
                        (1, 1, 760, True), (3, 2, 750, True)):
                    with self.subTest(seat=seat, seeds=seeds, future=future, money=money):
                        states, env, selected, rows = self.positive(
                            seat=seat, seeds=seeds, future=future, money=money)
                        fixed, report = h.transform(states[seat].observation,
                            env.configuration, selected, rows)
                        if land_expected:
                            self.assertEqual(report['certified_capital_rows'], [0])
                            h.prove_capital(states, env, fixed, report, seat)
                        else:
                            self.assertIs(fixed, selected)
                            self.assertEqual(report['certified_operating_rows'], [1])
                            self.assertEqual(report['cash_after_operating_lower_bound'], 990)
                            self.assertEqual(report['certified_capital_rows'], [])

        def test_atomic_overdemand_matches_full_interpreter(self):
            for seat in (0, 1):
                for seeds in (0, 1, 2, 3):
                    for hands in (0, 1, 2):
                        with self.subTest(seat=seat, seeds=seeds, hands=hands):
                            states, env = h.world(seat=seat, seeds=seeds, hands=hands)
                            selected = action(farmer=('PLANT', 'WHEAT'),
                                hands=[['PLANT', 'WHEAT']] * hands)
                            obs = states[seat].observation
                            projected = h.new._project_post_unit_private(
                                h.m, obs, env.configuration, selected, 1)
                            actual = h.execute(states, env, selected, seat=seat)
                            self.assertEqual(projected, actual[seat].observation.private)
                            expected = seeds if hands+1 > seeds else seeds-hands-1
                            self.assertEqual(projected['seeds']['WHEAT'], expected)
                            h.counts['atomic_projection_cases'] += 1

        def test_disabled_consumer_and_finalizer_identity(self):
            states, env, selected, rows = self.positive()
            for consumer, enabled in (('frozen', False), ('ordered', True), ('parent', True)):
                for finish in (False, True):
                    with self.subTest(consumer=consumer, enabled=enabled, finish=finish):
                        result, report = h.transform(states[0].observation, env.configuration,
                            selected, rows, enabled=enabled, consumer=consumer, finish=finish)
                        self.assertIs(result, selected)
                        self.assertEqual(report, {})

        def test_finalizer_and_direct_hook_agree(self):
            states, env, selected, rows = self.positive()
            a = h.transform(states[0].observation, env.configuration, selected, rows)
            b = h.transform(states[0].observation, env.configuration, selected, rows, finish=False)
            self.assertEqual(a, b)

        def test_raw_suffix_invariance_and_nonmutation(self):
            suffixes = [[], [['HIRE']], [['BUY_LAND']], [['SELL', 'MELON', 999]],
                [['BUY_SEED', 'WHEAT', 99]], [['BUY_ANIMAL', 'COW', 99]],
                [None, [], 'bad', {'order': 'HIRE'}], [['SELL', 'WHEAT', float('inf')]]]
            for seat in (0, 1):
                for limit in (3, 4, 10, 12):
                    states, env, selected, rows = self.positive(seat=seat)
                    env.configuration.maxMarketOrdersPerTurn = limit
                    selected['market'] += [['PASS']] * (limit - 3)
                    prefix, _ = h.transform(states[seat].observation, env.configuration, selected, rows)
                    for tail in suffixes:
                        with self.subTest(seat=seat, limit=limit, tail=tail):
                            source = deepcopy(selected)
                            source['market'] += deepcopy(tail)
                            old = deepcopy(source)
                            out, _ = h.transform(states[seat].observation, env.configuration, source, rows)
                            self.assertEqual(out['market'][:limit], prefix['market'])
                            self.assertEqual(out['market'][limit:], tail)
                            self.assertEqual(source, old)
                            self.assertEqual(out['farmer'], source['farmer'])
                            self.assertEqual(out['hands'], source['hands'])
                            h.counts['suffix_cases'] += 1

        def test_invalid_limits_and_terminal_are_identity(self):
            states, env, selected, rows = self.positive()
            for value in (True, False, '3', 3.0, None):
                with self.subTest(value=value):
                    cfg = dict(env.configuration, maxMarketOrdersPerTurn=value)
                    out, report = h.transform(states[0].observation, cfg, selected, rows)
                    self.assertIs(out, selected)
                    self.assertEqual(report['reason'], 'unsupported_market_limit')
            for step in (504, 695, 718, 719):
                states[0].observation.step = step
                out, report = h.transform(states[0].observation, env.configuration, selected, rows)
                self.assertIs(out, selected)
                self.assertFalse(report['changed'])

        def test_capital_needs_live_target_full_cash_and_capacity(self):
            for seat in (0, 1):
                for kind in ('land_cash', 'land_exhausted', 'animal_cash', 'animal_capacity'):
                    with self.subTest(seat=seat, kind=kind):
                        states, env = h.world(seat=seat, money=999, seeds=0, stock={})
                        market = [['BUY_PRODUCT', 'WHEAT', 1], ['BUY_LAND']]
                        if kind == 'land_exhausted':
                            states, env = h.world(seat=seat, money=5000, unlocked=4, stock={})
                        if kind.startswith('animal'):
                            market[1] = ['BUY_ANIMAL', 'COW', 3]
                            if kind == 'animal_capacity':
                                states, env = h.world(seat=seat, money=5000,
                                                     stock={'WHEAT': 98})
                        source = action(market)
                        out, report = h.transform(states[seat].observation,
                            env.configuration, source, route())
                        self.assertIs(out, source)
                        self.assertEqual(report['certified_capital_rows'], [])

        def test_randomized_full_turn_certificates(self):
            rng = random.Random(6129912156)
            activated = 0
            for index in range(512):
                seat = index % 2
                species = rng.choice(list(h.e.ANIMALS))
                stock_qty = rng.randint(1, 12)
                states, env = h.world(seat=seat, step=rng.choice((1, 22, 23, 71)),
                    money=rng.choice((300, 750, 1000, 1500, 3000, 6000)),
                    seeds=rng.randrange(4), stock={'MELON': stock_qty,
                    'WHEAT': rng.choice((0, 10, 80))}, inventory=rng.randint(9500, 13000))
                market = [['BUY_PRODUCT', 'WHEAT', rng.randint(1, 4)],
                    ['BUY_ANIMAL', species, rng.randint(1, 3)],
                    ['BUY_LAND'], ['SELL', 'MELON', rng.randint(1, stock_qty+2)],
                    ['BUY_SEED', 'WHEAT', rng.randint(1, 3)]]
                if index % 4 == 0:
                    market.insert(rng.randrange(len(market)+1), ['HIRE'])
                rng.shuffle(market)
                source = action(market, farmer=rng.choice((('PASS',), ('PLANT', 'WHEAT'))))
                rows = route(states[seat].observation.step, rng.randrange(3))
                env.configuration.maxMarketOrdersPerTurn = rng.choice((3, 4, 5, 10, 12))
                snap = deepcopy((states, source, rows))
                out, report = h.transform(states[seat].observation, env.configuration, source, rows)
                with self.subTest(index=index, seat=seat, source=source):
                    self.assertEqual((states, source, rows), snap)
                    limit = env.configuration.maxMarketOrdersPerTurn
                    self.assertEqual(Counter(map(repr, out['market'][:limit])),
                                     Counter(map(repr, source['market'][:limit])))
                    self.assertEqual(out['market'][limit:], source['market'][limit:])
                    if report['changed']:
                        activated += 1
                        h.prove_capital(states, env, out, report, seat,
                            action([['SELL', 'MELON', rng.randint(1, 4)]]))
                        h.counts['random_activations'] += 1
                    else:
                        self.assertIs(out, source)
                    h.counts['random_constructed_cases'] += 1
            self.assertGreater(activated, 50, 'empty/no-op corpus cannot certify')

        def test_floor_price_funding_preserves_market_inventory(self):
            for seat in (0, 1):
                with self.subTest(seat=seat):
                    states, env, selected, rows = self.positive(seat=seat, money=999)
                    for item in h.e.PRODUCTS:
                        states[seat].observation.market['inventory'][item] = 1000000
                    h.e._refresh_prices(states[seat].observation.market)
                    fixed, report = h.transform(states[seat].observation,
                        env.configuration, selected, rows)
                    self.assertEqual(report['guaranteed_funding_proceeds'], 1)
                    actual = h.prove_capital(states, env, fixed, report, seat,
                        action([['SELL', 'MELON', 4]]))
                    self.assertEqual(actual[seat].observation.farms[seat]['money'], 0)
                    self.assertEqual(actual[seat].observation.market,
                                     states[seat].observation.market)
                    h.counts['floor_funding_cases'] += 1

        def test_original_eight_contracts(self):
            # Exact inherited suite was recovered from the checked artifact.
            path = Path(__file__).resolve().parent / 'original/test_early_capital.py'
            self.assertEqual(git_blob(path.read_bytes()),
                             '89b451c47da299a68a755d49596a262aa507bbca')
            with patch.dict(sys.modules, {'mechanics': h.m, 'early_capital': h.new}):
                module = load('_capital_original_contracts', path)
                tests = unittest.defaultTestLoader.loadTestsFromModule(module)
                result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(tests)
            self.assertEqual(result.testsRun, 8)
            self.assertTrue(result.wasSuccessful(), str(result.errors + result.failures))
            self.assertEqual(result.skipped, [])
            h.counts['original_contracts'] += result.testsRun

        def test_four_semantic_mutants_are_rejected(self):
            source = (Path(__file__).resolve().parent / 'early_capital.py').read_text()
            mutations = [
                ('double_count', '_plant_demand(None, route, now, horizon)',
                 '_plant_demand(selected, route, now, horizon)'),
                ('land_cash', 'if cash < cost:', 'if False:'),
                ('animal_capacity', 'if room < quantity or cash < full_cost:',
                 'if cash < full_cost:'),
                ('animal_cash', 'if room < quantity or cash < full_cost:',
                 'if room < quantity:'),
            ]
            for name, old, new in mutations:
                with self.subTest(mutant=name):
                    self.assertEqual(source.count(old), 1)
                    mutant = types.ModuleType('_capital_mutant_' + name)
                    exec(compile(source.replace(old, new), name, 'exec'), mutant.__dict__)
                    if name == 'double_count':
                        states, env, selected, rows = self.positive()
                        good, _ = h.transform(states[0].observation, env.configuration, selected, rows)
                        bad, _ = h.transform(states[0].observation, env.configuration, selected, rows, module=mutant)
                        self.assertNotEqual(good, bad)
                        bad_after = h.execute(states, env, bad)
                        self.assertEqual(len(bad_after[0].observation.farms[0]['unlocked_quadrants']), 1)
                    else:
                        stock = {'WHEAT': 98} if name == 'animal_capacity' else {}
                        money = 5000 if name == 'animal_capacity' else 999
                        states, env = h.world(money=money, stock=stock)
                        capital = ['BUY_LAND'] if name == 'land_cash' else ['BUY_ANIMAL', 'COW', 3]
                        selected = action([['BUY_PRODUCT', 'WHEAT', 1], capital])
                        bad, report = h.transform(states[0].observation, env.configuration,
                            selected, route(), module=mutant)
                        self.assertTrue(report['changed'])
                        with self.assertRaisesRegex(AssertionError, 'failed to commit'):
                            h.prove_capital(states, env, bad, report, 0)
                    h.counts['semantic_mutants_rejected'] += 1
    return unittest.defaultTestLoader.loadTestsFromTestCase(Contracts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        e, r, m, old, new, pins = bind(args.runtime_root, args.engine)
    except (OSError, ValueError) as exc:
        print(f'INPUT ERROR: {exc}', file=sys.stderr)
        return 2
    h = Evidence(e, r, m, old, new)
    result = unittest.TextTestRunner(verbosity=2).run(suite(h))
    receipt = {'schema': 'titan-v4-capital-recovery/current-class-turn/v1',
        'success': result.wasSuccessful() and not result.skipped,
        'python': sys.version, 'optimization': sys.flags.optimize,
        'tests': result.testsRun, 'failures': len(result.failures),
        'errors': len(result.errors), 'skips': len(result.skipped),
        'pins': pins, 'counts': dict(h.counts), 'witnesses': h.witnesses,
        'scope': {'current_class_finalizer': True, 'full_official_turn': True,
                  'full_act_or_producer': False, 'full_game': False,
                  'field_economics': False, 'defaults_or_archive_changed': False}}
    text = json.dumps(receipt, indent=2, sort_keys=True) + '\n'
    if args.output:
        args.output.write_text(text)
    print(text)
    return 0 if receipt['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
