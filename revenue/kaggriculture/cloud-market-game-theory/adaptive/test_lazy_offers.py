# SPDX-License-Identifier: Apache-2.0
"""Source-level lazy-offer tests using real receipt/ledger/selection components.

The parent is a deterministic supplied-action fixture: these are not games or
replays. AST loading executes the exact production classes without importing
unrelated controller/history bootstrap paths. Receipt math, the real ledger,
whole-plan application and continuation validation are imported unchanged.
"""
from __future__ import annotations

import ast
import copy
import importlib.util
import inspect
from pathlib import Path
import random
import sys
from tempfile import TemporaryDirectory
from threading import RLock
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LAB = ROOT / 'cloud-execution-lab'
sys.path.insert(0, str(LAB))
import selected_action_sell as sale
import selected_sell_core as core


def load_file(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


recourse = load_file(HERE/'recourse.py', 'cove_recourse')
ash = load_file(ROOT/'cloud-plan-continuation/continuation.py', 'cove_continuation')
fills = load_file(ROOT/'cloud-observed-fills/observed_fills.py', 'cove_observed_fills')


def classes(path, names, environment, *, support=()):
    """Compile unchanged classes and their explicitly requested source helpers.

    Optional support names also let historical runtimes without these helpers
    remain loadable. Unrelated imports, assignments and bootstrap calls are not
    executed. Production class/function bodies are never rewritten.
    """
    module = ast.parse(path.read_text(), filename=str(path))
    body = []
    found = set()
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name in names:
            body.append(node)
            found.add(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in support:
            body.append(node)
        elif isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id in support for target in node.targets):
            body.append(node)
    if found != set(names):
        raise ValueError(f'Missing production classes in {path}')
    namespace = dict(environment)
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), 'exec'), namespace)
    return SimpleNamespace(**namespace)


def unused_solver(*args, **kwargs):
    raise AssertionError('Adaptive admission does not call the mixed-plan solver')


WholePlanSelector = classes(HERE.parent/'selector.py', ['WholePlanSelector'],
                            {'copy':copy, 'random':random, 'solve_table':unused_solver}).WholePlanSelector


class EmptyHistory:
    def scenarios(self, *args, **kwargs):
        return [], {}

    def add(self, value):
        raise AssertionError('These fixtures contain no observed flow history')


class SuppliedParent:
    """One deterministic producer decision with supplied captured windows."""
    def __init__(self):
        self.action = {'farmer':['PASS'], 'hands':[['PASS']], 'market':[], 'tag':'preserve'}
        self.records = []
        self.last_packet = None
        self.calls = 0
        self.error = None

    def act(self, observation, configuration):
        self.calls += 1
        if self.error:
            raise self.error
        # Exercise BROOK's actual call-scoped binding. Active/baseline calls
        # do not capture; do not fabricate records when collection is off.
        actor = getattr(sale.optimize_lot, '__self__', None)
        if actor is not None:
            actor.records.extend(copy.deepcopy(self.records))
        return copy.deepcopy(self.action)


def runtime(path=None, compiler=None):
    return classes(Path(path) if path else HERE/'runtime.py', ['AdaptiveTransform','Agent'], {
        'deepcopy':copy.deepcopy, 'WholePlanSelector':WholePlanSelector, 'ash':ash, 'fills':fills,
        'sale':sale, 'math':core, 'integrated':SimpleNamespace(IntegratedSelectedAgent=SuppliedParent),
        'flow':SimpleNamespace(FlowHistory=EmptyHistory),
        'sorrel':SimpleNamespace(infer_rival_flow=lambda *a, **k: {'products':{}}),
        'bounded_history_streams':lambda rows, limit: [],
        'compile_policy':compiler or recourse.compile_policy,
        'choose_observed':recourse.choose_observed,
        '_CAPTURE_LOCK':RLock(), '_OPTIMIZE_LOT':sale.optimize_lot,
    }, support=('_PRICE_FIELDS', '_economic_context', '_context_reason'))


def record(item='EGG', *, now=40, end=48, quantity=6, inventory=40):
    return ({'item':item,'now':now,'dates':[now,now+1,end], 'quantity':quantity,
             'inventory':inventory,'params':None,'shops':['BAKERY']},
            [{'id':'early','sales':[[now+1,quantity]]},
             {'id':'late','sales':[[end,quantity]]}])


