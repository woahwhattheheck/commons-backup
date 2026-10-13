# SPDX-License-Identifier: Apache-2.0
"""Production guard for represented funding traces at the official EOD boundary."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
if ROOT.name == 'checks':
    ROOT = ROOT.parent


def load_entrypoint():
    name = '_titan_funding_eod_boundary_test'
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, ROOT/'main.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FundingEodBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.main = load_entrypoint()
        self.calls = []
        self.seller = ModuleType('_titan_funding_eod_boundary_seller')

        def original(obs, config, farm, private, route, now, end, current_market,
                     stress_units=0):
            self.calls.append((obs, config, farm, private, route, now, end,
                               current_market, stress_units))
            return {'cash': 17, 'acquisitions': [('same-day', 1)]}

        self.original = original
        self.seller._funding_trace = original

    def test_same_day_trace_delegates_exactly(self):
        guarded = self.main._install_funding_eod_boundary(self.seller)
        objects = [object() for _ in range(6)]
        result = guarded(objects[0], {'turnsPerDay': 24}, objects[1], objects[2],
                         objects[3], 120, 123, objects[4], stress_units=7)

        self.assertEqual(result, {'cash': 17, 'acquisitions': [('same-day', 1)]})
        self.assertEqual(len(self.calls), 1)
        self.assertIs(self.calls[0][0], objects[0])
        self.assertEqual(self.calls[0][1], {'turnsPerDay': 24})
        self.assertIs(self.calls[0][2], objects[1])
        self.assertIs(self.calls[0][3], objects[2])
        self.assertIs(self.calls[0][4], objects[3])
        self.assertEqual(self.calls[0][5:7], (120, 123))
        self.assertIs(self.calls[0][7], objects[4])
        self.assertEqual(self.calls[0][8], 7)

    def test_119_to_120_rejects_before_stale_hand_replay(self):
        guarded = self.main._install_funding_eod_boundary(self.seller)
        with self.assertRaisesRegex(ValueError, 'cannot cross end-of-day lifecycle'):
            guarded({}, {'turnsPerDay': 24}, {}, {}, [], 119, 120, [])
        self.assertEqual(self.calls, [])

    def test_non_plain_or_noncanonical_clock_rejects_before_replay(self):
        guarded = self.main._install_funding_eod_boundary(self.seller)
        for turns in (None, True, 24.0, '24', 23, 25):
            with self.subTest(turns=turns):
                with self.assertRaisesRegex(ValueError, 'plain-int turnsPerDay == 24'):
                    guarded({}, {'turnsPerDay': turns}, {}, {}, [], 120, 123, [])
        self.assertEqual(self.calls, [])

    def test_install_is_idempotent_and_retains_exact_preimage(self):
        first = self.main._install_funding_eod_boundary(self.seller)
        second = self.main._install_funding_eod_boundary(self.seller)
        self.assertIs(first, second)
        self.assertIs(self.seller._funding_trace, first)
        self.assertIs(first._titan_funding_eod_original, self.original)
        self.assertTrue(first._titan_funding_eod_boundary)

        with self.assertRaisesRegex(RuntimeError, 'no funding trace'):
            self.main._install_funding_eod_boundary(ModuleType('missing_trace'))

    def test_new_instance_installs_guard_on_exact_loaded_consumer_module(self):
        seller_name = '_titan_funding_eod_boundary_loaded_seller'
        seller = ModuleType(seller_name)
        seller._funding_trace = self.original

        class FakeConsumer:
            pass

        FakeConsumer.__module__ = seller_name

        class Features:
            def __init__(self, **kwargs):
                self.consumer = kwargs.get('consumer', 'frozen')
                self.terminal_route = kwargs.get('terminal_route', False)
                self.fourth_quadrant = kwargs.get('fourth_quadrant', False)
                self.budget_seconds = kwargs.get('budget_seconds', 1.0)
                self.reserve_seconds = kwargs.get('reserve_seconds', 0.01)

        class TitanAgent:
            def __init__(self, features, *, fourth_quadrant_admission=None):
                self.features = features
                self.spatial = None

            def _initialize(self):
                self.consumer = FakeConsumer()

        runtime = ModuleType('titan_runtime')
        runtime.TitanAgent = TitanAgent
        runtime.Features = Features
        runtime.load = lambda *args, **kwargs: None

        with patch.dict(sys.modules, {
            'titan_runtime': runtime,
            seller_name: seller,
        }):
            instance = self.main._new_instance(ROOT, {})
            instance._initialize()

        guarded = seller._funding_trace
        self.assertTrue(guarded._titan_funding_eod_boundary)
        self.assertIs(guarded._titan_funding_eod_original, self.original)
        with self.assertRaisesRegex(ValueError, 'cannot cross end-of-day lifecycle'):
            guarded({}, {'turnsPerDay': 24}, {}, {}, [], 119, 120, [])
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
