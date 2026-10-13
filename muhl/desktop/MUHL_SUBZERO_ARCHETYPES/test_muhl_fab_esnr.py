#!/usr/bin/env python3
"""Structural tests for muhl_fab_esnr. Does not walk the organ as inference."""
import hashlib
import os
import struct
import tempfile
import unittest

import muhl_fab_esnr as fab


class TestEsnrFab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.meta, cls.stored = fab.fabricate(0)
        fab.verify_physical(cls.blob, cls.meta, cls.stored)

    def test_header_matches_mha_layout(self):
        self.assertEqual(self.blob[:8], b"MUHLESNR")
        header = struct.unpack_from("<IIIII", self.blob, 8)
        self.assertEqual(header, (43044, 45606, 512, 512, 16))
        self.assertEqual(self.meta["len"], 28 + 512 * 8 + 45606 + 43044 * 25)

    def test_exact_plumb_gate_arithmetic(self):
        self.assertEqual(4 + 40 + 4, 48)
        self.assertEqual(512 * 48, 24576)
        self.assertEqual(1024 + 2560 + 9, 3593)
        self.assertEqual(3593 * 4, 14372)
        self.assertEqual((512 + 512) * 4, 4096)
        self.assertEqual(24576 + 14372 + 4096, 43044)
        self.assertEqual(len(self.stored), 43044)

    def test_one_writer_per_gate_output(self):
        outputs = [record[3] for record in self.stored]
        self.assertEqual(len(outputs), 43044)
        self.assertEqual(len(set(outputs)), 43044)

    def test_self_clock_reservoir_out_is_reservoir_in(self):
        self.assertEqual(self.meta["input_addrs"], self.meta["output_addrs"])
        self.assertEqual(len(set(self.meta["input_addrs"])), 512)

    def test_declared_depth_matches_gate_dag(self):
        records, next_state, _weights, readout = fab.build_gates()
        depths = {wire: 0 for wire in range(fab.W_WEIGHT0 + fab.N_WEIGHTS)}
        max_depth = 0
        for _op, a, b, out in records:
            self.assertIn(a, depths)
            self.assertIn(b, depths)
            depths[out] = max(depths[a], depths[b]) + 1
            max_depth = max(max_depth, depths[out])
        self.assertEqual(max_depth, 16)
        self.assertEqual([depths[wire] for wire in next_state], [16] * 512)
        self.assertEqual([depths[wire] for wire in readout], [16] * 4)

    def test_sparse_k8_sources_are_distinct(self):
        for unit in range(512):
            src = fab.sources(unit)
            self.assertEqual(len(src), 8)
            self.assertEqual(len(set(src)), 8)
            self.assertNotIn(unit, src)

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
            fab.MNO_PATH = os.path.join(tmp, "muhl_esnr.mno")
            fab.REG_PATH = os.path.join(tmp, "esnr_circuits.json")
            try:
                self.assertEqual(fab.main(["--dry"]), 0)
                self.assertFalse(os.path.exists(fab.MNO_PATH))
                self.assertFalse(os.path.exists(fab.REG_PATH))
            finally:
                fab.MNO_PATH, fab.REG_PATH, fab.EXCERPT_DIR = old_mno, old_reg, old_dir


if __name__ == "__main__":
    unittest.main()
