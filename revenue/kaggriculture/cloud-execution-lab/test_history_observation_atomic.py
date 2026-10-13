# SPDX-License-Identifier: Apache-2.0
"""Cancellation-safety contracts for selected-action history reconciliation."""
import copy
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from terminal_history_join import TerminalHistoryJoin
from test_ordered_selected_sell import OrderedSelectedSellTests,action

ROOT=Path(__file__).resolve().parent


class _InjectedCancellation(BaseException):
    pass


class HistoryObservationAtomicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OrderedSelectedSellTests.setUpClass()
        cls.harness=OrderedSelectedSellTests()

    @staticmethod
    def bind_clock(obs,step,cfg):
        period=cfg.get('turnsPerDay',24)
        obs['step']=step
        obs['day']=step//period
        obs['hour']=step%period
        return obs

    def transition(self,step=100):
        history=TerminalHistoryJoin(terminal_enabled=False)
        obs,cfg,state,env=self.harness.fixture(step,{'CARROT':3})
        before=copy.deepcopy(state[0].observation)
        final=action(hands=[['PASS']],market=[['SELL','CARROT',1]])
        history.remember(before,cfg,final,copy.deepcopy(before))
        self.harness.advance(state,env,final,step)
        after=self.bind_clock(copy.deepcopy(state[0].observation),step+1,cfg)
        return history,after,cfg

    def test_interrupted_reconciliation_publishes_no_partial_state(self):
        history,after,_=self.transition()
        original_bridge=history.bridge
        original_pending=copy.deepcopy(history.pending)
        original_last=history.bridge.last_consumed_step
        original_identified=history.bridge.history.identified
        original_result=copy.deepcopy(history.bridge.ledger.last_result)
        bridge_type=type(history.bridge)

        def interrupt(working,observation,*,fill_result=None):
            # Deliberately poison every mutable family on the private working
            # bridge before simulating a hard asynchronous deadline.
            working.last_consumed_step=777
            working.history.identified=999
            working.ledger.last_result={'status':'poisoned'}
            raise _InjectedCancellation()

        with patch.object(bridge_type,'observe',interrupt):
            with self.assertRaises(_InjectedCancellation):
                history.observe(after)

        self.assertIs(history.bridge,original_bridge)
        self.assertEqual(history.pending,original_pending)
        self.assertEqual(history.bridge.last_consumed_step,original_last)
        self.assertEqual(history.bridge.history.identified,original_identified)
        self.assertEqual(history.bridge.ledger.last_result,original_result)
        self.assertEqual(history.deferred_observation,after)
        self.assertIsNone(history._observation_commit)

        # A retry of the exact observation uses the retained adjacency witness
        # and consumes the original returned action exactly once.
        history.observe(after)
        self.assertIsNone(history.pending)
        self.assertIsNone(history.deferred_observation)
        self.assertIsNone(history._observation_commit)
        self.assertIsNot(history.bridge,original_bridge)
        self.assertEqual(history.bridge.last_consumed_step,100)
        self.assertEqual(history.diagnostics['observed_fills']['status'],'recorded')
        self.assertEqual(history.fill_result,history.bridge.ledger.last_result)

    def test_interrupted_publication_finishes_idempotently(self):
        history,after,_=self.transition(step=150)
        original_pending=copy.deepcopy(history.pending)
        real_publish=history._publish_observation_commit

        def interrupt_publish():
            commit=history._observation_commit
            if commit is None:
                return None
            # Emulate a signal after the first live pointer publication but
            # before the join pending/diagnostics/deferred fields are finalized.
            history.bridge=commit['bridge']
            raise _InjectedCancellation()

        with patch.object(history,'_publish_observation_commit',side_effect=interrupt_publish):
            with self.assertRaises(_InjectedCancellation):
                history.observe(after)

        self.assertIsNotNone(history._observation_commit)
        self.assertEqual(history.pending,original_pending)
        self.assertIsNotNone(history.deferred_observation)

        # Restoring the real publisher completes the exact prepared transition;
        # it does not record or infer the flow a second time.
        with patch.object(history,'_publish_observation_commit',side_effect=real_publish):
            history.observe(after)
        self.assertIsNone(history._observation_commit)
        self.assertIsNone(history.deferred_observation)
        self.assertIsNone(history.pending)
        self.assertEqual(history.bridge.last_consumed_step,150)
        self.assertEqual(history.diagnostics['observed_fills']['status'],'recorded')

    def test_inner_deadline_restores_and_replays_missed_adjacency(self):
        import main as entrypoint
        from titan_runtime import Features

        instance=entrypoint._new_instance(ROOT,{
            'budget_seconds':0.04,
            'reserve_seconds':0.01,
        })
        instance._initialize()
        # Keep the initialized runtime but use the short exact inner budget for
        # this fault-injection call.
        instance.features=Features(budget_seconds=0.04,reserve_seconds=0.01)
        history,after,cfg=self.transition(step=300)
        instance.history=history
        instance._history_checkpoint=history
        original_bridge=history.bridge
        original_pending=copy.deepcopy(history.pending)
        bridge_type=type(history.bridge)

        def stall(*args,**kwargs):
            while True:
                pass

        started=time.perf_counter()
        with patch.object(bridge_type,'observe',stall):
            instance.act(after,cfg)
        elapsed=time.perf_counter()-started

        self.assertLess(elapsed,1.0)
        self.assertFalse(instance.ready)
        self.assertIs(instance.history,history)
        self.assertIs(instance.history.bridge,original_bridge)
        self.assertEqual(instance.history.pending,original_pending)
        self.assertEqual(instance.history.deferred_observation,after)
        self.assertEqual(instance.diagnostics['fallback_stage'],'history_observation')
        self.assertEqual(instance.diagnostics['history_observation_recovery'],
                         'restored_retryable')

        # The environment is allowed to advance after the safe fallback. The
        # next guarded call must consume the retained step-301 witness first;
        # step 302 must not turn the old receipt into a nonadjacent unknown.
        next_observation=self.bind_clock(copy.deepcopy(after),302,cfg)
        instance.features=Features(budget_seconds=1.0,reserve_seconds=0.01)
        instance.act(next_observation,cfg)
        self.assertEqual(instance.history.bridge.last_consumed_step,300)
        self.assertIsNone(instance.history.deferred_observation)
        self.assertIsNone(instance.history._observation_commit)
        self.assertIsNone(instance.history.fill_result)

    def test_same_step_and_empty_observation_keep_existing_contract(self):
        history,after,cfg=self.transition(step=200)
        history.diagnostics={'stale':True}
        history.fill_result={'stale':True}
        same=self.bind_clock(copy.deepcopy(after),200,cfg)
        pending=copy.deepcopy(history.pending)
        history.observe(same)
        self.assertEqual(history.pending,pending)
        self.assertEqual(history.diagnostics,{})
        self.assertIsNone(history.fill_result)

        history.pending=None
        history.diagnostics={'stale':True}
        history.fill_result={'stale':True}
        history.observe(after)
        self.assertEqual(history.diagnostics,{})
        self.assertIsNone(history.fill_result)


if __name__=='__main__':
    unittest.main()
