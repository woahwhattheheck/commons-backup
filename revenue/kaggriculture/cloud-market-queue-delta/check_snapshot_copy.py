# SPDX-License-Identifier: Apache-2.0
"""Exact-state copy and saved IRIS-consumer checks. No games or actor calls.

The input package is the existing TITAN-IRIS-Lonespear-Public-Clock delivery.
Rival private state in its six retained cases is used as offline test data only.
"""
from __future__ import annotations
import argparse
import copy
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import statistics
import sys
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
BEFORE = AFTER = ENGINE = CONSUMER = None
INPUTS = []
COUNTS = dict(report_pairs=0, full_market_references=0)
EXPECTED_BASE = 'b95dff0010cf70941cc96e7f416798d36a8aa57d'
EXPECTED_CASES = '3850381a54e1fcaf0c83a7073fce53787cae03b6f246fc1027c4f6724d200077'
EXPECTED_ENGINE = 'bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e'


def load(path, name):
    # Tests execute the bytes that they hash, not a potentially stale .pyc.
    path = Path(path).resolve()
    module = SimpleNamespace(__file__=str(path), __name__=name)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def untimed(report):
    result = copy.deepcopy(report)
    if 'comparison' in result:
        if result['comparison'] is not None:
            result['comparison'].pop('elapsed_seconds', None)
    else:
        result.pop('elapsed_seconds', None)
    return result


def direct_inputs(inputs, result):
    return dict(step=result['prediction']['step'], seat=inputs['observation']['player'],
        own_farm=inputs['own_farm'], own_private=inputs['own_private'], market=inputs['market'],
        baseline_action=inputs['selected_action'], proposed_action=result['proposal_action'],
        scenarios=inputs['scenarios'], configuration=inputs['configuration'])


def consumer(module, inputs):
    return CONSUMER.evaluate_wheat_response(module.compare_queues, ENGINE, **inputs)


def compare_complete(test, inputs):
    old = copy.deepcopy(inputs)
    left, right = consumer(BEFORE, inputs), consumer(AFTER, inputs)
    test.assertEqual(left['status'], 'complete_conditional')
    test.assertEqual(untimed(left), untimed(right))
    test.assertEqual(inputs, old)
    test.assertFalse(right['action_selected'])
    COUNTS['report_pairs'] += 1
    return right


def reference(test, inputs, result):
    """One original complete-market invocation, independent of slot traversal."""
    own = inputs['observation']['player']
    for scenario, row in zip(inputs['scenarios'], result['comparison']['scenario_results']):
        for arm, action in [('baseline', inputs['selected_action']), ('proposed', result['proposal_action'])]:
            farms, privates = [None, None], [None, None]
            farms[own], privates[own] = copy.deepcopy((inputs['own_farm'], inputs['own_private']))
            farms[1-own], privates[1-own] = copy.deepcopy((scenario['farm'], scenario['private']))
            market = copy.deepcopy(inputs['market'])
            actions = [None, None]
            actions[own], actions[1-own] = copy.deepcopy((action, scenario['action']))
            state = [SimpleNamespace(observation=SimpleNamespace(farms=farms, private=privates[i], market=market), action=actions[i]) for i in (0, 1)]
            ENGINE._process_market(state, SimpleNamespace(configuration=inputs['configuration']))
            COUNTS['full_market_references'] += 1
            test.assertEqual(row[arm]['own_farm'], farms[own])
            test.assertEqual(row[arm]['rival_farm'], farms[1-own])
            test.assertEqual(row[arm]['own_private'], privates[own])
            test.assertEqual(row[arm]['rival_private'], privates[1-own])
            test.assertEqual(row[arm]['market'], market)


def graph(value, memo=None):
    """Type/alias/cycle signature for independent copy results."""
    if memo is None:
        memo = {}
    if type(value) in (type(None), int, float, str, bool):
        return (type(value).__name__, value)
    if id(value) in memo:
        return ('ref', memo[id(value)])
    marker = len(memo); memo[id(value)] = marker
    if isinstance(value, dict):
        body = [(graph(k, memo), graph(v, memo)) for k, v in value.items()]
    elif isinstance(value, (list, tuple)):
        body = [graph(v, memo) for v in value]
    elif hasattr(value, '__dict__'):
        body = graph(value.__dict__, memo)
    else:
        body = repr(value)
    return (marker, type(value).__name__, body)


