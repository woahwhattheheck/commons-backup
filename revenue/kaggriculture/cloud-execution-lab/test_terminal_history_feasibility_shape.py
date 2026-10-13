# SPDX-License-Identifier: Apache-2.0
"""Shape-safety regressions for terminal-history final-action feasibility."""
from __future__ import annotations

from types import SimpleNamespace
import unittest

from terminal_history_join import TerminalHistoryJoin


class _Joint:
    @staticmethod
    def build_joint_terminal_scenarios(*args, **kwargs):
        return {"ready": True, "scenarios": ["s"]}


class _Inputs:
    def __init__(self, packet):
        self.packet = packet

    def build_terminal_inputs(self, *args, **kwargs):
        return self.packet


class _Selector:
    def __init__(self, candidate):
        self.candidate = candidate
        self.last_objective = {"test": "feasibility-shape"}

    def transform_terminal(self, obs, cfg, selected, *, document, feasible):
        return self.candidate if feasible(self.candidate) else selected


class TerminalHistoryFeasibilityShapeTests(unittest.TestCase):
    @staticmethod
    def _join(selected, candidate):
        baseline_receipt = {
            "plan": "baseline",
            "scenario": "s",
            "done": True,
            "own_seeds_after": {"WHEAT": 1},
            "own_hands_after": 2,
        }
        candidate_receipt = dict(baseline_receipt, plan="candidate")
        packet = {
            "complete": True,
            "plans": [
                {"id": "baseline", "action": selected},
                {"id": "candidate", "action": candidate},
            ],
            "document": {"receipts": [baseline_receipt, candidate_receipt]},
        }
        join = TerminalHistoryJoin.__new__(TerminalHistoryJoin)
        join.terminal_enabled = True
        join.selector = _Selector(candidate)
        join.joint = _Joint()
        join.inputs = _Inputs(packet)
        join.bridge = SimpleNamespace(history=object())
        join.m = SimpleNamespace(PRODUCTS=())
        join.hypotheses = {}
        join.diagnostics = {}
        return join

    @staticmethod
    def _transform(join, selected):
        return join.transform(
            {"step": 718},
            {
                "episodeSteps": 720,
                "shedCapacity": 100,
                "maxMarketOrdersPerTurn": 10,
            },
            selected,
            {},
            deadline=lambda: None,
        )

    def test_truthy_non_list_rows_are_inert_for_acquisition_guard(self):
        selected = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [7, {"malformed": True}, ["SELL", "WHEAT", 1]],
        }
        candidate = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [["SELL", "WHEAT", 1]],
        }
        join = self._join(selected, candidate)
        self.assertEqual(self._transform(join, selected), candidate)
        self.assertTrue(join.diagnostics["changed"])

    def test_valid_acquisition_rows_still_block_changed_plan(self):
        for operation in ("BUY_PRODUCT", "BUY_ANIMAL", "BUY_LAND"):
            with self.subTest(operation=operation):
                selected = {
                    "farmer": ["PASS"],
                    "hands": [],
                    "market": [[operation, "WHEAT", 1]],
                }
                candidate = {
                    "farmer": ["PASS"],
                    "hands": [],
                    "market": [],
                }
                join = self._join(selected, candidate)
                output = self._transform(join, selected)
                self.assertIs(output, selected)
                self.assertFalse(join.diagnostics["changed"])

    def test_malformed_market_container_fails_closed_to_selected(self):
        selected = {
            "farmer": ["PASS"],
            "hands": [],
            "market": "malformed-market-container",
        }
        candidate = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [],
        }
        join = self._join(selected, candidate)
        output = self._transform(join, selected)
        self.assertIs(output, selected)
        self.assertFalse(join.diagnostics["changed"])


if __name__ == "__main__":
    unittest.main()
