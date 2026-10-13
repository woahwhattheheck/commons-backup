#!/usr/bin/env python3
"""Structural tests for muhl_fab_tset. Does not walk the organ as inference."""
import hashlib
import os
import struct
import tempfile
import unittest

import muhl_fab_tset as fab


class TestTsetFab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.meta, cls.stored = fab.fabricate(0)
        fab.verify_physical(cls.blob, cls.meta, cls.stored)

    def test_header_matches_mha_layout(self):
        self.assertEqual(self.blob[:8], b"MUHLTSET")
        header = struct.unpack_from("<IIIII", self.blob, 8)
        self.assertEqual(header, (23856, 27986, 32, 1, 23))
        self.assertEqual(self.meta["len"], 28 + 1 * 8 + 27986 + 23856 * 25)

    def test_exact_plumb_gate_arithmetic(self):
        self.assertEqual(32 * 2 + 31, 95)
        self.assertEqual(32 * 95, 3040)
        self.assertEqual(2 * 160 + 16, 336)
        self.assertEqual(1024 * 20, 20480)
        self.assertEqual(3040 + 336 + 20480, 23856)
        self.assertEqual(len(self.stored), 23856)

    def test_one_writer_per_gate_output(self):
        outputs = [record[3] for record in self.stored]
        self.assertEqual(len(outputs), 23856)
        self.assertEqual(len(set(outputs)), 23856)

    def test_declared_depth_matches_gate_dag(self):
        records, clauses, vote, _next = fab.build_gates()
        depths = {wire: 0 for wire in range(fab.W_AUTO0 + fab.N_STATE)}
        max_depth = 0
        for _op, a, b, out in records:
            self.assertIn(a, depths)
            self.assertIn(b, depths)
            depths[out] = max(depths[a], depths[b]) + 1
            max_depth = max(max_depth, depths[out])
        self.assertEqual(max_depth, 23)
        self.assertEqual([depths[wire] for wire in clauses], [7] * 32)
        self.assertEqual(depths[vote], 23)

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
            fab.MNO_PATH = os.path.join(tmp, "muhl_tset.mno")
            fab.REG_PATH = os.path.join(tmp, "tset_circuits.json")
            try:
                self.assertEqual(fab.main(["--dry"]), 0)
                self.assertFalse(os.path.exists(fab.MNO_PATH))
                self.assertFalse(os.path.exists(fab.REG_PATH))
            finally:
                fab.MNO_PATH, fab.REG_PATH, fab.EXCERPT_DIR = old_mno, old_reg, old_dir


if __name__ == "__main__":
    unittest.main()
