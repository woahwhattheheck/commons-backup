#!/usr/bin/env python3
"""Structural tests for organ 30. Does not evaluate the organ."""
import hashlib
import os
import struct
import tempfile
import unittest

import muhl_fab_titanx_mirror as fab


class TestTitanxMirrorFab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.meta, cls.stored = fab.fabricate(0)
        fab.verify_physical(cls.blob, cls.meta, cls.stored)

    def test_header_matches_mha_layout(self):
        self.assertEqual(self.blob[:8], b"MUHLTITM")
        header = struct.unpack_from("<IIIII", self.blob, 8)
        self.assertEqual(header, (240, 242, 120, 120, 2))
        self.assertEqual(self.meta["len"], 28 + 120 * 8 + 242 + 240 * 25)

    def test_one_writer_per_gate_output(self):
        outputs = [record[3] for record in self.stored]
        self.assertEqual(len(outputs), 240)
        self.assertEqual(len(set(outputs)), 240)

    def test_self_clock(self):
        self.assertEqual(self.meta["input_addrs"], self.meta["output_addrs"])

    def test_dest_from_file(self):
        dests = self.meta["dests"]
        hops = {hop["name"]: hop for hop in dests["hops"]}
        self.assertEqual(len(dests["src_addrs"]), 120)
        self.assertEqual(hops["pred_surprise"]["src_addrs"], list(range(3102, 3134)))
        self.assertEqual(
            hops["hpc_fabric_surprise"]["src_addrs"],
            list(range(103788450894, 103788450922)),
        )
        self.assertEqual(hops["immn_surprise"]["src_addrs"], [29636])
        self.assertEqual(hops["hdvs_surprise"]["src_addrs"][:3], [10274, 10279, 10284])
        self.assertEqual(hops["sdmk_surprise"]["src_addrs"][:3], [1188, 1963, 2738])
        self.assertEqual(hops["rookery_witness_surprise"]["src_addrs"], list(range(256, 267)))

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

    def test_does_not_remint_landed_organs(self):
        for name, spec in fab.LANDED.items():
            with open(spec["mno"], "rb") as handle:
                blob = handle.read()
            self.assertEqual(blob[:8], spec["magic"], name)
            self.assertNotEqual(blob[:8], b"MUHLTITM")

    def test_dry_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_mno, old_reg = fab.MNO_PATH, fab.REG_PATH
            fab.MNO_PATH = os.path.join(tmp, "muhl_titanx_mirror.mno")
            fab.REG_PATH = os.path.join(tmp, "titanx_mirror_circuits.json")
            try:
                self.assertEqual(fab.main(["--dry"]), 0)
                self.assertFalse(os.path.exists(fab.MNO_PATH))
            finally:
                fab.MNO_PATH, fab.REG_PATH = old_mno, old_reg


if __name__ == "__main__":
    unittest.main()
