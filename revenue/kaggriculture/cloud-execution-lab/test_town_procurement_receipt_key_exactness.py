# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import unittest

LAB = Path(__file__).resolve().parent
SOURCE = LAB / "town_procurement.py"
SPEC = importlib.util.spec_from_file_location("town_procurement_receipt_key_test", SOURCE)
town = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = town
SPEC.loader.exec_module(town)


def _observation(*, player=1, step=200, wheat=0):
    return {
        "player": player,
        "step": step,
        "private": {"shed": {"WHEAT": wheat}},
    }


def _wheat_action(quantity=3):
    return {
        "farmer": ["PASS"],
        "hands": [],
        "market": [["BUY_PRODUCT", "WHEAT", quantity]],
    }


class TownReceiptKeyExactnessTests(unittest.TestCase):
    def setUp(self):
        town.reset()

    def _seed_pending_receipt(self):
        out, report = town.apply(
            _observation(player=1, step=200, wheat=0),
            _wheat_action(3),
            {"maxMarketOrdersPerTurn": 10},
            completed=True,
        )
        self.assertEqual(report["status"], "target_advanced")
        self.assertEqual(out["market"], [["BUY_PRODUCT", "WHEAT", 6]])
        self.assertIn(1, town._STATE)
        self.assertIsNotNone(town._STATE[1]["pending"])

    def test_malformed_player_aliases_cannot_touch_existing_receipt_state(self):
        self._seed_pending_receipt()
        before = copy.deepcopy(town._STATE)
        for player in (True, "1", 1.0, -1, 2, None):
            with self.subTest(player=player):
                with self.assertRaises(ValueError):
                    town.observe(_observation(player=player, step=201, wheat=6))
                self.assertEqual(town._STATE, before)

    def test_malformed_step_aliases_cannot_reconcile_or_reset_receipt_state(self):
        self._seed_pending_receipt()
        before = copy.deepcopy(town._STATE)
        for step in (True, "201", 201.0, -1, None):
            with self.subTest(step=step):
                with self.assertRaises(ValueError):
                    town.observe(_observation(player=1, step=step, wheat=6))
                self.assertEqual(town._STATE, before)

    def test_canonical_receipt_reconcile_and_source_suppression_are_unchanged(self):
        self._seed_pending_receipt()
        observed = town.observe(_observation(player=1, step=201, wheat=6))
        self.assertEqual(observed["status"], "receipt_reconciled")
        self.assertEqual(observed["confirmed_source"], 202)
        self.assertEqual(observed["confirmed_qty"], 3)

        out, report = town.apply(
            _observation(player=1, step=202, wheat=6),
            _wheat_action(3),
            {"maxMarketOrdersPerTurn": 10},
            completed=True,
        )
        self.assertEqual(report["status"], "source_suppressed")
        self.assertEqual(report["suppressed_qty"], 3)
        self.assertEqual(out["market"], [["BUY_PRODUCT", "WHEAT", 0]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
