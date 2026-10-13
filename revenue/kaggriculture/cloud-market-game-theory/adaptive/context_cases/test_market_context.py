# SPDX-License-Identifier: Apache-2.0
"""Source-bound adaptive context checks; no full games or new random seeds.

Runs the actual AdaptiveTransform/Agent.act definitions, actual selector and
continuation implementations, and actual MarketPath. A small explicit ledger
fixture supplies physical feasibility; it is not a production controller. The
optional engine test executes complete official action transitions on hand-built
states. No hidden rival action is supplied to the policy: the one rival stream
is an explicitly hypothetical model column, used as truth only by the evaluator.
"""
from __future__ import annotations
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys
import types
import unittest
from fractions import Fraction
from math import lcm
from threading import RLock

ARGS = None
G = None
CORE = None
RECOURSE = None
ENGINE = None
EVIDENCE = []


def file_meta(path):
    b = Path(path).read_bytes()
    return {'path': str(path), 'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest(),
            'git_blob': hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()}


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def never_solve(*args, **kwargs):
    raise AssertionError('This recourse boundary must not call a mixed-table solver')


def load_sources(args):
    global G, CORE, RECOURSE, ENGINE
    sys.path.insert(0, str(Path(args.core).resolve().parent))
    CORE = module(args.core, 'context_actual_core')
    RECOURSE = module(args.recourse, 'context_actual_recourse')
    sel = {'copy': copy, 'Fraction': Fraction, 'lcm': lcm, 'random': random,
           'solve_table': never_solve}
    node = next(n for n in ast.parse(Path(args.selector).read_text()).body
                if isinstance(n, ast.ClassDef) and n.name == 'WholePlanSelector')
    exec(compile(ast.Module(body=[node], type_ignores=[]), args.selector, 'exec'), sel)
    ash = module(args.continuation, 'context_actual_continuation')
    sale = types.SimpleNamespace(
        _sell=lambda o, item=None: bool(o and len(o) >= 3 and o[0] == 'SELL'
                                       and (item is None or o[1] == item)),
        PRODUCTS=CORE.m.PRODUCTS)
    G = {'deepcopy': copy.deepcopy, 'math': CORE, 'sale': sale, 'ash': ash,
         'WholePlanSelector': sel['WholePlanSelector'],
         'compile_policy': RECOURSE.compile_policy,
         'choose_observed': RECOURSE.choose_observed,
         '_CAPTURE_LOCK': RLock()}
    nodes = []
    for n in ast.parse(Path(args.runtime).read_text()).body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in (
                '_economic_context', '_context_reason', 'AdaptiveTransform', 'Agent'):
            nodes.append(n)
        elif isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and
                                               t.id == '_PRICE_FIELDS' for t in n.targets):
            nodes.append(n)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), args.runtime, 'exec'), G)
    if args.engine:
        tree = ast.parse(Path(args.engine).read_text())
        # The framework seed helper is not called by these constructed action
        # transitions; all game functions and constants remain unchanged.
        tree.body = [n for n in tree.body if not (isinstance(n, ast.ImportFrom)
                     and n.module == 'kaggle_environments.utils')]
        ENGINE = {'__file__': args.engine, 'resolve_episode_seed': never_solve}
        exec(compile(tree, args.engine, 'exec'), ENGINE)


def context(item='WOOL', params=None, shops=(), cfg=None, start=71, end=79):
    # Independent fixture snapshot, also lets the original runtime consume the
    # same enriched offer when measuring its missing check.
    p = (params or CORE.m.MARKET_PARAMS)[item]
    keys = ('base', 'I0', 'T', 'below_func', 'below_target', 'above_func', 'above_target')
    return {'version': 1, 'item': item, 'start': start, 'end': end,
            'price': {k: copy.deepcopy(p[k]) for k in keys},
            'absorption': [CORE.absorption(item, t, shops, cfg or {}) for t in range(start, end)]}


def observation(step=72, shops=(), params=None, player=0):
    market = {'inventory': {'WOOL': 10000}}
    if params is not None:
        market['params'] = copy.deepcopy(params)
    return {'step': step, 'player': player, 'market': market,
            'town': {'unlocked_shops': list(shops)},
            'private': {'shed': {'WOOL': 2}},
            'farms': [{'money': 5000}, {'money': 5000}]}


