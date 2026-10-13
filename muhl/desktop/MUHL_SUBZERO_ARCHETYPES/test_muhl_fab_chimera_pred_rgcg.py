#!/usr/bin/env python3
"""Structural tests for organ 27. Does not evaluate the organ."""
import hashlib
import os
import struct
import tempfile
import unittest

import muhl_fab_chimera_pred_rgcg as fab


class TestChimeraPredRgcgFab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.meta, cls.stored = fab.fabricate(0)
        fab.verify_physical(cls.blob, cls.meta, cls.stored)

    def test_header_matches_mha_layout(self):
        self.assertEqual(self.blob[:8], b"MUHLCHPR")
        header = struct.unpack_from("<IIIII", self.blob, 8)
        self.assertEqual(header, (24, 26, 12, 12, 2))
        self.assertEqual(self.meta["len"], 28 + 12 * 8 + 26 + 24 * 25)

    def test_one_writer_per_gate_output(self):
        outputs = [record[3] for record in self.stored]
        self.assertEqual(len(outputs), 24)
        self.assertEqual(len(set(outputs)), 24)

    def test_self_clock(self):
        self.assertEqual(self.meta["input_addrs"], self.meta["output_addrs"])

    def test_dest_from_file(self):
        dests = self.meta["dests"]
        self.assertEqual(dests["src_organ"], "muhl_pred")
        self.assertEqual(dests["dst_organ"], "muhl_rgcg")
        self.assertEqual(dests["src_addrs"], list(range(3102, 3114)))
        self.assertEqual(dests["dst_addrs"], list(range(62, 74)))

    def test_declared_depth_matches_gate_dag(self):
        records = fab.build_gates()
        depths = {wire: 0 for wire in range(fab.N_WIRES)}
        for _op, a, b, out in records:
            depths[out] = max(depths[a], depths[b]) + 1
        self.assertEqual(max(depths.values()), 2)

    def test_deterministic(self):
        blob2, meta2, _stored = fab.fabricate(0)
        self.assertEqual(self.blob, blob2)
        self.assertEqual(self.meta["sha256"], hashlib.sha256(self.blob).hexdigest())
        self.assertEqual(self.meta["sha256"], meta2["sha256"])

    def test_dry_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_mno, old_reg = fab.MNO_PATH, fab.REG_PATH
            fab.MNO_PATH = os.path.join(tmp, "muhl_chimera_pred_rgcg.mno")
            fab.REG_PATH = os.path.join(tmp, "chimera_pred_rgcg_circuits.json")
            try:
                self.assertEqual(fab.main(["--dry"]), 0)
                self.assertFalse(os.path.exists(fab.MNO_PATH))
            finally:
                fab.MNO_PATH, fab.REG_PATH = old_mno, old_reg


if __name__ == "__main__":
    unittest.main()
