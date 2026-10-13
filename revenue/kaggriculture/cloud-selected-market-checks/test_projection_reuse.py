# SPDX-License-Identifier: Apache-2.0
"""Exact-source projection parity; no games, hidden seeds, or new policy runner."""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
REF=HERE/'fixtures/integrated_projection_0336228e.py'
REF_SHA='908b8cae58686b3e16cb10ffb939ec6e86cce8a2cb0720efd12d25fbdabe6017'
OLD=NEW=ENGINE=None
COUNTS={'projection_comparisons':0,'exceptions_compared':0,'copy_witness':{}}

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    spec.loader.exec_module(module);return module

def setup(runtime,evaluator,engine_cache,engine_loader):
    global OLD,NEW,ENGINE
    sys.path.insert(0,str(runtime.resolve()))
    NEW=load(runtime/'integrated_selected.py','projection_reuse_new')
    OLD=load(runtime/'integrated_selected.py','projection_reuse_old')
    if sha(REF)!=REF_SHA: raise ValueError('Retained projection reference changed')
    exec(compile(REF.read_text(),str(REF),'exec'),OLD.__dict__)
    OLD.IntegratedSelectedAgent=type('OriginalProjection',(OLD.IntegratedSelectedAgent,),{'_projection':OLD._projection})
    ev=load(evaluator,'projection_reuse_evaluator')
    kwargs={'prepare':False}
    if engine_loader:kwargs['loader']=engine_loader
    ENGINE,hashes=ev.get_engine(engine_cache,**kwargs)
    return hashes

def action(farmer=None,hands=None,market=None):
    return {'farmer':farmer or ['PASS'],'hands':hands or [],'market':market or []}

