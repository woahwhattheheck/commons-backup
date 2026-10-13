# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import gzip
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from runtime import Portfolio, load
import continuation as c
from policy import EconomicPolicy


class ContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Portfolio({}).scheduler_module
        cls.kernel = c.market_kernel(cls.source.m)
        cls.obs = json.loads((HERE/'fixtures/development-step360.json').read_text())['observation']

    def test_complete_prefix_required(self):
        self.assertFalse(c.compatible({'a': [1, 2], 'b': [1]}, 'a', 'b', 2))
        self.assertFalse(c.compatible({'a': [1, 2], 'b': [1, 3]}, 'a', 'b', 2))
        self.assertTrue(c.compatible({'a': [1, 2], 'b': [1, 2, 3]}, 'a', 'b', 2))

    def test_evaluator_entries_accept_observation_and_configuration(self):
        import inspect
        entries = load(HERE/'controls.py', 't14_r2_test_entries')
        for name in ('sell','carrot_sell','economic','staged','lonespear','cok'):
            inspect.signature(getattr(entries, name)).bind({}, {})

    def test_relative_objective_rejects_larger_own_gross(self):
        plans = {'base': 0, 'own_greedy': 1, 'relative': 2}
        # Economic objective control, deliberately separate from engine fixtures.
        cash = [(0, 0), (100, 150), (80, 20)]
        def projection(obs, cfg, arm, scenario, *args, **kwargs):
            a, b = cash[arm]
            return {'relative_cash_change': a-b, 'own_cash_change': a, 'rival_cash_change': b,
                    'unfunded_orders': 0, 'cash_trough': 10}
        with patch.object(c, 'project', projection):
            result = c.evaluate_continuations({}, {}, plans, [{'id':'scenario'}], baseline='base', mechanics=None, kernel=None)
        self.assertEqual(result['selected'], 'relative')
        self.assertLess(result['scores']['own_greedy']['worst_relative_delta'], 0)

    def test_market_queue_matches_official_engine(self):
        ev = load(HERE.parent/'vendor/cloud-eval/evaluate.py', 't14_r2_test_engine')
        engine, _ = ev.get_engine(HERE.parent/'vendor/engine')
        def state():
            obs = deepcopy(self.obs)
            priv = [deepcopy(obs['private']), deepcopy(obs['private'])]
            priv[0]['shed']['MILK'] = 5
            priv[1]['shed']['MILK'] = 4
            actions = [{'market':[['SELL','MILK',5],['BUY_PRODUCT','WHEAT',3]]},
                       {'market':[['SELL','MILK',4],['BUY_PRODUCT','WHEAT',2]]}]
            return [SimpleNamespace(action=actions[i], observation=SimpleNamespace(
                farms=obs['farms'], market=obs['market'], private=priv[i])) for i in (0, 1)]
        actual, projected = state(), state()
        engine._process_market(actual, SimpleNamespace(configuration={}))
        self.kernel['_process_market'](projected, SimpleNamespace(configuration={}))
        for i in (0, 1):
            self.assertEqual(vars(actual[i].observation), vars(projected[i].observation))

    def test_selection_preserves_live_state_and_calls_no_parent(self):
        policy = EconomicPolicy(fixed='staged')
        policy.controller.cur = policy.parent.YARN
        scheduler, controller = policy.scheduler, policy.controller
        marker = object()
        scheduler.pending = {'MILK': marker}; scheduler.planned = {'MILK': [(362, 2)]}
        scheduler.previous = {'marker': marker}
        with patch.object(controller, 'act', side_effect=AssertionError('extra parent call')):
            policy.select(deepcopy(self.obs), {})
        self.assertIs(policy.scheduler, scheduler)
        self.assertIs(policy.controller, controller)
        self.assertIs(scheduler.pending['MILK'], marker)
        self.assertIs(scheduler.previous['marker'], marker)
        self.assertEqual(scheduler.planned, {'MILK': [(362, 2)]})
        self.assertEqual(controller.cur, policy.staged)

    def test_deadline_retains_baseline_without_mutating_observation(self):
        obs = deepcopy(self.obs); before = deepcopy(obs)
        route = self.source.parent.routes()[self.source.parent.YARN]
        result = c.evaluate_continuations(obs, {}, {'base': route},
            [{'id':'zero','day_orders':[[] for _ in range(24)]}], baseline='base',
            mechanics=self.source.m, kernel=self.kernel, budget_seconds=-1)
        self.assertEqual(result['reason'], 'deadline')
        self.assertEqual(result['selected'], 'base')
        self.assertEqual(obs, before)

    def test_history_excludes_unknowns_and_preserves_joint_days(self):
        from policy import flow
        history = flow.FlowHistory()
        products = ('MILK','WOOL')
        for t in range(336,360):
            for p in products:
                n = 5 if t == 350 else 0
                history.add(flow.FlowInterval(t,p,n,n,n,n,'identified'))
        cases = c.scenario_windows(history,360,718,products)
        self.assertEqual(cases[0]['training_end'],359)
        self.assertEqual(cases[0]['day_orders'][14],[['SELL','MILK',5],['SELL','WOOL',5]])
        history.records['MILK'][350] = flow.FlowInterval(350,'MILK',0,100,0,0,'floor_censored')
        self.assertEqual([s['id'] for s in c.scenario_windows(history,360,718,products)], ['unknown_zero_supply'])


if __name__ == '__main__':
    unittest.main()
