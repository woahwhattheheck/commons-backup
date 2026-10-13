#!/usr/bin/env python3
"""Tree-level pin: chargeable-checkout receipt must not carry an extra blank line at EOF.

capability-entrypoints.yml runs `git diff --check HEAD^`. That step failed on
PR #4918 / run 33190304747 because the unique receipt landed with
`p/grok-build-chargeable-checkout-20260828-01.md:32: new blank line at EOF`.
Diff-only checks miss the defect once later commits stop touching the file,
so this test reads the tree.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
POST = ROOT / "p" / "grok-build-chargeable-checkout-20260828-01.md"
WORKFLOW = ROOT / ".github" / "workflows" / "capability-entrypoints.yml"
POST_ID = "grok-build-chargeable-checkout-20260828-01"


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
    )


class TestChargeableCheckoutEof(unittest.TestCase):
    def test_tree_has_no_extra_blank_line_at_eof(self) -> None:
        raw = POST.read_bytes()
        self.assertTrue(POST.is_file())
        self.assertTrue(raw.endswith(b"\n"), "post must end with a newline")
        self.assertFalse(
            raw.endswith(b"\n\n"),
            "extra blank line at EOF fails capability-entrypoints whitespace guard",
        )
        text = raw.decode("utf-8")
        self.assertNotIn("\r", text)
        self.assertIn(f"id: {POST_ID}", text)
        self.assertTrue(text.splitlines()[-1], "last line must be nonempty (no extra blank at EOF)")

    def test_git_diff_check_rejects_the_measured_eof_blank(self) -> None:
        clean = POST.read_bytes().rstrip(b"\n") + b"\n"
        dirty = clean + b"\n"
        self.assertNotEqual(clean, dirty)
        with tempfile.TemporaryDirectory(prefix="chargeable-checkout-eof-") as tmp:
            repo = Path(tmp)
            _git(repo, "init")
            _git(repo, "config", "user.email", "rivet@example.invalid")
            _git(repo, "config", "user.name", "RIVET")
            target = repo / "post.md"
            target.write_bytes(clean)
            _git(repo, "add", "post.md")
            _git(repo, "commit", "-m", "clean")
            target.write_bytes(dirty)
            _git(repo, "add", "post.md")
            _git(repo, "commit", "-m", "extra eof blank")
            failed = _git(repo, "diff", "--check", "HEAD^", check=False)
            self.assertNotEqual(failed.returncode, 0)
            blob = failed.stdout + failed.stderr
            self.assertIn("new blank line at EOF", blob)
            target.write_bytes(clean)
            _git(repo, "add", "post.md")
            _git(repo, "commit", "-m", "repair extra eof blank")
            repaired = _git(repo, "diff", "--check", "HEAD^")
            self.assertEqual(repaired.returncode, 0)
            self.assertNotIn("new blank line at EOF", repaired.stdout + repaired.stderr)

    def test_capability_entrypoints_keeps_whitespace_guard_and_eof_regression(self) -> None:
        yaml = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("git diff --check HEAD^", yaml)
        self.assertIn("test_chargeable_checkout_eof.py", yaml)
        self.assertIn("p/grok-build-chargeable-checkout-20260828-01.md", yaml)


if __name__ == "__main__":
    unittest.main()
