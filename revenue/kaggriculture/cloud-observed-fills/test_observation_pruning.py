# SPDX-License-Identifier: Apache-2.0
"""Observation-constrained fill search: real modules, bounded exhaustive oracle.

No game policy runs or new benchmark seeds. The independent oracle enumerates
own-stock paths with unknown purchase affordability; native cases additionally
execute the pinned official market and compare an uninstrumented control.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import random
import statistics
import sys
import time
import unittest

HERE = Path(__file__).resolve().parent
OLD = NEW = ENGINE = LOADER = None
REPORT = {'full_games': 0, 'property_cases': 0, 'oracle_cases': 0,
          'native_cases': [], 'witnesses': {}}
ENGINE_HASHES = {
    'kaggriculture.py': 'bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e',
    'kaggriculture.json': 'a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867',
    'utils.py': '537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b',
}
WORK_FIELDS = {'peak_states', 'transitions'}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def identity(path):
    data = Path(path).read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'git_blob': hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()}


def action(orders):
    return {'farmer': ['PASS'], 'hands': [], 'market': deepcopy(orders)}


def inputs(before, orders, after, capacity=100, deposits=(), slots=10):
    return dict(post_unit_shed=before, submitted_action=action(orders), next_shed=after,
                configuration={'shedCapacity': capacity, 'maxMarketOrdersPerTurn': slots},
                after_market_deposits=deposits)


def semantic(result):
    return {k: v for k, v in result.items() if k not in WORK_FIELDS}


def compare(case):
    # These small cases cannot exhaust either enlarged bound.
    old = OLD.reconcile_shed_fills(**case, max_states=100_000, max_transitions=1_000_000)
    new = NEW.reconcile_shed_fills(**case, max_states=100_000, max_transitions=1_000_000)
    if old['reason'].endswith('budget_exceeded') or new['reason'].endswith('budget_exceeded'):
        raise AssertionError('Unfinished reference comparison')
    if semantic(old) != semantic(new):
        raise AssertionError(json.dumps({'input': case, 'old': old, 'new': new}, sort_keys=True))
    return old, new


def independent_paths(before, orders, after, capacity, deposits=(), slots=10):
    """Separate path enumeration for valid small queues; no production helpers."""
    paths = [(dict(before), [])]
    for index, order in enumerate(orders):
        next_paths = []
        for stock, counts in paths:
            op, item, request = order
            choices = [0]
            if index < max(1, slots):
                if op == 'SELL':
                    choices = [min(request, stock.get(item, 0), 99999)]
                elif op in ('BUY_PRODUCT', 'BUY_ANIMAL'):
                    choices = range(min(request, max(0, capacity-sum(stock.values())), 99999)+1)
            for quantity in choices:
                new_stock = dict(stock)
                new_stock[item] = stock.get(item, 0) + (-quantity if op == 'SELL' else quantity)
                next_paths.append((new_stock, counts+[quantity]))
        paths = next_paths
    matched = []
    for stock, counts in paths:
        final = dict(stock)
        for deposit in deposits:
            for item, request in deposit.items():
                quantity = min(request, max(0, capacity-sum(final.values())))
                final[item] = final.get(item, 0)+quantity
        keys = set(final) | set(after)
        if all(final.get(k, 0) == after.get(k, 0) for k in keys):
            matched.append(counts)
    return None if not matched else [(min(p[i] for p in matched), max(p[i] for p in matched))
                                     for i in range(len(orders))]


class PruningTests(unittest.TestCase):
    def test_two_large_terminal_buys_fit_tiny_work_budget(self):
        case = inputs({}, [['BUY_PRODUCT','WHEAT',100],['BUY_PRODUCT','FERTILIZER',100]],
                      {'WHEAT':40,'FERTILIZER':60})
        old = OLD.reconcile_shed_fills(**case)
        new = NEW.reconcile_shed_fills(**case, max_states=1, max_transitions=2)
        self.assertEqual(old['reason'], 'state_budget_exceeded')
        self.assertEqual(new['status'], 'reconciled')
        self.assertEqual([(r['fill_min'],r['fill_max']) for r in new['orders']], [(40,40),(60,60)])
        self.assertEqual(new['transitions'], 2)
        self.assertIsNone(new['cash_receipts'])
        reference, _ = compare(case)
        self.assertEqual(semantic(reference), semantic(new))
        REPORT['witnesses']['independent_terminal_buys'] = dict(input=case, default_old=old,
                                                             bounded_new=new, complete_reference=reference)

    def test_terminal_zero_buy_no_state_expansion(self):
        case = inputs({}, [['BUY_PRODUCT','WHEAT',100]], {})
        new = NEW.reconcile_shed_fills(**case,max_states=1,max_transitions=1)
        self.assertEqual(new['status'], 'reconciled')
        self.assertEqual(new['orders'][0]['fill_max'], 0)
        self.assertEqual(new['peak_states'], 1)

    def test_capacity_limit_not_overridden_by_observation(self):
        for after in ({'WHEAT':2,'FERTILIZER':2}, {'WHEAT':4}, {'WHEAT':1}):
            case=inputs({'EGG':2},[['BUY_PRODUCT','WHEAT',2],['BUY_PRODUCT','FERTILIZER',2]],after,capacity=3)
            _, new=compare(case)
            self.assertEqual(new['status'],'unknown')

    def test_final_buys_cannot_overfill_shared_capacity(self):
        _, new=compare(inputs({},[['BUY_PRODUCT','WHEAT',2],['BUY_PRODUCT','FERTILIZER',2]],
                             {'WHEAT':2,'FERTILIZER':2},capacity=3))
        self.assertEqual(new['status'],'unknown')

    def test_request_ceiling_not_overridden(self):
        _, new=compare(inputs({},[['BUY_PRODUCT','WHEAT',1]],{'WHEAT':2}))
        self.assertEqual(new['reason'],'observed_shed_not_explained')

    def test_negative_required_fill_is_not_admitted(self):
        _, new=compare(inputs({'WHEAT':2},[['BUY_PRODUCT','WHEAT',1]],{'WHEAT':1}))
        self.assertEqual(new['status'],'unknown')

    def test_duplicate_buys_keep_correlated_slot_ambiguity(self):
        _, new=compare(inputs({},[['BUY_PRODUCT','WHEAT',2],['BUY_PRODUCT','WHEAT',2]],{'WHEAT':2},capacity=4))
        self.assertEqual(new['status'],'ambiguous')
        self.assertEqual([(r['fill_min'],r['fill_max']) for r in new['orders']],[(0,2),(0,2)])

    def test_buy_sell_roundtrip_remains_unknown_fill(self):
        _, new=compare(inputs({},[['BUY_PRODUCT','WHEAT',2],['SELL','WHEAT',2]],{},capacity=3))
        self.assertEqual(new['status'],'ambiguous')
        self.assertIsNone(NEW.full_sale_verdict(new,1,2))

    def test_later_buy_not_earlier_buy_is_fixed(self):
        _, new=compare(inputs({},[['BUY_PRODUCT','WHEAT',2],['SELL','WHEAT',2],['BUY_PRODUCT','WHEAT',1]],
                             {'WHEAT':1},capacity=3))
        self.assertEqual([(r['fill_min'],r['fill_max']) for r in new['orders']],[(0,2),(0,2),(1,1)])

    def test_positive_same_product_deposit_disables_pruning(self):
        _, new=compare(inputs({},[['BUY_PRODUCT','WHEAT',2]],{'WHEAT':2},capacity=2,deposits=[{'WHEAT':2}]))
        self.assertEqual(new['status'],'ambiguous')
        self.assertEqual((new['orders'][0]['fill_min'],new['orders'][0]['fill_max']),(0,2))

    def test_zero_same_product_deposit_does_not_hide_fill(self):
        case=inputs({},[['BUY_PRODUCT','WHEAT',100]],{'WHEAT':40},deposits=[{'WHEAT':0}])
        new=NEW.reconcile_shed_fills(**case,max_states=1,max_transitions=1)
        self.assertEqual(new['status'],'reconciled')
        self.assertEqual(new['orders'][0]['fill_min'],40)

    def test_other_product_deposit_preserves_ordered_clipping(self):
        for deposits in ([{'EGG':2},{'MILK':2}],[{'MILK':2},{'EGG':2}]):
            after={'WHEAT':2, next(iter(deposits[0])):1}
            _, new=compare(inputs({},[['BUY_PRODUCT','WHEAT',3]],after,capacity=3,deposits=deposits))
            self.assertEqual(new['orders'][0]['fill_min'],2)

    def test_truncated_later_order_does_not_prevent_pruning(self):
        case=inputs({},[['BUY_PRODUCT','WHEAT',100],['SELL','WHEAT',100]],{'WHEAT':40},slots=1)
        new=NEW.reconcile_shed_fills(**case,max_states=1,max_transitions=1)
        self.assertEqual(new['status'],'reconciled')
        self.assertEqual([r['fill_min'] for r in new['orders']],[40,0])

    def test_malformed_later_order_does_not_change_last_update(self):
        for bad in ([],['SELL','WHEAT',0],['SELL','WHEAT','bad'],None,['SELL','INVALID',20]):
            case=inputs({},[['BUY_PRODUCT','WHEAT',100],bad],{'WHEAT':40})
            new=NEW.reconcile_shed_fills(**case,max_states=1,max_transitions=1)
            self.assertEqual(new['status'],'reconciled')
            self.assertEqual(new['orders'][0]['fill_min'],40)

    def test_seed_and_atomic_orders_are_not_shed_fill_evidence(self):
        _, new=compare(inputs({},[['BUY_PRODUCT','WHEAT',2],['BUY_SEED','WHEAT',100],['HIRE'],['BUY_LAND']],
                             {'WHEAT':1}))
        self.assertEqual(new['orders'][0]['fill_min'],1)
        self.assertTrue(all(r['fill_min'] is None for r in new['orders'][1:]))

    def test_animal_purchase_uses_same_exact_final_quantity(self):
        case=inputs({},[['BUY_ANIMAL','COW',100],['BUY_ANIMAL','SHEEP',100]],{'COW':40,'SHEEP':60})
        new=NEW.reconcile_shed_fills(**case,max_states=1,max_transitions=2)
        self.assertEqual(new['status'],'reconciled')
        self.assertEqual([r['fill_min'] for r in new['orders']],[40,60])

    def test_iteration_limit_still_applies_to_buys(self):
        case=inputs({},[['BUY_PRODUCT','WHEAT',100001]],{'WHEAT':100000},capacity=200000)
        new=NEW.reconcile_shed_fills(**case,max_states=1,max_transitions=1)
        self.assertEqual(new['reason'],'observed_shed_not_explained')

    def test_real_ambiguity_still_exhausts_budgets(self):
        case=inputs({},[['BUY_PRODUCT','WHEAT',100],['SELL','WHEAT',100]],{})
        for module in (OLD,NEW):
            self.assertEqual(module.reconcile_shed_fills(**case,max_states=2)['reason'],'state_budget_exceeded')
            self.assertEqual(module.reconcile_shed_fills(**case,max_transitions=2)['reason'],'transition_budget_exceeded')

    def test_sell_only_results_and_work_are_identical(self):
        for before,orders,after in [({'EGG':4},[['SELL','EGG',2]],{'EGG':2}),
                                   ({'EGG':4},[['SELL','EGG',3],['SELL','EGG',3]],{}),
                                   ({'STRAWBERRY':3},[['SELL','STRAWBERRY',3]],{})]:
            case=inputs(before,orders,after)
            self.assertEqual(OLD.reconcile_shed_fills(**case),NEW.reconcile_shed_fills(**case))

    def test_unknown_deposits_and_invalid_input_are_unchanged(self):
        for case in (inputs({},[['BUY_PRODUCT','WHEAT',2]],{},deposits=None),
                     inputs({'WHEAT':-1},[],{}),inputs({},[],{},capacity=-1)):
            self.assertEqual(OLD.reconcile_shed_fills(**case),NEW.reconcile_shed_fills(**case))

    def test_inputs_are_not_mutated(self):
        case=inputs({'EGG':2},[['SELL','EGG',1],['BUY_PRODUCT','WHEAT',2]],{'EGG':1,'WHEAT':1})
        original=deepcopy(case); compare(case)
        self.assertEqual(case,original)

    def test_stateful_ledger_consumes_new_coverage_both_seats(self):
        for seat in (0,1):
            before={'step':17,'day':0,'hour':17,'player':seat,'private':{'shed':{}}}
            after=deepcopy(before);after.update(step=18,hour=18)
            after['private']['shed']={'WHEAT':40,'FERTILIZER':60}
            ledger=NEW.ObservedFillLedger(max_states=1,max_transitions=2)
            binding=ledger.record(before,{},action([['BUY_PRODUCT','WHEAT',100],['BUY_PRODUCT','FERTILIZER',100]]),post_unit_shed={})
            self.assertEqual(ledger.observe(before)['status'],'pending')
            result=ledger.observe(after)
            self.assertEqual(result['status'],'reconciled')
            self.assertEqual(result['binding']['action_sha256'],binding['action_sha256'])
            self.assertEqual(ledger.observe(after)['reason'],'no_pending_action')

    def test_exhaustive_small_independent_oracle(self):
        menu=[['BUY_PRODUCT','WHEAT',2],['BUY_PRODUCT','FERTILIZER',2],['SELL','WHEAT',1],['BUY_ANIMAL','COW',1]]
        count=0
        for cap in (1,2,3):
            for seq in itertools.product(menu,repeat=3):
                for w,f,c in itertools.product(range(cap+1),repeat=3):
                    if w+f+c>cap:continue
                    after={'WHEAT':w,'FERTILIZER':f,'COW':c}
                    case=inputs({},list(seq),after,capacity=cap)
                    _,new=compare(case)
                    oracle=independent_paths({},list(seq),after,cap)
                    if oracle is None:self.assertEqual(new['status'],'unknown')
                    else:self.assertEqual([(r['fill_min'],r['fill_max']) for r in new['orders']],oracle)
                    count+=1
        REPORT['oracle_cases']=count

    def test_deterministic_mixed_queue_property_panel(self):
        rng=random.Random(9974);count=0
        menu=[['BUY_PRODUCT','WHEAT',1],['BUY_PRODUCT','WHEAT',3],['BUY_PRODUCT','FERTILIZER',2],
              ['BUY_ANIMAL','COW',2],['SELL','WHEAT',2],['SELL','FERTILIZER',3],['SELL','EGG',2],
              ['BUY_SEED','WHEAT',2],['HIRE'],['BUY_LAND'],[],['SELL','WHEAT',0],None,['PASS']]
        for _ in range(6000):
            cap=rng.randrange(1,7);before={};left=cap
            for p in ('WHEAT','FERTILIZER','EGG','COW'):
                before[p]=rng.randrange(left+1);left-=before[p]
            orders=deepcopy([rng.choice(menu) for _ in range(rng.randrange(1,7))])
            slots=rng.randrange(1,7)
            deposits=[] if rng.randrange(3)==0 else [{rng.choice(('WHEAT','FERTILIZER','EGG')):rng.randrange(4)} for _ in range(rng.randrange(3))]
            # Independent relaxed transition to generate many compatible targets.
            after=dict(before)
            for order in orders[:slots]:
                if not order or len(order)<3:continue
                op,p,q=order
                if op=='SELL':after[p]=max(0,after.get(p,0)-q)
                elif op in ('BUY_PRODUCT','BUY_ANIMAL'):
                    after[p]=after.get(p,0)+rng.randrange(min(q,max(0,cap-sum(after.values())))+1)
            for dep in deposits:
                for p,q in dep.items():after[p]=after.get(p,0)+min(q,max(0,cap-sum(after.values())))
            if rng.randrange(4)==0:after['WHEAT']=after.get('WHEAT',0)+1
            compare(inputs(before,orders,after,capacity=cap,deposits=deposits,slots=slots));count+=1
        REPORT['property_cases']=count


class NativeChecks(unittest.TestCase):
    def case(self,seat,orders,before,*,rival_orders=(),money=1000,cap=100,deposits=(),slots=10):
        e,S=ENGINE,LOADER.Struct
        farms=[e._new_farm(10,money) for _ in (0,1)]
        private=[e._new_private() for _ in (0,1)]
        private[seat]['shed'].update(before)
        private[1-seat]['shed'].update({'WHEAT':3,'FERTILIZER':3})
        private[seat]['inventories']=deepcopy(list(deposits)) or [{}]
        market=e._new_market()
        state=[S(observation=S(player=i,farms=farms,private=private[i],market=market,town=e._new_town(),day=0,hour=17,step=17),
                 action=action(orders if i==seat else rival_orders),status='ACTIVE',reward=0) for i in (0,1)]
        cfg=S(boardSize=10,shedCapacity=cap,maxMarketOrdersPerTurn=slots,farmHandCostMult=1)
        env=S(configuration=cfg,done=False,info={})
        control=deepcopy(state);e._process_market(control,env)
        positions={id(o):i for i,o in enumerate(state[seat].action['market'])}
        counts=[0]*len(orders);current=[None]
        parse0,commit0=e._parse_order,e._commit_unit
        def parse(order):
            if id(order) in positions:current[0]=positions[id(order)]
            return parse0(order)
        def commit(op,item,price,farm,priv,shared,shed_capacity=100):
            ok=commit0(op,item,price,farm,priv,shared,shed_capacity)
            if ok and farm is farms[seat]:counts[current[0]]+=1
            return ok
        e._parse_order,e._commit_unit=parse,commit
        try:e._process_market(state,env)
        finally:e._parse_order,e._commit_unit=parse0,commit0
        self.assertEqual(state,control)
        if deposits:e._drop_inventories_to_shed(private[seat],cap)
        case=inputs(before,orders,private[seat]['shed'],capacity=cap,deposits=deposits,slots=slots)
        old,new=compare(case)
        self.assertIn(new['status'],('reconciled','ambiguous'))
        for row,actual in zip(new['orders'],counts):
            if row['fill_min'] is not None:self.assertLessEqual(row['fill_min'],actual);self.assertGreaterEqual(row['fill_max'],actual)
        REPORT['native_cases'].append(dict(seat=seat,input=case,money=money,rival_orders=rival_orders,
            actual_fills=counts,result=new,reference_work={k:old.get(k) for k in WORK_FIELDS},
            traced_matches_uninstrumented=True))
        return case,new

    def test_paired_market_cash_and_capacity_cases(self):
        for seat,money,cap,rival in itertools.product((0,1),(0,25,1000,100000),(1,3,100),
                ([],[['BUY_PRODUCT','WHEAT',3]],[['SELL','WHEAT',3]])):
            self.case(seat,[['BUY_PRODUCT','WHEAT',3],['BUY_PRODUCT','FERTILIZER',3]],{},
                      rival_orders=rival,money=money,cap=cap)

    def test_native_large_lots_have_new_bounded_coverage(self):
        for seat in (0,1):
            case,new=self.case(seat,[['BUY_PRODUCT','WHEAT',100],['BUY_PRODUCT','FERTILIZER',100]],{},money=100000)
            bounded=NEW.reconcile_shed_fills(**case,max_states=1,max_transitions=2)
            self.assertEqual(semantic(new),semantic(bounded))
            self.assertEqual(bounded['status'],'reconciled')
            REPORT['witnesses']['native_large_lots_seat'+str(seat)]=dict(input=case,result=bounded,
                         old_default=OLD.reconcile_shed_fills(**case))

    def test_native_duplicate_and_sale_funded_queues(self):
        queues=[ [['BUY_PRODUCT','WHEAT',2],['SELL','WHEAT',2],['BUY_PRODUCT','WHEAT',1]],
                 [['BUY_PRODUCT','WHEAT',2],['BUY_PRODUCT','WHEAT',2]],
                 [['SELL','EGG',3],['BUY_ANIMAL','COW',1],['BUY_PRODUCT','WHEAT',3]],
                 [['HIRE'],['BUY_SEED','CARROT',2],['BUY_PRODUCT','FERTILIZER',3]]]
        for seat,queue,money in itertools.product((0,1),queues,(0,1000)):
            self.case(seat,queue,{'EGG':3},money=money)

    def test_native_eod_and_truncated_cases(self):
        for seat,deposits,slots in itertools.product((0,1),([{'WHEAT':3}],[{'EGG':3}]),(1,2)):
            self.case(seat,[['BUY_PRODUCT','WHEAT',3],['SELL','WHEAT',3]],{},
                      money=1000,cap=3,deposits=deposits,slots=slots)


def benchmark(rounds=9):
    workloads={
        'terminal_two_buys':(inputs({},[['BUY_PRODUCT','WHEAT',100],['BUY_PRODUCT','FERTILIZER',100]],{'WHEAT':40,'FERTILIZER':60}),20),
        'terminal_small_buy':(inputs({'EGG':4},[['BUY_PRODUCT','WHEAT',3]],{'EGG':4,'WHEAT':1}),1000),
        'sell_only':(inputs({'EGG':4,'MILK':3},[['SELL','EGG',3],['SELL','MILK',2]],{'EGG':1,'MILK':1}),1000),
        'roundtrip':(inputs({},[['BUY_PRODUCT','WHEAT',8],['SELL','WHEAT',8]],{}),300),
        'deposit_ambiguity':(inputs({},[['BUY_PRODUCT','WHEAT',8]],{'WHEAT':8},capacity=8,deposits=[{'WHEAT':8}]),300),
    }
    out={}
    for name,(case,repeat) in workloads.items():
        samples={'original':[],'candidate':[]}
        for r in range(rounds):
            for label,module in ([('original',OLD),('candidate',NEW)] if r%2==0 else [('candidate',NEW),('original',OLD)]):
                start=time.perf_counter_ns()
                for _ in range(repeat):module.reconcile_shed_fills(**case)
                samples[label].append((time.perf_counter_ns()-start)/repeat/1000)
        med={k:statistics.median(v) for k,v in samples.items()}
        out[name]={'microseconds_per_call':samples,'medians':med,'ratio_original_over_candidate':med['original']/med['candidate'],
                   'calls_per_round':repeat,'original_result':OLD.reconcile_shed_fills(**case),
                   'candidate_result':NEW.reconcile_shed_fills(**case)}
    return out


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--candidate',type=Path,default=HERE/'observed_fills.py')
    p.add_argument('--engine-loader',type=Path,required=True)
    p.add_argument('--engine-cache',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--benchmark',action='store_true')
    args=p.parse_args()
    if identity(args.baseline)['git_blob']!='cabe10ad3d683351077c9597ad7bb36cb58ce9c6':
        raise SystemExit('Baseline must be the original pinned reconciler')
    hashes={n:identity(args.engine_cache/n)['sha256'] for n in ENGINE_HASHES}
    if hashes!=ENGINE_HASHES:raise SystemExit('Engine cache differs from pinned source')
    global OLD,NEW,ENGINE,LOADER
    OLD=load('pruning_original',args.baseline);NEW=load('pruning_candidate',args.candidate)
    LOADER=load('pruning_engine_loader',args.engine_loader);ENGINE,actual=LOADER.get_engine(args.engine_cache)
    if actual!=ENGINE_HASHES:raise SystemExit('Loader engine mismatch')
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    REPORT.update(tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
                  success=result.wasSuccessful(),engine_sha256=hashes,source={
                      'baseline':identity(args.baseline),'candidate':identity(args.candidate),
                      'test':identity(__file__),'loader':identity(args.engine_loader)},
                  independent_reference_market_calls=len(REPORT['native_cases']))
    if args.benchmark and result.wasSuccessful():REPORT['benchmarks']=benchmark()
    args.report.write_text(json.dumps(REPORT,indent=2)+'\n',encoding='utf-8')
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
