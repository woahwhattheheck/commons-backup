from __future__ import annotations

from copy import deepcopy
import unittest

import outer_wrappers_current as current
import staged_runtime as staged


class StagedRuntimeTests(unittest.TestCase):
    def config(self):
        return {
            "episodeSteps": 720,
            "turnsPerDay": 24,
            "boardSize": 10,
            "shedCapacity": 100,
            "maxMarketOrdersPerTurn": 3,
        }

    def board(self):
        return [[{} for _ in range(10)] for _ in range(10)]

    def b9_observation(self, step):
        tiles = self.board()
        tiles[4][4] = {
            "kind": "COOP",
            "animal": "GOOSE",
            "fertilizer_available": True,
        }
        return {
            "step": step,
            "player": 0,
            "farms": [
                {"farmer": [4, 4], "hands": [], "tiles": tiles},
                {"farmer": [0, 0], "hands": [], "tiles": self.board()},
            ],
            "private": {"inventories": [{}], "shed": {}},
        }

    def h3c_observation(self, step=119):
        tiles = self.board()
        tiles[2][2] = {
            "kind": "COOP",
            "animal": "GOOSE",
            "placed_day": 0,
            "yield_units": 4,
            "consecutive_unfed": 0,
            "fed_today": True,
            "cared_today": True,
            "fertilizer_available": True,
            "pending_care_bonus": 0,
        }
        return {
            "step": step,
            "player": 0,
            "farms": [
                {"farmer": [2, 2], "hands": [], "tiles": tiles},
                {"farmer": [0, 0], "hands": [], "tiles": self.board()},
            ],
            "private": {"inventories": [{}], "shed": {}},
        }

    def test_submitted_activation_domains_are_exactly_disjoint(self):
        self.assertEqual(staged.B9_ACTIVE_STEPS, frozenset((716, 717, 718)))
        self.assertEqual(staged.H3C_TURNS_PER_DAY, 24)
        self.assertEqual(staged.H3C_HOUR, 23)
        self.assertTrue(staged.submitted_activation_domains_disjoint())
        for step in staged.B9_ACTIVE_STEPS:
            self.assertNotEqual(step % staged.H3C_TURNS_PER_DAY, staged.H3C_HOUR)

    def test_h3c_pre_capacity_does_not_advance_b9_state(self):
        adapter = staged.B9H3CStagedRuntime(
            terminal_fertilizer=True, goose_rescue=True
        )
        cfg = self.config()
        cfg["maxMarketOrdersPerTurn"] = 10
        selected = {"farmer": ["COLLECT_FERTILIZER"], "hands": [], "market": []}
        result, report = adapter.pre_capacity(self.h3c_observation(), cfg, selected)
        self.assertEqual(result["farmer"], ["HARVEST"])
        self.assertTrue(report["changed"])
        self.assertEqual(adapter._b9_state, {})
        result, report = adapter.post_market(self.h3c_observation(), cfg, result)
        self.assertEqual(result["farmer"], ["HARVEST"])
        self.assertEqual(report["reason"], "outside_terminal_transform")
        self.assertEqual(adapter._b9_state[0]["last_step"], 119)

    def test_staged_matches_combined_on_h3c_witness(self):
        cfg = self.config()
        cfg["maxMarketOrdersPerTurn"] = 10
        selected = {"farmer": ["COLLECT_FERTILIZER"], "hands": [], "market": []}
        combined = current.B9H3CCurrentABI(
            terminal_fertilizer=True, goose_rescue=True
        )
        split = staged.B9H3CStagedRuntime(
            terminal_fertilizer=True, goose_rescue=True
        )
        expected, _ = combined.transform(self.h3c_observation(), cfg, deepcopy(selected))
        actual, report = split.transform_staged(
            self.h3c_observation(), cfg, deepcopy(selected)
        )
        self.assertEqual(actual, expected)
        self.assertEqual(actual["farmer"], ["HARVEST"])
        self.assertTrue(report["submitted_domains_disjoint"])
        self.assertEqual(
            report["order"],
            ("goose_rescue_pre_capacity", "terminal_fertilizer_post_market"),
        )

    def test_staged_matches_combined_across_b9_collect_and_terminal_partition(self):
        cfg = self.config()
        combined = current.B9H3CCurrentABI(
            terminal_fertilizer=True, goose_rescue=True
        )
        split = staged.B9H3CStagedRuntime(
            terminal_fertilizer=True, goose_rescue=True
        )
        collect = {"farmer": ["PASS"], "hands": [], "market": []}
        expected_collect, _ = combined.transform(
            self.b9_observation(716), cfg, deepcopy(collect)
        )
        actual_collect, staged_collect = split.transform_staged(
            self.b9_observation(716), cfg, deepcopy(collect)
        )
        self.assertEqual(actual_collect, expected_collect)
        self.assertEqual(actual_collect["farmer"], ["COLLECT_FERTILIZER"])
        self.assertFalse(staged_collect["h3c"]["changed"])
        self.assertTrue(staged_collect["b9"]["changed"])

        terminal = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [
                ["SELL", "FERTILIZER", 1],
                ["SELL", "MILK", 2],
                ["SELL", "FERTILIZER", 3],
                ["SELL", "WOOL", 9],
            ],
        }
        expected_terminal, _ = combined.transform(
            self.b9_observation(718), cfg, deepcopy(terminal)
        )
        actual_terminal, staged_terminal = split.transform_staged(
            self.b9_observation(718), cfg, deepcopy(terminal)
        )
        self.assertEqual(actual_terminal, expected_terminal)
        self.assertEqual(
            actual_terminal["market"],
            [
                ["SELL", "MILK", 2],
                ["SELL", "FERTILIZER", 1],
                ["SELL", "FERTILIZER", 3],
                ["SELL", "WOOL", 9],
            ],
        )
        self.assertFalse(staged_terminal["h3c"]["changed"])
        self.assertTrue(staged_terminal["b9"]["changed"])

    def test_unrelated_step_is_identity_and_staged_equals_combined(self):
        cfg = self.config()
        selected = {"farmer": ["PASS"], "hands": [], "market": []}
        observation = self.b9_observation(120)
        combined = current.B9H3CCurrentABI(
            terminal_fertilizer=True, goose_rescue=True
        )
        split = staged.B9H3CStagedRuntime(
            terminal_fertilizer=True, goose_rescue=True
        )
        expected, _ = combined.transform(observation, cfg, selected)
        actual, report = split.transform_staged(observation, cfg, selected)
        self.assertIs(expected, selected)
        self.assertIs(actual, selected)
        self.assertFalse(report["changed"])

    def test_flags_keep_exact_bool_contract(self):
        staged.B9H3CStagedRuntime()
        for bad in (0, 1, None, "true"):
            with self.assertRaises(TypeError):
                staged.B9H3CStagedRuntime(terminal_fertilizer=bad)
            with self.assertRaises(TypeError):
                staged.B9H3CStagedRuntime(goose_rescue=bad)


if __name__ == "__main__":
    unittest.main()
