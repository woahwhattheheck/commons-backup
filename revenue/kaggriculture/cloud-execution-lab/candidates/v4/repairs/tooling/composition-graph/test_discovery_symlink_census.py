#!/usr/bin/env python3
"""Regression for LOOM discovery inventory of symlink objects."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

V4_ROOT = Path(__file__).resolve().parents[3]
CHECKER = V4_ROOT / "check_composition_graph.py"
SPEC = importlib.util.spec_from_file_location("titan_v4_composition_graph", CHECKER)
assert SPEC is not None and SPEC.loader is not None
cg = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cg)


class DiscoverySymlinkCensusTests(unittest.TestCase):
    def test_symlink_to_directory_is_unsafe_before_kind_filter(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "repairs").mkdir()
            research = root / "research"
            research.mkdir()
            real = root / "real-target"
            real.mkdir()
            (real / "rogue.py").write_text("# rogue\n", encoding="utf-8")
            link = research / "rogue.py"
            try:
                link.symlink_to(real, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")

            found, unsafe = cg._discover(
                root,
                {"roots": ["repairs", "research"], "patterns": ["rogue.py"]},
            )

            self.assertEqual(found, set())
            self.assertIn("research/rogue.py", unsafe)


if __name__ == "__main__":
    unittest.main()
