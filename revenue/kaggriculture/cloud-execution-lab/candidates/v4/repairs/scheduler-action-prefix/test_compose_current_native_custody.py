#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import compose_current_native as prefix


class PrefixMaterializerCustodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        (self.repo / ".git").mkdir()
        self.scratch = self.root / "scratch"
        self.scratch.mkdir()

    def test_fresh_in_repo_output_is_rejected(self):
        target = self.repo / "generated-prefix"
        with self.assertRaisesRegex(ValueError, "repository"):
            prefix._validate_external_target(target, self.repo, fresh=True)
        self.assertFalse(target.exists())

    def test_existing_canonical_receipt_target_is_rejected_unchanged(self):
        target = self.repo / "main.py"
        target.write_text("canonical\n", encoding="utf-8")
        before = target.read_bytes()
        with self.assertRaises(ValueError):
            prefix._validate_external_target(target, self.repo, fresh=True)
        self.assertEqual(target.read_bytes(), before)

    def test_symlinked_external_ancestor_is_rejected(self):
        real = self.root / "real"
        real.mkdir()
        link = self.root / "alias"
        try:
            link.symlink_to(real, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        target = link / "receipt.json"
        with self.assertRaisesRegex(ValueError, "symlink"):
            prefix._validate_external_target(target, self.repo, fresh=True)
        self.assertFalse((real / "receipt.json").exists())

    def test_explicit_receipt_cannot_alias_output_tree(self):
        output = self.scratch / "out"
        receipt = output / "scheduler.py"
        with self.assertRaises(ValueError):
            prefix._validate_publish_layout(output, receipt, self.repo, ())
        self.assertFalse(output.exists())
        self.assertFalse(receipt.exists())

    def test_receipt_cannot_alias_external_input(self):
        source = self.scratch / "source.py"
        source.write_text("input\n", encoding="utf-8")
        output = self.scratch / "out"
        with self.assertRaises(ValueError):
            prefix._validate_publish_layout(output, source, self.repo, (source,))
        self.assertFalse(output.exists())
        self.assertEqual(source.read_text(encoding="utf-8"), "input\n")

    def test_preexisting_temp_sidecar_symlink_is_rejected_without_clobber(self):
        target = self.scratch / "receipt.json"
        victim = self.scratch / "victim.txt"
        victim.write_text("keep\n", encoding="utf-8")
        sidecar = target.with_name(f".{target.name}.prefix.tmp")
        try:
            sidecar.symlink_to(victim)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaises(ValueError):
            prefix._publish_fresh(target, b"replacement\n", self.repo)
        self.assertEqual(victim.read_text(encoding="utf-8"), "keep\n")
        self.assertFalse(target.exists())

    def test_external_fresh_publication_is_exact_and_non_overwriting(self):
        target = self.scratch / "receipt.json"
        prefix._publish_fresh(target, b"first\n", self.repo)
        self.assertEqual(target.read_bytes(), b"first\n")
        with self.assertRaises(ValueError):
            prefix._publish_fresh(target, b"second\n", self.repo)
        self.assertEqual(target.read_bytes(), b"first\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
