from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("provision_from_artifact", HERE / "provision_from_artifact.py")
assert SPEC and SPEC.loader
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class RuntimeArtifactBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.pins_root = self.root / "pins"
        self.pins_root.mkdir()
        self.parent = self.root / "out"
        self.parent.mkdir()
        self.inner = b"small synthetic tar.zst placeholder"
        self.member = "cpython-9.9.9-x86_64-unknown-linux-gnu-test.tar.zst"

    def tearDown(self):
        self.tmp.cleanup()

    def make_zip(self, *, member=None, data=None, second_member=False) -> Path:
        member = member or self.member
        data = self.inner if data is None else data
        path = self.root / ("artifact-%d.zip" % len(list(self.root.glob("artifact-*.zip"))))
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
            zf.writestr(member, data)
            if second_member:
                zf.writestr("unexpected.txt", b"unexpected")
        return path

    def write_spec(self, archive: Path, *, zip_sha=None, archive_sha=None, member=None, zip_bytes=None):
        spec = {
            "version": "9.9.9",
            "minor": "9.9",
            "artifact_id": 1,
            "artifact_name": "synthetic",
            "zip_basename": archive.name,
            "zip_bytes": archive.stat().st_size if zip_bytes is None else zip_bytes,
            "zip_sha256": p.sha256(archive) if zip_sha is None else zip_sha,
            "archive_member": member or self.member,
            "repository": "example/repo",
            "workflow_run_id": 1,
            "workflow_source_head": "0" * 40,
            "archive_sha256": digest(self.inner) if archive_sha is None else archive_sha,
            "metadata_sha256": "1" * 64,
            "executable_sha256": "2" * 64,
        }
        (self.pins_root / "runtime_receipts.json").write_text(
            json.dumps({"artifacts": {"synthetic": spec}}), encoding="utf-8"
        )
        return spec

    def provision(self, archive: Path, output: Path, *, zstd="/usr/bin/zstd"):
        with mock.patch.object(p, "ROOT", self.pins_root), \
             mock.patch.object(p.platform, "system", return_value="Linux"), \
             mock.patch.object(p.platform, "machine", return_value="x86_64"), \
             mock.patch.object(p.shutil, "which", return_value=zstd):
            return p.provision("synthetic", archive, output)

    def test_retained_pins_are_exact(self):
        pins = json.loads((HERE / "runtime_receipts.json").read_text(encoding="utf-8"))["artifacts"]
        self.assertEqual(pins["python312"]["version"], "3.12.14")
        self.assertEqual(pins["python312"]["artifact_id"], 10477288847)
        self.assertEqual(pins["python312"]["zip_bytes"], 111935326)
        self.assertEqual(pins["python312"]["zip_sha256"], "c460be101a3b752ddffa1d66e2d10dc321ab073cec25cdb0b3bfcdf900df93d2")
        self.assertEqual(pins["python312"]["archive_sha256"], "a6446268edc9050c805bdcd377bcf69aa686ab6efd7c07721d1532d224e2cf61")
        self.assertEqual(pins["python312"]["executable_sha256"], "47c0b3b5141f9d709fd3966e65ab19e05feed14ac35b65bf9c627f6b03d862c2")
        self.assertEqual(pins["python310"]["version"], "3.10.21")
        self.assertEqual(pins["python310"]["artifact_id"], 10476749962)
        self.assertEqual(pins["python310"]["zip_bytes"], 65970874)
        self.assertEqual(pins["python310"]["zip_sha256"], "cc5b376f5ae4382962055d6de83d631ecdc49c0c365a1cab29bc74cc0ad544ed")
        self.assertEqual(pins["python310"]["archive_sha256"], "48f25876cfb351b6ee669d3a738723f30b4bb3515c16eab3b3917c9c13f7ff9e")
        self.assertEqual(pins["python310"]["executable_sha256"], "819dab3ec5ee5ef4a22a2d0fb7ffd0de3c7ea677e070800b711d972fc07367f7")
        for value in pins.values():
            self.assertEqual(value["workflow_run_id"], 35171964766)
            self.assertEqual(value["workflow_source_head"], "2aa6a42a1f8517541d2de167531ad2fd0a641fb6")
            self.assertEqual(value["workflow_event"], "push")
            self.assertEqual(value["workflow_conclusion"], "success")
            self.assertEqual(value["expires_at_utc"], "2026-12-16T01:48:24Z")

    def test_unknown_pin_refused(self):
        archive = self.make_zip()
        (self.pins_root / "runtime_receipts.json").write_text('{"artifacts":{}}', encoding="utf-8")
        with mock.patch.object(p, "ROOT", self.pins_root), \
             mock.patch.object(p.platform, "system", return_value="Linux"), \
             mock.patch.object(p.platform, "machine", return_value="x86_64"), \
             mock.patch.object(p.shutil, "which", return_value="/usr/bin/zstd"):
            with self.assertRaisesRegex(ValueError, "Unknown pinned runtime"):
                p.provision("synthetic", archive, self.parent / "runtime")

    def test_wrong_platform_refused_before_output(self):
        archive = self.make_zip(); self.write_spec(archive)
        with mock.patch.object(p, "ROOT", self.pins_root), \
             mock.patch.object(p.platform, "system", return_value="Darwin"), \
             mock.patch.object(p.platform, "machine", return_value="arm64"):
            with self.assertRaisesRegex(ValueError, "Linux x86_64"):
                p.provision("synthetic", archive, self.parent / "runtime")
        self.assertFalse((self.parent / "runtime").exists())

    def test_missing_zstd_refused_before_output(self):
        archive = self.make_zip(); self.write_spec(archive)
        with mock.patch.object(p, "ROOT", self.pins_root), \
             mock.patch.object(p.platform, "system", return_value="Linux"), \
             mock.patch.object(p.platform, "machine", return_value="x86_64"), \
             mock.patch.object(p.shutil, "which", return_value=None):
            with self.assertRaisesRegex(ValueError, "zstd"):
                p.provision("synthetic", archive, self.parent / "runtime")
        self.assertFalse((self.parent / "runtime").exists())

    def test_wrong_size_refused_before_output(self):
        archive = self.make_zip(); self.write_spec(archive, zip_bytes=archive.stat().st_size + 1)
        with self.assertRaisesRegex(ValueError, "byte count mismatch"):
            self.provision(archive, self.parent / "runtime")
        self.assertFalse((self.parent / "runtime").exists())

    def test_wrong_zip_digest_at_correct_size_refused_before_output(self):
        archive = self.make_zip(); self.write_spec(archive, zip_sha="0" * 64)
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.provision(archive, self.parent / "runtime")
        self.assertFalse((self.parent / "runtime").exists())

    def test_existing_destination_refused_and_preserved(self):
        archive = self.make_zip(); self.write_spec(archive)
        dest = self.parent / "runtime"; dest.mkdir(); marker = dest / "keep"; marker.write_text("keep")
        with self.assertRaisesRegex(ValueError, "must not exist"):
            self.provision(archive, dest)
        self.assertEqual(marker.read_text(), "keep")

    def test_dangling_destination_symlink_refused(self):
        archive = self.make_zip(); self.write_spec(archive)
        dest = self.parent / "runtime"; dest.symlink_to(self.parent / "missing")
        with self.assertRaisesRegex(ValueError, "must not exist"):
            self.provision(archive, dest)
        self.assertTrue(dest.is_symlink())

    def test_unexpected_zip_member_set_refused(self):
        archive = self.make_zip(second_member=True); self.write_spec(archive)
        with self.assertRaisesRegex(ValueError, "Unexpected ZIP member set"):
            self.provision(archive, self.parent / "runtime")
        self.assertFalse((self.parent / "runtime").exists())

    def test_wrong_member_name_refused(self):
        archive = self.make_zip(member="wrong.tar.zst"); self.write_spec(archive)
        with self.assertRaisesRegex(ValueError, "Unexpected ZIP member set"):
            self.provision(archive, self.parent / "runtime")

    def test_inner_archive_digest_refused_before_extraction(self):
        archive = self.make_zip(); self.write_spec(archive, archive_sha="f" * 64)
        with mock.patch.object(p.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "Inner archive SHA-256 mismatch"):
                self.provision(archive, self.parent / "runtime")
            run.assert_not_called()
        self.assertFalse((self.parent / "runtime").exists())

    def test_missing_parent_is_not_created(self):
        archive = self.make_zip(); self.write_spec(archive)
        dest = self.root / "missing-parent" / "runtime"
        with self.assertRaises(FileNotFoundError):
            self.provision(archive, dest)
        self.assertFalse(dest.parent.exists())

    def test_extractor_has_path_and_member_type_fences(self):
        source = (HERE / "extract_runtime.py").read_text(encoding="utf-8")
        for required in (
            "path.is_absolute()", "'..' in path.parts", "path.parts[0] != 'python'",
            "python/install/", "python/licenses/", "member.isfile()", "member.isdir()",
            "member.issym()", "filter='data'", "count > 20000", "total > 2 * 1024**3",
        ):
            self.assertIn(required, source)


if __name__ == "__main__":
    unittest.main()
