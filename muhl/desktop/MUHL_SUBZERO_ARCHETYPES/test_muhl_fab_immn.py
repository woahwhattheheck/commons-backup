#!/usr/bin/env python3
"""Structural tests for muhl_fab_immn. Does not walk the organ as inference."""
import hashlib
import os
import struct
import tempfile
import unittest

import muhl_fab_immn as fab


class TestImmnFab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.meta, cls.stored = fab.fabricate(0)
        fab.verify_physical(cls.blob, cls.meta, cls.stored)

    def test_header_matches_mha_layout(self):
        self.assertEqual(self.blob[:8], b"MUHLIMMN")
        header = struct.unpack_from("<IIIII", self.blob, 8)
        self.assertEqual(header, (29951, 34081, 32, 1, 27))
        self.assertEqual(self.meta["len"], 28 + 1 * 8 + 34081 + 29951 * 25)

    def test_exact_plumb_gate_arithmetic(self):
        self.assertEqual(32 + 160 + 6, 198)
        self.assertEqual(128 * 198, 25344)
        self.assertEqual(25344 + 127, 25471)
        self.assertEqual(128 * 35, 4480)
        self.assertEqual(25471 + 4480, 29951)
        self.assertEqual(len(self.stored), 29951)

    def test_one_writer_per_gate_output(self):
        outputs = [record[3] for record in self.stored]
        self.assertEqual(len(outputs), 29951)
        self.assertEqual(len(set(outputs)), 29951)

    def test_declared_depth_matches_gate_dag(self):
        records, flags, alarm, _next = fab.build_gates()
        depths = {wire: 0 for wire in range(fab.W_DET0 + fab.N_DET_BITS)}
        max_depth = 0
        for _op, a, b, out in records:
            self.assertIn(a, depths)
            self.assertIn(b, depths)
            depths[out] = max(depths[a], depths[b]) + 1
            max_depth = max(max_depth, depths[out])
        self.assertEqual(max_depth, 27)
        self.assertEqual([depths[wire] for wire in flags], [20] * 128)
        self.assertEqual(depths[alarm], 27)

    def test_flags_are_not_admission_gates(self):
        self.assertEqual(len(self.meta["flag_wires"]), 128)
        self.assertEqual(len(self.meta["output_addrs"]), 1)
        self.assertEqual(len(self.meta["input_addrs"]), 32)

    def test_detectors_are_baked_and_distinct(self):
        rows = [fab.det_bits(det) for det in range(128)]
        packed = ["".join("1" if bit else "0" for bit in row) for row in rows]
        self.assertEqual(len(set(packed)), 128)
        self.assertEqual(len(packed[0]), 32)
        self.assertEqual(self.meta["detectors"], packed)

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
            fab.MNO_PATH = os.path.join(tmp, "muhl_immn.mno")
            fab.REG_PATH = os.path.join(tmp, "immn_circuits.json")
            try:
                self.assertEqual(fab.main(["--dry"]), 0)
                self.assertFalse(os.path.exists(fab.MNO_PATH))
                self.assertFalse(os.path.exists(fab.REG_PATH))
            finally:
                fab.MNO_PATH, fab.REG_PATH, fab.EXCERPT_DIR = old_mno, old_reg, old_dir


if __name__ == "__main__":
    unittest.main()
