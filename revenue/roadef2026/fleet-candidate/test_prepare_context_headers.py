"""Regression for the actual pinned checker's extensionless sparsehash headers."""
import tempfile
import unittest
from pathlib import Path
import zipfile

from prepare_context import ARCHIVES, copy_archive_sources


class NetworktoolsHeadersTest(unittest.TestCase):
    def extract(self, members, destination):
        archive = destination / "networktools.zip"
        with zipfile.ZipFile(archive, "w") as stream:
            stream.writestr("pinned/networktools/networktools.h", b"// project marker\n")
            for name, content in members.items():
                stream.writestr("pinned/" + name, content)
        copy_archive_sources(archive, "networktools", ARCHIVES["networktools"], destination)

    def test_all_six_extensionless_public_headers_preserve_exact_bytes(self):
        names = ("dense_hash_map", "dense_hash_set", "sparse_hash_map",
                 "sparse_hash_set", "sparsetable", "traits")
        members = {"networktools/@deps/sparsehash/" + name:
                   ("// " + name + "\r\n").encode() for name in names}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.extract(members, root)
            for name, expected in members.items():
                with self.subTest(header=name):
                    path = root / "sources/networktools" / name
                    self.assertTrue(path.is_file(), str(path))
                    self.assertEqual(path.read_bytes(), expected)

    def test_existing_sources_and_license_remain_scoped(self):
        members = {
            "networktools/@deps/sparsehash/internal/densehashtable.h": b"// internal header\n",
            "networktools/@deps/sparsehash/LICENSE": b"license\n",
            "networktools/@deps/sparsehash/README": b"documentation\n",
            "networktools/@deps/sparsehash/arbitrary": b"not a known header\n",
            "networktools/@deps/other/dense_hash_map": b"outside sparsehash\n",
            "networktools/@deps/sparsehash/internal/traits": b"outside public header root\n",
        }
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.extract(members, root)
            staged = root / "sources/networktools"
            header = "networktools/@deps/sparsehash/internal/densehashtable.h"
            self.assertEqual((staged / header).read_bytes(), members[header])
            self.assertEqual((root / "attribution/networktools-dependencies/sparsehash/LICENSE").read_bytes(), b"license\n")
            for name in list(members)[2:]:
                with self.subTest(excluded=name):
                    self.assertFalse((staged / name).exists())


if __name__ == "__main__":
    unittest.main()
