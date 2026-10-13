# SPDX-License-Identifier: Apache-2.0
"""Joined tests for opt-in pure cash dominance at an absolute-score tie."""
from copy import deepcopy
from fractions import Fraction as F
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from full_support import solve_full_table, verify_certificate
from terminal_utility import build_table
from selector import WholePlanSelector
from weighted_selector import make_selector
import score_endgame as score


def document(margins):
    ids=['baseline']+['p'+str(i) for i in range(1,len(margins))]
    scenarios=['s'+str(j) for j in range(len(margins[0]))]
    return {'plan_ids':ids,'scenario_ids':scenarios,'baseline':'baseline',
            'receipts':[{'plan':ids[i],'scenario':scenarios[j],'own_cash':str(100+F(x)),
                         'rival_cash':100,'done':True}
                         for i,row in enumerate(margins) for j,x in enumerate(row)]}


def solve(doc, **kwargs):
    return score.solve_absolute(doc,build_table,solve_full_table,verify_certificate,**kwargs)


def factory(**kwargs):
    return score.make_score_selector(WholePlanSelector,make_selector,build_table,
                                    solve_full_table,verify_certificate,**kwargs)


class Rng:
    def __init__(self):self.calls=0
    def randrange(self,n):self.calls+=1; return 0


def terminal_doc():
    doc=document([[-4,4],[-4,6]])
    base={'farmer':['PASS'],'hands':[],'market':[[],['SELL','WHEAT',2]]}
    alternative={**base,'market':[['SELL','WHEAT',2]]}
    for r in doc['receipts']:
        r.update(step=718,own_action=deepcopy(base if r['plan']=='baseline' else alternative))
    return doc,base,alternative


