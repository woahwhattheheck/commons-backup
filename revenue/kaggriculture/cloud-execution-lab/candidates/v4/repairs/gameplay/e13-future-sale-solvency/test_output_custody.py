#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Adversarial output-custody tests for the E13 scratch materializer."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_port():
    path = HERE / "port_current_runtime.py"
    spec = importlib.util.spec_from_file_location("titan_v4_e13_port_custody", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


port = _load_port()
ROOT = port.find_repo_root(Path(__file__))
LAB = ROOT / "revenue/kaggriculture/cloud-execution-lab"


class E13OutputCustodyTests(unittest.TestCase):
    def test_arbitrary_runtime_candidate_destination_is_rejected_unchanged(self):
        victim = LAB / "scheduler.py"
        before = victim.read_bytes()
        with tempfile.TemporaryDirectory() as td:
            receipt = Path(td) / "receipt.json"
            with self.assertRaisesRegex(port.PortError, "refusing to overwrite repository path"):
                port.materialize(ROOT, victim, receipt)
            self.assertFalse(receipt.exists())
        self.assertEqual(victim.read_bytes(), before)

    def test_arbitrary_runtime_receipt_destination_is_rejected_unchanged(self):
        victim = LAB / "main.py"
        before = victim.read_bytes()
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "candidate.py"
            with self.assertRaisesRegex(port.PortError, "refusing to overwrite repository path"):
                port.materialize(ROOT, output, victim)
            self.assertFalse(output.exists())
        self.assertEqual(victim.read_bytes(), before)

    def test_external_symlink_ancestor_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            real = td / "real"
            real.mkdir()
            link = td / "redirect"
            link.symlink_to(real, target_is_directory=True)
            output = link / "candidate.py"
            receipt = td / "receipt.json"
            with self.assertRaisesRegex(port.PortError, "symlink component"):
                port.materialize(ROOT, output, receipt)
            self.assertFalse((real / "candidate.py").exists())
            self.assertFalse(receipt.exists())

    def test_preexisting_temp_sidecar_symlink_is_rejected_without_touching_target(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            output = td / "candidate.py"
            receipt = td / "receipt.json"
            target = td / "victim.txt"
            target.write_text("do-not-touch", encoding="utf-8")
            output.with_name(output.name + ".tmp").symlink_to(target)
            with self.assertRaisesRegex(port.PortError, "symlink component"):
                port.materialize(ROOT, output, receipt)
            self.assertEqual(target.read_text(encoding="utf-8"), "do-not-touch")
            self.assertFalse(output.exists())
            self.assertFalse(receipt.exists())

    def test_receipt_symlink_is_rejected_before_candidate_write(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            output = td / "candidate.py"
            target = td / "victim.json"
            target.write_text("{}", encoding="utf-8")
            receipt = td / "receipt.json"
            receipt.symlink_to(target)
            with self.assertRaisesRegex(port.PortError, "symlink component"):
                port.materialize(ROOT, output, receipt)
            self.assertEqual(target.read_text(encoding="utf-8"), "{}")
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