class Ledger:
    """Explicit physically feasible two-unit lot, fixed first market slot."""
    def __init__(self, now=72, end=79):
        self.now, self.end, self.max_orders = now, end, 10
        self.shed = {'WOOL': 2}
    def feasible(self, item, sales):
        return sum(q for _, q in sales) <= self.shed.get(item, 0)
    def market(self, step, item, quantity, stock):
        return [['SELL', item, quantity]]


def fixture(*, shops=(), cfg=None, mode='adaptive', active=True):
    cfg = cfg or {}
    plans = [{'id': str(t), 'sales': [[t, 2]]} for t in (73, 72, 76, 77, 79)]
    streams = [('hypothetical_later_slot', ((72, 2),), 'after')]
    model = CORE.MarketPath('WOOL', 10000, None, list(shops), cfg, 71, 79)
    tree = RECOURSE.compile_policy(model, plans, 2, streams, 72, CORE.absorption)
    tree['economic_context'] = context(shops=shops, cfg=cfg)
    tr = G['AdaptiveTransform'](mode)
    offer = {'tree': tree, 'item': 'WOOL', 'quantity': 2, 'end': 79}
    if active:
        tr.transform(observation(71, shops), cfg, {'farmer': ['PASS'], 'hands': [], 'market': []},
                     ledger=Ledger(71), offers=[offer])
        if tr.selector.active is None:
            raise AssertionError('Fixture failed to admit the actual compiled positive tree')
    return tr, offer


def fallback():
    return {'farmer': ['PASS'], 'hands': [['PASS']], 'market': [],
            'user_metadata': {'preserve': ['exact current parent']}}


