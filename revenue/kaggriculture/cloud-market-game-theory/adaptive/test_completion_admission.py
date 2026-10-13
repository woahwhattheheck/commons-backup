# SPDX-License-Identifier: Apache-2.0
"""Completion timing through the full runtime and real plan/ledger components.

Only the producer is a supplied-action fixture. No engine, games or seeds are
initialized. The compiler, context, flow, continuation and sale ledger are real.
"""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('renew_completion_runtime', HERE/'runtime.py')
runtime = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runtime
spec.loader.exec_module(runtime)
from test_lazy_offers import SuppliedParent, record, scenario


def advance(agent, obs, now, *, records=None, end=None):
    obs['step'] = now
    end = end if end is not None else max(now, 48)
    agent.parent.records = deepcopy(records or [])
    agent.parent.last_packet = {
        'projection': {'observed_step': now, 'end_step': end, 'stock_events': [],
                       'future_market': {t: [] for t in range(now+1, end+1)}},
        'post_unit_observation': deepcopy(obs), 'arrival_contract': None}


class CompletionAdmissionTests(unittest.TestCase):
    def actor(self, mode='adaptive', seat=0):
        with patch.object(runtime.integrated, 'IntegratedSelectedAgent', SuppliedParent):
            return scenario(module=runtime, mode=mode, seat=seat)

    def finish(self, mode='adaptive', seat=0):
        agent, obs, cfg = self.actor(mode, seat)
        agent.act(obs, cfg)
        old = agent.transformer.selector.active['key']
        obs['market']['inventory']['EGG'] = int(next(iter(agent.transformer.tree['groups'])))
        advance(agent, obs, 41)
        agent.act(obs, cfg)
        completion = agent.transformer.selector.active['completion_step']
        if completion > obs['step']:
            advance(agent, obs, completion)
            agent.act(obs, cfg)
        self.assertEqual(agent.transformer.selector.active['key'], old)
        return agent, obs, cfg, old

    def test_first_post_completion_call_admits_real_fresh_offer(self):
        for mode in ('adaptive', 'fixed', 'static'):
            for seat in (0, 1):
                with self.subTest(mode=mode, seat=seat):
                    agent, obs, cfg, old = self.finish(mode, seat)
                    now = obs['step'] + 1
                    obs['market']['inventory']['EGG'] = 40
                    advance(agent, obs, now, records=[record(now=now, end=now+8)], end=now+8)
                    calls = agent.parent.calls
                    agent.act(obs, cfg)
                    self.assertEqual(agent.parent.calls, calls+1)
                    self.assertIn(old, agent.transformer.selector.completed)
                    self.assertEqual(agent.transformer.counts['aborts'], 0)
                    self.assertEqual(agent.last.get('reason'), 'admitted')
                    self.assertEqual(agent.transformer.selector.active['now'], now)
                    self.assertFalse(agent.transformer.branch_done)
                    self.assertEqual(agent.offer_work, {'captured_windows': 1,
                        'inspected_windows': 1, 'compiled_windows': 1, 'admitted_index': 0})
                    self.assertEqual(agent.previous_action, agent.parent.action)

    def test_completion_date_preserves_due_sale_and_suppresses_capture(self):
        agent, obs, cfg = self.actor('fixed')
        agent.act(obs, cfg)
        old = deepcopy(agent.transformer.selector.active)
        now = old['completion_step']
        self.assertEqual(now, 41)
        obs['market']['inventory']['EGG'] = int(next(iter(agent.transformer.tree['groups'])))
        advance(agent, obs, now, records=[record('MILK', now=now, end=now+8)], end=now+8)
        action = agent.act(obs, cfg)
        self.assertEqual(action['market'], [['SELL', 'EGG', 6]])
        self.assertEqual(agent.transformer.selector.active['key'], old['key'])
        self.assertNotIn(old['key'], agent.transformer.selector.completed)
        self.assertEqual(agent.offer_work['captured_windows'], 0)
        self.assertEqual(agent.offer_work['compiled_windows'], 0)

    def test_stale_offer_context_is_rejected_after_expiry(self):
        agent, obs, cfg, old = self.finish()
        now = obs['step']+1
        advance(agent, obs, now, records=[record()], end=now+8)
        self.assertEqual(agent.act(obs, cfg), agent.parent.action)
        self.assertEqual(agent.offer_work['captured_windows'], 1)
        self.assertEqual(agent.last['reason'], 'market_context_unknown')
        self.assertIsNone(agent.transformer.selector.active)
        self.assertIn(old, agent.transformer.selector.completed)

    def test_missing_and_stale_projection_do_not_create_admission_or_abort(self):
        for stale in (False, True):
            with self.subTest(stale=stale):
                agent, obs, cfg, old = self.finish()
                now = obs['step']+1
                advance(agent, obs, now, records=[record(now=now, end=now+8)], end=now+8)
                if stale:
                    agent.parent.last_packet['projection']['observed_step'] = now-1
                else:
                    agent.parent.last_packet = None
                self.assertEqual(agent.act(obs, cfg), agent.parent.action)
                self.assertIn(old, agent.transformer.selector.completed)
                self.assertIsNone(agent.transformer.selector.active)
                self.assertEqual(agent.transformer.counts['aborts'], 0)
                self.assertEqual(agent.offer_work['compiled_windows'], 0)

    def test_parent_error_retires_expired_plan_and_retry_can_admit(self):
        agent, obs, cfg, old = self.finish()
        now = obs['step']+1
        obs['market']['inventory']['EGG'] = 40
        advance(agent, obs, now, records=[record(now=now, end=now+8)], end=now+8)
        error = TypeError('supplied producer failure')
        agent.parent.error = error
        original, calls = runtime.sale.optimize_lot, agent.parent.calls
        with self.assertRaises(TypeError) as caught:
            agent.act(obs, cfg)
        self.assertIs(caught.exception, error)
        self.assertEqual(agent.parent.calls, calls+1)
        self.assertIs(runtime.sale.optimize_lot, original)
        self.assertIn(old, agent.transformer.selector.completed)
        self.assertIsNone(agent.transformer.selector.active)
        agent.parent.error = None
        agent.act(obs, cfg)
        self.assertEqual(agent.last['reason'], 'admitted')

    def test_direct_transform_expiry_remains_idempotent(self):
        agent, obs, cfg, old = self.finish()
        advance(agent, obs, obs['step']+1)
        counts = deepcopy(agent.transformer.counts)
        base = agent.parent.action
        # An expired direct call with no offers needs no projection lookup.
        for _ in range(2):
            self.assertEqual(agent.transformer.transform(obs, cfg, base, ledger=None), base)
        self.assertEqual(agent.transformer.counts, counts)
        self.assertEqual(agent.transformer.selector.completed, {old})
        self.assertIsNone(agent.transformer.tree)

    def test_baseline_still_calls_parent_once_without_offer_work(self):
        agent, obs, cfg = self.actor('baseline')
        self.assertEqual(agent.act(obs, cfg), agent.parent.action)
        self.assertEqual(agent.parent.calls, 1)
        self.assertEqual(agent.offer_work['captured_windows'], 0)
        self.assertEqual(agent.offer_work['compiled_windows'], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
