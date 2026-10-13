# SPDX-License-Identifier: Apache-2.0
"""D4 guard, native source composition and full official-engine controls."""
from __future__ import annotations
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
ROOT=Path(os.environ['BLOOM_BASELINE']).resolve()
CAND=Path(os.environ['BLOOM_CANDIDATE']).resolve()
sys.path[:0]=[str(ROOT),str(HERE)]
import native_d4 as d4
import build_native_d4 as build
import run_native_d4 as driver
import frozen_selected as baseline
candidate=driver.load('_bloom_test_candidate',CAND/'frozen_selected.py')
def unanchored_control():
    # Deliberately broken comparison reference, never a production option.
    import types
    source=(CAND/'frozen_selected.py').read_text()
    for old,new in [('min(t,reference_end),q));rem-=q','min(t,item_end),q));rem-=q'),
                    ('for t in range(now+1,reference_end+1):','for t in range(now+1,item_end+1):')]:
        if source.count(old)!=1:raise ValueError('Unanchored control source drift')
        source=source.replace(old,new,1)
    module=types.ModuleType('_bloom_bad_reference_control')
    module.__file__=str(CAND/'frozen_selected.py')
    sys.modules[module.__name__]=module
    exec(compile(source,module.__file__,'exec'),module.__dict__)
    module.control_sha256=driver.digest(source.encode())
    return module


REPORT={'engine_calls':0,'transitions':0,'constructed_cells':[]}
PASS={'farmer':['PASS'],'hands':[],'market':[]}


def inputs():
    route=[copy.deepcopy(PASS) for _ in range(720)]
    route[380]['market']=[['SELL','STRAWBERRY',9]]
    return dict(enabled=True,now=365,last=718,route=route,action=copy.deepcopy(PASS),
        stock=4,price=200,item_end=373,hard_end=383,max_orders=10,min_price=180,
        turns_per_day=24)