class CashTieTests(unittest.TestCase):
    def test_default_remains_baseline(self):
        ans=solve(document([[-4,4],[-4,6]]))
        self.assertEqual(ans['status'],'baseline_optimal')
        self.assertEqual(ans['weights'],['1','0'])
        self.assertNotIn('tie_break_certificate',ans)

    def test_opt_in_selects_weak_cash_dominance(self):
        doc=document([[-4,4],[-4,6]])
        ans=solve(doc,tie_break='cash_pareto')
        self.assertEqual(ans['weights'],['0','1'])
        self.assertEqual(ans['selection_reason'],'cash_pareto_tie')
        self.assertEqual(ans['cash_margin_change_by_scenario'],['0','2'])
        self.assertEqual(ans['value'],ans['optimal_worst_expected_win_points'])
        self.assertEqual(ans['value'],'0')
        self.assertIsNone(ans['scenario_probabilities'])
        self.assertIsNone(ans['win_probability'])
        check=verify_certificate(score.embedding(build_table(doc)),ans['tie_break_certificate'])
        self.assertTrue(check['valid'])
        self.assertEqual(check['lower_bound'],check['upper_bound'])

    def test_single_negative_column_retains_baseline(self):
        ans=solve(document([[-4,4],[-5,400]]),tie_break='cash_pareto')
        self.assertEqual(ans['weights'],['1','0'])

    def test_all_equal_cash_retains_baseline(self):
        ans=solve(document([[-4,4],[-4,4]]),tie_break='cash_pareto')
        self.assertEqual(ans['status'],'baseline_optimal')

    def test_first_caller_order_not_best_mean(self):
        doc=document([[-4,4],[-4,6],[-4,800]])
        ans=solve(doc,tie_break='cash_pareto')
        self.assertEqual(ans['weights'],['0','1','0'])

    def test_rival_cash_not_own_cash_is_objective(self):
        doc=document([[-4,4],[-4,4]])
        for r in doc['receipts'][2:]:r['own_cash']=str(F(r['own_cash'])+10);r['rival_cash']=111
        ans=solve(doc,tie_break='cash_pareto')
        self.assertEqual(ans['weights'],['1','0'])

    def test_primary_absolute_gain_precedes_tie(self):
        doc=document([[-4,4],[1,4],[-4,50]])
        left=solve(doc);right=solve(doc,tie_break='cash_pareto')
        self.assertEqual(left,right)
        self.assertEqual(right['weights'],['0','1','0'])

    def test_primary_mixture_unchanged(self):
        doc=document([[-4,-4],[1,-4],[-4,1]])
        self.assertEqual(solve(doc),solve(doc,tie_break='cash_pareto'))
        self.assertEqual(solve(doc)['weights'],['0','1/2','1/2'])

    def test_tied_win_points_half_are_exact(self):
        ans=solve(document([[0,4],[0,6]]),tie_break='cash_pareto')
        self.assertEqual(ans['value'],'1/2')
        self.assertEqual(ans['column_expectations'],['1/2','1'])

    def test_pivot_limit_does_not_activate_tie(self):
        ans=solve(document([[-4,4],[-4,6]]),tie_break='cash_pareto',max_pivots=0)
        self.assertEqual(ans['status'],'solver_incomplete')
        self.assertEqual(ans['weights'],['1','0'])

    def test_invalid_certificate_no_tie(self):
        def invalid(rows,**kw):
            ans=solve_full_table(rows,**kw);ans['value']='88';return ans
        ans=score.solve_absolute(document([[-4,4],[-4,6]]),build_table,invalid,
                                 verify_certificate,tie_break='cash_pareto')
        self.assertEqual(ans['status'],'invalid_certificate')
        self.assertEqual(ans['weights'],['1','0'])

    def test_closed_but_unfinished_is_not_selectable(self):
        def unfinished(rows,**kw):
            ans=solve_full_table(rows,**kw);ans['status']='pivot_limit';ans['exact']=False;return ans
        ans=score.solve_absolute(document([[-4,4],[-4,6]]),build_table,unfinished,
                                 verify_certificate,tie_break='cash_pareto')
        self.assertEqual(ans['status'],'solver_incomplete')

    def test_partial_receipts_do_not_call_solver(self):
        for case in ('nonterminal','missing','cash'):
            doc=document([[-4,4],[-4,6]])
            if case=='nonterminal':doc['receipts'][0]['done']=False
            if case=='missing':doc['receipts'].pop()
            if case=='cash':doc['receipts'][0]['own_cash']=None
            ans=score.solve_absolute(doc,build_table,lambda *_a,**_kw:self.fail('called'),
                                     verify_certificate,tie_break='cash_pareto')
            self.assertFalse(ans['solver_called'])

    def test_bad_option(self):
        for option in ('mean_cash','',None):
            with self.assertRaises(ValueError):solve(document([[-4,4],[-4,6]]),tie_break=option)
            with self.assertRaises(ValueError):factory(tie_break=option)

    def test_original_input_and_cached_result_detached(self):
        doc=document([[-4,4],[-4,6]]);before=deepcopy(doc)
        rows=score.embedding(build_table(doc));raw=solve_full_table(rows)
        ans=solve(doc,tie_break='cash_pareto')
        self.assertEqual(ans['raw_solver'],raw)
        self.assertEqual(doc,before)
        ans['tie_break_certificate']['weights'][0]='99'
        self.assertEqual(solve_full_table(rows),raw)

    def test_full_terminal_action_provider_remapping(self):
        doc,base,alternative=terminal_doc();rng=Rng();obj=factory(rng=rng,tie_break='cash_pareto')
        obs={'step':718,'player':0}
        out=obj.transform_terminal(obs,{},base,document=doc,feasible=lambda _:True)
        self.assertEqual(out,alternative)
        self.assertEqual(obj.active['plan_index'],1)
        self.assertEqual(obj.active['weights'],['0','1'])
        self.assertEqual(obj.last_objective['value'],'0')
        self.assertEqual(obj.last_objective['raw_solver']['value'],'1')
        self.assertEqual(obj.transform_terminal(obs,{},base,document=doc,feasible=lambda _:True),alternative)
        self.assertEqual(rng.calls,1)
        self.assertEqual(obj.provider_calls,1)

    def test_feasibility_unknown_prevents_selection(self):
        doc,base,alternative=terminal_doc();rng=Rng();obj=factory(rng=rng,tie_break='cash_pareto')
        self.assertEqual(obj.transform_terminal({'step':718,'player':0},{},base,document=doc,
                         feasible=lambda a:None if a==alternative else True),base)
        self.assertEqual(rng.calls,0)
        self.assertEqual(obj.provider_calls,0)

    def test_parent_change_retires_commitment(self):
        doc,base,alternative=terminal_doc();rng=Rng();obj=factory(rng=rng,tie_break='cash_pareto');obs={'step':718,'player':0}
        obj.transform_terminal(obs,{},base,document=doc,feasible=lambda _:True)
        fresh=deepcopy(doc);base['farmer']=['DROP','WHEAT',1]
        for r in fresh['receipts']:r['own_action']['farmer']=base['farmer']
        self.assertEqual(obj.transform_terminal(obs,{},base,document=fresh,feasible=lambda _:True),base)
        self.assertIsNone(obj.active)
        self.assertEqual(rng.calls,1)

    def test_column_order_does_not_change_pure_choice(self):
        doc=document([[-4,4],[-4,6]])
        shuffled=deepcopy(doc);shuffled['scenario_ids'].reverse();shuffled['receipts'].reverse()
        a=solve(doc,tie_break='cash_pareto');b=solve(shuffled,tie_break='cash_pareto')
        self.assertEqual(a['weights'],b['weights'])
        self.assertEqual(a['value'],b['value'])
        self.assertEqual(a['cash_margin_change_by_scenario'],list(reversed(b['cash_margin_change_by_scenario'])))

    def test_context_cash_change_retires_cash_tie_choice(self):
        doc,base,alternative=terminal_doc();rng=Rng();obj=factory(rng=rng,tie_break='cash_pareto')
        obs={'step':718,'player':0,'farms':[{'money':100},{'money':100}]}
        self.assertEqual(obj.transform_terminal(obs,{},base,document=doc,feasible=lambda _:True),alternative)
        changed=deepcopy(obs);changed['farms'][0]['money']=99
        self.assertEqual(obj.transform_terminal(changed,{},base,document=doc,feasible=lambda _:True),base)
        self.assertIsNone(obj.active);self.assertIsNone(obj.last_objective)
        self.assertEqual(obj.draws,1);self.assertEqual(obj.provider_calls,1)
        self.assertEqual(obj.transform_terminal(obs,{},base,document=doc,feasible=lambda _:True),base)
        self.assertEqual(obj.draws,1)

    def test_context_receipt_change_no_redraw(self):
        doc,base,alternative=terminal_doc();obj=factory(tie_break='cash_pareto');obs={'step':718,'player':0}
        obj.transform_terminal(obs,{},base,document=doc,feasible=lambda _:True)
        changed=deepcopy(doc);changed['receipts'][-1]['own_cash']='107'
        self.assertEqual(obj.transform_terminal(obs,{},base,document=changed,feasible=lambda _:True),base)
        self.assertIsNone(obj.active);self.assertEqual(obj.draws,1);self.assertEqual(obj.provider_calls,1)

    def test_context_unavailable_no_stale_objective(self):
        doc,base,alternative=terminal_doc();obj=factory(tie_break='cash_pareto');obs={'step':718,'player':0}
        obj.transform_terminal(obs,{},base,document=doc,feasible=lambda _:True)
        self.assertEqual(obj.transform_terminal(obs,{},base,document={},feasible=lambda _:True),base)
        self.assertIsNone(obj.active);self.assertIsNone(obj.last_objective)
        self.assertEqual(obj.draws,1)

    def test_context_ignores_diagnostic_labels_with_same_choice(self):
        doc,base,alternative=terminal_doc();obj=factory(tie_break='cash_pareto');obs={'step':718,'player':0}
        obj.transform_terminal(obs,{},base,document=doc,feasible=lambda _:True)
        changed=deepcopy(doc);changed['source']={'record_label':'different'}
        for r in changed['receipts']:r['evaluation_only']='different'
        self.assertEqual(obj.transform_terminal({**obs,'remainingOverageTime':99},{'seed':1},base,
                         document=changed,feasible=lambda _:True),alternative)
        self.assertEqual(obj.draws,1);self.assertEqual(obj.provider_calls,1)

    def test_cli_opt_in(self):
        import terminal_utility,full_support
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.json';p.write_text(json.dumps(document([[-4,4],[-4,6]])))
            cmd=[sys.executable,score.__file__,'--input',str(p),'--terminal-file',terminal_utility.__file__,
                 '--solver-file',full_support.__file__,'--tie-break','cash_pareto']
            result=subprocess.run(cmd,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['weights'],['0','1'])


if __name__=='__main__':unittest.main(verbosity=2)