def scenario(records=None, *, mode='adaptive', module=None, seat=0, now=40, end=48):
    module = module or runtime()
    agent = module.Agent(mode)
    records = records if records is not None else [record()]
    agent.parent.records = copy.deepcopy(records)
    shed = {p:0 for p in sale.PRODUCTS}
    for kw, plans in records:
        shed[kw['item']] = max(shed.get(kw['item'],0), kw.get('quantity',0))
    obs = {'step':now, 'player':seat, 'private':{'shed':shed},
           'farms':[{'money':10000}, {'money':10000}],
           'market':{'inventory':{p:40 for p in core.m.PRODUCTS}, 'params':None},
           'town':{'unlocked_shops':['BAKERY']}}
    projection = {'observed_step':now, 'end_step':end, 'stock_events':[],
                  'future_market':{t:[] for t in range(now+1,end+1)}}
    agent.parent.last_packet = {'projection':projection,
        'post_unit_observation':copy.deepcopy(obs), 'arrival_contract':None}
    return agent, obs, {}


def controlled_compiler(active=None, fail_item=None, failure=ValueError):
    """Boundary-only compiler fixture; real compiler is tested separately."""
    calls=[]
    active = set(sale.PRODUCTS) if active is None else set(active)
    def compile_one(model, plans, quantity, streams, branch, absorption):
        calls.append(model.item)
        if model.item == fail_item:
            raise failure('controlled compilation failure')
        return {'active':model.item in active,'branch':branch,'prefix':[],
                'plans':copy.deepcopy(plans),'static_choice':1,
                'worst_margin':0,'choices':{str(model.inventory):1}}
    compile_one.calls = calls
    return compile_one


def eager_type(module):
    """List materialization recreates the original eager compilation boundary."""
    class Eager(module.Agent):
        def _offers(self, cfg, base):
            return list(super()._offers(cfg, base))
    return Eager


def observable(agent, output):
    tr=agent.transformer
    return {'action':output,'last':agent.last, 'previous':agent.previous,
            'previous_sales':agent.previous_sales,
            'active':tr.selector.active if tr else None,
            'completed':sorted(tr.selector.completed) if tr else [],
            'transform_counts':tr.counts if tr else {},
            'continuation':tr.continuation.last_decision if tr else None,
            'parent_calls':agent.parent.calls}


