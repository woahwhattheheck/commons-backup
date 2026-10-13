#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

import verify_archives as va


class ArchiveVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dock-v2-verify-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def build(
        self,
        *,
        source: bool,
        bad_hash: bool = False,
        extra: bool = False,
        omit: bool = False,
    ):
        path = self.root / ("source.zip" if source else "evidence.zip")
        relative = "payload.txt"
        payload = b"recovered bytes\n"
        record = {
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        if bad_hash:
            record["sha256"] = "0" * 64
        manifest_member = va.PREFIX + (
            "source-manifest.json" if source else "evidence-manifest.json"
        )
        manifest = {"files": {relative: record}} if source else {relative: record}
        with ZipFile(path, "w", ZIP_DEFLATED) as archive:
            if not omit:
                archive.writestr(va.PREFIX + relative, payload)
            archive.writestr(manifest_member, json.dumps(manifest, sort_keys=True))
            if source:
                archive.writestr(va.PREFIX + "notice.md", "notice\n")
            if extra:
                archive.writestr(va.PREFIX + "unexpected.bin", b"x")
        return path, path.stat().st_size, va.sha256_file(path), manifest_member

    def test_valid_source_shape(self):
        path, size, digest, manifest = self.build(source=True)
        result = va.verify_archive(
            path,
            expected_bytes=size,
            expected_outer_sha256=digest,
            manifest_member=manifest,
            records_field="files",
            allowed_extra_members=(va.PREFIX + "notice.md",),
        )
        self.assertEqual(result["manifest_payloads"], 1)
        self.assertEqual(result["member_set"], "EXACT")

    def test_valid_evidence_shape(self):
        path, size, digest, manifest = self.build(source=False)
        result = va.verify_archive(
            path,
            expected_bytes=size,
            expected_outer_sha256=digest,
            manifest_member=manifest,
            records_field=None,
        )
        self.assertEqual(result["archive_files"], 2)

    def test_outer_identity_mismatch_fails(self):
        path, size, _digest, manifest = self.build(source=False)
        with self.assertRaisesRegex(va.VerificationError, "outer sha256"):
            va.verify_archive(
                path,
                expected_bytes=size,
                expected_outer_sha256="f" * 64,
                manifest_member=manifest,
                records_field=None,
            )

    def test_manifest_payload_mismatch_fails(self):
        path, size, digest, manifest = self.build(source=False, bad_hash=True)
        with self.assertRaises(va.VerificationError):
            va.verify_archive(
                path,
                expected_bytes=size,
                expected_outer_sha256=digest,
                manifest_member=manifest,
                records_field=None,
            )

    def test_missing_payload_fails(self):
        path, size, digest, manifest = self.build(source=False, omit=True)
        with self.assertRaises(va.VerificationError):
            va.verify_archive(
                path,
                expected_bytes=size,
                expected_outer_sha256=digest,
                manifest_member=manifest,
                records_field=None,
            )

    def test_unexpected_member_fails(self):
        path, size, digest, manifest = self.build(source=False, extra=True)
        with self.assertRaises(va.VerificationError):
            va.verify_archive(
                path,
                expected_bytes=size,
                expected_outer_sha256=digest,
                manifest_member=manifest,
                records_field=None,
            )


if __name__ == "__main__":
    unittest.main()
