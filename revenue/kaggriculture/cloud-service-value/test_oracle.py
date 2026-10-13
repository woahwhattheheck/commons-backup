"""Real pinned-engine regression tests; set TITAN_ENGINE_DIR/TITAN_EVAL_ROOT."""
import copy
import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

from oracle import Scenario, simulate_bundle, value_bundle


def load_file(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class EngineCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        loader = os.environ.get('TITAN_ENGINE_LOADER')
        if loader is None:
            loader = str(Path(os.environ['TITAN_EVAL_ROOT'])/'cloud-eval/evaluate.py')
        import hashlib
        expected = {'kaggriculture.py':'3c202c7ee921da239356789e266b694635103fc4',
                    'kaggriculture.json':'b354d06b742fe48402513792253f1a5c29366b20',
                    'utils.py':'91c8822ee6201ba4a5a8416c7dbe34f95dd61c87'}
        for name, blob in expected.items():
            data = (Path(os.environ['TITAN_ENGINE_DIR'])/name).read_bytes()
            assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest() == blob
        cls.ev = load_file(Path(loader), 't04_eval')
        cls.e, cls.hashes = cls.ev.get_engine(Path(os.environ['TITAN_ENGINE_DIR']))

    def setUp(self):
        self.cfg = dict(boardSize=10, turnsPerDay=24, episodeSteps=720,
                        shedCapacity=100, maxMarketOrdersPerTurn=10,
                        farmHandCostMult=1, townShopSellInterval=4,
                        townCenterSellInterval=24, weedSpawnChance=0,
                        townShopUnlockInterval=1000000)
        self.farm = self.e._new_farm(10, 3000)
        self.private = self.e._new_private()
        self.obs = dict(player=0, step=0, day=0, hour=0, farms=[self.farm, self.e._new_farm(10, 3000)],
                        private=self.private, market=self.e._new_market(), town=self.e._new_town())

    def start(self, step):
        self.obs.update(step=step, day=step//24, hour=step%24)

    def tile(self, value):
        self.farm['tiles'][4][4] = value
        return value

    def hand(self, inventory=None):
        self.farm['hands'].append([4,4])
        self.private['inventories'].append(inventory or {})

    def run_plan(self, plan, end=None):
        return simulate_bundle(self.e, self.obs, self.cfg, plan,
                               end_step=self.obs['step'] if end is None else end)

    def test_unfed_animal_still_produces_base(self):
        self.start(95)
        self.tile(self.e._new_animal('GOOSE', 0))
        r = self.run_plan({})
        self.assertEqual(r['farm']['tiles'][4][4]['yield_units'], 1)
        self.assertEqual(r['consumed_inputs'], {})

    def test_second_unfed_day_escapes_before_production(self):
        self.start(95)
        t=self.tile(self.e._new_animal('GOOSE',0)); t['consecutive_unfed']=1
        self.assertEqual(self.run_plan({})['farm']['tiles'][4][4], {'kind':'COOP'})

    def test_today_care_is_after_production(self):
        self.start(95)
        t=self.tile(self.e._new_animal('GOOSE',0)); t['pending_care_bonus']=2
        self.private['inventories'][0]={'WHEAT':1}
        self.hand()
        r=self.run_plan({95:{'farmer':['FEED'],'hands':[['CARE']]}})
        t=r['farm']['tiles'][4][4]
        self.assertEqual((t['yield_units'], t['pending_care_bonus']), (3,1))
        self.assertEqual(r['consumed_inputs'], {'WHEAT':1})

    def test_unfed_production_discards_pending_care(self):
        self.start(95)
        t=self.tile(self.e._new_animal('GOOSE',0)); t['pending_care_bonus']=3
        r=self.run_plan({95:{'farmer':['CARE']}})
        t=r['farm']['tiles'][4][4]
        self.assertEqual((t['yield_units'],t['pending_care_bonus']), (1,0))

    def test_fertilizer_water_order_changes_same_day_cash(self):
        self.start(48)
        self.tile(self.e._new_plant('CARROT',0,24))
        self.private['inventories'][0]={'FERTILIZER':1}
        self.hand({'FERTILIZER':1})
        tail={49:{'farmer':['HARVEST']},50:{'farmer':['DROP'],'market':[['SELL','CARROT',100]]}}
        a={48:{'farmer':['WATER'],'hands':[['FERTILIZE']]},**tail}
        b={48:{'farmer':['FERTILIZE'],'hands':[['WATER']]},**tail}
        r=value_bundle(self.e,self.obs,self.cfg,a,b,end_step=50)
        self.assertGreater(r['incremental_cash'],0)
        self.assertEqual(r['candidate']['consumed_inputs'],{'FERTILIZER':1})
        self.assertEqual(r['control']['consumed_inputs'],{'FERTILIZER':1})

    def test_duplicate_feed_consumes_one_unit(self):
        self.start(94); self.tile(self.e._new_animal('GOOSE',0))
        self.private['inventories'][0]={'WHEAT':1}; self.hand({'WHEAT':1})
        r=self.run_plan({94:{'farmer':['FEED'],'hands':[['FEED']]}})
        self.assertEqual(r['consumed_inputs'],{'WHEAT':1})
        self.assertEqual(r['private']['inventories'][1],{'WHEAT':1})

    def test_fertilize_requires_actual_carried_input(self):
        self.start(48); self.tile(self.e._new_plant('CARROT',0,24))
        r=self.run_plan({48:{'farmer':['FERTILIZE']}})
        self.assertEqual(r['farm']['tiles'][4][4]['fertilized_until_day'],-1)

    def test_ongoing_has_four_events_then_decay(self):
        self.start(191)
        t=self.tile(self.e._new_plant('TOMATO',0,24)); t['consecutive_unwatered']=0
        plan={s:{'farmer':['WATER']} for s in (191,192,216,240,264,288)}
        r=self.run_plan(plan,287)
        self.assertEqual(r['farm']['tiles'][4][4]['yield_units'],4)
        self.assertEqual(r['farm']['tiles'][4][4]['max_lifespan_step'],288)
        self.assertEqual(self.run_plan(plan,290)['farm']['tiles'][4][4]['yield_units'],2)

    def test_harvest_frees_cap_before_production(self):
        self.start(94)
        t=self.tile(self.e._new_animal('GOOSE',0)); t.update(yield_units=4,pending_care_bonus=3,fed_today=True)
        tail={96:{'market':[['SELL','EGG',100]]}}
        r=value_bundle(self.e,self.obs,self.cfg,tail,{94:{'farmer':['HARVEST']},**tail},end_step=96)
        self.assertGreater(r['incremental_cash'],0)
        self.assertEqual(r['candidate']['farm']['tiles'][4][4]['yield_units'],4)

    def test_final_drop_can_sell_but_no_automatic_deposit(self):
        self.start(718); self.private['inventories'][0]={'MELON':2}
        control={718:{'market':[['SELL','MELON',100]]}}
        candidate={718:{'farmer':['DROP'],'market':[['SELL','MELON',100]]}}
        r=value_bundle(self.e,self.obs,self.cfg,control,candidate,end_step=718)
        self.assertEqual(r['control']['cash_gain'],0)
        self.assertEqual(r['control']['private']['inventories'][0],{'MELON':2})
        self.assertGreater(r['candidate']['cash_gain'],0)

    def test_automatic_deposit_is_after_same_turn_market(self):
        self.start(695); self.private['inventories'][0]={'MELON':2}
        plan={695:{'market':[['SELL','MELON',100]]},696:{'market':[['SELL','MELON',100]]}}
        self.assertEqual(self.run_plan(plan,695)['cash_gain'],0)
        self.assertEqual(self.run_plan(plan,696)['cash_ledger'][0]['step'],696)

    def test_drop_overflow_is_ordered_and_displaced(self):
        self.start(100); self.cfg['shedCapacity']=1
        self.private['inventories'][0]={'WHEAT':1,'MILK':1}
        sell=[['SELL','WHEAT',1],['SELL','MILK',1]]
        a={100:{'farmer':['DROP'],'market':sell}}
        b={100:{'farmer':['PLACE','MILK',1],'market':sell}}
        r=value_bundle(self.e,self.obs,self.cfg,a,b,end_step=100)
        self.assertEqual(r['control']['discarded_stock'],{'MILK':1})
        self.assertGreater(r['incremental_cash'],0)

    def test_pickup_is_ordered(self):
        self.start(100); self.private['shed']['WHEAT']=1; self.hand()
        r=self.run_plan({100:{'farmer':['PICKUP','WHEAT',1],'hands':[['PICKUP','WHEAT',1]]}})
        self.assertEqual(r['private']['inventories'],[{'WHEAT':1},{}])

    def test_real_movement_rejects_offboard(self):
        self.start(100); self.farm['farmer']=[0,0]
        r=self.run_plan({100:{'farmer':['NORTH']},101:{'farmer':['EAST']}},101)
        self.assertEqual(r['farm']['farmer'],[1,0])

    def test_atomic_seed_overcommit(self):
        self.start(100); self.private['seeds']['CARROT']=1; self.hand()
        self.farm['hands'][0]=[3,4]
        r=self.run_plan({100:{'farmer':['PLANT','CARROT'],'hands':[['PLANT','CARROT']]}})
        self.assertIsNone(r['farm']['tiles'][4][4]); self.assertIsNone(r['farm']['tiles'][4][3])
        self.assertEqual(r['private']['seeds']['CARROT'],1)

    def test_cash_value_does_not_invent_sale_for_held_output(self):
        self.start(100); t=self.tile(self.e._new_animal('GOOSE',0));t['yield_units']=4
        r=value_bundle(self.e,self.obs,self.cfg,{}, {100:{'farmer':['HARVEST']}},end_step=100,labor_unit_cost=2)
        self.assertEqual(r['incremental_cash'],0); self.assertEqual(r['value'],-2)

    def test_boundary_and_observation_are_unchanged(self):
        self.start(718); saved=copy.deepcopy(self.obs)
        self.run_plan({})
        self.assertEqual(self.obs,saved)
        with self.assertRaises(ValueError): self.run_plan({},719)

    def test_policy_forks_parent_and_changes_only_service_action(self):
        from policy import make_policy
        self.start(94)
        t=self.tile(self.e._new_animal('GOOSE',0));t.update(yield_units=4,fed_today=True)
        calls=[]
        def decision(obs):
            return ({'farmer':['CARE'],'hands':[],'market':[]} if obs['step']==94 else
                    {'market':[['SELL','EGG',obs['private']['shed'].get('EGG',0)]]} if obs['step']==96 else {})
        def parent(obs): calls.append(obs['step']); return decision(obs)
        forks=[]
        def fork(): forks.append(True); return decision
        agent=make_policy(parent,self.e,fork_parent=fork)
        result=agent(self.obs,self.cfg)
        self.assertEqual(calls,[94]); self.assertEqual(len(forks),2)
        self.assertEqual(result,{'farmer':['HARVEST'],'hands':[],'market':[]})

    def test_policy_leaves_final_day_untouched(self):
        from policy import make_policy
        self.start(718)
        t=self.tile(self.e._new_animal('GOOSE',0));t.update(yield_units=4,fed_today=True)
        def fork(): raise AssertionError('Must not forecast final-day changes')
        parent=lambda obs:{'farmer':['CARE'],'market':[['SELL','EGG',1]]}
        self.assertEqual(make_policy(parent,self.e,fork_parent=fork)(self.obs,self.cfg), parent(self.obs))

    def test_matches_complete_official_interpreter_across_daily_boundary(self):
        self.start(94); t=self.tile(self.e._new_animal('GOOSE',0));t.update(yield_units=3,pending_care_bonus=2)
        self.private['inventories'][0]={'WHEAT':2};self.hand()
        plan={94:{'farmer':['FEED'],'hands':[['HARVEST']]},95:{'farmer':['CARE']},
              96:{'market':[['SELL','EGG',100],['BUY_PRODUCT','WHEAT',2],['HIRE']]},
              97:{'farmer':['PICKUP','WHEAT',2]},98:{'farmer':['FEED']}}
        predicted=self.run_plan(plan,100)
        # Synthetic second player is PASS. No unknown future state is used by the oracle.
        shared=copy.deepcopy(self.obs['farms'])
        state=[]
        for i in range(2):
            p=copy.deepcopy(self.private) if i==0 else self.e._new_private()
            ob=self.ev.Struct(player=i,private=p,farms=shared,market=None,town=None,step=94)
            state.append(self.ev.Struct(observation=ob,action={},status='ACTIVE',reward=0))
        market,town=copy.deepcopy(self.obs['market']),copy.deepcopy(self.obs['town'])
        for s in state:s.observation.market=market;s.observation.town=town
        env=SimpleNamespace(configuration=SimpleNamespace(**self.cfg),done=False,info={'seed':17})
        for step in range(94,101):
            for s in state:s.observation.step=step
            state[0].action=plan.get(step,{})
            self.e.interpreter(state,env)
        self.assertEqual(predicted['farm'],state[0].observation.farms[0])
        self.assertEqual(predicted['private'],state[0].observation.private)
        self.assertEqual(predicted['market'],state[0].observation.market)
        self.assertEqual(predicted['town'],state[0].observation.town)


if __name__=='__main__': unittest.main(verbosity=2)
