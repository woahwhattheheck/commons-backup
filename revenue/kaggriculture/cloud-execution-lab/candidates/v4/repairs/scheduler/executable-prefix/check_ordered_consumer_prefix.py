# SPDX-License-Identifier: Apache-2.0
"""Pinned actual-class/ALDER/ATLAS/official-engine regression; no game panel.

Run with --package-root pointing at the already materialized reference package.
No tests are skipped when an input is missing or differs: startup exits 2.
"""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import ordered_consumer_prefix as repair

PINS = {
    'integrated_selected.py': 'defa9b84c77fff28ae107bce291b6235bec5d26c',
    'mechanics.py': '044a4f9c0a4a44dde10ada57563238bcaf82075d',
    'ordered_selected_sell.py': '8ce1394077df47dfc322a44f363050a6467292a3',
    'selected_action_sell.py': '7d0f4e681f2aaeac9a9495094033883f85f69a50',
    'selected_sell_core.py': 'd2cded3d35d4a60318e0dff71602c6b395dac3b8',
    'plant_suffix.py': '95d05ff28aa79074d82bdc08ce4148d3ace1b13d',
    'reference/integrated-selected/alder/seed_budget.py': 'eaa244ba05104535f9922a5f76d623a76c187096',
    'reference/selected-action/t08/arrival_contract.py': 'd72c0889b3f2348a23eb7c227fbe1a32ab9e5c4e',
    'reference/ordered-feasibility/atlas/projection.py': '436222e45bbbba2dd69f62191751f1ab568529f3',
    'checks/reference/engine/kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
    'checks/reference/engine/kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
}
ROOT = None
BASE = CANDIDATE = ENGINE = None
SOURCE = b''
RESULTS = {'projection_matrix_cells': 0, 'seed_matrix_cells': 0,
           'official_market_pairs': 0, 'mutants_rejected': 0}


class Struct(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as error:
            raise AttributeError(name) from error
    __setattr__ = dict.__setitem__


def action(market=None, farmer=None, hands=None):
    return {'farmer': deepcopy(farmer if farmer is not None else ['PASS']),
            'hands': deepcopy(hands if hands is not None else []),
            'market': deepcopy(market if market is not None else [])}


def load_source(name, source, path):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(source, str(path), 'exec'), module.__dict__)
    return module


def initialize(root):
    global ROOT, SOURCE, BASE, CANDIDATE, ENGINE
    ROOT = root.resolve()
    for relative, expected in PINS.items():
        path = ROOT / relative
        if path.is_symlink() or not path.is_file() or repair.git_blob(path.read_bytes()) != expected:
            raise ValueError(f'missing or different pinned input: {relative}')
    # Import only the authenticated fixture modules, not the archived main or
    # runtime. This process has no previous production module instances.
    sys.path.insert(0, str(ROOT))
    SOURCE = (ROOT / 'integrated_selected.py').read_bytes()
    BASE = load_source('ordered_prefix_base', SOURCE, ROOT / 'integrated_selected.py')
    CANDIDATE = load_source('ordered_prefix_candidate', repair.compose(SOURCE),
                            ROOT / 'integrated_selected.py')
    utility = types.ModuleType('kaggle_environments.utils')
    def no_seed_initialization(*args, **kwargs):
        raise AssertionError('fixture must not invoke unpinned environment initialization')
    utility.resolve_episode_seed = no_seed_initialization
    with patch.dict(sys.modules, {'kaggle_environments.utils': utility}):
        path = ROOT / 'checks/reference/engine/kaggriculture.py'
        ENGINE = load_source('ordered_prefix_official_engine', path.read_bytes(), path)


def fixture(seat=0, cap=10, step=100, cash=10000):
    farms = [ENGINE._new_farm(10, cash) for _ in range(2)]
    market = ENGINE._new_market()
    state = []
    for player in range(2):
        farms[player]['farmer'] = list(ENGINE._shed_access_tiles(10)[0])
        obs = Struct(player=player, step=step, day=step // 24, hour=step % 24,
                     farms=farms, private=ENGINE._new_private(), market=market,
                     town={'unlocked_shops': []})
        state.append(Struct(observation=obs, action=action(), status='ACTIVE', reward=0))
    cfg = Struct(episodeSteps=720, turnsPerDay=24, boardSize=10, shedCapacity=100,
                 maxMarketOrdersPerTurn=cap, farmHandCostMult=1, weedSpawnChance=0,
                 townShopUnlockInterval=3)
    env = Struct(configuration=cfg, done=False, info={'seed': 7})
    return state[seat].observation, cfg, state, env


