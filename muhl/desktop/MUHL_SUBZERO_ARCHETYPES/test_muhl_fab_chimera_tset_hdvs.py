#!/usr/bin/env python3
"""Structural tests for organ 22. Does not evaluate the organ."""
import hashlib
import os
import struct
import tempfile
import unittest

import muhl_fab_chimera_tset_hdvs as fab


class TestChimeraTsetHdvsFab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.meta, cls.stored = fab.fabricate(0)
        fab.verify_physical(cls.blob, cls.meta, cls.stored)

    def test_header_matches_mha_layout(self):
        self.assertEqual(self.blob[:8], b"MUHLCHTH")
        header = struct.unpack_from("<IIIII", self.blob, 8)
        self.assertEqual(header, (24, 26, 12, 12, 2))
        self.assertEqual(self.meta["len"], 28 + 12 * 8 + 26 + 24 * 25)

    def test_exact_plumb_gate_arithmetic(self):
        self.assertEqual(len(self.stored), 12 * 2)
        ops = [record[0] for record in self.stored]
        self.assertEqual(ops, [fab.OP_NAND] * 24)

    def test_one_writer_per_gate_output(self):
        outputs = [record[3] for record in self.stored]
        self.assertEqual(len(outputs), 24)
        self.assertEqual(len(set(outputs)), 24)

    def test_self_clock_bind_out_is_clause_in(self):
        self.assertEqual(self.meta["input_addrs"], self.meta["output_addrs"])
        self.assertEqual(len(set(self.meta["input_addrs"])), 12)

    def test_dest_from_file(self):
        dests = self.meta["dests"]
        self.assertEqual(dests["src_organ"], "muhl_tset")
        self.assertEqual(dests["dst_organ"], "muhl_hdvs")
        self.assertEqual(dests["src_addrs"][0], 4260)
        self.assertEqual(dests["src_addrs"], [
            4260, 4355, 4450, 4545, 4640, 4735,
            4830, 4925, 5020, 5115, 5210, 5305,
        ])
        self.assertEqual(dests["dst_addrs"], list(range(9246, 9258)))
        self.assertEqual(len(dests["src_addrs"]), 12)

    def test_declared_depth_matches_gate_dag(self):
        records, binds = fab.build_gates()
        depths = {wire: 0 for wire in range(fab.W_CLAUSE0 + fab.N_IN)}
        for _op, a, b, out in records:
            self.assertIn(a, depths)
            self.assertIn(b, depths)
            depths[out] = max(depths[a], depths[b]) + 1
        self.assertEqual(max(depths.values()), 2)
        self.assertEqual(max(depths[out] for out in binds), 2)

    def test_deterministic(self):
        blob2, meta2, _stored = fab.fabricate(0)
        self.assertEqual(self.blob, blob2)
        self.assertEqual(self.meta["sha256"], meta2["sha256"])
        self.assertEqual(self.meta["sha256"], hashlib.sha256(self.blob).hexdigest())

    def test_dry_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_mno, old_reg = fab.MNO_PATH, fab.REG_PATH
            fab.MNO_PATH = os.path.join(tmp, "muhl_chimera_tset_hdvs.mno")
            fab.REG_PATH = os.path.join(tmp, "chimera_tset_hdvs_circuits.json")
            try:
                self.assertEqual(fab.main(["--dry"]), 0)
                self.assertFalse(os.path.exists(fab.MNO_PATH))
                self.assertFalse(os.path.exists(fab.REG_PATH))
            finally:
                fab.MNO_PATH, fab.REG_PATH = old_mno, old_reg


if __name__ == "__main__":
    unittest.main()
