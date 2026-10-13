# SPDX-License-Identifier: Apache-2.0
"""Pinned full-interpreter evidence for the native two-scan route-boundary repair.

Run with TITAN_PACKAGE pointing at the extracted, unmodified b567 package.
Synthetic worlds demonstrate mechanism correctness, not natural engagement/EV.
"""
from __future__ import annotations

import ast
from collections import Counter
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import types
import unittest

from spatial_hire_prefix import NEW, OLD, PREIMAGE_SHA256, repaired_source

if not os.environ.get('TITAN_PACKAGE'):
    raise RuntimeError('Set TITAN_PACKAGE to the extracted pristine b567 archive')
ROOT = Path(os.environ['TITAN_PACKAGE']).resolve()
SOURCE_MANIFEST_SHA256 = 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'
manifest_bytes = (ROOT/'SOURCE.json').read_bytes()
if hashlib.sha256(manifest_bytes).hexdigest() != SOURCE_MANIFEST_SHA256:
    raise RuntimeError('SOURCE.json changed: expected exact b567 runtime map')
PINS = {
    'checks/reference/engine/kaggriculture.py': 'bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e',
    'checks/reference/engine/utils.py': '537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b',
    'checks/reference/engine/kaggriculture.json': 'a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867',
    'checks/reference/evaluator/evaluate.py': 'e30b3108e0027477ab7ddbc057892a241c41a1f2b38f72caf267477877c4333c',
    'checks/reference/evaluator/loader.py': 'cd113a94ae99b03492502e425bdcf09c3db17a2aa2a8fd866f0d78caec9e311e',
}
for relative, digest in PINS.items():
    if hashlib.sha256((ROOT/relative).read_bytes()).hexdigest() != digest:
        raise RuntimeError('test input changed: '+relative)
# Verify every package runtime input, not just the module under repair.
MANIFEST = json.loads(manifest_bytes)
for relative, record in MANIFEST['runtime'].items():
    data = (ROOT/relative).read_bytes()
    if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
        raise RuntimeError('runtime input changed: '+relative)

# Authenticate dependencies before importing or executing any package code.
sys.path[:0] = [str(ROOT), str(ROOT/'checks')]
import mechanics as mechanics
import test_weed_continuation as weed
from scheduler import parent

SOURCE = (ROOT/'spatial_tempo.py').read_bytes()
PATCHED = repaired_source(SOURCE)


def module_from(data: bytes, name: str):
    module = types.ModuleType(name)
    module.__file__ = str(ROOT/'spatial_tempo.py')
    exec(compile(data, module.__file__, 'exec'), module.__dict__)
    return module


BASE = module_from(SOURCE, '_thistle_base')
FIX = module_from(PATCHED, '_thistle_fix')
COUNTS = Counter()
CAPS = (None, -3, 0, 1, 2, 5, 10, 12)
POISON_CAPS = ('2', 2.9, False, True)


class SpatialHirePrefixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        weed.WeedContinuationTests.setUpClass()
        cls.fixture_owner = weed.WeedContinuationTests()
        cls.engine = cls.fixture_owner.engine
        cls.helper = cls.fixture_owner.helper

    def fixture(self, cap=10, seat=0, obligation=('BUILD_PASTURE',)):
        obs, cfg, route = self.fixture_owner.fixture(obligation)
        # Keep all original timing and non-target actors, remove synthetic sales.
        for row in route:
            row['market'] = []
        if cap is None:
            cfg.pop('maxMarketOrdersPerTurn', None)
        else:
            cfg['maxMarketOrdersPerTurn'] = cap
        if seat:
            obs['farms'] = [deepcopy(obs['farms'][1]), deepcopy(obs['farms'][0])]
            obs['player'] = seat
        return obs, cfg, route

    def owner(self, module, obs, cfg, route):
        p = weed.CountingParent()
        p.R = {'case': deepcopy(route)}
        p.cur = 'case'
        budget = weed.BUDGET(p.R)
        owner = module.SpatialTempo(mechanics, pathing=False, tempo=False,
                                   seed_reserve=budget.remaining)
        owner.configure(cfg)
        owner.install(p)
        return p, owner

    def direct(self, module, obs, cfg, route, market):
        p, owner = self.owner(module, obs, cfg, route)
        # Exercise the selected-action scan independently from Arlene's own cap.
        selected = deepcopy(route[28]); selected['farmer'] = ['DIG']
        selected['market'] = deepcopy(market)
        before = deepcopy((obs, selected))
        returned = owner.transform(obs, selected, p)
        self.assertIs(returned, selected)
        self.assertEqual((obs, selected), before)
        return owner

    def test_exact_source_transform_and_other_methods_unchanged(self):
        self.assertEqual(hashlib.sha256(SOURCE).hexdigest(), PREIMAGE_SHA256)
        self.assertEqual(SOURCE.count(OLD.encode()), 1)
        self.assertEqual(PATCHED.count(NEW.encode()), 1)
        self.assertEqual(PATCHED.replace(NEW.encode(), OLD.encode()), SOURCE)
        def methods(data):
            tree=ast.parse(data)
            return {n.name:ast.dump(n, include_attributes=False)
                    for top in tree.body if isinstance(top, ast.ClassDef)
                    for n in top.body if isinstance(n, ast.FunctionDef)}
        a,b=methods(SOURCE),methods(PATCHED)
        self.assertEqual(set(a),set(b))
        self.assertEqual([key for key in a if a[key]!=b[key]], ['transform'])

    def test_source_drift_and_repeat_are_rejected_even_optimized(self):
        for source in (SOURCE+b'\n', PATCHED, SOURCE.replace(b'market_limit', b'other_limit')+b'# drift\n'):
            with self.assertRaises(ValueError): repaired_source(source)
        with self.assertRaises(TypeError): repaired_source(SOURCE.decode())

    def test_current_selected_scan_uses_raw_prefix(self):
        for cap in CAPS:
            limit=max(1,10 if cap is None else cap)
            for seat in (0,1):
                for filler in (['PASS'], [], ['SELL','WHEAT',0]):
                    obs,cfg,route=self.fixture(cap,seat)
                    market=[deepcopy(filler) for _ in range(limit)]+[['HIRE']]
                    with self.subTest(cap=cap,seat=seat,filler=filler):
                        self.assertFalse(self.direct(BASE,obs,cfg,route,market).plans)
                        self.assertTrue(self.direct(FIX,obs,cfg,route,market).plans)
                        self.assertTrue(self.direct(FIX,obs,cfg,route,market[:limit]).plans)
                        COUNTS['selected_suffix_cases']+=1

    def test_future_authored_scan_uses_raw_prefix(self):
        for cap in CAPS:
            limit=max(1,10 if cap is None else cap)
            for seat in (0,1):
                for step in (28,29,30,31):
                    obs,cfg,route=self.fixture(cap,seat)
                    route[step]['market']=[['PASS'] for _ in range(limit)]+[['HIRE']]
                    with self.subTest(cap=cap,seat=seat,step=step):
                        old,old_owner=self.owner(BASE,obs,cfg,route);old.act(deepcopy(obs))
                        fixed,new_owner=self.owner(FIX,obs,cfg,route);fixed.act(deepcopy(obs))
                        self.assertFalse(old_owner.plans)
                        self.assertTrue(new_owner.plans)
                        # Source rows and all unrelated actors/markets stay exact.
                        for tick in range(28,34):
                            self.assertEqual(fixed.R['case'][tick]['market'],route[tick]['market'])
                            self.assertEqual(fixed.R['case'][tick]['hands'],route[tick]['hands'])
                        COUNTS['route_suffix_cases']+=1

    def test_noninteger_market_caps_fail_closed(self):
        for cap in POISON_CAPS:
            coerced_limit=max(1,int(cap))
            for seat in (0,1):
                obs,cfg,route=self.fixture(cap,seat)
                market=[['PASS'] for _ in range(coerced_limit)]+[['HIRE']]
                with self.subTest(cap=cap,seat=seat):
                    self.assertFalse(self.direct(FIX,obs,cfg,route,market).plans)
                    route[30]['market']=deepcopy(market)
                    p,o=self.owner(FIX,obs,cfg,route);p.act(deepcopy(obs))
                    self.assertFalse(o.plans)
                    COUNTS['poison_cap_fail_closed_cases']+=1

    def test_every_live_hire_slot_remains_a_boundary(self):
        for cap in CAPS:
            limit=max(1,10 if cap is None else cap)
            for slot in range(limit):
                for seat in (0,1):
                    obs,cfg,route=self.fixture(cap,seat)
                    market=[[] for _ in range(slot)]+[['HIRE']]
                    with self.subTest(cap=cap,slot=slot,seat=seat):
                        self.assertFalse(self.direct(FIX,obs,cfg,route,market).plans)
                        route[30]['market']=market
                        p,o=self.owner(FIX,obs,cfg,route);p.act(obs)
                        self.assertFalse(o.plans)
                        COUNTS['live_hire_controls']+=1

    def state(self,obs,cfg,step):
        state,env=self.helper.fixture(step=step,cash=100000)
        state[0].observation.farms=deepcopy(obs['farms'])
        for side in (0,1):
            state[side].observation.farms=state[0].observation.farms
        state[obs['player']].observation.private=deepcopy(obs['private'])
        env.configuration=self.fixture_owner.ev.Struct(deepcopy(cfg))
        return state,env

    def advance(self,state,env,step,seat,action):
        for side in (0,1):
            state[side].observation.step=step
            state[side].observation.day=step//24
            state[side].observation.hour=step%24
            state[side].action={'farmer':['PASS'],'hands':[],'market':[]}
        state[seat].action=deepcopy(action)
        self.engine.interpreter(state,env)
        COUNTS['official_interpreter_calls']+=1

    def test_full_engine_suffix_invariance_and_executable_hire_controls(self):
        for cap in CAPS:
            limit=max(1,10 if cap is None else cap)
            for seat in (0,1):
                for filler in ([],['PASS'],['SELL','WHEAT',0]):
                    obs,cfg,_=self.fixture(cap,seat)
                    left,le=self.state(obs,cfg,28);right,re=self.state(obs,cfg,28)
                    market=[deepcopy(filler) for _ in range(limit)]+[['HIRE']]
                    self.advance(left,le,28,seat,{'market':market})
                    self.advance(right,re,28,seat,{'market':market[:limit]})
                    self.assertEqual([s.observation for s in left],[s.observation for s in right])
                    self.assertEqual(len(left[0].observation.farms[seat]['hands']),2)
                    COUNTS['engine_suffix_pairs']+=1
                live,env=self.state(obs,cfg,28)
                self.advance(live,env,28,seat,{'market':[[]]*(limit-1)+[['HIRE']]})
                self.assertEqual(len(live[0].observation.farms[seat]['hands']),3)
                COUNTS['engine_hire_controls']+=1

    def test_full_engine_rejoin_builds_or_plants_in_both_seats(self):
        for seat in (0,1):
            for obligation in (('BUILD_PASTURE',),('BUILD_COOP',),('PLANT','WHEAT')):
                for market_step in (28,29,30,31):
                    obs,cfg,route=self.fixture(10,seat,obligation)
                    route[market_step]['market']=[['PASS'] for _ in range(10)]+[['HIRE']]
                    arms=[]
                    for module,trim in ((BASE,False),(FIX,False),(BASE,True)):
                        use=deepcopy(route)
                        if trim:use[market_step]['market']=use[market_step]['market'][:10]
                        p,owner=self.owner(module,obs,cfg,use)
                        state,env=self.state(obs,cfg,28)
                        outputs=[]
                        for step in range(28,34):
                            current=deepcopy(state[seat].observation)
                            current['step']=step;current['day']=step//24;current['hour']=step%24
                            action=p.act(current)
                            outputs.append(deepcopy(action))
                            owner.finish(current,action)
                            self.advance(state,env,step,seat,action)
                        arms.append((state,outputs))
                    baseline,candidate,reference=arms
                    with self.subTest(seat=seat,obligation=obligation,market_step=market_step):
                        self.assertEqual([s.observation for s in candidate[0]],
                                         [s.observation for s in reference[0]])
                        self.assertEqual(candidate[1],reference[1])
                        base_farm=baseline[0][0].observation.farms[seat]
                        fixed_farm=candidate[0][0].observation.farms[seat]
                        self.assertIsNone(base_farm['tiles'][4][2])
                        expected='PLANT' if obligation[0]=='PLANT' else obligation[0][6:]
                        self.assertEqual(fixed_farm['tiles'][4][2]['kind'],expected)
                        self.assertEqual(base_farm['farmer'],fixed_farm['farmer'])
                        self.assertEqual(base_farm['hands'],fixed_farm['hands'])
                        self.assertEqual(base_farm['money'],fixed_farm['money'])
                        self.assertEqual(len(fixed_farm['hands']),2)
                        if expected=='PLANT':
                            self.assertTrue(fixed_farm['tiles'][4][2]['watered_today'])
                        COUNTS['full_route_three_arm_worlds']+=1

    def test_guard_mutants_are_killed(self):
        global FIX
        text = PATCHED.decode()
        mutants = {
            'selected_full_vector': text.replace("selected.get('market',[])[:market_limit]", "selected.get('market',[])"),
            'route_full_vector': text.replace("route[step].get('market',[])[:market_limit]", "route[step].get('market',[])"),
            'off_by_one': text.replace('[:market_limit]', '[:market_limit+1]'),
            'filter_before_cap': text.replace("selected.get('market',[])[:market_limit]", "[x for x in selected.get('market',[]) if x][:market_limit]").replace("route[step].get('market',[])[:market_limit]", "[x for x in route[step].get('market',[]) if x][:market_limit]"),
            'zero_minimum': text.replace('market_limit=max(1,raw_market_limit)', 'market_limit=max(0,raw_market_limit)'),
            'coerce_type_poison': text.replace("if type(raw_market_limit) is not int:return selected\n        market_limit=max(1,raw_market_limit)", "market_limit=max(1,int(raw_market_limit))"),
        }
        original = FIX
        snapshot = COUNTS.copy()
        killed = {}
        try:
            for name, mutant in mutants.items():
                FIX = module_from(mutant.encode(), '_thistle_mutant_'+name)
                suite = unittest.TestSuite(SpatialHirePrefixTests(test) for test in (
                    'test_current_selected_scan_uses_raw_prefix',
                    'test_future_authored_scan_uses_raw_prefix',
                    'test_noninteger_market_caps_fail_closed',
                    'test_every_live_hire_slot_remains_a_boundary'))
                result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
                self.assertFalse(result.wasSuccessful(), name)
                self.assertEqual(len(result.errors), 0, name)
                self.assertGreater(len(result.failures), 0, name)
                killed[name] = len(result.failures)
        finally:
            FIX = original
            COUNTS.clear()
            COUNTS.update(snapshot)
        COUNTS['behavioral_mutants_killed'] = len(killed)
        print('THISTLE_MUTANTS='+json.dumps(killed,sort_keys=True))

    def test_current_pristine_route_census_is_explicitly_zero_engagement(self):
        p=parent.Agent()
        rows=[row for route in p.R.values() for row in route]
        tails=[(name,step,slot) for name,route in p.R.items() for step,row in enumerate(route)
               for slot,action in enumerate(row.get('market',[]))
               if action and action[0]=='HIRE' and slot>=10]
        self.assertEqual(len(p.R),4)
        self.assertEqual(len(rows),2880)
        self.assertEqual(tails,[])
        COUNTS['pristine_routes']=len(p.R)
        COUNTS['pristine_rows']=len(rows)
        COUNTS['pristine_hire_tails']=len(tails)


if __name__=='__main__':
    result=unittest.main(exit=False,verbosity=2).result
    print('THISTLE_COUNTS='+json.dumps(dict(COUNTS),sort_keys=True))
    sys.exit(0 if result.wasSuccessful() else 1)