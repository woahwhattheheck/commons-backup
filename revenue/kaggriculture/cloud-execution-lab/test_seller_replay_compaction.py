# SPDX-License-Identifier: Apache-2.0
"""Recovery regressions for bounded FrozenSelected fallback replay."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
if ROOT.name == 'checks':
    ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import titan_runtime


def observation(step, marker):
    return {
        'step': step,
        'player': 0,
        'farms': [
            {'tiles': []},
            {'tiles': [{'marker': marker}]},
        ],
    }


class FakeFrozen:
    """Small observer with the mutable fields retained by TitanAgent."""

    def __init__(self):
        self.planned = {}
        self.pending = {}
        self.previous = None
        self.observed_harvests = {'CROP': []}
        self.observe_calls = 0

    def observe(self, obs):
        self.observe_calls += 1
        marker = obs['farms'][1]['tiles'][0]['marker']
        row = (int(obs['step']), marker)
        self.observed_harvests.setdefault('CROP', []).append(row)
        self.pending['last'] = row


class SellerReplayCompactionTests(unittest.TestCase):
    def make_agent(self):
        agent = titan_runtime.TitanAgent()
        agent.consumer = FakeFrozen()
        return agent

    @staticmethod
    def queue(agent, *rows):
        for step, marker in rows:
            agent._remember_seller_fallback(observation(step, marker))

    def test_replayed_prefix_is_checkpointed_and_tail_stays_replaceable(self):
        agent = self.make_agent()
        self.queue(agent, (1, 'a'), (2, 'b'), (3, 'c'))

        agent._restore_seller_state()

        self.assertEqual(
            agent.consumer.observed_harvests['CROP'],
            [(1, 'a'), (2, 'b'), (3, 'c')],
        )
        self.assertEqual(agent.consumer.observe_calls, 3)
        self.assertTrue(agent._completed_seller_state['_fallback_prefix_checkpoint'])
        self.assertEqual(agent._completed_seller_state['previous']['step'], 2)
        self.assertEqual(
            agent._completed_seller_state['observed_harvests']['CROP'],
            [(1, 'a'), (2, 'b')],
        )
        self.assertEqual(
            [(row['step'], row['farms'][1]['tiles'][0]['marker'])
             for row in agent._seller_fallback_observations],
            [(3, 'c')],
        )

        # A retry of the same public step replaces the pending tail. Restoring
        # begins from the prefix checkpoint, so the old step-3 observation does
        # not survive in observer state.
        self.queue(agent, (3, 'c2'))
        before = agent.consumer.observe_calls
        agent._restore_seller_state()
        self.assertEqual(agent.consumer.observe_calls - before, 1)
        self.assertEqual(
            agent.consumer.observed_harvests['CROP'],
            [(1, 'a'), (2, 'b'), (3, 'c2')],
        )

    def test_repeated_recovery_keeps_backlog_and_work_bounded(self):
        agent = self.make_agent()
        self.queue(agent, (1, 'a'), (2, 'b'), (3, 'c'))
        agent._restore_seller_state()

        self.queue(agent, (4, 'd'))
        self.assertEqual(len(agent._seller_fallback_observations), 2)
        before = agent.consumer.observe_calls
        agent._restore_seller_state()
        self.assertEqual(agent.consumer.observe_calls - before, 2)
        self.assertTrue(agent._completed_seller_state['_fallback_prefix_checkpoint'])
        self.assertEqual(agent._completed_seller_state['previous']['step'], 3)
        self.assertEqual(len(agent._seller_fallback_observations), 1)
        self.assertEqual(
            agent.consumer.observed_harvests['CROP'],
            [(1, 'a'), (2, 'b'), (3, 'c'), (4, 'd')],
        )

        self.queue(agent, (4, 'd2'))
        before = agent.consumer.observe_calls
        agent._restore_seller_state()
        self.assertEqual(agent.consumer.observe_calls - before, 1)
        self.assertEqual(len(agent._seller_fallback_observations), 1)
        self.assertEqual(
            agent.consumer.observed_harvests['CROP'],
            [(1, 'a'), (2, 'b'), (3, 'c'), (4, 'd2')],
        )
        # Three initial observations, two for the next new step, and one for
        # its same-step retry: recovery cost grows with new observations rather
        # than replaying the complete historical prefix each time.
        self.assertEqual(agent.consumer.observe_calls, 6)

    def test_checkpoint_first_interruption_cannot_double_replay_prefix(self):
        agent = self.make_agent()
        rows = [(1, 'a'), (2, 'b'), (3, 'c')]
        self.queue(agent, *rows)
        agent._restore_seller_state()

        # Model interruption after publishing the compacted checkpoint but
        # before shrinking the old pending list. The checkpoint's exact prior
        # observation must discard the stale prefix on reconstruction.
        agent._seller_fallback_observations = [
            agent._seller_public_observation(observation(step, marker))
            for step, marker in rows
        ]
        agent.consumer = FakeFrozen()
        agent._restore_seller_state()

        self.assertEqual(agent.consumer.observe_calls, 1)
        self.assertEqual(
            agent.consumer.observed_harvests['CROP'],
            [(1, 'a'), (2, 'b'), (3, 'c')],
        )
        self.assertEqual(len(agent._seller_fallback_observations), 1)
        self.assertEqual(agent._seller_fallback_observations[0]['step'], 3)


if __name__ == '__main__':
    unittest.main()
