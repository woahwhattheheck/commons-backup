#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import deadcap_oracle as d

CLOUD = HERE.parents[3]
TAPES = CLOUD / "candidates" / "v4" / "donor" / "overlay" / "r01_tapes.py"
ENGINE = CLOUD / "reference" / "engine" / "kaggriculture.py"


class DeadcapOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.auth = d.authenticate(TAPES, ENGINE)
        cls.tapes = d.load_tapes(TAPES)
        cls.engine = d.load_engine(ENGINE)

    def test_exact_sources(self):
        self.assertEqual(self.auth["tape_blob"], d.TAPE_BLOB)
        self.assertEqual(self.auth["engine_blob"], d.ENGINE_BLOB)
        self.assertEqual(self.auth["tape_bytes"], 32955)

    def test_acquisition_census_is_exact(self):
        result = d.acquisition_census(self.tapes)
        self.assertEqual(result["counts"], {
            "BUY_PRODUCT": 724,
            "BUY_ANIMAL": 159,
            "BUY_SEED": 2330,
            "BUY_LAND": 26,
        })
        self.assertEqual(result["late_ge_480"], 929)
        self.assertEqual(result["dead_seed_candidates"], [{
            "tape": 12,
            "step": 284,
            "row_index": 0,
            "order": ["BUY_SEED", "MELON", 1],
            "reason": "no_future_plant_maturity_sale_path",
        }])

    def test_witness_has_no_future_melon_plant(self):
        self.assertIsNone(d.seed_cash_path(self.tapes[12], 284, "MELON"))
        future_plants = []
        for step in range(285, 719):
            for action in d.unit_actions(self.tapes[12][step]):
                if action[:2] == ["PLANT", "MELON"]:
                    future_plants.append(step)
        self.assertEqual(future_plants, [])

    def test_nearby_wheat_is_refused_not_called_dead(self):
        path = d.seed_cash_path(self.tapes[12], 663, "WHEAT")
        self.assertIsNotNone(path)

    def test_exact_engine_executes_and_strands_witness(self):
        receipt = d.witness_receipt(self.tapes, self.engine)
        self.assertEqual(receipt["pre_money"], 11021.0)
        self.assertEqual(receipt["post_money"], 10941.0)
        self.assertEqual(receipt["pre_melon_seeds"], 0)
        self.assertEqual(receipt["post_melon_seeds"], 1)
        self.assertEqual(receipt["terminal_melon_seeds"], 1)
        self.assertEqual(receipt["own_delta"], 80.0)
        self.assertEqual(receipt["rival_delta"], 0.0)

    def test_current_native_does_not_emit_donor_witness(self):
        # Bind the COLD claim to the exact production bytes advertised by this
        # package. A moving checkout must fail closed before the native probe;
        # donor-only theorem tests above remain independently reproducible.
        current = d.authenticate_current(CLOUD)
        self.assertEqual(current, {
            "main_blob": d.CURRENT_MAIN_BLOB,
            "runtime_blob": d.CURRENT_RUNTIME_BLOB,
            "config_blob": d.CURRENT_CONFIG_BLOB,
        })
        receipt = d.current_native_probe(CLOUD, self.engine, self.tapes, seed=0, rival_tape=0)
        self.assertFalse(receipt["emits_witness"])
        self.assertEqual(receipt["post_melon_seeds"], 0)
        self.assertFalse(receipt["config_deadcap_key_present"])

    def test_both_seats_preserve_exact_eighty_dollar_delta(self):
        for seat in (0, 1):
            base_own, base_rival, _ = d.replay_pair(
                self.engine, self.tapes[12], self.tapes[0],
                seat=seat, seed=0, remove_witness=False)
            arm_own, arm_rival, _ = d.replay_pair(
                self.engine, self.tapes[12], self.tapes[0],
                seat=seat, seed=0, remove_witness=True)
            self.assertEqual(arm_own - base_own, 80.0)
            self.assertEqual(arm_rival - base_rival, 0.0)


if __name__ == "__main__":
    unittest.main()
