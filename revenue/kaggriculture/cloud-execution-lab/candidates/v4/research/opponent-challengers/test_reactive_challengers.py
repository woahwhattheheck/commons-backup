# SPDX-License-Identifier: Apache-2.0
"""Independent unit/resource and full-engine contracts for synthetic opponents."""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

import bench_challengers as bench
import reactive_challengers as policy
RUNTIME = None

class Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ev, cls.engine, _, cls.cfg = bench.setup(RUNTIME)

    def fixture(self, seat=0, step=96, hands=0):
        state, env = bench.initialized(self.ev, self.engine, self.cfg, 17)
        obs = deepcopy(state[seat].observation)
        obs['step'] = step
        obs['day'], obs['hour'] = divmod(step, 24)
        farm, private = obs['farms'][seat], obs['private']
        farm['hands'] = [[4, 4] for _ in range(hands)]
        farm['hires_today'] = hands
        private['inventories'] = [{} for _ in range(hands + 1)]
        farm['money'] = 3000
        return obs, env.configuration, farm, private

    def units(self, action):
        return [action['farmer'], *action['hands']]

    def test_empty_observation(self):
        self.assertEqual(policy.agent({}, {}), {'farmer':['PASS'],'hands':[],'market':[]})

    def test_unknown_profile_rejected(self):
        with self.assertRaises(KeyError):
            policy.act({}, {}, profile='missing')

    def test_input_nonmutation(self):
        obs,cfg,_,private = self.fixture(hands=3)
        private['seeds']['CARROT'] = 2
        before = deepcopy((obs,cfg))
        for p in policy.PROFILES:
            policy.act(obs,cfg,profile=p)
        self.assertEqual((obs,cfg),before)

    def test_deterministic_stateless_interleaving(self):
        obs,cfg,_,_ = self.fixture()
        expected = policy.agent(obs,cfg)
        other,_,_,_ = self.fixture(seat=1,step=478,hands=8)
        for p in policy.PROFILES:
            policy.act(other,cfg,profile=p)
        self.assertEqual(policy.agent(obs,cfg),expected)

    def test_opponent_farm_not_consumed(self):
        for seat in (0,1):
            obs,cfg,_,_ = self.fixture(seat=seat)
            expected = policy.agent(obs,cfg)
            obs['farms'][1-seat] = {'unreadable_opponent_sentinel':True}
            self.assertEqual(policy.agent(obs,cfg),expected)

    def test_external_seed_not_consumed(self):
        obs,cfg,_,_ = self.fixture()
        expected = policy.agent(obs,cfg)
        obs['seed'] = 918273; cfg['seed'] = -1
        self.assertEqual(policy.agent(obs,cfg),expected)

    def test_profile_initial_actions_differ(self):
        obs,cfg,_,_ = self.fixture(step=0)
        actions = {bench.digest(policy.act(obs,cfg,profile=p)) for p in policy.PROFILES}
        self.assertEqual(len(actions), len(policy.PROFILES))

    def test_seat_permutation_equivariant(self):
        a,cfg,_,_ = self.fixture(seat=0,hands=3)
        b,_,_,_ = self.fixture(seat=1,hands=3)
        for p in policy.PROFILES:
            self.assertEqual(policy.act(a,cfg,profile=p),policy.act(b,cfg,profile=p))

    def test_existing_hands_only(self):
        for n in range(9):
            obs,cfg,_,_ = self.fixture(step=0,hands=n)
            self.assertEqual(len(policy.agent(obs,cfg)['hands']),n)

    def test_hire_never_creates_same_turn_units(self):
        obs,cfg,_,_ = self.fixture(step=0)
        a = policy.agent(obs,cfg)
        self.assertTrue(any(o[0]=='HIRE' for o in a['market']))
        self.assertEqual(a['hands'],[])

    def test_joint_seed_reservation(self):
        for seat in (0,1):
            obs,cfg,f,p = self.fixture(seat=seat,hands=3)
            f['farmer']=[4,4];f['hands']=[[3,4],[4,3],[3,3]]
            p['seeds']['CARROT']=1
            a=policy.act(obs,cfg,profile='roots')
            demand=Counter(u[1] for u in self.units(a) if u[0]=='PLANT')
            self.assertEqual(demand['CARROT'],1)
            self.assertLessEqual(demand['CARROT'],p['seeds']['CARROT'])

    def test_sequential_animal_pickup(self):
        obs,cfg,_,p=self.fixture(hands=4)
        p['shed']['COW']=1
        a=policy.act(obs,cfg,profile='dairy')
        self.assertEqual(sum(u==['PICKUP','COW',1] for u in self.units(a)),1)

    def test_same_animal_feeding_not_double_counted(self):
        obs,cfg,f,p=self.fixture(hands=2)
        f['farmer']=[3,3]; f['hands']=[[3,3],[3,3]]
        f['tiles'][3][3]=self.engine._new_animal('COW',0)
        p['inventories']=[{'WHEAT':1} for _ in range(3)]
        a=policy.act(obs,cfg,profile='dairy')
        self.assertEqual(sum(u==['FEED'] for u in self.units(a)),1)

    def test_market_purchase_cannot_feed_current_turn(self):
        obs,cfg,f,p=self.fixture(hands=2)
        f['farmer']=[3,3];f['hands']=[[3,3],[3,3]]
        f['tiles'][3][3]=self.engine._new_animal('COW',0)
        a=policy.act(obs,cfg,profile='dairy')
        self.assertTrue(any(o[0:2]==['BUY_PRODUCT','WHEAT'] for o in a['market']))
        self.assertFalse(any(u==['FEED'] for u in self.units(a)))

    def test_post_drop_capacity_sets_sell_quantity(self):
        obs,cfg,_,p=self.fixture(step=718)
        p['shed']['MILK']=99;p['inventories'][0]={'CARROT':5}
        a=policy.act(obs,cfg,profile='roots')
        self.assertEqual(a['farmer'],['DROP'])
        self.assertIn(['SELL','CARROT',1],a['market'])
        self.assertNotIn(['SELL','CARROT',5],a['market'])

    def test_terminal_cargo_moves_home(self):
        obs,cfg,f,p=self.fixture(step=716)
        f['farmer']=[3,4];p['inventories'][0]={'WOOL':1}
        self.assertEqual(policy.agent(obs,cfg)['farmer'],['EAST'])

    def test_terminal_no_stranded_harvest(self):
        obs,cfg,f,_=self.fixture(step=718)
        f['farmer']=[0,0]
        tile=self.engine._new_animal('SHEEP',0);tile['yield_units']=6
        f['tiles'][0][0]=tile
        self.assertEqual(policy.agent(obs,cfg)['farmer'],['PASS'])

    def test_no_late_livestock_purchase_or_hire(self):
        obs,cfg,_,_=self.fixture(step=718)
        self.assertFalse(any(o[0] in ('BUY_ANIMAL','BUY_SEED','HIRE') for o in policy.agent(obs,cfg)['market']))

    def test_market_cap_honored(self):
        obs,cfg,_,p=self.fixture(step=0)
        p['shed']={k:1 for k in policy.PRODUCTS}
        for limit in (1,2,3,10):
            cfg['maxMarketOrdersPerTurn']=limit
            self.assertLessEqual(len(policy.agent(obs,cfg)['market']),limit)

    def test_crop_quote_changes_choice(self):
        obs,cfg,_,p=self.fixture()
        p['seeds']['CARROT']=1;p['seeds']['WHEAT']=1
        obs['market']['prices']['CARROT']=500;obs['market']['prices']['WHEAT']=1
        a=policy.act(obs,cfg,profile='roots')
        obs['market']['prices']['CARROT']=1;obs['market']['prices']['WHEAT']=500
        b=policy.act(obs,cfg,profile='roots')
        self.assertEqual(a['farmer'],['PLANT','CARROT'])
        self.assertEqual(b['farmer'],['PLANT','WHEAT'])

    def test_feed_cargo_prevents_rebuy(self):
        obs,cfg,f,p=self.fixture()
        f['tiles'][0][0]=self.engine._new_animal('COW',0)
        p['inventories'][0]={'WHEAT':8}
        a=policy.act(obs,cfg,profile='dairy')
        self.assertFalse(any(o[:2]==['BUY_PRODUCT','WHEAT'] for o in a['market']))

    def test_sales_not_credited_before_buy(self):
        obs,cfg,f,p=self.fixture()
        f['money']=0;p['shed']['WOOL']=20
        a=policy.act(obs,cfg,profile='fiber')
        self.assertIn(['SELL','WOOL',20],a['market'])
        self.assertFalse(any(o[0] in ('BUY_SEED','BUY_ANIMAL','BUY_PRODUCT','HIRE') for o in a['market']))

    def test_constants_match_pinned_engine(self):
        for name,c in policy.CROPS.items():
            e=self.engine.CROPS[name]
            self.assertEqual(c,(e['seed'],e['first_yield_day'],e['max_yield_day'],e['ongoing']))
        for name,c in policy.ANIMALS.items():
            e=self.engine.ANIMALS[name]
            self.assertEqual(c,(e['cost'],e['first_yield_day'],e['interval'],e['product'],e['structure']))

    def test_projector_legal_action_matrix(self):
        cases=[]
        for crop in policy.CROPS:
            cases += [('plant',crop),('water',crop),('harvest',crop)]
        for animal in policy.ANIMALS:
            cases += [('place',animal),('feed',animal),('care',animal),('harvest-animal',animal),('fert',animal)]
        cases += [(a,None) for a in ['EAST','WEST','NORTH','SOUTH','DROP','PICKUP','DIG','BUILD_COOP','BUILD_PASTURE','PASS']]
        for seat in (0,1):
            for mode,item in cases:
                with self.subTest(seat=seat,mode=mode,item=item):
                    obs,cfg,f,p=self.fixture(seat=seat)
                    action=[mode]
                    if mode=='plant':
                        action=['PLANT',item];p['seeds'][item]=1
                    elif mode in ('water','harvest'):
                        f['tiles'][4][4]=self.engine._new_plant(item,-10,24)
                        f['tiles'][4][4]['yield_units']=3
                        action=[mode.upper()]
                    elif item in policy.ANIMALS:
                        t=self.engine._new_animal(item,0);f['tiles'][4][4]=t
                        if mode=='place':
                            f['tiles'][4][4]={'kind':policy.ANIMALS[item][4]};p['inventories'][0][item]=1;action=['PLACE',item]
                        elif mode=='feed':
                            p['inventories'][0]['WHEAT']=1;action=['FEED']
                        elif mode=='care': action=['CARE']
                        elif mode=='harvest-animal':t['yield_units']=3;action=['HARVEST']
                        else:t['fertilizer_available']=True;action=['COLLECT_FERTILIZER']
                    elif mode=='DROP':
                        p['inventories'][0]={'MILK':8,'WOOL':4};p['shed']['WHEAT']=97
                    elif mode=='PICKUP':
                        p['shed']['WHEAT']=2;action=['PICKUP','WHEAT',5]
                    elif mode=='DIG': f['tiles'][4][4]={'kind':'WEED'}
                    ef,ep=deepcopy(f),deepcopy(p)
                    self.engine._apply_unit_action(ef,ep,0,action,10,4,24,100)
                    policy._project(f,p,0,action,4,24,100)
                    self.assertEqual((f,p),(ef,ep))

    def test_json_actions(self):
        obs,cfg,_,_=self.fixture(hands=4)
        for name in policy.PROFILES:
            a=policy.act(obs,cfg,profile=name)
            self.assertEqual(json.loads(json.dumps(a,allow_nan=False)),a)

    def test_native_source_authentication(self):
        self.assertEqual(bench.verify_native(RUNTIME)['verified_members'],109)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--runtime',type=Path,required=True)
    args,rest=parser.parse_known_args()
    RUNTIME=args.runtime
    unittest.main(argv=[sys.argv[0],*rest])
