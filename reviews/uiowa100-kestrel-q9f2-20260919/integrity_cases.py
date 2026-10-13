"""Independent synthetic integrity regressions for Commons PR #16249.

Tests use the original author's tiny packaging fixtures. This does not execute
or establish the real compiler/workbench integration acceptance.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import zipfile

import test_uiowa100_portability as baseline

p = baseline.p


class IntegrityRegressionTests(unittest.TestCase):
    setUp = baseline.PortabilityTests.setUp
    package = baseline.PortabilityTests.package

    def manifest(self):
        return p.source_manifest(p.source_closure(self.root), baseline.REVISION)

    def test_git_blob_metadata_matches_git_itself(self):
        for raw in (b"", b"hello\n", "naive: caf\u00e9\n".encode(), bytes(range(256))):
            with self.subTest(raw_length=len(raw)):
                expected = subprocess.run(
                    ["git", "hash-object", "--stdin"], input=raw,
                    capture_output=True, check=True, timeout=10,
                ).stdout.decode("ascii").strip()
                row = p.source_manifest({"fixture.bin": raw}, baseline.REVISION)["files"][0]
                self.assertEqual(row["git_blob_sha1"], expected)
                self.assertEqual(row["sha256"], hashlib.sha256(raw).hexdigest())

    def test_git_blob_metadata_is_required(self):
        data = self.manifest()
        del data["files"][0]["git_blob_sha1"]
        with self.assertRaisesRegex(p.PortabilityError, "blob"):
            p.validate_manifest(data)

    def test_git_blob_metadata_requires_full_lowercase_digest(self):
        for bad in (None, False, 3, [], {}, "", "F" * 40, "z" * 40, "f" * 39, "f" * 41):
            with self.subTest(bad=bad):
                data = self.manifest()
                data["files"][0]["git_blob_sha1"] = bad
                with self.assertRaisesRegex(p.PortabilityError, "blob"):
                    p.validate_manifest(data)

    def test_verify_checks_git_blob_against_member_bytes(self):
        destination = self.package()
        manifest_path = destination / p.MANIFEST
        data = json.loads(manifest_path.read_text())
        data["files"][0]["git_blob_sha1"] = "0" * 40
        manifest_path.write_bytes(p.canonical(data))
        with self.assertRaisesRegex(p.PortabilityError, "blob"):
            p.verify(destination)

    def test_unpack_checks_git_blob_before_creating_destination(self):
        original = self.home / "original.zip"
        altered = self.home / "altered.zip"
        p.pack(self.root, original, baseline.REVISION)
        with zipfile.ZipFile(original) as source:
            with zipfile.ZipFile(altered, "w", compression=zipfile.ZIP_STORED) as target:
                for info in source.infolist():
                    raw = source.read(info.filename)
                    if info.filename == p.MANIFEST:
                        data = json.loads(raw)
                        data["files"][0]["git_blob_sha1"] = "0" * 40
                        raw = p.canonical(data)
                    target.writestr(info, raw)
        output = self.home / "must-not-exist"
        with self.assertRaisesRegex(p.PortabilityError, "blob"):
            p.unpack(altered, output)
        self.assertFalse(output.exists())

    def test_rejection_does_not_rewrite_manifest_or_source(self):
        destination = self.package()
        manifest_path = destination / p.MANIFEST
        data = json.loads(manifest_path.read_text())
        data["files"][0]["git_blob_sha1"] = "0" * 40
        manifest_path.write_bytes(p.canonical(data))
        before = {str(f.relative_to(destination)): f.read_bytes()
                  for f in destination.rglob("*") if f.is_file()}
        with self.assertRaisesRegex(p.PortabilityError, "blob"):
            p.verify(destination)
        after = {str(f.relative_to(destination)): f.read_bytes()
                 for f in destination.rglob("*") if f.is_file()}
        self.assertEqual(before, after)

    def test_malformed_trust_is_a_typed_validation_failure(self):
        for bad in (None, [], 1, False, "UNKNOWN"):
            with self.subTest(trust=bad):
                report = copy.deepcopy(baseline.reference_report())
                report["trust"] = bad
                with self.assertRaises(p.PortabilityError):
                    p.inspection_assertions(report)

    def test_malformed_report_retains_fail_not_running_receipt(self):
        destination = self.package()
        output = self.home / "malformed-report-run"
        report = baseline.reference_report()
        report["trust"] = None

        # A synthetic faulty producer exercises the runner's error contract;
        # this is not a claim that the real upstream compiler emits this shape.
        def fake_process(argv, **kwargs):
            if "compile" in argv:
                Path(argv[-1]).write_bytes(p.canonical(report))
                stdout = "fixture compile\n"
            elif "verify" in argv:
                stdout = "UNTRUSTED_INTEGRITY_ONLY fixture\n"
            elif "render" in argv:
                Path(argv[-1]).write_text("# Synthetic malformed-report fixture\n")
                stdout = "fixture render\n"
            else:
                raise AssertionError("malformed report should stop before the adapter")
            return subprocess.CompletedProcess(argv, 0, stdout, "")

        caught = None
        with patch.object(p.subprocess, "run", side_effect=fake_process):
            try:
                p.rehearse(destination, output)
            except Exception as exc:
                caught = exc
        receipt = json.loads((output / "receipt.json").read_text())
        self.assertEqual(receipt["state"], "FAIL")
        self.assertIsInstance(caught, p.PortabilityError)
        self.assertIn("trust", receipt["error"])
        self.assertNotIn("outputs", receipt)
        self.assertEqual([row["step"] for row in receipt["commands"]],
                         ["compiler_compile", "compiler_verify", "compiler_render"])

    def test_valid_report_retains_non_authorizing_mode(self):
        report = baseline.reference_report()
        result = p.inspection_assertions(report)
        self.assertEqual(result["cells"], 12)
        self.assertEqual(result["aggregate_state"], "HOLD_TRUSTED_AUTHORITY_REQUIRED")
        self.assertFalse(report["trust"]["current_evidence_review_authority"])


if __name__ == "__main__":
    unittest.main()
