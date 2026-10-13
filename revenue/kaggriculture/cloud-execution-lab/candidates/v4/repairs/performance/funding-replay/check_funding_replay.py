# SPDX-License-Identifier: Apache-2.0
"""Pinned predecessor/candidate funding equivalence and official-engine checks.

Run with an extracted b567 package. This gate never downloads, patches or runs
an archive builder, and uses the literal unmodified official interpreter.
"""
from __future__ import annotations
import argparse
import ast
import copy
import hashlib
import gc
import weakref
import importlib.util
import itertools
import json
import random
import statistics
import sys
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch
import apply_funding_replay as composer

HERE = Path(__file__).resolve().parent
METRICS = {}
OLD = NEW = ENGINE = LOADER = ROOT = SOURCE = COMPOSED = None


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_inputs(root):
    pins = json.loads((HERE / 'INPUTS.json').read_text())
    source = root / 'SOURCE.json'
    if not source.is_file() or digest(source) != pins['source_json_sha256']:
        raise ValueError('missing or changed SOURCE.json')
    manifest = json.loads(source.read_text())['runtime']
    if len(manifest) != pins['expected_runtime_files']:
        raise ValueError('unexpected runtime manifest cardinality')
    for name, pin in manifest.items():
        path = root / name
        if not path.is_file() or path.stat().st_size != pin['bytes'] or digest(path) != pin['sha256']:
            raise ValueError('missing or changed pinned runtime input: ' + name)
    return pins


def module_from_source(name, text):
    mod = types.ModuleType(name)
    mod.__file__ = str(ROOT / 'frozen_selected.py')
    exec(compile(text, mod.__file__, 'exec'), mod.__dict__)
    return mod


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def initialize(root):
    global OLD, NEW, ENGINE, LOADER, ROOT, SOURCE, COMPOSED
    ROOT = root.resolve()
    pins = verify_inputs(ROOT)
    sys.path.insert(0, str(ROOT))
    SOURCE = (ROOT / 'frozen_selected.py').read_text()
    COMPOSED = composer.apply(SOURCE)
    if hashlib.sha256(COMPOSED.encode()).hexdigest() != pins['composed_sha256']:
        raise ValueError('unexpected composed module')
    OLD = module_from_source('funding_predecessor', SOURCE)
    NEW = module_from_source('funding_candidate', COMPOSED)
    LOADER = load_file('funding_official_loader', ROOT / 'checks/reference/evaluator/loader.py')
    ENGINE, hashes = LOADER.get_engine(ROOT / 'checks/reference/engine')
    METRICS['pinned_runtime_files'] = pins['expected_runtime_files']
    METRICS['official_engine_sha256'] = hashes
    METRICS['composed_sha256'] = pins['composed_sha256']


def fixture(now=5, seat=0, stock=10, cash=0, inventory=10000, cap=10):
    cfg = {'shedCapacity': 100, 'farmHandCostMult': 1,
           'maxMarketOrdersPerTurn': cap, 'turnsPerDay': 24, 'episodeSteps': 720}
    farms = [ENGINE._new_farm(10, cash), ENGINE._new_farm(10, cash)]
    market = ENGINE._new_market()
    market['params'] = copy.deepcopy(OLD.m.MARKET_PARAMS)
    for item in market['inventory']:
        market['inventory'][item] = inventory
    ENGINE._refresh_prices(market)
    private = ENGINE._new_private()
    for item in private['shed']:
        private['shed'][item] = 0
    private['shed']['MILK'] = stock
    obs = {'step': now, 'player': seat, 'day': now // 24, 'hour': now % 24,
           'farms': farms, 'private': private, 'market': market,
           'town': {'unlocked_shops': []}}
    route = [{'farmer': ['PASS'], 'hands': [], 'market': []} for _ in range(720)]
    return obs, cfg, farms[seat], private, route