class EmptyProduction:
    """Only route/empty-commitment inputs; never a substitute game transition."""
    def __init__(self, route, switches=()):
        self.agent = types.SimpleNamespace(R={0: route}, cur=0)
        self.A = types.SimpleNamespace(DECISIONS=switches)
        self.one_way, self.max_steps, self.plans = True, 50, {}
    def act(self, *args):
        raise AssertionError('selected-action consumer must never call its producer')
    def producer_snapshot(self, obs, selected):
        return {'owner': 'pinned-prefix-fixture', 'observed_step': obs['step'], 'plans': []}


def agent(module, route, *, seed=True, sell=False, selector=None, switches=()):
    return module.IntegratedSelectedAgent(EmptyProduction(route, switches),
                seed=seed, sell=sell, seed_queue_selector=selector)


def route_of(length=130):
    return [action() for _ in range(length)]


def project(module, obs, cfg, selected, route, switches=()):
    consumer = agent(module, route, seed=False, switches=switches)
    return consumer._projection(obs, cfg, selected, deepcopy(obs['farms'][obs['player']]),
                                deepcopy(obs['private']), {})


class PrefixTests(unittest.TestCase):
    def test_current_source_and_exact_scope(self):
        out = repair.compose(SOURCE)
        self.assertNotEqual(out, SOURCE)
        self.assertEqual(repair.git_blob(out), '282d58612f80fec29109fbcd38fac0b317063c17')
        self.assertEqual(repair._outside_target_methods(ast.parse(SOURCE)),
                         repair._outside_target_methods(ast.parse(out)))

    def test_source_drift_and_double_apply_rejected(self):
        for source in (SOURCE + b'\n', SOURCE[:-1], repair.compose(SOURCE), b''):
            with self.assertRaises(ValueError):
                repair.compose(source)

    def test_future_dead_buy_no_longer_truncates_real_projection(self):
        obs, cfg, _, _ = fixture(cap=1)
        obs['private']['inventories'][0] = {'MILK': 3}
        route = route_of()
        route[101] = action([[], ['BUY_PRODUCT', 'WHEAT', 2]], ['DROP'])
        saved = deepcopy((obs, cfg, route))
        old, _ = project(BASE, obs, cfg, action(), route)
        new, why = project(CANDIDATE, obs, cfg, action(), route)
        self.assertEqual(old['end_step'], 100)
        self.assertEqual(new['end_step'], 108)
        self.assertEqual(new['future_market'][101], [[]])
        self.assertIn({'step': 101, 'phase': 'before_market', 'product': 'MILK',
                       'quantity_delta': 3, 'worker_index': 0, 'operation': 'DROP'}, new['stock_events'])
        self.assertEqual(why['end_reason'], 'horizon')
        self.assertEqual((obs, cfg, route), saved)

    def test_active_future_buy_keeps_cash_boundary(self):
        for cap in (-3, 0, 1, 2, 10):
            obs, cfg, _, _ = fixture(cap=cap)
            route = route_of()
            route[101] = action([['BUY_PRODUCT', 'WHEAT', 2]])
            projected, details = project(CANDIDATE, obs, cfg, action(), route)
            self.assertEqual(projected['end_step'], 100)
            self.assertEqual(details['end_reason'], 'future_product_purchase_needs_cash_bound')

    def test_projection_suffix_matrix_raw_slots_and_engine_parity(self):
        tails = (['BUY_PRODUCT', 'WHEAT', 2], ['BUY_PRODUCT', 'FERTILIZER', 3],
                 ['HIRE'], ['BUY_ANIMAL', 'COW', 1], ['SELL', 'MILK', 4],
                 None, ['BUY_PRODUCT'], [], {'poison': 'outside-prefix'})
        for seat in (0, 1):
            for cap in (-3, 0, 1, 2, 5, 10):
                active = [[] for _ in range(max(1, cap))]
                obs, cfg, _, _ = fixture(seat, cap)
                route = route_of(); route[101] = action(active, ['DROP'])
                expected = project(CANDIDATE, obs, cfg, action(), route)
                for tail in tails:
                    with self.subTest(seat=seat, cap=cap, tail=tail):
                        changed = deepcopy(route); changed[101]['market'].append(deepcopy(tail))
                        self.assertEqual(project(CANDIDATE, obs, cfg, action(), changed), expected)
                        RESULTS['projection_matrix_cells'] += 1
                        a, b = fixture(seat, cap)[2:], fixture(seat, cap)[2:]
                        a[0][seat].action = action(active)
                        b[0][seat].action = action(active + [deepcopy(tail)])
                        ENGINE._process_market(*a); ENGINE._process_market(*b)
                        self.assertEqual([dict(observation=r.observation, status=r.status, reward=r.reward) for r in a[0]],
                                         [dict(observation=r.observation, status=r.status, reward=r.reward) for r in b[0]])
                        self.assertEqual(a[0][seat].action, action(active))
                        self.assertEqual(b[0][seat].action, action(active + [deepcopy(tail)]))
                        RESULTS['official_market_pairs'] += 1

    def test_dead_suffix_hire_no_longer_vetoes_real_alder_reduction(self):
        obs, cfg, _, _ = fixture(cap=10)
        route = route_of(); route[101] = action(farmer=['PLANT', 'WHEAT'])
        selected = action([['BUY_SEED', 'WHEAT', 10]] + [[] for _ in range(9)] + [['HIRE']])
        old_agent, new_agent = agent(BASE, route), agent(CANDIDATE, route)
        old = old_agent.transform(obs, cfg, selected)
        new = new_agent.transform(obs, cfg, selected)
        self.assertEqual(old['market'][0], ['BUY_SEED', 'WHEAT', 10])
        self.assertEqual(new['market'][0], ['BUY_SEED', 'WHEAT', 1])
        self.assertEqual(new['market'][1:], selected['market'][1:])
        self.assertEqual(old_agent.diagnostics['seed_reason'], 'later_economic_order')
        self.assertEqual(new_agent.diagnostics['seed_reason'], 'applied')
        outcomes = []
        for out in (old, new):
            _, _, state, env = fixture(cap=10, cash=100)
            state[0].action = out; ENGINE.interpreter(state, env)
            outcomes.append((state[0].observation.farms[0]['money'],
                             state[0].observation.private['seeds']['WHEAT'],
                             len(state[0].observation.farms[0]['hands'])))
        self.assertEqual(outcomes, [(0, 10, 0), (90, 1, 0)])
        RESULTS['dead_hire_witness'] = {'baseline': outcomes[0], 'repair': outcomes[1],
                                        'units': ['cash', 'wheat_seeds', 'hands']}

    def test_active_dependencies_and_selector_remain_owned(self):
        route = route_of(); route[101] = action(farmer=['PLANT', 'WHEAT'])
        for op in (['HIRE'], ['BUY_LAND'], ['BUY_ANIMAL', 'COW', 1], ['BUY_PRODUCT', 'WHEAT', 1]):
            obs, cfg, _, _ = fixture(cap=2)
            selected = action([['BUY_SEED', 'WHEAT', 10], op])
            self.assertEqual(agent(CANDIDATE, route).transform(obs, cfg, selected), selected)
            called = []
            def selector(m, post, original, proposed, config):
                called.append(deepcopy(proposed))
                return original, {'status': 'not_certified'}
            out = agent(CANDIDATE, route, selector=selector).transform(obs, cfg, selected)
            self.assertEqual(out, selected); self.assertEqual(len(called), 1)

    def test_seed_suffix_matrix_preserves_all_inert_bytes(self):
        route = route_of(); route[101] = action(farmer=['PLANT', 'WHEAT'])
        tails = (['HIRE'], ['BUY_LAND'], ['BUY_ANIMAL', 'COW', 1],
                 ['BUY_PRODUCT', 'FERTILIZER', 8], ['BUY_SEED', 'WHEAT', 50],
                 None, [], ['SELL', 'MILK', 50], {'unparsed': True})
        for seat in (0, 1):
            for cap in (-2, 0, 1, 2, 5, 10):
                obs, cfg, _, _ = fixture(seat, cap)
                prefix = [['BUY_SEED', 'WHEAT', 10]] + [[] for _ in range(max(1, cap)-1)]
                for tail in tails:
                    with self.subTest(seat=seat, cap=cap, tail=tail):
                        selected = action(prefix + [deepcopy(tail)])
                        saved = deepcopy((selected, obs, cfg, route))
                        def forbidden(*args):
                            raise AssertionError('dead suffix may not invoke funding selector')
                        tx = agent(CANDIDATE, route, selector=forbidden)
                        out = tx.transform(obs, cfg, selected)
                        self.assertEqual(out['market'][0], ['BUY_SEED', 'WHEAT', 1])
                        self.assertEqual(out['market'][1:], selected['market'][1:])
                        self.assertEqual((selected, obs, cfg, route), saved)
                        self.assertEqual(len(tx.budget.events), 1)
                        RESULTS['seed_matrix_cells'] += 1

    def test_no_in_prefix_change_preserves_baseline_output(self):
        for seed in (False, True):
            for market in ([], [['SELL', 'MILK', 1]], [['BUY_SEED', 'WHEAT', 1]],
                           [['BUY_SEED', 'WHEAT', 5], ['HIRE']]):
                obs, cfg, _, _ = fixture()
                route = route_of(); route[101] = action(farmer=['PLANT', 'WHEAT'])
                selected = action(market)
                self.assertEqual(agent(BASE, route, seed=seed).transform(obs, cfg, selected),
                                 agent(CANDIDATE, route, seed=seed).transform(obs, cfg, selected))

    def test_whole_ordered_consumer_packet_recovers_future_drop(self):
        obs, cfg, _, _ = fixture(cap=1)
        obs['private']['shed'] = {'MILK': 5}
        obs['private']['inventories'][0] = {'MILK': 3}
        route = route_of(); route[101] = action([[], ['BUY_PRODUCT', 'WHEAT', 2]], ['DROP'])
        old, new = agent(BASE, route, seed=False, sell=True), agent(CANDIDATE, route, seed=False, sell=True)
        for tx in (old, new):
            tx.transform(obs, cfg, action())
            self.assertIsNotNone(tx.last_packet)
        self.assertEqual(old.last_packet['projection']['end_step'], 100)
        self.assertEqual(new.last_packet['projection']['end_step'], 108)
        self.assertEqual(new.last_packet['projection']['stock_events'][0]['quantity_delta'], 3)

    def test_seed_repair_survives_real_sell_consumer(self):
        route = route_of(); route[101] = action(farmer=['PLANT', 'WHEAT'])
        for seat in (0, 1):
            obs, cfg, _, _ = fixture(seat, 10)
            selected = action([['BUY_SEED', 'WHEAT', 10]] + [[] for _ in range(9)] + [['HIRE']])
            tx = agent(CANDIDATE, route, sell=True)
            out = tx.transform(obs, cfg, selected)
            self.assertEqual(out['market'][0], ['BUY_SEED', 'WHEAT', 1])
            self.assertEqual(out['market'][1:], selected['market'][1:])
            self.assertIsNotNone(tx.last_packet)
            self.assertEqual(tx.diagnostics['seed_reason'], 'applied')

    def test_nonpositive_cap_executes_first_seed_slot_in_engine(self):
        route = route_of(); route[101] = action(farmer=['PLANT', 'WHEAT'])
        for cap in (0, -1, -10):
            for seat in (0, 1):
                obs, cfg, state, env = fixture(seat, cap, cash=100)
                selected = action([['BUY_SEED', 'WHEAT', 10], ['HIRE']])
                out = agent(CANDIDATE, route).transform(obs, cfg, selected)
                self.assertEqual(out['market'], [['BUY_SEED', 'WHEAT', 1], ['HIRE']])
                state[seat].action = out
                ENGINE._process_market(state, env)
                self.assertEqual(obs['farms'][seat]['money'], 90)
                self.assertEqual(obs['private']['seeds']['WHEAT'], 1)
                self.assertEqual(obs['farms'][seat]['hands'], [])

    def test_missing_fixture_never_reports_a_skipped_green(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, __file__, '--package-root', directory],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn('INPUT_ERROR', result.stderr)
            self.assertNotIn('"tests_run"', result.stdout)

    def test_existing_route_eod_terminal_and_stock_boundaries_unchanged(self):
        for step, expected in ((22, 23), (23, 23), (710, 718), (718, 718)):
            obs, cfg, _, _ = fixture(step=step)
            route = route_of(719)
            self.assertEqual(project(BASE, obs, cfg, action(), route),
                             project(CANDIDATE, obs, cfg, action(), route))
            self.assertEqual(project(CANDIDATE, obs, cfg, action(), route)[0]['end_step'], expected)
        obs, cfg, _, _ = fixture()
        route = route_of(); route[101] = action(farmer=['PICKUP', 'MILK', 1])
        self.assertEqual(project(BASE, obs, cfg, action(), route),
                         project(CANDIDATE, obs, cfg, action(), route))
        route[101] = action()
        self.assertEqual(project(CANDIDATE, obs, cfg, action(), route, ((102, 0),))[0]['end_step'], 101)

    def test_selected_extra_plant_guard_preserved(self):
        obs, cfg, _, _ = fixture()
        selected = action([['BUY_SEED', 'WHEAT', 10]], ['PLANT', 'WHEAT'])
        tx = agent(CANDIDATE, route_of())
        self.assertEqual(tx.transform(obs, cfg, selected), selected)
        self.assertEqual(tx.diagnostics['seed_reason'], 'selected_plant_requests_exceed_route')

    def test_both_seed_and_projection_mutants_are_detectable(self):
        text = repair.compose(SOURCE).decode()
        variants = [text.replace("action.get('market', [])[:maximum]", "action.get('market', [])"),
                    text.replace("selected['market'][i+1:maximum]", "selected['market'][i+1:]")]
        for number, variant in enumerate(variants):
            mutant = load_source(f'ordered_mutant_{number}', variant, ROOT/'integrated_selected.py')
            obs, cfg, _, _ = fixture(cap=1)
            route = route_of(); route[101] = action([[], ['BUY_PRODUCT', 'WHEAT', 1]], ['PLANT', 'WHEAT'])
            if number == 0:
                self.assertNotEqual(project(mutant, obs, cfg, action(), route),
                                    project(CANDIDATE, obs, cfg, action(), route))
            else:
                selected = action([['BUY_SEED', 'WHEAT', 10], ['HIRE']])
                self.assertNotEqual(agent(mutant, route).transform(obs, cfg, selected),
                                    agent(CANDIDATE, route).transform(obs, cfg, selected))
            RESULTS['mutants_rejected'] += 1

    def test_cli_determinism_readback_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/'input.py'; source.write_bytes(SOURCE)
            outputs = []
            for name in ('one.py', 'two.py'):
                target = root/name
                result = subprocess.run([sys.executable, str(Path(repair.__file__)), str(source),
                                         '--output', str(target)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                outputs.append((target.read_bytes(), json.loads(result.stdout)))
            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual(source.read_bytes(), SOURCE)
            result = subprocess.run([sys.executable, str(Path(repair.__file__)), str(source),
                                     '--output', str(source)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(source.read_bytes(), SOURCE)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-root', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        initialize(args.package_root)
    except (OSError, ValueError, ImportError, SyntaxError) as error:
        print(f'INPUT_ERROR: {error}', file=sys.stderr)
        return 2
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PrefixTests))
    for relative, expected in PINS.items():
        if repair.git_blob((ROOT/relative).read_bytes()) != expected:
            print(f'INPUT_ERROR: fixture mutated: {relative}', file=sys.stderr)
            return 2
    print(json.dumps({'schema': 'titan-v4-ordered-prefix-tests/v1', 'tests_run': result.testsRun,
                     'failures': len(result.failures), 'errors': len(result.errors),
                     'skipped': len(result.skipped), 'optimized': not __debug__,
                     'source_blob': repair.SOURCE_BLOB, 'candidate_blob': repair.git_blob(repair.compose(SOURCE)),
                     'input_pins': PINS, 'full_games_run': 0, 'production_changed': False, **RESULTS}, sort_keys=True))
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == '__main__':
    raise SystemExit(main())