def fixture(now=10,horizon=8):
    farm=ENGINE._new_farm(10,10000);private=ENGINE._new_private()
    route=[action() for _ in range(720)]
    obs={'step':now,'player':0,'day':now//24,'hour':now%24}
    return {'obs':obs,'cfg':{},'selected':action(),'farm':farm,'private':private,
            'plans':{},'route':route,'switches':[],'horizon':horizon,'max_steps':20}

def capture(module,values,callback=None):
    data=copy.deepcopy(values)
    actor=object.__new__(module.IntegratedSelectedAgent)
    actor.controller=SimpleNamespace(R=[data['route']],cur=0)
    actor.execution=SimpleNamespace(seller=SimpleNamespace(horizon=data['horizon']))
    actor.production=SimpleNamespace(A=SimpleNamespace(DECISIONS=data['switches']),max_steps=data['max_steps'],
        _next_op=callback or (lambda plan,pos,inv,board: copy.deepcopy(plan.get('op'))))
    try:
        result=('return',actor._projection(data['obs'],data['cfg'],data['selected'],data['farm'],data['private'],data['plans']))
    except Exception as exc:
        result=('raise',type(exc).__name__,str(exc))
    return result,{k:data[k] for k in ('obs','cfg','selected','farm','private','plans','route')}

def compare(test,values,callback=None):
    a=capture(OLD,values,callback);b=capture(NEW,values,callback)
    test.assertEqual(a,b)
    COUNTS['projection_comparisons']+=1
    COUNTS['exceptions_compared']+=int(a[0][0]=='raise')
    return b


class ProjectionReuseTests(unittest.TestCase):
    def test_reference_integrity(self): self.assertEqual(sha(REF),REF_SHA)

    def test_nominal_date_horizon_and_market_lattice(self):
        for now,horizon,queue in itertools.product((0,10,17,22,23,24,667,717,718),(0,1,4,8),
                ([],[['BUY_SEED','WHEAT',2]],[['HIRE']],[['SELL','WHEAT',2]])):
            f=fixture(now,horizon);f['selected']['market']=copy.deepcopy(queue)
            f['private']['shed']['WHEAT']=5
            f['private']['inventories'][0]['MILK']=3
            compare(self,f)

    def test_current_market_caller_mutation_boundary(self):
        f=fixture();f['selected']['market']=[['BUY_SEED','WHEAT',1]]
        f['route'][11]['market']=[['BUY_SEED','WHEAT',2]]
        result,state=compare(self,f)
        self.assertEqual(result[0],'return')
        self.assertEqual(state['private']['seeds']['WHEAT'],1)
        self.assertEqual(result[1][0]['future_market'][11],[['BUY_SEED','WHEAT',2]])

    def test_one_detachment_instead_of_every_future_stage(self):
        f=fixture(now=10,horizon=8)
        values=[]
        for module in (OLD,NEW):
            counts={'farm':0,'private':0};original=module.deepcopy
            def observed(obj):
                if isinstance(obj,dict) and 'tiles' in obj:counts['farm']+=1
                if isinstance(obj,dict) and 'inventories' in obj:counts['private']+=1
                return original(obj)
            with patch.object(module,'deepcopy',observed):result=capture(module,f)
            self.assertEqual(result[0][0],'return');values.append(counts)
        self.assertEqual(values,[{'farm':8,'private':8},{'farm':1,'private':1}])
        COUNTS['copy_witness']={'reference':values[0],'candidate':values[1]}

    def test_route_and_purchase_boundaries_before_fork(self):
        for offset,kind in itertools.product((1,2,6),('switch','end','product')):
            f=fixture()
            if kind=='switch':f['switches']=[(10+offset,)]
            elif kind=='end':f['route']=f['route'][:10+offset]
            else:f['route'][10+offset]['market']=[['BUY_PRODUCT','WHEAT',1]]
            result,_=compare(self,f)
            self.assertEqual(result[1][0]['end_step'],9+offset)

    def test_no_future_stage_does_not_fork(self):
        for f in (fixture(718),fixture(10,0)):
            with patch.object(NEW,'deepcopy',wraps=NEW.deepcopy) as copied:
                result=capture(NEW,f)
            self.assertEqual(result[0][0],'return');self.assertEqual(copied.call_count,0)

    def test_early_and_late_missing_stock_keep_only_accepted_events(self):
        for offset in (1,2,6):
            f=fixture();f['route'][10+offset]['farmer']=['PICKUP','WHEAT',1]
            result,state=compare(self,f)
            self.assertEqual(result[0],'return')
            self.assertEqual(result[1][1]['end_reason'],'stock_dependent_pickup')
            self.assertEqual(result[1][0]['end_step'],9+offset)
            self.assertEqual(result[1][0]['stock_events'],[])

    def test_partial_failed_stage_does_not_publish_events(self):
        f=fixture();f['selected']['market']=[['HIRE']]
        f['private']['inventories'][0]['MILK']=4
        f['route'][12]=action(['DROP'],[['PICKUP','WHEAT',1]])
        result,state=compare(self,f)
        self.assertEqual(result[1][0]['end_step'],11)
        self.assertEqual(result[1][0]['stock_events'],[])
        self.assertEqual(state['private']['inventories'][0]['MILK'],4)

    def test_ordered_deposit_pickup_with_shared_shed(self):
        for reverse,capacity in itertools.product((False,True),(3,100)):
            f=fixture();f['cfg']['shedCapacity']=capacity;f['selected']['market']=[['HIRE']]
            f['private']['inventories'][0]['WHEAT']=4
            f['route'][11]=action(['DROP'],[['PICKUP','WHEAT',2]])
            if reverse:f['route'][11]=action(['PICKUP','WHEAT',2],[['DROP']])
            compare(self,f)

    def test_end_of_day_carry_records_preserved(self):
        f=fixture(now=20);f['private']['inventories'][0]['MILK']=7
        result,_=compare(self,f)
        self.assertEqual(result[1][0]['end_step'],23)
        rows=result[1][0]['stock_events']
        self.assertTrue(any(x['phase']=='after_market' and x['product']=='MILK' and x['quantity_delta']==7 for x in rows))

    def test_terminal_never_introduces_later_stage(self):
        f=fixture(now=718);f['private']['inventories'][0]['MILK']=7
        result,_=compare(self,f)
        self.assertEqual(result[1][0]['end_step'],718)
        self.assertEqual(result[1][0]['stock_events'],[])

    def test_committed_route_breaks_match(self):
        for mode in ('missing_worker','unit_conflict','max_steps','no_next_op'):
            f=fixture();worker=7 if mode=='missing_worker' else 0
            f['plans']={worker:{'steps':0,'op':['PASS']}}
            if mode=='unit_conflict':f['route'][11]['farmer']=['N']
            if mode=='max_steps':f['max_steps']=0
            if mode=='no_next_op':f['plans'][worker]['op']=None
            result,_=compare(self,f)
            self.assertEqual(result[1][1]['end_reason'],'committed_continuation_boundary')
            self.assertEqual(result[1][0]['end_step'],10)

    def test_committed_harvest_omission_and_plan_mutation(self):
        f=fixture();f['plans']={0:{'steps':0,'op':['HARVEST']}}
        f['private']['inventories'][0]['EGG']=2
        result,state=compare(self,f)
        self.assertEqual(state['plans'],{})
        self.assertEqual(result[1][1]['excluded_harvests'][0]['worker_index'],0)
        self.assertEqual(state['private']['inventories'][0]['EGG'],2)

    def test_invalid_selected_stage_exception_preserved(self):
        f=fixture();f['cfg']['turnsPerDay']=0
        result,_=compare(self,f)
        self.assertEqual(result[0],'raise');self.assertEqual(result[1],'ZeroDivisionError')

    def test_foreign_callback_exception_and_mutation_preserved(self):
        def failed(plan,pos,inv,board):
            plan['called']=True
            raise RuntimeError('callback fixture')
        f=fixture();f['plans']={0:{'steps':0,'op':['PASS']}}
        result,state=compare(self,f,failed)
        self.assertEqual(result,('raise','RuntimeError','callback fixture'))
        self.assertTrue(state['plans'][0]['called'])

    def test_no_cross_call_simulation_state(self):
        f=fixture();f['private']['shed']['WHEAT']=3
        f['route'][11]['farmer']=['PICKUP','WHEAT',1]
        first=compare(self,f)
        for q in (0,4,3):
            f['private']['shed']['WHEAT']=q;compare(self,f)
        self.assertEqual(first,capture(NEW,f))

    def test_output_is_detached_from_route_and_observation(self):
        f=fixture();result,state=compare(self,f)
        result[1][0]['future_market'][11].append(['HIRE'])
        result[1][0]['stock_events'].append({'detached':True})
        self.assertEqual(state['route'][11]['market'],[])
        self.assertEqual(f['route'][11]['market'],[])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime',type=Path,required=True);p.add_argument('--evaluator',type=Path,required=True)
    p.add_argument('--engine-cache',type=Path,required=True);p.add_argument('--engine-loader',type=Path)
    p.add_argument('--report',type=Path)
    a=p.parse_args();hashes=setup(a.runtime.resolve(),a.evaluator.resolve(),a.engine_cache.resolve(),a.engine_loader.resolve() if a.engine_loader else None)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ProjectionReuseTests))
    report={'test_methods':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
        'successful':result.wasSuccessful(),'counts':COUNTS,'engine_sha256':hashes,
        'runtime_sha256':sha(a.runtime/'integrated_selected.py'),'reference_sha256':sha(REF),
        'seller_sha256':sha(a.runtime/'selected_action_sell.py'),'core_sha256':sha(a.runtime/'selected_sell_core.py'),
        'scope':'exact-source deterministic projection comparisons; no full games or on-policy evidence','game_seeds':[]}
    if a.report:a.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report));return 0 if result.wasSuccessful() else 1

if __name__=='__main__':raise SystemExit(main())
