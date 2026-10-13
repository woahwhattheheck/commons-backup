# SPDX-License-Identifier: Apache-2.0
"""Output nonmutation contracts; real source/patch contracts live next door.

These tests use disposable synthetic inputs with their actual Git blob hashes.
Only patch_bytes is replaced: the pinned-source reader and output writer are
real. The existing test_current_abi suite authenticates the production inputs
and proves that the candidate's runtime transformation is unchanged.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import apply_repair as carrier


class MaterializeOutputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="titan-output-contract-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.tree = self.base / "source"
        self.main = self.tree / carrier.TARGET
        self.spatial = self.tree / carrier.SPATIAL_TARGET
        self.main.parent.mkdir(parents=True)
        self.main_bytes = b"# disposable main input\n"
        self.spatial_bytes = b"# disposable spatial input\n"
        self.candidate = b"# disposable transformed candidate\n"
        self.main.write_bytes(self.main_bytes)
        self.spatial.write_bytes(self.spatial_bytes)
        self.output = self.base / "candidate.py"
        self.receipt = self.base / "receipt.json"
        for name, value in (
            ("EXPECTED_MAIN_GIT_BLOB_SHA1", carrier.git_blob_sha1(self.main_bytes)),
            ("EXPECTED_SPATIAL_GIT_BLOB_SHA1", carrier.git_blob_sha1(self.spatial_bytes)),
        ):
            patcher = mock.patch.object(carrier, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(carrier, "patch_bytes", return_value=self.candidate)
        self.patch_bytes = patcher.start()
        self.addCleanup(patcher.stop)

    def assert_sources_unchanged(self):
        self.assertEqual(self.main.read_bytes(), self.main_bytes)
        self.assertEqual(self.spatial.read_bytes(), self.spatial_bytes)

    def test_new_output_and_receipt_bind_exact_bytes(self):
        result = carrier.materialize(self.tree, self.output, receipt_path=self.receipt)
        self.assertEqual(self.output.read_bytes(), self.candidate)
        self.assertEqual(json.loads(self.receipt.read_text()), result)
        self.assertEqual(result["candidate_git_blob_sha1"], carrier.git_blob_sha1(self.candidate))
        self.assertEqual(result["source_git_blob_sha1"], carrier.git_blob_sha1(self.main_bytes))
        self.assertEqual(result["guard_git_blob_sha1"], carrier.git_blob_sha1(self.spatial_bytes))
        self.assertEqual(result["composition_authority"], "none; current-ABI carrier only")
        self.assert_sources_unchanged()

    def test_candidate_only_api_still_works(self):
        carrier.materialize(self.tree, self.output)
        self.assertFalse(self.receipt.exists())
        self.assert_sources_unchanged()

    def test_nested_new_external_outputs(self):
        output = self.base / "new" / "candidate.py"
        receipt = self.base / "new" / "receipts" / "source.json"
        carrier.materialize(self.tree, output, receipt_path=receipt)
        self.assertEqual(output.read_bytes(), self.candidate)
        self.assertTrue(receipt.is_file())
        self.assert_sources_unchanged()

    def test_existing_regular_output_is_not_replaced(self):
        self.output.write_bytes(b"previous useful candidate\n")
        with self.assertRaises(FileExistsError):
            carrier.materialize(self.tree, self.output)
        self.assertEqual(self.output.read_bytes(), b"previous useful candidate\n")
        self.assert_sources_unchanged()

    def test_candidate_main_hardlink_does_not_mutate_input(self):
        os.link(self.main, self.output)
        with self.assertRaises(FileExistsError):
            carrier.materialize(self.tree, self.output)
        self.assert_sources_unchanged()

    def test_candidate_spatial_hardlink_does_not_mutate_guard(self):
        os.link(self.spatial, self.output)
        with self.assertRaises(FileExistsError):
            carrier.materialize(self.tree, self.output)
        self.assert_sources_unchanged()

    def test_candidate_symlink_is_not_followed(self):
        self.output.symlink_to(self.main)
        with self.assertRaises(FileExistsError):
            carrier.materialize(self.tree, self.output)
        self.assertTrue(self.output.is_symlink())
        self.assert_sources_unchanged()

    def test_dangling_candidate_symlink_is_not_followed(self):
        absent = self.base / "absent.py"
        self.output.symlink_to(absent)
        with self.assertRaises(FileExistsError):
            carrier.materialize(self.tree, self.output)
        self.assertFalse(absent.exists())
        self.assert_sources_unchanged()

    def test_existing_directory_is_not_an_output(self):
        self.output.mkdir()
        with self.assertRaises(FileExistsError):
            carrier.materialize(self.tree, self.output)
        self.assertTrue(self.output.is_dir())

    def test_direct_source_paths_refused_before_writing(self):
        for path in (self.main, self.spatial):
            with self.subTest(path=path), self.assertRaises(ValueError):
                carrier.materialize(self.tree, path)
        self.assert_sources_unchanged()

    def test_new_output_inside_source_tree_refused(self):
        output = self.tree / "new" / "candidate.py"
        with self.assertRaises(ValueError):
            carrier.materialize(self.tree, output)
        self.assertFalse(output.parent.exists())
        self.assert_sources_unchanged()

    def test_dotdot_path_into_source_tree_refused(self):
        path = self.base / "other" / ".." / "source" / "candidate.py"
        with self.assertRaises(ValueError):
            carrier.materialize(self.tree, path)
        self.assertFalse((self.tree / "candidate.py").exists())
        self.assert_sources_unchanged()

    def test_symlinked_directory_into_source_tree_refused(self):
        link = self.base / "linked-source"
        link.symlink_to(self.main.parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            carrier.materialize(self.tree, link / "candidate.py")
        self.assertFalse((self.main.parent / "candidate.py").exists())
        self.assert_sources_unchanged()

    def test_receipt_main_hardlink_refused_before_candidate(self):
        os.link(self.main, self.receipt)
        with self.assertRaises(FileExistsError):
            carrier.materialize(self.tree, self.output, receipt_path=self.receipt)
        self.assertFalse(self.output.exists())
        self.assert_sources_unchanged()

    def test_receipt_spatial_hardlink_refused_before_candidate(self):
        os.link(self.spatial, self.receipt)
        with self.assertRaises(FileExistsError):
            carrier.materialize(self.tree, self.output, receipt_path=self.receipt)
        self.assertFalse(self.output.exists())
        self.assert_sources_unchanged()

    def test_direct_source_receipt_refused_before_candidate(self):
        for path in (self.main, self.spatial):
            with self.subTest(path=path), self.assertRaises(ValueError):
                carrier.materialize(self.tree, self.output, receipt_path=path)
        self.assertFalse(self.output.exists())
        self.assert_sources_unchanged()

    def test_existing_receipt_remains_intact(self):
        self.receipt.write_bytes(b"retained evidence\n")
        with self.assertRaises(FileExistsError):
            carrier.materialize(self.tree, self.output, receipt_path=self.receipt)
        self.assertEqual(self.receipt.read_bytes(), b"retained evidence\n")
        self.assertFalse(self.output.exists())

    def test_dangling_receipt_symlink_remains_intact(self):
        absent = self.base / "absent.json"
        self.receipt.symlink_to(absent)
        with self.assertRaises(FileExistsError):
            carrier.materialize(self.tree, self.output, receipt_path=self.receipt)
        self.assertFalse(absent.exists())
        self.assertFalse(self.output.exists())

    def test_identical_candidate_receipt_refused(self):
        with self.assertRaises(ValueError):
            carrier.materialize(self.tree, self.output, receipt_path=self.output)
        self.assertFalse(self.output.exists())

    def test_directory_aliased_candidate_receipt_refused(self):
        directory = self.base / "products"
        directory.mkdir()
        link = self.base / "linked-products"
        link.symlink_to(directory, target_is_directory=True)
        with self.assertRaises(ValueError):
            carrier.materialize(self.tree, directory / "candidate", receipt_path=link / "candidate")
        self.assertEqual(list(directory.iterdir()), [])

    def test_source_drift_creates_no_outputs(self):
        self.main.write_bytes(b"changed outside the materializer\n")
        with self.assertRaisesRegex(ValueError, "preimage"):
            carrier.materialize(self.tree, self.output, receipt_path=self.receipt)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.receipt.exists())
        self.patch_bytes.assert_not_called()

    def test_patch_failure_creates_no_output_directory(self):
        self.patch_bytes.side_effect = ValueError("replacement closure failed")
        output = self.base / "new" / "candidate.py"
        with self.assertRaises(ValueError):
            carrier.materialize(self.tree, output)
        self.assertFalse(output.parent.exists())
        self.assert_sources_unchanged()

    def test_file_created_after_preflight_cannot_be_truncated(self):
        real_open = Path.open
        def appeared(path, mode="r", *args, **kwargs):
            if path == self.output and mode == "xb":
                os.link(self.main, path)
            return real_open(path, mode, *args, **kwargs)
        with mock.patch.object(Path, "open", appeared), self.assertRaises(FileExistsError):
            carrier.materialize(self.tree, self.output, receipt_path=self.receipt)
        self.assertFalse(self.receipt.exists())
        self.assert_sources_unchanged()

    def test_receipt_created_after_preflight_cannot_be_truncated(self):
        real_open = Path.open
        def appeared(path, mode="r", *args, **kwargs):
            if path == self.receipt and mode == "xb":
                os.link(self.spatial, path)
            return real_open(path, mode, *args, **kwargs)
        with mock.patch.object(Path, "open", appeared), self.assertRaises(FileExistsError):
            carrier.materialize(self.tree, self.output, receipt_path=self.receipt)
        self.assertEqual(self.output.read_bytes(), self.candidate)
        self.assert_sources_unchanged()

    def test_candidate_readback_failure_emits_no_receipt(self):
        real_read = Path.read_bytes
        def corrupted(path):
            return b"different readback" if path == self.output else real_read(path)
        with mock.patch.object(Path, "read_bytes", corrupted), self.assertRaises(OSError):
            carrier.materialize(self.tree, self.output, receipt_path=self.receipt)
        self.assertFalse(self.receipt.exists())
        self.assert_sources_unchanged()

    def test_main_drift_after_candidate_write_has_no_success_receipt(self):
        self._assert_postwrite_drift_fails(self.main)

    def test_guard_drift_after_candidate_write_has_no_success_receipt(self):
        self._assert_postwrite_drift_fails(self.spatial)

    def _assert_postwrite_drift_fails(self, source):
        real_write = carrier._write_new_bytes
        def changed(target, data):
            real_write(target, data)
            if target == self.output:
                source.write_bytes(b"concurrent source change in disposable fixture\n")
        with mock.patch.object(carrier, "_write_new_bytes", changed):
            with self.assertRaises(ValueError):
                carrier.materialize(self.tree, self.output, receipt_path=self.receipt)
        self.assertEqual(self.output.read_bytes(), self.candidate)
        self.assertFalse(self.receipt.exists())

    def test_cli_uses_same_nonreplacement_receipt_path(self):
        os.link(self.main, self.receipt)
        argv = ["apply_repair", "--tree", str(self.tree), "--output", str(self.output),
                "--receipt", str(self.receipt)]
        stdout = io.StringIO()
        with mock.patch("sys.argv", argv), contextlib.redirect_stdout(stdout):
            with self.assertRaises(FileExistsError):
                carrier.main()
        self.assertEqual(stdout.getvalue(), "")
        self.assertFalse(self.output.exists())
        self.assert_sources_unchanged()

    def test_cli_receipt_round_trip_is_exact(self):
        argv = ["apply_repair", "--tree", str(self.tree), "--output", str(self.output),
                "--receipt", str(self.receipt)]
        stdout = io.StringIO()
        with mock.patch("sys.argv", argv), contextlib.redirect_stdout(stdout):
            self.assertEqual(carrier.main(), 0)
        self.assertEqual(stdout.getvalue().encode(), self.receipt.read_bytes())
        self.assert_sources_unchanged()

    def test_second_run_never_overwrites_first_run(self):
        carrier.materialize(self.tree, self.output, receipt_path=self.receipt)
        original = self.output.read_bytes(), self.receipt.read_bytes()
        with self.assertRaises(FileExistsError):
            carrier.materialize(self.tree, self.output, receipt_path=self.receipt)
        self.assertEqual((self.output.read_bytes(), self.receipt.read_bytes()), original)
        self.assert_sources_unchanged()


if __name__ == "__main__":
    unittest.main()
