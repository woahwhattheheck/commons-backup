# SPDX-License-Identifier: Apache-2.0
"""S1 component and unmodified full-interpreter acceptance; no skipped tests."""
from __future__ import annotations
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import random
import unittest

import native_s1_experiment as s1
import run_native_experiment as runner

ROOT = Path(os.environ['S1_RUNTIME']).resolve()
ENGINE_CALLS = 0


class NativeS1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.authenticated = runner.authenticate(ROOT)
        cls.loader = runner.load(ROOT/'checks/reference/evaluator/loader.py', '_s1_test_loader')
        cls.engine, _ = cls.loader.get_engine(ROOT/'checks/reference/engine')

    def world(self, seat=0, step=110, animals=True):
        cfg = self.loader.Struct()
        for key, value in self.engine.specification['configuration'].items():
            cfg[key] = value.get('default') if isinstance(value, dict) else value
        cfg.seed = 27
        env = self.loader.Struct(configuration=cfg, done=False, info={})
        state = [self.loader.Struct(observation=self.loader.Struct(), action={},
                                    status='ACTIVE', reward=0) for _ in range(2)]
        self.advance(state, env, initialize=True)
        for a in state:
            a.observation.step = step
            a.observation.day, a.observation.hour = divmod(step, 24)
        farm = state[seat].observation.farms[seat]
        farm['money'] = 5000.
        if animals:
            farm['unlocked_quadrants'] = ['NW', 'NE', 'SW']
            for x, y in [(4,4), (5,4), (4,5), (3,4), (4,3), (3,3)]:
                animal = self.engine._new_animal('COW', 0)
                animal['fertilizer_available'] = True
                farm['tiles'][y][x] = animal
        return state, env, cfg

    def advance(self, state, env, actions=None, initialize=False):
        global ENGINE_CALLS
        if actions is not None:
            for actor, action in zip(state, actions):
                actor.action = deepcopy(action)
        self.engine.interpreter(state, env)
        ENGINE_CALLS += 1
        if not initialize:
            for actor in state:
                actor.observation.step += 1
        return state

    @staticmethod
    def passes(obs=None, cfg=None):
        n = len(obs['farms'][obs['player']]['hands']) if obs else 0
        return {'farmer': ['PASS'], 'hands': [['PASS'] for _ in range(n)], 'market': []}

    @staticmethod
    def tape():
        return [{'farmer': ['PASS'], 'hands': [], 'market': []} for _ in range(720)]

    def test_01_native_inputs_authenticated(self):
        self.assertEqual(self.authenticated, 109)

    def test_02_off_is_identical_callable_and_on_literal(self):
        parent = lambda o,c: {'unique': object()}
        self.assertIs(s1.install(parent, lambda:None), parent)
        for value in [None, 0, 1, '', 'true', {}, []]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                s1.install(parent, lambda:None, enabled=value)

    def test_03_positive_both_seats(self):
        for seat in (0,1):
            state, _, cfg = self.world(seat)
            gate = s1.assess(state[seat].observation, self.passes(), cfg, [self.tape()])
            self.assertTrue(gate.allowed)
            self.assertGreaterEqual(gate.units, 2)
            self.assertEqual(gate.hire_cost, 1)

    def test_04_complete_day_required(self):
        state, _, cfg = self.world()
        for length in range(110,120):
            with self.subTest(length=length):
                self.assertFalse(s1.assess(state[0].observation, self.passes(), cfg,
                                          [self.tape()[:length]]).allowed)
        self.assertTrue(s1.assess(state[0].observation, self.passes(), cfg,
                                 [self.tape()[:120]]).allowed)

    def test_05_all_route_choices_required(self):
        state, _, cfg = self.world()
        tape = self.tape()
        tape[119]['market'] = [['HIRE']]
        self.assertEqual(s1.assess(state[0].observation, self.passes(), cfg,
                                  [self.tape(), tape]).reason, 'future-market-or-schema')

    def test_06_current_and_future_collection_conflicts(self):
        state, _, cfg = self.world()
        for actor in ('farmer', 'hands'):
            action = self.passes()
            action[actor] = ['COLLECT_FERTILIZER'] if actor == 'farmer' else [['COLLECT_FERTILIZER']]
            self.assertEqual(s1.assess(state[0].observation, action, cfg,
                                      [self.tape()]).reason, 'current-collection')
            tape = self.tape()
            tape[119] = action
            self.assertEqual(s1.assess(state[0].observation, self.passes(), cfg,
                                      [tape]).reason, 'future-collection')

    def test_07_future_wheat_and_all_spending_ops(self):
        state, _, cfg = self.world()
        for op in ['HIRE','BUY_LAND','BUY_PRODUCT','BUY_SEED','BUY_ANIMAL','UNKNOWN']:
            tape = self.tape()
            tape[119]['market'] = [[op, 'WHEAT', 1]]
            self.assertFalse(s1.assess(state[0].observation, self.passes(), cfg,[tape]).allowed)
        tape = self.tape()
        tape[119]['hands'] = [['PICKUP', 'WHEAT', 1]]
        self.assertEqual(s1.assess(state[0].observation, self.passes(), cfg,[tape]).reason,
                         'future-wheat-pickup')

    def test_08_raw_market_cap_not_compacted(self):
        state, _, cfg = self.world()
        action = self.passes()
        action['market'] = [[] for _ in range(10)]
        self.assertFalse(s1.assess(state[0].observation, action, cfg,[self.tape()]).allowed)
        action['market'].pop()
        self.assertTrue(s1.assess(state[0].observation, action, cfg,[self.tape()]).allowed)

    def test_09_phase_all_days_hours(self):
        state, _, cfg = self.world()
        obs = state[0].observation
        for step in range(720):
            obs.step = step
            gate = s1.assess(obs, self.passes(), cfg,[self.tape()])
            day, hour = divmod(step, 24)
            if not (4 <= day <= 23 and 14 <= hour < 23):
                self.assertEqual(gate.reason, 'phase')
            # SE exclusion makes worst-spawn reach impossible with one turn left.
            if 4 <= day <= 23 and hour == 22:
                self.assertEqual(gate.reason, 'reachability')

    def test_10_config_custom_and_bool_fields_fail(self):
        state, _, cfg = self.world()
        for key in s1.STANDARD:
            for value in (True, None, str(cfg[key]), cfg[key]+1):
                bad = dict(cfg, **{key: value})
                self.assertEqual(s1.assess(state[0].observation,self.passes(),bad,[self.tape()]).reason,
                                 'configuration')
        self.assertFalse(s1.standard(dict(cfg,marketParams={'WHEAT': {}})))

    def test_11_all_animal_kinds_and_se_exclusion(self):
        state, _, _ = self.world()
        farm = state[0].observation.farms[0]
        farm['tiles'] = [[None]*10 for _ in range(10)]
        for x,a in enumerate(('GOOSE','COW','SHEEP')):
            tile = self.engine._new_animal(a,0)
            tile['fertilizer_available'] = True
            farm['tiles'][4][x+2] = tile
        se = self.engine._new_animal('COW',0)
        se['fertilizer_available'] = True
        farm['tiles'][5][5] = se
        self.assertEqual(s1.targets(farm),[(2,4),(3,4),(4,4)])
        farm['tiles'][4][2]['kind'] = 'PASTURE'
        self.assertEqual(s1.targets(farm),[(3,4),(4,4)])

    def test_12_numeric_fail_closed(self):
        state, _, cfg = self.world()
        obs = state[0].observation
        for cash in (True, -1, float('nan'), float('inf'), 10**10000, '5000'):
            with self.subTest(type=type(cash).__name__):
                obs.farms[0]['money'] = cash
                self.assertFalse(s1.assess(obs,self.passes(),cfg,[self.tape()]).allowed)
        obs.farms[0]['money'] = 5000
        for hires in (True,-1,241,'1'):
            obs.farms[0]['hires_today'] = hires
            self.assertFalse(s1.assess(obs,self.passes(),cfg,[self.tape()]).allowed)
        obs.farms[0]['hires_today'] = 0
        obs.market['prices']['FERTILIZER'] = 10**10000
        self.assertEqual(s1.assess(obs,self.passes(),cfg,[self.tape()]).reason,'numeric')

    def test_13_reserve_and_stock_boundaries(self):
        state, _, cfg = self.world()
        obs = state[0].observation
        obs.farms[0]['money'] = 101
        self.assertTrue(s1.assess(obs,self.passes(),cfg,[self.tape()]).allowed)
        self.assertFalse(s1.assess(obs,self.passes(),cfg,[self.tape()],reserve=1000).allowed)
        obs.farms[0]['money'] = 1001
        gate = s1.assess(obs,self.passes(),cfg,[self.tape()])
        obs.private['shed']['WHEAT'] = 88-gate.units
        self.assertTrue(s1.assess(obs,self.passes(),cfg,[self.tape()]).allowed)
        obs.private['shed']['WHEAT'] += 1
        self.assertEqual(s1.assess(obs,self.passes(),cfg,[self.tape()]).reason,'headroom')
        for bad in (True,99,None,float('inf')):
            self.assertFalse(s1.assess(obs,self.passes(),cfg,[self.tape()],reserve=bad).allowed)

    def test_14_actor_and_private_shape(self):
        state, _, cfg = self.world()
        for change in ('inventory','coordinate','player','quantity'):
            obs = deepcopy(state[0].observation)
            if change == 'inventory': obs.private['inventories'].append({})
            if change == 'coordinate': obs.farms[0]['farmer'] = [True,4]
            if change == 'player': obs.player = True
            if change == 'quantity': obs.private['shed']['WHEAT'] = -1
            self.assertEqual(s1.assess(obs,self.passes(),cfg,[self.tape()]).reason,'observation')

    def test_15_parent_view_detached_and_correct_inventory(self):
        state, _, _ = self.world()
        obs = state[0].observation
        obs.farms[0]['hands'] = [[1,1],[2,2],[3,3]]
        obs.private['inventories'] = [{'EGG':1},{'EGG':2},{'EGG':3},{'EGG':4}]
        before = deepcopy(obs)
        view = s1.parent_view(obs,1)
        self.assertEqual(view.farms[0]['hands'], [[1,1],[3,3]])
        self.assertEqual(view.private['inventories'], [{'EGG':1},{'EGG':2},{'EGG':4}])
        view.farms[0]['tiles'][4][4]['animal'] = 'SHEEP'
        view.private['shed']['EGG'] = 123
        self.assertEqual(obs,before)

    def test_16_short_invalid_and_ghost_remap(self):
        self.assertEqual(s1.remap({'hands': []},3,['PASS'])['hands'],[['PASS']]*4)
        self.assertEqual(s1.remap({'hands': None},2,['WEST'])['hands'],[['PASS'],['PASS'],['WEST']])
        original = {'farmer':None,'hands':[['NORTH'],None,['PLANT','WHEAT'],[]], 'market':[[],['SELL','EGG',1]]}
        before = deepcopy(original)
        result = s1.remap(original,1,['COLLECT_FERTILIZER'])
        self.assertEqual(result['hands'],[['NORTH'],['COLLECT_FERTILIZER'],None,['PLANT','WHEAT'],[]])
        self.assertEqual(original,before)
        self.assertEqual(result['market'],original['market'])
        for command in (['PLANT','WHEAT'],['DROP'],[],None):
            with self.assertRaises(ValueError): s1.remap(original,1,command)

    def test_17_full_engine_raw_actor_remap_matrix(self):
        rng = random.Random(57013)
        choices = [['PASS'],['NORTH'],[],['PLANT','WHEAT'],None,['HARVEST'],['WEST']]
        for seat in (0,1):
            for n in range(5):
                for index in range(n+1):
                    for length in range(n+4):
                        base, env, _ = self.world(seat,animals=False)
                        farm, private = base[seat].observation.farms[seat],base[seat].observation.private
                        farm['hands'] = [[1+i%3,1+i//3] for i in range(n)]
                        private['inventories'] += [{} for _ in range(n)]
                        private['seeds']['WHEAT'] = 2
                        actual = deepcopy(base)
                        actual[seat].observation.farms[seat]['hands'].insert(index,[4,4])
                        actual[seat].observation.private['inventories'].insert(index+1,{'FERTILIZER':3})
                        action = {'farmer':['PASS'],'hands':[deepcopy(rng.choice(choices)) for _ in range(length)],'market':[]}
                        pair = [self.passes(),self.passes()]
                        pair[seat] = action
                        self.advance(base,deepcopy(env),pair)
                        pair[seat] = s1.remap(action,index,['PASS'])
                        self.advance(actual,deepcopy(env),pair)
                        projected = s1.parent_view(actual[seat].observation,index)
                        self.assertEqual(projected,base[seat].observation)
                        self.assertEqual(actual[seat].observation.private['inventories'][index+1],{'FERTILIZER':3})

    def test_18_observed_hire_not_request_counter(self):
        for seat in (0,1):
            state, env, cfg = self.world(seat)
            candidate = s1.SweepExperiment(self.passes,lambda:[self.tape()])
            output = candidate(deepcopy(state[seat].observation),cfg)
            self.assertEqual(output['market'],[['HIRE']])
            self.assertEqual(candidate.report['confirmed_hires'],0)
            pair = [self.passes(),self.passes()];pair[seat]=output
            self.advance(state,env,pair)
            candidate(deepcopy(state[seat].observation),cfg)
            self.assertEqual(candidate.report['confirmed_hires'],1)
            self.assertEqual(candidate.index,0)

    def test_19_unfilled_hire_does_not_own_an_actor(self):
        state, env, cfg = self.world()
        candidate = s1.SweepExperiment(self.passes,lambda:[self.tape()])
        output = candidate(deepcopy(state[0].observation),cfg)
        state[0].observation.farms[0]['money']=0
        self.advance(state,env,[output,self.passes()])
        candidate(deepcopy(state[0].observation),cfg)
        self.assertIsNone(candidate.index)
        self.assertEqual(candidate.report['confirmed_hires'],0)
        self.assertEqual(candidate.report['failed_hires'],1)

    def test_20_cardinality_without_hire_counter_is_not_fill(self):
        state, env, cfg = self.world()
        candidate = s1.SweepExperiment(self.passes,lambda:[self.tape()])
        candidate(deepcopy(state[0].observation),cfg)
        obs = deepcopy(state[0].observation)
        obs.step += 1
        obs.farms[0]['hands'].append([5,4])
        obs.private['inventories'].append({})
        candidate(obs,cfg)
        self.assertIsNone(candidate.index)
        self.assertEqual(candidate.report['confirmed_hires'],0)

    def test_21_nonconsecutive_or_duplicate_actor_custody_rejected(self):
        state, _, cfg = self.world()
        for delta in (0,2,24):
            candidate = s1.SweepExperiment(self.passes,lambda:[self.tape()])
            candidate(deepcopy(state[0].observation),cfg)
            obs = deepcopy(state[0].observation);obs.step += delta
            with self.assertRaises(ValueError): candidate(obs,cfg)

    def test_22_no_cross_seat_or_instance_state(self):
        state, _, cfg = self.world()
        a = s1.SweepExperiment(self.passes,lambda:[self.tape()])
        b = s1.SweepExperiment(self.passes,lambda:[self.tape()])
        a(deepcopy(state[0].observation),cfg)
        self.assertIsNone(b.pending)
        with self.assertRaises(ValueError): a(deepcopy(state[1].observation),cfg)

    def test_23_complete_constructed_day_real_fertilizer_and_reset(self):
        for seat in (0,1):
            state, env, cfg = self.world(seat)
            candidate = s1.SweepExperiment(self.passes,lambda:[self.tape()])
            for step in range(110,120):
                self.assertEqual(state[seat].observation.step,step)
                output = candidate(deepcopy(state[seat].observation),cfg)
                pair=[self.passes(),self.passes()];pair[seat]=output
                self.advance(state,env,pair)
            private = state[seat].observation.private
            self.assertGreater(private['shed']['FERTILIZER'],0)
            self.assertEqual(candidate.report['confirmed_hires'],1)
            self.assertGreater(candidate.report['collection_requests'],0)
            self.assertEqual(state[seat].observation.farms[seat]['hands'],[])
            self.assertTrue(state[seat].observation.farms[seat]['tiles'][4][4]['fertilizer_available'])
            candidate(deepcopy(state[seat].observation),cfg)
            self.assertIsNone(candidate.index)
            self.assertIsNone(candidate.pending)

    def test_24_dynamic_parent_collection_has_priority(self):
        state, env, cfg = self.world()
        def parent(obs,cfg):
            result=self.passes(obs,cfg)
            if obs['step']>110: result['farmer']=['COLLECT_FERTILIZER']
            return result
        candidate = s1.SweepExperiment(parent,lambda:[self.tape()])
        action = candidate(deepcopy(state[0].observation),cfg)
        self.advance(state,env,[action,self.passes()])
        output = candidate(deepcopy(state[0].observation),cfg)
        self.assertEqual(output['hands'][candidate.index],['PASS'])
        self.assertEqual(output['farmer'],['COLLECT_FERTILIZER'])

    def test_25_parent_reconstruction_preserves_experiment_custody(self):
        state, env, cfg = self.world()
        seen=[]
        class Parent:
            def __call__(self,obs,cfg):
                seen.append(len(obs['farms'][0]['hands']))
                return NativeS1Tests.passes(obs,cfg)
        candidate=s1.SweepExperiment(Parent(),lambda:[self.tape()])
        output=candidate(deepcopy(state[0].observation),cfg)
        self.advance(state,env,[output,self.passes()])
        candidate.parent=Parent()
        candidate(deepcopy(state[0].observation),cfg)
        self.assertEqual(seen,[0,0])
        self.assertEqual(candidate.index,0)

    def test_26_exact_raw_market_append(self):
        state, _, cfg=self.world()
        original={'farmer':['PASS'],'hands':[], 'market':[[],['SELL','EGG',0],[]]}
        candidate=s1.SweepExperiment(lambda o,c:original,lambda:[self.tape()])
        output=candidate(deepcopy(state[0].observation),cfg)
        self.assertEqual(output['market'],[[],['SELL','EGG',0],[],['HIRE']])
        self.assertEqual(original['market'],[[],['SELL','EGG',0],[]])

    def test_27_saturated_eod_is_not_realized_collection_credit(self):
        state, env, cfg=self.world(step=119)
        farm=state[0].observation.farms[0]
        farm['hands']=[[4,4]]
        state[0].observation.private['inventories'].append({})
        state[0].observation.private['shed']['WHEAT']=100
        self.advance(state,env,[{'farmer':['PASS'],'hands':[['COLLECT_FERTILIZER']],'market':[]},self.passes()])
        self.assertEqual(state[0].observation.private['shed']['FERTILIZER'],0)
        self.assertEqual(state[0].observation.private['shed']['WHEAT'],100)

    def test_28_assess_and_remap_do_not_mutate_inputs(self):
        state, _, cfg=self.world()
        obs=deepcopy(state[0].observation);action=self.passes();tapes=[self.tape()]
        before=deepcopy((obs,action,cfg,tapes))
        s1.assess(obs,action,cfg,tapes)
        s1.remap(action,3,['NORTH'])
        self.assertEqual((obs,action,cfg,tapes),before)


if __name__ == '__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(NativeS1Tests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({'tests':result.testsRun,'failures':len(result.failures),
                      'errors':len(result.errors),'skips':len(result.skipped),
                      'full_engine_calls_including_initializations':ENGINE_CALLS},sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() and result.testsRun == 28 and not result.skipped else 1)
