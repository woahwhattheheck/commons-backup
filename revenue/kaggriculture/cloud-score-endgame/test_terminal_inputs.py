# SPDX-License-Identifier: Apache-2.0
"""New terminal-input producer boundaries against native engine and real consumers."""
from __future__ import annotations
import argparse
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

import terminal_inputs as ti
import terminal_input_cases as cases

DEPS = None
COUNTS = {'producer_cells': 0, 'full_interpreter_comparisons': 0, 'unit_snapshots': 0}
WITNESSES = []


def fixture(player=0, lead=33):
    farm = {'money':100000, 'tiles':[[None for _ in range(10)] for _ in range(10)],
            'farmer':[4,4], 'hands':[], 'unlocked_quadrants':['NW'], 'hires_today':0}
    farms = [deepcopy(farm), deepcopy(farm)]; farms[player]['money'] += lead
    market = {'inventory':{p:10000 for p in DEPS.engine.PRODUCTS}, 'prices':{}}
    DEPS.engine._refresh_prices(market)
    cfg = dict(episodeSteps=720, boardSize=10, turnsPerDay=24, shedCapacity=100,
               maxMarketOrdersPerTurn=10, farmHandCostMult=1)
    obs = {'step':718, 'player':player, 'farms':farms, 'market':market,
           'day':29, 'hour':22, 'town':{'unlocked_shops':[]},
           'private':{'shed':{'WHEAT':2,'MILK':2}, 'seeds':{}, 'inventories':[{}]}}
    action = {'farmer':['PASS'], 'hands':[], 'market':[[], ['SELL','WHEAT',2], ['SELL','MILK',2]]}
    scenarios = [{'id':'wheat17', 'shed':{'WHEAT':17}, 'market':[['SELL','WHEAT',17],[]],
                  'origin':'retained PORT constructed fixture'},
                 {'id':'milk2-wheat3', 'shed':{'MILK':2,'WHEAT':3},
                  'market':[['SELL','MILK',2],['SELL','WHEAT',3]],
                  'origin':'retained PORT constructed fixture'}]
    return obs, cfg, action, scenarios


def packet(obs, cfg, action, scenarios, **kwargs):
    post = kwargs.pop('post_unit_observation', None)
    if post is None:
        post = cases.own_unit_snapshot(DEPS.engine, obs, cfg, action)
        COUNTS['unit_snapshots'] += 1
    value = ti.build_terminal_inputs(DEPS.engine, obs, cfg, action,
          post_unit_observation=post, scenarios=scenarios, **kwargs)
    COUNTS['producer_cells'] += value['native_market_calls']
    return value


def verify_native(test, obs, cfg, p):
    scenarios = {s['id']:s for s in p['scenarios']}
    for r in p['document']['receipts']:
        if not r['done']: continue
        state, env = cases.make_state(obs, cfg, r['own_action'], scenarios[r['scenario']])
        DEPS.engine.interpreter(state, env)
        COUNTS['full_interpreter_comparisons'] += 1
        test.assertEqual([s.status for s in state], ['DONE','DONE'])
        test.assertEqual([r['own_cash'],r['rival_cash']],
                         [state[obs['player']].reward,state[1-obs['player']].reward])


class TerminalInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if DEPS is None:
            raise unittest.SkipTest('Run this file with the existing pinned engine and consumer paths')

    def test_absolute_lead33_selects_real_winning_queue_both_positions(self):
        for player in (0,1):
            obs,cfg,action,scenarios=fixture(player)
            p=packet(obs,cfg,action,scenarios)
            verify_native(self,obs,cfg,p)
            output,actor=cases.choose(DEPS,obs,cfg,action,p)
            self.assertNotEqual(output,action)
            self.assertEqual(actor.draws,1)
            self.assertEqual(actor.last_objective['value'],'1')
            self.assertEqual(actor.last_objective['baseline_worst_expected_win_points'],'0')
            self.assertEqual(output['market'][:2],[['SELL','WHEAT',2],['SELL','MILK',2]])
            WITNESSES.append({'name':'lead33','player':player,'document':p['document'],
                              'output':output,'objective':actor.last_objective})

    def test_recovery_mixture_uses_same_fixed_scenario_across_plans(self):
        for player in (0,1):
            obs,cfg,action,scenarios=fixture(player,30)
            p=packet(obs,cfg,action,scenarios)
            verify_native(self,obs,cfg,p)
            output,actor=cases.choose(DEPS,obs,cfg,action,p)
            self.assertEqual(actor.last_objective['value'],'1/2')
            self.assertEqual(actor.draws,1)
            self.assertIn(output,[v['action'] for v in p['plans']])
            for scenario in p['scenarios']:
                self.assertEqual(len({r['scenario_sha256'] for r in p['document']['receipts']
                                     if r['scenario']==scenario['id']}),1)

    def test_drop_snapshot_is_used_once_without_native_unit_replay(self):
        obs,cfg,action,scenarios=fixture()
        obs['private']['shed']={}; obs['private']['inventories']=[{'WHEAT':2,'MILK':2}]
        action['farmer']=['DROP']
        post=cases.own_unit_snapshot(DEPS.engine,obs,cfg,action)
        self.assertEqual(post['private']['shed'],{'WHEAT':2,'MILK':2})
        with patch.object(DEPS.engine,'_apply_unit_action',side_effect=AssertionError('second unit call')):
            p=packet(obs,cfg,action,scenarios,post_unit_observation=post)
        verify_native(self,obs,cfg,p)
        self.assertEqual(obs['private']['shed'],{})

    def test_inherited_hire_is_priced_after_changed_sale(self):
        obs,cfg,action,scenarios=fixture()
        obs['farms'][0]['money']=0
        action['market']=[[],['HIRE'],['SELL','WHEAT',2],['SELL','MILK',2]]
        p=packet(obs,cfg,action,scenarios[:1])
        verify_native(self,obs,cfg,p)
        by_plan={r['plan']:r for r in p['document']['receipts']}
        self.assertEqual(by_plan['baseline']['own_hands_after'],0)
        self.assertTrue(any(r['own_hands_after']==1 for k,r in by_plan.items() if k!='baseline'))
        self.assertTrue(all(plan['action']['market'][1]==['HIRE'] for plan in p['plans']))

    def test_native_buy_product_and_seeds_stay_in_order(self):
        obs,cfg,action,scenarios=fixture()
        action['market']=[['BUY_PRODUCT','WHEAT',1],[],['BUY_SEED','CARROT',2],
                          ['SELL','WHEAT',3],['SELL','MILK',2]]
        p=packet(obs,cfg,action,scenarios)
        verify_native(self,obs,cfg,p)
        for plan in p['plans']:
            self.assertEqual(plan['action']['market'][0],action['market'][0])
            self.assertEqual(plan['action']['market'][2],action['market'][2])

    def test_quantity_floor_sale_counts_cash_without_inventory_increase(self):
        obs,cfg,action,scenarios=fixture()
        obs['market']['inventory']['MILK']=20000
        DEPS.engine._refresh_prices(obs['market'])
        self.assertEqual(obs['market']['prices']['MILK'],1)
        p=packet(obs,cfg,action,[{'id':'quiet','shed':{},'market':[]}])
        verify_native(self,obs,cfg,p)
        self.assertTrue(all(r['own_cash']>obs['farms'][0]['money'] for r in p['document']['receipts']))

    def test_same_public_input_ignores_extra_evaluator_fields(self):
        obs,cfg,action,scenarios=fixture()
        a=packet(obs,cfg,action,None)
        altered=deepcopy(obs); altered['opponent_private']={'MILK':999};altered['future']=['WIN']
        changed_cfg={**cfg,'seed':93214,'evaluation_outcome':'loss'}
        b=packet(altered,changed_cfg,action,None)
        self.assertEqual(a,b)

    def test_stress_hypotheses_share_capacity_and_ignore_own_selected_goods(self):
        obs,cfg,action,scenarios=fixture()
        rows=ti.stress_scenarios(DEPS.engine,obs,cfg)
        changed=deepcopy(obs);changed['private']['shed']={'TOMATO':100}
        self.assertEqual(rows,ti.stress_scenarios(DEPS.engine,changed,cfg))
        self.assertEqual(len(rows),21)
        self.assertTrue(all(sum(s['shed'].values())<=100 for s in rows))
        self.assertTrue(all(s['origin']=='current-snapshot-stress' for s in rows))

    def test_cell_limit_leaves_missing_cells_and_does_not_choose_partial_table(self):
        obs,cfg,action,scenarios=fixture()
        p=packet(obs,cfg,action,scenarios,max_cells=1)
        self.assertEqual(p['status'],'cell_limit');self.assertEqual(p['native_market_calls'],1)
        self.assertTrue(any(r['own_cash'] is None and r['done'] is False for r in p['document']['receipts']))
        table=DEPS.terminal.build_table(p['document']);self.assertFalse(table['solver_ready'])
        out,actor=cases.choose(DEPS,obs,cfg,action,p)
        self.assertEqual(out,action);self.assertEqual(actor.draws,0)

    def test_expired_deadline_executes_no_market(self):
        obs,cfg,action,scenarios=fixture()
        p=packet(obs,cfg,action,scenarios,deadline=time.perf_counter()-1)
        self.assertEqual(p['status'],'deadline');self.assertEqual(p['native_market_calls'],0)
        self.assertFalse(DEPS.terminal.build_table(p['document'])['terminal'])

    def test_snapshot_missing_stale_or_postmarket_is_not_consumed(self):
        obs,cfg,action,scenarios=fixture()
        good=cases.own_unit_snapshot(DEPS.engine,obs,cfg,action)
        wrong=[]
        for field,val in [('step',717),('player',1)]:
            p=deepcopy(good);p[field]=val;wrong.append(p)
        p=deepcopy(good);p['market']['inventory']['WHEAT']+=1;wrong.append(p)
        p=deepcopy(good);p['farms'][0]['money']+=1;wrong.append(p)
        for post in [None,*wrong]:
            with self.assertRaises(ValueError):
                ti.build_terminal_inputs(DEPS.engine,obs,cfg,action,post_unit_observation=post,scenarios=scenarios)

    def test_nonterminal_never_claims_done(self):
        obs,cfg,action,scenarios=fixture();obs['step']=717
        with self.assertRaises(ValueError): packet(obs,cfg,action,scenarios)

    def test_native_terminal_cash_is_same_even_when_final_step_is_day_close(self):
        obs,cfg,action,scenarios=fixture();cfg['episodeSteps']=721;obs['step']=719;obs['hour']=23
        obs['private']['inventories']=[{'CARROT':20}]
        p=packet(obs,cfg,action,scenarios)
        verify_native(self,obs,cfg,p)
        self.assertTrue(all(r['done'] for r in p['document']['receipts']))

    def test_shared_rival_capacity_and_whole_sale_validation(self):
        obs,cfg,action,scenarios=fixture()
        bad=[{'id':'x','shed':{'WHEAT':100,'MILK':1},'market':[]},
             {'id':'x','shed':{'WHEAT':1},'market':[['SELL','WHEAT',2]]},
             {'id':'x','shed':{'WHEAT':1},'market':[['SELL','WHEAT',1],['SELL','WHEAT',1]]},
             {'id':'x','shed':{'WHEAT':1},'market':[['BUY_PRODUCT','WHEAT',1]]},
             {'id':'x','shed':{'SECRET':1},'market':[]}]
        for value in bad:
            with self.subTest(value=value),self.assertRaises(ValueError):packet(obs,cfg,action,[value])
        with self.assertRaises(ValueError):packet(obs,cfg,action,[scenarios[0],scenarios[0]])

    def test_no_positive_goods_and_no_open_slot_keep_baseline_family(self):
        obs,cfg,action,scenarios=fixture();obs['private']['shed']={}
        p=packet(obs,cfg,action,scenarios)
        self.assertEqual(len(p['plans']),1)
        obs,cfg,action,scenarios=fixture();action['market']=[['BUY_SEED','WHEAT',1]]*10
        p=packet(obs,cfg,action,scenarios)
        self.assertEqual(len(p['plans']),1)
        verify_native(self,obs,cfg,p)

    def test_inactive_market_tail_and_nonmarket_metadata_preserved(self):
        obs,cfg,action,scenarios=fixture();cfg['maxMarketOrdersPerTurn']=2
        action['market']=[[],['SELL','MILK',2],['HIRE'],['BUY_SEED','WHEAT',1000000]]
        action['user_metadata']={'source':'selected'}
        p=packet(obs,cfg,action,[scenarios[0]])
        verify_native(self,obs,cfg,p)
        for plan in p['plans']:
            self.assertEqual(plan['action']['market'][2:],action['market'][2:])
            self.assertEqual(plan['action']['user_metadata'],action['user_metadata'])

    def test_input_and_returned_actions_are_detached(self):
        obs,cfg,action,scenarios=fixture();initial=deepcopy((obs,cfg,action,scenarios))
        p=packet(obs,cfg,action,scenarios)
        self.assertEqual((obs,cfg,action,scenarios),initial)
        p['plans'][0]['action']['market'][1][2]=999
        self.assertEqual(p['document']['receipts'][0]['own_action'],action)
        self.assertEqual(p['fallback_action'],action)

    def test_bounded_settings_and_oversized_order(self):
        obs,cfg,action,scenarios=fixture()
        for kw in [{'max_cells':257},{'max_cells':True},{'max_plans':9},{'deadline':float('nan')}]:
            with self.assertRaises(ValueError):packet(obs,cfg,action,scenarios,**kw)
        action['market'][1][2]=1001
        with self.assertRaises(ValueError):packet(obs,cfg,action,scenarios)

    def test_price_overrides_are_native_not_replaced_by_default_quotes(self):
        obs,cfg,action,scenarios=fixture()
        obs['market']['params']=DEPS.engine._resolve_market_params({'MILK':{'base':500}})
        DEPS.engine._refresh_prices(obs['market'])
        p=packet(obs,cfg,action,scenarios)
        verify_native(self,obs,cfg,p)
        self.assertGreater(p['document']['receipts'][0]['own_cash'],100800)

    def test_generated_rows_retain_original_action_binding_in_all_columns(self):
        obs,cfg,action,scenarios=fixture()
        p=packet(obs,cfg,action,None)
        for plan in p['plans']:
            receipts=[r for r in p['document']['receipts'] if r['plan']==plan['id']]
            self.assertEqual(len(receipts),len(p['scenarios']))
            self.assertTrue(all(r['own_action']==plan['action'] for r in receipts))
            self.assertEqual(len({r['plan_sha256'] for r in receipts}),1)
        self.assertEqual(len({r['public_state_sha256'] for r in p['document']['receipts']}),1)
        self.assertIsNone(p['source']['scenario_probabilities'])


def main():
    global DEPS
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--loader',type=Path,required=True);parser.add_argument('--engine-dir',type=Path,required=True)
    parser.add_argument('--consumers',type=Path,required=True);parser.add_argument('--core-file',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();DEPS=cases.dependencies(args.loader,args.engine_dir,args.consumers,args.core_file)
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(TerminalInputTests))
    report={'schema':'titan.terminal-inputs.tests.v1','methods':result.testsRun,'failures':len(result.failures),
            'errors':len(result.errors),'skips':len(result.skipped),'counts':COUNTS,'witnesses':WITNESSES,
            'engine_hashes':DEPS.engine_hashes,'log':stream.getvalue(),'full_games':0}
    with args.output.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2);f.write('\n')
    print(stream.getvalue());print(COUNTS)
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
