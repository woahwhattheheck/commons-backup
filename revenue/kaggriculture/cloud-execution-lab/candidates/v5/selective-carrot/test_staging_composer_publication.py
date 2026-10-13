import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import publication_custody as pc
import staging_composer as sc


class PublicationCustodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_composer_delegates_exact_pair_to_shared_primitive(self):
        out = self.root / "candidate.tar.gz"
        receipt = self.root / "receipt.json"
        with patch.object(sc, "publish_exclusive") as delegated:
            sc.publish_pair(out, receipt, b"archive-payload", b"receipt-payload")
        delegated.assert_called_once_with((
            (out, b"archive-payload"),
            (receipt, b"receipt-payload"),
        ))

    def test_private_publication_implementation_is_retired(self):
        self.assertFalse(hasattr(sc, "_write_all"))
        self.assertFalse(hasattr(sc, "_verify_owned_final"))
        self.assertFalse(hasattr(sc, "_fsync_directory"))
        self.assertFalse(hasattr(sc, "_unlink_if_owned"))
        self.assertIs(sc.publish_exclusive, pc.publish_exclusive)

    def test_success_publishes_exact_pair(self):
        out = self.root / "candidate.tar.gz"
        receipt = self.root / "receipt.json"
        sc.publish_pair(out, receipt, b"archive-payload", b"receipt-payload")
        self.assertEqual(out.read_bytes(), b"archive-payload")
        self.assertEqual(receipt.read_bytes(), b"receipt-payload")

    def test_equal_paths_fail_before_shared_publication(self):
        out = self.root / "same.final"
        with patch.object(sc, "publish_exclusive") as delegated:
            with self.assertRaisesRegex(sc.ComposerError, "paths must differ"):
                sc.publish_pair(out, out, b"archive", b"receipt")
        delegated.assert_not_called()
        self.assertFalse(out.exists())

    def test_shared_value_error_preserves_composer_error_surface(self):
        out = self.root / "candidate.tar.gz"
        receipt = self.root / "receipt.json"
        with patch.object(
            sc, "publish_exclusive", side_effect=ValueError("publication paths must be distinct")
        ):
            with self.assertRaisesRegex(sc.ComposerError, "paths must be distinct"):
                sc.publish_pair(out, receipt, b"archive", b"receipt")

    def test_shared_rollback_removes_owned_pair_on_write_failure(self):
        out = self.root / "candidate.tar.gz"
        receipt = self.root / "receipt.json"
        real_write = pc._write_all
        writes = 0

        def fail_second_write(fd, payload):
            nonlocal writes
            writes += 1
            if writes == 2:
                raise OSError("root publication failure")
            real_write(fd, payload)

        with patch.object(pc, "_write_all", side_effect=fail_second_write):
            with self.assertRaisesRegex(OSError, "root publication failure"):
                sc.publish_pair(out, receipt, b"archive", b"receipt")
        self.assertFalse(out.exists())
        self.assertFalse(receipt.exists())

    def test_shared_custody_preserves_foreign_replacement(self):
        out = self.root / "candidate.tar.gz"
        receipt = self.root / "receipt.json"
        real_verify = pc._verify_final
        verifies = 0

        def replace_before_first_verify(item):
            nonlocal verifies
            verifies += 1
            if verifies == 1:
                if os.name == "nt":
                    os.close(item.fd)
                item.path.unlink()
                item.path.write_bytes(b"foreign-sentinel")
            return real_verify(item)

        with patch.object(pc, "_verify_final", side_effect=replace_before_first_verify):
            with self.assertRaisesRegex(OSError, "identity changed"):
                sc.publish_pair(out, receipt, b"archive", b"receipt")
        self.assertEqual(out.read_bytes(), b"foreign-sentinel")
        self.assertFalse(receipt.exists())


if __name__ == "__main__":
    unittest.main()
