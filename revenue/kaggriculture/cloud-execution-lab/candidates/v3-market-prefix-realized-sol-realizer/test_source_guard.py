# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from source_guard import git_blob_sha1


class SourceGuardTests(unittest.TestCase):
    def test_git_blob_hash_is_length_delimited(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "x"
            path.write_bytes(b"test\n")
            self.assertEqual(git_blob_sha1(path), "9daeafb9864cf43055ae93beb0afd6c7d144bfa4")


if __name__ == "__main__":
    unittest.main()
