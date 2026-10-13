# SPDX-License-Identifier: Apache-2.0
"""Exact selected-SELL queue-copy parity, including custom metaclass values.

Runs the actual seller and a reference differing only at the two copy sites.
Constructed input cases and timings are not complete games or actor profiles.
"""
from __future__ import annotations
import argparse
import ast
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import random
import statistics
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / 'cloud-execution-lab'
SELLER = REFERENCE = None
COUNTS = {'queue_comparisons': 0, 'replacement_comparisons': 0,
          'complete_transform_comparisons': 0, 'feasibility_comparisons': 0}


def load_pair(lab):
    lab = Path(lab).resolve()
    sys.path.insert(0, str(lab))
    path = lab / 'selected_action_sell.py'
    raw = path.read_bytes()
    candidate_spec = importlib.util.spec_from_file_location('queue_candidate', path)
    candidate = importlib.util.module_from_spec(candidate_spec)
    sys.modules[candidate_spec.name] = candidate
    exec(compile(raw, str(path), 'exec'), candidate.__dict__)
    reference_source = raw.decode().replace('out = _copy_market_orders(orders)', 'out = copy.deepcopy(orders)', 1)
    reference_source = reference_source.replace(
        'market = (_copy_market_orders(self.future.get(t, [])) if item is None else',
        'market = (copy.deepcopy(self.future.get(t, [])) if item is None else', 1)
    if reference_source == raw.decode():
        raise ValueError('Expected the two published copy sites')
    spec = importlib.util.spec_from_file_location('queue_reference', path)
    reference = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = reference
    exec(compile(reference_source, str(path), 'exec'), reference.__dict__)
    return candidate, reference


def fixture(kind='multi', player=0, horizon=4):
    now = 714 if kind == 'terminal' else 200
    end = min(718, now + horizon)
    obs = {'step': now, 'player': player, 'day': now//24, 'hour': now%24,
           'farms': [{'money': 5000, 'tiles': [[None]], 'hires_today': 0,
                      'unlocked_quadrants': ['NW']} for _ in range(2)],
           'market': {'inventory': {p: 10020 for p in SELLER.m.PRODUCTS}},
           'town': {'unlocked_shops': ['BAKERY', 'YARN_STORE', 'FARMERS_MARKET']}}
    config = {'episodeSteps': 720, 'turnsPerDay': 24, 'shedCapacity': 100,
              'maxMarketOrdersPerTurn': 10}
    shed = {'EGG': 7, 'WOOL': 6, 'MILK': 5}
    market = [['SELL', 'EGG', 4], ['SELL', 'WOOL', 3], ['SELL', 'MILK', 3]]
    if kind == 'dense':
        market = [['SELL', 'EGG', 2], ['BUY_SEED', 'WHEAT', 1], [],
                  ['SELL', 'EGG', 2], ['SELL', 'WOOL', 2], ['SELL', 'MILK', 2], [], []]
    if kind == 'empty':
        shed = {'WHEAT': 5}
        market = [['BUY_SEED', 'WHEAT', 1], ['HIRE'], [], ['HIRE']]
    base = {'farmer': ['PASS'], 'hands': [], 'market': market}
    future = {t: [['SELL', p, q] for p, q in shed.items() if p in SELLER.PRODUCTS]
              for t in range(now + 1, end + 1)}
    projection = {'observed_step': now, 'end_step': end, 'stock_events': [], 'future_market': future}
    return (obs, config, base), {'post_unit_shed': shed, 'projection': projection,
                               'fallback_action': {'farmer': ['PASS'], 'hands': [], 'market': []}}


def invoke_pair(args, kwargs, capture=True):
    results = []
    for module in (REFERENCE, SELLER):
        seller = module.SelectedActionSell()
        records = []
        original = module.ProjectionLedger.feasible
        def observed(ledger, item, plan):
            result = original(ledger, item, plan)
            records.append((item, copy.deepcopy(plan), result))
            return result
        before = copy.deepcopy((args, kwargs))
        with patch.object(module.ProjectionLedger, 'feasible', observed if capture else original):
            out = seller.transform(*args, **kwargs)
        if (args, kwargs) != before:
            raise AssertionError('Caller input changed')
        results.append((out, seller.diagnostics, seller.previous,
                        seller.observed_harvests, records))
    return results


