from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import outer_wrappers_current as current


class B9H3CCurrentABITests(unittest.TestCase):
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

    def h3c_observation(self, *, step=119, shed=None, inventory=None):
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
            "private": {
                "inventories": [inventory or {}],
                "shed": shed or {},
            },
        }

    def test_exact_submitted_donor_blobs_are_authenticated(self):
        self.assertEqual(current.DONOR_COMMIT, "a90d888f03987ef0b35cfd20ec3519c6144db08a")
        self.assertEqual(current.git_blob_id(current.B9_PATH), current.B9_GIT_BLOB)
        self.assertEqual(current.git_blob_id(current.H3C_PATH), current.H3C_GIT_BLOB)
        self.assertEqual(current.B9_GIT_BLOB, "ed8d6923541e700c3a0ae4b93695bbd56455a3b6")
        self.assertEqual(current.H3C_GIT_BLOB, "2044d6cf1e0c51f95027229863f910aa43ac7008")
        self.assertTrue(current.B9_PATH.is_file())
        self.assertTrue(current.H3C_PATH.is_file())

    def test_authenticated_bytes_execute_even_if_path_disappears_after_read(self):
        module_name = "_titan_v5_self_deleting_donor_test"
        raw = b"VALUE = 73\n"
        expected = current._git_blob_id_bytes(raw)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "donor.py"
            path.write_bytes(raw)
            real_read_bytes = Path.read_bytes
            reads = []

            def read_then_delete(candidate):
                data = real_read_bytes(candidate)
                reads.append(Path(candidate))
                Path(candidate).unlink()
                return data

            try:
                with mock.patch.object(Path, "read_bytes", read_then_delete):
                    module = current._load_pinned(module_name, path, expected)
                self.assertEqual(module.VALUE, 73)
                self.assertEqual(reads, [path])
                self.assertFalse(path.exists())
            finally:
                sys.modules.pop(module_name, None)

    def test_drifted_donor_bytes_fail_before_execution(self):
        module_name = "_titan_v5_drifted_donor_test"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "donor.py"
            path.write_text("raise AssertionError('must not execute')\n")
            try:
                with self.assertRaisesRegex(RuntimeError, "submitted donor drift"):
                    current._load_pinned(module_name, path, "0" * 40)
                self.assertNotIn(module_name, sys.modules)
            finally:
                sys.modules.pop(module_name, None)

    def test_flags_are_exact_bool_and_default_off_identity(self):
        adapter = current.B9H3CCurrentABI()
        selected = {"farmer": ["PASS"], "hands": [], "market": []}
        result, report = adapter.transform(self.b9_observation(716), self.config(), selected)
        self.assertIs(result, selected)
        self.assertFalse(report["changed"])
        self.assertEqual(report["order"], ("terminal_fertilizer", "goose_rescue"))
        for value in (0, 1, None, "true"):
            with self.assertRaises(TypeError):
                current.B9H3CCurrentABI(terminal_fertilizer=value)
            with self.assertRaises(TypeError):
                current.B9H3CCurrentABI(goose_rescue=value)

    def test_b9_collect_then_terminal_partition_preserves_tail_indexes(self):
        adapter = current.B9H3CCurrentABI(terminal_fertilizer=True)
        collect = {"farmer": ["PASS"], "hands": [], "market": []}
        collect_result, collect_report = adapter.transform(
            self.b9_observation(716), self.config(), collect
        )
        self.assertEqual(collect_result["farmer"], ["COLLECT_FERTILIZER"])
        self.assertTrue(collect_report["b9"]["collected_episode"])

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
        terminal_before = deepcopy(terminal)
        result, report = adapter.transform(
            self.b9_observation(718), self.config(), terminal
        )
        self.assertEqual(
            result["market"],
            [
                ["SELL", "MILK", 2],
                ["SELL", "FERTILIZER", 1],
                ["SELL", "FERTILIZER", 3],
                ["SELL", "WOOL", 9],
            ],
        )
        self.assertEqual(terminal, terminal_before)
        self.assertTrue(report["b9"]["changed"])
        self.assertEqual(report["b9"]["reason"], "terminal_sale_partition")

    def test_b9_invalid_configuration_clears_episode_state(self):
        adapter = current.B9H3CCurrentABI(terminal_fertilizer=True)
        collect = {"farmer": ["PASS"], "hands": [], "market": []}
        result, _ = adapter.transform(self.b9_observation(716), self.config(), collect)
        self.assertEqual(result["farmer"], ["COLLECT_FERTILIZER"])

        bad = self.config()
        bad["turnsPerDay"] = 12
        same, report = adapter.transform(self.b9_observation(717), bad, collect)
        self.assertIs(same, collect)
        self.assertEqual(report["b9"]["reason"], "nonstandard_terminal_configuration")

        terminal = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [["SELL", "FERTILIZER", 1], ["SELL", "MILK", 2]],
        }
        result, report = adapter.transform(self.b9_observation(718), self.config(), terminal)
        self.assertIs(result, terminal)
        self.assertFalse(report["b9"]["collected_episode"])

    def test_b9_retry_or_rewind_resets_collection_state_like_submitted_agent(self):
        adapter = current.B9H3CCurrentABI(terminal_fertilizer=True)
        collect = {"farmer": ["PASS"], "hands": [], "market": []}
        first, _ = adapter.transform(self.b9_observation(716), self.config(), collect)
        self.assertEqual(first["farmer"], ["COLLECT_FERTILIZER"])
        identity = {"farmer": ["WATER"], "hands": [], "market": []}
        second, report = adapter.transform(self.b9_observation(716), self.config(), identity)
        self.assertIs(second, identity)
        self.assertTrue(report["b9"]["reset"])
        self.assertFalse(report["b9"]["collected_episode"])

    def test_h3c_replaces_only_collect_on_real_eod_overflow_witness(self):
        cfg = self.config()
        cfg["maxMarketOrdersPerTurn"] = 10
        selected = {"farmer": ["COLLECT_FERTILIZER"], "hands": [], "market": []}
        before = deepcopy(selected)
        adapter = current.B9H3CCurrentABI(goose_rescue=True)
        result, report = adapter.transform(self.h3c_observation(), cfg, selected)
        self.assertEqual(result["farmer"], ["HARVEST"])
        self.assertEqual(result["market"], [])
        self.assertEqual(selected, before)
        self.assertTrue(report["h3c"]["changed"])
        self.assertEqual(report["h3c"]["reason"], "goose_eod_cap_rescue")

    def test_h3c_market_inflow_and_capacity_guards_preserve_identity(self):
        cfg = self.config()
        cfg["maxMarketOrdersPerTurn"] = 10
        adapter = current.B9H3CCurrentABI(goose_rescue=True)
        buy = {
            "farmer": ["COLLECT_FERTILIZER"],
            "hands": [],
            "market": [["BUY_PRODUCT", "WHEAT", 1]],
        }
        result, report = adapter.transform(self.h3c_observation(), cfg, buy)
        self.assertIs(result, buy)
        self.assertFalse(report["h3c"]["changed"])

        full = {"farmer": ["COLLECT_FERTILIZER"], "hands": [], "market": []}
        observation = self.h3c_observation(shed={"MILK": 97})
        result, report = adapter.transform(observation, cfg, full)
        self.assertIs(result, full)
        self.assertFalse(report["h3c"]["changed"])

    def test_submitted_wrapper_order_is_explicit(self):
        cfg = self.config()
        cfg["maxMarketOrdersPerTurn"] = 10
        adapter = current.B9H3CCurrentABI(
            terminal_fertilizer=True, goose_rescue=True
        )
        selected = {"farmer": ["COLLECT_FERTILIZER"], "hands": [], "market": []}
        result, report = adapter.transform(self.h3c_observation(), cfg, selected)
        self.assertEqual(report["order"], ("terminal_fertilizer", "goose_rescue"))
        self.assertEqual(report["b9"]["reason"], "outside_terminal_transform")
        self.assertEqual(result["farmer"], ["HARVEST"])
        self.assertTrue(report["h3c"]["changed"])


if __name__ == "__main__":
    unittest.main()
