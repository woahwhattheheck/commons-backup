#!/usr/bin/env python3
"""Structural tests for muhl_fab_synd; never evaluates the organ."""
import hashlib
import os
import struct
import tempfile
import unittest

import muhl_fab_synd as fab


class TestSyndFab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.meta, cls.stored = fab.fabricate(0)
        fab.verify_physical(cls.blob, cls.meta, cls.stored)

    def test_header_matches_live_layout(self):
        self.assertEqual(self.blob[:8], b"MUHLSYND")
        header = struct.unpack_from("<IIIII", self.blob, 8)
        self.assertEqual(header, (27520, 27778, 256, 256, 45))
        self.assertEqual(self.meta["len"], 28 + 256 * 8 + 27778 + 27520 * 25)

    def test_exact_plumb_gate_arithmetic(self):
        self.assertEqual(len(self.stored), 640 + 11520 + 15360)
        syn = self.stored[:640]
        self.assertEqual([record[0] for record in syn].count(fab.OP_XOR), 640)
        # Emission is 3 iterations of 128 CN then 256 VN, not all CN first.
        cursor = 640
        for it in range(3):
            cn = self.stored[cursor:cursor + 128 * 30]
            cursor += 128 * 30
            vn = self.stored[cursor:cursor + 256 * 20]
            cursor += 256 * 20
            self.assertEqual(len(cn), 3840)
            self.assertEqual(len(vn), 5120)
            for block in range(128):
                chunk = cn[block * 30:(block + 1) * 30]
                ops = [record[0] for record in chunk]
                self.assertEqual(len(chunk), 30)
                self.assertEqual(ops.count(fab.OP_XOR), 11)
                self.assertEqual(ops.count(fab.OP_AND), 18)
                self.assertEqual(ops.count(fab.OP_OR), 1)
            for var in range(256):
                chunk = vn[var * 20:(var + 1) * 20]
                self.assertEqual(len(chunk), 20)
        self.assertEqual(cursor, len(self.stored))

    def test_one_writer_per_gate_output(self):
        outputs = [record[3] for record in self.stored]
        self.assertEqual(len(outputs), 27520)
        self.assertEqual(len(set(outputs)), 27520)

    def test_physical_edges_precede_reads_and_codeword_writes_are_terminal(self):
        base = self.meta["base_off"]
        initial = {fab.wa(base, wire) for wire in range(fab.W_VAR0 + fab.N_IN)}
        marking = set(self.meta["input_addrs"])
        readable = set(initial)
        written_marking = set()
        for _op, a, b, out in self.stored:
            self.assertIn(a, readable)
            self.assertIn(b, readable)
            self.assertNotIn(a, written_marking)
            self.assertNotIn(b, written_marking)
            if out in marking:
                written_marking.add(out)
            else:
                readable.add(out)
        self.assertEqual(written_marking, marking)

    def test_declared_depth_matches_gate_dag(self):
        records, roots, _syndromes, _tanner = fab.build_gates()
        depths = {wire: 0 for wire in range(fab.W_VAR0 + fab.N_IN)}
        max_depth = 0
        for _op, a, b, out in records:
            self.assertIn(a, depths)
            self.assertIn(b, depths)
            depths[out] = max(depths[a], depths[b]) + 1
            max_depth = max(max_depth, depths[out])
        self.assertEqual(max_depth, 45)
        self.assertLessEqual(max(depths[root] for root in roots), 45)

    def test_self_clocked_codeword(self):
        self.assertEqual(self.meta["output_addrs"], self.meta["input_addrs"])
        self.assertEqual(len(self.meta["input_addrs"]), 256)
        self.assertEqual(len(set(self.meta["input_addrs"])), 256)

    def test_tanner_is_regular_36(self):
        degrees = [0] * 256
        for check in range(128):
            owned = fab.check_vars(check)
            self.assertEqual(len(set(owned)), 6)
            self.assertEqual(self.meta["tanner"]["checks"][check], list(owned))
            for var in owned:
                degrees[var] += 1
                self.assertIn(check, fab.var_checks(var))
        self.assertEqual(degrees, [3] * 256)

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
            fab.MNO_PATH = os.path.join(tmp, "muhl_synd.mno")
            fab.REG_PATH = os.path.join(tmp, "synd_circuits.json")
            try:
                self.assertEqual(fab.main(["--dry"]), 0)
                self.assertFalse(os.path.exists(fab.MNO_PATH))
                self.assertFalse(os.path.exists(fab.REG_PATH))
            finally:
                fab.MNO_PATH, fab.REG_PATH, fab.EXCERPT_DIR = old_mno, old_reg, old_dir


if __name__ == "__main__":
    unittest.main()
