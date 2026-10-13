#!/usr/bin/env python3
"""Structural tests for organ 31. Does not evaluate the organ."""
import hashlib
import os
import struct
import tempfile
import unittest

import muhl_fab_titanx_commons as fab


class TestTitanxCommonsFab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.meta, cls.stored = fab.fabricate(0)
        fab.verify_physical(cls.blob, cls.meta, cls.stored)

    def test_header_matches_mha_layout(self):
        self.assertEqual(self.blob[:8], b"MUHLTITX")
        header = struct.unpack_from("<IIIII", self.blob, 8)
        self.assertEqual(header, (600, 602, 300, 300, 2))
        self.assertEqual(self.meta["len"], 28 + 300 * 8 + 602 + 600 * 25)

    def test_one_writer_per_gate_output(self):
        outputs = [record[3] for record in self.stored]
        self.assertEqual(len(outputs), 600)
        self.assertEqual(len(set(outputs)), 600)

    def test_self_clock(self):
        self.assertEqual(self.meta["input_addrs"], self.meta["output_addrs"])

    def test_dest_from_file(self):
        dests = self.meta["dests"]
        hops = {hop["name"]: hop for hop in dests["hops"]}
        self.assertEqual(len(dests["src_addrs"]), 300)
        self.assertEqual(hops["hdvs_identity"]["src_addrs"][:3], [10274, 10279, 10284])
        self.assertEqual(hops["immn_nonself"]["src_addrs"], [29636])
        self.assertEqual(hops["hopf_memory"]["src_addrs"], list(range(542, 558)))
        self.assertEqual(hops["pdap_envelope"]["src_addrs"], list(range(286, 302)))
        self.assertEqual(hops["flow_thread"]["src_addrs"], list(range(16414, 16446)))
        self.assertEqual(hops["vscf_court"]["src_addrs"], list(range(93709728614, 93709728630)))
        self.assertEqual(hops["dmb_bloom"]["src_addrs"], list(range(93709782657, 93709782667)))
        self.assertEqual(len(hops), 26)

    def test_door_stays_open(self):
        hops = {hop["name"]: hop for hop in self.meta["dests"]["hops"]}
        self.assertEqual(hops["immn_nonself"]["lanes"], 1)
        self.assertEqual(hops["immn_nonself"]["src_organ"], "muhl_immn")

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
            self.assertNotEqual(blob[:8], b"MUHLTITX")

    def test_dry_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_mno, old_reg = fab.MNO_PATH, fab.REG_PATH
            fab.MNO_PATH = os.path.join(tmp, "muhl_titanx_commons.mno")
            fab.REG_PATH = os.path.join(tmp, "titanx_commons_circuits.json")
            try:
                self.assertEqual(fab.main(["--dry"]), 0)
                self.assertFalse(os.path.exists(fab.MNO_PATH))
            finally:
                fab.MNO_PATH, fab.REG_PATH = old_mno, old_reg


if __name__ == "__main__":
    unittest.main()
