# SPDX-License-Identifier: Apache-2.0
"""Retry/reset contracts for TerminalHistoryJoin pending reconciliation."""
from types import SimpleNamespace
import unittest

from terminal_history_join import TerminalHistoryJoin


class _Bridge:
    def __init__(self):
        self.records=[]
        self.observations=[]
        self.ledger=SimpleNamespace(last_result={'status':'recorded'})

    def record(self, before, cfg, final, *, post_unit_shed, post_unit_inventories):
        self.records.append((before, cfg, final, post_unit_shed, post_unit_inventories))

    def observe(self, obs):
        self.observations.append(obs)
        return {'status':'observed','step':obs['step']}


def _join(step):
    join=object.__new__(TerminalHistoryJoin)
    join.bridge=_Bridge()
    join.pending=(
        {'step':step},
        {'episodeSteps':720},
        {'market':[['SELL','WHEAT',1]]},
        {'private':{'shed':{'WHEAT':1},'inventories':{'WHEAT':2}}},
    )
    join.diagnostics={'stale':True}
    join.fill_result={'stale':True}
    return join


class TerminalHistoryJoinBackstepTests(unittest.TestCase):
    def test_same_step_retry_keeps_pending_until_strictly_newer_observation(self):
        join=_join(100)
        pending=join.pending

        join.observe({'step':100})

        self.assertIs(join.pending,pending)
        self.assertEqual(join.bridge.records,[])
        self.assertEqual(join.bridge.observations,[])
        self.assertEqual(join.diagnostics,{})
        self.assertIsNone(join.fill_result)

        join.observe({'step':101})

        self.assertIsNone(join.pending)
        self.assertEqual(len(join.bridge.records),1)
        self.assertEqual(join.bridge.records[0][0]['step'],100)
        self.assertEqual(join.bridge.observations,[{'step':101}])
        self.assertEqual(join.diagnostics['observed_fills'],{'status':'observed','step':101})
        self.assertEqual(join.fill_result,{'status':'recorded'})
        self.assertIsNot(join.fill_result,join.bridge.ledger.last_result)

    def test_strict_backstep_discards_pending_and_cannot_cross_episode(self):
        join=_join(646)

        join.observe({'step':0})

        self.assertIsNone(join.pending)
        self.assertEqual(join.bridge.records,[])
        self.assertEqual(join.bridge.observations,[])
        self.assertEqual(join.diagnostics,{})
        self.assertIsNone(join.fill_result)

        # A later step in the new episode must not reconcile the stale step-646
        # action that was pending before the reset boundary.
        join.observe({'step':647})
        self.assertEqual(join.bridge.records,[])
        self.assertEqual(join.bridge.observations,[])


if __name__=='__main__':
    unittest.main(verbosity=2)
