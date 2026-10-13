"""Independent full pinned-interpreter containment tests; no runtime policy.

Run with --reference-root PATH_TO_checks/reference. Missing or modified engine,
spec, seed utility, or loader fails before any test (never a skipped green).
Oracle instrumentation calls the original _commit_unit unchanged, recording
inventory deltas by seat. That privileged oracle data NEVER enters the helper.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import sys
import unittest
import effective_flow_bounds as f

PINS = {
    'evaluator/loader.py': 'cd113a94ae99b03492502e425bdcf09c3db17a2aa2a8fd866f0d78caec9e311e',
    'engine/kaggriculture.py': 'bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e',
    'engine/kaggriculture.json': 'a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867',
    'engine/utils.py': '537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b',
}
REFERENCE_ROOT = None
STATS = {'initialized_worlds': 0, 'full_transitions': 0, 'random_worlds': 0,
         'product_containment_checks': 0, 'witnesses': []}


def reference_root():
    supplied = REFERENCE_ROOT or os.environ.get('TITAN_REFERENCE_ROOT')
    if supplied:
        return Path(supplied).resolve()
    for parent in Path(__file__).resolve().parents:
        candidate = parent / 'checks/reference'
        if candidate.is_dir():
            return candidate
    raise RuntimeError('Provide --reference-root (no engine download or skip fallback)')


def public(obs):
    return {k: copy.deepcopy(obs[k]) for k in ('step', 'player', 'market', 'town')}


class FlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = reference_root()
        for name, digest in PINS.items():
            path = root / name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise RuntimeError('reference pin mismatch or missing file: ' + name)
        spec = importlib.util.spec_from_file_location('estuary_reference_loader', root/'evaluator/loader.py')
        cls.loader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.loader)
        cls.engine, _ = cls.loader.get_engine(root/'engine')
        if tuple(cls.engine.PRODUCTS) != f.PRODUCTS:
            raise RuntimeError('product contract drift')
        if {k: tuple(v) for k,v in cls.engine.SHOPS.items()} != f.SHOPS:
            raise RuntimeError('shop contract drift')

    def world(self, step=101, shops=(), config=None, cash=(100000,100000), sheds=None, inventory=None):
        e, S = self.engine, self.loader.Struct
        cfg = S({k:v.get('default') if isinstance(v,dict) else v
                 for k,v in e.specification['configuration'].items()})
        cfg.update(config or {})
        cfg.seed = 20260911
        env = S(configuration=cfg,done=False,info={})
        state = [S(observation=S(),action={},status='ACTIVE',reward=0) for _ in (0,1)]
        e.interpreter(state,env)
        STATS['initialized_worlds'] += 1
        state[0].observation.town['unlocked_shops'] = list(shops)
        if inventory is not None:
            state[0].observation.market['inventory'].update(inventory)
            e._refresh_prices(state[0].observation.market)
        for seat,s in enumerate(state):
            s.observation.step = step
            s.action = {'farmer':['PASS'],'hands':[],'market':[]}
            s.observation.farms[seat]['money'] = cash[seat]
            s.observation.private['shed'] = dict((sheds or ({},{}))[seat])
        return state, env

    def run_world(self, own, rival, *, seat=0, **kwargs):
        state, env = self.world(**kwargs)
        state[seat].action = copy.deepcopy(own)
        state[1-seat].action = copy.deepcopy(rival)
        before = public(state[seat].observation)
        farms = state[0].observation.farms
        flows = [dict.fromkeys(f.PRODUCTS,0) for _ in (0,1)]
        original = self.engine._commit_unit
        def record(op,item,price,farm,private,market,shed_capacity=100):
            pid = 0 if farm is farms[0] else 1
            snapshot = dict(market['inventory'])
            ok = original(op,item,price,farm,private,market,shed_capacity)
            for p in f.PRODUCTS:
                flows[pid][p] += market['inventory'][p] - snapshot[p]
            return ok
        self.engine._commit_unit = record
        try:
            self.engine.interpreter(state,env)
            STATS['full_transitions'] += 1
        finally:
            self.engine._commit_unit = original
        after = public(state[seat].observation)
        after['step'] = before['step'] + 1  # framework-owned recording counter
        untouched = copy.deepcopy((before, own, after, env.configuration))
        bounds = f.effective_flow_bounds(before, own, after, env.configuration)
        self.assertIsNotNone(bounds)
        self.assertEqual((before,own,after,env.configuration), untouched)
        for p in f.PRODUCTS:
            lo,hi = bounds[p]
            self.assertLessEqual(lo, flows[1-seat][p], (p,bounds,flows,kwargs,own,rival))
            self.assertGreaterEqual(hi, flows[1-seat][p], (p,bounds,flows,kwargs,own,rival))
            STATS['product_containment_checks'] += 1
        return bounds, flows, before, after, state

    def test_unaffordable_buy_phantom_dump_both_seats(self):
        for seat in (0,1):
            action = {'market':[['BUY_PRODUCT','WHEAT',1000]]}
            b,flows,pre,post,_ = self.run_world(action,{},seat=seat,cash=(0,0))
            naive = post['market']['inventory']['WHEAT']-pre['market']['inventory']['WHEAT']+1000
            self.assertEqual(naive,1000)
            self.assertEqual(flows[1-seat]['WHEAT'],0)
            self.assertEqual(b['WHEAT'],(0,1000))
            self.assertEqual(f.confirmed_net_sells(b),{})
            STATS['witnesses'].append({'seat':seat,'naive_requested_point':naive,
                'true_rival_effective_flow':0,'new_bounds':list(b['WHEAT'])})

    def test_full_shed_and_partial_buy(self):
        for seat in (0,1):
            for stock in (100,95):
                sheds = [{},{}]; sheds[seat]={'WHEAT':stock}
                b,flow,*_ = self.run_world({'market':[['BUY_PRODUCT','WHEAT',1000]]},{},
                                           seat=seat,sheds=sheds)
                self.assertEqual(flow[seat]['WHEAT'],-(100-stock))
                self.assertEqual(b['WHEAT'],(-(100-stock),1000-(100-stock)))
                self.assertEqual(f.confirmed_net_sells(b),{})

    def test_unsupported_product_buys_are_not_flow(self):
        for product in f.PRODUCTS:
            if product in ('WHEAT','FERTILIZER'): continue
            b,flow,*_ = self.run_world({'market':[['BUY_PRODUCT',product,1000]]},{})
            self.assertEqual(b[product],(0,0))
            self.assertEqual(flow[0][product],0)

    def test_raw_prefix_before_filtering(self):
        for seat in (0,1):
            for cap in (0,1,3,10):
                raw = [[],None,('SELL','MILK',5),'PASS',{}]*2
                raw = raw[:max(1,cap)]+[['BUY_PRODUCT','WHEAT',1000],['SELL','MILK',300]]
                b,*_ = self.run_world({'market':raw},{},seat=seat,
                                     config={'maxMarketOrdersPerTurn':cap})
                self.assertEqual(b['WHEAT'],(0,0))
                self.assertEqual(b['MILK'],(0,0))

    def test_nonlist_market_and_row_ignored(self):
        for market in ((['SELL','MILK',20],), 'SELL', {}, None,
                       [('SELL','MILK',20)]):
            b,*_ = self.run_world({'market':market},{},sheds=({'MILK':20},{}))
            self.assertEqual(b['MILK'],(0,0))

    def test_engine_quantity_conversion(self):
        for q,want in [('3',3),(3.9,3),(True,1),(False,0),(-5,0),
                       (None,0),('oops',0),(float('nan'),0)]:
            b,*_ = self.run_world({'market':[['SELL','MILK',q]]},{},sheds=({},{}))
            self.assertEqual(b['MILK'],(-want,0))

    def test_per_row_loop_escape_bound(self):
        # Empty shed ends execution early; envelope still obeys engine's row limit.
        b,*_ = self.run_world({'market':[['SELL','MILK',200000],
                                       ['BUY_PRODUCT','WHEAT',200000]]},{},cash=(0,0))
        self.assertEqual(b['MILK'],(-99999,0))
        self.assertEqual(b['WHEAT'],(0,99999))

    def test_floor_sells_are_invisible_not_negative_rival(self):
        inv = dict.fromkeys(f.PRODUCTS,10**20)
        for seat in (0,1):
            sheds=[{},{}];sheds[seat]={'WHEAT':90}
            b,flow,pre,post,state = self.run_world({'market':[['SELL','WHEAT',90]]},{},
                                                  seat=seat,sheds=sheds,inventory=inv)
            self.assertEqual(pre['market']['prices']['WHEAT'],1)
            self.assertEqual(flow[seat]['WHEAT'],0)
            self.assertEqual(b['WHEAT'],(-90,0))
            self.assertEqual(state[seat].observation.private['shed']['WHEAT'],0)

    def test_exact_rival_flow_when_own_has_no_product_rows(self):
        for seat in (0,1):
            sheds=[{},{}];sheds[1-seat]={'MILK':80}
            b,flow,*_ = self.run_world({'market':[['BUY_SEED','WHEAT',2],['HIRE']]},
                {'market':[['SELL','MILK',70],['BUY_PRODUCT','WHEAT',15]]},
                seat=seat,sheds=sheds,inventory=dict.fromkeys(f.PRODUCTS,0))
            self.assertEqual(b['MILK'],(70,70)); self.assertEqual(b['WHEAT'],(-15,-15))
            self.assertEqual(f.confirmed_net_sells(b,60),{'MILK':70})

    def test_simultaneous_same_product_orders(self):
        for seat in (0,1):
            for ownop in ('SELL','BUY_PRODUCT'):
                for otherop in ('SELL','BUY_PRODUCT'):
                    b,flow,*_ = self.run_world({'market':[[ownop,'WHEAT',50]]},
                        {'market':[[otherop,'WHEAT',70]]},seat=seat,
                        sheds=({'WHEAT':80},{'WHEAT':80}),inventory={'WHEAT':500})
                    self.assertLessEqual(b['WHEAT'][0],flow[1-seat]['WHEAT'])

    def test_duplicate_shops_and_negative_inventory(self):
        b,flow,pre,post,_ = self.run_world({}, {},step=24,
            shops=['YARN_STORE','YARN_STORE','BAKERY'],inventory=dict.fromkeys(f.PRODUCTS,0))
        self.assertEqual(post['market']['inventory']['WOOL'],-5)
        self.assertEqual(post['market']['inventory']['WHEAT'],-2)
        self.assertTrue(all(v==(0,0) for v in b.values()))

    def test_prior_shops_not_newly_unlocked_shops(self):
        for seat in (0,1):
            b,flow,pre,post,_ = self.run_world({}, {},seat=seat,step=71,
                config={'townShopSellInterval':1,'townShopUnlockInterval':3})
            self.assertEqual(len(post['town']['unlocked_shops']),len(pre['town']['unlocked_shops'])+1)
            self.assertTrue(all(v==(0,0) for v in b.values()))

    def test_prior_tick_and_custom_intervals(self):
        for step in (0,1,3,4,7,8,11,12,23,24,47,48,71):
            b,*_ = self.run_world({}, {},step=step,shops=['BAKERY','PET_CAFE'],
                config={'townShopSellInterval':7,'townCenterSellInterval':11,'turnsPerDay':12})
            self.assertTrue(all(v==(0,0) for v in b.values()))

    def test_missing_bad_and_nonadjacent_inputs_fail_closed(self):
        state,env=self.world(); before=public(state[0].observation)
        after=copy.deepcopy(before);after['step']+=1
        for field in ('step','player','market','town'):
            a=copy.deepcopy(before);del a[field]
            self.assertIsNone(f.effective_flow_bounds(a,{},after,env.configuration))
        for q in (None, True, '4', 3.5, float('nan'),float('inf')):
            for target in ('step','inventory'):
                a=copy.deepcopy(before)
                if target=='step':a['step']=q
                else:a['market']['inventory']['WHEAT']=q
                self.assertIsNone(f.effective_flow_bounds(a,{},after,env.configuration))
        for delta in (-10,0,2):
            a=copy.deepcopy(after);a['step']=before['step']+delta
            self.assertIsNone(f.effective_flow_bounds(before,{},a,env.configuration))
        a=copy.deepcopy(after);a['player']=1
        self.assertIsNone(f.effective_flow_bounds(before,{},a,env.configuration))
        a=copy.deepcopy(before);del a['market']['inventory']['MILK']
        self.assertIsNone(f.effective_flow_bounds(a,{},after,env.configuration))
        a=copy.deepcopy(before);a['town']['unlocked_shops']=['UNKNOWN']
        self.assertIsNone(f.effective_flow_bounds(a,{},after,env.configuration))
        for cfg in ([],{'maxMarketOrdersPerTurn':None},{'townShopSellInterval':float('inf')}):
            self.assertIsNone(f.effective_flow_bounds(before,{},after,cfg))
        self.assertIsNone(f.effective_flow_bounds(before,{'market':[['SELL','MILK',float('inf')]]},after))

    def test_positive_signal_is_lower_bound_only(self):
        for b in (None, {'WHEAT':(0,1000)},{'WHEAT':(-100,1000)},
                  {'WHEAT':(150,1)},{'WHEAT':(True,150)},{'UNKNOWN':(900,900)}):
            self.assertEqual(f.confirmed_net_sells(b),{})
        self.assertEqual(f.confirmed_net_sells({'WHEAT':(150,1000)}),{'WHEAT':150})
        self.assertEqual(f.confirmed_net_sells({'WHEAT':(100,1000)},0),{})

    def test_no_hidden_private_dependency_or_state(self):
        state,env=self.world();a=public(state[0].observation);b=copy.deepcopy(a);b['step']+=1
        expected=f.effective_flow_bounds(a,{},b,env.configuration)
        a['private']={'fake_secret':'DO NOT CONSUME'};b['private']={'money':10**30}
        for seat in (1,0,1,0):
            a['player']=b['player']=seat
            self.assertEqual(f.effective_flow_bounds(a,{},b,env.configuration),expected)
        self.assertFalse(hasattr(f,'_STATES'))

    def test_randomized_full_interpreter_containment(self):
        rng=random.Random(202609110891)
        def orders():
            rows=[]
            for _ in range(rng.randrange(0,14)):
                if rng.random()<.2:rows.append(rng.choice([[],None,{},['PASS']]));continue
                op=rng.choice(['SELL','BUY_PRODUCT','BUY_ANIMAL','BUY_SEED','HIRE','BUY_LAND'])
                product=rng.choice(list(f.PRODUCTS)+['SHEEP','GOOSE','UNKNOWN'])
                rows.append([op,product,rng.choice([0,-1,1,3,20,100,1000,'12','bad',None])])
            return {'market':rows,'farmer':['PASS'],'hands':[]}
        for n in range(400):
            own,rival=orders(),orders()
            inv={p:rng.choice([-200,0,300,3000,100000]) for p in f.PRODUCTS}
            sheds=[]
            for _ in (0,1):
                shed={}
                for __ in range(rng.randrange(0,5)):
                    p=rng.choice(f.PRODUCTS);shed[p]=shed.get(p,0)+rng.randrange(0,20)
                sheds.append(shed)
            self.run_world(own,rival,seat=n%2,step=rng.randrange(0,718),
                config={'maxMarketOrdersPerTurn':rng.choice([0,1,3,10]),
                        'townShopSellInterval':rng.choice([1,4,7]),
                        'townCenterSellInterval':rng.choice([11,24]),
                        'shedCapacity':rng.choice([25,100])},
                shops=[rng.choice(tuple(f.SHOPS)) for _ in range(rng.randrange(0,6))],
                inventory=inv,sheds=sheds,cash=(rng.choice([0,30,1000,100000]),rng.choice([0,30,1000,100000])))
            STATS['random_worlds']+=1


if __name__=='__main__':
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--reference-root')
    opts,rest=parser.parse_known_args()
    REFERENCE_ROOT=opts.reference_root
    run=unittest.main(argv=[sys.argv[0],*rest],exit=False)
    STATS.update(tests=run.result.testsRun,failures=len(run.result.failures),
                 errors=len(run.result.errors),skipped=len(run.result.skipped),optimized=sys.flags.optimize)
    print('ESTUARY_COUNTERS '+json.dumps(STATS,sort_keys=True))
    sys.exit(0 if run.result.wasSuccessful() and run.result.testsRun>0 and not run.result.skipped else 1)
