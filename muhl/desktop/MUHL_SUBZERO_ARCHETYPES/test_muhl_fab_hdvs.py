#!/usr/bin/env python3
"""Structural tests for muhl_fab_hdvs. Does not walk the organ as inference."""
import hashlib
import os
import struct
import tempfile
import unittest

import muhl_fab_hdvs as fab


class TestHdvsFab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.meta, cls.stored = fab.fabricate(0)
        fab.verify_physical(cls.blob, cls.meta, cls.stored)

    def test_header_matches_mha_layout(self):
        self.assertEqual(self.blob[:8], b"MUHLHDVS")
        header = struct.unpack_from("<IIIII", self.blob, 8)
        self.assertEqual(header, (12288, 13314, 1024, 1024, 34))
        self.assertEqual(self.meta["len"], 28 + 1024 * 8 + 13314 + 12288 * 25)

    def test_exact_plumb_gate_arithmetic(self):
        self.assertEqual(1024 + 5120 + 1024 + 5120, 12288)
        self.assertEqual(len(self.stored), 12288)
        bind = self.stored[:1024]
        self.assertEqual([record[0] for record in bind], [fab.OP_XOR] * 1024)
        bundle = self.stored[1024:1024 + 5120]
        for bit in range(1024):
            chunk = bundle[bit * 5:(bit + 1) * 5]
            self.assertEqual([record[0] for record in chunk], [
                fab.OP_AND, fab.OP_AND, fab.OP_AND, fab.OP_OR, fab.OP_OR
            ])
        sim = self.stored[1024 + 5120:1024 + 5120 + 1024]
        self.assertEqual([record[0] for record in sim], [fab.OP_XOR] * 1024)
        pop = self.stored[1024 + 5120 + 1024:]
        self.assertEqual(len(pop), 5120)
        for adder in range(1024):
            chunk = pop[adder * 5:(adder + 1) * 5]
            self.assertEqual([record[0] for record in chunk], [
                fab.OP_XOR, fab.OP_XOR, fab.OP_AND, fab.OP_AND, fab.OP_OR
            ])

    def test_one_writer_per_gate_output(self):
        outputs = [record[3] for record in self.stored]
        self.assertEqual(len(outputs), 12288)
        self.assertEqual(len(set(outputs)), 12288)

    def test_declared_depth_matches_gate_dag(self):
        records, roots, pop_root = fab.build_gates()
        depths = {wire: 0 for wire in range(fab.W_VEC0 + fab.N_IN)}
        max_depth = 0
        for _op, a, b, out in records:
            self.assertIn(a, depths)
            self.assertIn(b, depths)
            depths[out] = max(depths[a], depths[b]) + 1
            max_depth = max(max_depth, depths[out])
        self.assertEqual(max_depth, 34)
        self.assertLessEqual(max(depths[root] for root in roots), 34)
        self.assertEqual(depths[pop_root], 34)

    def test_permute_is_wiring(self):
        self.assertEqual(fab.PERM_BIND, 1)
        self.assertEqual(fab.PERM_BUNDLE_A, 3)
        self.assertEqual(fab.PERM_BUNDLE_B, 17)

    def test_result_plane_is_the_bundle(self):
        self.assertEqual(len(self.meta["output_addrs"]), 1024)
        self.assertEqual(len(set(self.meta["output_addrs"])), 1024)

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
            fab.MNO_PATH = os.path.join(tmp, "muhl_hdvs.mno")
            fab.REG_PATH = os.path.join(tmp, "hdvs_circuits.json")
            try:
                self.assertEqual(fab.main(["--dry"]), 0)
                self.assertFalse(os.path.exists(fab.MNO_PATH))
                self.assertFalse(os.path.exists(fab.REG_PATH))
            finally:
                fab.MNO_PATH, fab.REG_PATH, fab.EXCERPT_DIR = old_mno, old_reg, old_dir


if __name__ == "__main__":
    unittest.main()
