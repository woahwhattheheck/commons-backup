#!/usr/bin/env python3
"""Tree-level pin: .gitignore must not carry an extra blank line at EOF.

revenue-hardening.yml runs `git diff --check HEAD^`. That step failed on
PR #4886 / run 33187110273 because the vault ignore addition landed with
`.gitignore:21: new blank line at EOF`. Diff-only checks miss the defect
once later commits stop touching the file, so this test reads the tree.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
GITIGNORE = ROOT / ".gitignore"
VAULT_LINES = ("*.vault", "**/.commons/*.vault")


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
    )


class TestGitignoreEof(unittest.TestCase):
    def test_tree_has_no_extra_blank_line_at_eof(self) -> None:
        raw = GITIGNORE.read_bytes()
        self.assertTrue(raw.endswith(b"\n"), ".gitignore must end with a newline")
        self.assertFalse(
            raw.endswith(b"\n\n"),
            ".gitignore extra blank line at EOF fails revenue-hardening whitespace guard",
        )
        text = raw.decode("utf-8")
        self.assertNotIn("\r", text)
        lines = text.splitlines()
        for line in VAULT_LINES:
            self.assertIn(line, lines)

    def test_git_diff_check_rejects_the_measured_eof_blank(self) -> None:
        clean = GITIGNORE.read_bytes().rstrip(b"\n") + b"\n"
        dirty = clean + b"\n"
        self.assertNotEqual(clean, dirty)
        with tempfile.TemporaryDirectory(prefix="gitignore-eof-") as tmp:
            repo = Path(tmp)
            _git(repo, "init")
            _git(repo, "config", "user.email", "rivet@example.invalid")
            _git(repo, "config", "user.name", "RIVET")
            target = repo / ".gitignore"
            target.write_bytes(clean)
            _git(repo, "add", ".gitignore")
            _git(repo, "commit", "-m", "clean")
            target.write_bytes(dirty)
            _git(repo, "add", ".gitignore")
            _git(repo, "commit", "-m", "extra eof blank")
            failed = _git(repo, "diff", "--check", "HEAD^", check=False)
            self.assertNotEqual(failed.returncode, 0)
            blob = failed.stdout + failed.stderr
            self.assertIn("new blank line at EOF", blob)
            target.write_bytes(clean)
            _git(repo, "add", ".gitignore")
            _git(repo, "commit", "-m", "repair extra eof blank")
            repaired = _git(repo, "diff", "--check", "HEAD^")
            self.assertEqual(repaired.returncode, 0)
            self.assertNotIn("new blank line at EOF", repaired.stdout + repaired.stderr)


if __name__ == "__main__":
    unittest.main()
