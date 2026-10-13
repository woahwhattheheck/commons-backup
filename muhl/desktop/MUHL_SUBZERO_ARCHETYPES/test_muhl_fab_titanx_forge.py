#!/usr/bin/env python3
"""Structural tests for organ 29. Does not evaluate the organ."""
import hashlib
import os
import struct
import tempfile
import unittest

import muhl_fab_titanx_forge as fab


class TestTitanxForgeFab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.meta, cls.stored = fab.fabricate(0)
        fab.verify_physical(cls.blob, cls.meta, cls.stored)

    def test_header_matches_mha_layout(self):
        self.assertEqual(self.blob[:8], b"MUHLTITF")
        header = struct.unpack_from("<IIIII", self.blob, 8)
        self.assertEqual(header, (180, 182, 90, 90, 2))
        self.assertEqual(self.meta["len"], 28 + 90 * 8 + 182 + 180 * 25)

    def test_one_writer_per_gate_output(self):
        outputs = [record[3] for record in self.stored]
        self.assertEqual(len(outputs), 180)
        self.assertEqual(len(set(outputs)), 180)

    def test_self_clock(self):
        self.assertEqual(self.meta["input_addrs"], self.meta["output_addrs"])

    def test_dest_from_file(self):
        dests = self.meta["dests"]
        hops = {hop["name"]: hop for hop in dests["hops"]}
        self.assertEqual(len(dests["src_addrs"]), 90)
        self.assertEqual(hops["lvin_ispn"]["src_addrs"], list(range(542, 574)))
        self.assertEqual(hops["lvin_ispn"]["dst_addrs"], list(range(2078, 2110)))
        self.assertEqual(hops["socr_nefg"]["dst_addrs"], list(range(93709716802, 93709716810)))
        self.assertEqual(hops["nefg_dmb"]["dst_addrs"], list(range(93709782658, 93709782666)))
        self.assertEqual(hops["petr_dmb"]["dst_addrs"], [93709782666, 93709782667])
        used_dmb = hops["nefg_dmb"]["dst_addrs"] + hops["petr_dmb"]["dst_addrs"]
        self.assertEqual(used_dmb, list(range(93709782658, 93709782668)))

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
            fab.MNO_PATH = os.path.join(tmp, "muhl_titanx_forge.mno")
            fab.REG_PATH = os.path.join(tmp, "titanx_forge_circuits.json")
            try:
                self.assertEqual(fab.main(["--dry"]), 0)
                self.assertFalse(os.path.exists(fab.MNO_PATH))
            finally:
                fab.MNO_PATH, fab.REG_PATH = old_mno, old_reg


if __name__ == "__main__":
    unittest.main()
