#!/usr/bin/env python3
"""Structural tests for muhl_fab_sdmk. Does not walk the organ as inference."""
import hashlib
import os
import struct
import tempfile
import unittest

import muhl_fab_sdmk as fab


class TestSdmkFab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.meta, cls.stored = fab.fabricate(0)
        fab.verify_physical(cls.blob, cls.meta, cls.stored)

    def test_header_matches_mha_layout(self):
        self.assertEqual(self.blob[:8], b"MUHLSDMK")
        header = struct.unpack_from("<IIIII", self.blob, 8)
        self.assertEqual(header, (24800, 24930, 128, 32, 25))
        self.assertEqual(self.meta["len"], 28 + 32 * 8 + 24930 + 24800 * 25)

    def test_exact_plumb_gate_arithmetic(self):
        self.assertEqual(128 + 640 + 7, 775)
        self.assertEqual(32 * 775, 24800)
        self.assertEqual(len(self.stored), 24800)
        for loc in range(32):
            chunk = self.stored[loc * 775:(loc + 1) * 775]
            xor = chunk[:128]
            self.assertEqual([record[0] for record in xor], [fab.OP_XOR] * 128)
            pop = chunk[128:128 + 640]
            self.assertEqual(len(pop), 640)
            for adder in range(128):
                fa_ops = [record[0] for record in pop[adder * 5:(adder + 1) * 5]]
                self.assertEqual(fa_ops, [
                    fab.OP_XOR, fab.OP_XOR, fab.OP_AND, fab.OP_AND, fab.OP_OR
                ])
            thresh = chunk[128 + 640:]
            self.assertEqual([record[0] for record in thresh], [
                fab.OP_NOT, fab.OP_AND, fab.OP_OR, fab.OP_XOR,
                fab.OP_OR, fab.OP_AND, fab.OP_AND
            ])

    def test_one_writer_per_gate_output(self):
        outputs = [record[3] for record in self.stored]
        self.assertEqual(len(outputs), 24800)
        self.assertEqual(len(set(outputs)), 24800)

    def test_declared_depth_matches_gate_dag(self):
        records, activations = fab.build_gates()
        depths = {wire: 0 for wire in range(fab.W_ADDR0 + fab.N_IN)}
        max_depth = 0
        for _op, a, b, out in records:
            self.assertIn(a, depths)
            self.assertIn(b, depths)
            depths[out] = max(depths[a], depths[b]) + 1
            max_depth = max(max_depth, depths[out])
        self.assertEqual(max_depth, 25)
        self.assertEqual(
            [depths[wire] for wire in activations],
            [25] * 32,
        )

    def test_hard_locations_are_baked_and_distinct(self):
        rows = [fab.loc_bits(loc) for loc in range(32)]
        packed = ["".join("1" if bit else "0" for bit in row) for row in rows]
        self.assertEqual(len(set(packed)), 32)
        self.assertEqual(len(packed[0]), 128)
        self.assertEqual(self.meta["locations"], packed)

    def test_result_plane_is_the_thirty_two_activations(self):
        self.assertEqual(len(self.meta["output_addrs"]), 32)
        self.assertEqual(len(set(self.meta["output_addrs"])), 32)

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
            fab.MNO_PATH = os.path.join(tmp, "muhl_sdmk.mno")
            fab.REG_PATH = os.path.join(tmp, "sdmk_circuits.json")
            try:
                self.assertEqual(fab.main(["--dry"]), 0)
                self.assertFalse(os.path.exists(fab.MNO_PATH))
                self.assertFalse(os.path.exists(fab.REG_PATH))
            finally:
                fab.MNO_PATH, fab.REG_PATH, fab.EXCERPT_DIR = old_mno, old_reg, old_dir


if __name__ == "__main__":
    unittest.main()