def same_args(orders, f):
    obs, cfg, farm, private, route = f
    return (orders, farm, private, obs['market'], [], cfg, obs['step'],
            {'MILK', 'WOOL', 'EGG', 'CARROT'}, {'MILK': 16, 'WOOL': 4})


def minimum_args(orders, f, end=None, stress=32):
    obs, cfg, farm, private, route = f
    current = OLD.sale_quantities(orders)
    targets = {i for i, q in private['shed'].items() if q > 0 and i in OLD.PRODUCTS}
    return (obs, cfg, {'market': orders}, farm, private, route,
            obs['step'] if end is None else end, current, targets, 'MILK', stress)


def outcome(func, args):
    try:
        return 'return', func(*args)
    except Exception as exc:
        return 'exception', type(exc).__name__, str(exc)


def consumer(mod, route):
    bot = mod.FrozenSelected.__new__(mod.FrozenSelected)
    bot.controller = types.SimpleNamespace(R={'test': route}, cur='test')
    bot.mode = 'candidate'
    bot.pending = {}; bot.planned = {}; bot.previous = None
    bot.observed_harvests = {}; bot.diagnostics = {}
    return bot


def official_transition(f, own, rival, seat):
    obs, cfg, _, private, _ = copy.deepcopy(f)
    S = LOADER.Struct
    ecfg = S({k: v.get('default') if isinstance(v, dict) else v
              for k, v in ENGINE.specification['configuration'].items()})
    ecfg.update(cfg); ecfg.weedSpawnChance = 0
    farms = obs['farms']; market = obs['market']; state = []
    for p in (0, 1):
        priv = private if p == seat else ENGINE._new_private()
        if p != seat:
            priv['shed']['MILK'] = 60; priv['shed']['WOOL'] = 20
        state.append(S(observation=S(player=p, step=obs['step'], day=obs['step']//24,
                                    hour=obs['step']%24, farms=farms, private=priv,
                                    market=market, town=obs['town']),
                       action={'farmer': ['PASS'], 'hands': [],
                               'market': copy.deepcopy(own if p == seat else rival)},
                       status='ACTIVE', reward=0))
    env = S(configuration=ecfg, done=False, info={'seed': 20260911})
    ENGINE.interpreter(state, env)
    return state, env


