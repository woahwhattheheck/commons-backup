#!/usr/bin/env python3
"""Structural tests for muhl_fab_ispn. Does not evaluate the organ."""
import hashlib
import os
import struct
import tempfile
import unittest

import muhl_fab_ispn as fab


class TestIspnFab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.meta, cls.stored = fab.fabricate(0)
        fab.verify_physical(cls.blob, cls.meta, cls.stored)

    def test_header_matches_mha_layout(self):
        self.assertEqual(self.blob[:8], b"MUHLISPN")
        ng, nw, ni, no, dp = struct.unpack_from("<IIIII", self.blob, 8)
        self.assertEqual((ng, nw, ni, no, dp), (8784, 9058, 256, 256, 12))
        self.assertEqual(self.meta["len"], 28 + 256 * 8 + 9058 + 8784 * 25)

    def test_one_writer_per_out(self):
        outs = [g[3] for g in self.stored]
        self.assertEqual(len(outs), 8784)
        self.assertEqual(len(set(outs)), 8784)

    def test_self_clock_spin_out_is_spin_in(self):
        self.assertEqual(self.meta["input_addrs"], self.meta["output_addrs"])
        self.assertEqual(len(set(self.meta["input_addrs"])), 256)

    def test_counter_and_per_spin_split(self):
        cnt = self.stored[:80]
        self.assertEqual([g[0] for g in cnt].count(fab.OP_XOR), 32)
        self.assertEqual([g[0] for g in cnt].count(fab.OP_AND), 32)
        self.assertEqual([g[0] for g in cnt].count(fab.OP_OR), 16)
        for node in range(256):
            chunk = self.stored[80 + node * 34:80 + (node + 1) * 34]
            ops = [g[0] for g in chunk]
            self.assertEqual(ops.count(fab.OP_XOR), 13)
            self.assertEqual(ops.count(fab.OP_NOT), 6)
            self.assertEqual(ops.count(fab.OP_AND), 10)
            self.assertEqual(ops.count(fab.OP_OR), 5)
            self.assertTrue(all(op in (0, 1, 2, 3, 4) for op in ops))

    def test_four_neighbours_wrap(self):
        self.assertEqual(fab.neighbors(0), (1, 15, 16, 240))
        self.assertEqual(fab.neighbors(15), (0, 14, 31, 255))
        self.assertEqual(fab.neighbors(255), (240, 254, 15, 239))
        for node in range(256):
            nbs = fab.neighbors(node)
            self.assertEqual(len(nbs), 4)
            self.assertEqual(len(set(nbs)), 4)
            self.assertNotIn(node, nbs)

    def test_deterministic(self):
        blob2, meta2, _ = fab.fabricate(0)
        self.assertEqual(self.blob, blob2)
        self.assertEqual(self.meta["sha256"], meta2["sha256"])
        self.assertEqual(self.meta["sha256"], hashlib.sha256(self.blob).hexdigest())

    def test_dry_does_not_write(self):
        here = os.path.dirname(os.path.abspath(fab.__file__))
        with tempfile.TemporaryDirectory() as tmp:
            old_mno, old_reg = fab.MNO_PATH, fab.REG_PATH
            fab.MNO_PATH = os.path.join(tmp, "muhl_ispn.mno")
            fab.REG_PATH = os.path.join(tmp, "ispn_circuits.json")
            try:
                rc = fab.main(["--dry"])
                self.assertEqual(rc, 0)
                self.assertFalse(os.path.exists(fab.MNO_PATH))
                self.assertFalse(os.path.exists(fab.REG_PATH))
            finally:
                fab.MNO_PATH, fab.REG_PATH = old_mno, old_reg
        self.assertTrue(os.path.isdir(here))


if __name__ == "__main__":
    unittest.main()
