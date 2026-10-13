#!/usr/bin/env python3
"""Structural tests for muhl_fab_pdap. Does not evaluate the organ."""
import hashlib
import os
import struct
import tempfile
import unittest

import muhl_fab_pdap as fab


class TestPdapFab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.meta, cls.stored = fab.fabricate(0)
        fab.verify_physical(cls.blob, cls.meta, cls.stored)

    def test_header_matches_mha_layout(self):
        self.assertEqual(self.blob[:8], b"MUHLPDAP")
        ng, nw, ni, no, dp = struct.unpack_from("<IIIII", self.blob, 8)
        self.assertEqual((ng, nw, ni, no, dp), (2656, 2690, 32, 32, 192))
        self.assertEqual(self.meta["len"], 28 + 32 * 8 + 2690 + 2656 * 25)

    def test_one_writer_per_out(self):
        outs = [g[3] for g in self.stored]
        self.assertEqual(len(outs), 2656)
        self.assertEqual(len(set(outs)), 2656)

    def test_self_clock_state_out_is_state_in(self):
        self.assertEqual(self.meta["input_addrs"], self.meta["output_addrs"])
        self.assertEqual(len(set(self.meta["input_addrs"])), 32)

    def test_ops_per_step_split(self):
        for step in range(32):
            chunk = self.stored[step * 83:(step + 1) * 83]
            ops = [g[0] for g in chunk]
            self.assertEqual(ops[:3], [fab.OP_NOT, fab.OP_NOT, fab.OP_NOT])
            self.assertEqual(ops.count(fab.OP_AND), 52)
            self.assertEqual(ops.count(fab.OP_OR), 28)
            self.assertTrue(all(op in (0, 1, 2, 3, 4) for op in ops))

    def test_plumb_arithmetic(self):
        self.assertEqual(32 * 83, 2656)
        self.assertEqual(19 + 60 + 4, 83)

    def test_deterministic(self):
        blob2, meta2, _ = fab.fabricate(0)
        self.assertEqual(self.blob, blob2)
        self.assertEqual(self.meta["sha256"], meta2["sha256"])
        self.assertEqual(self.meta["sha256"], hashlib.sha256(self.blob).hexdigest())

    def test_dry_does_not_write(self):
        here = os.path.dirname(os.path.abspath(fab.__file__))
        with tempfile.TemporaryDirectory() as tmp:
            old_mno, old_reg = fab.MNO_PATH, fab.REG_PATH
            fab.MNO_PATH = os.path.join(tmp, "muhl_pdap.mno")
            fab.REG_PATH = os.path.join(tmp, "pdap_circuits.json")
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