class ContextTests(unittest.TestCase):
    def apply(self, tr, obs=None, cfg=None, base=None):
        obs = obs or observation()
        return tr.transform(obs, cfg or {}, base or fallback(), ledger=Ledger(obs['step']))

    def assert_retired(self, tr, out, reason='market_context_changed', base=None):
        self.assertEqual(out, base or fallback())
        self.assertIsNone(tr.selector.active)
        self.assertEqual(tr.last['reason'], reason)
        self.assertIn('71:WOOL:2:79', tr.selector.completed)
        self.assertEqual(tr.selector.draws, 0)

    def test_exact_current_core_economic_discriminator(self):
        tr, offer = fixture()
        tree = offer['tree']
        self.assertEqual(tree['choices']['10000'], 1)
        self.assertEqual(tree['deltas'][1], [1])
        model = CORE.MarketPath('WOOL', 10000, None, ['YARN_STORE'], {}, 72, 79)
        baseline = model.score(((73, 2),), 2, ((72, 2),), 'after', True)
        stale = model.score(((72, 2),), 2, ((72, 2),), 'after', True)
        self.assertEqual(baseline, (6, 406, 400, 0))
        self.assertEqual(stale, (1, 400, 399, 0))
        EVIDENCE.append({'kind': 'current_MarketPath_counterexample', 'old_delta': 1,
                         'baseline': baseline, 'obsolete_choice': stale, 'new_delta': -5,
                         'inventory': 10000, 'now': 71, 'branch': 72, 'end': 79})

    def test_unchanged_context_keeps_actual_choice(self):
        tr, _ = fixture()
        out = self.apply(tr)
        self.assertEqual(out['market'], [['SELL', 'WOOL', 2]])
        self.assertEqual(out['farmer'], ['PASS'])
        self.assertEqual(tr.counts['branches'], 1)
        self.assertEqual(tr.selector.draws, 0)

    def test_new_relevant_shop_returns_entire_fallback(self):
        for player in (0, 1):
            with self.subTest(player=player):
                tr, _ = fixture()
                base = fallback()
                before = copy.deepcopy(base)
                out = self.apply(tr, observation(shops=['YARN_STORE'], player=player), base=base)
                self.assert_retired(tr, out, base=base)
                self.assertEqual(base, before)
                out['user_metadata']['preserve'].append('detached')
                self.assertEqual(base, before)

    def test_irrelevant_shop_does_not_discard_choice(self):
        tr, _ = fixture()
        out = self.apply(tr, observation(shops=['PET_CAFE', 'BAKERY']))
        self.assertEqual(out['market'], [['SELL', 'WOOL', 2]])
        self.assertIsNotNone(tr.selector.active)

    def test_each_relevant_price_field_invalidates(self):
        changes = {'base': 201, 'I0': 9999, 'T': 106, 'below_func': 'linear',
                   'below_target': .3, 'above_func': 'linear', 'above_target': 3.3}
        for field, value in changes.items():
            with self.subTest(field=field):
                tr, _ = fixture()
                p = copy.deepcopy(CORE.m.MARKET_PARAMS)
                p['WOOL'][field] = value
                self.assert_retired(tr, self.apply(tr, observation(params=p)))

    def test_irrelevant_product_price_is_equivalent(self):
        tr, _ = fixture()
        p = copy.deepcopy(CORE.m.MARKET_PARAMS)
        p['EGG']['base'] = 999
        out = self.apply(tr, observation(params=p))
        self.assertEqual(out['market'], [['SELL', 'WOOL', 2]])

    def test_explicit_defaults_and_unused_keys_are_equivalent(self):
        tr, _ = fixture()
        p = copy.deepcopy(CORE.m.MARKET_PARAMS)
        p['WOOL']['unused_metadata'] = {'tag': 'not a pricing input'}
        out = self.apply(tr, observation(params=p), {'townShopSellInterval': 4,
                          'townCenterSellInterval': 24, 'irrelevant_flag': True})
        self.assertEqual(out['market'], [['SELL', 'WOOL', 2]])

    def test_changed_center_consumption_invalidates(self):
        tr, _ = fixture()
        self.assert_retired(tr, self.apply(tr, cfg={'townCenterSellInterval': 1000}))

    def test_changed_shop_interval_when_relevant_invalidates(self):
        tr, _ = fixture(shops=['YARN_STORE'])
        self.assert_retired(tr, self.apply(tr, observation(shops=['YARN_STORE']),
                                         {'townShopSellInterval': 5}))

    def test_unused_shop_interval_is_equivalent(self):
        tr, _ = fixture()
        out = self.apply(tr, cfg={'townShopSellInterval': 9})
        self.assertEqual(out['market'], [['SELL', 'WOOL', 2]])

    def test_shop_order_is_equivalent(self):
        tr, _ = fixture(shops=['YARN_STORE', 'PET_CAFE'])
        self.apply(tr, observation(shops=['PET_CAFE', 'YARN_STORE']))
        self.assertIsNotNone(tr.selector.active)
        self.assertEqual(tr.counts['branches'], 1)

    def test_duplicate_relevant_shop_changes_consumption(self):
        tr, _ = fixture(shops=['YARN_STORE'])
        self.assert_retired(tr, self.apply(tr, observation(shops=['YARN_STORE', 'YARN_STORE'])))

    def test_missing_observed_town_is_unknown(self):
        tr, _ = fixture()
        obs = observation(); del obs['town']
        self.assert_retired(tr, self.apply(tr, obs), 'market_context_unknown')

    def test_missing_relevant_parameter_is_unknown(self):
        tr, _ = fixture()
        p = copy.deepcopy(CORE.m.MARKET_PARAMS); del p['WOOL']['T']
        self.assert_retired(tr, self.apply(tr, observation(params=p)), 'market_context_unknown')

    def test_missing_table_context_is_unknown(self):
        tr, _ = fixture(); del tr.tree['economic_context']
        self.assert_retired(tr, self.apply(tr), 'market_context_unknown')

    def test_malformed_table_context_is_unknown(self):
        for mutate in (lambda c: c.update(version=2), lambda c: c.update(item='EGG'),
                       lambda c: c.update(end=80), lambda c: c['absorption'].pop()):
            with self.subTest(mutate=mutate.__code__.co_firstlineno):
                tr, _ = fixture(); mutate(tr.tree['economic_context'])
                self.assert_retired(tr, self.apply(tr), 'market_context_unknown')

    def test_bad_interval_is_unknown_without_exception(self):
        tr, _ = fixture()
        self.assert_retired(tr, self.apply(tr, cfg={'townShopSellInterval': 0}),
                            'market_context_unknown')

    def test_same_step_retry_cannot_resurrect_retired_context(self):
        tr, offer = fixture()
        self.assert_retired(tr, self.apply(tr, observation(shops=['YARN_STORE'])))
        self.assertEqual(self.apply(tr), fallback())
        self.assertIsNone(tr.selector.active)
        self.assertEqual(tr.counts['aborts'], 1)
        self.assertEqual(tr.selector.draws, 0)

    def test_after_branch_context_change_retires_fixed_suffix(self):
        tr, _ = fixture(mode='fixed')
        self.apply(tr)
        self.assertTrue(tr.branch_done)
        p = copy.deepcopy(CORE.m.MARKET_PARAMS); p['WOOL']['base'] += 1
        self.assert_retired(tr, self.apply(tr, observation(73, params=p)))

    def test_past_consumption_change_does_not_invalidate_remaining_suffix(self):
        tr, _ = fixture(mode='fixed')
        self.apply(tr)
        out = self.apply(tr, observation(73), {'townCenterSellInterval': 1000})
        self.assertEqual(out['market'], [['SELL', 'WOOL', 2]])
        self.assertIsNotNone(tr.selector.active)

    def test_context_applies_to_all_three_modes(self):
        for mode in ('adaptive', 'static', 'fixed'):
            with self.subTest(mode=mode):
                tr, _ = fixture(mode=mode)
                self.assert_retired(tr, self.apply(tr, observation(shops=['YARN_STORE'])))

    def test_offer_context_must_match_current_economics(self):
        tr, offer = fixture(active=False)
        out = tr.transform(observation(71, ['YARN_STORE']), {}, fallback(),
                           ledger=Ledger(71), offers=[offer])
        self.assertEqual(out, fallback())
        self.assertIsNone(tr.selector.active)
        self.assertEqual(tr.last['reason'], 'market_context_changed')

    def test_legacy_offer_requires_source_context(self):
        tr, offer = fixture(active=False); del offer['tree']['economic_context']
        out = tr.transform(observation(71), {}, fallback(), ledger=Ledger(71), offers=[offer])
        self.assertEqual(out, fallback())
        self.assertIsNone(tr.selector.active)
        self.assertEqual(tr.last['reason'], 'market_context_unknown')

    def test_old_offer_cannot_be_newly_admitted_at_later_step(self):
        tr, offer = fixture(active=False)
        tr.transform(observation(72), {}, fallback(), ledger=Ledger(72), offers=[offer])
        self.assertIsNone(tr.selector.active)
        self.assertEqual(tr.last['reason'], 'market_context_unknown')

    def test_admission_detaches_snapshot_from_input_mutations(self):
        tr, offer = fixture()
        offer['tree']['economic_context']['price']['base'] = 900
        offer['tree']['economic_context']['absorption'][:] = [999] * 8
        self.assertEqual(self.apply(tr)['market'], [['SELL', 'WOOL', 2]])

    def test_unknown_inventory_keeps_existing_fallback_semantics(self):
        tr, _ = fixture()
        obs = observation(); obs['market']['inventory']['WOOL'] = 8888
        self.assert_retired(tr, self.apply(tr, obs), 'unmodelled_public_inventory')

    def test_actual_agent_act_attaches_compiled_offer_context(self):
        # Exercise the production Agent.act body on a declared one-call parent
        # fixture. This is not an instantiated IntegratedSelectedAgent.
        parent_calls, observed_offers = [], []
        agent = object.__new__(G['Agent'])
        agent.calls = 0; agent.records = []; agent.last = {}
        agent.counts = {'tables': 0, 'positive_trees': 0}
        agent.observe = lambda obs, cfg: None
        # History is a separate consumer; this fixture checks offer binding only.
        agent._remember_action = lambda obs, cfg, action, packet: None
        agent.streams = lambda kw, slot: [('model', ((72, 2),), 'after')]
        agent.parent = types.SimpleNamespace(last_packet={
            'projection': {'observed_step': 71},
            'post_unit_observation': {'private': {'shed': {'WOOL': 2}}},
            'arrival_contract': {}})
        _, offer = fixture(active=False)
        def parent(obs, cfg):
            parent_calls.append(1)
            agent.records = [({'item': 'WOOL', 'inventory': 10000, 'params': None,
                               'shops': [], 'now': 71, 'dates': [71, 79], 'quantity': 2},
                              offer['tree']['plans'])]
            return fallback()
        agent._parent_action = parent
        class Consumer:
            expire = G['AdaptiveTransform'].expire
            selector = types.SimpleNamespace(active=None)
            last = {}
            counts = {'projection_fallbacks': 0, 'admissions': 0}
            def transform(self, obs, cfg, base, *, ledger, offers):
                observed_offers.extend(copy.deepcopy(list(offers))); return base
            def abort(self, base, reason):
                raise AssertionError(reason)
        agent.transformer = Consumer()
        old = getattr(G['sale'], 'ProjectionLedger', None)
        G['sale'].ProjectionLedger = lambda *args: Ledger(71)
        try:
            out = agent.act(observation(71), {})
        finally:
            if old is None: del G['sale'].ProjectionLedger
            else: G['sale'].ProjectionLedger = old
        self.assertEqual(parent_calls, [1])
        self.assertEqual(out, fallback())
        self.assertEqual(len(observed_offers), 1)
        self.assertEqual(observed_offers[0]['tree'].get('economic_context'), context())


