# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

import materialize


PREFIX = """PRODUCTS = ('MILK', 'EGG')\n\nclass Probe:\n    def __init__(self, pending):\n        self.pending = pending\n\n    def targets(self, shed, baseline_q):\n"""
SUFFIX = """        return targets\n"""


class MaterializeTests(unittest.TestCase):
    def source_tree(self, root: Path, *, copies: int = 1) -> Path:
        source = root / "v2"
        (source / "reference" / "decision").mkdir(parents=True)
        scheduler = PREFIX + materialize.OLD * copies + SUFFIX
        (source / "scheduler.py").write_text(scheduler, encoding="utf-8")
        (source / "candidate.py").write_text(
            "from scheduler import Probe\n", encoding="utf-8"
        )
        (source / "reference" / "decision" / "receipt.txt").write_text(
            "unchanged\n", encoding="utf-8"
        )
        return source

    def test_one_factor_materialization_and_semantics(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.source_tree(root)
            original = (source / "scheduler.py").read_bytes()
            expected = materialize.git_blob_sha1(original)
            output = root / "candidate"
            receipt = materialize.materialize(
                source, output, expected_scheduler_blob=expected
            )
            self.assertEqual(receipt["ablation"]["changed_files"], ["scheduler.py"])
            self.assertEqual((source / "scheduler.py").read_bytes(), original)
            self.assertEqual(
                (source / "candidate.py").read_bytes(),
                (output / "candidate.py").read_bytes(),
            )
            self.assertEqual(
                (source / "reference" / "decision" / "receipt.txt").read_bytes(),
                (output / "reference" / "decision" / "receipt.txt").read_bytes(),
            )
            spec = importlib.util.spec_from_file_location(
                "patched_scheduler", output / "scheduler.py"
            )
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
            # V2 would target both positive shed products.  The ablation keeps
            # only baseline-owned or pending-owned intent, with quantity capped
            # by physical stock.
            probe = module.Probe({"EGG": 3})
            self.assertEqual(
                probe.targets({"MILK": 7, "EGG": 5}, {"MILK": 2}),
                {"EGG": 3, "MILK": 2},
            )

    def test_duplicate_target_expression_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.source_tree(root, copies=2)
            expected = materialize.git_blob_sha1(
                (source / "scheduler.py").read_bytes()
            )
            with self.assertRaisesRegex(
                materialize.MaterializeError, "exactly one"
            ):
                materialize.materialize(
                    source, root / "candidate", expected_scheduler_blob=expected
                )

    def test_wrong_blob_fails_before_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.source_tree(root)
            output = root / "candidate"
            with self.assertRaisesRegex(
                materialize.MaterializeError, "blob mismatch"
            ):
                materialize.materialize(
                    source, output, expected_scheduler_blob="0" * 40
                )
            self.assertFalse(output.exists())

    def test_non_regular_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.source_tree(root)
            try:
                (source / "alias").symlink_to(source / "candidate.py")
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are unavailable")
            with self.assertRaisesRegex(
                materialize.MaterializeError, "non-regular"
            ):
                materialize.materialize(
                    source,
                    root / "candidate",
                    expected_scheduler_blob=materialize.git_blob_sha1(
                        (source / "scheduler.py").read_bytes()
                    ),
                )


if __name__ == "__main__":
    unittest.main()
