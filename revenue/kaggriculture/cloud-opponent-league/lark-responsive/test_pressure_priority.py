"""Contracts for the disclosed public-curve pressure proxy, not strength tests."""
import copy
import json
import unittest
from collections import Counter
from unittest.mock import patch

from pressure_priority import actor_class, lot_pressure, transform
from sell_priority import actor_class as quote_actor_class

BASE = {'MILK': 143, 'WOOL': 240, 'WHEAT': 50, 'FERTILIZER': 50}
SLOPE = {'MILK': 2, 'WOOL': 0, 'WHEAT': 1, 'FERTILIZER': 1}

def curve(item, stock, params=None):
    p = params or {}
    return max(1, BASE[item] - p.get('slope', SLOPE[item]) * stock)

def obs():
    return {'market': {'inventory': dict.fromkeys(BASE, 0), 'prices': BASE.copy()}}

def apply(action, observation=None, cfg=None, quote=curve):
    return transform(action, obs() if observation is None else observation, cfg, quote=quote)

class PressureTests(unittest.TestCase):
    def test_pressure_not_absolute_quote(self):
        a = {'market': [['SELL','WOOL',14],['SELL','MILK',15]]}
        self.assertEqual(apply(a)['market'], a['market'][::-1])
        self.assertEqual(lot_pressure(a['market'][0],obs()['market'],curve),0)
        self.assertEqual(lot_pressure(a['market'][1],obs()['market'],curve),450)

    def test_quantity_is_explicit_proxy(self):
        a = {'market': [['SELL','WHEAT',2],['SELL','FERTILIZER',3]]}
        self.assertEqual(apply(a)['market'],a['market'][::-1])
        self.assertEqual(lot_pressure(a['market'][0],obs()['market'],curve),4)
        self.assertEqual(lot_pressure(a['market'][1],obs()['market'],curve),9)

    def test_equal_scores_stable(self):
        a = {'market': [['SELL','WHEAT',2],['SELL','FERTILIZER',2],['SELL','WHEAT',2]]}
        self.assertEqual(apply(a),a)

    def test_floor_can_remove_pressure(self):
        o=obs();o['market']['inventory']['MILK']=100;o['market']['prices']['MILK']=1
        self.assertEqual(lot_pressure(['SELL','MILK',15],o['market'],curve),0)

    def test_negative_deterioration_not_urgency(self):
        def rising(item,stock,params):return BASE[item]+stock
        self.assertEqual(lot_pressure(['SELL','MILK',2],obs()['market'],rising),0)

    def test_current_public_quote_must_match(self):
        o=obs();o['market']['prices']['MILK']=144
        self.assertIsNone(lot_pressure(['SELL','MILK',2],o['market'],curve))
        a={'market':[['SELL','WOOL',2],['SELL','MILK',2]]};self.assertEqual(apply(a,o),a)

    def test_public_override_passed_explicitly(self):
        o=obs();o['market']['params']={'slope':3}
        self.assertEqual(lot_pressure(['SELL','MILK',2],o['market'],curve),12)

    def test_no_private_rival_or_future_reads(self):
        o=obs();o.update(private=object(),farms=object(),seed=object(),town=object())
        a={'market':[['SELL','WOOL',2],['SELL','MILK',2]]}
        self.assertEqual(apply(a,o),apply(a))

    def test_non_sell_barriers_keep_index_and_units(self):
        a={'farmer':['DROP'],'hands':[['HIRE'],['WATER']],
           'market':[['HIRE'],['SELL','WOOL',2],['SELL','MILK',2],['BUY_SEED','WHEAT',2],
                     ['SELL','WHEAT',1],['SELL','FERTILIZER',2],['BUY_LAND']]}
        b=apply(a)
        for i in (0,3,6):self.assertEqual(a['market'][i],b['market'][i])
        self.assertEqual(a['farmer'],b['farmer']);self.assertEqual(a['hands'],b['hands'])
        self.assertEqual(Counter(map(json.dumps,a['market'])),Counter(map(json.dumps,b['market'])))

    def test_suffix_never_moves_into_prefix(self):
        a={'market':[['SELL','WOOL',2],['SELL','WHEAT',2],['SELL','MILK',15]]}
        self.assertEqual(apply(a,cfg={'maxMarketOrdersPerTurn':2})['market'],[a['market'][1],a['market'][0],a['market'][2]])
        self.assertEqual(apply(a,cfg={'maxMarketOrdersPerTurn':0}),a)

    def test_oversize_quantity_is_barrier_not_clamped(self):
        a={'market':[['SELL','WOOL',2],['SELL','MILK',257],['SELL','WHEAT',2]]}
        self.assertEqual(apply(a),a)
        self.assertIsNone(lot_pressure(a['market'][1],obs()['market'],curve))

    def test_large_order_count_is_identity(self):
        a={'market':[['SELL','MILK',2],['SELL','WOOL',1]]*33}
        self.assertEqual(apply(a,cfg={'maxMarketOrdersPerTurn':66}),a)

    def test_missing_nonintegral_boolean_inventory_is_barrier(self):
        for value in (None,1.5,True,'2'):
            o=obs();o['market']['inventory']['MILK']=value
            self.assertIsNone(lot_pressure(['SELL','MILK',2],o['market'],curve))

    def test_malformed_quote_values_are_barriers(self):
        for value in (True,'3',float('nan'),float('inf'),0,-1):
            def bad(item,stock,params):return BASE[item] if stock==0 else value
            self.assertIsNone(lot_pressure(['SELL','MILK',2],obs()['market'],bad))

    def test_expected_curve_data_errors_are_barriers(self):
        for exception in (ValueError,OverflowError,KeyError,TypeError):
            def bad(*args):raise exception('retained')
            self.assertIsNone(lot_pressure(['SELL','MILK',2],obs()['market'],bad))

    def test_unexpected_callback_errors_are_not_hidden(self):
        def broken(*args):raise RuntimeError('retain programmer failure')
        with self.assertRaisesRegex(RuntimeError,'retain programmer failure'):
            lot_pressure(['SELL','MILK',2],obs()['market'],broken)

    def test_malformed_and_unknown_orders_are_barriers(self):
        for middle in (None,[],['SELL'],['SELL','MILK',0],['SELL','MILK','bad'],['SELL','UNKNOWN',2]):
            a={'market':[['SELL','WOOL',1],middle,['SELL','MILK',2]]}
            self.assertEqual(apply(a),a)

    def test_inputs_and_output_detached(self):
        a={'farmer':['PASS'],'market':[['SELL','WOOL',2],['SELL','MILK','2']]};o=obs();before=copy.deepcopy((a,o))
        b=apply(a,o);b['farmer'][0]='DROP';b['market'][0][2]=999
        self.assertEqual((a,o),before)

    def test_missing_or_malformed_market_identity(self):
        a={'market':[['SELL','WOOL',2],['SELL','MILK',2]]}
        for o in ({},{'market':None},{'market':{'prices':None}},{'market':{'inventory':None}}):
            self.assertEqual(apply(a,o),a)
        o=obs();o['market']['params']='bad';self.assertEqual(apply(a,o),a)

    def test_bad_parent_action_or_config_rejected(self):
        for a in (None,[],{'market':'SELL'}):
            with self.assertRaises(ValueError):apply(a)
        with self.assertRaises(ValueError):apply({},cfg={'maxMarketOrdersPerTurn':'bad'})

