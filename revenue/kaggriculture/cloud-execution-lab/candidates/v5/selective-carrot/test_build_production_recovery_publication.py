import hashlib
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import build_production_recovery as bpr
import publication_custody as custody


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.out = self.root / "candidate"
        self.tar = self.root / "candidate.tar.gz"
        self.manifest = self.root / "candidate-manifest.json"
        self.files = {"main.py": b"payload\n", "nested/x.py": b"x\n"}
        self.packed = b"archive-bytes"
        self.receipt = {
            "schema": "test",
            "candidate_archive_sha256": hashlib.sha256(self.packed).hexdigest(),
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_success_uses_shared_pair_and_tree(self):
        bpr._publish(self.files, self.packed, self.receipt, self.out, self.tar, self.manifest)
        self.assertEqual(self.tar.read_bytes(), self.packed)
        self.assertTrue(self.manifest.read_text().endswith("\n"))
        self.assertEqual((self.out / "main.py").read_bytes(), b"payload\n")
        self.assertEqual((self.out / "nested/x.py").read_bytes(), b"x\n")

    def test_manifest_collision_cleans_tree_and_preserves_foreign(self):
        self.manifest.write_bytes(b"foreign")
        with self.assertRaises(FileExistsError):
            bpr._publish(self.files, self.packed, self.receipt, self.out, self.tar, self.manifest)
        self.assertFalse(self.tar.exists())
        self.assertEqual(self.manifest.read_bytes(), b"foreign")
        self.assertFalse(self.out.exists())

    def test_shared_second_write_failure_rolls_back_pair_and_tree(self):
        real = custody._write_all
        calls = {"n": 0}

        def fail_second(fd, payload):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("injected manifest write failure")
            return real(fd, payload)

        with patch.object(custody, "_write_all", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "injected"):
                bpr._publish(self.files, self.packed, self.receipt, self.out, self.tar, self.manifest)
        self.assertFalse(self.tar.exists())
        self.assertFalse(self.manifest.exists())
        self.assertFalse(self.out.exists())

    def test_foreign_output_tree_replacement_is_preserved(self):
        def replace_tree_and_fail(_pairs):
            shutil.rmtree(self.out)
            self.out.mkdir()
            (self.out / "FOREIGN").write_text("keep", encoding="utf-8")
            raise OSError("injected shared publication failure")

        with patch.object(bpr, "publish_exclusive", side_effect=replace_tree_and_fail):
            with self.assertRaisesRegex(OSError, "injected"):
                bpr._publish(self.files, self.packed, self.receipt, self.out, self.tar, self.manifest)
        self.assertEqual((self.out / "FOREIGN").read_text(encoding="utf-8"), "keep")

    def test_publication_paths_reject_aliases_and_finals_inside_tree(self):
        with self.assertRaisesRegex(ValueError, "distinct"):
            bpr._validate_publication_paths(self.out, self.out, self.manifest)
        with self.assertRaisesRegex(ValueError, "inside"):
            bpr._validate_publication_paths(self.out, self.out / "x.tar.gz", self.manifest)
        with self.assertRaisesRegex(ValueError, "inside"):
            bpr._validate_publication_paths(self.out, self.tar, self.out / "manifest.json")
        self.assertFalse(self.out.exists())

    def test_private_final_custody_helpers_are_gone(self):
        for name in ("_reserve", "_write_reserved", "_unlink_if_owned"):
            self.assertFalse(hasattr(bpr, name), name)
        self.assertIs(bpr.publish_exclusive, custody.publish_exclusive)


if __name__ == "__main__":
    unittest.main()
