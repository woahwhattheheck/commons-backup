"""Independent archive-custody checks; no archived test or patch is executed."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "basalt42_review_restore_under_test", Path(__file__).with_name("restore.py"))
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Cannot load the adjacent review restore module")
restore = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(restore)


class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.parts = self.root / "parts"
        self.parts.mkdir()
        for source in restore.HERE.glob("retained.tar.xz.part-*"):
            shutil.copyfile(source, self.parts / source.name)

    def test_exact_archive_inventory_and_read_only_verification(self):
        before = {p.name: p.read_bytes() for p in self.parts.iterdir()}
        files = restore.verify(self.parts)
        self.assertEqual(len(files), 26)
        self.assertEqual(sum(map(len, files.values())), 220838)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.parts.iterdir()})
        self.assertIn(b"KNOWN_UNRESOLVED_IN_REFERENCE_PATCH", files[
            "zz-basalt42-workbench-review/numeric-limit-diagnostic.json"])

    def test_extract_all_files_byte_identically(self):
        destination = self.root / "restored"
        files = restore.extract(self.parts, destination)
        actual = {p.relative_to(destination).as_posix(): p.read_bytes()
                  for p in destination.rglob("*") if p.is_file()}
        self.assertEqual(actual, files)
        self.assertEqual(hashlib.sha256(actual[
            "zz-basalt42-workbench-review/intake_integration.test.cjs"
        ]).hexdigest(), "fe013debddfc1e78a669722a905df72ddf311851ebbd908fa52ce7b0c342cbf1")

    def test_corruption_rejected_without_output_creation(self):
        part = self.parts / "retained.tar.xz.part-03"
        contents = bytearray(part.read_bytes()); contents[10] ^= 1
        part.write_bytes(contents)
        destination = self.root / "not-created"
        with self.assertRaisesRegex(restore.ArchiveError, "digest mismatch"):
            restore.extract(self.parts, destination)
        self.assertFalse(destination.exists())

    def test_missing_part_rejected(self):
        (self.parts / "retained.tar.xz.part-04").unlink()
        with self.assertRaisesRegex(restore.ArchiveError, "missing regular"):
            restore.verify(self.parts)

    def test_truncated_part_rejected(self):
        part = self.parts / "retained.tar.xz.part-02"
        part.write_bytes(part.read_bytes()[:-1])
        with self.assertRaisesRegex(restore.ArchiveError, "size"):
            restore.verify(self.parts)

    def test_swapped_equal_length_parts_rejected(self):
        a = self.parts / "retained.tar.xz.part-01"
        b = self.parts / "retained.tar.xz.part-02"
        old = a.read_bytes(); a.write_bytes(b.read_bytes()); b.write_bytes(old)
        with self.assertRaisesRegex(restore.ArchiveError, "digest mismatch"):
            restore.verify(self.parts)

    def test_existing_output_never_overwritten(self):
        destination = self.root / "existing"; destination.mkdir()
        marker = destination / "keep.txt"; marker.write_bytes(b"keep")
        with self.assertRaises(FileExistsError):
            restore.extract(self.parts, destination)
        self.assertEqual(list(destination.iterdir()), [marker])
        self.assertEqual(marker.read_bytes(), b"keep")

    def test_missing_parent_not_created(self):
        destination = self.root / "absent" / "output"
        with self.assertRaisesRegex(restore.ArchiveError, "parent"):
            restore.extract(self.parts, destination)
        self.assertFalse(destination.parent.exists())

    def test_symlink_part_is_not_followed(self):
        part = self.parts / "retained.tar.xz.part-01"
        part.unlink()
        try:
            part.symlink_to(restore.HERE / part.name)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unsupported in this environment")
        with self.assertRaisesRegex(restore.ArchiveError, "regular"):
            restore.verify(self.parts)

    def test_unexpected_member_paths_rejected(self):
        for name in ("../outside", "/absolute", "other/file", "zz-basalt42-workbench-review/../escape",
                     "zz-basalt42-workbench-review//file", "zz-basalt42-workbench-review\\file"):
            with self.subTest(name=name), self.assertRaises(restore.ArchiveError):
                restore.member_path(name)

    def test_archive_pin_checked_independently_of_parts(self):
        with patch.object(restore, "ARCHIVE_SHA256", "0" * 64):
            with self.assertRaisesRegex(restore.ArchiveError, "joined archive"):
                restore.verify(self.parts)

    def test_inventory_pin_checked_independently_of_archive(self):
        with patch.object(restore, "FILE_COUNT", 27):
            with self.assertRaisesRegex(restore.ArchiveError, "inventory"):
                restore.verify(self.parts)


if __name__ == "__main__":
    unittest.main(verbosity=2)