class SnapshotCopyTests(unittest.TestCase):
    def assertCopy(self, value):
        expected = copy.deepcopy(value)
        actual = AFTER._snapshot_copy(value)
        self.assertEqual(graph(expected), graph(actual))
        return actual

    def test_exact_scalars_and_nested_containers(self):
        for value in [None, True, 7, -9, 3.5, 'stock', {}, [], {'x':[1,2,{'y':False}]}]:
            with self.subTest(value=value): self.assertCopy(value)

    def test_repeated_references_stay_shared_but_detached(self):
        stock = {'WHEAT':3}; value = {'a': stock, 'b':[stock, stock]}
        out = self.assertCopy(value)
        self.assertIs(out['a'], out['b'][0]); self.assertIs(out['a'], out['b'][1])
        self.assertIsNot(out['a'], stock); out['a']['WHEAT'] = 8
        self.assertEqual(stock['WHEAT'], 3)

    def test_list_and_dict_cycles(self):
        a=[]; b={'a':a}; a.extend([a,b]); b['self']=b
        self.assertCopy(a); self.assertCopy(b)

    def test_tuple_fallback_crosses_fast_graph(self):
        a=[]; t=(a,); a.append(t)
        self.assertCopy({'list':a,'tuple':t,'again':a})

    def test_container_subclasses_keep_their_deepcopy_hooks(self):
        calls=[]
        class Bag(list):
            def __deepcopy__(self,memo):
                calls.append('bag'); out=Bag();memo[id(self)]=out
                out.extend(copy.deepcopy(v,memo) for v in self);return out
        class Map(dict):
            def __deepcopy__(self,memo):
                calls.append('map'); out=Map();memo[id(self)]=out
                out.update((k,copy.deepcopy(v,memo)) for k,v in self.items());return out
        common={}; value={'bag':Bag([common]),'map':Map(a=common),'common':common}
        expected=copy.deepcopy(value); old=list(calls);calls.clear()
        actual=AFTER._snapshot_copy(value)
        self.assertEqual(calls,old);self.assertEqual(graph(expected),graph(actual))

    def test_scalar_subclasses_do_not_take_atomic_shortcut(self):
        calls=[]
        class Scalar(int):
            def __deepcopy__(self,memo):
                calls.append(int(self));return Scalar(int(self)+1)
        result=self.assertCopy({'value':Scalar(8)})
        self.assertEqual(result['value'],9);self.assertEqual(calls,[8,8])

    def test_custom_object_aliases_cross_both_copy_paths(self):
        class Payload:
            def __init__(self, shared): self.shared=shared
        common=[]; obj=Payload(common);common.append(obj)
        self.assertCopy({'obj':obj,'common':common})

    def test_custom_dictionary_key_copy_order_matches(self):
        calls=[]
        class Key:
            def __deepcopy__(self,memo): calls.append('key');return self
        class Value:
            def __deepcopy__(self,memo): calls.append('value');return 'copied'
        key=Key(); value={key:Value()}
        expected=copy.deepcopy(value);sequence=list(calls);calls.clear()
        actual=AFTER._snapshot_copy(value)
        self.assertEqual(actual,expected);self.assertEqual(calls,sequence)

    def test_copy_exception_and_cancellation_identity(self):
        class Stop(BaseException): pass
        for failure in (ValueError('copy failed'),Stop('cancel')):
            class Value:
                def __deepcopy__(self,memo): raise failure
            with self.assertRaises(type(failure)) as exc:
                AFTER._snapshot_copy({'value':Value()})
            self.assertIs(exc.exception,failure)

    def test_copy_keeps_memo_sources_alive(self):
        value={'a':[{}]}; memo={}
        AFTER._snapshot_copy(value,memo)
        retained=memo[id(memo)]
        for original in (value,value['a'],value['a'][0]):
            self.assertTrue(any(x is original for x in retained))

    def test_view_aliases_and_detachment(self):
        a=INPUTS[0];f=copy.deepcopy(a['own_farm']);p=copy.deepcopy(a['own_private'])
        shared={'WHEAT':2};p['shed']=shared;p['seeds']=shared
        old=BEFORE._view(f,p);new=AFTER._view(f,p)
        self.assertEqual(graph(old),graph(new));self.assertIs(new['shed'],new['seeds'])
        new['shed']['WHEAT']=9;self.assertEqual(p['shed']['WHEAT'],2)

    def test_ordinary_snapshot_avoids_generic_deepcopy(self):
        a=INPUTS[0]
        with patch.object(AFTER.copy,'deepcopy',side_effect=AssertionError('generic traversal')):
            snapshot=AFTER._view(a['own_farm'],a['own_private'])
        self.assertEqual(snapshot['cash'],a['own_farm']['money'])
        with patch.object(BEFORE.copy,'deepcopy',side_effect=AssertionError('baseline generic traversal')):
            with self.assertRaises(AssertionError): BEFORE._view(a['own_farm'],a['own_private'])

    def test_all_six_retained_inputs_match_full_reports_and_market(self):
        for a in INPUTS:
            with self.subTest(seat=a['observation']['player']):
                result=compare_complete(self,a);reference(self,a,result)

    def test_sparse_and_null_clock_consumer_reports_remain_equal(self):
        for a in INPUTS:
            for form in ('missing','null'):
                b=copy.deepcopy(a)
                if form=='missing':b['observation'].pop('step')
                else:b['observation']['step']=None
                result=compare_complete(self,b);reference(self,b,result)

    def test_custom_configuration_exact_reports(self):
        for a in INPUTS:
            for mult in (0,1,3):
                b=copy.deepcopy(a);b['configuration']['farmHandCostMult']=mult
                result=compare_complete(self,b);reference(self,b,result)

    def test_repeated_market_orders_and_input_aliases(self):
        base=consumer(BEFORE,INPUTS[0]);kw=direct_inputs(INPUTS[0],base)
        kw=copy.deepcopy(kw);order=['SELL','WHEAT',2]
        kw['baseline_action']['market']=[order,order];kw['proposed_action']['market']=[[],order,order]
        old=copy.deepcopy(kw)
        left=BEFORE.compare_queues(ENGINE,**kw);right=AFTER.compare_queues(ENGINE,**kw)
        self.assertEqual(untimed(left),untimed(right));self.assertEqual(kw,old)
        COUNTS['report_pairs']+=1

    def test_engine_call_and_deadline_counts_unchanged(self):
        a=INPUTS[0];counts=[]
        for module in (BEFORE,AFTER):
            native=ENGINE._process_market;ticks=[];calls=[]
            def observe(*args): calls.append(1);return native(*args)
            original=module._check_deadline
            def check(*args):ticks.append(1);return original(*args)
            with patch.object(ENGINE,'_process_market',side_effect=observe),patch.object(module,'_check_deadline',side_effect=check):
                result=consumer(module,a)
            self.assertEqual(result['status'],'complete_conditional');counts.append((len(calls),len(ticks)))
        self.assertEqual(counts[0],counts[1])

    def test_deadlines_preserve_partial_unknown_reports(self):
        # Identical checkpoints including preflight and exhaustion after a row.
        for stop in (1,2,4,8,16,22,30):
            reports=[]
            for module in (BEFORE,AFTER):
                calls=[0]
                def check(deadline):
                    calls[0]+=1
                    if calls[0]==stop:raise module.BudgetExceeded('deadline')
                with patch.object(module,'_check_deadline',side_effect=check):reports.append(consumer(module,INPUTS[0]))
            self.assertEqual(untimed(reports[0]),untimed(reports[1]))
            if reports[1]['status']=='unknown':
                self.assertIsNone(reports[1]['comparison']['bounds']);self.assertIsNone(reports[1]['proposal_action'])
            COUNTS['report_pairs']+=1

    def test_engine_failure_and_foreign_cancellation(self):
        class Cancel(BaseException):pass
        for failure in (RuntimeError('engine failure'),Cancel('outer cancelled')):
            reports=[]
            for module in (BEFORE,AFTER):
                with patch.object(ENGINE,'_process_market',side_effect=failure):
                    if isinstance(failure,Exception):reports.append(consumer(module,INPUTS[0]))
                    else:
                        with self.assertRaises(Cancel) as exc:consumer(module,INPUTS[0])
                        self.assertIs(exc.exception,failure)
            if reports:self.assertEqual(untimed(reports[0]),untimed(reports[1]))

    def test_unknown_inputs_preserve_fallback(self):
        for key,value in [('scenarios',[]),('retained_wheat',1),('max_unit_steps',0),('deadline',0.0)]:
            a=copy.deepcopy(INPUTS[0]);a[key]=value
            self.assertEqual(untimed(consumer(BEFORE,a)),untimed(consumer(AFTER,a)))
            COUNTS['report_pairs']+=1

    def test_complete_report_output_is_detached(self):
        a=copy.deepcopy(INPUTS[0]);saved=copy.deepcopy(a);r=compare_complete(self,a)
        row=r['comparison']['scenario_results'][0]
        row['proposed']['own_farm']['tiles'][0][0]='changed'
        row['proposed']['own_private']['shed']['WHEAT']=999
        row['proposed']['own']['shed']['WHEAT']=1000
        self.assertEqual(a,saved)


