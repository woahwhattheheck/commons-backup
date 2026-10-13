#!/usr/bin/env python3
"""Structural tests for muhl_fab_hopf. Does not walk the organ as inference."""
import hashlib
import os
import struct
import tempfile
import unittest

import muhl_fab_hopf as fab


class TestHopfFab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.meta, cls.stored = fab.fabricate(0)
        fab.verify_physical(cls.blob, cls.meta, cls.stored)

    def test_header_matches_mha_layout(self):
        self.assertEqual(self.blob[:8], b"MUHLHOPF")
        header = struct.unpack_from("<IIIII", self.blob, 8)
        self.assertEqual(header, (37248, 41410, 64, 64, 24))
        self.assertEqual(self.meta["len"], 28 + 64 * 8 + 41410 + 37248 * 25)

    def test_exact_plumb_gate_arithmetic(self):
        self.assertEqual(128 + 320 + 6, 454)
        self.assertEqual(64 * 454, 29056)
        self.assertEqual(4096 * 2, 8192)
        self.assertEqual(29056 + 8192, 37248)
        self.assertEqual(len(self.stored), 37248)

    def test_one_writer_per_gate_output(self):
        outputs = [record[3] for record in self.stored]
        self.assertEqual(len(outputs), 37248)
        self.assertEqual(len(set(outputs)), 37248)

    def test_self_clock_state_out_is_state_in(self):
        self.assertEqual(self.meta["input_addrs"], self.meta["output_addrs"])
        self.assertEqual(len(set(self.meta["input_addrs"])), 64)

    def test_declared_depth_matches_gate_dag(self):
        records, next_state, _weights = fab.build_gates()
        depths = {wire: 0 for wire in range(fab.W_WEIGHT0 + fab.N_WEIGHTS)}
        max_depth = 0
        for _op, a, b, out in records:
            self.assertIn(a, depths)
            self.assertIn(b, depths)
            depths[out] = max(depths[a], depths[b]) + 1
            max_depth = max(max_depth, depths[out])
        self.assertEqual(max_depth, 24)
        self.assertEqual([depths[wire] for wire in next_state], [24] * 64)

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
            fab.MNO_PATH = os.path.join(tmp, "muhl_hopf.mno")
            fab.REG_PATH = os.path.join(tmp, "hopf_circuits.json")
            try:
                self.assertEqual(fab.main(["--dry"]), 0)
                self.assertFalse(os.path.exists(fab.MNO_PATH))
                self.assertFalse(os.path.exists(fab.REG_PATH))
            finally:
                fab.MNO_PATH, fab.REG_PATH, fab.EXCERPT_DIR = old_mno, old_reg, old_dir


if __name__ == "__main__":
    unittest.main()
