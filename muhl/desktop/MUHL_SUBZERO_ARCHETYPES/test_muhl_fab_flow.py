"""Structural tests for muhl_fab_flow. Does not walk the organ as inference."""
import hashlib
import os
import struct
import tempfile
import unittest

import muhl_fab_flow as fab


class TestFlowFab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.meta, cls.stored = fab.fabricate(0)
        fab.verify_physical(cls.blob, cls.meta, cls.stored)

    def test_header_matches_mha_layout(self):
        self.assertEqual(self.blob[:8], b"MUHLFLOW")
        header = struct.unpack_from("<IIIII", self.blob, 8)
        self.assertEqual(header, (23040, 25090, 2048, 2048, 16))
        self.assertEqual(self.meta["len"], 28 + 2048 * 8 + 25090 + 23040 * 25)

    def test_exact_plumb_gate_arithmetic(self):
        self.assertEqual(512 * 45, 23040)
        self.assertEqual(20 + 5 + 20, 45)
        self.assertEqual(len(self.stored), 23040)

    def test_one_writer_per_gate_output(self):
        outputs = [record[3] for record in self.stored]
        self.assertEqual(len(outputs), 23040)
        self.assertEqual(len(set(outputs)), 23040)

    def test_self_clock_conductance_out_is_conductance_in(self):
        self.assertEqual(self.meta["input_addrs"], self.meta["output_addrs"])
        self.assertEqual(len(set(self.meta["input_addrs"])), 2048)

    def test_declared_depth_matches_gate_dag(self):
        records, next_cond = fab.build_gates()
        depths = {wire: 0 for wire in range(fab.W_C0 + fab.N_IN)}
        max_depth = 0
        for _op, a, b, out in records:
            self.assertIn(a, depths)
            self.assertIn(b, depths)
            depths[out] = max(depths[a], depths[b]) + 1
            max_depth = max(max_depth, depths[out])
        self.assertEqual(max_depth, 16)
        for edge in range(512):
            self.assertEqual(depths[next_cond[edge * 4 + 3]], 16)

    def test_pairs_are_east_south_at_the_same_cell(self):
        self.assertEqual(fab.pair_edge(0), 256)
        self.assertEqual(fab.pair_edge(256), 0)
        self.assertEqual(fab.pair_edge(255), 511)
        self.assertEqual(fab.pair_edge(511), 255)
        for edge in range(512):
            self.assertEqual(fab.pair_edge(fab.pair_edge(edge)), edge)
            self.assertNotEqual(fab.pair_edge(edge), edge)

    def test_deterministic_bytes(self):
        blob2, meta2, stored2 = fab.fabricate(0)
        self.assertEqual(self.blob, blob2)
        self.assertEqual(self.stored, stored2)
        self.assertEqual(self.meta["sha256"], meta2["sha256"])
        self.assertEqual(self.meta["sha256"], hashlib.sha256(self.blob).hexdigest())

    def test_dry_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_mno, old_reg, old_dir = fab.MNO_PATH, fab.REG_PATH, fab.EXCERPT_DIR
            fab.EXCERPT_DIR = tmp
            fab.MNO_PATH = os.path.join(tmp, "muhl_flow.mno")
            fab.REG_PATH = os.path.join(tmp, "flow_circuits.json")
            try:
                self.assertEqual(fab.main(["--dry"]), 0)
                self.assertFalse(os.path.exists(fab.MNO_PATH))
                self.assertFalse(os.path.exists(fab.REG_PATH))
            finally:
                fab.MNO_PATH, fab.REG_PATH, fab.EXCERPT_DIR = old_mno, old_reg, old_dir


if __name__ == "__main__":
    unittest.main()