class FundingReplayChecks(unittest.TestCase):
    def test_01_exact_composition_idempotence(self):
        self.assertNotEqual(SOURCE, COMPOSED)
        self.assertEqual(composer.apply(COMPOSED), COMPOSED)
        self.assertEqual(OLD._funding_trace.__code__.co_code, NEW._funding_trace.__code__.co_code)
        self.assertEqual(OLD.FrozenSelected.transform.__code__.co_code,
                         NEW.FrozenSelected.transform.__code__.co_code)

    def test_02_peer_edits_outside_four_methods_survive(self):
        for n in range(64):
            prefix = '# unrelated peer %d\n' % n
            suffix = '\nPEER_%d = %d\n' % (n, n)
            result = composer.apply(prefix + SOURCE + suffix)
            self.assertEqual(result, prefix + COMPOSED + suffix)
            self.assertEqual(composer.apply(result), result)
        METRICS['peer_composition_cases'] = 64

    def test_03_changed_mixed_missing_duplicate_spans_fail_closed(self):
        before_spans = composer._spans(SOURCE)
        after_spans = composer._spans(COMPOSED)
        cases = []
        for name in composer.BEFORE:
            a, b = before_spans[name]; c, d = after_spans[name]
            cases.extend([SOURCE[:a] + SOURCE[a:b].replace('def ', 'def changed_', 1) + SOURCE[b:],
                          SOURCE[:a] + SOURCE[a:b].replace('\n', '\n    # drift\n', 1) + SOURCE[b:],
                          SOURCE[:a] + COMPOSED[c:d] + SOURCE[b:],
                          SOURCE + '\n' + SOURCE[a:b]])
        for text in cases:
            with self.assertRaises((ValueError, SyntaxError)):
                composer.apply(text)
        METRICS['source_drift_rejections'] = len(cases)

    def test_04_all_receipt_shapes_exact_with_shared_models(self):
        f = fixture(); market = f[0]['market']; pool = {}; count = 0
        for item, inv, quantity, rival in itertools.product(
                OLD.m.PRODUCTS, (9900, 10000, 10030, 10075, 10076, 10400),
                (0, 1, 2, 9, 32, 100), (0, 1, 16, 64)):
            args = (item, quantity, inv, market, [], f[1], 5, rival)
            self.assertEqual(OLD._stressed_sale_receipt(*args),
                             NEW._stressed_sale_receipt(*args, _models=pool))
            count += 1
        METRICS['receipt_comparisons'] = count

    def test_05_parameter_changes_and_return_to_old_values_invalidate(self):
        f = fixture(); market = f[0]['market']; pool = {}
        for base, inv in itertools.product((160, 80, 320, 160), (10000, 10075)):
            market['params']['MILK']['base'] = base
            args = ('MILK', 20, inv, market, [], f[1], 5, 16)
            self.assertEqual(OLD._stressed_sale_receipt(*args),
                             NEW._stressed_sale_receipt(*args, _models=pool))
        self.assertEqual(len(pool), 1)

    def test_06_custom_mapping_falls_back_without_snapshotting(self):
        class CountingDict(dict):
            calls = 0
            def __getitem__(self, key):
                self.calls += 1
                return super().__getitem__(key)
        for mod in (OLD, NEW):
            f = fixture(); market = f[0]['market']
            table = CountingDict(market['params']); market['params'] = table
            args = ('MILK', 4, 10000, market, [], f[1], 5, 2)
            pool = {}
            if mod is NEW:
                result = mod._stressed_sale_receipt(*args, _models=pool)
            else:
                result = mod._stressed_sale_receipt(*args)
                reference = result; calls = table.calls
            self.assertEqual(result, reference)
            self.assertEqual(table.calls, calls)
            self.assertFalse(pool)

    def test_07_complete_same_turn_outputs_and_input_identity(self):
        rng = random.Random(9101107); engaged = 0
        for n in range(1000):
            f = fixture(now=rng.choice((5, 23, 24, 718)), seat=n%2,
                        stock=rng.choice((0, 1, 3, 12, 40)),
                        cash=rng.choice((0, 10, 80, 299, 500)),
                        inventory=rng.choice((9950, 10000, 10040, 10075, 10500)),
                        cap=rng.choice((-2, 0, 1, 2, 10)))
            f[3]['shed']['WOOL'] = rng.randrange(8)
            f[2]['hires_today'] = rng.randrange(4)
            f[1]['shedCapacity'] = rng.choice((1, 10, 100))
            choices = [[], ['HIRE'], ['BUY_LAND'], ['BUY_SEED','CARROT',rng.randrange(5)],
                       ['BUY_ANIMAL','GOOSE',rng.randrange(3)], ['BUY_PRODUCT','WHEAT',2],
                       ['SELL','MILK',rng.randrange(1,41)], ['SELL','WOOL',rng.randrange(1,8)]]
            orders = copy.deepcopy([rng.choice(choices) for _ in range(rng.randrange(2,9))])
            if n%3 == 0:
                orders = [[], ['BUY_SEED','CARROT',3], ['SELL','MILK',20]]
            args = same_args(orders, f); snapshot = copy.deepcopy(args)
            expected = outcome(OLD.fund_same_turn_acquisition, args)
            actual = outcome(NEW.fund_same_turn_acquisition, args)
            self.assertEqual(actual, expected, (n, orders))
            self.assertEqual(args, snapshot)
            if actual[0] == 'return' and actual[1][1] and actual[1][1].get('applied'):
                engaged += 1
        self.assertGreater(engaged, 20)
        METRICS['same_turn_comparisons'] = 1000
        METRICS['same_turn_engaged'] = engaged

    def test_08_rival_callback_counts_and_price_mutation_match(self):
        outputs = []
        for mod in (OLD, NEW):
            f = fixture(stock=60, inventory=10050)
            calls = []
            def rival(item):
                calls.append(item)
                f[0]['market']['params'][item]['base'] = (120, 160, 80)[len(calls)%3]
                return len(calls)%7
            args = list(same_args([[], ['BUY_ANIMAL','COW',3], ['SELL','MILK',60]], f))
            args[-1] = rival
            outputs.append((outcome(mod.fund_same_turn_acquisition, args), calls))
        self.assertEqual(outputs[0], outputs[1])
        self.assertGreater(len(outputs[0][1]), 1)

    def test_09_model_lifetime_is_search_local(self):
        counts = []
        for mod in (OLD, NEW):
            f = fixture(stock=100, inventory=10500)
            args = same_args([[], ['BUY_SEED','CARROT',4], ['SELL','MILK',100]], f)
            cls = mod.MarketPath
            with patch.object(mod, 'MarketPath', wraps=cls) as counted:
                first = mod.fund_same_turn_acquisition(*args)
                n = counted.call_count
                second = mod.fund_same_turn_acquisition(*args)
                self.assertEqual(counted.call_count, 2*n)
            self.assertEqual(first, second)
            counts.append(n)
        self.assertGreater(counts[0], 60)
        self.assertEqual(counts[1], 1)
        METRICS['market_model_constructions_per_search'] = {'before': counts[0], 'after': counts[1]}

    def test_10_funded_minimum_outputs_reports_and_inputs(self):
        rng = random.Random(9101110); nonzero = fallback = 0
        for n in range(900):
            now = rng.choice((0, 5, 21, 22, 23, 24, 714, 717, 718))
            end = min(718, now+rng.randrange(5))
            f = fixture(now=now, seat=n%2, stock=rng.choice((0,1,3,6,12)),
                        cash=rng.choice((0,10,100,399,1000)),
                        inventory=rng.choice((9950,10000,10050,10075,10500)),
                        cap=rng.choice((-2,0,1,2,10)))
            f[1]['shedCapacity'] = rng.choice((1,10,100))
            f[3]['shed']['WOOL'] = rng.randrange(3)
            q = rng.randrange(13)
            buys = [[], ['HIRE'], ['BUY_LAND'], ['BUY_SEED','STRAWBERRY',2],
                    ['BUY_ANIMAL','COW',2], ['BUY_PRODUCT','FERTILIZER',3]]
            orders = [['SELL','MILK',q], copy.deepcopy(rng.choice(buys))]
            if n%3 == 0: orders.reverse()
            for t in range(now+1,end+1):
                f[4][t]['market'] = [copy.deepcopy(rng.choice(buys))]
                if rng.randrange(3) == 0:
                    f[4][t]['market'].insert(0,['SELL','WOOL',2])
                f[4][t]['farmer'] = rng.choice([['PASS'],['WEST'],['DROP'],['PICKUP','MILK',2]])
            args = minimum_args(orders, f, end, rng.choice((0,1,32,100)))
            snapshot = copy.deepcopy(args)
            expected = outcome(OLD.funded_minimum_now, args)
            actual = outcome(NEW.funded_minimum_now, args)
            self.assertEqual(actual, expected, n)
            self.assertEqual(args, snapshot)
            if actual[0] == 'return':
                nonzero += actual[1][0] > 0
                fallback += bool(actual[1][1]['fallback'])
        self.assertGreater(nonzero, 20)
        METRICS['funded_minimum_comparisons'] = 900
        METRICS['funded_minimum_nonzero'] = nonzero
        METRICS['funded_minimum_fallback'] = fallback

    def test_11_no_product_buy_reduces_replays_keeps_two_certificates(self):
        results = []; counts = []
        for mod in (OLD, NEW):
            f = fixture(stock=10)
            args = minimum_args([['SELL','MILK',10],['BUY_ANIMAL','COW',1]],f)
            with patch.object(mod,'_funding_trace',wraps=mod._funding_trace) as calls:
                results.append(mod.funded_minimum_now(*args)); counts.append(calls.call_count)
        self.assertEqual(results[0],results[1])
        self.assertEqual(counts,[9,5])
        self.assertEqual(len(results[1][1]['scenario_terminal_cash']),2)
        METRICS['fixed_buy_trace_calls'] = {'before':counts[0],'after':counts[1]}

    def test_12_live_buy_product_stress_never_elided(self):
        counts=[]; results=[]
        for mod in (OLD,NEW):
            f=fixture(stock=10)
            args=minimum_args([['SELL','MILK',10],['BUY_PRODUCT','FERTILIZER',3]],f)
            with patch.object(mod,'_funding_trace',wraps=mod._funding_trace) as calls:
                results.append(mod.funded_minimum_now(*args));counts.append(calls.call_count)
        self.assertEqual(results[0],results[1]);self.assertEqual(counts[0],counts[1])
        self.assertNotEqual(*results[1][1]['scenario_terminal_cash'])
        METRICS['live_product_buy_trace_calls']={'before':counts[0],'after':counts[1]}

    def test_13_raw_cap_empty_slots_and_future_prefix_cuts(self):
        cases=0
        for cap, future, cut, stress in itertools.product((0,1,2,3,10,-1), (False,True), (False,True), (0,32)):
            f=fixture(stock=10,cap=cap)
            orders=[['SELL','MILK',10],['BUY_ANIMAL','COW',1],[],['BUY_PRODUCT','FERTILIZER',2]]
            if future:
                orders[-1]=[]
                f[4][7]['market']=[['BUY_PRODUCT','FERTILIZER',2]]
            if cut:
                f[3]['shed']['WOOL']=1
                f[4][6]['market']=[['SELL','WOOL',1]]
            args=minimum_args(orders,f,8,stress)
            self.assertEqual(outcome(OLD.funded_minimum_now,args),outcome(NEW.funded_minimum_now,args))
            cases+=1
        METRICS['raw_prefix_stress_controls']=cases

    def test_14_malformed_inputs_preserve_exception_or_fallback(self):
        cases=0
        for row in (None, ['BUY_PRODUCT'], ['BUY_PRODUCT','FERTILIZER','bad'],
                    ['SELL','MILK','bad'], ['SELL',None,1], ['BUY_SEED','CARROT',None],
                    ['SELL','MILK',-2], ['HIRE'], [], ['BUY_ANIMAL','GOOSE',-2]):
            for cap in (0,1,2,10):
                f=fixture(stock=10,cap=cap)
                for orders in ([[],row,['SELL','MILK',10]], [row,['BUY_ANIMAL','COW',1]]):
                    args=same_args(copy.deepcopy(orders),f)
                    self.assertEqual(outcome(OLD.fund_same_turn_acquisition,args),outcome(NEW.fund_same_turn_acquisition,args))
                    # Deliberately do not derive current from malformed SELL rows.
                    args=(f[0],f[1],{'market':copy.deepcopy(orders)},f[2],f[3],f[4],5,
                          {'MILK':10},{'MILK'},'MILK',32)
                    self.assertEqual(outcome(OLD.funded_minimum_now,args),outcome(NEW.funded_minimum_now,args))
                    cases+=2
        METRICS['malformed_comparisons']=cases

    def test_15_exact_full_interpreter_both_seats(self):
        pairs=engaged=0
        for seat, step, inv, cash, rival in itertools.product(
                (0,1),(5,23,718),(10000,10075),(0,50),
                ([],[['SELL','MILK',10]],[['BUY_PRODUCT','MILK',3]])):
            f=fixture(now=step,seat=seat,stock=40,cash=cash,inventory=inv)
            f[3]['inventories'][0]={'WOOL':3}
            orders=[[],['BUY_SEED','CARROT',3],['SELL','MILK',40]]
            args=same_args(orders,f)
            old,info=OLD.fund_same_turn_acquisition(*args)
            new,newinfo=NEW.fund_same_turn_acquisition(*args)
            self.assertEqual((old,info),(new,newinfo))
            self.assertEqual(official_transition(f,old,rival,seat),official_transition(f,new,rival,seat))
            pairs+=1;engaged+=bool(info and info.get('applied'))
        self.assertGreater(engaged,0)
        METRICS['full_official_interpreter_pairs']=pairs
        METRICS['full_official_interpreter_calls']=2*pairs
        METRICS['engine_pairs_with_funding_reorder']=engaged

    def test_16_real_frozen_transform_and_history_are_identical(self):
        count=0
        for seat, now, money, inv in itertools.product((0,1),(5,22,100,710),(0,500),(10000,10075)):
            f=fixture(now=now,seat=seat,stock=3,cash=money,inventory=inv)
            f[3]['shed']['WOOL']=2
            f[4][now]['market']=[[],['BUY_SEED','CARROT',2],['SELL','MILK',3]]
            if now<718:f[4][now+1]['market']=[['BUY_PRODUCT','FERTILIZER',1]]
            bots=[consumer(mod,copy.deepcopy(f[4])) for mod in (OLD,NEW)]
            snapshots=[]
            for bot in bots:
                args=copy.deepcopy((f[0],f[1],f[4][now]))
                before=copy.deepcopy(args)
                result=bot.transform(*args)
                self.assertEqual(args,before)
                snapshots.append((result,bot.planned,bot.pending,bot.previous,bot.diagnostics,bot.observed_harvests))
            self.assertEqual(snapshots[0],snapshots[1])
            count+=1
        METRICS['unmocked_frozen_transform_pairs']=count

    def test_17_inherited_funded_prefix_tests(self):
        inherited=load_file('funding_inherited_tests',ROOT/'checks/test_funded_prefix.py')
        inherited.fs=NEW
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(inherited.FundedPrefixTests)
        result=unittest.TestResult();suite.run(result)
        self.assertTrue(result.wasSuccessful(), str(result.failures)+str(result.errors))
        self.assertEqual(result.testsRun,8)
        METRICS['inherited_tests']=result.testsRun

    def test_18_unsound_stress_skip_mutant_is_rejected(self):
        bad=COMPOSED.replace('if has_draw else nominal)', 'if False else nominal)',1)
        mutant=module_from_source('bad_stress_skip',bad)
        f=fixture(stock=10)
        args=minimum_args([['SELL','MILK',10],['BUY_PRODUCT','FERTILIZER',3]],f)
        self.assertNotEqual(OLD.funded_minimum_now(*args),mutant.funded_minimum_now(*args))

    def test_19_unsound_stale_parameter_cache_mutant_is_rejected(self):
        bad=COMPOSED.replace('cached[0]==signature:', 'True:',1)
        mutant=module_from_source('bad_stale_params',bad)
        f=fixture();market=f[0]['market'];pool={}
        args=('MILK',20,10000,market,[],f[1],5,16)
        mutant._stressed_sale_receipt(*args,_models=pool)
        market['params']['MILK']['base']*=2
        self.assertNotEqual(OLD._stressed_sale_receipt(*args),mutant._stressed_sale_receipt(*args,_models=pool))

    def test_20_wrong_single_certificate_mutant_is_rejected(self):
        bad=COMPOSED.replace('traces = [nominal, stressed]', 'traces = [nominal]',1)
        mutant=module_from_source('bad_single_certificate',bad)
        f=fixture(stock=10)
        args=minimum_args([['SELL','MILK',10],['BUY_ANIMAL','COW',1]],f)
        self.assertNotEqual(OLD.funded_minimum_now(*args),mutant.funded_minimum_now(*args))

    def test_21_default_parameter_table_versions_are_checked(self):
        f=fixture();f[0]['market'].pop('params');pool={}
        original=OLD.m.MARKET_PARAMS['MILK']['base']
        try:
            for value in (160,80,320,160):
                OLD.m.MARKET_PARAMS['MILK']['base']=value
                args=('MILK',10,10000,f[0]['market'],[],f[1],5,16)
                self.assertEqual(OLD._stressed_sale_receipt(*args),
                                 NEW._stressed_sale_receipt(*args,_models=pool))
        finally:
            OLD.m.MARKET_PARAMS['MILK']['base']=original
            for _signature,model in pool.values():NEW._dispose_funding_model(model)

    def test_22_private_owner_models_are_released_without_cyclic_gc(self):
        retained=[]
        for mod in (OLD,NEW):
            count,created=retention_probe(mod,'search')
            retained.append(count)
            self.assertGreater(created,0)
        self.assertGreater(retained[0],0)
        self.assertEqual(retained[1],0)
        METRICS['gc_paused_retained_search_models']={'before':retained[0],'after':retained[1]}

    def test_23_standalone_quote_and_callback_exception_owners_release(self):
        for mode in ('standalone','quote_exception','callback_exception'):
            retained,created=retention_probe(NEW,mode)
            self.assertGreater(created,0)
            self.assertEqual(retained,0,mode)
        METRICS['zero_retention_paths']=['search','standalone','quote_exception','callback_exception']

    def test_24_borrowed_pool_model_survives_until_owner_release(self):
        f=fixture();pool={}
        args=('MILK',10,10000,f[0]['market'],[],f[1],5,16)
        first=NEW._stressed_sale_receipt(*args,_models=pool)
        model=pool['MILK'][1]
        self.assertTrue(hasattr(model,'joint'))
        self.assertEqual(NEW._stressed_sale_receipt(*args,_models=pool),first)
        self.assertIs(pool['MILK'][1],model)
        self.assertGreater(model.joint.cache_info().hits,0)
        NEW._dispose_funding_model(model)
        self.assertNotIn('single',model.__dict__)
        self.assertNotIn('joint',model.__dict__)

    def test_25_clear_only_lifetime_mutant_is_rejected(self):
        bad=COMPOSED.replace('    del model.single, model.joint','    pass # unsound clear-only mutation',1)
        mutant=module_from_source('bad_clear_only',bad)
        retained,created=retention_probe(mutant,'search')
        self.assertGreater(created,0);self.assertGreater(retained,0)

    def test_26_premature_borrowed_model_disposal_is_rejected(self):
        bad=COMPOSED.replace('        if owned:', '        if True:',1)
        mutant=module_from_source('bad_premature_disposal',bad)
        f=fixture(stock=40,inventory=10050)
        args=same_args([[],['BUY_SEED','STRAWBERRY',5],['SELL','MILK',40]],f)
        self.assertNotEqual(outcome(OLD.fund_same_turn_acquisition,args),
                            outcome(mutant.fund_same_turn_acquisition,args))
        METRICS['behavioral_mutants_rejected']=5

    def test_27_composed_disposal_helper_is_required_and_exact(self):
        for text in (COMPOSED.replace(composer.ADDED,''),
                     COMPOSED.replace('    del model.single, model.joint','    pass',1),
                     SOURCE+'\n'+composer.ADDED):
            with self.assertRaises(ValueError):composer.apply(text)


