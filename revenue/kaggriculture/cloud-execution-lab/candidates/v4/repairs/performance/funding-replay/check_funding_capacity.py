# SPDX-License-Identifier: Apache-2.0
"""Offline, source-authenticated full-interpreter acceptance for CAPTRACE.

Constructed same-day worlds isolate capacity and funding-slot custody. They
are not a claim of arbitrary-market, town, dawn, or competitive-game parity.
"""
from __future__ import annotations
import argparse
import ast
import copy
import hashlib
import importlib.util
import io
import json
import random
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

import compose_funding_capacity as compose

SOURCE_SHA = 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'
UNIT_BLOB = 'e1127c4aad842278a9e617903b0718d21c00f348'
TOWN_BLOB = '527811763c80e627895d8e11319f8877b18105e6'
PERF_BLOB = 'd579759e8f6bd6c4649d58f220b1b193a9bda491'
COUNT = {'initializations': 0, 'transitions': 0, 'trace_comparisons': 0,
         'minimum_comparisons': 0, 'audit_parity': 0}


def blob(data):
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def authenticate(runtime, unitpath, perfpath, townpath):
    source = (runtime/'SOURCE.json').read_bytes()
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA:
        raise ValueError('SOURCE manifest pin mismatch')
    manifest = json.loads(source)
    if len(manifest['runtime']) != 109:
        raise ValueError('incomplete manifest')
    for name, meta in manifest['runtime'].items():
        data = (runtime/name).read_bytes()
        if len(data) != meta['bytes'] or hashlib.sha256(data).hexdigest() != meta['sha256']:
            raise ValueError('runtime pin mismatch: '+name)
    for path, expected in [(unitpath, UNIT_BLOB), (perfpath, PERF_BLOB), (townpath, TOWN_BLOB)]:
        if blob(path.read_bytes()) != expected:
            raise ValueError('peer source pin mismatch: '+str(path))
    return manifest


