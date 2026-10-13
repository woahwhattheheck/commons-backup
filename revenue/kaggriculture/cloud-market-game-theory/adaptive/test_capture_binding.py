# SPDX-License-Identifier: Apache-2.0
"""Exercise the real Agent class without importing unrelated policy dependencies.

The parent and observation plumbing below are explicit boundary-test harnesses.
The optimizer comparisons separately execute the unchanged production optimizer.
No test here is a full game, deadline measurement, or held-panel replay.
"""
import argparse
import ast
from copy import deepcopy
import gc
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from threading import RLock
from types import SimpleNamespace
import unittest
import weakref

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / 'runtime.py'
OPTIMIZER = HERE.parents[1] / 'cloud-execution-lab' / 'selected_sell_core.py'
REPORT = {'scope': 'Agent binding and real-optimizer component checks', 'games': 0}


def sample_kw(capacity=None):
    return dict(item='EGG', quantity=4, inventory=9998, params={},
                shops=['BAKERY', 'BRUNCH_SPOT'], config={}, now=650,
                dates=[650, 651, 658], reference=((658, 4),),
                rival_quantity=4, capacity_ok=capacity)


def sample_obs():
    return {'step': 650, 'market': {'inventory': {'EGG': 9998}, 'params': {}},
            'private': {'shed': {'EGG': 4}}}


def instrumented_optimizer(**kw):
    """Binding witness; not a substitute economic model."""
    return tuple(kw['reference']), {'feasible': True, 'binding_witness': True}


class Capacity:
    def __init__(self):
        self.calls = 0
    def __call__(self, plan):
        self.calls += 1
        return True


def load_agent(runtime_path, optimizer=instrumented_optimizer):
    """Compile the verbatim production Agent AST with named boundary fixtures."""
    sale = SimpleNamespace(optimize_lot=optimizer, PRODUCTS=('EGG',),
                           _sell=lambda order, item=None: bool(order) and order[0]=='SELL'
                           and (item is None or order[1]==item))
    class Parent:
        def __init__(self):
            self.calls = 0
            self.last_packet = None
            self.kw = sample_kw()
            self.before = None
            self.failure = None
            self.result = None
        def act(self, obs, cfg):
            self.calls += 1
            if self.before is not None:
                self.before()
            self.result = sale.optimize_lot(**self.kw)
            if self.failure is not None:
                raise self.failure
            return {'farmer':['PASS'], 'hands':[],
                    'market':[['SELL', self.kw['item'], dict(self.result[0]).get(self.kw['now'],0)]]}
    class Transformer:
        def __init__(self, mode):
            self.selector = SimpleNamespace(active=None)
            self.last = {}
            self.counts = {'projection_fallbacks':0}
        def expire(self, now):
            # These capture fixtures model no completion event. Actual expiry
            # and admission use the real runtime in test_completion_admission.
            pass
        def abort(self, base, reason):
            self.selector.active = None
            self.last = {'reason':reason}
            return deepcopy(base)
    namespace = dict(deepcopy=deepcopy, RLock=RLock, sale=sale,
                     integrated=SimpleNamespace(IntegratedSelectedAgent=Parent),
                     AdaptiveTransform=Transformer,
                     flow=SimpleNamespace(FlowHistory=lambda: SimpleNamespace()),
                     sorrel=SimpleNamespace(infer_rival_flow=lambda *a,**kw:{'products':{}}),
                     math=SimpleNamespace(m=SimpleNamespace(SHOPS={},TOWN_CENTER_PRODUCTS=[])))
    parsed = ast.parse(Path(runtime_path).read_text(), filename=str(runtime_path))
    selected = []
    for node in parsed.body:
        if isinstance(node, ast.ClassDef) and node.name == 'Agent':
            selected.append(node)
        elif isinstance(node, ast.Assign) and any(
            isinstance(t,ast.Name) and t.id in ('_OPTIMIZE_LOT','_CAPTURE_LOCK') for t in node.targets
        ):
            selected.append(node)
    if not any(isinstance(n,ast.ClassDef) for n in selected):
        raise ValueError('Production Agent class not found')
    exec(compile(ast.Module(body=selected,type_ignores=[]), str(runtime_path),'exec'), namespace)
    return namespace['Agent'], sale