class ActorTests(unittest.TestCase):
    def setUp(self):
        class Base:
            def __init__(self,spec,*args,**kwargs):self.spec=spec;self.stats={}
            def act(self,*args):return {'kind':'action','marker':1,'action':{'market':[['SELL','WOOL',2],['SELL','MILK',2]]}}
        self.Base=Base;self.Actor=actor_class(Base,curve)

    def test_actual_activation(self):
        a=self.Actor('/p|supply-pressure');r=a.act(obs(),{},1)
        self.assertEqual(a.spec,'/p');self.assertEqual(r['action']['market'][0][1],'MILK');self.assertEqual(r['marker'],1)
        self.assertEqual(a.stats['pressure_priority_changed_turns'],1)
        self.assertEqual(len(a.stats['pressure_priority_total_seconds']),1)

    def test_unmarked_parent_and_fresh_counters(self):
        a=self.Actor('/p');self.assertEqual(a.act(obs(),{},1)['action']['market'][0][1],'WOOL')
        self.assertEqual(a.stats['pressure_priority_total_seconds'],[])
        self.assertEqual(self.Actor('/q|supply-pressure').stats['pressure_priority_changed_turns'],0)

    def test_total_deadline_retained(self):
        a=self.Actor('/p|supply-pressure')
        with patch('pressure_priority.time.perf_counter',side_effect=[0,.99,1.01,1.02]):r=a.act(obs(),{},1)
        self.assertEqual(r['kind'],'timeout');self.assertEqual(r['phase'],'pressure_priority')

    def test_failed_parent_passes_through(self):
        class Failed(self.Base):
            def act(self,*args):return {'kind':'timeout','original':True}
        a=actor_class(Failed,curve)('/p|supply-pressure')
        self.assertEqual(a.act(obs(),{},1),{'kind':'timeout','original':True})
        self.assertEqual(a.stats['pressure_priority_transform_seconds'],[])

    def test_existing_quote_arm_composes_without_double_transform(self):
        composed=actor_class(quote_actor_class(self.Base),curve)
        high=composed('/p|sell-priority');pressure=composed('/p|supply-pressure');base=composed('/p')
        self.assertEqual(high.act(obs(),{},1)['action']['market'][0][1],'WOOL')
        self.assertEqual(pressure.act(obs(),{},1)['action']['market'][0][1],'MILK')
        self.assertEqual(base.act(obs(),{},1)['action']['market'][0][1],'WOOL')
        self.assertFalse(high.stats['pressure_priority_enabled']);self.assertFalse(pressure.stats['sell_priority_enabled'])
        self.assertEqual(pressure.spec,'/p')

if __name__=='__main__':unittest.main(verbosity=2)
