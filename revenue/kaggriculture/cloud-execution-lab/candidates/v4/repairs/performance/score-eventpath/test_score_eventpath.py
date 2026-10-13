# SPDX-License-Identifier: Apache-2.0
"""Exact-source differential tests; point TITAN_RUNTIME at the native source tree.

No Kaggle install or network is used. Full source pins prevent a green result
against a different predecessor. This suite does not mutate production files.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import itertools
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import types
import unittest

from build_score_eventpath import compose, SCORE

ROOT = Path(os.environ.get('TITAN_RUNTIME') or next((p for p in Path(__file__).resolve().parents
            if (p/'selected_sell_core.py').exists()), Path.cwd())).resolve()
PINS = {
    'scheduler.py': 'a483b24dd72b580d7d8811636b54d2d44f391575',
    'selected_sell_core.py': 'f23d3a8b5ee5e82029026e7f8f44eb36c143a5a3',
}
DEPENDENCY_PINS = {
    'mechanics.py':'044a4f9c0a4a44dde10ada57563238bcaf82075d',
    'reference/decision/decision.py':'2931aa55831204fbb473ab85a6f5b81ec947fcf7',
}
SOURCES = {}
MODULES = {}

def git_blob(data):
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()

def load(source, name, path):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(source, str(path), 'exec'), module.__dict__)
    return module

def setup():
    for filename,pin in DEPENDENCY_PINS.items():
        if git_blob((ROOT/filename).read_bytes())!=pin:
            raise RuntimeError(f'dependency drift: {filename}')
    sys.path.insert(0,str(ROOT))
    for filename, pin in PINS.items():
        data=(ROOT/filename).read_bytes()
        if git_blob(data)!=pin:
            raise RuntimeError(f'input source drift: {filename} {git_blob(data)} != {pin}')
        source=data.decode();SOURCES[filename]=source
        MODULES[filename]=(load(source,'event_base_'+filename[:-3],ROOT/filename),
                           load(compose(source),'event_candidate_'+filename[:-3],ROOT/filename))

def model(mod, *, item='MILK', inventory=10015, shops=None, config=None, now=0, end=8):
    return mod.MarketPath(item,inventory,None,[] if shops is None else shops,
                          {} if config is None else config,now,end)

def outcome(fn):
    try:
        return ('ok',fn())
    except Exception as exc:
        return ('error',type(exc).__name__,str(exc))

class EventPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not MODULES:setup()

    def test_01_exact_source_custody(self):
        for f,p in PINS.items():self.assertEqual(git_blob((ROOT/f).read_bytes()),p)

    def test_02_compose_idempotent(self):
        for source in SOURCES.values():
            self.assertEqual(compose(compose(source)),compose(source))

    def test_03_preserves_every_other_source_byte(self):
        for source in SOURCES.values():
            candidate=compose(source)
            restored=candidate.replace(SCORE+'\n','',1).replace('def _score_eventpath_reference(', 'def score(',1)
            self.assertEqual(restored,source)

    def test_04_rejects_method_drift(self):
        for source in SOURCES.values():
            bad=source.replace('own_cash+carry-other_cash, own_cash,other_cash,remaining',
                               'own_cash+carry, own_cash,other_cash,remaining')
            with self.assertRaises(ValueError):compose(bad)

    def test_05_reference_drift_is_not_idempotent(self):
        for source in SOURCES.values():
            bad=compose(source).replace('own_cash+carry-other_cash, own_cash,other_cash,remaining',
                                       'own_cash+carry, own_cash,other_cash,remaining')
            with self.assertRaises(ValueError):compose(bad)

    def test_06_duplicate_class_rejected(self):
        with self.assertRaises(ValueError):compose(SOURCES['scheduler.py']+'\nclass MarketPath: pass\n')

    def test_07_peer_methods_preserved(self):
        for source in SOURCES.values():
            # Disjoint source edits remain byte-for-byte, not rolled back.
            changed=source.replace('def _single(self, inv, quantity):','def _single(self, inv, quantity):\n        # peer receipt-prefix seam')
            self.assertIn('# peer receipt-prefix seam',compose(changed))

    def test_08_cli_nonoverwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'input.py';out=Path(tmp)/'output.py';src.write_text(SOURCES['scheduler.py'])
            command=[sys.executable,str(Path(__file__).with_name('build_score_eventpath.py')),str(src),str(out)]
            self.assertEqual(subprocess.run(command,capture_output=True).returncode,0)
            before=out.read_bytes()
            self.assertEqual(subprocess.run(command,capture_output=True).returncode,2)
            self.assertEqual(out.read_bytes(),before)
            self.assertEqual(subprocess.run(command[:-1]+[str(src)],capture_output=True).returncode,2)
            self.assertEqual(src.read_text(),SOURCES['scheduler.py'])

    def test_09_exhaustive_small_streams(self):
        # 2 sources x 3 alignments x 3 inventory levels x 4 quantities x
        # 3 starts x 2 terminal states x 8 plans x 4 rival streams = 13,824.
        for filename,(old,new) in MODULES.items():
            for align,inventory,q,now,terminal in itertools.product(
                    ['paired','before','after'],[9990,10000,10040],[0,1,3,8],[0,3,23],[False,True]):
                params=dict(inventory=inventory,now=now,end=now+4,shops=['SMOOTHIE_SHOP','SMOOTHIE_SHOP'])
                a,b=model(old,**params),model(new,**params)
                plans=[(),((now,q),),((now+4,q),),((now,q//2),(now+4,q-q//2)),
                       ((now-1,99),(now+5,99)),((now,-2),(now+1,q+4)),
                       ((now,2),(now,1)),((now+4,q),(now,q))]
                rivals=[0,3,((now+1,2),),((now-1,20),(now+3,3),(now+3,1))]
                for plan,r in itertools.product(plans,rivals):
                    self.assertEqual(a.score(plan,q,r,align,terminal),b.score(plan,q,r,align,terminal),
                                     (filename,params,q,plan,r,align,terminal))

    def test_10_seeded_all_products(self):
        rng=random.Random(9180316)
        for filename,(old,new) in MODULES.items():
            for i in range(800):
                now=rng.choice([0,1,22,23,24,95,708,716,718]);end=now+rng.randrange(25)
                q=rng.randrange(45)
                params=dict(item=rng.choice(['WHEAT','MILK','WOOL','EGG','CARROT','TOMATO','STRAWBERRY','MELON','FERTILIZER']),
                    inventory=rng.choice([-20,0,9990,10000,10020,10100,20000]),now=now,end=end,
                    shops=rng.choice([[],['SMOOTHIE_SHOP'],['BAKERY','FARMERS_MARKET'],['SMOOTHIE_SHOP','SMOOTHIE_SHOP','UNKNOWN']]),
                    config={'townShopSellInterval':rng.choice([1,3,4,8]),'townCenterSellInterval':rng.choice([1,5,24])})
                plan=tuple((rng.randrange(now-1,end+2),rng.randrange(-2,q+3)) for _ in range(rng.randrange(6)))
                rival=tuple((rng.randrange(now-1,end+2),rng.randrange(20)) for _ in range(rng.randrange(4)))
                args=(plan,q,rival,rng.choice(['paired','before','after']),rng.choice([False,True]))
                self.assertEqual(model(old,**params).score(*args),model(new,**params).score(*args),(filename,params,args))

    def test_11_mutable_absorption_context(self):
        for old,new in MODULES.values():
            a,b=model(old),model(new)
            for changes in [{'shops':['SMOOTHIE_SHOP']},{'shops':['SMOOTHIE_SHOP','SMOOTHIE_SHOP']},{'config':{'townShopSellInterval':3}},
                            {'now':23,'end':35},{'config':{'townCenterSellInterval':3}},
                            {'item':'FERTILIZER'},{'inventory':20000},{'now':716,'end':718}]:
                for k,v in changes.items():setattr(a,k,copy.deepcopy(v));setattr(b,k,copy.deepcopy(v))
                args=(((a.now,3),(a.end,9)),12,((a.now+1,4),),'paired',False)
                self.assertEqual(a.score(*args),b.score(*args))

    def test_12_fallback_values_and_errors(self):
        cases=[((),-1,0,'paired',False),((),1.5,0,'paired',False),(((0,1.5),),3,0,'paired',False),
               (((0,1),),3,-1,'before',False),(((0,1),),3,0.5,'paired',False),
               ((('unused',3),),4,0,'paired',False),(((False,2),),3,0,'paired',False),
               (((0,1),),3,((False,1),),'paired',False)]
        for old,new in MODULES.values():
            for args in cases:
                a,b=model(old),model(new)
                self.assertEqual(outcome(lambda:a.score(*args)),outcome(lambda:b.score(*args)),args)

    def test_13_empty_horizon(self):
        for old,new in MODULES.values():
            for now,end in [(8,7),(718,717)]:
                a,b=model(old,now=now,end=end),model(new,now=now,end=end)
                for terminal in [False,True]:self.assertEqual(a.score(((now,3),),8,4,'paired',terminal),b.score(((now,3),),8,4,'paired',terminal))

    def test_14_single_tick(self):
        for old,new in MODULES.values():
            for now in [0,1,23,24,718]:
                a,b=model(old,now=now,end=now),model(new,now=now,end=now)
                self.assertEqual(a.score(((now,3),),8,4,'paired'),b.score(((now,3),),8,4,'paired'))

    def test_15_generator_plan_fallback(self):
        for old,new in MODULES.values():
            a,b=model(old),model(new)
            self.assertEqual(a.score(iter([(0,3),(8,2)]),8,1,'paired'),b.score(iter([(0,3),(8,2)]),8,1,'paired'))

    def test_16_string_intervals_preserved(self):
        for old,new in MODULES.values():
            for cfg in [{'townShopSellInterval':'3'}, {'townCenterSellInterval':'24'}, {'townShopSellInterval':0}]:
                a,b=model(old,config=cfg),model(new,config=cfg)
                self.assertEqual(outcome(lambda:a.score(((8,4),),8,1,'paired')),outcome(lambda:b.score(((8,4),),8,1,'paired')))

    def test_17_joint_call_reduction_is_measured(self):
        for old,new in MODULES.values():
            a,b=model(old),model(new);calls=[0,0]
            for i,m in enumerate([a,b]):
                original=m.joint
                def wrapped(*args,index=i,fn=original):calls[index]+=1;return fn(*args)
                m.joint=wrapped
            args=(((0,4),(8,8)),12,((1,3),),'paired',False)
            self.assertEqual(a.score(*args),b.score(*args));self.assertEqual(calls,[9,3])

    def test_18_cache_invalidates_inplace_shops(self):
        for old,new in MODULES.values():
            a,b=model(old,shops=[]),model(new,shops=[])
            args=(((8,10),),10,0,'paired')
            self.assertEqual(a.score(*args),b.score(*args))
            a.shops.append('SMOOTHIE_SHOP');b.shops.append('SMOOTHIE_SHOP')
            self.assertEqual(a.score(*args),b.score(*args))

    def test_19_optimizer_full_result_and_callback_order(self):
        for filename,(old,new) in MODULES.items():
            rules=['strict','expected_downside','minimax_regret'] if filename.startswith('selected') else ['strict']
            for rule,now,q,item,forced in itertools.product(rules,[0,23,710],[3,12],['MILK','FERTILIZER'],[False,True]):
                calls=[[],[]];outputs=[]
                for i,mod in enumerate([old,new]):
                    def capacity(plan):
                        calls[i].append(plan)
                        return not forced or dict(plan).get(now,0)>=q//2
                    outputs.append(mod.optimize_lot(item=item,quantity=q,inventory=10010,params=None,shops=['SMOOTHIE_SHOP'],
                        config={'sellAcceptanceRule':rule,'sellDownsideBound':20},now=now,dates=[now,now+1,now+8],
                        reference=((now,0),(now+8,q)) if forced else ((now,q),),rival_quantity=4,capacity_ok=capacity))
                self.assertEqual(outputs[0],outputs[1],(filename,rule,now,q,item,forced))
                self.assertEqual(calls[0],calls[1],(filename,rule,now,q,item,forced))

    def test_20_optimizer_terminal_and_minimum(self):
        for old,new in MODULES.values():
            for now,q,minimum in itertools.product([716,718],[0,6],[0,2]):
                args=dict(item='MILK',quantity=q,inventory=10002,params=None,shops=['SMOOTHIE_SHOP'],config={},now=now,
                    dates=sorted({now,718}),reference=((now,q),),rival_quantity=3,minimum_now=minimum)
                self.assertEqual(old.optimize_lot(**args),new.optimize_lot(**args))

    def test_21_official_market_and_town_consumption(self):
        import importlib.util
        directory=ROOT/'checks/reference'
        pins={
            'engine/kaggriculture.py':'3c202c7ee921da239356789e266b694635103fc4',
            'engine/kaggriculture.json':'b354d06b742fe48402513792253f1a5c29366b20',
            'evaluator/evaluate.py':'1fb6b655bb4ca1e1684be165a8ef513e2e6c2325',
            'evaluator/loader.py':'23948e10cfc3d32f46c9abb1321b0d8fc8db21d5'}
        for path,pin in pins.items():self.assertEqual(git_blob((directory/path).read_bytes()),pin)
        spec=importlib.util.spec_from_file_location('eventpath_official_evaluator',directory/'evaluator/evaluate.py')
        ev=importlib.util.module_from_spec(spec);spec.loader.exec_module(ev)
        engine,_=ev.get_engine(directory/'engine',directory/'evaluator/loader.py')
        S=ev.Struct
        cells=0
        for seat,item,now,inventory,align,terminal in itertools.product(
                [0,1],['MILK','WOOL','FERTILIZER'],[3,23],[10030,10075,10100],
                ['paired','before','after'],[False,True]):
            cfg=S({k:v.get('default') if isinstance(v,dict) else v
                   for k,v in engine.specification['configuration'].items()})
            farms=[engine._new_farm(10,0),engine._new_farm(10,0)]
            market=engine._new_market();market['inventory'][item]=inventory;engine._refresh_prices(market)
            shops=['SMOOTHIE_SHOP','SMOOTHIE_SHOP','YARN_STORE']
            town={'unlocked_shops':shops}
            state=[]
            for player in [0,1]:
                private=engine._new_private();private['shed'][item]=12 if player==seat else 5
                state.append(S(observation=S(player=player,step=now,day=now//24,hour=now%24,
                    farms=farms,private=private,market=market,town=town),
                    action={'farmer':['PASS'],'hands':[],'market':[]},status='ACTIVE',reward=0))
            env=S(configuration=cfg,done=False,info={'seed':9180316})
            plan=((now,4),(now+8,5));rival=((now,3),(now+7,2))
            for step in range(now,now+9):
                q=dict(plan).get(step,0);r=dict(rival).get(step,0)
                own=[['SELL',item,q]];other=[['SELL',item,r]]
                if align=='after':other=[[]]+other
                if align=='before':own=[[]]+own
                state[seat].action['market']=own;state[1-seat].action['market']=other
                engine._process_market(state,env);engine._town_consume(env,state,step)
            cash=farms[seat]['money'];othercash=farms[1-seat]['money']
            remaining=state[seat].observation.private['shed'][item]
            post_inventory=market['inventory'][item]
            carry=0.0
            if not terminal:
                state[seat].action['market']=[['SELL',item,remaining]]
                state[1-seat].action['market']=[]
                engine._process_market(state,env)
                carry=float(farms[seat]['money']-cash)
            expected=(cash+carry-othercash,cash,othercash,remaining)
            for filename,(old,new) in MODULES.items():
                for mod in [old,new]:
                    m=model(mod,item=item,inventory=inventory,shops=shops,now=now,end=now+8)
                    self.assertEqual(m.score(plan,12,rival,align,terminal),expected,
                                     (filename,seat,item,now,inventory,align,terminal,post_inventory))
            cells+=1
        self.assertEqual(cells,216)

    def test_22_absorption_phase_mutant_rejected(self):
        for filename,source in SOURCES.items():
            bad=compose(source).replace('used = prefix[step]',
                'used = prefix.get(step + 1, self._eventpath_total)')
            mutant=load(bad,'eventpath_bad_phase_'+filename,ROOT/filename)
            old,_=MODULES[filename]
            kw=dict(item='MILK',inventory=10030,shops=['SMOOTHIE_SHOP']*4,now=4,end=12)
            args=(((4,6),(12,6)),12,0,'paired',False)
            self.assertNotEqual(model(old,**kw).score(*args),model(mutant,**kw).score(*args))

    def test_23_carry_tail_mutant_rejected(self):
        for filename,source in SOURCES.items():
            bad=compose(source).replace('inv -= self._eventpath_total - consumed','inv -= 0')
            mutant=load(bad,'eventpath_bad_tail_'+filename,ROOT/filename)
            old,_=MODULES[filename]
            kw=dict(item='MILK',inventory=10030,shops=['SMOOTHIE_SHOP']*4,now=4,end=12)
            args=(((4,3),),12,0,'paired',False)
            self.assertNotEqual(model(old,**kw).score(*args),model(mutant,**kw).score(*args))

    def test_24_missing_rival_event_mutant_rejected(self):
        for filename,source in SOURCES.items():
            bad=compose(source).replace('events = orders.keys() | rivals.keys()','events = orders.keys()')
            mutant=load(bad,'eventpath_bad_rival_'+filename,ROOT/filename)
            old,_=MODULES[filename]
            args=(((8,12),),12,((4,8),),'paired',False)
            self.assertNotEqual(model(old).score(*args),model(mutant).score(*args))

    def test_25_rejects_decorated_score(self):
        for source in SOURCES.values():
            with self.assertRaises(ValueError):
                compose(source.replace('    def score(', '    @staticmethod\n    def score(',1))

    def test_26_rejects_absorption_drift(self):
        for source in SOURCES.values():
            with self.assertRaises(ValueError):
                compose(source.replace("if item!='FERTILIZER'", "if item!='WHEAT'",1))

if __name__=='__main__':unittest.main(verbosity=2)