class HorizonTests(unittest.TestCase):
    def test_positive_representation_and_nonmutation(self):
        x=inputs();saved=copy.deepcopy(x);out=d4.sale_horizon(**x)
        self.assertEqual(out['due'],380);self.assertEqual(out['represented_units'],4)
        self.assertEqual(x,saved)

    def test_disabled_exact_no_op(self):
        for v in (False,None,0,1,'true'):
            self.assertIsNone(d4.sale_horizon(**dict(inputs(),enabled=v))['due'])

    def test_numeric_contract(self):
        for key in ('now','last','stock','price','item_end','hard_end','max_orders','min_price','turns_per_day'):
            for bad in (None,True,'24',24.0,float('nan'),float('inf')):
                with self.subTest(key=key,bad=bad):
                    self.assertIsNone(d4.sale_horizon(**dict(inputs(),**{key:bad}))['due'])

    def test_stock_and_threshold(self):
        for k,v in [('stock',0),('stock',-1),('price',179),('min_price',1)]:
            self.assertIsNone(d4.sale_horizon(**dict(inputs(),**{k:v}))['due'])
        self.assertEqual(d4.sale_horizon(**dict(inputs(),price=2,min_price=2))['due'],380)

    def test_window_terminal_day_and_checkpoint(self):
        for k,v in [('now',287),('now',456),('last',365),('hard_end',379),('hard_end',365),('item_end',383),('turns_per_day',12)]:
            self.assertIsNone(d4.sale_horizon(**dict(inputs(),**{k:v}))['due'])
        x=inputs();x['route'][380]['market']=[];x['route'][384]['market']=[['SELL','STRAWBERRY',5]];x['hard_end']=400
        self.assertIsNone(d4.sale_horizon(**x)['due'])

        # A coherent positive-shaped opportunity outside days12-18 isolates
        # the day guard instead of accidentally failing a different boundary.
        for day in (11,19):
            x=inputs();x['route'][380]['market']=[]
            x.update(now=day*24+5,item_end=day*24+13,hard_end=day*24+23)
            x['route'][day*24+20]['market']=[['SELL','STRAWBERRY',9]]
            self.assertEqual(d4.sale_horizon(**x)['reason'],'day_window')

    def test_future_raw_cap_not_compacted(self):
        x=inputs();x['route'][380]['market']=[[]]*10+[['SELL','STRAWBERRY',50]]
        self.assertIsNone(d4.sale_horizon(**x)['due'])
        x['route'][380]['market']=[[]]*9+[['SELL','STRAWBERRY',50]]
        self.assertEqual(d4.sale_horizon(**x)['due'],380)

    def test_current_raw_cap_and_minimum_one(self):
        x=inputs();x['action']['market']=[[]]*10
        self.assertEqual(d4.sale_horizon(**x)['reason'],'current_cap_full')
        x=inputs();x['max_orders']=0;x['route'][380]['market']=[[],['SELL','STRAWBERRY',9]]
        self.assertIsNone(d4.sale_horizon(**x)['due'])
        x['route'][380]['market']=[['SELL','STRAWBERRY',9]]
        self.assertEqual(d4.sale_horizon(**x)['due'],380)

    def test_current_incumbent_and_consumption(self):
        for order in (['SELL','STRAWBERRY',2],['BUY_PRODUCT','STRAWBERRY',1]):
            x=inputs();x['action']['market']=[order]
            self.assertIsNone(d4.sale_horizon(**x)['due'])
        for actor in ('farmer','hands'):
            x=inputs();x['action'][actor]=['PICKUP','STRAWBERRY',1] if actor=='farmer' else [['PICKUP','STRAWBERRY',1]]
            self.assertEqual(d4.sale_horizon(**x)['reason'],'pickup_barrier')

    def test_intervening_pickup_buy_and_incumbent_sale(self):
        for date in (366,373,374,380):
            for kind in ('pickup','buy'):
                x=inputs()
                if kind=='pickup':x['route'][date]['farmer']=['PICKUP','STRAWBERRY',1]
                else:x['route'][date]['market'].insert(0,['BUY_PRODUCT','STRAWBERRY',1])
                self.assertIsNone(d4.sale_horizon(**x)['due'])
        x=inputs();x['route'][373]['market']=[['SELL','STRAWBERRY',1]]
        self.assertEqual(d4.sale_horizon(**x)['reason'],'incumbent_future_sale')

    def test_dead_suffix_does_not_create_barrier(self):
        x=inputs();x['route'][370]['market']=[[]]*10+[['BUY_PRODUCT','STRAWBERRY',99]]
        self.assertEqual(d4.sale_horizon(**x)['due'],380)

    def test_poison_before_due_and_irrelevant_tail(self):
        for key,bad in [('market',None),('market',[{}]),('farmer',[]),('hands',[None])]:
            x=inputs();x['route'][379][key]=bad
            self.assertIsNone(d4.sale_horizon(**x)['due'])
        for bad in (-1,True,1.2,None,'9'):
            x=inputs();x['route'][380]['market']=[['SELL','STRAWBERRY',bad]]
            self.assertIsNone(d4.sale_horizon(**x)['due'])
        x=inputs();x['route'][381]=None
        self.assertEqual(d4.sale_horizon(**x)['due'],380)

    def test_first_due_and_multiple_raw_lots(self):
        x=inputs();x['route'][376]['market']=[['SELL','STRAWBERRY',1],[],['SELL','STRAWBERRY',2]]
        self.assertEqual(d4.sale_horizon(**x)['due'],376)
        self.assertEqual(d4.sale_horizon(**x)['represented_units'],3)