def retention_probe(mod,mode):
    # No production GC changes. The weakrefs alone do not own the models.
    gc.collect();enabled=gc.isenabled();refs=[];cls=mod.MarketPath;cuts=0
    def factory(*args,**kwargs):
        instance=cls(*args,**kwargs);refs.append(weakref.ref(instance));return instance
    gc.disable()
    try:
        with patch.object(mod,'MarketPath',factory):
            for _ in range(8):
                f=fixture(stock=10)
                if mode=='search':
                    mod.fund_same_turn_acquisition(*same_args([[],['BUY_ANIMAL','COW',1],['SELL','MILK',10]],f))
                elif mode in ('standalone','quote_exception'):
                    if mode=='quote_exception':f[0]['market']['params']['MILK']['T']=0
                    try:mod._stressed_sale_receipt('MILK',3,10000,f[0]['market'],[],f[1],5,16)
                    except ZeroDivisionError:
                        if mode!='quote_exception':raise
                        cuts+=1
                else:
                    calls=[]
                    def rival(item):
                        calls.append(item)
                        if len(calls)>1:raise RuntimeError('callback cut')
                        return 16
                    args=list(same_args([[],['BUY_ANIMAL','COW',1],['SELL','MILK',10]],f));args[-1]=rival
                    try:mod.fund_same_turn_acquisition(*args)
                    except RuntimeError:cuts+=1
        if mode in ('quote_exception','callback_exception') and cuts!=8:
            raise AssertionError('expected all eight injected exception cuts')
        return sum(ref() is not None for ref in refs),len(refs)
    finally:
        if enabled:gc.enable()
        gc.collect()


