#!/usr/bin/env python3
"""Prove the named puzzle71 paths are Fable's exact live-run bytes.

Does not open C:/llm/models/muhl_puzzle71.mno. Does not --fab or --go.
"""
from __future__ import annotations

import hashlib
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "host"))

from muhl_puzzle71_fire_add import main as fire_main
from muhl_puzzle71_organs_add import R_RINGS, TICK, main as organs_main, plan

ORGANS = Path(ROOT) / "host" / "muhl_puzzle71_organs_add.py"
FIRE = Path(ROOT) / "host" / "muhl_puzzle71_fire_add.py"
FABLE_ORGANS = "9128536487cb20181bf4dc96605a23a515ba9854"
FABLE_FIRE = "72e8544056c248b56975317887f39494798ff731"


def _git_blob(path):
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()


class TestMuhlPuzzle71LiveInstrument(unittest.TestCase):
    def test_named_paths_are_fable_exact_blobs(self):
        self.assertEqual(_git_blob(ORGANS), FABLE_ORGANS)
        self.assertEqual(_git_blob(FIRE), FABLE_FIRE)

    def test_plan_or_tree_writes_tick_once(self):
        P = plan()
        self.assertEqual(len(P["rings"]), R_RINGS)
        self.assertEqual(P["recs"][-1][3], TICK)
        outs = [rc[3] for rc in P["recs"]]
        self.assertEqual(len(outs), len(set(outs)))
        self.assertEqual(P["n_new"], len(P["recs"]))

    def test_dry_fail_closed_without_live_container(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = organs_main([])
        self.assertEqual(rc, 1)
        self.assertIn("container missing", buf.getvalue())

    def test_fire_fail_closed_without_registry(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = fire_main(["--go"])
        self.assertEqual(rc, 1)
        self.assertIn("FAIL CLOSED", buf.getvalue())
        self.assertIn("registry missing", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
