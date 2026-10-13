# SPDX-License-Identifier: Apache-2.0
"""Offline staging-mechanics tests; fixtures are NOT official-engine validation."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import stage_evaluator_defaults as stage


class StagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="evaluator-stage-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "checkout"
        self.lab = self.repo / "revenue/kaggriculture/cloud-execution-lab"
        self.lab.mkdir(parents=True)
        (self.repo / ".git").mkdir()
        self.tool = self.lab / "candidates/v4/repairs/tooling/evaluator-defaults"
        self.donor = self.tool / "donor"
        self.donor.mkdir(parents=True)
        self.output = self.root / "staged"
        self.original = stage.SOURCES
        self.sources = []
        for target, origin, source, pin in self.original:
            base = self.lab if origin == "lab" else self.donor
            path = base / source
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                # These bytes would raise if imported. Staging must only copy them.
                path.write_bytes(("raise RuntimeError('must never execute: " + source + "')\n").encode())
            data = path.read_bytes()
            self.sources.append((target, origin, source, stage.git_blob(data)))
        (self.lab / "main.py").write_text("raise RuntimeError('candidate must not execute')\n")
        for patcher in (mock.patch.object(stage, "HERE", self.tool),
                        mock.patch.object(stage, "SOURCES", tuple(self.sources))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_exact_copy_and_receipt_without_executing_sources(self):
        receipt = stage.stage(self.lab, self.output)
        self.assertEqual(9, len(receipt["files"]))
        for target, origin, source, pin in self.sources:
            source_path = (self.lab if origin == "lab" else self.donor) / source
            self.assertEqual(source_path.read_bytes(), (self.output / target).read_bytes())
        self.assertEqual(receipt, json.loads((self.output / "STAGING.json").read_text()))
        self.assertIs(receipt["executed"], False)
        self.assertIs(receipt["economic_gate"], False)

    def test_loader_alias_is_byte_identical(self):
        stage.stage(self.lab, self.output)
        a = self.output / "reference/evaluator/loader.py"
        b = self.output / "reference/20260907-offline-agent/evaluate.py"
        self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_real_candidate_mapping_not_official_agent_alias(self):
        candidates = [row for row in self.original if row[0].endswith("offline-agent/main.py")]
        self.assertEqual(1, len(candidates))
        self.assertEqual("../20260907-offline-agent/main.py", candidates[0][2])
        self.assertEqual("f76bfdaa442b63c2a35de829e52e006fc55f6049", candidates[0][3])

    def test_command_preserves_four_default_opponents_and_loader(self):
        receipt = stage.stage(self.lab, self.output)
        command = receipt["smoke_argv_not_executed"]
        self.assertNotIn("--loader", command)
        self.assertNotIn("--opponent", command)
        self.assertNotIn("--prepare-engine", command)
        self.assertEqual(str(self.lab / "main.py"), command[command.index("--candidate") + 1])
        self.assertEqual("8", command[command.index("--episode-steps") + 1])

    def test_production_candidate_not_copied_or_mutated(self):
        before = {str(p.relative_to(self.repo)): p.read_bytes()
                  for p in self.repo.rglob("*") if p.is_file()}
        stage.stage(self.lab, self.output)
        after = {str(p.relative_to(self.repo)): p.read_bytes()
                 for p in self.repo.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse((self.output / "main.py").exists())

    def test_source_mismatch_leaves_no_output(self):
        (self.lab / "reference/engine/utils.py").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "pin mismatch"):
            stage.stage(self.lab, self.output)
        self.assertFalse(self.output.exists())

    def test_missing_source_leaves_no_output(self):
        (self.lab / "reference/engine/utils.py").unlink()
        with self.assertRaises(FileNotFoundError):
            stage.stage(self.lab, self.output)
        self.assertFalse(self.output.exists())

    def test_oversize_source_leaves_no_output(self):
        with mock.patch.object(stage, "MAX_FILE_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "size limit"):
                stage.stage(self.lab, self.output)
        self.assertFalse(self.output.exists())

    def test_leaf_symlink_rejected_even_when_bytes_match(self):
        source = self.lab / "reference/engine/utils.py"
        alternate = source.with_name("duplicate.py")
        alternate.write_bytes(source.read_bytes())
        source.unlink()
        source.symlink_to(alternate)
        with self.assertRaisesRegex(ValueError, "non-symlink"):
            stage.stage(self.lab, self.output)
        self.assertFalse(self.output.exists())

    def test_source_cannot_escape_checkout_through_symlink(self):
        source = self.lab / "reference/engine/utils.py"
        outside = self.root / "outside.py"
        outside.write_bytes(source.read_bytes())
        source.unlink()
        source.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "escapes"):
            stage.stage(self.lab, self.output)
        self.assertFalse(self.output.exists())

    def test_existing_directory_preserved(self):
        self.output.mkdir()
        sentinel = self.output / "keep.txt"
        sentinel.write_text("keep")
        with self.assertRaisesRegex(ValueError, "already exists"):
            stage.stage(self.lab, self.output)
        self.assertEqual("keep", sentinel.read_text())

    def test_existing_file_preserved(self):
        self.output.write_text("keep")
        with self.assertRaisesRegex(ValueError, "already exists"):
            stage.stage(self.lab, self.output)
        self.assertEqual("keep", self.output.read_text())

    def test_dangling_output_symlink_not_replaced(self):
        self.output.symlink_to(self.root / "missing")
        with self.assertRaisesRegex(ValueError, "already exists"):
            stage.stage(self.lab, self.output)
        self.assertTrue(self.output.is_symlink())

    def test_output_inside_checkout_refused(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            stage.stage(self.lab, self.repo / "scratch")
        self.assertFalse((self.repo / "scratch").exists())

    def test_output_parent_symlink_to_checkout_refused(self):
        alias = self.root / "alias"
        alias.symlink_to(self.repo, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "outside"):
            stage.stage(self.lab, alias / "scratch")
        self.assertFalse((self.repo / "scratch").exists())

    def test_missing_parent_not_created(self):
        with self.assertRaisesRegex(ValueError, "parent must already exist"):
            stage.stage(self.lab, self.root / "missing/staged")
        self.assertFalse((self.root / "missing").exists())

    def test_checkout_marker_required(self):
        (self.repo / ".git").rmdir()
        with self.assertRaisesRegex(ValueError, "checkout"):
            stage.stage(self.lab, self.output)
        self.assertFalse(self.output.exists())

    def test_worktree_git_file_supported(self):
        (self.repo / ".git").rmdir()
        (self.repo / ".git").write_text("gitdir: elsewhere\n")
        self.assertTrue(stage.stage(self.lab, self.output)["stage_only"])

    def test_duplicate_target_rejected_before_writes(self):
        with mock.patch.object(stage, "SOURCES", (*self.sources, self.sources[0])):
            with self.assertRaisesRegex(ValueError, "duplicate"):
                stage.stage(self.lab, self.output)
        self.assertFalse(self.output.exists())

    def test_target_traversal_rejected_before_writes(self):
        row = self.sources[0]
        with mock.patch.object(stage, "SOURCES", (("../escape", *row[1:]),)):
            with self.assertRaisesRegex(ValueError, "output path"):
                stage.stage(self.lab, self.output)
        self.assertFalse(self.output.exists())

    def test_unknown_origin_rejected_before_writes(self):
        target, _, source, pin = self.sources[0]
        with mock.patch.object(stage, "SOURCES", ((target, "remote", source, pin),)):
            with self.assertRaisesRegex(ValueError, "origin"):
                stage.stage(self.lab, self.output)
        self.assertFalse(self.output.exists())

    def test_partial_write_failure_removes_only_new_output(self):
        original_open = Path.open
        def failing_open(path, *args, **kwargs):
            if path == self.output / "reference/evaluator/loader.py" and args and args[0] == "xb":
                raise OSError("injected write failure")
            return original_open(path, *args, **kwargs)
        with mock.patch.object(Path, "open", failing_open):
            with self.assertRaisesRegex(OSError, "injected"):
                stage.stage(self.lab, self.output)
        self.assertFalse(self.output.exists())
        self.assertTrue((self.lab / "main.py").is_file())

    def test_exclusive_claim_race_does_not_remove_other_output(self):
        original_mkdir = Path.mkdir
        def racing_mkdir(path, *args, **kwargs):
            if path == self.output:
                original_mkdir(path)
                (path / "other-writer").write_text("preserve")
            return original_mkdir(path, *args, **kwargs)
        with mock.patch.object(Path, "mkdir", racing_mkdir):
            with self.assertRaises(FileExistsError):
                stage.stage(self.lab, self.output)
        self.assertEqual("preserve", (self.output / "other-writer").read_text())

    def test_cli_success_is_staging_not_execution(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = stage.main(["--lab", str(self.lab), "--output", str(self.output)])
        self.assertEqual(0, result)
        self.assertIs(json.loads(stdout.getvalue())["executed"], False)

    def test_cli_pin_failure_returns_two(self):
        (self.donor / "opponents.py").write_text("tampered\n")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = stage.main(["--lab", str(self.lab), "--output", str(self.output)])
        self.assertEqual(2, result)
        self.assertIn("pin mismatch", stderr.getvalue())
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
