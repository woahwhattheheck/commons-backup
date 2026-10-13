#!/usr/bin/env python3
"""Offline failure/retry checks for the real build-context preparation function.

Only archive pins and runtime inputs are synthetic. Real ZIP validation, hashing,
extraction, file copying, required-source checks and manifest writing execute.
No compiler, solver, checker binary, provider or network service is invoked.
"""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile


ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "roadef_prepare_transaction_target", ROOT / "prepare_context.py")
prep = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prep)


class PrepareContextTransactionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="roadef-prep-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.runtime = self.root / "runtime"
        self.archives = self.root / "archives"
        self.runtime.mkdir()
        self.archives.mkdir()
        self.destination = self.root / "output" / "context"
        self.candidate = self.runtime / "main.cpp"
        self.candidate.write_bytes(b"// synthetic candidate, never compiled\n")
        for name in ("run.sh", "supervisor.py", "compare_checker.py", "build.sh",
                     "Dockerfile", "README.md", "ATTRIBUTION.md", ".dockerignore"):
            (self.runtime / name).write_bytes(("synthetic runtime " + name + "\n").encode())
        self.members = {
            "sedge": {
                "sedge-roadef-solver/main.cpp": b"// synthetic sedge\n",
                "sedge-roadef-solver/vendor/rapidjson-LICENSE": b"synthetic license\n",
                "sedge-roadef-solver/vendor/rapidjson/document.h": b"// synthetic header\n",
                "sedge-roadef-solver/LICENSE": b"synthetic sedge license\n"},
            "flora": {"cloud-optimizer/main.cpp": b"// synthetic flora\n",
                      "cloud-optimizer/LICENSE": b"synthetic flora license\n"},
            "checker": {"official-root/checker/src/main.cpp": b"// synthetic checker\n",
                        "official-root/checker/src/CLI11.hpp": b"// synthetic CLI header\n",
                        "official-root/LICENSE": b"synthetic checker license\n"},
            "networktools": {
                "network-root/networktools/networktools.h": b"// synthetic networktools\n",
                "network-root/networktools/@deps/sparsehash/dense_hash_map": b"// extensionless header\n",
                "network-root/networktools/@deps/sparsehash/README": b"not a source header\n",
                "network-root/LICENSE": b"synthetic networktools license\n"},
        }
        self.pins = {name: dict(spec) for name, spec in prep.ARCHIVES.items()}
        for name in self.members:
            self.write_archive(name)
        pins = mock.patch.object(prep, "ARCHIVES", self.pins)
        pins.start()
        self.addCleanup(pins.stop)
        network = mock.patch.object(prep.urllib.request, "urlopen",
                                    side_effect=AssertionError("unexpected network"))
        self.network = network.start()
        self.addCleanup(network.stop)

    def write_archive(self, name):
        path = self.archives / self.pins[name]["file"]
        with zipfile.ZipFile(path, "w") as archive:
            for member, raw in self.members[name].items():
                info = zipfile.ZipInfo(member, date_time=(2026, 1, 1, 0, 0, 0))
                archive.writestr(info, raw)
        self.pins[name]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.pins[name]["url"] = "https://example.invalid/offline-fixture/" + path.name

    def prepare(self):
        return prep.prepare(self.destination, self.runtime, self.candidate, self.archives)

    def assert_no_context(self):
        self.assertFalse(self.destination.exists(), "failed preparation retained a partial context")
        self.network.assert_not_called()

    def assert_manifest(self, manifest):
        saved = json.loads((self.destination / "source-manifest.json").read_text())
        self.assertEqual(saved, manifest)
        self.assertFalse(saved["submitted"])
        self.assertEqual(saved["stage_version"], 2)
        paths = {row["path"] for row in saved["files"]}
        actual = {path.relative_to(self.destination).as_posix()
                  for path in self.destination.rglob("*") if path.is_file()}
        self.assertEqual(paths, actual - {"source-manifest.json"})
        for row in saved["files"]:
            self.assertEqual(row["sha256"], prep.sha256(self.destination / row["path"]))
        self.assertEqual((self.destination / "sources/candidate/main.cpp").read_bytes(),
                         self.candidate.read_bytes())
        self.network.assert_not_called()

    def test_success_preserves_all_payloads_and_manifest(self):
        self.assert_manifest(self.prepare())
        self.assertEqual((self.destination / ".dockerignore").read_bytes(),
                         (self.runtime / ".dockerignore").read_bytes())
        # Carry forward QUARTZ's extensionless-header extraction without broadening it.
        headers = self.destination / "sources/networktools/networktools/@deps/sparsehash"
        self.assertEqual((headers / "dense_hash_map").read_bytes(), b"// extensionless header\n")
        self.assertFalse((headers / "README").exists())

    def test_success_without_optional_dockerignore(self):
        (self.runtime / ".dockerignore").unlink()
        self.assert_manifest(self.prepare())
        self.assertFalse((self.destination / ".dockerignore").exists())

    def test_missing_staged_source_cleans_context_and_allows_retry(self):
        raw = self.members["checker"].pop("official-root/checker/src/CLI11.hpp")
        self.write_archive("checker")
        with self.assertRaisesRegex(ValueError, "Missing required staged source"):
            self.prepare()
        self.assert_no_context()
        self.members["checker"]["official-root/checker/src/CLI11.hpp"] = raw
        self.write_archive("checker")
        self.assert_manifest(self.prepare())

    def test_missing_license_cleans_context(self):
        self.members["sedge"].pop("sedge-roadef-solver/vendor/rapidjson-LICENSE")
        self.write_archive("sedge")
        with self.assertRaises(FileNotFoundError):
            self.prepare()
        self.assert_no_context()

    def test_extraction_failure_preserves_exception_and_inputs(self):
        failure = OSError("synthetic extraction I/O failure")
        real_copy = prep.copy_archive_sources
        before = {p: p.read_bytes() for folder in (self.runtime, self.archives)
                  for p in folder.rglob("*") if p.is_file()}
        def copy_then_fail(archive, name, spec, destination):
            real_copy(archive, name, spec, destination)
            if name == "flora":
                raise failure
        with mock.patch.object(prep, "copy_archive_sources", side_effect=copy_then_fail):
            with self.assertRaises(OSError) as caught:
                self.prepare()
        self.assertIs(caught.exception, failure)
        self.assert_no_context()
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_runtime_copy_failure_cleans_context(self):
        failure = OSError("synthetic runtime copy failure")
        original = prep.shutil.copyfile
        def copy(source, target, *args, **kwargs):
            if Path(source) == self.runtime / "supervisor.py":
                raise failure
            return original(source, target, *args, **kwargs)
        with mock.patch.object(prep.shutil, "copyfile", side_effect=copy):
            with self.assertRaises(OSError) as caught:
                self.prepare()
        self.assertIs(caught.exception, failure)
        self.assert_no_context()

    def test_candidate_copy_failure_cleans_context(self):
        original = prep.shutil.copyfile
        def copy(source, target, *args, **kwargs):
            if Path(source) == self.candidate:
                raise OSError("synthetic candidate copy failure")
            return original(source, target, *args, **kwargs)
        with mock.patch.object(prep.shutil, "copyfile", side_effect=copy):
            with self.assertRaisesRegex(OSError, "candidate copy"):
                self.prepare()
        self.assert_no_context()

    def test_hash_failure_cleans_context(self):
        original = prep.sha256
        def digest(path):
            if path.is_relative_to(self.destination):
                raise OSError("synthetic staged hash failure")
            return original(path)
        with mock.patch.object(prep, "sha256", side_effect=digest):
            with self.assertRaisesRegex(OSError, "staged hash"):
                self.prepare()
        self.assert_no_context()

    def test_partial_manifest_write_cleans_context(self):
        original = Path.write_text
        def write(path, data, *args, **kwargs):
            if path.name == "source-manifest.json":
                path.write_bytes(b'{"stage_version":')
                raise OSError("synthetic manifest write failure")
            return original(path, data, *args, **kwargs)
        with mock.patch.object(Path, "write_text", write):
            with self.assertRaisesRegex(OSError, "manifest write"):
                self.prepare()
        self.assert_no_context()

    def test_keyboard_interrupt_during_staging_cleans_context(self):
        with mock.patch.object(prep, "copy_archive_sources", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.prepare()
        self.assert_no_context()

    def test_cleanup_failure_keeps_original_error_primary(self):
        failure = OSError("synthetic preparation failure")
        cleanup = PermissionError("synthetic cleanup denial")
        original = prep.shutil.rmtree
        def remove(path, *args, **kwargs):
            if Path(path) == self.destination:
                raise cleanup
            return original(path, *args, **kwargs)
        with mock.patch.object(prep, "copy_archive_sources", side_effect=failure):
            with mock.patch.object(prep.shutil, "rmtree", side_effect=remove):
                with self.assertRaises(OSError) as caught:
                    self.prepare()
        self.assertIs(caught.exception, failure)
        self.assertIs(caught.exception.__cause__, cleanup)
        # Failed rollback must not be reported as a successful cleanup.
        self.assertTrue(self.destination.exists())
        self.assertFalse((self.destination / "source-manifest.json").exists())

    def test_missing_runtime_input_never_creates_context(self):
        (self.runtime / "supervisor.py").unlink()
        with self.assertRaises(FileNotFoundError):
            self.prepare()
        self.assert_no_context()

    def test_real_cli_main_failure_emits_no_success_record(self):
        self.members["checker"].pop("official-root/checker/src/CLI11.hpp")
        self.write_archive("checker")
        output = io.StringIO()
        with mock.patch.object(prep, "__file__", str(self.runtime / "prepare_context.py")):
            with mock.patch("sys.argv", ["prepare_context.py", "--output", str(self.destination),
                                         "--archive-dir", str(self.archives)]):
                with contextlib.redirect_stdout(output):
                    with self.assertRaisesRegex(ValueError, "Missing required staged source"):
                        prep.main()
        self.assertEqual(output.getvalue(), "")
        self.assert_no_context()

    def test_hash_rejection_never_creates_context(self):
        self.pins["checker"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.prepare()
        self.assert_no_context()
        self.assertFalse(self.destination.parent.exists())

    def test_missing_marker_never_creates_context(self):
        self.members["checker"].pop("official-root/checker/src/main.cpp")
        self.write_archive("checker")
        with self.assertRaisesRegex(ValueError, "Expected one source marker"):
            self.prepare()
        self.assert_no_context()

    def test_existing_destinations_are_never_removed(self):
        for kind in ("file", "empty-directory", "populated-directory"):
            with self.subTest(kind=kind):
                self.destination = self.root / kind
                if kind == "file":
                    self.destination.write_bytes(b"existing-file")
                else:
                    self.destination.mkdir()
                    if kind == "populated-directory":
                        (self.destination / "keep.txt").write_bytes(b"existing-data")
                with self.assertRaisesRegex(ValueError, "existing paths are never overwritten"):
                    self.prepare()
                self.assertTrue(self.destination.exists())
                if kind == "file":
                    self.assertEqual(self.destination.read_bytes(), b"existing-file")
                elif kind == "populated-directory":
                    self.assertEqual((self.destination / "keep.txt").read_bytes(), b"existing-data")
                else:
                    self.assertEqual(list(self.destination.iterdir()), [])

    def test_failed_directory_claim_does_not_remove_competing_context(self):
        original = Path.mkdir
        self.destination.parent.mkdir()
        def claim(path, *args, **kwargs):
            if path == self.destination:
                original(path)
                (path / "keep.txt").write_bytes(b"other-preparation")
                raise FileExistsError("synthetic competing directory claim")
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, "mkdir", claim):
            with self.assertRaises(FileExistsError):
                self.prepare()
        self.assertEqual((self.destination / "keep.txt").read_bytes(), b"other-preparation")

    def test_real_cli_main_success_reports_prepared_not_built_or_submitted(self):
        output = io.StringIO()
        with mock.patch.object(prep, "__file__", str(self.runtime / "prepare_context.py")):
            with mock.patch("sys.argv", ["prepare_context.py", "--output", str(self.destination),
                                         "--archive-dir", str(self.archives)]):
                with contextlib.redirect_stdout(output):
                    prep.main()
        record = json.loads(output.getvalue())
        self.assertEqual(record["context"], str(self.destination))
        self.assertEqual(record["archive_hashes_verified"], 4)
        self.assertFalse(record["built"])
        self.assertFalse(record["submitted"])
        self.assert_manifest(json.loads((self.destination / "source-manifest.json").read_text()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
