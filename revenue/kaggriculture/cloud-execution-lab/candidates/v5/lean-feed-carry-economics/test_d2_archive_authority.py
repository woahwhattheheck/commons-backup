import gzip
import hashlib
import io
import json
from pathlib import PurePosixPath
import tarfile
import unittest

import d2_archive_authority as authority


def git_blob(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def make_tar(entries):
    """entries: list[(name, kind, bytes|target)] preserving order."""
    raw = io.BytesIO()
    with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w") as tf:
            for name, kind, value in entries:
                info = tarfile.TarInfo(name)
                info.mtime = 0
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                if kind == "file":
                    data = value
                    info.size = len(data)
                    tf.addfile(info, io.BytesIO(data))
                elif kind == "dir":
                    info.type = tarfile.DIRTYPE
                    info.size = 0
                    tf.addfile(info)
                elif kind == "symlink":
                    info.type = tarfile.SYMTYPE
                    info.linkname = value
                    tf.addfile(info)
                elif kind == "hardlink":
                    info.type = tarfile.LNKTYPE
                    info.linkname = value
                    tf.addfile(info)
                elif kind == "sparse":
                    info.type = tarfile.GNUTYPE_SPARSE
                    info.size = 0
                    tf.addfile(info)
                else:
                    raise AssertionError(kind)
    return raw.getvalue()


def root_for(raw, entries, *, runtime_path="pkg/titan_runtime.py"):
    files = {name: value for name, kind, value in entries if kind == "file"}
    return authority.AuthorityRoot(
        archive_sha256=hashlib.sha256(raw).hexdigest(),
        archive_bytes=len(raw),
        member_count=len(entries),
        main_sha256=hashlib.sha256(files["pkg/main.py"]).hexdigest(),
        runtime_member=runtime_path,
        runtime_git_blob=git_blob(files[runtime_path]),
        helper_git_blob=git_blob(files["pkg/operating_stock.py"]),
    )


class ArchiveAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.entries = [
            ("pkg", "dir", b""),
            ("pkg/main.py", "file", b"print('main')\n"),
            ("pkg/titan_runtime.py", "file", b"class TitanAgent: pass\n"),
            ("pkg/operating_stock.py", "file", b"def protect_feed_stock(): pass\n"),
            ("pkg/other.txt", "file", b"x\n"),
        ]
        self.raw = make_tar(self.entries)
        self.root = root_for(self.raw, self.entries)

    def test_authenticates_exact_source_root(self):
        receipt = authority.audit_archive_bytes(self.raw, self.root)
        self.assertEqual(receipt["state"], "D2_SOURCE_AUTHENTICATED")
        self.assertTrue(receipt["source_authority_verified"])
        self.assertFalse(receipt["promotion_authorized"])
        self.assertFalse(receipt["execution_inputs_ready"])
        self.assertEqual(
            receipt["bindings"]["runtime"]["git_blob"],
            self.root.runtime_git_blob,
        )
        self.assertEqual(
            receipt["bindings"]["operating_stock"]["git_blob"],
            self.root.helper_git_blob,
        )

    def test_receipt_is_deterministic(self):
        a = authority.audit_archive_bytes(self.raw, self.root)
        b = authority.audit_archive_bytes(self.raw, self.root)
        self.assertEqual(a, b)
        self.assertEqual(
            a["receipt_sha256"],
            hashlib.sha256(
                authority._canonical_json(
                    {k: v for k, v in a.items() if k != "receipt_sha256"}
                )
            ).hexdigest(),
        )

    def test_archive_hash_mismatch_fails_closed(self):
        bad = authority.AuthorityRoot(
            "0" * 64, len(self.raw), len(self.entries),
            self.root.main_sha256, self.root.runtime_member,
            self.root.runtime_git_blob, self.root.helper_git_blob,
        )
        with self.assertRaisesRegex(authority.AuthorityError, "SHA-256 mismatch"):
            authority.audit_archive_bytes(self.raw, bad)

    def test_archive_size_mismatch_precedes_tar_trust(self):
        bad = authority.AuthorityRoot(
            self.root.archive_sha256, len(self.raw) + 1, len(self.entries),
            self.root.main_sha256, self.root.runtime_member,
            self.root.runtime_git_blob, self.root.helper_git_blob,
        )
        with self.assertRaisesRegex(authority.AuthorityError, "byte-size mismatch"):
            authority.audit_archive_bytes(self.raw, bad)

    def test_member_count_mismatch(self):
        bad = authority.AuthorityRoot(
            self.root.archive_sha256, len(self.raw), len(self.entries) + 1,
            self.root.main_sha256, self.root.runtime_member,
            self.root.runtime_git_blob, self.root.helper_git_blob,
        )
        with self.assertRaisesRegex(authority.AuthorityError, "member count mismatch"):
            authority.audit_archive_bytes(self.raw, bad)

    def test_runtime_blob_mismatch(self):
        bad = authority.AuthorityRoot(
            self.root.archive_sha256, len(self.raw), len(self.entries),
            self.root.main_sha256, self.root.runtime_member,
            "0" * 40, self.root.helper_git_blob,
        )
        with self.assertRaisesRegex(authority.AuthorityError, "runtime Git-blob"):
            authority.audit_archive_bytes(self.raw, bad)

    def test_helper_blob_missing(self):
        bad = authority.AuthorityRoot(
            self.root.archive_sha256, len(self.raw), len(self.entries),
            self.root.main_sha256, self.root.runtime_member,
            self.root.runtime_git_blob, "0" * 40,
        )
        with self.assertRaisesRegex(authority.AuthorityError, "operating_stock.py"):
            authority.audit_archive_bytes(self.raw, bad)

    def test_main_hash_mismatch(self):
        bad = authority.AuthorityRoot(
            self.root.archive_sha256, len(self.raw), len(self.entries),
            "0" * 64, self.root.runtime_member,
            self.root.runtime_git_blob, self.root.helper_git_blob,
        )
        with self.assertRaisesRegex(authority.AuthorityError, "main.py SHA-256 identity mismatch"):
            authority.audit_archive_bytes(self.raw, bad)

    def test_path_traversal_rejected_without_extraction(self):
        entries = self.entries + [("../escape", "file", b"bad")]
        raw = make_tar(entries)
        root = authority.AuthorityRoot(
            hashlib.sha256(raw).hexdigest(), len(raw), len(entries),
            self.root.main_sha256, self.root.runtime_member,
            self.root.runtime_git_blob, self.root.helper_git_blob,
        )
        with self.assertRaisesRegex(authority.AuthorityError, "not canonical"):
            authority.audit_archive_bytes(raw, root)

    def test_absolute_path_rejected(self):
        entries = self.entries + [("/tmp/escape", "file", b"bad")]
        raw = make_tar(entries)
        root = authority.AuthorityRoot(
            hashlib.sha256(raw).hexdigest(), len(raw), len(entries),
            self.root.main_sha256, self.root.runtime_member,
            self.root.runtime_git_blob, self.root.helper_git_blob,
        )
        with self.assertRaisesRegex(authority.AuthorityError, "absolute"):
            authority.audit_archive_bytes(raw, root)

    def test_symlink_rejected(self):
        entries = self.entries + [("pkg/link", "symlink", "pkg/main.py")]
        raw = make_tar(entries)
        root = authority.AuthorityRoot(
            hashlib.sha256(raw).hexdigest(), len(raw), len(entries),
            self.root.main_sha256, self.root.runtime_member,
            self.root.runtime_git_blob, self.root.helper_git_blob,
        )
        with self.assertRaisesRegex(authority.AuthorityError, "unsafe archive member type"):
            authority.audit_archive_bytes(raw, root)


    def test_hardlink_rejected(self):
        entries = self.entries + [("pkg/hard", "hardlink", "pkg/main.py")]
        raw = make_tar(entries)
        root = authority.AuthorityRoot(
            hashlib.sha256(raw).hexdigest(), len(raw), len(entries),
            self.root.main_sha256, self.root.runtime_member,
            self.root.runtime_git_blob, self.root.helper_git_blob,
        )
        with self.assertRaisesRegex(authority.AuthorityError, "unsafe archive member type"):
            authority.audit_archive_bytes(raw, root)

    def test_gnu_sparse_rejected(self):
        entries = self.entries + [("pkg/sparse.bin", "sparse", b"")]
        raw = make_tar(entries)
        root = authority.AuthorityRoot(
            hashlib.sha256(raw).hexdigest(), len(raw), len(entries),
            self.root.main_sha256, self.root.runtime_member,
            self.root.runtime_git_blob, self.root.helper_git_blob,
        )
        with self.assertRaisesRegex(authority.AuthorityError, "unsafe archive member type"):
            authority.audit_archive_bytes(raw, root)

    def test_second_main_py_rejected_even_if_one_hash_matches(self):
        entries = self.entries + [("other/main.py", "file", b"untrusted\n")]
        raw = make_tar(entries)
        root = authority.AuthorityRoot(
            hashlib.sha256(raw).hexdigest(), len(raw), len(entries),
            self.root.main_sha256, self.root.runtime_member,
            self.root.runtime_git_blob, self.root.helper_git_blob,
        )
        with self.assertRaisesRegex(authority.AuthorityError, "main.py binding"):
            authority.audit_archive_bytes(raw, root)

    def test_duplicate_member_rejected(self):
        entries = self.entries + [("pkg/other.txt", "file", b"y\n")]
        raw = make_tar(entries)
        root = authority.AuthorityRoot(
            hashlib.sha256(raw).hexdigest(), len(raw), len(entries),
            self.root.main_sha256, self.root.runtime_member,
            self.root.runtime_git_blob, self.root.helper_git_blob,
        )
        with self.assertRaisesRegex(authority.AuthorityError, "duplicate archive member"):
            authority.audit_archive_bytes(raw, root)

    def test_backslash_member_rejected(self):
        entries = self.entries + [(r"pkg\evil.py", "file", b"bad")]
        raw = make_tar(entries)
        root = authority.AuthorityRoot(
            hashlib.sha256(raw).hexdigest(), len(raw), len(entries),
            self.root.main_sha256, self.root.runtime_member,
            self.root.runtime_git_blob, self.root.helper_git_blob,
        )
        with self.assertRaisesRegex(authority.AuthorityError, "backslash"):
            authority.audit_archive_bytes(raw, root)

    def test_blocked_receipt_is_fail_closed_and_stable(self):
        a = authority.blocked_receipt()
        b = authority.blocked_receipt()
        self.assertEqual(a, b)
        self.assertEqual(a["state"], "D2_SOURCE_BYTES_ABSENT")
        self.assertFalse(a["source_authority_verified"])
        self.assertFalse(a["promotion_authorized"])
        self.assertEqual(
            a["required_archive"]["sha256"],
            authority.D2_ARCHIVE_SHA256,
        )


if __name__ == "__main__":
    unittest.main()
