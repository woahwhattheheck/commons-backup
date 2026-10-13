#!/usr/bin/env python3
"""Structural tests for muhl_fab_petr; never evaluates the organ."""
import hashlib
import os
import struct
import tempfile
import unittest

import muhl_fab_petr as fab


class TestPetrFab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.meta, cls.stored = fab.fabricate(0)
        fab.verify_physical(cls.blob, cls.meta, cls.stored)

    def test_header_matches_live_layout(self):
        self.assertEqual(self.blob[:8], b"MUHLPETR")
        header = struct.unpack_from("<IIIII", self.blob, 8)
        self.assertEqual(header, (3552, 3810, 256, 256, 14))
        self.assertEqual(self.meta["len"], 28 + 256 * 8 + 3810 + 3552 * 25)

    def test_exact_plumb_gate_arithmetic(self):
        self.assertEqual(len(self.stored), 32 * 111)
        for transition in range(32):
            chunk = self.stored[transition * 111 : (transition + 1) * 111]
            ops = [record[0] for record in chunk]
            self.assertEqual(len(chunk), 11 + 3 * 20 + 2 * 20)
            self.assertEqual(ops.count(fab.OP_OR), 29)
            self.assertEqual(ops.count(fab.OP_AND), 42)
            self.assertEqual(ops.count(fab.OP_XOR), 40)

    def test_one_writer_per_gate_output(self):
        outputs = [record[3] for record in self.stored]
        self.assertEqual(len(outputs), 3552)
        self.assertEqual(len(set(outputs)), 3552)

    def test_physical_edges_precede_reads_and_marking_writes_are_terminal(self):
        base = self.meta["base_off"]
        initial = {
            fab.wa(base, wire) for wire in range(fab.W_MARKING0 + fab.N_IN)
        }
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
        records, roots, _transitions = fab.build_gates()
        depths = {wire: 0 for wire in range(fab.W_MARKING0 + fab.N_IN)}
        for _op, a, b, out in records:
            self.assertIn(a, depths)
            self.assertIn(b, depths)
            depths[out] = max(depths[a], depths[b]) + 1
        self.assertEqual(max(depths[out] for _op, _a, _b, out in records), 14)
        self.assertLessEqual(max(depths[root] for root in roots), 14)

    def test_self_clocked_marking(self):
        self.assertEqual(self.meta["output_addrs"], self.meta["input_addrs"])
        self.assertEqual(len(self.meta["input_addrs"]), 64 * 4)
        self.assertEqual(len(set(self.meta["input_addrs"])), 64 * 4)

    def test_transition_map_covers_64_places_once(self):
        owned = []
        for transition, row in enumerate(self.meta["transitions"]):
            place_a, place_b = fab.transition_places(transition)
            owned.extend((place_a, place_b))
            self.assertEqual(row["input_places"], [place_a, place_a, place_b])
            self.assertEqual(row["output_places"], [place_b, place_b])
            self.assertEqual(row["reaction"], f"2P{place_a} + P{place_b} -> 2P{place_b}")
        self.assertEqual(owned, list(range(64)))

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
            fab.MNO_PATH = os.path.join(tmp, "muhl_petr.mno")
            fab.REG_PATH = os.path.join(tmp, "petr_circuits.json")
            try:
                self.assertEqual(fab.main(["--dry"]), 0)
                self.assertFalse(os.path.exists(fab.MNO_PATH))
                self.assertFalse(os.path.exists(fab.REG_PATH))
            finally:
                fab.MNO_PATH, fab.REG_PATH, fab.EXCERPT_DIR = old_mno, old_reg, old_dir


if __name__ == "__main__":
    unittest.main()