class CompositionTests(unittest.TestCase):
    def test_generated_bytes_and_idempotence(self):
        for filename,keys in [('titan_runtime.py',['features','initialize']),('frozen_selected.py',['transform'])]:
            original=(ROOT/filename).read_text();changed=build.compose_text(original,keys)
            self.assertEqual(changed,(CAND/filename).read_text())
            self.assertEqual(build.compose_text(changed,keys),changed)
            # Every byte outside the declared methods/class is restored exactly.
            undo=changed
            for key in reversed(keys):
                pin=build.METHODS[key];a,b=build.span(undo,pin['class'],pin['method'])
                c,d=build.span(original,pin['class'],pin['method'])
                undo=undo[:a]+original[c:d]+undo[b:]
            self.assertEqual(undo,original)

    def test_method_drift_rejected(self):
        for filename,key in [('titan_runtime.py','features'),('titan_runtime.py','initialize'),('frozen_selected.py','transform')]:
            pin=build.METHODS[key];s=(ROOT/filename).read_text();a,b=build.span(s,pin['class'],pin['method'])
            s=s[:b-1]+' # unintended drift'+s[b-1:]
            with self.assertRaises(ValueError):build.compose_text(s,[key])

    def test_unrelated_peer_bytes_preserved(self):
        for filename,keys in [('titan_runtime.py',['features','initialize']),('frozen_selected.py',['transform'])]:
            s=(ROOT/filename).read_text()+'\nPEER_SENTINEL = 73\n'
            out=build.compose_text(s,keys)
            self.assertTrue(out.endswith('PEER_SENTINEL = 73\n'))

    def test_nonoverwriting_output_and_default_off(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);build.compose(ROOT,p/'ok');build.compose(ROOT,p/'ok')
            self.assertIs(json.loads((p/'ok/TITAN-CONFIG.json').read_text())[d4.KEY],False)
            (p/'ok/native_d4.py').write_text('peer source')
            with self.assertRaises(ValueError):build.compose(ROOT,p/'ok')
        with self.assertRaises(ValueError):build.compose(ROOT,ROOT)

    def test_actual_features_and_initialization(self):
        runtime=driver.load('_bloom_candidate_runtime',CAND/'titan_runtime.py')
        self.assertIs(runtime.Features().r04_d4_strawberry_timing,False)
        for kwargs in ({d4.KEY:'yes'},{d4.KEY:True,'consumer':'ordered'},
                       {d4.KEY:True,'terminal_route':True},{'r04_d4_strawberry_min_price':True}):
            with self.assertRaises(ValueError):runtime.Features(**kwargs)
        agent=runtime.TitanAgent(runtime.Features(**{d4.KEY:True,'r04_d4_strawberry_min_price':2}))
        agent._initialize()
        self.assertIs(agent.consumer.r04_d4_strawberry_timing,True)
        self.assertEqual(agent.consumer.r04_d4_strawberry_min_price,2)

    def test_full_package_custody(self):
        self.assertEqual(len(driver.verify(ROOT)[0]),109)
        self.assertEqual(len(driver.verify(CAND)[0]),110)


class NativeEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ev=driver.load('_bloom_test_engine_loader',ROOT/'checks/reference/evaluator/evaluate.py')
        cls.engine,cls.hashes=cls.ev.get_engine(ROOT/'checks/reference/engine',ROOT/'checks/reference/evaluator/loader.py')
        REPORT['engine_sha256']=cls.hashes

    def world(self,seat=0,quantity=80,inventory=10000,now=361,shops=4):
        e,S=self.engine,self.ev.Struct
        cfg=S({k:v.get('default')if isinstance(v,dict)else v for k,v in e.specification['configuration'].items()})
        cfg.weedSpawnChance=0
        farms=[e._new_farm(10,1000),e._new_farm(10,1000)]
        for x in range(5):
            plant=e._new_plant('STRAWBERRY',1,24)
            plant['yield_units']=4
            farms[1-seat]['tiles'][0][x]=plant
        market=e._new_market();market['inventory']['STRAWBERRY']=inventory;e._refresh_prices(market)
        town={'unlocked_shops':['SMOOTHIE_SHOP']*shops}
        state=[]
        for i in range(2):
            p=e._new_private();p['shed']['STRAWBERRY']=quantity if i==seat else 0
            state.append(S(observation=S(player=i,step=now,day=now//24,hour=now%24,
                farms=farms,private=p,market=market,town=town),action=copy.deepcopy(PASS),status='ACTIVE',reward=0))
        env=S(configuration=cfg,done=False,info={'seed':9600803})
        route=[copy.deepcopy(PASS)for _ in range(720)];route[now+15]['market']=[['SELL','STRAWBERRY',quantity]]
        return state,env,route

    def consumer(self,cls,route,enabled=True,threshold=2):
        c=cls();c.controller.R={'d4-fixture':route};c.controller.cur='d4-fixture'
        c.r04_d4_strawberry_timing=enabled;c.r04_d4_strawberry_min_price=threshold
        return c

    def step(self,state,env,seat,now,action,rival=None):
        for i,s in enumerate(state):
            s.observation.step=now;s.action=copy.deepcopy(action if i==seat else (rival or PASS))
        self.engine.interpreter(state,env)
        REPORT['engine_calls']+=1;REPORT['transitions']+=1

    def test_real_native_engaged_output_and_engine_fill(self):
        for seat in (0,1):
            for inventory,quantity in [(10000,80),(10020,80),(10050,30),(0,4)]:
                states,env,route=self.world(seat,quantity,inventory)
                obs=states[seat].observation
                before=copy.deepcopy((obs,route));c=self.consumer(candidate.FrozenSelected,route)
                out=c.transform(copy.deepcopy(obs),env.configuration,copy.deepcopy(PASS))
                b=self.consumer(baseline.FrozenSelected,route,False)
                old=b.transform(copy.deepcopy(obs),env.configuration,copy.deepcopy(PASS))
                self.assertEqual(c.diagnostics['d4']['due'],376)
                self.assertEqual(c.diagnostics['evaluations'][0]['horizon_end'],376)
                self.assertEqual(out,old)
                self.assertEqual(c.diagnostics['evaluations'][0]['reference'],
                                 b.diagnostics['evaluations'][0]['reference'])
                bad=self.consumer(unanchored_control().FrozenSelected,route)
                bad_out=bad.transform(copy.deepcopy(obs),env.configuration,copy.deepcopy(PASS))
                self.assertNotEqual(bad_out,old)
                self.assertEqual((obs,route),before)
                amount=sum(o[2]for o in bad_out['market']if o[:2]==['SELL','STRAWBERRY'])
                self.assertGreater(amount,0);self.assertLessEqual(amount,quantity)
                oldmoney=obs.farms[seat]['money'];self.step(states,env,seat,361,bad_out)
                self.assertEqual(states[seat].observation.private['shed']['STRAWBERRY'],quantity-amount)
                self.assertGreater(states[seat].observation.farms[seat]['money'],oldmoney)
                self.assertFalse(hasattr(c,'sale_window_debts'))
                REPORT['constructed_cells'].append(dict(seat=seat,inventory=inventory,quantity=quantity,
                    unanchored_control_sold=amount,cash_received=states[seat].observation.farms[seat]['money']-oldmoney))

    def test_disabled_and_guarded_native_equivalence(self):
        for seat in (0,1):
            for block in ('off','price','current_sell','cap','pickup','dead_sale'):
                states,env,route=self.world(seat);action=copy.deepcopy(PASS)
                if block=='current_sell':action['market']=[['SELL','STRAWBERRY',3]]
                if block=='cap':action['market']=[[]]*10
                if block=='pickup':route[370]['farmer']=['PICKUP','STRAWBERRY',1]
                if block=='dead_sale':route[376]['market']=[[]]*10+[['SELL','STRAWBERRY',80]]
                left=self.consumer(baseline.FrozenSelected,route,False)
                right=self.consumer(candidate.FrozenSelected,route,block!='off',9999 if block=='price' else 2)
                a=left.transform(copy.deepcopy(states[seat].observation),env.configuration,copy.deepcopy(action))
                b=right.transform(copy.deepcopy(states[seat].observation),env.configuration,copy.deepcopy(action))
                self.assertEqual(a,b)
                self.assertEqual(left.planned,right.planned);self.assertEqual(left.pending,right.pending)
                other,oe=copy.deepcopy((states,env))
                self.step(states,env,seat,361,a);self.step(other,oe,seat,361,b)
                self.assertEqual(states,other)

    def test_complete_engine_raw_slot_intervening_barriers(self):
        for seat in (0,1):
            for cap in (0,1,2,10):
                states,env,route=self.world(seat,quantity=4)
                env.configuration.maxMarketOrdersPerTurn=cap
                count=max(1,cap);a=copy.deepcopy(PASS);a['market']=[[]]*count+[['SELL','STRAWBERRY',4]]
                self.step(states,env,seat,361,a)
                self.assertEqual(states[seat].observation.private['shed']['STRAWBERRY'],4)
                a['market']=[[]]*(count-1)+[['SELL','STRAWBERRY',4]]
                self.step(states,env,seat,362,a)
                self.assertEqual(states[seat].observation.private['shed']['STRAWBERRY'],0)

    def test_threshold_not_a_profit_certificate(self):
        # A returned horizon is a candidate admission, never an unconditional
        # economic endorsement; zero rival standing stock is an engaged control
        # where the incumbent optimizer elects to keep the current PASS.
        states,env,route=self.world()
        states[0].observation.farms[1]=self.engine._new_farm(10,1000)
        c=self.consumer(candidate.FrozenSelected,route)
        out=c.transform(copy.deepcopy(states[0].observation),env.configuration,copy.deepcopy(PASS))
        self.assertIsNotNone(c.diagnostics['d4']['due'])
        self.assertEqual(out,PASS)


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    if os.environ.get('BLOOM_TEST_RECEIPT'):
        REPORT.update(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skips=len(result.skipped))
        Path(os.environ['BLOOM_TEST_RECEIPT']).write_text(json.dumps(REPORT,indent=2,sort_keys=True)+'\n')
    raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)
