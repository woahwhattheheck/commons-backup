"""Real-Git regressions for no-overwrite Git bundle publication.

By default loads host/repo_backup.py next to this file. Override with
REPO_BACKUP_MODULE=/absolute/path/to/repo_backup.py. Each test owns a fresh
TemporaryDirectory; no network, existing repository, or owner disk is used.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(os.environ.get(
    "REPO_BACKUP_MODULE", str(Path(__file__).parent / "host" / "repo_backup.py")
)).resolve()
spec = importlib.util.spec_from_file_location("backup_under_test", MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot import source: {MODULE_PATH}")
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 9, 8, 11, 0, 0, tzinfo=timezone.utc)
        return value if tz is not None else value.replace(tzinfo=None)


class BundleCollisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="backup-collision-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.git("init", "--initial-branch=main")
        self.git("config", "user.name", "Backup Regression Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.source / "tracked.txt").write_text("preserve this commit\n")
        self.git("add", "tracked.txt")
        self.git("commit", "-m", "synthetic fixture")
        self.head = self.git("rev-parse", "HEAD").stdout.strip()
        self.output = self.root / "backups"
        self.output.mkdir()
        self.bundle = self.output / f"commons-20260908T110000Z-{self.head[:12]}.bundle"
        self.manifest = self.bundle.with_suffix(".manifest.json")
        self.clock = patch.object(backup, "datetime", FrozenDateTime)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def git(self, *args):
        return subprocess.run(
            ["git", *args], cwd=self.source, check=True,
            capture_output=True, text=True,
        )

    def assert_output_only(self, *paths):
        self.assertEqual(
            sorted(p.name for p in self.output.iterdir()),
            sorted(p.name for p in paths),
        )

    def test_round_trip_bare(self):
        manifest = backup.snapshot(self.source, self.output)
        self.assertEqual(backup.verify(manifest)["state"], "VERIFIED")
        result = backup.restore(manifest, self.root / "bare", bare=True)
        self.assertEqual(result["restored_head_sha"], self.head)
        self.assertTrue(result["bare"])
        self.assert_output_only(self.bundle, self.manifest)

    def test_round_trip_worktree(self):
        manifest = backup.snapshot(self.source, self.output)
        target = self.root / "restored"
        backup.restore(manifest, target)
        self.assertEqual((target / "tracked.txt").read_text(), "preserve this commit\n")
        self.assert_output_only(self.bundle, self.manifest)

    def test_repeat_refuses_without_changing_existing_pair(self):
        manifest = backup.snapshot(self.source, self.output)
        before = (self.bundle.read_bytes(), manifest.read_bytes())
        with self.assertRaises(backup.BackupError):
            backup.snapshot(self.source, self.output)
        self.assertEqual(before, (self.bundle.read_bytes(), manifest.read_bytes()))
        self.assertEqual(backup.verify(manifest)["state"], "VERIFIED")

    def test_bundle_appearing_after_exists_check_is_not_overwritten(self):
        real_run = backup._run
        sentinel = b"a peer-created file, not ours to overwrite\n"

        def inject(args, cwd=None, check=True):
            if args[:2] == ["bundle", "create"]:
                self.bundle.write_bytes(sentinel)
            return real_run(args, cwd=cwd, check=check)

        with patch.object(backup, "_run", side_effect=inject):
            with self.assertRaises(backup.BackupError):
                backup.snapshot(self.source, self.output)
        self.assertEqual(self.bundle.read_bytes(), sentinel)
        self.assert_output_only(self.bundle)

    def test_existing_dangling_symlink_is_not_replaced(self):
        missing = self.root / "intentionally-absent"
        try:
            self.bundle.symlink_to(missing)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symbolic links unavailable on this platform: {exc}")
        # Windows pathlib stores an extended-length \\?\ target. Compare the
        # occupied name's stored bytes, not Path(missing) object equality.
        stored_target = os.readlink(self.bundle)
        self.assertTrue(os.path.lexists(self.bundle))
        self.assertFalse(self.bundle.exists())
        with self.assertRaisesRegex(backup.BackupError, "refusing to overwrite snapshot"):
            backup.snapshot(self.source, self.output)
        self.assertTrue(self.bundle.is_symlink())
        self.assertEqual(os.readlink(self.bundle), stored_target)
        self.assertFalse(missing.exists())
        self.assert_output_only(self.bundle)

    def test_windows_extended_path_readlink_is_not_missing_path_equality(self):
        # Hosted Windows pathlib returns //?/C:/... from Path.readlink(); that
        # Path is not equal to the original missing Path used in symlink_to.
        from pathlib import PureWindowsPath

        missing = PureWindowsPath(
            "C:/Users/RUNNER~1/AppData/Local/Temp/backups/intentionally-absent"
        )
        stored = PureWindowsPath(
            "//?/C:/Users/RUNNER~1/AppData/Local/Temp/backups/intentionally-absent"
        )
        self.assertNotEqual(stored, missing)
        self.assertEqual(
            os.path.normcase(os.path.normpath(str(stored)[4:])),
            os.path.normcase(os.path.normpath(str(missing))),
        )

    def test_failed_git_generation_leaves_no_published_partial_bundle(self):
        real_run = backup._run

        def inject(args, cwd=None, check=True):
            if args[:2] == ["bundle", "create"]:
                Path(args[2]).write_bytes(b"synthetic partial Git output")
                raise backup.BackupError("injected Git generation failure")
            return real_run(args, cwd=cwd, check=check)

        with patch.object(backup, "_run", side_effect=inject):
            with self.assertRaisesRegex(backup.BackupError, "generation failure"):
                backup.snapshot(self.source, self.output)
        self.assert_output_only()

    def test_moved_ref_inventory_leaves_no_published_bundle(self):
        real_heads = backup._repo_heads

        def move_ref(source):
            self.git("tag", "created-after-bundle")
            return real_heads(source)

        with patch.object(backup, "_repo_heads", side_effect=move_ref):
            with self.assertRaisesRegex(backup.BackupError, "ref inventory differs"):
                backup.snapshot(self.source, self.output)
        self.assert_output_only()

    def test_existing_manifest_is_not_overwritten(self):
        self.manifest.write_bytes(b"independent peer manifest\n")
        with self.assertRaises(backup.BackupError):
            backup.snapshot(self.source, self.output)
        self.assertEqual(self.manifest.read_bytes(), b"independent peer manifest\n")

    def _exercise_delayed_contender(self, *, move_after_creation=False):
        # A contender passes the existence gate, then pauses before Git creates
        # its bundle. The winner finishes its snapshot. The contender must not
        # overwrite or unlink that winner, even if the live ref inventory moves.
        entered = threading.Event()
        release = threading.Event()
        real_run = backup._run
        outcomes = []

        def intercept(args, cwd=None, check=True):
            contender = threading.current_thread().name == "delayed-contender"
            if contender and args[:2] == ["bundle", "create"]:
                entered.set()
                if not release.wait(10):
                    raise RuntimeError("test barrier timed out")
                result = real_run(args, cwd=cwd, check=check)
                if move_after_creation:
                    self.git("tag", "moved-after-contender-bundle")
                return result
            return real_run(args, cwd=cwd, check=check)

        def contender():
            try:
                outcomes.append(("success", backup.snapshot(self.source, self.output)))
            except Exception as exc:
                outcomes.append(("error", exc))

        with patch.object(backup, "_run", side_effect=intercept):
            thread = threading.Thread(target=contender, name="delayed-contender")
            thread.start()
            try:
                self.assertTrue(entered.wait(10), "contender never reached Git barrier")
                manifest = backup.snapshot(self.source, self.output)
                before = (self.bundle.read_bytes(), manifest.read_bytes())
                self.git("tag", "created-after-winner")
            finally:
                release.set()
                thread.join(15)
            self.assertFalse(thread.is_alive(), "contender failed to terminate")

        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0][0], "error", outcomes)
        self.assertIsInstance(outcomes[0][1], backup.BackupError)
        self.assertTrue(self.bundle.is_file(), "rejected contender deleted winner's bundle")
        self.assertEqual(
            before, (self.bundle.read_bytes(), manifest.read_bytes()),
            "rejected contender changed winner's committed backup pair",
        )
        self.assertEqual(backup.verify(manifest)["state"], "VERIFIED")
        self.assert_output_only(self.bundle, self.manifest)

    def test_rejected_contender_preserves_successful_snapshot_bytes(self):
        self._exercise_delayed_contender()

    def test_ref_mismatch_in_contender_does_not_unlink_winner(self):
        self._exercise_delayed_contender(move_after_creation=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
