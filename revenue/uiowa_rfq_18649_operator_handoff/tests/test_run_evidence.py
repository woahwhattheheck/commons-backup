"""Runner contract tests using real local synthetic child scripts, never client data.

Run from the lane: python -m unittest discover -s tests -p 'test_run_evidence.py' -v
Set UIOWA_RUNNER_UNDER_TEST to a directory to test the exact same contract against
an earlier sample_run.py/preflight.py pair. No external dependencies are needed.
"""
from __future__ import annotations
import contextlib
import copy
import hashlib
import io
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MODULE_DIR = Path(os.environ.get("UIOWA_RUNNER_UNDER_TEST", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(MODULE_DIR))
import sample_run as runner
from preflight import ALLOWED_PHASES, validate


def make_fixture(root: Path, code: str | None = None) -> dict:
    """Minimal, six-phase manifest accepted by the real unchanged preflight."""
    lane = root / "fixture lane"
    lane.mkdir(parents=True)
    (lane / "notes.md").write_text("SYNTHETIC fixture; not University findings.\n", encoding="utf-8")
    if code is None:
        code = "import pathlib,sys\npathlib.Path(sys.argv[1]).write_text('SYNTHETIC result\\n')\nprint('fixture complete')\n"
    (lane / "sample.py").write_text(code, encoding="utf-8")
    assets = []
    for phase in sorted(ALLOWED_PHASES):
        asset = {"asset_id": "exec" if phase == "analysis" else "reference_" + phase,
                 "work_order": "SYNTHETIC-CONTRACT", "phase": phase,
                 "status": "working" if phase == "analysis" else "working_reference",
                 "path": "fixture lane/sample.py" if phase == "analysis" else "fixture lane/notes.md",
                 "purpose": "Isolated regression fixture.", "operator_action": "Run synthetic test only.",
                 "authority_ceiling": "No University or production claims."}
        if phase == "analysis":
            asset.update(working_dir="fixture lane", sample_commands=[["sample.py", "${OUT}/artifact.txt"]])
        assets.append(asset)
    return {"schema": "uiowa.operator-handoff.v1", "snapshot_main_sha": "1" * 40,
            "phases": sorted(ALLOWED_PHASES), "assets": assets,
            "required_university_inputs": ["UNKNOWN; no University data in this fixture."]}


class RunEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="uiowa runner evidence ")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "repo"
        self.manifest = make_fixture(self.root)
        self.out = self.base / "output"
        self.assertTrue(validate(self.manifest, self.root)["ok"])

    def run_sample(self, **kwargs):
        arguments = dict(manifest=self.manifest, root=self.root, out_dir=self.out,
                         timeout=3.0, dry_run=False)
        arguments.update(kwargs)
        return runner.run_sample(**arguments)

    def command_asset(self):
        return next(a for a in self.manifest["assets"] if a["asset_id"] == "exec")

    def set_code(self, code):
        (self.root / "fixture lane/sample.py").write_text(code, encoding="utf-8")

    def manifest_path(self):
        path = self.base / "manifest.json"
        path.write_text(json.dumps(self.manifest), encoding="utf-8")
        return path

    def test_real_success_has_execution_evidence(self):
        r = self.run_sample()
        self.assertTrue(r["success"])
        self.assertTrue(r["execution_verified"])
        self.assertEqual(r["status"], "PASSED")
        self.assertEqual(r["planned_steps"], 1)
        self.assertEqual(r["attempted_steps"], 1)
        self.assertEqual(r["steps"][0]["returncode"], 0)
        self.assertEqual((self.out / "artifact.txt").read_text(), "SYNTHETIC result\n")

    def test_output_inventory_matches_actual_bytes(self):
        r = self.run_sample()
        self.assertEqual(len(r["outputs"]), 1)
        row = r["outputs"][0]
        content = (self.out / row["path"]).read_bytes()
        self.assertEqual(row["sha256"], hashlib.sha256(content).hexdigest())
        self.assertEqual(row["bytes"], len(content))

    def test_receipt_is_not_an_output_or_self_hash(self):
        r = self.run_sample()
        self.assertNotIn("sample-run-receipt.json", [row["path"] for row in r["outputs"]])
        self.assertFalse((self.out / ".sample-run-in-progress").exists())

    def test_serialized_receipt_equals_return_value(self):
        r = self.run_sample()
        self.assertEqual(json.loads(Path(r["receipt_path"]).read_text()), r)

    def test_dry_run_is_a_plan_not_execution(self):
        with mock.patch.object(runner.subprocess, "run") as child:
            r = self.run_sample(dry_run=True)
        child.assert_not_called()
        self.assertTrue(r["success"])  # legacy plan-success compatibility
        self.assertFalse(r["execution_verified"])
        self.assertEqual(r["status"], "PLANNED")
        self.assertEqual(r["attempted_steps"], 0)
        self.assertIsNone(r["steps"][0]["returncode"])
        self.assertFalse((self.out / "artifact.txt").exists())

    def test_reference_only_selection_is_rejected_before_writing(self):
        with self.assertRaisesRegex(ValueError, "no executable"):
            self.run_sample(selected_assets={"reference_kickoff"})
        self.assertFalse(self.out.exists())

    def test_mixed_executable_and_reference_selection_is_not_silently_partial(self):
        with self.assertRaisesRegex(ValueError, "no executable"):
            self.run_sample(selected_assets={"exec", "reference_kickoff"})
        self.assertFalse(self.out.exists())

    def test_unknown_direct_api_selection_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "preflight failed:.*unknown --asset values"):
            self.run_sample(selected_assets={"not-a-known-asset"})
        self.assertFalse(self.out.exists())

    def test_empty_execution_plan_is_rejected(self):
        del self.command_asset()["sample_commands"]
        with self.assertRaisesRegex(ValueError, "no executable"):
            self.run_sample()
        self.assertFalse(self.out.exists())

    def test_valid_explicit_selection_executes(self):
        r = self.run_sample(selected_assets={"exec"})
        self.assertEqual(r["selected_assets"], ["exec"])
        self.assertTrue(r["execution_verified"])

    def test_actual_timeout_preserves_failure_receipt(self):
        self.set_code("import time\nprint('partial evidence', flush=True)\ntime.sleep(5)\n")
        r = self.run_sample(timeout=0.3)
        self.assertFalse(r["success"])
        self.assertFalse(r["execution_verified"])
        self.assertEqual(r["status"], "TIMED_OUT")
        self.assertIsNone(r["steps"][0]["returncode"])
        # A busy host can time out during interpreter startup. Empty capture is
        # legitimate; deterministic partial-capture behavior is tested below.
        self.assertIn(r["steps"][0]["stdout_excerpt"], ("", "partial evidence\n"))
        self.assertEqual(json.loads(Path(r["receipt_path"]).read_text())["status"], "TIMED_OUT")

    def test_timeout_partial_stream_variants(self):
        for index, value in enumerate((b"partial", "partial", None)):
            with self.subTest(value=value):
                exc = subprocess.TimeoutExpired(["fixture"], 0.1, output=value, stderr=value)
                with mock.patch.object(runner.subprocess, "run", side_effect=exc):
                    r = self.run_sample(out_dir=self.base / f"timeout-{index}")
                self.assertFalse(r["success"])
                self.assertEqual(r["status"], "TIMED_OUT")
                expected = b"partial" if value is not None else b""
                self.assertEqual(r["steps"][0]["stdout_sha256"], hashlib.sha256(expected).hexdigest())

    def test_launch_error_preserves_failure_receipt(self):
        with mock.patch.object(runner.subprocess, "run", side_effect=OSError("fixture launch unavailable")):
            r = self.run_sample()
        self.assertFalse(r["success"])
        self.assertEqual(r["status"], "EXECUTION_ERROR")
        self.assertIn("fixture launch unavailable", r["steps"][0]["error"])
        self.assertTrue(Path(r["receipt_path"]).is_file())

    def test_real_nonzero_exit_stops_later_commands(self):
        self.set_code("import sys\nprint('failure detail', file=sys.stderr)\nsys.exit(7)\n")
        self.command_asset()["sample_commands"] *= 2
        r = self.run_sample()
        self.assertFalse(r["success"])
        self.assertEqual(r["status"], "FAILED")
        self.assertEqual(r["planned_steps"], 2)
        self.assertEqual(len(r["steps"]), 1)
        self.assertEqual(r["steps"][0]["returncode"], 7)
        self.assertIn("failure detail", r["steps"][0]["stderr_excerpt"])

    def test_partial_completion_cannot_be_verified(self):
        self.command_asset()["sample_commands"] *= 3
        responses = [subprocess.CompletedProcess([], 0, b"first", b""),
                     subprocess.CompletedProcess([], 4, b"", b"second failed")]
        with mock.patch.object(runner.subprocess, "run", side_effect=responses) as child:
            r = self.run_sample()
        self.assertEqual(child.call_count, 2)
        self.assertEqual(r["planned_steps"], 3)
        self.assertEqual(r["attempted_steps"], 2)
        self.assertFalse(r["execution_verified"])

    def test_stale_output_is_rejected_and_preserved(self):
        self.out.mkdir()
        stale = self.out / "old-result.txt"
        stale.write_bytes(b"previous run")
        with mock.patch.object(runner.subprocess, "run") as child:
            with self.assertRaisesRegex(ValueError, "new or empty"):
                self.run_sample()
        child.assert_not_called()
        self.assertEqual(stale.read_bytes(), b"previous run")
        self.assertFalse((self.out / "sample-run-receipt.json").exists())

    def test_completed_run_cannot_overwrite_previous_receipt(self):
        first = self.run_sample()
        receipt_path = Path(first["receipt_path"])
        old = receipt_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "new or empty"):
            self.run_sample()
        self.assertEqual(receipt_path.read_bytes(), old)

    def test_existing_empty_output_directory_is_supported(self):
        self.out.mkdir()
        self.assertTrue(self.run_sample()["execution_verified"])

    def test_regular_file_cannot_be_output_directory(self):
        self.out.write_bytes(b"existing file")
        with self.assertRaises(ValueError):
            self.run_sample()
        self.assertEqual(self.out.read_bytes(), b"existing file")

    def test_other_runner_reservation_is_not_removed(self):
        reservation = self.out / ".sample-run-in-progress"
        reservation.mkdir(parents=True)
        with self.assertRaises(ValueError):
            self.run_sample()
        self.assertTrue(reservation.is_dir())

    def test_run_completing_between_empty_check_and_reservation_is_preserved(self):
        original_mkdir = Path.mkdir
        def interleaved_mkdir(path, *args, **kwargs):
            if path.name == ".sample-run-in-progress":
                (path.parent / "other-run-result.txt").write_bytes(b"completed other run")
            return original_mkdir(path, *args, **kwargs)
        with mock.patch.object(Path, "mkdir", autospec=True, side_effect=interleaved_mkdir):
            with mock.patch.object(runner.subprocess, "run") as child:
                with self.assertRaisesRegex(ValueError, "new or empty"):
                    self.run_sample()
        child.assert_not_called()
        self.assertEqual((self.out / "other-run-result.txt").read_bytes(), b"completed other run")
        self.assertFalse((self.out / ".sample-run-in-progress").exists())
        self.assertFalse((self.out / "sample-run-receipt.json").exists())

    def test_output_directory_symlink_is_rejected(self):
        target = self.base / "target"
        target.mkdir()
        self.out.symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.run_sample()
        self.assertEqual(list(target.iterdir()), [])

    def test_inventory_failure_is_not_success(self):
        with mock.patch.object(runner, "inventory_outputs", side_effect=OSError("fixture unreadable output")):
            r = self.run_sample()
        self.assertEqual(r["status"], "INVENTORY_FAILED")
        self.assertFalse(r["success"])
        self.assertFalse(r["execution_verified"])
        self.assertTrue(Path(r["receipt_path"]).is_file())

    def test_output_symlink_is_not_hashed_as_generated_content(self):
        def child(*args, **kwargs):
            (self.out / "alias.txt").symlink_to(self.root / "fixture lane/notes.md")
            return subprocess.CompletedProcess([], 0, b"", b"")
        with mock.patch.object(runner.subprocess, "run", side_effect=child):
            r = self.run_sample()
        self.assertEqual(r["status"], "INVENTORY_FAILED")
        self.assertFalse(r["execution_verified"])
        self.assertEqual(r["outputs"], [])

    def test_invalid_timeouts_fail_before_creating_output(self):
        for value in (0, -1, float("nan"), float("inf"), -float("inf"), True, "1"):
            with self.subTest(timeout=value):
                with self.assertRaises(ValueError):
                    self.run_sample(timeout=value)
                self.assertFalse(self.out.exists())

    def test_invalid_preflight_does_not_create_output(self):
        self.manifest["schema"] = "wrong"
        with self.assertRaises(RuntimeError):
            self.run_sample()
        self.assertFalse(self.out.exists())

    def test_entrypoint_hash_is_of_actual_executed_file(self):
        script = self.root / "fixture lane/sample.py"
        expected = hashlib.sha256(script.read_bytes()).hexdigest()
        r = self.run_sample()
        self.assertEqual(r["steps"][0]["entrypoint_sha256"], expected)
        self.assertEqual(r["steps"][0]["entrypoint_sha256_after"], expected)
        self.assertIn("NOT the identity", r["snapshot_semantics"])
        self.assertIn("dependencies are not hashed", r["provenance_scope"])

    def test_source_change_during_execution_cannot_be_verified(self):
        def child(*args, **kwargs):
            self.set_code("print('changed fixture')\n")
            return subprocess.CompletedProcess([], 0, b"", b"")
        with mock.patch.object(runner.subprocess, "run", side_effect=child):
            r = self.run_sample()
        self.assertEqual(r["status"], "SOURCE_CHANGED")
        self.assertFalse(r["success"])
        self.assertNotEqual(r["steps"][0]["entrypoint_sha256"], r["steps"][0]["entrypoint_sha256_after"])

    def test_manifest_hash_is_content_bound_not_key_order_bound(self):
        first = self.run_sample(dry_run=True)
        shuffled = dict(reversed(list(self.manifest.items())))
        second = self.run_sample(manifest=shuffled, out_dir=self.base / "second-plan", dry_run=True)
        self.assertEqual(first["manifest_sha256"], second["manifest_sha256"])
        shuffled = copy.deepcopy(shuffled)
        shuffled["assets"][0]["purpose"] += " changed"
        third = self.run_sample(manifest=shuffled, out_dir=self.base / "third-plan", dry_run=True)
        self.assertNotEqual(first["manifest_sha256"], third["manifest_sha256"])

    def test_argv_uses_no_shell_and_bytecode_writes_are_disabled(self):
        completed = subprocess.CompletedProcess([], 0, b"", b"")
        with mock.patch.object(runner.subprocess, "run", return_value=completed) as child:
            self.run_sample()
        args, kwargs = child.call_args
        self.assertIsInstance(args[0], list)
        self.assertEqual(args[0][-1], str(self.out / "artifact.txt"))
        self.assertFalse(kwargs.get("shell", False))
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(kwargs["env"]["PYTHONDONTWRITEBYTECODE"], "1")

    def test_relative_root_path_is_resolved(self):
        relroot = Path(os.path.relpath(self.root, Path.cwd()))
        r = self.run_sample(root=relroot)
        self.assertTrue(r["execution_verified"])

    def test_cli_dry_run_says_planned_not_pass(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = runner.main(["--manifest", str(self.manifest_path()), "--root", str(self.root),
                                "--out", str(self.out), "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("sample: PLANNED", stdout.getvalue())
        self.assertNotIn("sample: PASS", stdout.getvalue())
        self.assertIn("execution_verified=False", stdout.getvalue())

    def test_cli_reference_selection_returns_clear_error(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
            code = runner.main(["--manifest", str(self.manifest_path()), "--root", str(self.root),
                                "--out", str(self.out), "--asset", "reference_kickoff"])
        self.assertEqual(code, 2)
        self.assertIn("no executable", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_cli_timeout_returns_failure_and_receipt(self):
        exc = subprocess.TimeoutExpired(["fixture"], 1, output=b"partial")
        stdout = io.StringIO()
        with mock.patch.object(runner.subprocess, "run", side_effect=exc), contextlib.redirect_stdout(stdout):
            code = runner.main(["--manifest", str(self.manifest_path()), "--root", str(self.root),
                                "--out", str(self.out)])
        self.assertEqual(code, 1)
        self.assertIn("TIMED_OUT", stdout.getvalue())
        self.assertTrue((self.out / "sample-run-receipt.json").is_file())

    def test_pending_at_snapshot_cannot_run_unverified_commands(self):
        self.command_asset()["status"] = "pending_at_snapshot"
        with mock.patch.object(runner.subprocess, "run") as child:
            with self.assertRaisesRegex(ValueError, "pending-at-snapshot"):
                self.run_sample()
        child.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_entrypoint_disappearing_after_preflight_gets_failure_receipt(self):
        real_validate = runner.validate
        def checked_then_removed(manifest, root, selected_assets):
            result = real_validate(manifest, root, selected_assets)
            (root / "fixture lane/sample.py").unlink()
            return result
        with mock.patch.object(runner, "validate", side_effect=checked_then_removed):
            r = self.run_sample()
        self.assertEqual(r["status"], "EXECUTION_ERROR")
        self.assertFalse(r["execution_verified"])
        self.assertTrue(Path(r["receipt_path"]).is_file())

    def test_captured_output_survives_post_run_source_read_failure(self):
        def child(*args, **kwargs):
            (self.root / "fixture lane/sample.py").unlink()
            return subprocess.CompletedProcess([], 0, b"captured before removal", b"diagnostic")
        with mock.patch.object(runner.subprocess, "run", side_effect=child):
            r = self.run_sample()
        self.assertEqual(r["status"], "EXECUTION_ERROR")
        self.assertFalse(r["execution_verified"])
        self.assertEqual(r["steps"][0]["stdout_excerpt"], "captured before removal")
        self.assertEqual(r["steps"][0]["stderr_excerpt"], "diagnostic")
        self.assertEqual(r["steps"][0]["returncode"], 0)

    def test_fixture_source_tree_is_unchanged_by_real_execution(self):
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.run_sample()
        after = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
