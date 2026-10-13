#!/usr/bin/env python3
"""Structural tests for muhl_fab_pred. Does not walk the organ as inference."""
import hashlib
import os
import struct
import tempfile
import unittest

import muhl_fab_pred as fab


class TestPredFab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.meta, cls.stored = fab.fabricate(0)
        fab.verify_physical(cls.blob, cls.meta, cls.stored)

    def test_header_matches_mha_layout(self):
        self.assertEqual(self.blob[:8], b"MUHLPRED")
        header = struct.unpack_from("<IIIII", self.blob, 8)
        self.assertEqual(header, (17664, 18050, 384, 384, 42))
        self.assertEqual(self.meta["len"], 28 + 384 * 8 + 18050 + 17664 * 25)

    def test_exact_plumb_gate_arithmetic(self):
        self.assertEqual(40 + 4, 44)
        self.assertEqual(44 + 1 + 1, 46)
        self.assertEqual(384 * 46, 17664)
        self.assertEqual(len(self.stored), 17664)

    def test_one_writer_per_gate_output(self):
        outputs = [record[3] for record in self.stored]
        self.assertEqual(len(outputs), 17664)
        self.assertEqual(len(set(outputs)), 17664)

    def test_self_clock_error_out_is_prediction_in(self):
        self.assertEqual(self.meta["input_addrs"], self.meta["output_addrs"])
        self.assertEqual(len(set(self.meta["input_addrs"])), 384)

    def test_declared_depth_matches_stacked_layers(self):
        records, next_state, transmits = fab.build_gates()
        depths = {wire: 0 for wire in range(fab.W_STATE0 + fab.N_IN)}
        max_depth = 0
        for _op, a, b, out in records:
            self.assertIn(a, depths)
            self.assertIn(b, depths)
            depths[out] = max(depths[a], depths[b]) + 1
            max_depth = max(max_depth, depths[out])
        self.assertEqual(max_depth, 42)
        self.assertEqual([depths[wire] for wire in transmits[0]], [14] * 128)
        self.assertEqual([depths[wire] for wire in transmits[1]], [28] * 128)
        self.assertEqual([depths[wire] for wire in transmits[2]], [42] * 128)
        self.assertEqual([depths[wire] for wire in next_state[256:]], [42] * 128)

    def test_deterministic_bytes(self):
        blob2, meta2, stored2 = fab.fabricate(0)
        self.assertEqual(self.blob, blob2)
        self.assertEqual(self.stored, stored2)
        self.assertEqual(self.meta["sha256"], meta2["sha256"])
        self.assertEqual(self.meta["sha256"], hashlib.sha256(self.blob).hexdigest())

    def test_dry_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_mno, old_reg, old_dir = fab.MNO_PATH, fab.REG_PATH, fab.EXCERPT_DIR
            fab.EXCERPT_DIR = tmp
            fab.MNO_PATH = os.path.join(tmp, "muhl_pred.mno")
            fab.REG_PATH = os.path.join(tmp, "pred_circuits.json")
            try:
                self.assertEqual(fab.main(["--dry"]), 0)
                self.assertFalse(os.path.exists(fab.MNO_PATH))
                self.assertFalse(os.path.exists(fab.REG_PATH))
            finally:
                fab.MNO_PATH, fab.REG_PATH, fab.EXCERPT_DIR = old_mno, old_reg, old_dir


if __name__ == "__main__":
    unittest.main()
