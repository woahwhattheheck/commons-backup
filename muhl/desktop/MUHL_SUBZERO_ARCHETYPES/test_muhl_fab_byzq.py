#!/usr/bin/env python3
"""Structural tests for muhl_fab_byzq. Does not walk the organ as inference."""
import hashlib
import os
import struct
import tempfile
import unittest

import muhl_fab_byzq as fab


class TestByzqFab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.meta, cls.stored = fab.fabricate(0)
        fab.verify_physical(cls.blob, cls.meta, cls.stored)

    def test_header_matches_mha_layout(self):
        self.assertEqual(self.blob[:8], b"MUHLBYZQ")
        header = struct.unpack_from("<IIIII", self.blob, 8)
        self.assertEqual(header, (14880, 14913, 31, 31, 30))
        self.assertEqual(self.meta["len"], 28 + 31 * 8 + 14913 + 14880 * 25)

    def test_exact_plumb_gate_arithmetic(self):
        self.assertEqual(155 + 5, 160)
        self.assertEqual(31 * 160 * 3, 14880)
        self.assertEqual(len(self.stored), 14880)

    def test_one_writer_per_gate_output(self):
        outputs = [record[3] for record in self.stored]
        self.assertEqual(len(outputs), 14880)
        self.assertEqual(len(set(outputs)), 14880)

    def test_declared_depth_matches_gate_dag(self):
        records, roots = fab.build_gates()
        depths = {wire: 0 for wire in range(fab.W_VOTE0 + fab.N_IN)}
        max_depth = 0
        for _op, a, b, out in records:
            self.assertIn(a, depths)
            self.assertIn(b, depths)
            depths[out] = max(depths[a], depths[b]) + 1
            max_depth = max(max_depth, depths[out])
        self.assertEqual(max_depth, 30)
        self.assertEqual([depths[root] for root in roots], [30] * 31)

    def test_each_unit_is_32_full_adders(self):
        for unit in range(93):
            chunk = self.stored[unit * 160:(unit + 1) * 160]
            for adder in range(32):
                ops = [g[0] for g in chunk[adder * 5:(adder + 1) * 5]]
                self.assertEqual(ops, [
                    fab.OP_XOR, fab.OP_XOR, fab.OP_AND, fab.OP_AND, fab.OP_OR
                ])

    def test_result_plane_is_final_phase(self):
        self.assertEqual(len(self.meta["output_addrs"]), 31)
        self.assertEqual(len(set(self.meta["output_addrs"])), 31)

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
            fab.MNO_PATH = os.path.join(tmp, "muhl_byzq.mno")
            fab.REG_PATH = os.path.join(tmp, "byzq_circuits.json")
            try:
                self.assertEqual(fab.main(["--dry"]), 0)
                self.assertFalse(os.path.exists(fab.MNO_PATH))
                self.assertFalse(os.path.exists(fab.REG_PATH))
            finally:
                fab.MNO_PATH, fab.REG_PATH, fab.EXCERPT_DIR = old_mno, old_reg, old_dir


if __name__ == "__main__":
    unittest.main()