class Attr(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


def engine_plan(seat, shops, sale_date):
    e = ENGINE
    farms = [e['_new_farm'](10, 0) for _ in range(2)]
    private = [e['_new_private']() for _ in range(2)]
    for p in private: p['shed']['WOOL'] = 2
    market = e['_new_market']()
    town = {'unlocked_shops': list(shops)}
    state = [Attr(observation=Attr(farms=farms, market=market, town=town,
                    private=private[i], step=72, day=3, hour=0, player=i),
                  action={}, status='ACTIVE', reward=0) for i in range(2)]
    env = Attr(configuration=Attr(episodeSteps=720), done=False, info={})
    trace = []
    for step in range(72, 80):
        for s in state: s.observation.step = step
        own = [['SELL', 'WOOL', 2]] if step == sale_date else []
        rival = [[], ['SELL', 'WOOL', 2]] if step == 72 else []
        state[seat].action = {'farmer': ['PASS'], 'hands': [], 'market': own}
        state[1-seat].action = {'farmer': ['PASS'], 'hands': [], 'market': rival}
        e['interpreter'](state, env)
        trace.append({'step': step, 'own_action': copy.deepcopy(state[seat].action),
                      'rival_action': copy.deepcopy(state[1-seat].action),
                      'own_cash': farms[seat]['money'], 'rival_cash': farms[1-seat]['money'],
                      'inventory_after': market['inventory']['WOOL']})
    return (farms[seat]['money'] - farms[1-seat]['money'],
            farms[seat]['money'], farms[1-seat]['money'], 0), trace


class EngineTests(unittest.TestCase):
    def test_exact_official_action_transitions_old_and_changed_context(self):
        if ENGINE is None:
            self.skipTest('Supply --engine for official action transitions')
        for seat in (0, 1):
            for shops in ([], ['YARN_STORE']):
                for date in (72, 73):
                    with self.subTest(seat=seat, shops=shops, sale_date=date):
                        actual, trace = engine_plan(seat, shops, date)
                        model = CORE.MarketPath('WOOL', 10000, None, shops, {}, 72, 79)
                        expected = model.score(((date, 2),), 2, ((72, 2),), 'after', True)
                        self.assertEqual(actual, expected)
                        EVIDENCE.append({'kind': 'official_interpreter', 'seat': seat,
                                         'shops': shops, 'sale_date': date, 'result': actual,
                                         'transitions': trace})


def main():
    global ARGS
    root = Path(__file__).resolve().parents[5] if len(Path(__file__).resolve().parents) > 5 else Path('.')
    kg = root/'revenue/kaggriculture'
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--runtime', type=Path, default=kg/'cloud-market-game-theory/adaptive/runtime.py')
    ap.add_argument('--core', type=Path, default=kg/'cloud-execution-lab/selected_sell_core.py')
    ap.add_argument('--recourse', type=Path, default=kg/'cloud-market-game-theory/adaptive/recourse.py')
    ap.add_argument('--selector', type=Path, default=kg/'cloud-market-game-theory/selector.py')
    ap.add_argument('--continuation', type=Path, default=kg/'cloud-plan-continuation/continuation.py')
    ap.add_argument('--engine', type=Path)
    ap.add_argument('--report', type=Path)
    ARGS = ap.parse_args()
    load_sources(ARGS)
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(ContextTests),
                               unittest.defaultTestLoader.loadTestsFromTestCase(EngineTests)])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'schema': 1, 'tests': result.testsRun,
              'failures': [{'test': str(t), 'traceback': text} for t, text in result.failures],
              'errors': [{'test': str(t), 'traceback': text} for t, text in result.errors],
              'skipped': [{'test': str(t), 'reason': reason} for t, reason in result.skipped],
              'sources': {k: file_meta(getattr(ARGS, k)) for k in
                          ('runtime', 'core', 'recourse', 'selector', 'continuation', 'engine')
                          if getattr(ARGS, k)},
              'scope': 'actual source class/consumer with explicit ledger/parent fixtures; '
                       'official constructed action transitions when engine supplied; zero full games',
              'evidence': EVIDENCE}
    if ARGS.report:
        ARGS.report.parent.mkdir(parents=True, exist_ok=True)
        ARGS.report.write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
