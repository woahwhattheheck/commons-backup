# SPDX-License-Identifier: Apache-2.0
"""Predecessor killers for raw-market suffix influence in TitanAgent finalizers."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

_LAB = Path(__file__).resolve().parent
for _extra in (_LAB.parent / 'cloud-runtime-pulse', _LAB.parent / 'cloud-quickstep'):
    _path = str(_extra)
    if _path not in sys.path:
        sys.path.append(_path)

import operating_stock as operating_stock_module
import titan_runtime as tr


class RuntimeFinalizerPrefixTests(unittest.TestCase):
    @staticmethod
    def _operating_agent():
        agent = object.__new__(tr.TitanAgent)
        agent.features = tr.Features(operating_stock=True)
        agent.consumer = SimpleNamespace(selected_post_units=(
            {'money': 100, 'tiles': [], 'farmer': [0, 0], 'hands': []},
            {'shed': {'FERTILIZER': 1}, 'inventories': []},
        ))
        agent.selected = {'farmer': ['PASS'], 'hands': []}
        agent.controller = SimpleNamespace(cur='route', R={'route': []})
        agent.diagnostics = {}
        agent.spatial = None
        return agent

    def test_operating_stock_tail_only_sale_never_invokes_helper(self):
        cfg = {'maxMarketOrdersPerTurn': 1}
        selected = {
            'farmer': ['PASS'], 'hands': [],
            'market': [['SELL', 'MILK', 1], ['SELL', 'FERTILIZER', 1]],
        }
        agent = self._operating_agent()
        calls = []
        original = operating_stock_module.protect_operating_stock

        def trap(*args, **kwargs):
            calls.append(copy.deepcopy(args[3]))
            return args[3], {'changed': False, 'reason': 'trap'}

        operating_stock_module.protect_operating_stock = trap
        try:
            result = agent._operating_stock_selected({}, cfg, copy.deepcopy(selected))
        finally:
            operating_stock_module.protect_operating_stock = original
        self.assertEqual(result, selected)
        self.assertEqual(calls, [])

    def test_operating_stock_suffix_cannot_flip_executable_prefix(self):
        cfg = {'maxMarketOrdersPerTurn': 1}
        head = {
            'farmer': ['PASS'], 'hands': [],
            'market': [['SELL', 'FERTILIZER', 1]],
        }
        tailed = copy.deepcopy(head)
        tailed['market'].append(['SELL', 'FERTILIZER', 100])
        original = operating_stock_module.protect_operating_stock

        def adversarial(_m, _obs, _cfg, selected, *_args, **_kwargs):
            result = copy.deepcopy(selected)
            offered = sum(
                int(order[2]) for order in selected.get('market', [])
                if order and len(order) > 2 and order[:2] == ['SELL', 'FERTILIZER'])
            if offered > 1:
                result['market'][0] = []
            return result, {'changed': offered > 1, 'offered': offered}

        operating_stock_module.protect_operating_stock = adversarial
        try:
            plain = self._operating_agent()._operating_stock_selected(
                {}, cfg, copy.deepcopy(head))
            with_tail = self._operating_agent()._operating_stock_selected(
                {}, cfg, copy.deepcopy(tailed))
        finally:
            operating_stock_module.protect_operating_stock = original
        self.assertEqual(with_tail['market'][:1], plain['market'][:1])
        self.assertEqual(with_tail['market'][1:], tailed['market'][1:])

    def test_redundant_hire_tail_only_order_never_invokes_helper(self):
        cfg = {'maxMarketOrdersPerTurn': 1}
        selected = {'market': [['SELL', 'MILK', 1], ['HIRE']]}
        agent = object.__new__(tr.TitanAgent)
        agent.features = tr.Features(redundant_hire=True)
        agent.controller = SimpleNamespace(cur='route', R={'route': []})
        agent.diagnostics = {}
        calls = []

        def trap(*args, **kwargs):
            calls.append(copy.deepcopy(args[3]))
            return args[3], {'changed': False, 'reason': 'trap'}

        agent.redundant_hire_module = SimpleNamespace(propose_redundant_hires=trap)
        result = agent._redundant_hire_selected({}, cfg, copy.deepcopy(selected))
        self.assertEqual(result, selected)
        self.assertEqual(calls, [])

    def test_feed_stock_uses_configured_cap_not_literal_ten(self):
        cfg = {'maxMarketOrdersPerTurn': 1}
        selected = {
            'farmer': ['PASS'], 'hands': [],
            'market': [['SELL', 'MILK', 1], ['SELL', 'WHEAT', 1]],
        }
        agent = self._operating_agent()
        snapshots = []

        def snapshot(*args, **kwargs):
            snapshots.append(True)
            return None

        agent._selected_snapshot = snapshot
        result = agent._feed_stock_selected({}, cfg, copy.deepcopy(selected))
        self.assertEqual(result, selected)
        self.assertEqual(snapshots, [])


if __name__ == '__main__':
    unittest.main()
