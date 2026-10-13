# SPDX-License-Identifier: Apache-2.0
"""Pure consumer checks. Synthetic cash tables are not game or forecast evidence."""
from copy import deepcopy
from fractions import Fraction as F
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from dated_scenarios import CashScenario, DatedSelector, compare_routes
from test_physical_outcomes import fixture


def nominal(matrix, names=None):
    names = names or [f's{i}' for i in range(len(matrix[0]))]
    ids = [f'r{i}' for i in range(len(matrix))]
    offers = [{'route_id': key, 'orders': [
        {'step': 226, 'slot': 0, 'order': ['SELL','WOOL',1], 'delta': 0}]} for key in ids]
    scenarios = [CashScenario(name, {key: {(226,0): row[j]} for key, row in zip(ids,matrix)})
                 for j,name in enumerate(names)]
    observation = {'step':226,'player':0,'farms':[{'money':0},{'money':100}]}
    return offers, observation, scenarios


def compare(matrix, **kwargs):
    return compare_routes(*nominal(matrix), **kwargs)


def physical_matrix(matrix):
    obs, offers, replay = fixture()
    for case in replay['cases']:
        i = 0 if case['offered_route']=='main' else 1
        j = 0 if case['scenario_id']=='a' else 1
        value = matrix[i][j]
        case.update(final_cash=value,cash_gain=value-100,minimum_after_market_cash=min(90,value))
        case['market_rows'][1].update(cash_after=value,cash_delta=value-90)
        case['market_rows'][2].update(cash_before=value,cash_after=value)
        case['result']['farm']['money']=value
        case['result']['cash_gain']=value-100
    return obs,offers,replay


