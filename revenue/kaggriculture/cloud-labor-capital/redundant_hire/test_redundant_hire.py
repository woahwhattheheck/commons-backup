# SPDX-License-Identifier: Apache-2.0
"""Real pinned-engine tests for the selected-action redundant-hire proposal.

Set TITAN_REPO_ROOT and TITAN_ENGINE_DIR to an existing source/engine cache.
No downloads, full-game panels, or hidden inputs to the proposal.
"""
from __future__ import annotations
import copy
import importlib.util
import json
import os
import random
from pathlib import Path
import sys
import unittest

from redundant_hire import NO_ORDER, propose_redundant_hires

ROOT = Path(os.environ['TITAN_REPO_ROOT']).resolve()
BASE = ROOT / 'revenue/kaggriculture'
spec = importlib.util.spec_from_file_location('idle_hire_existing_evaluator', BASE/'cloud-eval/evaluate.py')
ev = importlib.util.module_from_spec(spec); sys.modules[spec.name] = ev; spec.loader.exec_module(ev)
ENGINE, HASHES = ev.get_engine(Path(os.environ['TITAN_ENGINE_DIR']))
S = ev.Struct
NATIVE_TRANSITIONS = 0
GENERATED = {}
PASS = {'farmer':['PASS'], 'hands':[], 'market':[]}


def fixture(*, seat=0, step=21, hires=1, money=100.0):
    cfg = S({k:v.get('default') if isinstance(v,dict) else v
             for k,v in ENGINE.specification['configuration'].items()})
    cfg.seed = None
    farms = [ENGINE._new_farm(10, money) for _ in range(2)]
    private = ENGINE._new_private()
    farms[seat]['tiles'][4][5] = ENGINE._new_plant('CARROT',0,24)
    obs = S(step=step,day=step//24,hour=step%24,player=seat,farms=farms,
            private=private,market=ENGINE._new_market(),town=ENGINE._new_town())
    route = [copy.deepcopy(PASS) for _ in range(720)]
    action = {'farmer':['PASS'],'hands':[], 'market':[['HIRE'] for _ in range(hires)]}
    route[step] = copy.deepcopy(action)
    route[22] = {'farmer':['EAST'],'hands':[['WATER']], 'market':[]}
    route[23] = {'farmer':['WATER'],'hands':[['PASS']], 'market':[]}
    return obs,cfg,action,route


def proposal(obs,cfg,action,route, switches=()):
    return propose_redundant_hires(ENGINE,obs,cfg,action,
        route=route,route_id='explicit-test-route',route_switch_steps=switches)