class LoaderTests(unittest.TestCase):
    def test_current_runtime_binds_economic_helpers(self):
        module = runtime()
        self.assertEqual(module._PRICE_FIELDS,
                         ('base', 'I0', 'T', 'below_func', 'below_target',
                          'above_func', 'above_target'))
        context = module._economic_context('EGG', None, ['BAKERY'], {}, 40, 48)
        observation = {'step': 40, 'town': {'unlocked_shops': ['BAKERY']},
                       'market': {'params': None}}
        self.assertIsNone(module._context_reason({'economic_context': context},
                                                observation, {}, 'EGG', 48,
                                                admission=True))

    def test_current_runtime_uses_real_fill_recorder(self):
        module = runtime()
        self.assertIs(module.fills, fills)
        recorder = module.fills.ObservedFillLedger()
        recorded = recorder.record({'step': 40, 'player': 0}, {},
            {'market': [['SELL', 'EGG', 2]]}, post_unit_shed={'EGG': 2})
        result = recorder.observe({'step': 41, 'player': 0,
                                   'private': {'shed': {'EGG': 0}}})
        self.assertEqual(recorded['status'], 'recorded')
        self.assertTrue(module.fills.full_sale_verdict(result, 0, 2))

    def test_only_requested_support_nodes_execute(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'fixture.py'
            path.write_text("LIMIT = 7\n"
                            "UNRELATED = trigger()\n"
                            "def helper(value): return value + LIMIT\n"
                            "class Fixture:\n"
                            "    def call(self): return helper(2)\n")
            module = classes(path, ['Fixture'], {}, support=('LIMIT', 'helper'))
            self.assertEqual(module.Fixture().call(), 9)
            self.assertFalse(hasattr(module, 'UNRELATED'))
            self.assertEqual(module.helper.__code__.co_filename, str(path))

    def test_historical_class_needs_no_optional_helpers(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'fixture.py'
            path.write_text('class Fixture:\n    value = 11\n')
            module = classes(path, ['Fixture'], {}, support=('absent_helper',))
            self.assertEqual(module.Fixture.value, 11)

    def test_missing_required_class_is_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'fixture.py'
            path.write_text('def optional_helper(): return 1\n')
            with self.assertRaisesRegex(ValueError, 'Missing production classes'):
                classes(path, ['Missing'], {}, support=('optional_helper',))


class LazyOfferTests(unittest.TestCase):
    def test_first_admissible_stops_compilation(self):
        compiler=controlled_compiler()
        a,o,c=scenario([record('EGG'),record('MILK'),record('WOOL')],module=runtime(compiler=compiler))
        out=a.act(o,c)
        self.assertEqual(compiler.calls,['EGG'])
        self.assertEqual(a.offer_work,{'captured_windows':3,'inspected_windows':1,'compiled_windows':1,'admitted_index':0})
        self.assertEqual(a.transformer.selector.active['item'],'EGG')
        self.assertEqual(out['farmer'],['PASS'])
        self.assertEqual(a.parent.calls,1)

    def test_rejected_window_keeps_order(self):
        compiler=controlled_compiler(active={'MILK','WOOL'})
        a,o,c=scenario([record('EGG'),record('MILK'),record('WOOL')],module=runtime(compiler=compiler))
        a.act(o,c)
        self.assertEqual(compiler.calls,['EGG','MILK'])
        self.assertEqual(a.offer_work['admitted_index'],1)
        self.assertEqual(a.transformer.selector.active['item'],'MILK')

    def test_no_admission_compiles_every_window(self):
        compiler=controlled_compiler(active=set())
        a,o,c=scenario([record('EGG'),record('MILK'),record('WOOL')],module=runtime(compiler=compiler))
        self.assertEqual(a.act(o,c),a.parent.action)
        self.assertEqual(compiler.calls,['EGG','MILK','WOOL'])
        self.assertEqual(a.offer_work['compiled_windows'],3)
        self.assertIsNone(a.offer_work['admitted_index'])

    def test_duplicate_slots_preserve_record_index(self):
        compiler=controlled_compiler()
        a,o,c=scenario([record('EGG'),record('MILK')],module=runtime(compiler=compiler))
        a.parent.action['market']=[['SELL','EGG',1],['SELL','EGG',1]]
        # Keep the chosen MILK slot (2) identical across future dates.
        for orders in a.parent.last_packet['projection']['future_market'].values():
            orders.extend([[],[]])
        out=a.act(o,c)
        self.assertEqual(compiler.calls,['MILK'])
        self.assertEqual(a.offer_work,{'captured_windows':2,'inspected_windows':2,'compiled_windows':1,'admitted_index':1})
        self.assertEqual(out['market'][:2],a.parent.action['market'])

    def test_unused_failure_cannot_veto_accepted_choice(self):
        compiler=controlled_compiler(fail_item='MILK')
        a,o,c=scenario([record('EGG'),record('MILK')],module=runtime(compiler=compiler))
        a.act(o,c)
        self.assertEqual(a.last['reason'],'admitted')
        self.assertEqual(compiler.calls,['EGG'])
        self.assertEqual(a.transformer.counts['projection_fallbacks'],0)

    def test_reached_failure_keeps_original_fallback(self):
        for exc in (ValueError,KeyError,TypeError,IndexError):
            with self.subTest(exc=exc.__name__):
                compiler=controlled_compiler(active=set(),fail_item='MILK',failure=exc)
                a,o,c=scenario([record('EGG'),record('MILK'),record('WOOL')],module=runtime(compiler=compiler))
                self.assertEqual(a.act(o,c),a.parent.action)
                self.assertEqual(compiler.calls,['EGG','MILK'])
                self.assertEqual(a.last,{'reason':exc.__name__})
                self.assertEqual(a.offer_work['compiled_windows'],1)
                self.assertIsNone(a.offer_work['admitted_index'])

    def test_uncaught_failure_still_propagates_once(self):
        compiler=controlled_compiler(fail_item='EGG',failure=RuntimeError)
        a,o,c=scenario(module=runtime(compiler=compiler))
        with self.assertRaisesRegex(RuntimeError,'controlled compilation'):
            a.act(o,c)
        self.assertEqual(compiler.calls,['EGG'])
        self.assertEqual(a.parent.calls,1)

    def test_baseline_never_collects_or_compiles(self):
        compiler=controlled_compiler(fail_item='EGG')
        a,o,c=scenario(mode='baseline',module=runtime(compiler=compiler))
        self.assertEqual(a.act(o,c),a.parent.action)
        self.assertEqual(compiler.calls,[])
        self.assertEqual(a.offer_work['captured_windows'],0)

    def test_active_plan_does_not_compile_and_counters_reset(self):
        compiler=controlled_compiler()
        a,o,c=scenario(module=runtime(compiler=compiler))
        first=a.act(o,c)
        second=a.act(o,c)
        self.assertEqual(first,second)
        self.assertEqual(compiler.calls,['EGG'])
        self.assertEqual(a.offer_work,{'captured_windows':0,'inspected_windows':0,'compiled_windows':0,'admitted_index':None})
        self.assertEqual(a.parent.calls,2)

    def test_completed_plan_collects_but_rejects_stale_offer_context(self):
        compiler=controlled_compiler()
        a,o,c=scenario(module=runtime(compiler=compiler))
        a.act(o,c)
        o['step']=49
        p=a.parent.last_packet['projection'];p.update(observed_step=49,end_step=57,future_market={})
        self.assertEqual(a.act(o,c),a.parent.action)
        self.assertEqual(compiler.calls,['EGG','EGG'])
        self.assertEqual(a.offer_work['captured_windows'],1)
        self.assertEqual(a.last,{'reason':'market_context_unknown','item':'EGG'})
        self.assertIsNone(a.transformer.selector.active)

    def test_inputs_and_stream_order_are_unchanged(self):
        compiler=controlled_compiler()
        a,o,c=scenario([record('EGG'),record('MILK')],module=runtime(compiler=compiler))
        initial=copy.deepcopy((o,c,a.parent.action,a.parent.records,a.parent.last_packet))
        a.act(o,c)
        self.assertEqual((o,c,a.parent.action,a.parent.records,a.parent.last_packet),initial)
        self.assertEqual(a.transformer.tree['streams'],a.streams(a.parent.records[0][0],0))
        self.assertEqual(a.transformer.tree['plans'],a.parent.records[0][1])

    def test_parent_exception_restores_optimizer(self):
        a,o,c=scenario()
        error=TypeError('original parent body')
        a.parent.error=error
        original=sale.optimize_lot
        with self.assertRaises(TypeError) as seen:
            a.act(o,c)
        self.assertIs(seen.exception,error)
        self.assertIs(sale.optimize_lot,original)
        self.assertEqual(a.parent.calls,1)

    def test_missing_packet_never_compiles(self):
        compiler=controlled_compiler(fail_item='EGG')
        a,o,c=scenario(module=runtime(compiler=compiler));a.parent.last_packet=None
        self.assertEqual(a.act(o,c),a.parent.action)
        self.assertEqual(compiler.calls,[])

    def test_projection_error_never_compiles(self):
        compiler=controlled_compiler(fail_item='EGG')
        a,o,c=scenario(module=runtime(compiler=compiler))
        a.parent.last_packet['projection']['end_step']=999
        self.assertEqual(a.act(o,c),a.parent.action)
        self.assertEqual(compiler.calls,[])
        self.assertEqual(a.last,{'reason':'ValueError'})

    def test_full_slots_keep_no_admission_fallback(self):
        a,o,c=scenario(module=runtime(compiler=controlled_compiler()))
        c['maxMarketOrdersPerTurn']=1
        a.parent.action['market']=[['SELL','OTHER',1]]
        self.assertEqual(a.act(o,c),a.parent.action)
        self.assertIsNone(a.offer_work['admitted_index'])

    def test_prefix_mismatch_keeps_searching(self):
        compiler=controlled_compiler()
        a,o,c=scenario([record('EGG'),record('MILK')],module=runtime(compiler=compiler))
        a.parent.action['market']=[['SELL','EGG',1]]
        for orders in a.parent.last_packet['projection']['future_market'].values():
            orders.append([])
        a.act(o,c)
        self.assertEqual(compiler.calls,['EGG','MILK'])
        self.assertEqual(a.offer_work['admitted_index'],1)

    def test_successful_boundary_parity_all_modes_and_positions(self):
        for mode in ('adaptive','fixed','static'):
            for seat in (0,1):
                for active in (set(),{'EGG'},{'MILK'},{'WOOL'}):
                    with self.subTest(mode=mode,seat=seat,active=active):
                        m=runtime(compiler=controlled_compiler(active))
                        a,o,c=scenario([record(p) for p in ('EGG','MILK','WOOL')],module=m,mode=mode,seat=seat)
                        e,eo,ec=scenario(a.parent.records,module=SimpleNamespace(Agent=eager_type(m)),mode=mode,seat=seat)
                        self.assertEqual(observable(a,a.act(o,c)),observable(e,e.act(eo,ec)))

    def test_real_compiler_eager_and_lazy_match(self):
        for seat in (0,1):
            for mode in ('adaptive','fixed','static'):
                for inv in (0,40,200):
                    for quantity in (2,6):
                        with self.subTest(seat=seat,mode=mode,inv=inv,q=quantity):
                            m=runtime()
                            rows=[record(p,inventory=inv,quantity=quantity) for p in ('EGG','MILK','WOOL')]
                            a,o,c=scenario(rows,module=m,mode=mode,seat=seat)
                            e,eo,ec=scenario(rows,module=SimpleNamespace(Agent=eager_type(m)),mode=mode,seat=seat)
                            self.assertEqual(observable(a,a.act(o,c)),observable(e,e.act(eo,ec)))
                            self.assertLessEqual(a.counts['tables'],e.counts['tables'])

    def test_infeasible_first_window_keeps_searching(self):
        compiler=controlled_compiler()
        a,o,c=scenario([record('EGG'),record('MILK')],module=runtime(compiler=compiler))
        a.parent.last_packet['post_unit_observation']['private']['shed']['EGG']=0
        a.act(o,c)
        self.assertEqual(compiler.calls,['EGG','MILK'])
        self.assertEqual(a.offer_work['admitted_index'],1)

    def test_real_compiler_unused_malformed_plan_is_not_evaluated(self):
        rows=[record('EGG'),record('MILK')]
        rows[1][1][0]['sales'][0][1] += 1
        a,o,c=scenario(rows)
        a.act(o,c)
        self.assertEqual(a.last['reason'],'admitted')
        self.assertEqual(a.offer_work['compiled_windows'],1)
        self.assertEqual(a.transformer.counts['projection_fallbacks'],0)

    def test_real_compiler_reached_malformed_plan_keeps_fallback(self):
        rows=[record('EGG')]
        rows[0][1][0]['sales'][0][1] += 1
        a,o,c=scenario(rows)
        self.assertEqual(a.act(o,c),a.parent.action)
        self.assertEqual(a.last,{'reason':'ValueError'})
        self.assertEqual(a.offer_work['compiled_windows'],0)

    def test_admitted_index_retained_when_continuation_raises(self):
        a,o,c=scenario(module=runtime(compiler=controlled_compiler()))
        with patch.object(a.transformer.continuation,'transform',side_effect=TypeError('fixture')):
            self.assertEqual(a.act(o,c),a.parent.action)
        self.assertEqual(a.last,{'reason':'TypeError'})
        self.assertEqual(a.offer_work['admitted_index'],0)
        self.assertEqual(a.transformer.counts['admissions'],1)

    def test_real_branch_and_completion_match_eager(self):
        for mode in ('adaptive','fixed','static'):
            m=runtime()
            a,o,c=scenario([record('EGG'),record('MILK')],module=m,mode=mode)
            e,eo,ec=scenario(a.parent.records,module=SimpleNamespace(Agent=eager_type(m)),mode=mode)
            self.assertEqual(observable(a,a.act(o,c)),observable(e,e.act(eo,ec)))
            observed=int(next(iter(a.transformer.tree['groups'])))
            a.parent.records=[]; e.parent.records=[]
            for now in (41,48,49):
                for actor, obs in ((a,o),(e,eo)):
                    obs['step']=now
                    obs['market']['inventory']['EGG']=observed
                    projection=actor.parent.last_packet['projection']
                    projection.update(observed_step=now,end_step=max(now,48))
                self.assertEqual(observable(a,a.act(o,c)),observable(e,e.act(eo,ec)))
                self.assertEqual(a.offer_work['compiled_windows'],0)

    def test_generator_does_no_work_before_consumption(self):
        a,o,c=scenario(module=runtime(compiler=controlled_compiler()))
        a.records=copy.deepcopy(a.parent.records)
        offers=a._offers(c,a.parent.action)
        self.assertTrue(inspect.isgenerator(offers))
        self.assertEqual(a.counts['tables'],0)
        self.assertEqual(a.offer_work['inspected_windows'],0)
        next(offers)
        self.assertEqual(a.counts['tables'],1)


if __name__=='__main__':
    unittest.main(verbosity=2)
