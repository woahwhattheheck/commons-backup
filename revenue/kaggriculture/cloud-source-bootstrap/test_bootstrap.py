# SPDX-License-Identifier: MIT
"""Offline archive fixtures plus opt-in readback of the actual shared artifacts."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
import warnings
import zipfile
from unittest import mock

import bootstrap as b


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.engine_files = {"kaggriculture.py": b"# engine\n", "kaggriculture.json": b"{}\n",
                             "utils.py": b"# utilities\n", "LICENSE": b"engine license\n"}
        self.engine_ref = "1" * 40
        pins = {n: b.blob(data) for n, data in self.engine_files.items() if n != "LICENSE"}
        self.files = {
            b.EVALUATOR: f"ENGINE_REF = {self.engine_ref!r}\nENGINE_BLOBS = {pins!r}\n".encode(),
            b.BASE + "cloud-pack/official.py": b"raise RuntimeError('must not execute')\n",
            b.BASE + "cloud-pack/pack.py": b"# pack adapter\n",
            b.BASE + "cloud-frontier-policy/next-panel/vendor/arlene.py": b"# arlene\n",
            b.BASE + "cloud-titan-composition/arms/sell.py": b"# sell snapshot\n",
            b.BASE + "cloud-titan-composition/NOTICE.md": b"Attribution preserved\n",
        }
        self.sources, self.engine = self.root / "sources.zip", self.root / "engine.zip"
        self.output = self.root / "out"
        self.write_engine()
        self.write_source()

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def metadata(data):
        return {"size_bytes": len(data), "sha256": b.sha256(data), "git_blob": b.blob(data)}

    def write_engine(self):
        with zipfile.ZipFile(self.engine, "w") as z:
            for name, data in self.engine_files.items():
                z.writestr("engine/" + name, data)
            z.writestr("historical-policy.py", "raise RuntimeError('never extract/run me')")

    def write_source(self, change_manifest=None, extra_member=None, duplicate_zip=False):
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w") as t:
            for name, data in self.files.items():
                item = tarfile.TarInfo(name)
                item.size = len(data)
                t.addfile(item, io.BytesIO(data))
            if extra_member:
                t.addfile(*extra_member)
        tar_data = raw.getvalue()
        checkpoint = b"unchanged archived checkpoint; never executed"
        manifest = {
            "schema": "titan.pinned-source-export.v2", "source_commit": "2" * 40,
            "archives": {b.SOURCE_TAR: self.metadata(tar_data),
                         "carrot-cap-checkpoint.tar.gz": self.metadata(checkpoint)},
            "files": {n: self.metadata(d) for n, d in self.files.items()},
            "engine_artifact": {**self.metadata(self.engine.read_bytes()),
                                "engine_ref": self.engine_ref, "cache_subdirectory": "engine"},
        }
        if change_manifest:
            change_manifest(manifest)
        with warnings.catch_warnings(), zipfile.ZipFile(self.sources, "w") as z:
            warnings.simplefilter("ignore", UserWarning)
            z.writestr(b.MANIFEST, json.dumps(manifest))
            z.writestr(b.SOURCE_TAR, tar_data)
            z.writestr("carrot-cap-checkpoint.tar.gz", checkpoint)
            z.writestr("REUSE.md", "Frozen snapshot, not the latest policy.\n")
            if duplicate_zip:
                z.writestr(b.MANIFEST, json.dumps(manifest))
        self.source_digest = b.sha256(self.sources.read_bytes())

    def run_prepare(self):
        return b.prepare(self.sources, self.engine, self.output, self.source_digest)

    def assert_rejected(self, pattern):
        with self.assertRaisesRegex((ValueError, FileNotFoundError, KeyError), pattern):
            self.run_prepare()
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob("titan-bootstrap-*")))

    def test_real_output_layout_and_receipt(self):
        before = (self.sources.read_bytes(), self.engine.read_bytes())
        receipt = self.run_prepare()
        self.assertEqual(receipt["source_file_count"], len(self.files))
        self.assertEqual(receipt["games"], 0)
        self.assertFalse(receipt["candidate_executed"])
        for name, data in self.files.items():
            self.assertEqual((self.output / "sources" / name).read_bytes(), data)
        for name, data in self.engine_files.items():
            self.assertEqual((self.output / "engine" / name).read_bytes(), data)
        self.assertEqual(json.loads((self.output / "workspace.json").read_text()), receipt)
        self.assertFalse((self.output / "historical-policy.py").exists())
        self.assertEqual(before, (self.sources.read_bytes(), self.engine.read_bytes()))
        self.assertEqual((self.output / "transport/carrot-cap-checkpoint.tar.gz").read_bytes(),
                         b"unchanged archived checkpoint; never executed")

    def test_existing_output_is_never_overwritten(self):
        self.output.mkdir()
        sentinel = self.output / "peer-work"
        sentinel.write_bytes(b"keep")
        with self.assertRaises(FileExistsError):
            self.run_prepare()
        self.assertEqual(sentinel.read_bytes(), b"keep")

    def test_output_symlink_is_not_followed(self):
        target = self.root / "missing-peer-work"
        self.output.symlink_to(target)
        with self.assertRaises(FileExistsError):
            self.run_prepare()
        self.assertTrue(self.output.is_symlink())
        self.assertFalse(target.exists())

    def test_same_inputs_in_new_directories_are_identical(self):
        first = self.run_prepare()
        first_files = {str(p.relative_to(self.output)): p.read_bytes()
                       for p in self.output.rglob("*") if p.is_file()}
        self.output = self.root / "out2"
        self.assertEqual(first, self.run_prepare())
        second_files = {str(p.relative_to(self.output)): p.read_bytes()
                        for p in self.output.rglob("*") if p.is_file()}
        self.assertEqual(first_files, second_files)

    def test_source_zip_digest(self):
        self.source_digest = "0" * 64
        self.assert_rejected("Source ZIP differs")

    def test_source_digest_format(self):
        self.source_digest = "not-a-digest"
        self.assert_rejected("lowercase SHA-256")

    def test_engine_zip_digest(self):
        self.engine.write_bytes(self.engine.read_bytes() + b"changed")
        self.assert_rejected("engine ZIP")

    def test_source_member_hash(self):
        def change(m):
            m["files"][b.EVALUATOR]["sha256"] = "0" * 64
        self.write_source(change)
        self.assert_rejected("SHA-256 mismatch")

    def test_source_member_git_blob(self):
        def change(m):
            m["files"][b.EVALUATOR]["git_blob"] = "0" * 40
        self.write_source(change)
        self.assert_rejected("Git blob mismatch")

    def test_missing_source_member(self):
        def change(m):
            m["files"]["missing.py"] = self.metadata(b"")
        self.write_source(change)
        self.assert_rejected("member set")

    def test_archive_digest(self):
        def change(m):
            m["archives"][b.SOURCE_TAR]["sha256"] = "0" * 64
        self.write_source(change)
        self.assert_rejected("SHA-256 mismatch")

    def test_rejects_older_incomplete_schema(self):
        self.write_source(lambda m: m.update(schema="titan.pinned-source-export.v1"))
        self.assert_rejected("Expected v2")

    def test_ref_mismatch(self):
        def change(m):
            m["engine_artifact"]["engine_ref"] = "3" * 40
        self.write_source(change)
        self.assert_rejected("Engine ref differs")

    def test_engine_blob_not_only_zip_digest(self):
        self.engine_files["utils.py"] = b"changed engine\n"
        self.write_engine()
        self.write_source()  # ZIP receipt updated; evaluator's original pin still differs.
        self.assert_rejected("Official engine blob mismatch")

    def test_path_traversal(self):
        item = tarfile.TarInfo("../escape")
        self.write_source(extra_member=(item, io.BytesIO(b"")))
        self.assert_rejected("Noncanonical")
        self.assertFalse((self.root / "escape").exists())

    def test_noncanonical_paths(self):
        for name in ("/absolute", "a//b", "a/./b", "a/../b", "C:/file", "a\\b", "", "a\0b"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                b.relative_name(name)

    def test_symbolic_link(self):
        item = tarfile.TarInfo("shortcut")
        item.type = tarfile.SYMTYPE
        item.linkname = "../escape"
        self.write_source(extra_member=(item, None))
        self.assert_rejected("nonregular")

    def test_duplicate_tar_member(self):
        name = b.EVALUATOR
        item = tarfile.TarInfo(name)
        item.size = len(self.files[name])
        self.write_source(extra_member=(item, io.BytesIO(self.files[name])))
        self.assert_rejected("Duplicate TAR")

    def test_duplicate_zip_member(self):
        self.write_source(duplicate_zip=True)
        self.assert_rejected("Duplicate ZIP")

    def test_failed_write_has_no_partial_workspace(self):
        with mock.patch.object(Path, "write_bytes", side_effect=OSError("disk unavailable")):
            with self.assertRaisesRegex(OSError, "disk unavailable"):
                self.run_prepare()
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob("titan-bootstrap-*")))

    def test_cli_success_and_failure_are_structured(self):
        command = [sys.executable, str(Path(b.__file__)), "--sources-zip", str(self.sources),
                   "--source-sha256", self.source_digest, "--engine-zip", str(self.engine),
                   "--output", str(self.output)]
        first = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(first.stdout)["source_file_count"], len(self.files))
        again = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(again.returncode, 2)
        self.assertIn("Use a new output directory", again.stderr)
        self.assertNotIn("Traceback", again.stderr)


@unittest.skipUnless(os.environ.get("TITAN_REAL_SOURCES_ZIP") and os.environ.get("TITAN_REAL_ENGINE_ZIP")
                     and os.environ.get("TITAN_REAL_SOURCE_SHA256"), "shared artifacts not supplied")
class RealTransportTests(unittest.TestCase):
    def test_all_real_members_and_official_offline_loader(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "workspace"
            receipt = b.prepare(Path(os.environ["TITAN_REAL_SOURCES_ZIP"]),
                                Path(os.environ["TITAN_REAL_ENGINE_ZIP"]), root,
                                os.environ["TITAN_REAL_SOURCE_SHA256"])
            paths = receipt["paths_relative_to_workspace"]
            probe = r'''
import importlib.util, json, pathlib, socket, sys
root = pathlib.Path(sys.argv[1])
paths = json.loads((root / "workspace.json").read_text())["paths_relative_to_workspace"]
def no_network(*args, **kwargs):
    raise AssertionError("offline bootstrap loader attempted network")
socket.socket = no_network
socket.create_connection = no_network
spec = importlib.util.spec_from_file_location("bootstrap_real_eval", root / paths["evaluator"])
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)
engine, hashes = ev.get_engine(root / paths["engine"])
assert callable(engine.interpreter)
assert len(hashes) == 3
loader_spec = importlib.util.spec_from_file_location("bootstrap_real_official", root / paths["file_loader"])
loader = importlib.util.module_from_spec(loader_spec)
loader_spec.loader.exec_module(loader)
assert callable(loader.contract()["build_agent"])
print(json.dumps({"engine_loaded": True, "file_loader_loaded": True, "engine_files": len(hashes), "games": 0}))
'''
            result = subprocess.run([sys.executable, "-B", "-c", probe, str(root)],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)["engine_loaded"])
            manifest = json.loads((root / "transport" / b.MANIFEST).read_text())
            self.assertEqual(receipt["source_file_count"], len(manifest["files"]))
            for name, item in manifest["files"].items():
                self.assertEqual(b.sha256((root / "sources" / name).read_bytes()), item["sha256"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
