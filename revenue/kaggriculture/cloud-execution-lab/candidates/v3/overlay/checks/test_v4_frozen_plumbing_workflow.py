# SPDX-License-Identifier: Apache-2.0
"""Regression: V4 candidates must carry the frozen titan-v4-plumbing workflow blob.

titan-v4-trust-root (pull_request_target on main) authenticates
`.github/workflows/titan-v4-plumbing.yml` as one ordinary 100644 Git blob
`2a1800c02d2a4c11293bdccc7914ab8f6fd93321`. A missing path fails closed with
"candidate is missing .github/workflows/titan-v4-plumbing.yml".
"""
from __future__ import annotations

import hashlib
import stat
import tempfile
import unittest
from pathlib import Path

APPROVED_WORKFLOW_BLOB = "2a1800c02d2a4c11293bdccc7914ab8f6fd93321"
WORKFLOW_REL = Path(".github/workflows/titan-v4-plumbing.yml")
MISSING_MSG = "candidate is missing .github/workflows/titan-v4-plumbing.yml"


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def find_workflow(start: Path) -> Path:
    for candidate in (start.resolve(), *start.resolve().parents):
        marker = candidate / WORKFLOW_REL
        if marker.is_file():
            return marker
    raise FileNotFoundError(MISSING_MSG)


class FrozenPlumbingWorkflowTests(unittest.TestCase):
    def test_workflow_is_ordinary_file_with_approved_blob(self):
        path = find_workflow(Path(__file__))
        self.assertTrue(path.is_file(), f"missing {WORKFLOW_REL}")
        st = path.stat()
        self.assertTrue(stat.S_ISREG(st.st_mode), "workflow must be a regular file")
        self.assertFalse(path.is_symlink(), "workflow must not be a symlink")
        data = path.read_bytes()
        self.assertTrue(data.startswith(b"name: titan-v4-plumbing\n"))
        self.assertEqual(_git_blob_sha(data), APPROVED_WORKFLOW_BLOB)

    def test_missing_path_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            isolated = Path(tmp) / "isolated-candidate"
            isolated.mkdir()
            with self.assertRaises(FileNotFoundError) as ctx:
                find_workflow(isolated)
        self.assertEqual(str(ctx.exception), MISSING_MSG)

    def test_byte_drift_is_rejected(self):
        data = find_workflow(Path(__file__)).read_bytes()
        self.assertNotEqual(_git_blob_sha(data + b"\n"), APPROVED_WORKFLOW_BLOB)
        self.assertNotEqual(_git_blob_sha(b""), APPROVED_WORKFLOW_BLOB)


if __name__ == "__main__":
    unittest.main()
