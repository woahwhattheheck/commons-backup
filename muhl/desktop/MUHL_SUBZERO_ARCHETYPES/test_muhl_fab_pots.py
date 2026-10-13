#!/usr/bin/env python3
"""Structural tests for muhl_fab_pots. Does not walk the organ as inference."""
import hashlib
import os
import struct
import tempfile
import unittest

import muhl_fab_pots as fab


class TestPotsFab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.meta, cls.stored = fab.fabricate(0)
        fab.verify_physical(cls.blob, cls.meta, cls.stored)

    def test_header_matches_mha_layout(self):
        self.assertEqual(self.blob[:8], b"MUHLPOTS")
        header = struct.unpack_from("<IIIII", self.blob, 8)
        self.assertEqual(header, (34304, 35330, 1024, 1024, 20))
        self.assertEqual(self.meta["len"], 28 + 1024 * 8 + 35330 + 34304 * 25)

    def test_exact_plumb_gate_arithmetic(self):
        self.assertEqual(8 * 11, 88)
        self.assertEqual(88 + 40 + 6, 134)
        self.assertEqual(256 * 134, 34304)
        self.assertEqual(len(self.stored), 34304)

    def test_one_writer_per_gate_output(self):
        outputs = [record[3] for record in self.stored]
        self.assertEqual(len(outputs), 34304)
        self.assertEqual(len(set(outputs)), 34304)

    def test_self_clock_id_out_is_id_in(self):
        self.assertEqual(self.meta["input_addrs"], self.meta["output_addrs"])
        self.assertEqual(len(set(self.meta["input_addrs"])), 1024)

    def test_declared_depth_matches_gate_dag(self):
        records, next_id = fab.build_gates()
        depths = {wire: 0 for wire in range(fab.W_ID0 + fab.N_IN)}
        max_depth = 0
        for _op, a, b, out in records:
            self.assertIn(a, depths)
            self.assertIn(b, depths)
            depths[out] = max(depths[a], depths[b]) + 1
            max_depth = max(max_depth, depths[out])
        self.assertEqual(max_depth, 20)
        self.assertEqual([depths[wire] for wire in next_id], [20] * 1024)

    def test_eight_neighbors_are_torus_and_not_self(self):
        self.assertEqual(fab.neighbors(0), (240, 241, 1, 17, 16, 31, 15, 255))
        for site in range(256):
            neigh = fab.neighbors(site)
            self.assertEqual(len(neigh), 8)
            self.assertEqual(len(set(neigh)), 8)
            self.assertNotIn(site, neigh)

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
            fab.MNO_PATH = os.path.join(tmp, "muhl_pots.mno")
            fab.REG_PATH = os.path.join(tmp, "pots_circuits.json")
            try:
                self.assertEqual(fab.main(["--dry"]), 0)
                self.assertFalse(os.path.exists(fab.MNO_PATH))
                self.assertFalse(os.path.exists(fab.REG_PATH))
            finally:
                fab.MNO_PATH, fab.REG_PATH, fab.EXCERPT_DIR = old_mno, old_reg, old_dir


if __name__ == "__main__":
    unittest.main()
