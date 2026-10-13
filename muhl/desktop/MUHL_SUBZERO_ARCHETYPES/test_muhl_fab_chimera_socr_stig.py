#!/usr/bin/env python3
"""Structural tests for organ 24. Does not evaluate the organ."""
import hashlib
import os
import struct
import tempfile
import unittest

import muhl_fab_chimera_socr_stig as fab


class TestChimeraSocrStigFab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.meta, cls.stored = fab.fabricate(0)
        fab.verify_physical(cls.blob, cls.meta, cls.stored)

    def test_header_matches_mha_layout(self):
        self.assertEqual(self.blob[:8], b"MUHLCHSS")
        header = struct.unpack_from("<IIIII", self.blob, 8)
        self.assertEqual(header, (18, 20, 9, 9, 2))
        self.assertEqual(self.meta["len"], 28 + 9 * 8 + 20 + 18 * 25)

    def test_exact_plumb_gate_arithmetic(self):
        self.assertEqual(len(self.stored), 9 * 2)
        ops = [record[0] for record in self.stored]
        self.assertEqual(ops, [fab.OP_NAND] * 18)

    def test_one_writer_per_gate_output(self):
        outputs = [record[3] for record in self.stored]
        self.assertEqual(len(outputs), 18)
        self.assertEqual(len(set(outputs)), 18)

    def test_self_clock_deposit_out_is_avalanche_in(self):
        self.assertEqual(self.meta["input_addrs"], self.meta["output_addrs"])
        self.assertEqual(len(set(self.meta["input_addrs"])), 9)

    def test_dest_from_file(self):
        dests = self.meta["dests"]
        self.assertEqual(dests["src_organ"], "muhl_socr")
        self.assertEqual(dests["dst_organ"], "muhl_stig")
        self.assertEqual(dests["src_addrs"][0], 7002)
        self.assertEqual(dests["src_addrs"], [7002 + 62 * i for i in range(9)])
        self.assertEqual(dests["dst_addrs"], [6174 + 3 * i for i in range(9)])

    def test_declared_depth_matches_gate_dag(self):
        records, deposits = fab.build_gates()
        depths = {wire: 0 for wire in range(fab.W_AV0 + fab.N_IN)}
        for _op, a, b, out in records:
            self.assertIn(a, depths)
            self.assertIn(b, depths)
            depths[out] = max(depths[a], depths[b]) + 1
        self.assertEqual(max(depths.values()), 2)
        self.assertEqual(max(depths[out] for out in deposits), 2)

    def test_deterministic(self):
        blob2, meta2, _stored = fab.fabricate(0)
        self.assertEqual(self.blob, blob2)
        self.assertEqual(self.meta["sha256"], meta2["sha256"])
        self.assertEqual(self.meta["sha256"], hashlib.sha256(self.blob).hexdigest())

    def test_dry_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_mno, old_reg = fab.MNO_PATH, fab.REG_PATH
            fab.MNO_PATH = os.path.join(tmp, "muhl_chimera_socr_stig.mno")
            fab.REG_PATH = os.path.join(tmp, "chimera_socr_stig_circuits.json")
            try:
                self.assertEqual(fab.main(["--dry"]), 0)
                self.assertFalse(os.path.exists(fab.MNO_PATH))
                self.assertFalse(os.path.exists(fab.REG_PATH))
            finally:
                fab.MNO_PATH, fab.REG_PATH = old_mno, old_reg


if __name__ == "__main__":
    unittest.main()
