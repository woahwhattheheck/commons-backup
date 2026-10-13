# SPDX-License-Identifier: Apache-2.0
"""V5 contracts for final-action market-slot salvage."""
from __future__ import annotations

import unittest

from titan_runtime import Features, TitanAgent


class TerminalMarketPressureTests(unittest.TestCase):
    def setUp(self):
        self.market = {
            'inventory': {'MILK': 10000},
            'prices': {'MILK': 160},
        }
        self.cfg = {
            'maxMarketOrdersPerTurn': 3,
            'episodeSteps': 720,
        }
        self.sale = ['SELL', 'MILK', 1]

    def _run(self, step, market):
        agent = TitanAgent(Features(market_pressure=True))
        action = {'farmer': ['PASS'], 'hands': [], 'market': market}
        result = agent._market_pressure_selected(
            {'player': 0, 'step': step, 'market': self.market}, self.cfg, action)
        return action, result, agent

    def test_final_action_promotes_sale_only_suffix_into_dead_prefix_slots(self):
        action, result, agent = self._run(
            718, [[], list(self.sale), [], list(self.sale), list(self.sale)])
        self.assertEqual(
            result['market'],
            [list(self.sale), list(self.sale), list(self.sale), [], []],
        )
        self.assertEqual(action['market'][0], [])
        self.assertEqual(agent.diagnostics['market_pressure'],
                         {'enabled': True, 'changed': True})

    def test_same_queue_midgame_never_crosses_executable_boundary(self):
        _action, result, _agent = self._run(
            717, [[], list(self.sale), [], list(self.sale), list(self.sale)])
        self.assertEqual(
            result['market'],
            [list(self.sale), [], [], list(self.sale), list(self.sale)],
        )

    def test_terminal_promotion_stops_at_economic_barrier(self):
        _action, result, _agent = self._run(
            718, [[], list(self.sale), [], ['HIRE'], list(self.sale)])
        self.assertEqual(
            result['market'],
            [list(self.sale), [], [], ['HIRE'], list(self.sale)],
        )

    def test_terminal_promotion_declines_operating_input_prefix(self):
        market = [[], ['SELL', 'FERTILIZER', 0], [], list(self.sale)]
        _action, result, _agent = self._run(718, market)
        self.assertEqual(result['market'], market)

    def test_invalid_episode_boundary_declines_suffix_promotion(self):
        self.cfg['episodeSteps'] = True
        market = [[], list(self.sale), [], list(self.sale)]
        _action, result, _agent = self._run(718, market)
        self.assertEqual(result['market'], [list(self.sale), [], [], list(self.sale)])

    def test_disabled_feature_is_exact_identity(self):
        action = {
            'farmer': ['PASS'], 'hands': [],
            'market': [[], list(self.sale), [], list(self.sale)],
        }
        agent = TitanAgent(Features(market_pressure=False))
        out = agent._market_pressure_selected(
            {'player': 0, 'step': 718, 'market': self.market}, self.cfg, action)
        self.assertIs(out, action)


if __name__ == '__main__':
    unittest.main(verbosity=2)
