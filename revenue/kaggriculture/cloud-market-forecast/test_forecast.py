# SPDX-License-Identifier: MIT OR CC-BY-4.0
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
import forecast as f
from forecast_market_mechanics import MARKET_PARAMS, PRODUCTS

HERE=Path(__file__).resolve().parent


def obs(step=0, tile=None, copies=None):
    tiles=[[None]*4 for _ in range(4)]
    if tile:tiles[1][1]=tile
    return {'step':step,'day':step//24,'hour':step%24,'player':0,
            'farms':[{'tiles':tiles,'farmer':[1,1],'hands':[]}],
            'town':{'unlocked_shops':copies or []},
            'market':{'inventory':{p:10000 for p in PRODUCTS},'prices':{p:v['base'] for p,v in MARKET_PARAMS.items()}}}


def plant(crop='STRAWBERRY', day=0, held=0, watered=True, until=-1):
    return {'kind':'PLANT','crop':crop,'planted_day':day,'yield_units':held,
            'watered_today':watered,'fertilized_until_day':until,
            'consecutive_unwatered':0,'max_lifespan_step':-1}


class ForecastTests(unittest.TestCase):
    def test_floor_supply_timeline_and_same_unit_joint_quotes(self):
        rows, timeline = f.project_sale_timeline(0,{1:{0:4},5:{0:1}},[1,5],
            lambda i:max(1,3-i),lambda step:0 if step==1 else 2)
        self.assertEqual(rows[1]['inventory'],2)
        self.assertEqual(rows[5]['inventory'],1)
        self.assertEqual(rows[5]['sale_units_by_seat'],{0:5})
        self.assertEqual(rows[5]['market_supply_units_by_seat'],{0:3})
        self.assertEqual(rows[5]['conditional_cash_by_seat'],{0:10})
        self.assertEqual(timeline[0]['market_supply_units_by_seat'],{0:2})
        rows,_=f.project_sale_timeline(1,{1:{0:2,1:2}},[1],
            lambda i:max(1,3-i),lambda step:0)
        self.assertEqual(rows[1]['conditional_cash_by_seat'],{0:3,1:3})
        self.assertEqual(rows[1]['market_supply_units_by_seat'],{0:1,1:1})
        self.assertEqual(rows[1]['inventory'],3)

    def test_forecast_exposes_floor_sale_counts_separately(self):
        o=obs(287,plant(held=4,until=11));o['farms'].append(deepcopy(o['farms'][0]))
        o['market']['inventory']['STRAWBERRY']=11000
        r=f.forecast_market(o,{},[288,289])
        row=r['frames'][0]['products']['STRAWBERRY']['scenarios']['fertilized_prompt']
        self.assertEqual(row['conditional_crop_sale_units'],8)
        self.assertEqual(row['conditional_crop_market_supply_units'],0)
        self.assertEqual(row['floor_sale_units'],8)
        self.assertEqual(row['inventory_delta'],0)
        self.assertEqual(r['frames'][1]['products']['STRAWBERRY']['scenarios']['fertilized_prompt']['inventory'],10999)
        self.assertEqual(r['schema'],2)
        self.assertEqual(r['conditional_sale_timeline']['fertilized_prompt']['STRAWBERRY'][0]['sale_units_by_seat'],{0:4,1:4})

    def test_duplicate_shops_and_sale_phase(self):
        o=obs(216,copies=['PIZZA_SHOP','PIZZA_SHOP','FARMERS_MARKET','YARN_STORE'])
        self.assertEqual(f.public_demand(o,{},216)['units']['TOMATO'],0)
        d=f.public_demand(o,{},217)
        self.assertEqual(d['units']['TOMATO'],4) # three shop copies + center
        self.assertEqual(d['units']['WOOL'],3) # single-product shop doubles + center
        self.assertEqual(d['units']['FERTILIZER'],0)
        cfg={'townShopSellInterval':5,'townCenterSellInterval':7}
        d=f.public_demand(o,cfg,222)
        self.assertEqual(d['units']['TOMATO'],4) # shop220 + center217

    def test_fertilizer_care_day_and_realization_delay(self):
        o=obs(239,plant(until=9))
        result=f.forecast_market(o,{},[240,241])
        a=result['frames'][0]['products']['STRAWBERRY']['scenarios']['fertilized_prompt']
        b=result['frames'][1]['products']['STRAWBERRY']['scenarios']['fertilized_prompt']
        self.assertEqual(a['new_yield_units'],2)
        self.assertEqual(a['conditional_crop_sale_units'],0)
        self.assertEqual(b['conditional_crop_sale_units'],2)
        self.assertEqual(result['crop_witnesses'][0]['fertilizer_contract']['care_day'],11)

    def test_capacity_uncertain_harvest_and_both_farms(self):
        o=obs(287,plant(held=4,until=11))
        o['farms'].append(deepcopy(o['farms'][0]))
        r=f.forecast_market(o,{},[288])['frames'][0]['products']['STRAWBERRY']['scenarios']
        self.assertEqual(r['maintained_buffered']['capacity_clipped_units'],4)
        self.assertEqual(r['maintained_buffered']['conditional_crop_sale_units'],0)
        self.assertEqual(r['fertilized_prompt']['conditional_crop_sale_units'],8)
        self.assertEqual(r['fertilized_prompt']['new_yield_units'],4)

    def test_ongoing_capacity_and_finite_events(self):
        o=obs(239,plant())
        r=f.forecast_market(o,{},[409],buffered_harvest_delay=1000)
        rows=r['frames'][0]['products']['STRAWBERRY']['scenarios']
        self.assertEqual(rows['maintained_buffered']['new_yield_units'],4)
        self.assertEqual(rows['fertilized_prompt']['new_yield_units'],8)
        self.assertEqual(rows['fertilized_prompt']['conditional_crop_sale_units'],8)
        self.assertEqual(rows['no_future_work']['conditional_crop_sale_units'],0)

    def test_one_time_growth_requires_water_and_is_capped(self):
        t=plant('WHEAT',0,1,False);t['max_lifespan_step']=120
        rows=f.forecast_market(obs(48,t),{},[99])['frames'][0]['products']['WHEAT']['scenarios']
        self.assertEqual(rows['no_future_work']['new_yield_units'],0)
        self.assertEqual(rows['fertilized_prompt']['conditional_crop_sale_units'],6)
        self.assertEqual(rows['maintained_buffered']['new_yield_units'],3)

    def test_no_hidden_input_and_no_mutation(self):
        o=obs(239,plant());original=deepcopy(o)
        base=f.forecast_market(o,{},[241])
        self.assertEqual(o,original)
        o.update(seed=123,future_shops=['PIZZA_SHOP']*8,future_prices={'TOMATO':9999})
        self.assertEqual(base,f.forecast_market(o,{'seed':9999},[241]))
        self.assertEqual(base['frames'][0]['products']['STRAWBERRY']['guaranteed_future_crop_sales'],0)

    def test_terminal_horizon(self):
        o=obs(700,plant(day=20))
        r=f.forecast_market(o,{},[718])['frames'][0]['products']['STRAWBERRY']
        self.assertTrue(all(s['new_yield_units']==0 for s in r['scenarios'].values()))
        with self.assertRaises(ValueError): f.forecast_market(o,{},[719])

    def test_unreachable_last_action_water_is_not_assumed(self):
        t=plant(watered=False);t['consecutive_unwatered']=1
        o=obs(239,t);o['farms'][0]['farmer']=[0,0]
        r=f.forecast_market(o,{},[240])['frames'][0]['products']['STRAWBERRY']['scenarios']
        self.assertTrue(all(row['new_yield_units']==0 for row in r.values()))

    def test_flora_contract_injection_and_seat_supply_partition(self):
        o=obs(287,plant(held=4,until=11))
        other=deepcopy(o['farms'][0]);other['tiles'][1][1]['yield_units']=1
        o['farms'].append(other);o['player']=1
        called=set()
        def wrap(name):
            def invoke(*args,**kwargs):
                called.add(name)
                return getattr(f.events,name)(*args,**kwargs)
            return invoke
        names=('production_events','harvest_contract','fertilizer_contract','liquidation_window')
        result=f.forecast_market(o,{},[289],contracts={n:wrap(n) for n in names})
        self.assertEqual(result,f.forecast_market(o,{},[289]))
        self.assertEqual(called,set(names))
        row=result['frames'][0]['products']['STRAWBERRY']
        self.assertEqual(row['own_supply']['observed_held'],1)
        self.assertEqual(row['opponent_public_supply']['observed_held'],4)
        self.assertEqual(row['own_supply']['guaranteed'],0)

    def test_actual_leader_current_states(self):
        for name,prices,step in [('leader-day9',(68,166),224),('leader-day17',(94,176),430)]:
            case=json.loads((HERE/'fixtures'/f'{name}.json').read_text())
            o=case['observation'];cfg=case['configuration']
            self.assertEqual(o['step'],step)
            self.assertEqual((o['market']['prices']['TOMATO'],o['market']['prices']['STRAWBERRY']),prices)
            r=f.forecast_market(o,cfg,[step])
            self.assertEqual(tuple(r['frames'][0]['products'][p]['scenarios']['no_future_work']['price'] for p in ('TOMATO','STRAWBERRY')),prices)
            self.assertEqual(r['frames'][0]['demand']['shop_copies']['PIZZA_SHOP'],2)
            self.assertEqual(len(r['crop_witnesses']),sum(isinstance(t,dict) and t.get('kind')=='PLANT' for farm in o['farms'] for row in farm['tiles'] for t in row))


if __name__=='__main__':
    unittest.main()
