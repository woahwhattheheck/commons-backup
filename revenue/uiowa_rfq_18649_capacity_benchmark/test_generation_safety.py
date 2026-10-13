"""Executed regressions for UIOWA-095's real generator, using synthetic data only.

The immutable parity_reference.json was derived from original blob 6a21c5b6.
Tests only read it; they never regenerate expected digests. No performance claim.
"""
from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("uiowa095_safety_generator", HERE / "generate_collection.py")
gen = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gen
SPEC.loader.exec_module(gen)


def file_tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


def tree_digest(root: Path) -> str:
    records = [[name, hashlib.sha256(data).hexdigest()]
               for name, data in file_tree(root).items()]
    return hashlib.sha256(json.dumps(records, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


class GenerationSafety(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="uiowa095-safety-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / "collection"
        self.profile = gen.PROFILES["small"]

    def run_cli(self, out=None, *, optimized=False, extra=(), cwd=None):
        command = [sys.executable] + (["-O"] if optimized else []) + [
            str(HERE / "generate_collection.py"), "--out", str(out or self.out),
            "--profile", "small", *extra]
        return subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=30)

    def test_original_profile_bytes_and_summaries_are_preserved(self):
        reference_path = HERE / "parity_reference.json"
        before = reference_path.read_bytes()
        reference = json.loads(before)
        self.assertEqual(reference["source_blob"], "6a21c5b6df263960c88bbc992d7bbfd78399bd4c")
        for name, expected in reference["profiles"].items():
            with self.subTest(profile=name):
                target = self.root / name
                actual = gen.generate(target, gen.PROFILES[name], reference["seed"])
                self.assertEqual(actual, expected["summary"])
                self.assertEqual(tree_digest(target), expected["tree_sha256"])
                self.assertEqual(len(file_tree(target)), expected["files"])
                self.assertFalse((target / gen.INCOMPLETE_DIRECTORY).exists())
        self.assertEqual(reference_path.read_bytes(), before)

    def test_existing_nonempty_directory_is_untouched(self):
        self.out.mkdir()
        (self.out / "sentinel.txt").write_bytes(b"SYNTHETIC user-owned bytes\x00")
        (self.out / "nested").mkdir()
        (self.out / "nested" / "notes.md").write_text("SYNTHETIC retained note")
        before = file_tree(self.out)
        with self.assertRaisesRegex(FileExistsError, "choose a new destination"):
            gen.generate(self.out, self.profile)
        self.assertEqual(file_tree(self.out), before)

    def test_existing_empty_directory_is_not_replaced(self):
        self.out.mkdir()
        before = self.out.stat()
        with self.assertRaises(FileExistsError):
            gen.generate(self.out, self.profile)
        self.assertEqual((self.out.stat().st_ino, self.out.stat().st_mtime_ns),
                         (before.st_ino, before.st_mtime_ns))
        self.assertEqual(list(self.out.iterdir()), [])

    def test_existing_regular_file_is_untouched(self):
        self.out.write_bytes(b"SYNTHETIC retained file")
        with self.assertRaises(FileExistsError):
            gen.generate(self.out, self.profile)
        self.assertEqual(self.out.read_bytes(), b"SYNTHETIC retained file")

    def test_existing_directory_symlink_is_untouched(self):
        target = self.root / "target"
        target.mkdir()
        (target / "keep").write_bytes(b"SYNTHETIC")
        self.out.symlink_to(target, target_is_directory=True)
        with self.assertRaises(FileExistsError):
            gen.generate(self.out, self.profile)
        self.assertTrue(self.out.is_symlink())
        self.assertEqual(file_tree(target), {"keep": b"SYNTHETIC"})

    def test_dangling_symlink_is_untouched(self):
        target = self.root / "absent"
        self.out.symlink_to(target, target_is_directory=True)
        with self.assertRaises(FileExistsError):
            gen.generate(self.out, self.profile)
        self.assertTrue(self.out.is_symlink())
        self.assertEqual(os.readlink(self.out), str(target))
        self.assertFalse(target.exists())

    def test_existing_file_symlink_is_untouched(self):
        target = self.root / "retained"
        target.write_text("SYNTHETIC")
        self.out.symlink_to(target)
        with self.assertRaises(FileExistsError):
            gen.generate(self.out, self.profile)
        self.assertTrue(self.out.is_symlink())
        self.assertEqual(target.read_text(), "SYNTHETIC")

    def test_file_parent_is_untouched(self):
        parent = self.root / "parent"
        parent.write_text("SYNTHETIC")
        with self.assertRaises(OSError):
            gen.generate(parent / "new", self.profile)
        self.assertEqual(parent.read_text(), "SYNTHETIC")

    def test_new_parent_directories_are_supported(self):
        out = self.root / "new" / "nested" / "collection"
        result = gen.generate(out, self.profile)
        self.assertEqual(result["evidence_rows"], 200)
        self.assertTrue((out / "manifest.json").is_file())

    def test_invalid_positive_counts_do_not_create_parents(self):
        for field in ("evidence", "findings", "recommendations", "statements", "documents", "big_doc_every"):
            for bad in (0, -1, True, 1.0, "1", None):
                with self.subTest(field=field, value=bad):
                    profile = dataclasses.replace(self.profile, **{field: bad})
                    with self.assertRaises(ValueError):
                        gen.generate(self.root / "absent" / "out", profile)
                    self.assertFalse((self.root / "absent").exists())

    def test_invalid_body_counts_do_not_create_output(self):
        for field in ("doc_body_lines", "big_doc_body_lines"):
            for bad in (-1, True, 1.0, "1", None):
                with self.subTest(field=field, value=bad):
                    with self.assertRaises(ValueError):
                        gen.generate(self.out, dataclasses.replace(self.profile, **{field: bad}))
                    self.assertFalse(self.out.exists())

    def test_minimal_profile_with_zero_body_lines_is_valid(self):
        profile = gen.Profile("tiny", 1, 1, 1, 1, 1, 0, 1, 0)
        summary = gen.generate(self.out, profile)
        self.assertEqual(summary["evidence_rows"], 1)
        self.assertEqual(summary["documents_on_disk"], 0)  # deliberate missing document
        self.assertFalse((self.out / gen.INCOMPLETE_DIRECTORY).exists())

    def test_invalid_profile_type_does_not_create_output(self):
        for value in (None, {}, "small"):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    gen.generate(self.out, value)
                self.assertFalse(self.out.exists())

    def test_invalid_profile_names_do_not_create_output(self):
        for value in ("", "  ", None, 1):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    gen.generate(self.out, dataclasses.replace(self.profile, name=value))
                self.assertFalse(self.out.exists())

    def test_invalid_seed_does_not_create_output(self):
        for value in (None, True, 1.0, "20260919", b"seed"):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    gen.generate(self.out, self.profile, value)
                self.assertFalse(self.out.exists())

    def test_negative_seed_is_supported_and_repeatable(self):
        first = gen.generate(self.out, self.profile, -7)
        second_path = self.root / "second"
        second = gen.generate(second_path, self.profile, -7)
        self.assertEqual(first, second)
        self.assertEqual(file_tree(self.out), file_tree(second_path))

    def test_input_validation_happens_before_existing_path_mutation(self):
        self.out.mkdir()
        (self.out / "keep").write_bytes(b"SYNTHETIC")
        with self.assertRaises(ValueError):
            gen.generate(self.out, dataclasses.replace(self.profile, evidence=0))
        self.assertEqual(file_tree(self.out), {"keep": b"SYNTHETIC"})

    def test_write_failure_retains_partial_data_and_marker(self):
        original = Path.write_text
        def fail_at_report(path, *args, **kwargs):
            if path.name == "final-report.md":
                raise OSError("injected synthetic write failure")
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, "write_text", fail_at_report):
            with self.assertRaisesRegex(OSError, "injected synthetic"):
                gen.generate(self.out, self.profile)
        self.assertTrue((self.out / gen.INCOMPLETE_DIRECTORY).is_dir())
        self.assertTrue((self.out / "executive-summary.md").is_file())
        self.assertFalse((self.out / "manifest.json").exists())
        before = file_tree(self.out)
        with self.assertRaises(FileExistsError):
            gen.generate(self.out, self.profile)
        self.assertEqual(file_tree(self.out), before)

    def test_interrupt_retains_partial_data_and_marker(self):
        original = Path.write_text
        def interrupt(path, *args, **kwargs):
            if path.name == "final-report.md":
                raise KeyboardInterrupt()
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, "write_text", interrupt):
            with self.assertRaises(KeyboardInterrupt):
                gen.generate(self.out, self.profile)
        self.assertTrue((self.out / gen.INCOMPLETE_DIRECTORY).is_dir())
        self.assertTrue((self.out / "executive-summary.md").is_file())

    def test_late_failure_is_not_reported_successful(self):
        with mock.patch.object(Path, "rglob", side_effect=OSError("injected late failure")):
            with self.assertRaisesRegex(OSError, "injected late failure"):
                gen.generate(self.out, self.profile)
        self.assertTrue((self.out / "manifest.json").is_file())
        self.assertTrue((self.out / gen.INCOMPLETE_DIRECTORY).is_dir())

    def test_marker_removal_failure_is_not_swallowed(self):
        with mock.patch.object(Path, "rmdir", side_effect=OSError("injected marker failure")):
            with self.assertRaisesRegex(OSError, "injected marker failure"):
                gen.generate(self.out, self.profile)
        self.assertTrue((self.out / gen.INCOMPLETE_DIRECTORY).is_dir())

    def test_cli_success_normal_and_optimized(self):
        targets = []
        for optimized in (False, True):
            target = self.root / str(optimized)
            result = self.run_cli(target, optimized=optimized)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            self.assertEqual(json.loads(result.stdout)["evidence_rows"], 200)
            self.assertFalse((target / gen.INCOMPLETE_DIRECTORY).exists())
            targets.append(target)
        self.assertEqual(file_tree(targets[0]), file_tree(targets[1]))

    def test_cli_refusal_normal_and_optimized(self):
        self.out.mkdir()
        (self.out / "KEEP.txt").write_bytes(b"SYNTHETIC")
        for optimized in (False, True):
            result = self.run_cli(optimized=optimized)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertIn("refusing existing output", result.stderr)
            self.assertEqual(file_tree(self.out), {"KEEP.txt": b"SYNTHETIC"})

    def test_cli_dot_refuses_current_directory(self):
        (self.root / "KEEP.txt").write_text("SYNTHETIC")
        result = self.run_cli(Path("."), cwd=self.root)
        self.assertEqual(result.returncode, 2)
        self.assertEqual((self.root / "KEEP.txt").read_text(), "SYNTHETIC")
        self.assertFalse((self.root / "manifest.json").exists())

    def test_cli_invalid_seed_creates_nothing(self):
        result = self.run_cli(extra=("--seed", "bad"))
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.out.exists())

    def test_concurrent_cli_writers_have_exactly_one_winner(self):
        command = [sys.executable, str(HERE / "generate_collection.py"), "--out", str(self.out)]
        children = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    for _ in range(3)]
        try:
            results = [(child.communicate(timeout=30), child.returncode) for child in children]
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.communicate()
        self.assertEqual(sorted(code for _, code in results), [0, 2, 2])
        reference = json.loads((HERE / "parity_reference.json").read_text())["profiles"]["small"]
        self.assertEqual(tree_digest(self.out), reference["tree_sha256"])
        self.assertFalse((self.out / gen.INCOMPLETE_DIRECTORY).exists())
        for (stdout, stderr), code in results:
            if code == 0:
                self.assertEqual(json.loads(stdout), reference["summary"])
            else:
                self.assertEqual(stdout, "")
                self.assertIn("refusing existing output", stderr)

    def test_failed_run_does_not_touch_external_sentinel(self):
        sentinel = self.root / "outside.txt"
        sentinel.write_bytes(b"SYNTHETIC must survive")
        with mock.patch.object(gen, "_write_collection", side_effect=RuntimeError("synthetic failure")):
            with self.assertRaises(RuntimeError):
                gen.generate(self.out, self.profile)
        self.assertEqual(sentinel.read_bytes(), b"SYNTHETIC must survive")
        self.assertTrue((self.out / gen.INCOMPLETE_DIRECTORY).is_dir())


if __name__ == "__main__":
    unittest.main()