def benchmark():
    scenarios=[]
    f=fixture(stock=100,inventory=10500)
    scenarios.append(('same_turn_floor_80_units', 'fund_same_turn_acquisition',
                      same_args([[],['BUY_SEED','CARROT',4],['SELL','MILK',100]],f)))
    f=fixture(stock=40,inventory=10050)
    f[3]['shed']['WOOL']=60;f[0]['market']['inventory']['WOOL']=10500
    scenarios.append(('repeated_sale_prefix', 'fund_same_turn_acquisition',
                      same_args([[],['SELL','MILK',40],['BUY_ANIMAL','COW',3],['SELL','WOOL',60]],f)))
    f=fixture(stock=10)
    scenarios.append(('fixed_buy_minimum','funded_minimum_now',
                      minimum_args([['SELL','MILK',10],['BUY_ANIMAL','COW',1]],f)))
    f=fixture(stock=10)
    scenarios.append(('live_product_buy_control','funded_minimum_now',
                      minimum_args([['SELL','MILK',10],['BUY_PRODUCT','FERTILIZER',3]],f)))
    rows=[]
    for name,fn,args in scenarios:
        a=getattr(OLD,fn);b=getattr(NEW,fn)
        reference=a(*args)
        if b(*args)!=reference:raise ValueError('benchmark equivalence failed: '+name)
        samples=[[],[]]
        for repetition in range(9):
            for index in ((0,1) if repetition%2==0 else (1,0)):
                call=(a,b)[index]
                start=time.perf_counter_ns()
                for _ in range(20):
                    value=call(*args)
                    if value!=reference:raise ValueError('benchmark output drift')
                samples[index].append((time.perf_counter_ns()-start)/20/1000)
        old,new=map(statistics.median,samples)
        rows.append({'case':name,'before_us':round(old,3),'after_us':round(new,3),
                     'speedup':round(old/new,3),'samples_per_arm':9,'calls_per_sample':20,
                     'ordering':'alternating AB/BA','min_us':[round(min(s),3) for s in samples],
                     'max_us':[round(max(s),3) for s in samples]})
    return rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--benchmark',action='store_true')
    args=parser.parse_args()
    initialize(args.runtime)
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(FundingReplayChecks)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    METRICS.update(success=result.wasSuccessful(),tests=result.testsRun,
                   failures=len(result.failures),errors=len(result.errors),optimized=not __debug__)
    if result.wasSuccessful() and args.benchmark:METRICS['microbenchmarks']=benchmark()
    text=json.dumps(METRICS,indent=2,sort_keys=True)+'\n'
    if args.output:args.output.write_text(text)
    print(text)
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':main()
