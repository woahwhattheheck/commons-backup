#!/usr/bin/env python3
"""Structural tests for muhl_fab_rgcg. Does not walk the organ as inference."""
import hashlib
import os
import struct
import tempfile
import unittest

import muhl_fab_rgcg as fab


class TestRgcgFab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.meta, cls.stored = fab.fabricate(0)
        fab.verify_physical(cls.blob, cls.meta, cls.stored)

    def test_header_matches_mha_layout(self):
        self.assertEqual(self.blob[:8], b"MUHLRGCG")
        ng, nw, ni, no, dp = struct.unpack_from("<IIIII", self.blob, 8)
        self.assertEqual((ng, nw, ni, no, dp), (7820, 8846, 1024, 4, 32))
        self.assertEqual(self.meta["len"], 28 + 4 * 8 + 8846 + 7820 * 25)

    def test_one_writer_per_out(self):
        outs = [g[3] for g in self.stored]
        self.assertEqual(len(outs), 7820)
        self.assertEqual(len(set(outs)), 7820)

    def test_plumb_arithmetic(self):
        self.assertEqual(256 + 64 + 16 + 4, 340)
        self.assertEqual(20 + 3, 23)
        self.assertEqual(340 * 23, 7820)

    def test_ops_per_block(self):
        for block in range(340):
            chunk = self.stored[block * 23:(block + 1) * 23]
            ops = [g[0] for g in chunk]
            self.assertEqual(ops.count(fab.OP_XOR), 8)
            self.assertEqual(ops.count(fab.OP_AND), 9)
            self.assertEqual(ops.count(fab.OP_OR), 6)

    def test_four_result_bits(self):
        self.assertEqual(len(self.meta["output_addrs"]), 4)
        self.assertEqual(len(set(self.meta["output_addrs"])), 4)

    def test_deterministic(self):
        blob2, meta2, _ = fab.fabricate(0)
        self.assertEqual(self.blob, blob2)
        self.assertEqual(self.meta["sha256"], meta2["sha256"])
        self.assertEqual(self.meta["sha256"], hashlib.sha256(self.blob).hexdigest())

    def test_dry_does_not_write(self):
        here = os.path.dirname(os.path.abspath(fab.__file__))
        with tempfile.TemporaryDirectory() as tmp:
            old_mno, old_reg = fab.MNO_PATH, fab.REG_PATH
            fab.MNO_PATH = os.path.join(tmp, "muhl_rgcg.mno")
            fab.REG_PATH = os.path.join(tmp, "rgcg_circuits.json")
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