class Harness:
    def __init__(self, runtime, unitpath, perfpath, townpath):
        self.runtime = runtime
        self.manifest = authenticate(runtime, unitpath, perfpath, townpath)
        sys.path.insert(0, str(runtime))
        self.unit = load(unitpath, '_captrace_peer_unit')
        self.perf = load(perfpath, '_captrace_peer_perf')
        self.town = load(townpath, '_captrace_peer_town')
        self.loader = load(runtime/'checks/reference/evaluator/loader.py', '_captrace_loader')
        self.engine, self.engine_hashes = self.loader.get_engine(runtime/'checks/reference/engine')
        self.base = __import__('frozen_selected')
        s = (runtime/'scheduler.py').read_text()
        f = (runtime/'frozen_selected.py').read_text()
        self.sources = {}; self.predecessors = {}; self.models = {}
        for town in [False, True]:
            for unit in [False, True]:
                tf = self.town.apply(f) if town else f
                sc, fr = self.unit.compose_sources(s, tf) if unit else (s, tf)
                for perf in [False, True]:
                    label = ('town-' if town else '') + f'unit{int(unit)}-perf{int(perf)}'
                    before = self.perf.apply(fr) if perf else fr
                    after = compose.apply(before)
                    self.sources[label] = (sc, after)
                    self.predecessors[label] = before
                    self.models[label] = self.model(after, unit)
        self.primary = self.models['town-unit1-perf1']

    def model(self, source, unit=True):
        # Execute the actual complete native module, not a reimplementation of
        # either changed function. Unit helper is the exact peer's public helper.
        module = types.ModuleType('_captrace_candidate')
        module.__file__ = str(self.runtime/'frozen_selected.py')
        exec(compile(source, module.__file__, 'exec'), module.__dict__)
        if unit:
            exec(compile(self.unit.HELPER, 'exact_UNITFLOW_helper', 'exec'), module.__dict__)
        return module

    def world(self, seat=0, capacity=100, money=0, hands=0, milk=1, wheat=None, carry=None):
        e = self.engine; S = self.loader.Struct
        cfg = S({k: v.get('default') if isinstance(v,dict) else v
                 for k,v in e.specification['configuration'].items()})
        cfg.update(seed=17, shedCapacity=capacity, townShopSellInterval=99999,
                   townCenterSellInterval=99999, farmHandCostMult=1)
        env = S(configuration=cfg, done=False, info={})
        state = [S(observation=S(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
        e.interpreter(state, env); COUNT['initializations'] += 1
        for i, st in enumerate(state):
            st.observation.step = 5
            st.observation.market['inventory'] = {k:10000 for k in e.PRODUCTS}
            st.observation.market['params'] = None
            st.observation.town['unlocked_shops'] = []
            f = st.observation.farms[i]
            f.update(money=money if i==seat else 0, farmer=[4,4],
                     hires_today=hands if i==seat else 0,
                     hands=[[4,4] for _ in range(hands if i==seat else 0)],
                     tiles=[[None for _ in range(10)] for _ in range(10)])
            p = st.observation.private
            p['shed'] = {k:0 for k in e.PRODUCTS+list(e.ANIMALS)}
            p['seeds'] = {k:0 for k in e.CROPS}
            p['inventories'] = [{} for _ in range(len(f['hands'])+1)]
        own = state[seat].observation.private
        own['shed'].update(MILK=milk, WHEAT=max(0,capacity-milk) if wheat is None else wheat)
        if carry is not None:
            own['inventories'] = copy.deepcopy(carry)
        return {'seat':seat,'cfg':cfg,'env':env,'state':state,'now':5}

    def official(self, world, route, market, end, stress=0, audit=True):
        state, env = copy.deepcopy((world['state'], world['env']))
        seat, now = world['seat'], world['now']; e = self.engine; cap = env.configuration.maxMarketOrdersPerTurn
        if stress:
            items = {o[1] for t in range(now,end+1)
                     for o in (market if t==now else route[t].get('market',[]))[:cap]
                     if isinstance(o,list) and len(o)>2 and o[0]=='BUY_PRODUCT'}
            for item in items:
                state[0].observation.market['inventory'][item] -= stress
        farm = state[0].observation.farms[seat]
        recorded = {}; current = {'step':now,'slot':-1}
        oldparse, oldcommit, oldhire = e._parse_order, e._commit_unit, e._do_hire
        def parse(order):
            # Rival PASS has no market queue, so every parse is our next raw slot.
            current['slot'] += 1
            return oldparse(order)
        def commit(op,item,price,f,p,m,capacity=100):
            ok = oldcommit(op,item,price,f,p,m,capacity)
            if ok and f is farm:
                key=(current['step'],current['slot'],op,item)
                q,cash=recorded.get(key,(0,0));recorded[key]=(q+1,cash+price)
            return ok
        def hire(f,p,size,mult):
            before=len(f['hands']); oldhire(f,p,size,mult)
            if f is farm:
                recorded[(current['step'],current['slot'],'HIRE','')]=(len(f['hands'])-before,0)
        if audit:
            e._parse_order, e._commit_unit, e._do_hire = parse,commit,hire
        try:
            for t in range(now,end+1):
                current.update(step=t,slot=-1)
                for st in state:
                    st.observation.step=t;st.action={}
                state[seat].action={'market':copy.deepcopy(market)} if t==now else copy.deepcopy(route[t])
                e.interpreter(state,env);COUNT['transitions'] += 1
        finally:
            e._parse_order,e._commit_unit,e._do_hire=oldparse,oldcommit,oldhire
        acquisitions=[];sales=[]
        for t in range(now,end+1):
            orders=market if t==now else route[t].get('market',[])
            for index,o in enumerate(orders[:cap]):
                if not isinstance(o,list) or not o:continue
                op=o[0];item=o[1] if len(o)>1 else ''
                q,cash=recorded.get((t,index,op,item),(0,0))
                if op=='HIRE':acquisitions.append(((t,index,op,''),q))
                elif len(o)>2 and op in ('BUY_SEED','BUY_ANIMAL','BUY_PRODUCT'):
                    acquisitions.append(((t,index,op,item),q))
                elif len(o)>2 and op=='SELL' and t>now:
                    sales.append((t,index,item,q,cash))
        return {'cash':farm['money'],'acquisitions':acquisitions,'sale_receipts':sales,
                'executed_sales':[(t,item,q,c) for t,_,item,q,c in sales],
                'state':state,'env':env}

    def trace(self, model, w, route, market, end, stress=0):
        obs=w['state'][w['seat']].observation
        return model._funding_trace(obs,w['cfg'],obs.farms[w['seat']],obs.private,
                                    route,w['now'],end,market,stress)

    def minimum(self, model, w, route, market, end, baseline=1, stress=0):
        obs=w['state'][w['seat']].observation
        return model.funded_minimum_now(obs,w['cfg'],{'market':market},obs.farms[w['seat']],
                    obs.private,route,end,{'MILK':baseline},{'MILK':baseline},'MILK',stress)

    def oracle_minimum(self,w,route,market,end,baseline=1,stress=0):
        obs=w['state'][w['seat']].observation
        def orders(q):
            return self.base.materialize_sales(market,{'MILK':q},obs.private['shed'],{'MILK':baseline},w['cfg'].maxMarketOrdersPerTurn)
        ref=self.official(w,route,orders(baseline),end)
        boundary=next((r for r in ref['sale_receipts'] if r[4]>0),None)
        required={k:q for k,q in ref['acquisitions'] if q>0 and (boundary is None or k[:2]<boundary[:2])}
        for quantity in range(baseline+1):
            safe=True
            for draw in (0,stress):
                observed=self.official(w,route,orders(quantity),boundary[0] if boundary else end,draw)
                filled=dict(observed['acquisitions'])
                if any(filled.get(k,0)<q for k,q in required.items()):safe=False
                if boundary:
                    row=next((r for r in observed['sale_receipts'] if r[:3]==boundary[:3]),None)
                    if row is None or row[3]<boundary[3] or row[4]<boundary[4]:safe=False
            if safe:return quantity
        return baseline


H=None


class FundingCapacityTests(unittest.TestCase):
    def basic(self,seat=0):
        w=H.world(seat,carry=[{'EGG':2}]);r=[{} for _ in range(32)]
        r[6]={'farmer':['DROP'],'market':[['SELL','EGG',1]]};r[7]={'market':[['HIRE']]}
        return w,r,[['SELL','MILK',1]]

    def test_discarded_goods_are_not_cash(self):
        for seat in (0,1):
            w,r,_=self.basic(seat)
            actual=H.official(w,r,[],7)
            self.assertEqual(actual['cash'],0);self.assertEqual(actual['acquisitions'],[((7,0,'HIRE',''),0)])
            for model in H.models.values():
                tr=H.trace(model,w,r,[],7)
                for key in ('cash','acquisitions','executed_sales','sale_receipts'):
                    self.assertEqual(tr[key],actual[key])

    def test_minimum_retains_capacity_for_funding_sale(self):
        for seat in (0,1):
            w,r,m=self.basic(seat)
            self.assertEqual(H.minimum(H.base,w,r,m,7)[0],0)
            for model in H.models.values():
                minimum,cert=H.minimum(model,w,r,m,7)
                self.assertEqual(minimum,1);self.assertFalse(cert['fallback'])
                self.assertEqual(cert['funding_boundary'][:3],(6,0,'EGG'))

    def test_cap_only_is_not_the_full_fix(self):
        source=(H.runtime/'frozen_selected.py').read_text()
        pos=compose.spans(source)['_funding_trace'];part=source[slice(*pos)].replace('24, 10**6)','24, cap)')
        model=H.model(source[:pos[0]]+part+source[pos[1]:],False)
        w,r,m=self.basic()
        self.assertEqual(H.trace(model,w,r,[],7)['cash'],0)
        self.assertEqual(H.minimum(model,w,r,m,7)[0],0)
        self.assertEqual(H.minimum(H.primary,w,r,m,7)[0],1)

    def test_acquisition_before_same_turn_sale_needs_cash(self):
        for seat in (0,1):
            w=H.world(seat,milk=1,wheat=0);w['state'][seat].observation.private['shed']['EGG']=1
            r=[{} for _ in range(32)];r[6]={'market':[[],['HIRE'],[],['SELL','EGG',1]]}
            m=[['SELL','MILK',1]]
            self.assertEqual(H.minimum(H.base,w,r,m,6)[0],0)
            for model in H.models.values():
                minimum,cert=H.minimum(model,w,r,m,6)
                self.assertEqual(minimum,1);self.assertEqual(cert['reference_acquisitions'],1)
                self.assertEqual(cert['funding_boundary'][:3],(6,3,'EGG'))

    def test_acquisition_after_sale_not_overreserved(self):
        w=H.world(milk=1,wheat=0);w['state'][0].observation.private['shed']['EGG']=1
        r=[{} for _ in range(32)];r[6]={'market':[['SELL','EGG',1],['BUY_ANIMAL','COW',1]]}
        for model in H.models.values():
            self.assertEqual(H.minimum(model,w,r,[['SELL','MILK',1]],6)[0],0)

    def test_raw_slots_and_zero_fill_are_retained(self):
        w,r,m=self.basic();r[6]['market']=[[],['SELL','WOOL',1],['SELL','EGG',1],['SELL','EGG',5]]
        for model in H.models.values():
            tr=H.trace(model,w,r,m,7)
            self.assertEqual([row[:3] for row in tr['sale_receipts']],[(6,1,'WOOL'),(6,2,'EGG'),(6,3,'EGG')])
            self.assertEqual([row[3] for row in tr['sale_receipts']],[0,1,0])
            self.assertEqual(H.minimum(model,w,r,m,7)[1]['funding_boundary'][:3],(6,2,'EGG'))

    def test_unreachable_future_suffix_never_binds(self):
        w,r,m=self.basic();w['cfg'].maxMarketOrdersPerTurn=1;r[6]['market']+=[['BUY_PRODUCT','FERTILIZER','bad']]
        for model in H.models.values():
            self.assertEqual(H.minimum(model,w,r,m,7,stress=32)[0],1)

    def test_boundary_buy_stress_is_not_deduplicated(self):
        w=H.world(milk=1,wheat=0,money=H.engine.market_price('FERTILIZER',9999,None))
        w['state'][0].observation.private['shed']['EGG']=1
        r=[{} for _ in range(32)];r[6]={'market':[['BUY_PRODUCT','FERTILIZER',1],['SELL','EGG',1]]}
        m=[['SELL','MILK',1]]
        expected=H.oracle_minimum(w,r,m,6,stress=10000)
        self.assertEqual(expected,1)
        for model in H.models.values():
            self.assertEqual(H.minimum(model,w,r,m,6,stress=10000)[0],expected)

    def test_minimum_matches_independent_engine_matrix(self):
        for seat in (0,1):
            for capacity in (1,2,5,100):
                for carried in (0,1,3):
                    for before in (False,True):
                        w=H.world(seat,capacity=capacity,carry=[{'EGG':carried}])
                        r=[{} for _ in range(32)]
                        rows=[[],['SELL','EGG',2]]
                        if before:rows.insert(0,['HIRE'])
                        r[6]={'farmer':['DROP'],'market':rows};r[7]={'market':[['HIRE']]}
                        m=[['SELL','MILK',1]];expected=H.oracle_minimum(w,r,m,7)
                        for model in H.models.values():
                            self.assertEqual(H.minimum(model,w,r,m,7)[0],expected)
                            COUNT['minimum_comparisons']+=1

    def test_ordered_deposit_and_market_engine_matrix(self):
        rng=random.Random(207731)
        for case in range(160):
            cap=rng.choice((0,1,2,4,10,100));milk=rng.randrange(min(cap,4)+1)
            hands=rng.randrange(3);carry=[{k:rng.randrange(4) for k in rng.sample(['WHEAT','EGG','MILK'],3)} for _ in range(hands+1)]
            w=H.world(case%2,cap,money=rng.randrange(500),hands=hands,milk=milk,carry=carry)
            w['cfg'].maxMarketOrdersPerTurn=rng.choice((1,3,10))
            r=[{} for _ in range(32)]
            def command():return rng.choice([['DROP'],['PLACE','EGG',2],['PICKUP','WHEAT',1],['PASS']])
            for t in range(6,10):
                r[t]={'farmer':command(),'hands':[command() for _ in range(hands)],
                      'market':[rng.choice([[],['SELL','EGG',2],['SELL','MILK',1],['HIRE'],['BUY_SEED','WHEAT',1],['BUY_PRODUCT','FERTILIZER',1],['BUY_ANIMAL','GOOSE',1]]) for _ in range(4)]}
            m=[['SELL','MILK',milk]]
            original=copy.deepcopy((w,r,m));actual=H.official(w,r,m,9)
            if case<16:
                plain=H.official(w,r,m,9,audit=False)
                self.assertEqual((actual['state'],actual['env']),(plain['state'],plain['env']));COUNT['audit_parity']+=1
            for model in H.models.values():
                tr=H.trace(model,w,r,m,9)
                for key in ('cash','acquisitions','sale_receipts','executed_sales'):self.assertEqual(tr[key],actual[key],(case,key))
                COUNT['trace_comparisons']+=1
            self.assertEqual((w,r,m),original)

    def test_town_consumption_and_nonbuyable_rows_survive_composition(self):
        models={k:v for k,v in H.models.items() if k.startswith('town-')}
        for seat in (0,1):
            for count in (0,1,8):
                w=H.world(seat,capacity=5,milk=1,wheat=1,money=500,carry=[{'EGG':3}])
                w['cfg'].townShopSellInterval=1;w['cfg'].townCenterSellInterval=2
                obs=w['state'][0].observation;obs.town['unlocked_shops']=['BAKERY']*count
                obs.market['inventory']['WHEAT']=-100
                r=[{} for _ in range(32)]
                r[6]={'farmer':['DROP'],'market':[[],['BUY_PRODUCT','WHEAT',2],['SELL','EGG',2]]}
                r[7]={'market':[['BUY_PRODUCT','EGG',1],['BUY_PRODUCT','CARROT',2]]}
                r[8]={'market':[['SELL','WHEAT',2],['BUY_PRODUCT','WHEAT',2]]}
                actual=H.official(w,r,[['SELL','MILK',1]],8)
                for model in models.values():
                    tr=H.trace(model,w,r,[['SELL','MILK',1]],8)
                    for key in ('cash','acquisitions','sale_receipts','executed_sales'):self.assertEqual(tr[key],actual[key])
                    COUNT['trace_comparisons']+=1

    def test_town_dawn_guard_remains_fail_closed(self):
        w,r,m=self.basic()
        for label,model in H.models.items():
            if label.startswith('town-'):
                value,certificate=H.minimum(model,w,r,m,24)
                self.assertEqual(value,1);self.assertTrue(certificate['fallback'])
                self.assertIn('unobserved dawn',certificate['error'])

    def test_input_immutability(self):
        w,r,m=self.basic();before=copy.deepcopy((w,r,m))
        for model in H.models.values():H.minimum(model,w,r,m,7)
        self.assertEqual((w,r,m),before)

    def test_no_boundary_preserves_inherited_quantity(self):
        w=H.world(milk=5,wheat=0);r=[{} for _ in range(32)];r[6]={'market':[['BUY_ANIMAL','COW',1]]}
        m=[['SELL','MILK',5]];expected=H.minimum(H.base,w,r,m,6)[0]
        for model in H.models.values():self.assertEqual(H.minimum(model,w,r,m,6)[0],expected)

    def test_unitflow_and_perf_bytes_preserved_outside_owned_functions(self):
        for label,(sc,after) in H.sources.items():
            before=H.predecessors[label];out=after
            positions=compose.spans(after)
            for name in sorted(compose.BEFORE,key=lambda n:positions[n][0],reverse=True):
                a,b=positions[name];x,y=compose.spans(before)[name]
                out=out[:a]+before[x:y]+out[b:]
            self.assertEqual(out,before)
            self.assertEqual(compose.apply(after),after)

    def test_composition_rejects_mixed_and_unknown_functions(self):
        before=H.predecessors['unit1-perf1'];after=H.sources['unit1-perf1'][1]
        for name in compose.BEFORE:
            a,b=compose.spans(before)[name];x,y=compose.spans(after)[name]
            with self.assertRaises(ValueError):compose.apply(before[:a]+after[x:y]+before[b:])
        with self.assertRaises(ValueError):compose.apply(before.replace('stress_units=0):','stress_units=1):',1))
        with self.assertRaises(ValueError):compose.apply(before+'\ndef _funding_trace():\n    return None\n')

    def test_unrelated_source_text_is_preserved(self):
        for n in range(20):
            before=H.predecessors['unit1-perf1']+'\n# unrelated peer text '+str(n)+'\n'
            self.assertTrue(compose.apply(before).endswith('# unrelated peer text '+str(n)+'\n'))

    def test_real_cli_rejects_same_path_and_existing_output(self):
        cli=Path(compose.__file__)
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/'a.py';b=Path(tmp)/'b.py';a.write_text(H.predecessors['unit1-perf1'])
            flags=[sys.executable]+(['-O'] if not __debug__ else [])+[str(cli)]
            run=subprocess.run(flags+[str(a),str(b)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual(b.read_text(),H.sources['unit1-perf1'][1])
            sentinel=b.read_bytes()
            self.assertNotEqual(subprocess.run(flags+[str(a),str(b)],capture_output=True).returncode,0)
            self.assertEqual(b.read_bytes(),sentinel)
            self.assertNotEqual(subprocess.run(flags+[str(a),str(a)],capture_output=True).returncode,0)
            a.write_text(a.read_text().replace('stress_units=0):','stress_units=3):',1));c=Path(tmp)/'c.py'
            self.assertNotEqual(subprocess.run(flags+[str(a),str(c)],capture_output=True).returncode,0)
            self.assertFalse(c.exists())

    def test_inherited_funding_suite(self):
        mod=load(H.runtime/'checks/test_funded_prefix.py','_captrace_inherited')
        for model in H.models.values():
            mod.fs=model;result=unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromModule(mod))
            self.assertEqual((result.testsRun,len(result.failures),len(result.errors)),(8,0,0))


def run_mutants():
    source=H.sources['town-unit1-perf1'][1]
    specs=[
        ('oversized_shed','24, cap)','24, 10**6)','test_discarded_goods_are_not_cash'),
        ('unverified_zero','if not required and boundary is None:','if not required:','test_minimum_retains_capacity_for_funding_sale'),
        ('skip_pre_sale_buys',"if units > 0 and key[:2] < boundary[:2]}","if units > 0 and key[0] < boundary[0]}",'test_acquisition_before_same_turn_sale_needs_cash'),
        ('shift_raw_slot','sale_receipts.append((t, index, item, executed, cash))','sale_receipts.append((t, index + 1, item, executed, cash))','test_raw_slots_and_zero_fill_are_retained'),
        ('skip_boundary_draw','for t in range(now, trace_end+1)','for t in range(now, prefix_end+1)','test_boundary_buy_stress_is_not_deduplicated'),
    ]
    saved=H.models.copy();savedprimary=H.primary;results=[]
    try:
        for name,old,new,test in specs:
            if source.count(old)!=1:raise ValueError('mutation anchor '+name)
            mutant=H.model(source.replace(old,new,1))
            H.models={'mutant':mutant};H.primary=mutant
            result=unittest.TextTestRunner(stream=io.StringIO()).run(unittest.TestSuite([FundingCapacityTests(test)]))
            if not result.failures or result.errors:raise AssertionError('mutant not assertion-rejected: '+name)
            results.append({'name':name,'assertion_failures':len(result.failures),'errors':len(result.errors)})
    finally:H.models=saved;H.primary=savedprimary
    return results


def main():
    global H
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--unitflow',type=Path,required=True);p.add_argument('--funding-perf',type=Path,required=True)
    p.add_argument('--town-funding',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--no-mutants',action='store_true')
    a=p.parse_args();H=Harness(a.runtime,a.unitflow,a.funding_perf,a.town_funding)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FundingCapacityTests))
    report={'python':sys.version,'optimized':not __debug__,'tests':result.testsRun,'failures':len(result.failures),
            'errors':len(result.errors),'skips':len(result.skipped),'runtime_members':109,'source_sha256':SOURCE_SHA,
            'engine_sha256':H.engine_hashes,'counts_before_mutants':dict(COUNT),
            'sources':{k:{'scheduler_blob':blob(v[0].encode()),'frozen_blob':blob(v[1].encode()),
                          'frozen_sha256':hashlib.sha256(v[1].encode()).hexdigest()} for k,v in H.sources.items()}}
    if result.wasSuccessful() and not a.no_mutants:report['mutants']=run_mutants()
    report['counts_including_mutants']=dict(COUNT)
    a.output.write_text(json.dumps(report,indent=2)+'\n')
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':main()
