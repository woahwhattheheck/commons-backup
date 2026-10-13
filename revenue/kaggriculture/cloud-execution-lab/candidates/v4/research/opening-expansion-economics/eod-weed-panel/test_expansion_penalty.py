#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("expansion_penalty", HERE / "expansion_penalty.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

ENGINE_PATH = os.environ.get("TITAN_ENGINE_PATH")
CONFIG_PATH = os.environ.get("TITAN_CONFIG_PATH")


class PairedSummaryContractTests(unittest.TestCase):
    def test_canonical_hundred_sample_panel_uses_df99_t_interval(self):
        values = [i % 7 for i in range(100)]
        result = mod._paired_summary(values)
        mean = float(result["mean"])
        se = float(result["standard_error"])
        self.assertAlmostEqual(mean - mod.T_CRIT_DF99_95 * se, result["t95_low"])
        self.assertAlmostEqual(mean + mod.T_CRIT_DF99_95 * se, result["t95_high"])

    def test_non_hundred_sample_panels_do_not_emit_df99_t_interval(self):
        for values in ([1], [1, 2], list(range(10)), list(range(101))):
            with self.subTest(n=len(values)):
                result = mod._paired_summary(values)
                self.assertIsNone(result["t95_low"])
                self.assertIsNone(result["t95_high"])
                self.assertTrue(math.isfinite(float(result["mean"])))
                self.assertTrue(math.isfinite(float(result["standard_error"])))


@unittest.skipUnless(ENGINE_PATH and CONFIG_PATH, "set TITAN_ENGINE_PATH and TITAN_CONFIG_PATH")
class ExpansionPenaltyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = mod.load_engine(ENGINE_PATH)
        cls.config = mod.load_config(CONFIG_PATH)

    def test_exact_source_and_config_identities(self):
        engine = Path(ENGINE_PATH).read_bytes()
        config = Path(CONFIG_PATH).read_bytes()
        self.assertEqual(mod.ENGINE_GIT_BLOB, mod._git_blob_sha(engine))
        self.assertEqual(mod.ENGINE_SHA256, hashlib.sha256(engine).hexdigest())
        self.assertEqual(mod.CONFIG_GIT_BLOB, mod._git_blob_sha(config))
        self.assertEqual(mod.CONFIG_SHA256, hashlib.sha256(config).hexdigest())

    def test_pinned_defaults_and_land_prices(self):
        self.assertEqual(10, mod.default_value(self.config, "boardSize"))
        self.assertEqual(0.005, mod.default_value(self.config, "weedSpawnChance"))
        self.assertEqual([1000, 2000, 4000], list(self.engine.LAND_PRICES))

    def test_unlocked_empty_tile_counts(self):
        self.assertEqual(25, mod.unlocked_empty_tiles(mod._farm_with_quadrants(self.engine, 1)))
        self.assertEqual(100, mod.unlocked_empty_tiles(mod._farm_with_quadrants(self.engine, 4)))

    def test_exact_hundred_seed_panel(self):
        rows, summary = mod.run_panel(self.engine, self.config, range(1, 101), days=30)
        self.assertEqual(100, len(rows))
        clear = summary["perfect_clear_spawn_events"]
        self.assertAlmostEqual(3.79, clear["q1"]["mean"])
        self.assertAlmostEqual(15.14, clear["q4"]["mean"])
        self.assertAlmostEqual(11.35, clear["incremental_q4_minus_q1"]["mean"])
        self.assertEqual(0, clear["incremental_q4_minus_q1"]["negative_pairs"])
        self.assertEqual(0, clear["incremental_q4_minus_q1"]["zero_pairs"])
        self.assertEqual(100, clear["incremental_q4_minus_q1"]["positive_pairs"])
        self.assertAlmostEqual(10.669406310738124, clear["incremental_q4_minus_q1"]["t95_low"])
        self.assertAlmostEqual(12.030593689261876, clear["incremental_q4_minus_q1"]["t95_high"])
        persistent = summary["persistent_no_clear_final_weeds"]
        self.assertAlmostEqual(3.48, persistent["q1"]["mean"])
        self.assertAlmostEqual(14.08, persistent["q4"]["mean"])
        self.assertAlmostEqual(10.60, persistent["incremental_q4_minus_q1"]["mean"])

    def test_analytic_perfect_clear_expectation(self):
        _, summary = mod.run_panel(self.engine, self.config, [1], days=30)
        expected = summary["perfect_clear_spawn_events"]["analytic_expectation"]
        self.assertEqual(3.75, expected["q1"])
        self.assertEqual(15.0, expected["q4"])
        self.assertEqual(11.25, expected["incremental"])
        self.assertEqual(7000, summary["break_even"]["extra_land_cash_cost"])
        self.assertAlmostEqual(93.33333333333333, summary["break_even"]["average_upfront_cash_per_extra_tile"])
        self.assertEqual(0.15, summary["break_even"]["expected_random_digs_per_extra_empty_tile_over_30d"])
        self.assertIsNone(summary["perfect_clear_spawn_events"]["incremental_q4_minus_q1"]["t95_low"])
        self.assertIsNone(summary["persistent_no_clear_final_weeds"]["incremental_q4_minus_q1"]["t95_high"])

    def test_persistent_analytic_expectation_matches_formula(self):
        _, summary = mod.run_panel(self.engine, self.config, [1], days=30)
        persistent = summary["persistent_no_clear_final_weeds"]["analytic_expectation"]
        p = 0.005
        self.assertAlmostEqual(25 * (1 - (1 - p) ** 30), persistent["q1"])
        self.assertAlmostEqual(100 * (1 - (1 - p) ** 30), persistent["q4"])

    def test_wrong_engine_or_config_bytes_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bad_engine = root / "engine.py"
            bad_engine.write_bytes(Path(ENGINE_PATH).read_bytes() + b"\n# drift\n")
            with self.assertRaises(mod.ExpansionError):
                mod.load_engine(bad_engine)
            bad_config = root / "config.json"
            value = json.loads(Path(CONFIG_PATH).read_text())
            value["configuration"]["weedSpawnChance"]["default"] = 0.5
            bad_config.write_text(json.dumps(value))
            with self.assertRaises(mod.ExpansionError):
                mod.load_config(bad_config)


if __name__ == "__main__":
    unittest.main()