def settle(obs,cfg,first,route):
    """Execute the unchanged full interpreter to daily reset, both real queues."""
    global NATIVE_TRANSITIONS
    farms=copy.deepcopy(obs['farms']); market=copy.deepcopy(obs['market']);town=copy.deepcopy(obs['town'])
    states=[]
    for i in range(2):
        own=copy.deepcopy(obs['private']) if i==obs['player'] else ENGINE._new_private()
        states.append(S(observation=S(player=i,farms=farms,market=market,town=town,private=own),
                        action={},status='ACTIVE',reward=0))
    env=S(configuration=copy.deepcopy(cfg),done=False,info={'seed':1234})
    # The engine's day RNG is supplied only to the evaluator, never the proposal.
    end=min((obs['step']//cfg.turnsPerDay+1)*cfg.turnsPerDay-1,cfg.episodeSteps-2)
    for t in range(obs['step'],end+1):
        for i in range(2):
            states[i].observation.update(step=t,day=t//cfg.turnsPerDay,hour=t%cfg.turnsPerDay)
            states[i].action=copy.deepcopy(first if i==obs['player'] and t==obs['step'] else route[t] if i==obs['player'] else PASS)
        ENGINE.interpreter(states,env);NATIVE_TRANSITIONS+=1
    return states


def physical(states):
    data=copy.deepcopy(states)
    for s in data:
        for f in s.observation.farms:f.pop('money',None)
        # Authoring a zero-order versus a hire is expected, not a state mismatch.
        s.pop('action',None)
    return data


class RedundantHireTests(unittest.TestCase):
    def test_actual_interpreter_duplicate_watering_both_positions(self):
        for seat in (0,1):
            with self.subTest(player=seat):
                obs,cfg,a,r=fixture(seat=seat)
                out,report=proposal(obs,cfg,a,r)
                self.assertTrue(report['changed']);self.assertEqual(out['market'],[NO_ORDER])
                self.assertEqual(report['immediate_wage_saving'],1)
                self.assertEqual(report['watering_witnesses'][0]['retained_watering'],[[23,0]])
                b,c=settle(obs,cfg,a,r),settle(obs,cfg,out,r)
                self.assertEqual(physical(b),physical(c))
                self.assertEqual(c[seat].observation.farms[seat]['money']-b[seat].observation.farms[seat]['money'],1)
                self.assertEqual(c[1-seat].observation.farms[1-seat]['money'],b[1-seat].observation.farms[1-seat]['money'])

    def test_useful_watering_is_not_removed(self):
        obs,cfg,a,r=fixture();r[23]['farmer']=['PASS']
        out,report=proposal(obs,cfg,a,r);self.assertFalse(report['changed']);self.assertEqual(out,a)

    def test_useful_harvest_or_feed_not_removed(self):
        for op in ['HARVEST','FEED','CARE','COLLECT_FERTILIZER','PICKUP','PLACE','PLANT','DIG']:
            obs,cfg,a,r=fixture();r[22]['hands']=[[op]]
            out,report=proposal(obs,cfg,a,r);self.assertFalse(report['changed']);self.assertEqual(out,a)

    def test_intervening_productive_tile_operations_not_assumed_equal(self):
        for op in ['HARVEST','FERTILIZE','DIG','PLANT']:
            obs,cfg,a,r=fixture();r[23]['farmer']=[op]
            out,report=proposal(obs,cfg,a,r);self.assertFalse(report['changed']);self.assertEqual(out,a)

    def test_already_watered_no_later_worker_needed(self):
        obs,cfg,a,r=fixture();obs['farms'][0]['tiles'][4][5]['watered_today']=True;r[23]['farmer']=['PASS']
        out,report=proposal(obs,cfg,a,r);self.assertTrue(report['changed'])
        self.assertEqual(physical(settle(obs,cfg,a,r)),physical(settle(obs,cfg,out,r)))

    def test_weed_and_midday_expiry_preserve_hire(self):
        expired=ENGINE._new_plant('CARROT',0,24);expired['max_lifespan_step']=22
        for tile in [{'kind':'WEED'},expired]:
            obs,cfg,a,r=fixture();obs['farms'][0]['tiles'][4][5]=tile
            out,report=proposal(obs,cfg,a,r);self.assertFalse(report['changed']);self.assertEqual(out,a)

    def test_future_hire_preserves_original_cost_and_spawn(self):
        obs,cfg,a,r=fixture();r[23]['market']=[['HIRE']]
        out,report=proposal(obs,cfg,a,r);self.assertEqual(report['reason'],'later_hire_changes_cost_or_spawn');self.assertEqual(out,a)

    def test_any_possible_route_switch_preserves_original(self):
        obs,cfg,a,r=fixture()
        out,report=proposal(obs,cfg,a,r,[22]);self.assertEqual(report['reason'],'possible_route_switch');self.assertEqual(out,a)
        self.assertTrue(proposal(obs,cfg,a,r,[21,24])[1]['changed'])

    def test_current_purchase_or_sale_retains_complete_queue(self):
        for extra in [['SELL','WHEAT',1],['BUY_SEED','CARROT',1],['BUY_PRODUCT','WHEAT',1],['BUY_LAND']]:
            obs,cfg,a,r=fixture();a['market'].append(extra)
            out,report=proposal(obs,cfg,a,r);self.assertFalse(report['changed']);self.assertEqual(out,a)

    def test_not_all_original_hires_funded(self):
        obs,cfg,a,r=fixture(hires=2,money=1.0)
        out,report=proposal(obs,cfg,a,r);self.assertEqual(report['reason'],'current_hires_not_all_funded');self.assertEqual(out,a)

    def test_zero_cost_and_invalid_cash(self):
        obs,cfg,a,r=fixture();cfg.farmHandCostMult=0
        self.assertFalse(proposal(obs,cfg,a,r)[1]['changed'])
        for money in [float('nan'),float('inf'),True,-1.0]:
            obs,cfg,a,r=fixture();obs['farms'][0]['money']=money
            self.assertFalse(proposal(obs,cfg,a,r)[1]['changed'])

    def test_slot_positions_and_trailing_suffix(self):
        obs,cfg,a,r=fixture(hires=2)
        a['market']=[list(NO_ORDER),['HIRE'],list(NO_ORDER),['HIRE']]
        r[22]['hands']=[['HARVEST'],['PASS']];r[23]['hands']=[['PASS'],['PASS']]
        out,report=proposal(obs,cfg,a,r)
        self.assertEqual(report['removed_order_indices'],[3]);self.assertEqual(len(out['market']),4)
        self.assertEqual(out['market'][1],['HIRE']);self.assertEqual(out['market'][3],NO_ORDER)

    def test_all_idle_new_hands_can_be_removed(self):
        obs,cfg,a,r=fixture(hires=3)
        r[22]=copy.deepcopy(PASS);r[23]=copy.deepcopy(PASS)
        out,report=proposal(obs,cfg,a,r)
        self.assertEqual(report['removed_workers'],3);self.assertEqual(report['immediate_wage_saving'],4)
        self.assertEqual(physical(settle(obs,cfg,a,r)),physical(settle(obs,cfg,out,r)))

    def test_no_mutation_of_observation_configuration_action_or_route(self):
        obs,cfg,a,r=fixture();before=copy.deepcopy((obs,cfg,a,r))
        out,report=proposal(obs,cfg,a,r);self.assertTrue(report['changed'])
        self.assertEqual((obs,cfg,a,r),before)
        out['market'][0][2]=99;self.assertEqual(a,before[2])

    def test_sparse_clock_and_optional_configuration(self):
        obs,cfg,a,r=fixture();expected=proposal(obs,cfg,a,r)
        obs.pop('step');self.assertEqual(proposal(obs,None,a,r),expected)
        obs['step']=None;self.assertEqual(proposal(obs,None,a,r),expected)

    def test_route_horizon_and_order_limit_are_explicit(self):
        obs,cfg,a,r=fixture();out,report=proposal(obs,cfg,a,r[:23]);self.assertEqual(report['reason'],'incomplete_route')
        cfg.maxMarketOrdersPerTurn=1;a['market'].append(['BUY_PRODUCT','WHEAT',20])
        out,report=proposal(obs,cfg,a,r);self.assertTrue(report['changed']);self.assertEqual(out['market'][1],a['market'][1])
        out,report=propose_redundant_hires(ENGINE,obs,cfg,a,route=r,route_id='r',route_switch_steps=[],max_route_steps=1)
        self.assertFalse(report['changed']);self.assertEqual(report['reason'],'outside_bounded_shift')

    def test_last_executable_turn_has_no_worker_value(self):
        obs,cfg,a,r=fixture(step=718,hires=2)
        out,report=proposal(obs,cfg,a,r);self.assertTrue(report['changed']);self.assertEqual(report['removed_workers'],2)
        b,c=settle(obs,cfg,a,r),settle(obs,cfg,out,r)
        self.assertEqual(c[0].reward-b[0].reward,2)
        self.assertEqual(c[0].status,'DONE')

    def test_generated_source_legal_storage_free_routes(self):
        rng=random.Random(12026);accepted=0
        for case in range(240):
            seat=case%2;obs,cfg,a,r=fixture(seat=seat,hires=1+case%3)
            f=obs['farms'][seat]
            # All tiles are visible, independent synthetic post-unit inputs.
            for y in range(3,7):
                for x in range(3,7):
                    pick=rng.randrange(5)
                    tile=ENGINE._new_plant('CARROT',0,24) if pick<3 else {'kind':'WEED'} if pick==3 else None
                    if isinstance(tile,dict) and tile.get('kind')=='PLANT':
                        tile['watered_today']=rng.choice([False,True])
                        if rng.random()<0.1:tile['max_lifespan_step']=22
                    f['tiles'][y][x]=tile
            for t in [22,23]:
                choices=[['PASS'],['WATER'],['NORTH'],['SOUTH'],['EAST'],['WEST']]
                r[t]={'farmer':copy.deepcopy(rng.choice(choices)),
                      'hands':[copy.deepcopy(rng.choice(choices)) for _ in range(case%3+1)],'market':[]}
            out,report=proposal(obs,cfg,a,r)
            if not report['changed']:continue
            accepted+=1
            b,c=settle(obs,cfg,a,r),settle(obs,cfg,out,r)
            with self.subTest(case=case,player=seat):
                self.assertEqual(physical(b),physical(c))
                self.assertEqual(c[seat].observation.farms[seat]['money']-b[seat].observation.farms[seat]['money'],report['immediate_wage_saving'])
        GENERATED.update(cases=240,accepted=accepted)
        self.assertGreater(accepted,25)

    def test_report_does_not_claim_terminal_or_opponent_guarantee(self):
        obs,cfg,a,r=fixture();_,report=proposal(obs,cfg,a,r)
        self.assertIsNone(report['terminal_gain']);self.assertIn('not established',report['future_cash_compatibility'])


if __name__=='__main__':
    report_path=None
    if '--report' in sys.argv:
        i=sys.argv.index('--report');report_path=Path(sys.argv[i+1]);del sys.argv[i:i+2]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RedundantHireTests))
    if report_path:
        report_path.write_text(json.dumps({'methods':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'native_transitions':NATIVE_TRANSITIONS,'generated_cases':GENERATED,'engine_sha256':HASHES},indent=2)+'\n')
    raise SystemExit(not result.wasSuccessful())
