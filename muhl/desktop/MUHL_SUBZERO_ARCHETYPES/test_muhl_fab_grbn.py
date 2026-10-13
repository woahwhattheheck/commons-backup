#!/usr/bin/env python3
"""Structural tests for muhl_fab_grbn. Does not evaluate the organ."""
import hashlib
import os
import struct
import tempfile
import unittest

import muhl_fab_grbn as fab


class TestGrbnFab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.meta, cls.stored = fab.fabricate(0)
        fab.verify_physical(cls.blob, cls.meta, cls.stored)

    def test_header_matches_mha_layout(self):
        self.assertEqual(self.blob[:8], b"MUHLGRBN")
        ng, nw, ni, no, dp = struct.unpack_from("<IIIII", self.blob, 8)
        self.assertEqual((ng, nw, ni, no, dp), (8704, 8962, 256, 256, 7))
        self.assertEqual(self.meta["len"], 28 + 256 * 8 + 8962 + 8704 * 25)

    def test_one_writer_per_out(self):
        outs = [g[3] for g in self.stored]
        self.assertEqual(len(outs), 8704)
        self.assertEqual(len(set(outs)), 8704)

    def test_self_clock_state_out_is_state_in(self):
        self.assertEqual(self.meta["input_addrs"], self.meta["output_addrs"])
        self.assertEqual(len(set(self.meta["input_addrs"])), 256)

    def test_ops_and_per_node_split(self):
        for node in range(256):
            chunk = self.stored[node * 34:(node + 1) * 34]
            ops = [g[0] for g in chunk]
            self.assertEqual(ops[:3], [fab.OP_NOT, fab.OP_NOT, fab.OP_NOT])
            self.assertEqual(ops.count(fab.OP_AND), 24)
            self.assertEqual(ops.count(fab.OP_OR), 7)
            self.assertTrue(all(op in (0, 1, 2, 3, 4) for op in ops))

    def test_nk_sources_distinct(self):
        for node in range(256):
            src = fab.sources(node)
            self.assertEqual(len(src), 3)
            self.assertEqual(len(set(src)), 3)
            self.assertNotIn(node, src)

    def test_deterministic(self):
        blob2, meta2, _ = fab.fabricate(0)
        self.assertEqual(self.blob, blob2)
        self.assertEqual(self.meta["sha256"], meta2["sha256"])
        self.assertEqual(self.meta["sha256"], hashlib.sha256(self.blob).hexdigest())

    def test_dry_does_not_write(self):
        here = os.path.dirname(os.path.abspath(fab.__file__))
        with tempfile.TemporaryDirectory() as tmp:
            old_mno, old_reg = fab.MNO_PATH, fab.REG_PATH
            fab.MNO_PATH = os.path.join(tmp, "muhl_grbn.mno")
            fab.REG_PATH = os.path.join(tmp, "grbn_circuits.json")
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
