# SPDX-License-Identifier: Apache-2.0
"""Direct family/producer consumer regressions; uses existing native dependencies."""
from copy import deepcopy
import argparse
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import terminal_input_cases as cases
import terminal_inputs as ti
from interior_liquidation import interior_liquidation_scenarios
from check_interior_liquidation import extend_packet

DEPS=None
NATIVE_COMPARISONS=0


def fixture(player=0):
    farm={'money':100000,'tiles':[[None]*10 for _ in range(10)],'farmer':[4,4],
          'hands':[],'unlocked_quadrants':['NW'],'hires_today':0}
    market={'inventory':{p:10000 for p in DEPS.engine.PRODUCTS},'prices':{}}
    DEPS.engine._refresh_prices(market)
    cfg=dict(episodeSteps=720,boardSize=10,turnsPerDay=24,shedCapacity=100,
             maxMarketOrdersPerTurn=10,farmHandCostMult=1)
    obs={'player':player,'step':718,'farms':[deepcopy(farm),deepcopy(farm)],'market':market,
         'private':{'shed':{'WHEAT':2,'MILK':2},'seeds':{},'inventories':[{}]},
         'day':29,'hour':22,'town':{'unlocked_shops':[]}}
    action={'farmer':['PASS'],'hands':[],'market':[[],['SELL','WHEAT',2],['SELL','MILK',2]]}
    return obs,cfg,action


class InteriorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if DEPS is None:raise unittest.SkipTest('Supply the existing native engine paths to this CLI')

    def test_original_twenty_one_scenarios_are_preserved(self):
        obs,cfg,_=fixture();base=ti.stress_scenarios(DEPS.engine,obs,cfg)
        new=interior_liquidation_scenarios(DEPS.engine,obs,cfg)
        self.assertEqual(len(base),21);self.assertEqual(len(new),32);self.assertEqual(new[:21],base)

    def test_middle_positions_and_full_shared_capacity(self):
        obs,cfg,_=fixture();family=interior_liquidation_scenarios(DEPS.engine,obs,cfg)
        for s in family[21:30]:
            self.assertEqual(s['market'][:5],[[]]*5)
            self.assertEqual(len(s['market']),6);self.assertEqual(sum(s['shed'].values()),100)
        self.assertEqual(len(ti._scenarios(DEPS.engine,family,ti._config(cfg))),32)

    def test_interleaving_is_deterministic_and_balanced(self):
        obs,cfg,_=fixture();a=interior_liquidation_scenarios(DEPS.engine,obs,cfg)
        self.assertEqual(a,interior_liquidation_scenarios(DEPS.engine,deepcopy(obs),deepcopy(cfg)))
        self.assertEqual([r[1] for r in a[-1]['market']],[r[1] for r in a[-2]['market']][::-1])
        self.assertEqual(sorted(a[-1]['shed'].values()),[11]*8+[12])

    def test_private_stock_actions_and_outcomes_are_not_inputs(self):
        obs,cfg,_=fixture();other=deepcopy(obs)
        other['private']={'shed':{'WOOL':100},'inventories':[{'MILK':100}], 'seeds':{}}
        other['farms'][1]['money']=3;other['rival_action']=[['SELL','MILK',100]];other['reward']=-123
        self.assertEqual(interior_liquidation_scenarios(DEPS.engine,obs,cfg),
                         interior_liquidation_scenarios(DEPS.engine,other,cfg))

    def test_no_mutation_and_detached_results(self):
        obs,cfg,_=fixture();before=deepcopy((obs,cfg))
        result=interior_liquidation_scenarios(DEPS.engine,obs,cfg);result[0]['shed']['MILK']=999
        self.assertEqual((obs,cfg),before)
        self.assertEqual(interior_liquidation_scenarios(DEPS.engine,obs,cfg)[0]['shed'],{})

    def test_small_native_limits_keep_valid_complete_hypotheses(self):
        obs,cfg,_=fixture()
        for limit in (1,2,3,9,32):
            for cap in (1,8,9,10,100):
                c={**cfg,'maxMarketOrdersPerTurn':limit,'shedCapacity':cap}
                family=interior_liquidation_scenarios(DEPS.engine,obs,c)
                self.assertLessEqual(len(family),32)
                self.assertEqual(len(ti._scenarios(DEPS.engine,family,ti._config(c))),len(family))
                keys=[ti.fingerprint((s['shed'],s['market'])) for s in family]
                # Original entries are preserved; only added duplicates are suppressed.
                self.assertEqual(len(keys[ len(ti.stress_scenarios(DEPS.engine,obs,c)): ]),
                                 len(set(keys)-set(keys[:len(ti.stress_scenarios(DEPS.engine,obs,c))])))

    def test_nonterminal_and_changed_rule_set_do_not_make_a_family(self):
        obs,cfg,_=fixture();obs['step']=717
        with self.assertRaises(ValueError):interior_liquidation_scenarios(DEPS.engine,obs,cfg)
        obs['step']=718
        with patch.object(DEPS.engine,'PRODUCTS',DEPS.engine.PRODUCTS[:-1]):
            with self.assertRaises(ValueError):interior_liquidation_scenarios(DEPS.engine,obs,cfg)

    def test_middle_cash_pair_is_not_an_extreme_slot_copy(self):
        obs,cfg,action=fixture();obs['private']['shed']={'MILK':2}
        action['market']=[[]]*5+[['SELL','MILK',2]]
        family=interior_liquidation_scenarios(DEPS.engine,obs,cfg)
        relevant=[s for s in family if s['shed']=={'MILK':100}]
        cash=[]
        for s in relevant:
            value=ti.market_cell(DEPS.engine,obs['farms'],obs['private'],obs['market'],cfg,0,action,s)
            cash.append((value['own_cash'],value['rival_cash']))
        self.assertEqual(len(cash),3);self.assertEqual(len(set(cash)),3)

    def test_added_cells_match_full_interpreter_in_both_positions(self):
        global NATIVE_COMPARISONS
        for player in (0,1):
            obs,cfg,action=fixture(player);family=interior_liquidation_scenarios(DEPS.engine,obs,cfg)
            post=cases.own_unit_snapshot(DEPS.engine,obs,cfg,action)
            packet=ti.build_terminal_inputs(DEPS.engine,obs,cfg,action,
                  post_unit_observation=post,scenarios=family[21:],max_plans=3)
            scenarios={s['id']:s for s in packet['scenarios']}
            for r in packet['document']['receipts']:
                state,env=cases.make_state(obs,cfg,r['own_action'],scenarios[r['scenario']])
                DEPS.engine.interpreter(state,env);NATIVE_COMPARISONS+=1
                self.assertEqual([s.status for s in state],['DONE','DONE'])
                self.assertEqual([r['own_cash'],r['rival_cash']],
                                 [state[player].reward,state[1-player].reward])

    def test_join_preserves_original_cells_and_refuses_new_plans(self):
        obs,cfg,action=fixture();family=interior_liquidation_scenarios(DEPS.engine,obs,cfg)
        post=cases.own_unit_snapshot(DEPS.engine,obs,cfg,action)
        old=ti.build_terminal_inputs(DEPS.engine,obs,cfg,action,post_unit_observation=post,scenarios=family[:21],max_plans=2)
        extra=ti.build_terminal_inputs(DEPS.engine,obs,cfg,action,post_unit_observation=post,scenarios=family[21:],max_plans=2)
        before=deepcopy(old);joined=extend_packet(old,extra);self.assertEqual(old,before)
        old_by_key={(r['plan'],r['scenario']):r for r in old['document']['receipts']}
        for r in joined['document']['receipts']:
            if (r['plan'],r['scenario']) in old_by_key:self.assertEqual(r,old_by_key[r['plan'],r['scenario']])
        extra['plans'][0]['id']='changed'
        with self.assertRaises(ValueError):extend_packet(old,extra)

    def test_partial_extra_family_cannot_start_selection(self):
        obs,cfg,action=fixture();family=interior_liquidation_scenarios(DEPS.engine,obs,cfg)
        post=cases.own_unit_snapshot(DEPS.engine,obs,cfg,action)
        old=ti.build_terminal_inputs(DEPS.engine,obs,cfg,action,post_unit_observation=post,scenarios=family[:21],max_plans=2)
        extra=ti.build_terminal_inputs(DEPS.engine,obs,cfg,action,post_unit_observation=post,scenarios=family[21:],max_plans=2,max_cells=0)
        joined=extend_packet(old,extra);self.assertFalse(joined['complete'])
        output,actor=cases.choose(DEPS,obs,cfg,action,joined)
        self.assertEqual(output,action);self.assertEqual(actor.draws,0)


def main():
    global DEPS
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--loader',type=Path,required=True);p.add_argument('--engine-dir',type=Path,required=True)
    p.add_argument('--consumers',type=Path,required=True);p.add_argument('--core-file',type=Path,required=True)
    p.add_argument('--score-file',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();DEPS=cases.dependencies(a.loader,a.engine_dir,a.consumers,a.core_file)
    DEPS.score=cases.load(a.score_file,'_interior_test_score')
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(InteriorTests))
    report={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
            'native_terminal_comparisons':NATIVE_COMPARISONS,'engine_hashes':DEPS.engine_hashes,'log':stream.getvalue()}
    with a.output.open('x') as out:json.dump(report,out,indent=2)
    print(stream.getvalue(),end='');print('native_terminal_comparisons',NATIVE_COMPARISONS)
    raise SystemExit(not result.wasSuccessful())


if __name__=='__main__':main()