def prepare(source,baseline,package):
    global BEFORE,AFTER,ENGINE,CONSUMER,INPUTS
    source,baseline,package=map(lambda p:Path(p).resolve(),(source,baseline,package))
    raw=baseline.read_bytes()
    if hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()!=EXPECTED_BASE:
        raise ValueError('Baseline must be original PR10035 b95dff00')
    cases_body=(package/'evidence/cases.json.gz').read_bytes()
    if hashlib.sha256(cases_body).hexdigest()!=EXPECTED_CASES:raise ValueError('Original six cases required')
    if hashlib.sha256((package/'engine/kaggriculture.py').read_bytes()).hexdigest()!=EXPECTED_ENGINE:
        raise ValueError('Pinned engine required')
    sys.path.insert(0,str(package/'source'))
    import queue_response
    CONSUMER=queue_response; BEFORE=load(baseline,'snapshot_copy_before');AFTER=load(source,'snapshot_copy_after')
    ENGINE=AFTER.load_market_engine(package/'engine/kaggriculture.py')
    cfg=json.loads((package/'source/base-frame.json').read_text())['configuration']
    INPUTS=[]
    for case in json.loads(gzip.decompress(cases_body)):
        own=case['own'];other=1-own;post=case['post_unit_observation'];priv=case['offline_post_unit_privates'];actions=case['original_actions']
        no_feed=copy.deepcopy(actions[other]);no_feed['market']=[['PASS'] if isinstance(o,list) and len(o)==3 and o[:2]==['BUY_PRODUCT','WHEAT'] else o for o in no_feed['market']]
        scenarios=[dict(id='recorded-rival',provenance='Retained evaluation-only scenario, not a runtime inference',farm=post['farms'][other],private=priv[other],action=actions[other]),dict(id='no-feed',provenance='Existing offline no-feed intervention',farm=post['farms'][other],private=priv[other],action=no_feed)]
        INPUTS.append(dict(observation=case['observation'],configuration=cfg,selected_action=actions[own],own_farm=post['farms'][own],own_private=priv[own],market=post['market'],scenarios=scenarios,retained_wheat=0))
    return dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),baseline_git_blob=EXPECTED_BASE,
                cases_sha256=EXPECTED_CASES,engine_sha256=EXPECTED_ENGINE,
                consumer_sha256=hashlib.sha256((package/'source/queue_response.py').read_bytes()).hexdigest(),
                behavior_sha256=hashlib.sha256((package/'source/behavior.py').read_bytes()).hexdigest())


