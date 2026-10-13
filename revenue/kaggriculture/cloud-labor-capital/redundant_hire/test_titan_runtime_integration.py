# SPDX-License-Identifier: Apache-2.0
"""Current TitanAgent integration checks for the landed redundant-hire component."""
from __future__ import annotations
import copy
import hashlib
import os
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
LAB = Path(os.environ.get('TITAN_CURRENT_DIR', HERE.parents[1] / 'cloud-execution-lab')).resolve()
if str(LAB) not in sys.path:
    sys.path.insert(0, str(LAB))
from titan_runtime import Features, TitanAgent
import scheduler

PASS = {'farmer':['PASS'], 'hands':[], 'market':[]}


def case():
    step = 21; board = 10
    tiles = [[None if x < 5 and y < 5 else 'LOCKED' for x in range(board)] for y in range(board)]
    tiles[4][5] = scheduler.m._new_plant('CARROT', 0, 24)
    farm = {'money':100.0, 'tiles':tiles, 'farmer':[4,4], 'hands':[],
            'unlocked_quadrants':['NW'], 'hires_today':0}
    other = copy.deepcopy(farm)
    private = {'seeds':{c:0 for c in scheduler.m.CROPS},
               'shed':{p:0 for p in [*scheduler.m.PRODUCTS, *scheduler.m.ANIMALS]},
               'inventories':[{}]}
    obs = {'step':step, 'day':0, 'hour':step, 'player':0,
           'farms':[farm,other], 'private':private,
           'market':{'inventory':{p:10000 for p in scheduler.m.PRODUCTS},
                     'prices':{p:1 for p in scheduler.m.PRODUCTS}},
           'town':{'unlocked_shops':[]}}
    cfg = {'boardSize':board, 'turnsPerDay':24, 'episodeSteps':720,
           'shedCapacity':100, 'maxMarketOrdersPerTurn':10, 'farmHandCostMult':1}
    selected = {'farmer':['PASS'], 'hands':[], 'market':[['HIRE']]}
    route = [copy.deepcopy(PASS) for _ in range(720)]
    route[step] = copy.deepcopy(selected)
    route[22] = {'farmer':['EAST'], 'hands':[['WATER']], 'market':[]}
    route[23] = {'farmer':['WATER'], 'hands':[['PASS']], 'market':[]}
    return obs,cfg,selected,route


class CurrentRedundantHireIntegrationTests(unittest.TestCase):
    def actor(self, enabled=True):
        actor = TitanAgent(Features(redundant_hire=enabled)); actor._initialize()
        obs,cfg,selected,route = case()
        actor.controller.R = {'integration-route':route}; actor.controller.cur = 'integration-route'
        return actor,obs,cfg,selected

    def test_actual_current_runtime_consumes_the_landed_component(self):
        actor,obs,cfg,selected = self.actor(); before = copy.deepcopy((obs,cfg,selected))
        out = actor._redundant_hire_selected(obs,cfg,selected)
        self.assertEqual(out['market'], [['SELL','WHEAT',0]])
        report = actor.diagnostics['redundant_hire']
        self.assertTrue(report['changed'])
        self.assertEqual(report['removed_order_indices'], [0])
        self.assertEqual(report['immediate_wage_saving'], 1)
        self.assertEqual(report['watering_witnesses'][0]['retained_watering'], [[23,0]])
        self.assertEqual((obs,cfg,selected), before)

    def test_default_actor_is_byte_behavior_unchanged(self):
        actor,obs,cfg,selected = self.actor(enabled=False)
        self.assertEqual(actor._redundant_hire_selected(obs,cfg,selected), selected)
        self.assertNotIn('redundant_hire', actor.diagnostics)
        self.assertFalse(hasattr(actor, 'redundant_hire_module'))

    def test_landed_component_is_consumed_byte_exact(self):
        canonical = LAB / 'reference/titan-current/redundant_hire.py'
        landed = HERE / 'redundant_hire.py'
        self.assertEqual(canonical.read_bytes(), landed.read_bytes())
        self.assertEqual(hashlib.sha256(canonical.read_bytes()).hexdigest(),
                         'a881284d6b59366536ebc5e77f0f7c7f2923599dfb8588fd8b1ed6166bd51483')

    def test_feature_is_limited_to_tested_frozen_nonterminal_mode(self):
        for kwargs in ({'consumer':'ordered'}, {'consumer':'parent'}, {'terminal_route':True}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, 'redundant_hire'):
                Features(redundant_hire=True, **kwargs)

    def test_no_hire_fast_path_preserves_action_and_skips_component(self):
        actor,obs,cfg,selected = self.actor(); selected['market'] = []
        original = actor.redundant_hire_module.propose_redundant_hires
        actor.redundant_hire_module.propose_redundant_hires = lambda *a, **k: (_ for _ in ()).throw(AssertionError('called'))
        try:
            self.assertEqual(actor._redundant_hire_selected(obs,cfg,selected), selected)
        finally:
            actor.redundant_hire_module.propose_redundant_hires = original

    def test_pipeline_order_is_sell_then_hire_then_seed(self):
        actor,obs,cfg,selected = self.actor(); calls = []
        actor.consumer.transform = lambda o, c, s: calls.append('sell') or copy.deepcopy(s)
        actor._redundant_hire_selected = lambda o, c, s: calls.append('hire') or copy.deepcopy(s)
        actor._seed_selected = lambda o, c, s: calls.append('seed') or copy.deepcopy(s)
        self.assertEqual(actor.transform_selected(obs,cfg,selected), selected)
        self.assertEqual(calls, ['sell','hire','seed'])

    def test_selected_transform_does_not_call_the_parent(self):
        actor,obs,cfg,selected = self.actor()
        actor.consumer.transform = lambda o,c,s: copy.deepcopy(s)
        original = actor.production.act
        actor.production.act = lambda *_: (_ for _ in ()).throw(AssertionError('second parent call'))
        try:
            out = actor.transform_selected(obs,cfg,selected)
        finally:
            actor.production.act = original
        self.assertEqual(out['market'], [['SELL','WHEAT',0]])


if __name__ == '__main__':
    unittest.main(verbosity=2)
