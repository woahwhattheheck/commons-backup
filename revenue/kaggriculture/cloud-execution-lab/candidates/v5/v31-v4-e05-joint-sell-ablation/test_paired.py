# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

import paired


class PairedHelpersTest(unittest.TestCase):
    def test_leaf_custody_receipt_schema_is_v2(self):
        self.assertEqual(paired.SCHEMA, "astra.v5.v31-v4-e05-joint-sell-paired.v2")

    def test_git_blob_bytes_matches_git_formula(self):
        raw = b"abc\n"
        expected = hashlib.sha1(b"blob 4\0abc\n").hexdigest()
        self.assertEqual(paired.git_blob_bytes(raw), expected)

    def test_capture_git_blob_single_read(self):
        raw = b"x = 1\n"
        expected = paired.git_blob_bytes(raw)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "helper.py"
            path.write_bytes(raw)
            captured = paired.capture_git_blob(path, expected)
            path.write_bytes(b"poison = True\n")
            self.assertEqual(captured, raw)

    def test_load_captured_does_not_reopen_origin(self):
        raw = b"VALUE = 7\n"
        with tempfile.TemporaryDirectory() as td:
            origin = Path(td) / "module.py"
            origin.write_bytes(b"VALUE = 99\n")
            module = paired.load_captured(raw, origin, "e05_test_captured")
            self.assertEqual(module.VALUE, 7)

    def test_captured_harness_survives_source_swap_after_auth(self):
        raw = b"VALUE = 7\n"
        expected = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as td:
            origin = Path(td) / "evaluator.py"
            origin.write_bytes(raw)
            captured = paired.capture_sha256(origin, expected)
            origin.write_bytes(b"VALUE = 99\n")
            module = paired.load_captured(captured, origin, "e05_swap_captured")
            self.assertEqual(module.VALUE, 7)
            self.assertNotEqual(origin.read_bytes(), captured)

    def test_captured_harness_survives_source_delete_after_auth(self):
        raw = b"VALUE = 11\n"
        expected = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as td:
            origin = Path(td) / "pack.py"
            origin.write_bytes(raw)
            captured = paired.capture_sha256(origin, expected)
            origin.unlink()
            module = paired.load_captured(captured, origin, "e05_delete_captured")
            self.assertEqual(module.VALUE, 11)
            self.assertFalse(origin.exists())

    def test_private_loader_is_written_from_authenticated_capture(self):
        raw = b"VALUE = 23\n"
        expected = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            origin = root / "public-evidence-loader.py"
            origin.write_bytes(raw)
            captured = paired.capture_sha256(origin, expected)
            origin.write_bytes(b"VALUE = 101\n")
            private = root / "private-runtime" / "evaluate.py"
            self.assertEqual(
                paired.write_private_runtime_bytes(captured, private, expected), private
            )
            self.assertEqual(private.read_bytes(), raw)
            self.assertNotEqual(private.read_bytes(), origin.read_bytes())

    def test_private_loader_rejects_wrong_captured_digest(self):
        raw = b"VALUE = 23\n"
        expected = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as td:
            private = Path(td) / "private-runtime" / "evaluate.py"
            with self.assertRaisesRegex(
                ValueError, "Private runtime bytes do not match authenticated SHA256"
            ):
                paired.write_private_runtime_bytes(b"VALUE = 24\n", private, expected)
            self.assertFalse(private.exists())

    def test_execution_leaf_rejects_public_output_origin(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            private = root / "private"
            output = root / "output"
            private.mkdir()
            output.mkdir()
            public_adapter = output / "opponents" / "apex" / "adapter.py"
            public_adapter.parent.mkdir(parents=True)
            public_adapter.write_text("PUBLIC = True\n")
            with self.assertRaisesRegex(ValueError, "escaped private runtime"):
                paired.require_private_execution_path(public_adapter, private, output)

    def test_private_opponent_leaf_survives_public_swap_and_delete(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            private = root / "private"
            output = root / "output"
            private_adapter = private / "execution-leaves" / "opponents" / "apex" / "adapter.py"
            public_adapter = output / "opponents" / "apex" / "adapter.py"
            private_adapter.parent.mkdir(parents=True)
            public_adapter.parent.mkdir(parents=True)
            private_adapter.write_bytes(b"PRIVATE-GOOD\n")
            public_adapter.write_bytes(b"PUBLIC-OLD\n")
            selected = paired.require_private_execution_path(private_adapter, private, output)
            public_adapter.write_bytes(b"PUBLIC-POISON\n")
            public_adapter.unlink()
            self.assertEqual(selected.read_bytes(), b"PRIVATE-GOOD\n")
            self.assertFalse(public_adapter.exists())

    def test_private_candidate_leaf_rejects_public_symlink_poison(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            private = root / "private"
            output = root / "output"
            private.mkdir()
            output.mkdir()
            poison = output / "candidate.py"
            poison.write_text("POISON = True\n")
            link = private / "candidate.py"
            link.symlink_to(poison)
            with self.assertRaisesRegex(ValueError, "escaped private runtime"):
                paired.require_private_execution_path(link, private, output)

    def test_margin_requires_complete_719(self):
        self.assertEqual(paired.margin({"status": "complete", "steps": 719, "scores": [10, 4]}, 0), 6)
        self.assertIsNone(paired.margin({"status": "complete", "steps": 718, "scores": [10, 4]}, 0))
        self.assertIsNone(paired.margin({"status": "error", "steps": 719, "scores": [10, 4]}, 0))

    def test_summary_keeps_opponents_separate(self):
        cells = [
            {"opponent": "apex_v7", "margin_delta": 5},
            {"opponent": "apex_v7", "margin_delta": -1},
            {"opponent": "arlene_v14", "margin_delta": 0},
        ]
        value = paired.summarize(cells)
        self.assertEqual(value["complete_pairs"], 3)
        self.assertEqual(value["opponents"]["apex_v7"]["mean_margin_delta"], 2)
        self.assertEqual(value["opponents"]["arlene_v14"]["unchanged"], 1)


if __name__ == "__main__":
    unittest.main()