class CopyCases(unittest.TestCase):
    def same_queue(self, orders):
        expected = copy.deepcopy(orders)
        actual = SELLER._copy_market_orders(orders)
        self.assertEqual(actual, expected)
        self.assertIsNot(actual, orders)
        for i in range(len(orders)):
            if type(orders[i]) is list:
                self.assertIsNot(actual[i], orders[i])
            for j in range(len(orders)):
                self.assertEqual(actual[i] is actual[j], expected[i] is expected[j])
        COUNTS['queue_comparisons'] += 1
        return actual

    def test_empty_outer_queue(self):
        self.same_queue([])

    def test_all_flat_builtin_values(self):
        values = ['SELL', 'WOOL', 7, -3, 0.25, True, False, None, '']
        out = self.same_queue([values, [], ['PASS']])
        self.assertTrue(all(a is b for a,b in zip(values, out[0])))

    def test_repeated_order_alias_is_preserved(self):
        order = ['SELL', 'WOOL', 2]
        out = self.same_queue([order, [], order])
        self.assertIs(out[0], out[2])
        out[0][2] = 9
        self.assertEqual(out[2][2], 9)
        self.assertEqual(order[2], 2)

    def test_equal_distinct_orders_remain_distinct(self):
        out = self.same_queue([['PASS'], ['PASS']])
        self.assertIsNot(out[0], out[1])

    def test_outer_subclass_deepcopy(self):
        class Queue(list): pass
        out = self.same_queue(Queue([['PASS']]))
        self.assertIs(type(out), Queue)

    def test_order_subclass_deepcopy(self):
        class Order(list): pass
        out = self.same_queue([Order(['PASS'])])
        self.assertIs(type(out[0]), Order)

    def test_nested_shared_values_are_detached(self):
        nested = {'x': [1]}
        orders = [['PASS', nested], ['PASS', nested]]
        out = self.same_queue(orders)
        self.assertIs(out[0][1], out[1][1])
        self.assertIsNot(out[0][1], nested)
        out[0][1]['x'].append(2)
        self.assertEqual(nested, {'x': [1]})

    def test_recursive_queue_preserves_cycle(self):
        orders = []
        orders.append(orders)
        out = SELLER._copy_market_orders(orders)
        self.assertIs(out[0], out)
        self.assertIsNot(out, orders)

    def test_custom_deepcopy_hook_called_once(self):
        class Custom:
            calls = 0
            def __deepcopy__(self, memo):
                type(self).calls += 1
                return ['custom-copy']
        value = Custom()
        result = SELLER._copy_market_orders([['PASS', value], ['PASS', value]])
        self.assertEqual(Custom.calls, 1)
        self.assertIs(result[0][1], result[1][1])

    def test_atomic_subclass_not_reused(self):
        class Text(str): pass
        value = Text('note'); value.mutable = [1]
        out = SELLER._copy_market_orders([[value]])
        self.assertIsNot(out[0][0], value)
        self.assertIsNot(out[0][0].mutable, value.mutable)

    def test_metaclass_cannot_spoof_atomic_type(self):
        class PretendsAtomic(type):
            __hash__ = type.__hash__
            def __eq__(cls, other): return other is str
        class Mutable(metaclass=PretendsAtomic):
            def __init__(self): self.values = [1]
        value = Mutable()
        out = SELLER._copy_market_orders([['PASS', value]])
        self.assertIsNot(out[0][1], value)
        out[0][1].values.append(2)
        self.assertEqual(value.values, [1])

    def test_metaclass_equality_never_invoked(self):
        class Raises(type):
            __hash__ = type.__hash__
            def __eq__(cls, other): raise RuntimeError('metaclass equality')
        class Mutable(metaclass=Raises): pass
        value = Mutable()
        out = SELLER._copy_market_orders([[value]])
        self.assertIsNot(out[0][0], value)

    def test_unhashable_custom_type_preserves_deepcopy_error(self):
        class Unhashable(type):
            def __eq__(cls, other): return other is str
        class Value(metaclass=Unhashable): pass
        queue = [[Value()]]
        for copier in (copy.deepcopy, SELLER._copy_market_orders):
            with self.assertRaisesRegex(TypeError, 'unhashable type'):
                copier(queue)

    def test_invalid_outer_shape_uses_original_copy(self):
        for value in (None, 17, (['PASS'],), {'market': [['PASS']]}):
            self.assertEqual(SELLER._copy_market_orders(value), copy.deepcopy(value))

    def test_random_flat_queue_graphs(self):
        rng = random.Random(713)
        for _ in range(240):
            pool = [[rng.choice(('SELL', 'PASS', 'BUY_SEED')), 'WOOL', rng.randrange(8)]
                    for _ in range(rng.randrange(1, 8))]
            self.same_queue([rng.choice(pool) for _ in range(rng.randrange(12))])

    def test_replace_sales_original_parity(self):
        templates = [[], [['SELL','WOOL',8]], [['SELL','WOOL',2], ['HIRE'], ['SELL','WOOL',5]],
                     [[],['SELL','EGG',2],['SELL','WOOL',3],[]], [['BUY_SEED','WHEAT',1]],
                     [['SELL','WOOL',3],['SELL','WOOL',3]]]
        same = ['SELL','WOOL',3]; templates.append([same,same])
        for orders in templates:
            for quantity in range(10):
                for capacity in (2, 5, 10):
                    for reserved in ((), (0,)):
                        before = copy.deepcopy(orders)
                        a = REFERENCE.replace_sales(orders,'WOOL',quantity,8,capacity,reserved)
                        b = SELLER.replace_sales(orders,'WOOL',quantity,8,capacity,reserved)
                        self.assertEqual(a,b);self.assertEqual(orders,before)
                        if a is not None:
                            for i in range(len(a)):
                                for j in range(len(a)):
                                    self.assertEqual(a[i] is a[j], b[i] is b[j])
                        COUNTS['replacement_comparisons'] += 1

    def test_replace_sales_uses_new_copy(self):
        original = SELLER._copy_market_orders
        with patch.object(SELLER, '_copy_market_orders', wraps=original) as wrapped:
            SELLER.replace_sales([['SELL','WOOL',1]], 'WOOL',1,2,10)
        self.assertEqual(wrapped.call_count,1)

    def test_literal_feasibility_uses_new_copy(self):
        args, kwargs = fixture('empty',horizon=1)
        ledger = SELLER.ProjectionLedger(args[0],args[1],args[2],kwargs['post_unit_shed'],
                    kwargs['projection'],None,{},8)
        original = SELLER._copy_market_orders
        with patch.object(SELLER,'_copy_market_orders',wraps=original) as wrapped:
            self.assertTrue(ledger.feasible(None,()))
        self.assertEqual(wrapped.call_count,2)

    def test_dynamic_market_override_is_preserved(self):
        args, kwargs = fixture('multi',horizon=1)
        class CustomLedger(SELLER.ProjectionLedger):
            calls = 0
            def market(self,*args):
                self.calls += 1
                return None
        ledger = CustomLedger(args[0],args[1],args[2],kwargs['post_unit_shed'],kwargs['projection'],None,{},8)
        self.assertFalse(ledger.feasible('WOOL',((200,1),)))
        self.assertEqual(ledger.calls,1)

    def test_complete_transform_parity(self):
        for kind in ('multi','dense','terminal','empty'):
            for player in (0,1):
                for horizon in (1,2,4,8):
                    with self.subTest(kind=kind,player=player,horizon=horizon):
                        results = invoke_pair(*fixture(kind,player,horizon))
                        self.assertEqual(*results)
                        COUNTS['complete_transform_comparisons'] += 1
                        COUNTS['feasibility_comparisons'] += len(results[0][-1])

    def test_underfunded_empty_queue_fallback(self):
        args,kwargs=fixture('empty')
        args[0]['farms'][0]['money']=0
        results=invoke_pair(args,kwargs)
        self.assertEqual(*results)
        self.assertEqual(results[1][0],kwargs['fallback_action'])
        self.assertEqual(results[1][1]['status'],'fallback')

    def test_stateful_history_is_preserved(self):
        for player in (0,1):
            actors=[m.SelectedActionSell() for m in (REFERENCE,SELLER)]
            for step in (200,201,224):
                args,kwargs=fixture('multi',player,1)
                args[0].update(step=step,day=step//24,hour=step%24)
                kwargs['projection'].update(observed_step=step,end_step=step+1,
                    future_market={step+1:[['SELL','WOOL',6]]})
                rows=[]
                for actor in actors:
                    result=actor.transform(*args,**kwargs)
                    rows.append((result,actor.diagnostics,actor.previous,actor.observed_harvests))
                self.assertEqual(*rows)

    def test_nested_value_exception_matches_reference(self):
        class Broken:
            def __deepcopy__(self,memo): raise LookupError('copy witness')
        for module in (REFERENCE,SELLER):
            with self.assertRaisesRegex(LookupError,'copy witness'):
                module.replace_sales([['PASS',Broken()]],'WOOL',0,0,10)


def benchmark(rounds=9, repetitions=25):
    result={}
    for kind in ('multi','dense','terminal','empty'):
        args,kwargs=fixture(kind)
        samples={'reference':[],'candidate':[]}
        for round_index in range(rounds):
            order=((REFERENCE,'reference'),(SELLER,'candidate'))
            if round_index%2:order=tuple(reversed(order))
            for module,name in order:
                started=time.perf_counter()
                for _ in range(repetitions):
                    actor=module.SelectedActionSell()
                    actor.transform(*args,**kwargs)
                samples[name].append((time.perf_counter()-started)/repetitions)
        result[kind]={'samples_seconds':samples,
                      'median_reference_seconds':statistics.median(samples['reference']),
                      'median_candidate_seconds':statistics.median(samples['candidate'])}
    return result


def main():
    global SELLER,REFERENCE
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lab',default=str(ROOT))
    parser.add_argument('--report')
    parser.add_argument('--benchmark',action='store_true')
    args=parser.parse_args()
    SELLER,REFERENCE=load_pair(args.lab)
    stream=io.StringIO()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(CopyCases))
    report={'schema':'titan.queue-copy.final.v1','methods':result.testsRun,
            'failures':len(result.failures),'errors':len(result.errors),
            'passed':result.wasSuccessful(),'counts':COUNTS,'log':stream.getvalue(),
            'source_sha256':hashlib.sha256(Path(SELLER.__file__).read_bytes()).hexdigest(),
            'python':sys.version,'new_games':0,'engine_transitions':0}
    if args.benchmark and result.wasSuccessful():report['benchmark']=benchmark()
    if args.report:Path(args.report).write_text(json.dumps(report,indent=2)+'\n')
    print(stream.getvalue());print(json.dumps({k:v for k,v in report.items() if k not in ('log','benchmark')}))
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':
    raise SystemExit(main())
