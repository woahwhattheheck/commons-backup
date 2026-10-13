# SPDX-License-Identifier: Apache-2.0
"""Independent official-engine evidence for the existing V4 EVENTPATH score lane.

This is an oracle, not another score implementation or agent. It authenticates
all 109 files in the existing checked b567 runtime, uses the pinned official
market and town functions, and optionally tests an explicitly SHA-pinned full
candidate module. Candidate code is loaded only after the caller-supplied pin
matches. Run each candidate/surface in a separate process.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import importlib.util
import io
import json
import random
import sys
import types
import unittest
from unittest import mock
from pathlib import Path

SOURCE_SHA256 = 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'
SURFACE_PINS = {
    'scheduler': '00d72a5c6b511e73ed1923ea402c4a36e0f9490f3b4c177490ddc72440f4a64a',
    'selected_sell_core': '6588b37ebb8237422513eb65ba1b5478a426dd193da34d42e0b4b7e6c13f4846',
}
CTX = {}
COUNTS = {'worlds': 0, 'market_calls': 0, 'town_calls': 0, 'score_comparisons': 0,
          'optimizer_pairs': 0, 'mutation_rejections': 0}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def authenticate(root: Path) -> dict:
    raw = (root / 'SOURCE.json').read_bytes()
    if sha(raw) != SOURCE_SHA256:
        raise ValueError('wrong checked-runtime SOURCE.json: expected exact b567 package')
    manifest = json.loads(raw)
    files = manifest['runtime']
    if len(files) != 109:
        raise ValueError('runtime manifest must contain exactly 109 pinned members')
    for name, expected in files.items():
        path = (root / name).resolve()
        if root.resolve() not in path.parents:
            raise ValueError('runtime path escapes root')
        data = path.read_bytes()
        if len(data) != expected['bytes'] or sha(data) != expected['sha256']:
            raise ValueError('runtime member differs: ' + name)
    return {'source_sha256': sha(raw), 'runtime_files_verified': len(files)}


def load_source(root: Path, surface: str, source: str, name: str):
    # Retain the actual runtime-relative dependency path without modifying it.
    mod = types.ModuleType(name)
    mod.__file__ = str(root / (surface + '.py'))
    sys.modules[name] = mod
    exec(compile(source, mod.__file__, 'exec'), mod.__dict__)
    return mod


def prepare(root: Path, candidate: Path | None, candidate_sha: str | None,
            surface: str) -> dict:
    if bool(candidate) != bool(candidate_sha):
        raise ValueError('--candidate and --candidate-sha256 must be supplied together')
    receipt = authenticate(root)
    sys.path.insert(0, str(root))
    originals = {}
    for key, expected in SURFACE_PINS.items():
        data = (root / (key + '.py')).read_bytes()
        if sha(data) != expected:
            raise ValueError('wrong predecessor ' + key)
        originals[key] = load_source(root, key, data.decode(), 'eventpath_original_' + key)
    spec = importlib.util.spec_from_file_location(
        'eventpath_evaluator', root / 'checks/reference/evaluator/evaluate.py')
    ev = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ev)
    engine, hashes = ev.get_engine(root / 'checks/reference/engine',
                                   root / 'checks/reference/evaluator/loader.py')
    tested = dict(originals)
    if candidate:
        data = candidate.read_bytes()
        if sha(data) != candidate_sha:
            raise ValueError('candidate SHA256 mismatch; code was not loaded')
        tested['candidate_' + surface] = load_source(
            root, surface, data.decode(), 'eventpath_candidate_' + surface)
        receipt['candidate'] = {'surface': surface, 'sha256': sha(data), 'bytes': len(data)}
    receipt['engine'] = hashes
    receipt['predecessors'] = SURFACE_PINS
    CTX.update(root=root, ev=ev, engine=engine, originals=originals,
               tested=tested, surface=surface, receipt=receipt)
    return receipt


def world(case: dict, seat: int):
    """Actual public/private engine state; both players have physical sale stock."""
    e, S = CTX['engine'], CTX['ev'].Struct
    cfg = S({k: v.get('default') if isinstance(v, dict) else v
             for k, v in e.specification['configuration'].items()})
    cfg.update(case['config'])
    cfg.maxMarketOrdersPerTurn = 10
    cfg.weedSpawnChance = 0
    farms = [e._new_farm(10, 0), e._new_farm(10, 0)]
    market = e._new_market(copy.deepcopy(case['params']))
    market['inventory'][case['item']] = case['inventory']
    e._refresh_prices(market)
    town = {'unlocked_shops': list(case['shops'])}
    state = []
    for player in range(2):
        private = e._new_private()
        private['shed'][case['item']] = case['quantity'] if player == seat else 100
        obs = S(player=player, step=case['now'], day=case['now'] // 24,
                hour=case['now'] % 24, farms=farms, private=private,
                market=market, town=town)
        state.append(S(observation=obs, action={'farmer': ['PASS'], 'hands': [],
                                                'market': []}, status='ACTIVE', reward=0))
    COUNTS['worlds'] += 1
    return state, S(configuration=cfg, done=False, info={'seed': 9600911})


def engine_score(case: dict, seat: int) -> tuple:
    """Oracle: execute actual market slots, then actual town demand, then carry.

    No MarketPath, sale_receipts, absorption helper, price curve, or own copy of
    town arithmetic is used here. Carry is valued by a separate physical SELL
    after the last town transition; it is not falsely counted as an action in
    the authored planning horizon.
    """
    e = CTX['engine']
    state, env = world(case, seat)
    own, rival_seat = state[seat], state[1 - seat]
    item = case['item']
    plan = dict(case['plan'])
    rival = (dict(case['rival']) if isinstance(case['rival'], tuple)
             else {case['now']: case['rival']})
    for step in range(case['now'], case['end'] + 1):
        for member in state:
            member.observation.update(step=step, day=step // 24, hour=step % 24)
        quantity = min(own.observation.private['shed'][item], max(0, plan.get(step, 0)))
        q = [['SELL', item, quantity]]
        r = [['SELL', item, rival.get(step, 0)]]
        if case['alignment'] == 'after':
            r.insert(0, [])
        elif case['alignment'] == 'before':
            q.insert(0, [])
        own.action['market'], rival_seat.action['market'] = q, r
        e._process_market(state, env)
        COUNTS['market_calls'] += 1
        e._town_consume(env, state, step)
        COUNTS['town_calls'] += 1
    farms = own.observation.farms
    a, b = farms[seat]['money'], farms[1 - seat]['money']
    remaining = own.observation.private['shed'][item]
    carry = 0.0
    ending_inventory = own.observation.market['inventory'][item]
    if remaining and not case['terminal']:
        own.action['market'] = [['SELL', item, remaining]]
        rival_seat.action['market'] = []
        e._process_market(state, env)
        COUNTS['market_calls'] += 1
        carry = float(farms[seat]['money'] - a)
    return (a + carry - b, a, b, remaining), ending_inventory


def model_score(module, case):
    model = module.MarketPath(case['item'], case['inventory'], case['params'],
                              case['shops'], case['config'], case['now'], case['end'])
    return model.score(case['plan'], case['quantity'], case['rival'],
                       case['alignment'], case['terminal'])


def vectors():
    e = CTX['engine']
    all_shops = tuple(e.SHOPS)
    for product_index, item in enumerate(e.PRODUCTS):
        for offset in (-40, 0, 76):
            for alignment in ('paired', 'before', 'after'):
                for pattern in range(4):
                    now = (0, 23, 701, 710)[pattern]
                    end = now + 8
                    quantity = 13
                    if pattern == 0:
                        plan, rival = ((now, 13),), 7
                    elif pattern == 1:
                        plan = ((end, 8), (now, 5))
                        rival = ((now + 1, 9), (end - 1, 5))
                    elif pattern == 2:
                        plan, rival = (), ((end, 4),)
                    else:
                        # Last duplicate wins, negative own request clamps to
                        # zero, outside dates do nothing, oversell clamps stock.
                        plan = ((now - 1, 50), (now, 4), (now, 3),
                                (now + 2, -5), (end, 30), (end + 1, 50))
                        rival = ((now, 2), (now, 6), (end + 1, 20))
                    params = copy.deepcopy(e.MARKET_PARAMS)
                    if pattern == 1:
                        params[item]['base'] += 3
                    shops = (all_shops if pattern == 0 else
                             ('YARN_STORE', 'YARN_STORE', 'PIZZA_SHOP', 'PET_CAFE')
                             if pattern == 1 else ('SMOOTHIE_SHOP', 'BAKERY'))
                    yield dict(item=item, quantity=quantity, inventory=10000 + offset,
                               params=params, shops=shops, now=now, end=end,
                               config={'townShopSellInterval': (1, 4, 3, 4)[pattern],
                                       'townCenterSellInterval': (24, 7, 24, 24)[pattern]},
                               plan=plan, rival=rival, alignment=alignment,
                               terminal=pattern in (0, 3))


class EventPathEngineTests(unittest.TestCase):
    def test_01_full_score_against_official_market_and_town_both_seats(self):
        count = 0
        for case in vectors():
            for seat in (0, 1):
                expected, _ = engine_score(case, seat)
                for name, module in CTX['tested'].items():
                    with self.subTest(surface=name, item=case['item'], now=case['now'],
                                      inventory=case['inventory'],
                                      alignment=case['alignment'], seat=seat):
                        self.assertEqual(model_score(module, case), expected)
                    COUNTS['score_comparisons'] += 1
                count += 1
        self.assertEqual(count, 648)

    def test_02_floor_admission_and_same_step_demand_witness(self):
        case = next(c for c in vectors() if c['item'] == 'MILK')
        case.update(inventory=10075, quantity=4, now=24, end=24,
                    plan=((24, 4),), rival=0, terminal=True, shops=())
        for seat in (0, 1):
            expected, inventory = engine_score(case, seat)
            self.assertEqual(expected, (6.0, 6, 0, 0))
            self.assertEqual(inventory, 10075)  # admit one, then town consumes one
            for module in CTX['tested'].values():
                self.assertEqual(model_score(module, case), expected)
        CTX['receipt']['same_step_witness'] = {'initial_inventory': 10075,
            'own_quantity': 4, 'own_cash': 6, 'post_town_inventory': 10075,
            'step': 24, 'claim': 'market before town, not town before market'}

    def test_03_empty_and_single_step_horizons(self):
        case = next(vectors())
        for end in (case['now'] - 1, case['now']):
            for terminal in (False, True):
                case.update(end=end, terminal=terminal, plan=())
                for seat in (0, 1):
                    expected, _ = engine_score(case, seat)
                    for module in CTX['tested'].values():
                        self.assertEqual(model_score(module, case), expected)

    def test_04_context_mutation_invalidates_cache(self):
        for name, module in CTX['tested'].items():
            case = next(c for c in vectors() if c['item'] == 'WOOL')
            case.update(plan=(), terminal=False, shops=[], rival=0)
            model = module.MarketPath(case['item'], case['inventory'], case['params'],
                                     [], dict(case['config']), case['now'], case['end'])
            for change in range(6):
                if change == 1:
                    model.shops.extend(['YARN_STORE', 'YARN_STORE'])
                elif change == 2:
                    model.config['townShopSellInterval'] = 3
                elif change == 3:
                    model.config['townCenterSellInterval'] = 5
                elif change == 4:
                    model.end += 4
                elif change == 5:
                    model.now += 1
                case.update(shops=list(model.shops), config=dict(model.config),
                            now=model.now, end=model.end)
                expected, _ = engine_score(case, 0)
                with self.subTest(surface=name, mutation=change):
                    self.assertEqual(model.score((), 13, 0, 'paired', False), expected)

    def test_05_source_guard_rejects_wrong_runtime(self):
        # The accepted manifest is fixed by literal SHA, not a user-mutable
        # collection of self-reported member hashes.
        self.assertEqual(sha((CTX['root'] / 'SOURCE.json').read_bytes()), SOURCE_SHA256)
        self.assertEqual(len(CTX['receipt']['engine']), 3)
        self.assertEqual(CTX['receipt']['runtime_files_verified'], 109)
        original_read = Path.read_bytes
        for relative in ('SOURCE.json', 'mechanics.py',
                         'checks/reference/engine/kaggriculture.py'):
            target = (CTX['root'] / relative).resolve()
            def altered_read(path):
                data = original_read(path)
                return data + b'\n# altered evidence' if path.resolve() == target else data
            with self.subTest(member=relative), mock.patch.object(Path, 'read_bytes', altered_read):
                with self.assertRaises(ValueError):
                    authenticate(CTX['root'])

    def test_06_complete_optimizer_and_capacity_callback_parity(self):
        candidate = CTX['tested'].get('candidate_' + CTX['surface'])
        if candidate is None:
            self.skipTest('no candidate supplied: engine-baseline certification only')
        original = CTX['originals'][CTX['surface']]
        rng = random.Random(9600911)
        for index in range(36):
            item = rng.choice(CTX['engine'].PRODUCTS)
            now = rng.choice((0, 23, 701, 710))
            quantity = rng.randrange(1, 19)
            minimum = 0 if index % 3 else quantity // 3
            rule = ('strict', 'expected_downside', 'minimax_regret')[index % 3]
            kwargs = dict(item=item, quantity=quantity, inventory=rng.randrange(9940, 10110),
                          params=CTX['engine'].MARKET_PARAMS, shops=['PIZZA_SHOP', 'YARN_STORE'],
                          config={'sellAcceptanceRule': rule, 'sellDownsideBound': 10},
                          now=now, dates=[now, now + 1, now + 4, now + 8],
                          reference=((now, quantity),), rival_quantity=rng.randrange(0, 20),
                          minimum_now=minimum)
            logs = [[], []]
            answers = []
            for position, module in enumerate((original, candidate)):
                def capacity(plan, position=position):
                    logs[position].append(tuple(plan))
                    return sum(q for _, q in plan) <= quantity and (
                        index % 4 != 0 or dict(plan).get(now, 0) >= minimum)
                answers.append(module.optimize_lot(**kwargs, capacity_ok=capacity))
            with self.subTest(case=index, rule=rule):
                self.assertEqual(answers[0], answers[1])
                self.assertEqual(logs[0], logs[1])
            COUNTS['optimizer_pairs'] += 1

    def test_07_oracle_rejects_timing_and_rival_and_carry_mutants(self):
        # Independent evidence must distinguish subtle wrong schedules, not
        # just echo the baseline. Mutate inputs to a real scorer, compare with
        # the unmutated physical engine world, and require actual mismatches.
        module = CTX['originals']['selected_sell_core']
        rejected = set()
        for case in vectors():
            expected, _ = engine_score(case, 0)
            mutants = {}
            shifted = copy.deepcopy(case)
            shifted.update(now=case['now'] + 1, end=case['end'] + 1,
                           plan=tuple((t + 1, q) for t, q in case['plan']))
            if isinstance(case['rival'], tuple):
                shifted['rival'] = tuple((t + 1, q) for t, q in case['rival'])
            mutants['wrong_calendar_phase'] = shifted
            mutants['drop_rival'] = dict(case, rival=0)
            mutants['drop_residual_carry'] = dict(case, terminal=True)
            mutants['deduplicate_town_shops'] = dict(case, shops=tuple(dict.fromkeys(case['shops'])))
            for label, altered in mutants.items():
                if model_score(module, altered) != expected:
                    rejected.add(label)
            if len(rejected) == 4:
                break
        self.assertEqual(rejected, {'wrong_calendar_phase', 'drop_rival',
                                    'drop_residual_carry', 'deduplicate_town_shops'})
        COUNTS['mutation_rejections'] = len(rejected)

    def test_08_frozen_consumer_uses_active_core_not_standalone_optimizer(self):
        frozen = importlib.import_module('frozen_selected')
        active = importlib.import_module('selected_sell_core')
        standalone = importlib.import_module('scheduler')
        config = json.loads((CTX['root'] / 'TITAN-CONFIG.json').read_text())
        self.assertEqual(config['consumer'], 'frozen')
        self.assertIs(frozen.optimize_lot, active.optimize_lot)
        self.assertIsNot(frozen.optimize_lot, standalone.optimize_lot)
        CTX['receipt']['active_callpath'] = 'consumer=frozen -> frozen_selected.optimize_lot -> selected_sell_core.optimize_lot'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--candidate-sha256')
    parser.add_argument('--surface', choices=tuple(SURFACE_PINS), default='selected_sell_core')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        receipt = prepare(args.runtime_root.resolve(), args.candidate,
                          args.candidate_sha256, args.surface)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, str(exc) + '\n')
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(EventPathEngineTests))
    sys.stderr.write(stream.getvalue())
    receipt.update(schema='titan-v4-eventpath-official-score-v1',
                   validation='candidate-and-baselines' if args.candidate else 'baselines-only',
                   optimized_python=not __debug__, counts=COUNTS,
                   unittest={'run': result.testsRun, 'failures': len(result.failures),
                             'errors': len(result.errors), 'skipped': len(result.skipped)},
                   passed=result.wasSuccessful(),
                   exclusions=['no full game or runtime-action timing claim',
                               'no production/default/archive/Kaggle modification'])
    data = json.dumps(receipt, indent=2, sort_keys=True) + '\n'
    if args.output:
        args.output.write_text(data, encoding='utf-8')
    print(data, end='')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