class ObjectiveTests(unittest.TestCase):
    def test_robust_default_retains_original_report_shape(self):
        args=nominal([[100,100],[110,80]])
        result=compare_routes(*args)
        self.assertEqual(result,compare_routes(*args,objective='robust'))
        self.assertNotIn('decision_objective',result)
        self.assertEqual(result['selected'],'r0')

    def test_expected_cash_uses_all_named_weights(self):
        result=compare([[100,100],[150,80]],objective='expected_cash',scenario_weights={'s0':'1/2','s1':'1/2'})
        self.assertEqual(result['selected'],'r1')
        self.assertEqual(result['objective_values']['r1']['expected_paired_gain'],'15')
        self.assertFalse(result['probabilities_calibrated'])
        self.assertIsNone(result['rival_utility'])

    def test_expected_weight_direction_and_exact_crossover(self):
        matrix=[[89291,109492],[84040,118750]]
        for probability, chosen in [(F(0),'r0'),(F(1,4),'r0'),(F(5251,14509),'r0'),(F(1,2),'r1'),(F(1),'r1')]:
            result=compare(matrix,objective='expected_cash',scenario_weights={'s0':1-probability,'s1':probability})
            self.assertEqual(result['selected'],chosen)
            self.assertEqual(F(result['objective_values']['r1']['expected_paired_gain']),-5251+14509*probability)

    def test_minimax_regret_changes_one_route_without_probabilities(self):
        result=compare([[89291,109492],[84040,118750]],objective='minimax_regret')
        self.assertEqual(result['selected'],'r1')
        self.assertEqual(result['objective_values']['r0']['worst_regret'],'9258')
        self.assertEqual(result['objective_values']['r1']['worst_regret'],'5251')
        self.assertEqual(result['objective_values']['r1']['worst_regret_reduction'],'4007')
        self.assertIsNone(result['scenario_weights'])

    def test_expected_strict_margin_and_incumbent_tie(self):
        for threshold,chosen in [(0,'r1'),(9,'r1'),(10,'r0')]:
            self.assertEqual(compare([[100],[110]],objective='expected_cash',scenario_weights={'s0':1},minimum_gain=threshold)['selected'],chosen)
        self.assertEqual(compare([[100,100],[90,110]],objective='expected_cash',scenario_weights={'s0':'1/2','s1':'1/2'})['selected'],'r0')

    def test_regret_strict_margin_and_equal_worst_regret(self):
        for threshold,chosen in [(0,'r1'),(4007,'r0')]:
            self.assertEqual(compare([[89291,109492],[84040,118750]],objective='minimax_regret',minimum_gain=threshold)['selected'],chosen)
        self.assertEqual(compare([[100,200],[200,100]],objective='minimax_regret')['selected'],'r0')

    def test_equal_alternatives_keep_offer_order(self):
        for mode,options in [('expected_cash',{'scenario_weights':{'s0':1}}),('minimax_regret',{})]:
            self.assertEqual(compare([[100],[110],[110]],objective=mode,**options)['selected'],'r1')

    def test_weight_names_not_list_position_bind_scenarios(self):
        offers,obs,scenarios=nominal([[100,100],[150,80]])
        kwargs={'objective':'expected_cash','scenario_weights':{'s0':'1/4','s1':'3/4'}}
        a=compare_routes(offers,obs,scenarios,**kwargs)
        b=compare_routes(offers,obs,list(reversed(scenarios)),**kwargs)
        self.assertEqual(a['selected'],b['selected'])
        self.assertEqual(a['objective_values'],b['objective_values'])

    def test_missing_extra_or_nonunit_weight_bank_returns_fallback(self):
        for weights in (None,{}, {'s0':1}, {'s0':1,'s1':0,'extra':0}, {'s0':1,'s1':1}, {'s0':-1,'s1':2}):
            result=compare([[100,100],[120,120]],objective='expected_cash',scenario_weights=weights)
            self.assertEqual(result['selected'],'r0')
            self.assertEqual(result['reason'],'objective_input_invalid')

    def test_invalid_nonfinite_boolean_weights_return_fallback(self):
        for invalid in (True,None,'nan','inf','1/0',float('nan'),float('inf'),{},[]):
            result=compare([[100,100],[120,120]],objective='expected_cash',scenario_weights={'s0':invalid,'s1':0})
            self.assertEqual(result['selected'],'r0')
            self.assertEqual(result['reason'],'objective_input_invalid')

    def test_declared_decimal_weights_remain_exact(self):
        result=compare([[100]*3,[110]*3],objective='expected_cash',scenario_weights={'s0':0.1,'s1':0.2,'s2':0.7})
        self.assertEqual(result['selected'],'r1')
        self.assertEqual(result['scenario_weights'],{'s0':'1/10','s1':'1/5','s2':'7/10'})

    def test_no_silent_weights_in_robust_or_regret_mode(self):
        for mode in ('robust','minimax_regret','unknown'):
            result=compare([[100],[120]],objective=mode,scenario_weights={'s0':1})
            self.assertEqual(result['selected'],'r0')
            self.assertEqual(result['reason'],'objective_input_invalid')

    def test_zero_weight_scenario_still_needs_complete_candidate(self):
        offers,obs,scenarios=nominal([[100,100],[120,120]])
        del scenarios[1].flows['r1']
        result=compare_routes(offers,obs,scenarios,objective='expected_cash',scenario_weights={'s0':1,'s1':0})
        self.assertEqual(result['selected'],'r0')
        self.assertFalse(result['candidates']['r1']['complete'])

    def test_missing_incumbent_never_ranked(self):
        offers,obs,scenarios=nominal([[100],[120]])
        del scenarios[0].flows['r0']
        for mode in ('expected_cash','minimax_regret'):
            result=compare_routes(offers,obs,scenarios,objective=mode)
            self.assertEqual(result['selected'],'r0')
            self.assertEqual(result['reason'],'incumbent_scenario_incomplete')

    def test_ineligible_route_cannot_distort_regret_reference(self):
        offers,obs,scenarios=nominal([[100,100],[200,90],[0,1000]])
        # r2 spends before its declared receipt and is therefore not eligible.
        offers[2]['orders'].insert(0,{'step':226,'slot':0,'order':['HIRE'],'delta':-1})
        offers[2]['orders'][1]['slot']=1
        for sc in scenarios:
            sc.flows['r2'][(226,1)]=sc.flows['r2'].pop((226,0))+1
        result=compare_routes(offers,obs,scenarios,objective='minimax_regret')
        self.assertEqual(result['selected'],'r1')
        self.assertEqual(result['eligible_routes'],['r0','r1'])
        self.assertEqual(result['scenario_best_own_cash'],{'s0':'200','s1':'100'})

    def test_zero_weight_case_cannot_hide_budget_failure(self):
        offers,obs,scenarios=nominal([[100,100],[200,200]])
        offers[1]['orders']=[{'step':226,'slot':0,'order':['BUY_PRODUCT','WHEAT',1],'delta':0},
                             {'step':226,'slot':1,'order':['SELL','WOOL',1],'delta':0}]
        scenarios[0].flows['r1']={(226,0):0,(226,1):200}
        scenarios[1].flows['r1']={(226,0):-10,(226,1):210}
        result=compare_routes(offers,obs,scenarios,objective='expected_cash',scenario_weights={'s0':1,'s1':0})
        self.assertEqual(result['selected'],'r0')
        self.assertFalse(result['candidates']['r1']['nominal_budget_nonnegative'])

    def test_incumbent_negative_budget_keeps_fallback(self):
        offers,obs,scenarios=nominal([[100],[120]])
        offers[0]['orders'].insert(0,{'step':226,'slot':0,'order':['HIRE'],'delta':-1})
        offers[0]['orders'][1]['slot']=1
        scenarios[0].flows['r0']={(226,1):101}
        result=compare_routes(offers,obs,scenarios,objective='minimax_regret')
        self.assertEqual(result['reason'],'incumbent_budget_unsupported')
        self.assertEqual(result['selected'],'r0')

    def test_selector_copies_weights_and_keeps_input_immutable(self):
        args=nominal([[100,100],[150,80]]); before=deepcopy(args)
        weights={'s0':'1/2','s1':'1/2'}
        selector=DatedSelector(args[2],objective='expected_cash',scenario_weights=weights)
        weights['s0']=0
        self.assertEqual(selector(args[0],args[1]),'r1')
        self.assertEqual(args,before)
        json.dumps(selector.last_report,allow_nan=False)

    def test_physical_path_uses_same_objectives_and_original_rows(self):
        obs,offers,replay=physical_matrix([[100,100],[150,80]])
        before=deepcopy((obs,offers,replay))
        selector=DatedSelector.from_completed_replay(replay,{'episodeSteps':4},scenario_ids=['a','b'],
                  objective='expected_cash',scenario_weights={'a':'1/2','b':'1/2'})
        self.assertEqual(selector(offers,obs),'sheep')
        self.assertEqual(selector.last_report['objective_values']['sheep']['expected_paired_gain'],'15')
        self.assertEqual((obs,offers,replay),before)
        self.assertEqual(selector.last_report['minimum_cash_scope'],'observed_after_whole_market_queue_not_per_slot')

    def test_physical_partial_zero_weight_and_foreign_inputs_stay_invalid(self):
        for edit in ('missing','partial','foreign','nonterminal'):
            obs,offers,replay=physical_matrix([[100,100],[150,80]])
            if edit=='missing': replay['cases'].pop()
            elif edit=='partial': replay['complete']=False
            elif edit=='foreign': obs['player']=1
            else: replay['end_step']=1
            selector=DatedSelector.from_completed_replay(replay,{'episodeSteps':4},scenario_ids=['a','b'],
                     objective='expected_cash',scenario_weights={'a':1,'b':0})
            self.assertEqual(selector(offers,obs),'main')
            self.assertEqual(selector.last_report['reason'],'execution_report_invalid')

    def test_physical_cache_revalidates_each_call(self):
        obs,offers,replay=physical_matrix([[100,100],[150,80]])
        selector=DatedSelector.from_completed_replay(replay,{'episodeSteps':4},scenario_ids=['a','b'],objective='minimax_regret')
        self.assertEqual(selector(offers,obs),'sheep')
        replay['cases'].pop()
        self.assertEqual(selector(offers,obs),'main')

    def test_no_scenarios_retains_incumbent(self):
        offers,obs,_=nominal([[100],[120]])
        result=compare_routes(offers,obs,[],objective='expected_cash',scenario_weights={})
        self.assertEqual(result['selected'],'r0')
        self.assertEqual(result['reason'],'no_scenarios')

    def test_single_route_has_zero_regret_and_no_change(self):
        result=compare([[100,200]],objective='minimax_regret')
        self.assertEqual(result['selected'],'r0')
        self.assertEqual(result['objective_values']['r0']['worst_regret'],'0')

    def test_cli_uses_declared_objective(self):
        offers,obs,_=nominal([[100,100],[150,80]])
        data={'offers':offers,'observation':obs,'objective':'expected_cash','scenario_weights':{'s0':'1/2','s1':'1/2'},
              'scenarios':[{'name':n,'flows':{r:[{'step':226,'slot':0,'delta':v}] for r,v in zip(['r0','r1'],cash)}}
                           for n,cash in [('s0',[100,150]),('s1',[100,80])]]}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'input.json';path.write_text(json.dumps(data))
            proc=subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('dated_scenarios.py')),str(path)],capture_output=True,text=True,check=True)
            self.assertEqual(json.loads(proc.stdout)['selected'],'r1')

    def test_generated_tables_match_independent_direct_enumeration(self):
        rng=random.Random(741052)
        for case in range(1000):
            n,m=rng.randint(1,8),rng.randint(1,8)
            matrix=[[rng.randint(0,1000) for _ in range(m)] for _ in range(n)]
            ints=[rng.randint(0,20) for _ in range(m)];ints[0]+=1
            weights=[F(x,sum(ints)) for x in ints]
            margin=rng.randint(0,10)
            expected=[sum(w*x for w,x in zip(weights,row)) for row in matrix]
            optimum=max(range(n),key=lambda i:expected[i])
            choice=optimum if expected[optimum]-expected[0]>margin else 0
            report=compare(matrix,objective='expected_cash',scenario_weights={f's{j}':w for j,w in enumerate(weights)},minimum_gain=margin)
            self.assertEqual(report['selected'],f'r{choice}',case)
            reference=[max(row[j] for row in matrix) for j in range(m)]
            regrets=[max(a-b for a,b in zip(reference,row)) for row in matrix]
            optimum=min(range(n),key=lambda i:regrets[i])
            choice=optimum if regrets[0]-regrets[optimum]>margin else 0
            report=compare(matrix,objective='minimax_regret',minimum_gain=margin)
            self.assertEqual(report['selected'],f'r{choice}',case)


if __name__=='__main__':
    unittest.main()