def load_optimizer(path):
    sys.path.insert(0,str(path.parent))
    spec=importlib.util.spec_from_file_location('brook_actual_optimizer',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CaptureBindingTests(unittest.TestCase):
    def setUp(self):
        self.Agent,self.sale=load_agent(RUNTIME)

    def test_constructor_does_not_mutate_shared_optimizer(self):
        original=self.sale.optimize_lot
        self.Agent()
        self.assertIs(self.sale.optimize_lot,original)

    def test_two_instances_bind_the_same_optimizer(self):
        a,b=self.Agent(),self.Agent()
        self.assertIs(a.original,instrumented_optimizer)
        self.assertIs(b.original,instrumented_optimizer)

    def test_only_current_instance_collects_offers(self):
        a,b=self.Agent(),self.Agent()
        a.act(sample_obs())
        self.assertTrue(a.records)
        self.assertEqual(b.records,[])

    def test_second_instance_does_not_collect_into_first(self):
        a,b=self.Agent(),self.Agent()
        b.act(sample_obs())
        self.assertTrue(b.records)
        self.assertEqual(a.records,[])

    def test_many_instances_do_not_repeat_capacity_enumeration(self):
        actors=[self.Agent() for _ in range(12)]
        capacity=Capacity(); actors[-1].parent.kw=sample_kw(capacity)
        actors[-1].act(sample_obs())
        calls=capacity.calls
        fresh,sale=load_agent(RUNTIME); one=fresh(); single=Capacity()
        one.parent.kw=sample_kw(single); one.act(sample_obs())
        self.assertEqual(calls,single.calls)
        self.assertTrue(calls>0)
        self.assertEqual(sum(bool(a.records) for a in actors),1)

    def test_restores_shared_optimizer_on_success(self):
        original=self.sale.optimize_lot
        a=self.Agent(); a.act(sample_obs())
        self.assertIs(self.sale.optimize_lot,original)

    def test_restores_shared_optimizer_after_typeerror(self):
        original=self.sale.optimize_lot; failure=TypeError('body witness')
        a=self.Agent(); a.parent.failure=failure
        with self.assertRaises(TypeError) as caught:a.act(sample_obs())
        self.assertIs(caught.exception,failure)
        self.assertEqual(a.parent.calls,1)
        self.assertIs(self.sale.optimize_lot,original)

    def test_restores_shared_optimizer_after_baseexception(self):
        original=self.sale.optimize_lot; failure=KeyboardInterrupt('interruption witness')
        a=self.Agent(); a.parent.failure=failure
        with self.assertRaises(KeyboardInterrupt) as caught:a.act(sample_obs())
        self.assertIs(caught.exception,failure)
        self.assertIs(self.sale.optimize_lot,original)

    def test_restores_previous_external_binding(self):
        a=self.Agent()
        def external(**kw):return instrumented_optimizer(**kw)
        self.sale.optimize_lot=external
        a.act(sample_obs())
        self.assertIs(self.sale.optimize_lot,external)
        self.assertTrue(a.records)

    def test_baseline_skips_unused_offer_collection(self):
        a=self.Agent('baseline'); capacity=Capacity()
        a.parent.kw=sample_kw(capacity); a.act(sample_obs())
        self.assertEqual(a.records,[])
        self.assertEqual(capacity.calls,0)
        self.assertEqual(a.parent.result,instrumented_optimizer(**a.parent.kw))

    def test_active_plan_skips_unused_offer_collection(self):
        a=self.Agent(); a.transformer.selector.active={'existing':'plan'}
        capacity=Capacity(); a.parent.kw=sample_kw(capacity); a.act(sample_obs())
        self.assertEqual(a.records,[])
        self.assertEqual(capacity.calls,0)
        self.assertEqual(a.parent.result,instrumented_optimizer(**a.parent.kw))

    def test_baseline_after_adaptive_does_not_collect_into_either(self):
        a,b=self.Agent(),self.Agent('baseline'); b.act(sample_obs())
        self.assertEqual(a.records,[]); self.assertEqual(b.records,[])

    def test_unused_actor_can_be_collected(self):
        a=self.Agent(); reference=weakref.ref(a); del a; gc.collect()
        self.assertIsNone(reference())

    def test_used_actor_can_be_collected(self):
        a=self.Agent(); a.act(sample_obs()); reference=weakref.ref(a)
        del a; gc.collect(); self.assertIsNone(reference())

    def test_alternating_actors_keep_independent_records(self):
        a,b=self.Agent(),self.Agent(); a.act(sample_obs())
        count=len(a.records); b.act(sample_obs())
        self.assertEqual(len(a.records),count)
        self.assertEqual(len(b.records),count)
        self.assertEqual((a.parent.calls,b.parent.calls),(1,1))

    def test_nested_actor_calls_restore_outer_capture(self):
        outer,inner=self.Agent(),self.Agent(); original=instrumented_optimizer
        outer.parent.before=lambda:inner.act(sample_obs())
        outer.act(sample_obs())
        self.assertEqual(len(outer.records),1);self.assertEqual(len(inner.records),1)
        self.assertEqual((outer.parent.calls,inner.parent.calls),(1,1))
        self.assertIs(self.sale.optimize_lot,original)

    def test_nested_actor_construction_does_not_capture_outer(self):
        outer=self.Agent(); inner=[]
        def nested():
            a=self.Agent();inner.append(a);a.act(sample_obs())
        outer.parent.before=nested;outer.act(sample_obs())
        self.assertIs(inner[0].original,instrumented_optimizer)
        self.assertEqual(len(outer.records),1);self.assertEqual(len(inner[0].records),1)

    def test_exactly_one_parent_call_and_no_input_mutation(self):
        a=self.Agent();obs=sample_obs();before=deepcopy(obs)
        out=a.act(obs)
        self.assertEqual(a.parent.calls,1);self.assertEqual(obs,before)
        self.assertEqual(out,{'farmer':['PASS'],'hands':[],'market':[['SELL','EGG',0]]})

    def test_new_admission_collects_original_plan_first(self):
        a=self.Agent();a.act(sample_obs())
        kw,plans=a.records[0]
        self.assertEqual(tuple(map(tuple,plans[0]['sales'])),kw['reference'])
        self.assertTrue(len(plans)>1)

    def test_optimizer_error_is_not_retried(self):
        failure=ValueError('optimizer witness');calls=[]
        def broken(**kw):calls.append(kw);raise failure
        Agent,sale=load_agent(RUNTIME,broken);a=Agent()
        with self.assertRaises(ValueError) as caught:a.act(sample_obs())
        self.assertIs(caught.exception,failure)
        self.assertEqual(len(calls),1);self.assertEqual(a.parent.calls,1)


class ActualOptimizerTests(unittest.TestCase):
    def test_all_products_preserve_actual_optimizer_results(self):
        model=load_optimizer(OPTIMIZER)
        Agent,sale=load_agent(RUNTIME,model.optimize_lot)
        rows=[];active=0
        for item in model.m.PRODUCTS:
            for quantity in (1,2,6):
                for inventory in (9950,10000,10200,11000):
                    kw=sample_kw();kw.update(item=item,quantity=quantity,inventory=inventory,
                        params=model.m.MARKET_PARAMS,shops=list(model.m.SHOPS),
                        reference=((658,quantity),),rival_quantity=quantity)
                    expected=model.optimize_lot(**kw)
                    a=Agent();a.parent.kw=kw;a.act(sample_obs())
                    self.assertEqual(a.parent.result,expected)
                    active+=bool(a.records)
                    rows.append({'item':item,'quantity':quantity,'inventory':inventory,
                                 'plan':expected[0],'info':expected[1]})
        self.assertGreater(active,0)
        REPORT['actual_optimizer']={'cases':len(rows),'capturing_cases':active,
            'results_sha256':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()}

    def test_baseline_and_active_keep_real_results_with_fewer_callbacks(self):
        model=load_optimizer(OPTIMIZER);rows=[]
        for mode in ('baseline','active','adaptive'):
            Agent,sale=load_agent(RUNTIME,model.optimize_lot)
            a=Agent('adaptive' if mode=='active' else mode)
            if mode=='active':a.transformer.selector.active={'existing':'plan'}
            capacity=Capacity();kw=sample_kw(capacity);kw.update(params=model.m.MARKET_PARAMS)
            a.parent.kw=kw;a.act(sample_obs());calls=capacity.calls
            direct_capacity=Capacity();direct=model.optimize_lot(**(kw|{'capacity_ok':direct_capacity}))
            self.assertEqual(a.parent.result,direct)
            if mode!='adaptive':self.assertEqual(calls,direct_capacity.calls)
            else:self.assertGreater(calls,direct_capacity.calls)
            rows.append({'mode':mode,'capacity_calls':calls,'direct_calls':direct_capacity.calls})
        REPORT['capacity_callbacks']=rows


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,default=RUNTIME)
    parser.add_argument('--optimizer',type=Path,default=OPTIMIZER)
    parser.add_argument('--report',type=Path)
    args,rest=parser.parse_known_args();RUNTIME=args.runtime;OPTIMIZER=args.optimizer
    REPORT['runtime_sha256']=hashlib.sha256(RUNTIME.read_bytes()).hexdigest()
    REPORT['optimizer_sha256']=hashlib.sha256(OPTIMIZER.read_bytes()).hexdigest()
    suite=unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    REPORT['tests']={'run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
                    'success':result.wasSuccessful()}
    if args.report:args.report.write_text(json.dumps(REPORT,indent=2,sort_keys=True)+'\n')
    sys.exit(not result.wasSuccessful())