def benchmark(samples):
    result=[]
    for inputs in INPUTS:
        times={'before':[],'after':[]}
        consumer(BEFORE,inputs);consumer(AFTER,inputs)
        for i in range(samples):
            output={}
            order=[('before',BEFORE),('after',AFTER)]
            if i%2:order.reverse()
            for label,module in order:
                start=time.perf_counter();output[label]=consumer(module,inputs)
                times[label].append(time.perf_counter()-start)
            if untimed(output['before'])!=untimed(output['after']):raise AssertionError('Timed output drift')
        a,b=map(lambda k:statistics.median(times[k]),('before','after'))
        result.append(dict(player=inputs['observation']['player'],samples=samples,seconds=times,
                           before_median_seconds=a,after_median_seconds=b,reduction_fraction=1-b/a))
    a=sum(r['before_median_seconds'] for r in result);b=sum(r['after_median_seconds'] for r in result)
    return dict(cases=result,before_sum_medians_seconds=a,after_sum_medians_seconds=b,reduction_fraction=1-b/a,
                scope='Warm complete evaluate_wheat_response calls, two retained scenarios per case; no imports, serialization, actor or game measurement')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=HERE/'queue_delta.py')
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--iris-package',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--benchmark-samples',type=int,default=0)
    args=parser.parse_args()
    if not 0<=args.benchmark_samples<=101:parser.error('benchmark-samples must be between 0 and 101')
    pins=prepare(args.source,args.baseline,args.iris_package)
    log=io.StringIO();start=time.perf_counter()
    tests=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SnapshotCopyTests))
    report=dict(pins=pins,tests=tests.testsRun,failures=len(tests.failures),errors=len(tests.errors),elapsed_seconds=time.perf_counter()-start,
                counts=COUNTS,log=log.getvalue(),new_games=0,policy_calls=0)
    if tests.wasSuccessful() and args.benchmark_samples:report['benchmark']=benchmark(args.benchmark_samples)
    args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(log.getvalue());print(json.dumps({k:v for k,v in report.items() if k not in ('log','benchmark')},indent=2))
    if 'benchmark' in report:print('weighted workload reduction',report['benchmark']['reduction_fraction'])
    return 0 if tests.wasSuccessful() else 1

if __name__=='__main__':raise SystemExit(main())
