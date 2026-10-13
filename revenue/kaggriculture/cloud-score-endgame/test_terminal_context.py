# SPDX-License-Identifier: Apache-2.0
"""Actual terminal selector continuity tests; no engine or game calls.

Pass the existing flattened PORT/POLY/PRISM/T15 dependency directory and the
exact score runtime. All assertions use the real receipt builder and selector.
Receipts below are explicit constructed contract fixtures, not game evidence.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys
import unittest

D = None


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configure(runtime, consumers):
    global D
    from types import SimpleNamespace
    old = sys.modules.get('solver')
    sys.modules['solver'] = load(consumers/'solver.py', '_anchor_t15_solver')
    try:
        selector = load(consumers/'selector.py', '_anchor_t15_selector')
    finally:
        if old is None:
            sys.modules.pop('solver', None)
        else:
            sys.modules['solver'] = old
    D = SimpleNamespace(score=load(runtime, '_anchor_score'),
        terminal=load(consumers/'terminal_utility.py', '_anchor_port'),
        core=load(consumers/'full_support.py', '_anchor_poly'),
        weighted=load(consumers/'weighted_selector.py', '_anchor_prism'), selector=selector)


def fixture(player=0):
    obs = {'step':718, 'player':player,
           'farms':[{'money':100033, 'hands':[]}, {'money':100000, 'hands':[]}],
           'private':{'shed':{'WHEAT':2,'MILK':2}, 'seeds':{}, 'inventories':[{}]},
           'market':{'inventory':{'WHEAT':10000,'MILK':10000}},
           'town':{'unlocked_shops':[]}}
    base = {'farmer':['PASS'], 'hands':[],
            'market':[[],['SELL','WHEAT',2],['SELL','MILK',2]]}
    alt = deepcopy(base)
    alt['market'] = [['SELL','WHEAT',2], ['SELL','MILK',2], []]
    other = deepcopy(base)
    other['market'] = [['SELL','MILK',2], ['SELL','WHEAT',2], []]
    actions = [base, alt, other]
    plans = ['baseline','wheat-first','milk-first']
    margins = [[-1,1], [4,2], [-1,9]]
    doc = {'plan_ids':plans, 'scenario_ids':['rival-A','rival-B'], 'baseline':'baseline',
           'source':{'scope':'constructed contract fixture'}, 'receipts':[]}
    for i, plan in enumerate(plans):
        for j, scenario in enumerate(doc['scenario_ids']):
            doc['receipts'].append({'plan':plan, 'scenario':scenario,
                'step':718, 'own_action':deepcopy(actions[i]),
                'own_cash':100000+margins[i][j], 'rival_cash':100000, 'done':True,
                'plan_sha256':'fixture-plan-'+plan, 'scenario_sha256':'fixture-scenario-'+scenario,
                'public_state_sha256':'fixture-state'})
    return obs, {'episodeSteps':720}, base, alt, doc


def actor():
    return D.score.make_score_selector(D.selector.WholePlanSelector,
        D.weighted.make_selector, D.terminal.build_table,
        D.core.solve_full_table, D.core.verify_certificate, rng=random.Random(5307))


def call(s, obs, cfg, base, doc, feasible=lambda action:True):
    return s.transform_terminal(obs,cfg,base,document=doc,feasible=feasible)


class TerminalContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if D is None:
            raise unittest.SkipTest('Run with the exact runtime and existing consumer directory')

    def begin(self, player=0):
        obs,cfg,base,alt,doc=fixture(player)
        s=actor()
        self.assertEqual(call(s,obs,cfg,base,doc),alt)
        self.assertEqual((s.provider_calls,s.draws),(1,1))
        return s,obs,cfg,base,alt,doc

    def retired(self,s,obs,cfg,base,doc,original=None):
        self.assertEqual(call(s,obs,cfg,base,doc),base)
        self.assertIsNone(s.active)
        self.assertIsNone(s.last_objective)
        self.assertIn(('terminal-score',obs['player'],obs['step']),s.completed)
        self.assertEqual((s.provider_calls,s.draws),(1,1))
        if original is not None:
            ob,cf,ba,do=original
            self.assertEqual(call(s,ob,cf,ba,do),ba)
            self.assertEqual((s.provider_calls,s.draws),(1,1))

    def test_identical_retry_preserves_one_draw_and_detaches_inputs(self):
        s,obs,cfg,base,alt,doc=self.begin()
        saved=deepcopy((obs,cfg,base,doc))
        out=call(s,obs,cfg,base,doc)
        self.assertEqual(out,alt)
        out['market'][0][2]=900
        self.assertEqual((obs,cfg,base,doc),saved)
        self.assertEqual(s.active['plan']['action'],alt)
        self.assertEqual((s.provider_calls,s.draws),(1,1))

    def test_current_cash_changes_even_with_stale_receipts(self):
        for player in (0,1):
            with self.subTest(player=player):
                s,obs,cfg,base,alt,doc=self.begin(player)
                original=deepcopy((obs,cfg,base,doc))
                obs['farms'][player]['money']-=3
                self.retired(s,obs,cfg,base,doc,original)

    def test_changed_fresh_cash_evidence_retires_both_seats(self):
        for player in (0,1):
            with self.subTest(player=player):
                s,obs,cfg,base,alt,doc=self.begin(player)
                obs['farms'][player]['money']-=3
                for r in doc['receipts']:
                    r['own_cash']-=3
                    r['public_state_sha256']='new-current-state'
                fresh=D.score.solve_absolute(doc,D.terminal.build_table,
                       D.core.solve_full_table,D.core.verify_certificate)
                self.assertEqual(fresh['value'],'1/2')
                self.retired(s,obs,cfg,base,doc)

    def test_market_inventory_change_retires(self):
        s,obs,cfg,base,alt,doc=self.begin()
        obs['market']['inventory']['MILK']+=10
        self.retired(s,obs,cfg,base,doc)

    def test_private_stock_change_retires(self):
        s,obs,cfg,base,alt,doc=self.begin()
        obs['private']['shed']['WHEAT']+=1
        self.retired(s,obs,cfg,base,doc)

    def test_town_change_retires(self):
        s,obs,cfg,base,alt,doc=self.begin()
        obs['town']['unlocked_shops'].append('YARN_STORE')
        self.retired(s,obs,cfg,base,doc)

    def test_economic_configuration_change_retires(self):
        for key,value in [('boardSize',11),('turnsPerDay',25),('shedCapacity',99),
                          ('maxMarketOrdersPerTurn',9),('farmHandCostMult',2)]:
            with self.subTest(key=key):
                s,obs,cfg,base,alt,doc=self.begin()
                cfg[key]=value
                self.retired(s,obs,cfg,base,doc)

    def test_no_longer_terminal_configuration_retires(self):
        s,obs,cfg,base,alt,doc=self.begin()
        original=deepcopy((obs,cfg,base,doc))
        cfg['episodeSteps']=721
        self.retired(s,obs,cfg,base,doc,original)

    def test_changed_terminal_cash_alone_retires(self):
        s,obs,cfg,base,alt,doc=self.begin()
        for r in doc['receipts']:r['own_cash']-=3
        self.retired(s,obs,cfg,base,doc)

    def test_changed_scenario_binding_retires(self):
        s,obs,cfg,base,alt,doc=self.begin()
        for r in doc['receipts']:
            if r['scenario']=='rival-A':r['scenario_sha256']='replaced-whole-scenario'
        self.retired(s,obs,cfg,base,doc)

    def test_changed_public_binding_retires(self):
        s,obs,cfg,base,alt,doc=self.begin()
        for r in doc['receipts']:r['public_state_sha256']='other-state'
        self.retired(s,obs,cfg,base,doc)

    def test_unselected_plan_evidence_change_retires(self):
        s,obs,cfg,base,alt,doc=self.begin()
        for r in doc['receipts']:
            if r['plan']=='milk-first':
                r['own_action']['market'][0][2]=1
                r['plan_sha256']='other-unselected-plan'
        self.retired(s,obs,cfg,base,doc)

    def test_changed_scenario_order_retires_without_resampling(self):
        s,obs,cfg,base,alt,doc=self.begin()
        doc['scenario_ids'].reverse()
        self.retired(s,obs,cfg,base,doc)

    def test_raw_receipt_order_is_normalized(self):
        s,obs,cfg,base,alt,doc=self.begin()
        doc['receipts'].reverse()
        self.assertEqual(call(s,obs,cfg,base,doc),alt)
        self.assertEqual((s.provider_calls,s.draws),(1,1))

    def test_cash_representation_is_normalized_by_port(self):
        s,obs,cfg,base,alt,doc=self.begin()
        for r in doc['receipts']:
            r['own_cash']=str(r['own_cash']);r['rival_cash']=str(r['rival_cash'])
        self.assertEqual(call(s,obs,cfg,base,doc),alt)
        self.assertEqual((s.provider_calls,s.draws),(1,1))

    def test_evaluator_metadata_and_source_labels_are_not_policy_inputs(self):
        s,obs,cfg,base,alt,doc=self.begin()
        obs.update(seed=999,opponent_private={'MILK':900},evaluation_outcome='loss')
        cfg.update(seed=999,evaluation_outcome='win',remainingOverageTime=19)
        doc['source']={'changed_diagnostic_label':True}
        self.assertEqual(call(s,obs,cfg,base,doc),alt)
        self.assertEqual((s.provider_calls,s.draws),(1,1))

    def test_explicit_defaults_match_omitted_defaults(self):
        s,obs,cfg,base,alt,doc=self.begin()
        cfg.update(boardSize=10,turnsPerDay=24,shedCapacity=100,
                   maxMarketOrdersPerTurn=10,farmHandCostMult=1)
        self.assertEqual(call(s,obs,cfg,base,doc),alt)
        self.assertEqual((s.provider_calls,s.draws),(1,1))

    def test_incomplete_retry_cannot_revive_old_draw(self):
        for change in ('missing','cash','done'):
            with self.subTest(change=change):
                s,obs,cfg,base,alt,doc=self.begin()
                original=deepcopy((obs,cfg,base,doc))
                if change=='missing':doc['receipts'].pop()
                elif change=='cash':doc['receipts'][0]['own_cash']=None
                else:doc['receipts'][0]['done']=False
                self.retired(s,obs,cfg,base,doc,original)

    def test_malformed_retry_cannot_revive_old_draw(self):
        s,obs,cfg,base,alt,doc=self.begin()
        original=deepcopy((obs,cfg,base,doc))
        doc['receipts'].append(deepcopy(doc['receipts'][0]))
        self.retired(s,obs,cfg,base,doc,original)

    def test_nonfinite_visible_context_cannot_revive_old_draw(self):
        s,obs,cfg,base,alt,doc=self.begin()
        original=deepcopy((obs,cfg,base,doc))
        obs['farms'][0]['money']=float('nan')
        self.retired(s,obs,cfg,base,doc,original)

    def test_first_incomplete_input_can_later_complete(self):
        obs,cfg,base,alt,doc=fixture()
        s=actor(); incomplete=deepcopy(doc);incomplete['receipts'].pop()
        self.assertEqual(call(s,obs,cfg,base,incomplete),base)
        self.assertEqual((s.provider_calls,s.draws),(0,0))
        self.assertEqual(call(s,obs,cfg,base,doc),alt)
        self.assertEqual((s.provider_calls,s.draws),(1,1))

    def test_other_player_key_does_not_retire_current_actor(self):
        s,obs,cfg,base,alt,doc=self.begin()
        active=deepcopy(s.active)
        obs['player']=1
        self.assertEqual(call(s,obs,cfg,base,doc),base)
        self.assertEqual(s.active,active)
        self.assertEqual((s.provider_calls,s.draws),(1,1))

    def test_changed_parent_guard_still_preserves_current_fallback(self):
        s,obs,cfg,base,alt,doc=self.begin()
        base['farmer']=['DROP']
        for r in doc['receipts']:r['own_action']['farmer']=['DROP']
        self.retired(s,obs,cfg,base,doc)

    def test_unknown_current_feasibility_still_retires(self):
        s,obs,cfg,base,alt,doc=self.begin()
        self.assertEqual(call(s,obs,cfg,base,doc,feasible=lambda a:None),base)
        self.assertIsNone(s.active)
        self.assertEqual((s.provider_calls,s.draws),(1,1))

    def test_cancellation_is_not_swallowed(self):
        class Cancel(BaseException):pass
        s,obs,cfg,base,alt,doc=self.begin()
        def cancelled(action):raise Cancel()
        with self.assertRaises(Cancel):call(s,obs,cfg,base,doc,feasible=cancelled)
        self.assertEqual((s.provider_calls,s.draws),(1,1))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--consumers',type=Path,required=True)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    configure(args.runtime,args.consumers)
    result=unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(TerminalContextTests))
    report={'scope':'actual five-component terminal selector; constructed receipts, no engine/game calls',
            'runtime_sha256':hashlib.sha256(args.runtime.read_bytes()).hexdigest(),
            'test_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'dependencies':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                [args.consumers/x for x in ('solver.py','selector.py','terminal_utility.py',
                                          'full_support.py','weighted_selector.py')]},
            'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
            'successful':result.wasSuccessful(),'full_games':0,'game_seeds':0,
            'failing_cases':[{'test':t.id(),'traceback':s} for t,s in result.failures],
            'error_cases':[{'test':t.id(),'traceback':s} for t,s in result.errors]}
    if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n')
    return not result.wasSuccessful()

if __name__=='__main__':raise SystemExit(main())
