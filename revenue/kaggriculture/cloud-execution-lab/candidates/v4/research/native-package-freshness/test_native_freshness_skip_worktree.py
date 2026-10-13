import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "check_native_freshness_skip_worktree_test",
    HERE / "check_native_freshness.py",
)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MOD)


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return proc.stdout.strip()


def _repo() -> tuple[tempfile.TemporaryDirectory, Path]:
    tmp = tempfile.TemporaryDirectory()
    repo = Path(tmp.name)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "native-freshness@example.invalid")
    _git(repo, "config", "user.name", "native-freshness-test")
    (repo / "live").mkdir()
    (repo / "outside").mkdir()
    (repo / "live" / "keep.py").write_text("KEEP = 1\n", encoding="utf-8")
    (repo / "outside" / "keep.py").write_text("OUTSIDE = 1\n", encoding="utf-8")
    _git(repo, "add", "live/keep.py", "outside/keep.py")
    _git(repo, "commit", "-qm", "base")
    return tmp, repo


class SkipWorktreeDeletionGateTest(unittest.TestCase):
    def test_skip_worktree_absence_under_tracked_root_cannot_hide_expected_member(self):
        tmp, repo = _repo()
        with tmp:
            vanished = repo / "live" / "keep.py"
            head = _git(repo, "rev-parse", "HEAD")

            # This is the primitive sparse-checkout uses for omitted tracked files.
            # The file is physically absent but ordinary `git diff <HEAD>` deletion
            # scans intentionally ignore it, so live rglob() enumeration can shrink.
            _git(repo, "update-index", "--skip-worktree", "live/keep.py")
            vanished.unlink()

            deleted = _git(
                repo,
                "diff",
                "--no-ext-diff",
                "--no-renames",
                "--name-only",
                "--diff-filter=D",
                head,
                "--",
                "live",
            )
            self.assertEqual("", deleted)
            self.assertTrue(
                _git(repo, "ls-files", "-t", "--", "live/keep.py").startswith("S ")
            )

            with self.assertRaises(MOD.InvalidEvidence):
                MOD._assert_no_tracked_deletions(repo, head, Path("live"))

    def test_present_skip_worktree_member_under_tracked_root_is_not_itself_invalid(self):
        tmp, repo = _repo()
        with tmp:
            head = _git(repo, "rev-parse", "HEAD")
            _git(repo, "update-index", "--skip-worktree", "live/keep.py")
            self.assertTrue((repo / "live" / "keep.py").is_file())
            self.assertTrue(
                _git(repo, "ls-files", "-t", "--", "live/keep.py").startswith("S ")
            )

            # Freshness must prove expected tracked bytes are physically present;
            # the index hint bit is not itself publication authority or a defect.
            MOD._assert_no_tracked_deletions(repo, head, Path("live"))

    def test_absent_skip_worktree_member_outside_tracked_root_does_not_poison_scope(self):
        tmp, repo = _repo()
        with tmp:
            head = _git(repo, "rev-parse", "HEAD")
            outside = repo / "outside" / "keep.py"
            _git(repo, "update-index", "--skip-worktree", "outside/keep.py")
            outside.unlink()
            self.assertFalse(outside.exists())
            self.assertTrue((repo / "live" / "keep.py").is_file())

            MOD._assert_no_tracked_deletions(repo, head, Path("live"))

    def test_ordinary_tracked_deletion_under_scope_still_fails_closed(self):
        tmp, repo = _repo()
        with tmp:
            head = _git(repo, "rev-parse", "HEAD")
            (repo / "live" / "keep.py").unlink()
            deleted = _git(
                repo,
                "diff",
                "--no-ext-diff",
                "--no-renames",
                "--name-only",
                "--diff-filter=D",
                head,
                "--",
                "live",
            )
            self.assertEqual("live/keep.py", deleted)
            with self.assertRaises(MOD.InvalidEvidence):
                MOD._assert_no_tracked_deletions(repo, head, Path("live"))


if __name__ == "__main__":
    unittest.main()
