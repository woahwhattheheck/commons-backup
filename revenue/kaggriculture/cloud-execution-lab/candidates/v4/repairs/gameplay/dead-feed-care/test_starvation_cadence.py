#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("starvation_cadence", HERE / "starvation_cadence.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

ENGINE_PATH = os.environ.get("TITAN_ENGINE_PATH")


@unittest.skipUnless(ENGINE_PATH, "set TITAN_ENGINE_PATH to exact pinned engine/kaggriculture.py")
class StarvationCadenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = mod.load_engine(ENGINE_PATH)

    def test_engine_identity_is_exact(self):
        data = Path(ENGINE_PATH).read_bytes()
        self.assertEqual(mod.ENGINE_GIT_BLOB, mod._git_blob_sha(data))
        import hashlib
        self.assertEqual(mod.ENGINE_SHA256, hashlib.sha256(data).hexdigest())

    def test_all_species_base_output_and_fertilizer_survive_half_feed(self):
        for species, expected_product in mod.EXPECTED_PRODUCTS.items():
            with self.subTest(species=species):
                daily = mod.run_cadence(self.engine, species, feed_mode="daily")
                alt = mod.run_cadence(self.engine, species, feed_mode="alternating", phase=0)
                self.assertTrue(daily["survived"])
                self.assertTrue(alt["survived"])
                self.assertEqual(expected_product, daily["product_total"])
                self.assertEqual(daily["product_total"], alt["product_total"])
                self.assertEqual(30, daily["fertilizer_total"])
                self.assertEqual(daily["fertilizer_total"], alt["fertilizer_total"])
                self.assertEqual(30, daily["wheat_consumed"])
                self.assertEqual(15, alt["wheat_consumed"])
                self.assertEqual(30, daily["action_attempts"]["feed"])
                self.assertEqual(15, alt["action_attempts"]["feed"])
                self.assertEqual(30, daily["action_attempts"]["pickup"])
                self.assertEqual(15, alt["action_attempts"]["pickup"])

    def test_both_alternating_phases_are_safe_without_care(self):
        for species in self.engine.ANIMALS:
            with self.subTest(species=species):
                phase0 = mod.run_cadence(self.engine, species, feed_mode="alternating", phase=0)
                phase1 = mod.run_cadence(self.engine, species, feed_mode="alternating", phase=1)
                self.assertTrue(phase0["survived"])
                self.assertTrue(phase1["survived"])
                self.assertEqual(phase0["product_total"], phase1["product_total"])
                self.assertEqual(phase0["fertilizer_total"], phase1["fertilizer_total"])
                self.assertEqual(15, phase0["wheat_consumed"])
                self.assertEqual(15, phase1["wheat_consumed"])

    def test_two_consecutive_unfed_days_escape(self):
        for species in self.engine.ANIMALS:
            with self.subTest(species=species):
                result = mod.run_cadence(self.engine, species, days=2, feed_mode="never")
                self.assertFalse(result["survived"])
                self.assertEqual(1, result["escaped_day"])

    def test_held_capacity_does_not_create_false_alternating_advantage(self):
        for species, cap in mod.EXPECTED_HELD_CAPS.items():
            with self.subTest(species=species):
                daily = mod.run_cadence(
                    self.engine, species, feed_mode="daily", harvest_every_day=False
                )
                alt = mod.run_cadence(
                    self.engine, species, feed_mode="alternating", harvest_every_day=False
                )
                self.assertEqual(cap, daily["product_total"])
                self.assertEqual(daily["product_total"], alt["product_total"])
                self.assertEqual(30, daily["fertilizer_total"])
                self.assertEqual(30, alt["fertilizer_total"])
                self.assertEqual(30, daily["wheat_consumed"])
                self.assertEqual(15, alt["wheat_consumed"])

    def test_daily_care_breaks_blanket_half_feed_equivalence(self):
        expected_loss = {"GOOSE": 29, "COW": 27, "SHEEP": 25}
        for species, loss in expected_loss.items():
            with self.subTest(species=species):
                daily = mod.run_cadence(
                    self.engine, species, feed_mode="daily", care_every_day=True
                )
                alt = mod.run_cadence(
                    self.engine, species, feed_mode="alternating", care_every_day=True
                )
                self.assertTrue(daily["survived"])
                self.assertTrue(alt["survived"])
                self.assertEqual(15, alt["wheat_consumed"])
                self.assertEqual(30, alt["fertilizer_total"])
                self.assertEqual(loss, daily["product_total"] - alt["product_total"])

    def test_wrong_engine_bytes_fail_before_execution(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "kaggriculture.py"
            bad.write_bytes(Path(ENGINE_PATH).read_bytes() + b"\n# drift\n")
            with self.assertRaises(mod.VerificationError):
                mod.load_engine(bad)


if __name__ == "__main__":
    unittest.main()
