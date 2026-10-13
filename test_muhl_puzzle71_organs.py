#!/usr/bin/env python3
"""Synthetic fixture tests for the derived cloud puzzle71 helpers.

Never touch the live 4.8GB muhl_puzzle71.mno. This VM is not the owner PC.
The live-run instrument is host/muhl_puzzle71_organs_add.py (Fable exact bytes).
These tests import the *_cloud.py copies only.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "host"))

from muhl_puzzle71_fire_cloud import main as fire_main
from muhl_puzzle71_organs_cloud import (
    AND,
    LATCH_N,
    PUZFOLD_LEN,
    PUZFOLD_MAGIC,
    STRIDE,
    TICK_ADDR,
    WIN_OUT,
    main as organs_main,
    pack_rec,
    scan_records,
    unpack_rec,
)


LATCH_B = 999
FIXTURE_OVERRIDES = [
    "--latch-b",
    str(LATCH_B),
    "--latch-n",
    str(LATCH_N),
    "--win-out",
    str(WIN_OUT),
    "--tick",
    str(TICK_ADDR),
]


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_fixture(path):
    recs = []
    for i in range(LATCH_N):
        recs.append(pack_rec(AND, i, LATCH_B, 10 + i))
    Path(path).write_bytes(b"".join(recs))
    return os.path.getsize(path)


def run(fn, argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = fn(argv)
    return rc, buf.getvalue()


class TestMuhlPuzzle71Organs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.dest = os.path.join(self.dir, "muhl_puzzle71.mno")
        self.reg = os.path.join(self.dir, "muhl_puzzle71.circuits.json")
        self.org_journal = os.path.join(self.dir, "organs.jsonl")
        self.fire_journal = os.path.join(self.dir, "fire.jsonl")
        self.old_size = write_fixture(self.dest)
        self.paths = [
            "--dest",
            self.dest,
            "--reg",
            self.reg,
            "--journal",
            self.org_journal,
        ]

    def tearDown(self):
        self.tmp.cleanup()

    def test_dry_writes_nothing(self):
        before = _sha(self.dest)
        rc, out = run(organs_main, ["--dry", *self.paths, *FIXTURE_OVERRIDES])
        self.assertEqual(rc, 0, out)
        self.assertIn("DRY. no write.", out)
        self.assertEqual(_sha(self.dest), before)
        self.assertFalse(os.path.isfile(self.reg))
        self.assertFalse(os.path.isfile(self.org_journal))
        self.assertEqual(os.path.getsize(self.dest), self.old_size)

    def test_go_retargets_appends_registry_puzfold_tick_unwritten_as_fire(self):
        rc, out = run(organs_main, ["--go", *self.paths, *FIXTURE_OVERRIDES])
        self.assertEqual(rc, 0, out)
        self.assertIn("DIE", out)
        self.assertGreater(os.path.getsize(self.dest), self.old_size)
        blob = Path(self.dest).read_bytes()
        latches = []
        for off in range(0, self.old_size, STRIDE):
            _op, _a, b, _out = unpack_rec(blob[off : off + STRIDE])
            latches.append({"off": off, "b": b})
        self.assertEqual(len(latches), LATCH_N)
        self.assertTrue(all(r["b"] == WIN_OUT for r in latches))
        self.assertFalse(any(r["b"] == LATCH_B for r in latches))
        with open(self.reg, encoding="utf-8") as f:
            reg = json.load(f)
        # Gate records start after the 1-byte-per-address wire acreage, so a
        # whole-file stride-25 scan cannot see tick@88. Read from gate_base.
        gate_off = int(reg["gate_base"])
        puz_off = int(reg["PUZFOLD1"]["offset"])
        self.assertEqual(puz_off - gate_off, int(reg["n_new_gates"]) * STRIDE)
        tick_hits = []
        off = gate_off
        while off + STRIDE <= puz_off:
            op, _a, _b, out_addr = unpack_rec(blob[off : off + STRIDE])
            if out_addr == TICK_ADDR:
                tick_hits.append((off, op))
            off += STRIDE
        self.assertEqual(len(tick_hits), 1, tick_hits)
        self.assertEqual(tick_hits[0][1], 2)  # OR
        tail = blob[-PUZFOLD_LEN:]
        self.assertTrue(tail.startswith(PUZFOLD_MAGIC))
        self.assertEqual(len(reg["rings"]), 16)
        self.assertEqual(reg["rings"][0]["cells"], 32)
        self.assertEqual(len(reg["rings"][0]["clocks"]), 24)
        self.assertEqual(reg["PUZFOLD1"]["addr_bits"], 70)
        self.assertTrue(reg["PUZFOLD1"]["winner_only"])
        self.assertEqual(reg["PUZFOLD1"]["stored_per_lane"], 0)
        self.assertEqual(reg["tick"]["addr"], TICK_ADDR)
        self.assertEqual(reg["win"]["addr"], WIN_OUT)
        # Organs must not fire 0x01 into cell 0. Wire acreage stays zeros.
        ring0 = reg["rings"][0]
        wire = blob[self.old_size : ring0["fwd"] + 66]
        self.assertEqual(wire, b"\x00" * len(wire))

    def test_fire_dry_and_surface_no_write(self):
        rc, out = run(organs_main, ["--go", *self.paths, *FIXTURE_OVERRIDES])
        self.assertEqual(rc, 0, out)
        before = _sha(self.dest)
        fire_argv = [
            "--dest",
            self.dest,
            "--reg",
            self.reg,
            "--journal",
            self.fire_journal,
        ]
        rc, out = run(fire_main, ["--dry", *fire_argv])
        self.assertEqual(rc, 0, out)
        self.assertIn("NO WRITE.", out)
        self.assertEqual(_sha(self.dest), before)
        rc, out = run(fire_main, ["--surface", *fire_argv])
        self.assertEqual(rc, 0, out)
        self.assertIn("SURFACE only.", out)
        self.assertEqual(_sha(self.dest), before)
        self.assertFalse(os.path.isfile(self.fire_journal))

    def test_fire_go_or_mask_then_organs_revert(self):
        rc, out = run(organs_main, ["--go", *self.paths, *FIXTURE_OVERRIDES])
        self.assertEqual(rc, 0, out)
        with open(self.reg, encoding="utf-8") as f:
            rings = json.load(f)["rings"]
        fire_argv = [
            "--go",
            "--dest",
            self.dest,
            "--reg",
            self.reg,
            "--journal",
            self.fire_journal,
        ]
        rc, out = run(fire_main, fire_argv)
        self.assertEqual(rc, 0, out)
        blob = Path(self.dest).read_bytes()
        for ring in rings:
            self.assertEqual(blob[ring["fwd"]] & 0x01, 0x01)
            self.assertEqual(blob[ring["rev"]] & 0x01, 0x01)
        rc, out = run(organs_main, ["revert", *self.paths])
        self.assertEqual(rc, 0, out)
        self.assertEqual(os.path.getsize(self.dest), self.old_size)
        scan = scan_records(self.dest)
        latches = [r for r in scan["records"] if r["b"] == LATCH_B]
        self.assertEqual(len(latches), LATCH_N)
        self.assertFalse(os.path.isfile(self.reg))
        self.assertFalse(os.path.isfile(self.org_journal))

    def test_refuse_inject_and_titan(self):
        rc, out = run(
            organs_main,
            ["--go", "--inject", *self.paths, *FIXTURE_OVERRIDES],
        )
        self.assertEqual(rc, 2, out)
        self.assertIn("REFUSE", out)
        titan = os.path.join(self.dir, "titan.gguf")
        Path(titan).write_bytes(b"not-a-real-titan")
        rc, out = run(
            organs_main,
            ["--go", "--dest", titan, "--reg", self.reg, "--journal", self.org_journal],
        )
        self.assertEqual(rc, 2, out)
        self.assertIn("REFUSE dest titan.gguf", out)
        rc, out = run(
            fire_main,
            ["--go", "--inject", "--dest", self.dest, "--reg", self.reg, "--journal", self.fire_journal],
        )
        self.assertEqual(rc, 2, out)
        self.assertIn("REFUSE", out)
        rc, out = run(
            fire_main,
            ["--go", "--dest", titan, "--reg", self.reg, "--journal", self.fire_journal],
        )
        self.assertEqual(rc, 2, out)
        self.assertIn("REFUSE dest titan.gguf", out)
        self.assertEqual(os.path.getsize(self.dest), self.old_size)

    def test_fail_closed_wrong_latch_count(self):
        rc, out = run(
            organs_main,
            ["--dry", *self.paths, "--latch-b", str(LATCH_B), "--latch-n", "69"],
        )
        self.assertEqual(rc, 1, out)
        self.assertIn("FAIL CLOSED", out)

    def test_need_mode_flag(self):
        rc, out = run(organs_main, [*self.paths])
        self.assertEqual(rc, 1, out)
        self.assertIn("NEED --dry or --go", out)


if __name__ == "__main__":
    unittest.main()
