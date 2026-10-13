#!/usr/bin/env python3
"""Structural tests for organ 25. Does not evaluate the organ."""
import hashlib
import os
import struct
import tempfile
import unittest

import muhl_fab_chimera_flow_stig as fab


class TestChimeraFlowStigFab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.meta, cls.stored = fab.fabricate(0)
        fab.verify_physical(cls.blob, cls.meta, cls.stored)

    def test_header_matches_mha_layout(self):
        self.assertEqual(self.blob[:8], b"MUHLCHFS")
        self.assertEqual(struct.unpack_from("<IIIII", self.blob, 8), (18, 20, 9, 9, 2))
        self.assertEqual(self.meta["len"], 28 + 9 * 8 + 20 + 18 * 25)

    def test_exact_plumb_gate_arithmetic(self):
        self.assertEqual(len(self.stored), 18)
        self.assertEqual([row[0] for row in self.stored], [fab.OP_NAND] * 18)
        self.assertEqual(len(set(row[3] for row in self.stored)), 18)

    def test_self_clock_and_dests(self):
        self.assertEqual(self.meta["input_addrs"], self.meta["output_addrs"])
        dests = self.meta["dests"]
        self.assertEqual(dests["src_addrs"], list(range(16414, 16423)))
        self.assertEqual(dests["dst_addrs"], list(range(6174, 6183)))
        self.assertEqual(dests["flow_sha256"],
                         "8530b99896e8ec35d74d462f600448aa60e64f9f4cd8833b561666d50eb1e97d")

    def test_depth_and_dry(self):
        records, rates = fab.build_gates()
        depths = {wire: 0 for wire in range(fab.W_COND0 + fab.N_IN)}
        for _op, a, b, out in records:
            depths[out] = max(depths[a], depths[b]) + 1
        self.assertEqual(max(depths[out] for out in rates), 2)
        blob2, meta2, _stored = fab.fabricate(0)
        self.assertEqual(self.blob, blob2)
        self.assertEqual(self.meta["sha256"], hashlib.sha256(self.blob).hexdigest())
        with tempfile.TemporaryDirectory() as tmp:
            old_mno, old_reg = fab.MNO_PATH, fab.REG_PATH
            fab.MNO_PATH = os.path.join(tmp, "x.mno")
            fab.REG_PATH = os.path.join(tmp, "x.json")
            try:
                self.assertEqual(fab.main(["--dry"]), 0)
                self.assertFalse(os.path.exists(fab.MNO_PATH))
            finally:
                fab.MNO_PATH, fab.REG_PATH = old_mno, old_reg


if __name__ == "__main__":
    unittest.main()
