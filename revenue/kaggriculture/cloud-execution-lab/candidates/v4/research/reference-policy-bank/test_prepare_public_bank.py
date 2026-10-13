#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import sys
import tarfile
import tempfile
import unittest
import zipfile

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("prepare_public_bank", HERE / "prepare_public_bank.py")
assert SPEC and SPEC.loader
m = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = m
SPEC.loader.exec_module(m)


class ReforgeRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def make_runtime(self):
        root = self.root / "runtime"
        root.mkdir()
        entries = {}
        for identity, family in m.FAMILY.items():
            src = root / f"{identity}.source"
            src.write_text(identity + "\n", encoding="utf-8")
            entries[identity] = {
                "source": src.name,
                "source_sha256": m.sha256_file(src),
                "assignment": "scipy" if identity.endswith("scipy") else "greedy" if identity.endswith("greedy") else "not_applicable",
            }
        (root / "BANK.json").write_text(json.dumps({"entries": entries}), encoding="utf-8")
        files = {p.name: m.sha256_file(p) for p in root.iterdir() if p.is_file()}
        manifest = {
            "schema": m.SCHEMA,
            "entries": {identity: {"family": family} for identity, family in m.FAMILY.items()},
            "files": files,
        }
        (root / "REFORGE-BANK.json").write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        frozen = m.sha256_file(root / "REFORGE-BANK.json")
        return root, frozen

    def test_safe_rel_rejects_absolute_and_parent(self):
        for bad in ("/x", "../x", "a/../b", "./x", ""):
            with self.subTest(bad=bad), self.assertRaises(m.RecoveryError):
                m._safe_rel(bad)

    def test_zip_extract_accepts_regular_nested_file(self):
        z = self.root / "ok.zip"
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("a/b.txt", b"ok")
        out = self.root / "out"
        m.extract_zip_safe(z, out)
        self.assertEqual(b"ok", (out / "a/b.txt").read_bytes())

    def test_zip_extract_rejects_traversal(self):
        z = self.root / "bad.zip"
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("../escape", b"x")
        with self.assertRaises(m.RecoveryError):
            m.extract_zip_safe(z, self.root / "out")

    def test_zip_extract_rejects_symlink(self):
        z = self.root / "link.zip"
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(z, "w") as f:
            f.writestr(info, "target")
        with self.assertRaises(m.RecoveryError):
            m.extract_zip_safe(z, self.root / "out")

    def test_tar_extract_accepts_regular_file(self):
        t = self.root / "ok.tar"
        with tarfile.open(t, "w") as tf:
            data = b"ok"
            info = tarfile.TarInfo("a/b.txt")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        out = self.root / "tarout"
        m.extract_tar_safe(t, out)
        self.assertEqual(b"ok", (out / "a/b.txt").read_bytes())

    def test_tar_extract_rejects_link(self):
        t = self.root / "link.tar"
        with tarfile.open(t, "w") as tf:
            info = tarfile.TarInfo("link")
            info.type = tarfile.SYMTYPE
            info.linkname = "target"
            tf.addfile(info)
        with self.assertRaises(m.RecoveryError):
            m.extract_tar_safe(t, self.root / "tarout")

    def test_git_blob_matches_git_object_formula(self):
        p = self.root / "f"
        p.write_bytes(b"abc")
        expected = hashlib.sha1(b"blob 3\0abc").hexdigest()
        self.assertEqual(expected, m.git_blob(p))

    def test_verify_runtime_accepts_frozen_manifest(self):
        root, frozen = self.make_runtime()
        result = m.verify_runtime(root, frozen)
        self.assertEqual(m.SCHEMA, result["schema"])

    def test_verify_runtime_rejects_wrong_frozen_hash(self):
        root, _ = self.make_runtime()
        with self.assertRaisesRegex(m.RecoveryError, "caller-frozen"):
            m.verify_runtime(root, "0" * 64)

    def test_verify_runtime_rejects_file_tamper(self):
        root, frozen = self.make_runtime()
        (root / "cok-v10.source").write_text("tampered\n")
        with self.assertRaisesRegex(m.RecoveryError, "runtime file mismatch"):
            m.verify_runtime(root, frozen)

    def test_verify_runtime_rejects_family_relabel(self):
        root, _ = self.make_runtime()
        path = root / "REFORGE-BANK.json"
        manifest = json.loads(path.read_text())
        manifest["entries"]["lonespear-v18-scipy"]["family"] = "fake-independent-family"
        path.write_text(json.dumps(manifest, sort_keys=True))
        frozen = m.sha256_file(path)
        with self.assertRaisesRegex(m.RecoveryError, "family identity changed"):
            m.verify_runtime(root, frozen)

    def test_lonespear_modes_are_one_family(self):
        self.assertEqual(m.FAMILY["lonespear-v18-greedy"], m.FAMILY["lonespear-v18-scipy"])
        self.assertNotEqual(m.FAMILY["cok-v10"], m.FAMILY["lonespear-v18-scipy"])

    def test_pinned_public_source_hashes_are_distinct_and_complete(self):
        self.assertEqual({"cok-v10", "lonespear-v18"}, set(m.EXPECTED_SOURCE_SHA256))
        self.assertTrue(all(len(v) == 64 for v in m.EXPECTED_SOURCE_SHA256.values()))
        self.assertEqual(2, len(set(m.EXPECTED_SOURCE_SHA256.values())))


if __name__ == "__main__":
    unittest.main()
