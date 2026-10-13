#!/usr/bin/env python3
"""Structural tests for muhl_fab_socr. Does not walk the organ as inference."""
import hashlib
import os
import struct
import tempfile
import unittest

import muhl_fab_socr as fab


class TestSocrFab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.meta, cls.stored = fab.fabricate(0)
        fab.verify_physical(cls.blob, cls.meta, cls.stored)

    def test_header_matches_mha_layout(self):
        self.assertEqual(self.blob[:8], b"MUHLSOCR")
        header = struct.unpack_from("<IIIII", self.blob, 8)
        self.assertEqual(header, (15872, 16642, 768, 768, 14))
        self.assertEqual(self.meta["len"], 28 + 768 * 8 + 16642 + 15872 * 25)

    def test_exact_plumb_gate_arithmetic(self):
        self.assertEqual(256 * 62, 15872)
        self.assertEqual(60 + 1 + 1, 62)
        self.assertEqual(4 * 15, 60)
        self.assertEqual(len(self.stored), 15872)

    def test_one_writer_per_gate_output(self):
        outputs = [record[3] for record in self.stored]
        self.assertEqual(len(outputs), 15872)
        self.assertEqual(len(set(outputs)), 15872)

    def test_self_clock_height_out_is_height_in(self):
        self.assertEqual(self.meta["input_addrs"], self.meta["output_addrs"])
        self.assertEqual(len(set(self.meta["input_addrs"])), 768)

    def test_declared_depth_matches_gate_dag(self):
        records, next_state = fab.build_gates()
        depths = {wire: 0 for wire in range(fab.W_FIELD0 + fab.N_IN)}
        max_depth = 0
        for _op, a, b, out in records:
            self.assertIn(a, depths)
            self.assertIn(b, depths)
            depths[out] = max(depths[a], depths[b]) + 1
            max_depth = max(max_depth, depths[out])
        self.assertEqual(max_depth, 14)
        for cell in range(256):
            self.assertEqual(depths[next_state[cell * 3 + 2]], 14)

    def test_neighbors_wrap_the_16x16_torus(self):
        self.assertEqual(fab.neighbor(0, -1, 0), 240)
        self.assertEqual(fab.neighbor(0, 0, -1), 15)
        self.assertEqual(fab.neighbor(255, 1, 0), 15)
        self.assertEqual(fab.neighbor(255, 0, 1), 240)

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
            fab.MNO_PATH = os.path.join(tmp, "muhl_socr.mno")
            fab.REG_PATH = os.path.join(tmp, "socr_circuits.json")
            try:
                self.assertEqual(fab.main(["--dry"]), 0)
                self.assertFalse(os.path.exists(fab.MNO_PATH))
                self.assertFalse(os.path.exists(fab.REG_PATH))
            finally:
                fab.MNO_PATH, fab.REG_PATH, fab.EXCERPT_DIR = old_mno, old_reg, old_dir


if __name__ == "__main__":
    unittest.main()
