#!/usr/bin/env python3
"""Structural tests for muhl_fab_lvin. Does not evaluate the organ."""
import hashlib
import os
import struct
import tempfile
import unittest

import muhl_fab_lvin as fab


class TestLvinFab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.meta, cls.stored = fab.fabricate(0)
        fab.verify_physical(cls.blob, cls.meta, cls.stored)

    def test_header_matches_mha_layout(self):
        self.assertEqual(self.blob[:8], b"MUHLLVIN")
        ng, nw, ni, no, dp = struct.unpack_from("<IIIII", self.blob, 8)
        self.assertEqual((ng, nw, ni, no, dp), (2368, 2510, 64, 64, 30))
        self.assertEqual(self.meta["len"], 28 + 64 * 8 + 2510 + 2368 * 25)

    def test_one_writer_per_out(self):
        outs = [g[3] for g in self.stored]
        self.assertEqual(len(outs), 2368)
        self.assertEqual(len(set(outs)), 2368)

    def test_self_clock_tape_out_is_tape_in(self):
        self.assertEqual(self.meta["input_addrs"], self.meta["output_addrs"])
        self.assertEqual(len(set(self.meta["input_addrs"])), 64)

    def test_control_latch_and_counter_split(self):
        ctrl = self.stored[:151]
        self.assertEqual(len(ctrl), 151)
        self.assertEqual([g[0] for g in ctrl].count(fab.OP_NOT), 7)
        self.assertEqual(len(self.stored[:2048]), 2048)
        fa = self.stored[2048:]
        self.assertEqual(len(fa), 320)
        self.assertEqual([g[0] for g in fa].count(fab.OP_XOR), 128)
        self.assertEqual([g[0] for g in fa].count(fab.OP_AND), 128)
        self.assertEqual([g[0] for g in fa].count(fab.OP_OR), 64)

    def test_deterministic(self):
        blob2, meta2, _ = fab.fabricate(0)
        self.assertEqual(self.blob, blob2)
        self.assertEqual(self.meta["sha256"], meta2["sha256"])
        self.assertEqual(self.meta["sha256"], hashlib.sha256(self.blob).hexdigest())

    def test_dry_does_not_write(self):
        here = os.path.dirname(os.path.abspath(fab.__file__))
        with tempfile.TemporaryDirectory() as tmp:
            old_mno, old_reg = fab.MNO_PATH, fab.REG_PATH
            fab.MNO_PATH = os.path.join(tmp, "muhl_lvin.mno")
            fab.REG_PATH = os.path.join(tmp, "lvin_circuits.json")
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
