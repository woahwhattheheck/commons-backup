# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("seat_symmetry_oracle", HERE / "seat_symmetry_oracle.py")
oracle = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = oracle
spec.loader.exec_module(oracle)


class SeatSymmetryOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = oracle._load_engine(oracle.DEFAULT_ENGINE)

    def test_authenticated_engine_buffer_survives_post_read_path_swap(self):
        original = b"MARKER = 'authenticated'\n"
        attacker = "MARKER = 'attacker'\n"
        expected = hashlib.sha256(original).hexdigest()
        original_read_bytes = Path.read_bytes
        with tempfile.TemporaryDirectory() as tmp:
            engine_path = Path(tmp) / "engine.py"
            engine_path.write_bytes(original)

            def read_then_swap(path):
                raw = original_read_bytes(path)
                if path == engine_path:
                    path.write_text(attacker, encoding="utf-8")
                return raw

            with patch.object(oracle, "ENGINE_SHA256", expected), \
                 patch.object(Path, "read_bytes", new=read_then_swap):
                module = oracle._load_engine(engine_path)

            self.assertEqual(module.MARKER, "authenticated")
            self.assertEqual(engine_path.read_text(encoding="utf-8"), attacker)

    def test_known_mixed_market_queue_commutes_under_seat_swap(self):
        q_a = [["SELL", "MILK", 3], ["BUY_PRODUCT", "WHEAT", 2], ["HIRE"],
               ["BUY_LAND"], ["SELL", "FERTILIZER", 2]]
        q_b = [["BUY_PRODUCT", "FERTILIZER", 2], ["SELL", "MILK", 2], ["HIRE"],
               ["BUY_LAND"], ["SELL", "WHEAT", 1]]
        state_ab, env_ab = oracle._fresh_state(self.engine, seed=17)
        state_ba, env_ba = oracle._fresh_state(self.engine, seed=17)
        state_ab[0].action = {"market": q_a}
        state_ab[1].action = {"market": q_b}
        state_ba[0].action = {"market": q_b}
        state_ba[1].action = {"market": q_a}
        self.engine._process_market(state_ab, env_ab)
        self.engine._process_market(state_ba, env_ba)
        oracle._assert_swapped(state_ab, state_ba)

    def test_random_market_swap_trials_engage_and_pass(self):
        report = oracle.market_swap_trials(self.engine, trials=64, seed=8801)
        self.assertEqual(report["trials"], 64)
        self.assertGreater(report["engaged_market_trials"], 0)

    def test_non_eod_full_interpreter_swap_trials_pass(self):
        report = oracle.full_step_swap_trials(self.engine, trials=32, seed=8802)
        self.assertEqual(report["trials"], 32)

    def test_eod_is_symmetric_with_weeds_disabled(self):
        self.assertEqual(oracle.weed_off_eod_control(self.engine), {"symmetric": True})

    def test_eod_shared_rng_has_a_seat_stream_witness(self):
        witness = oracle.weed_stream_witness(self.engine, search_seeds=32)
        self.assertTrue(witness["different"])
        self.assertGreaterEqual(witness["seed"], 0)

    def test_full_report_is_descriptive_not_promotion(self):
        report = oracle.run(oracle.DEFAULT_ENGINE, market_trials=16, step_trials=8)
        self.assertEqual(report["schema"], "titan-v4-seat-symmetry-oracle/v1")
        self.assertEqual(report["engine_sha256"], oracle.ENGINE_SHA256)
        self.assertEqual(report["interpretation"]["promotion_decision"], "NOT_ASSESSED")


if __name__ == "__main__":
    unittest.main()
