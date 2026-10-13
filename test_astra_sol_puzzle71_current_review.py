#!/usr/bin/env python3
"""Puzzle71 current-review must fetch HEAD^ before the workflow-only proof.

Measured: run 34384951717 on SHA 43dcc48b8e8ae7ce48fcfc8993875a4b5c175544
failed step "Prove evidence carrier is workflow-only" with
`fatal: bad revision 'HEAD^'` because actions/checkout@v4 defaults to
fetch-depth: 1. The carrier commit has a parent; depth 2 resolves HEAD^
and the workflow-only pathspec stays clean.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github" / "workflows" / "astra-sol-puzzle71-current-review.yml"
WORKFLOW_REL = ".github/workflows/astra-sol-puzzle71-current-review.yml"
PINS = (
    ("host/muhl_puzzle71_organs_add.py", "9128536487cb20181bf4dc96605a23a515ba9854"),
    ("host/muhl_puzzle71_fire_add.py", "72e8544056c248b56975317887f39494798ff731"),
    ("test_muhl_puzzle71_organs.py", "156ad8cb91a199ceb52bef7243c7b509ca139c36"),
    ("test_muhl_puzzle71_live_instrument.py", "d02db36fd9b75a84a223bbda841d7b89dd2cffd3"),
)
GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "puzzle71-review",
    "GIT_AUTHOR_EMAIL": "puzzle71-review@commons.local",
    "GIT_COMMITTER_NAME": "puzzle71-review",
    "GIT_COMMITTER_EMAIL": "puzzle71-review@commons.local",
}


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        env=GIT_ENV,
    )
    if check and completed.returncode:
        raise AssertionError(
            f"git {args!r} failed rc={completed.returncode}: {completed.stderr}"
        )
    return completed


class Puzzle71CurrentReviewWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_checkout_fetches_parent_before_head_parent_diff(self) -> None:
        checkout = re.search(
            r"- uses: actions/checkout@v4\s+with:\s+(.*?)(?=\n\s+- (?:name|uses):)",
            self.text,
            re.S,
        )
        self.assertIsNotNone(checkout, "checkout with fetch-depth is required")
        block = checkout.group(1)
        depth = re.search(r"^\s*fetch-depth:\s*(\d+)\s*$", block, re.M)
        self.assertIsNotNone(depth, block)
        self.assertGreaterEqual(int(depth.group(1)), 2, block)
        parent_proof = self.text.split("Prove evidence carrier parent is present", 1)
        self.assertEqual(len(parent_proof), 2, "parent-present step missing")
        self.assertIn("git rev-parse --verify HEAD^", parent_proof[1].split("- name:", 1)[0])
        only = self.text.split("Prove evidence carrier is workflow-only", 1)
        self.assertEqual(len(only), 2, "workflow-only step missing")
        only_body = only[1].split("- name:", 1)[0]
        self.assertIn("git diff --exit-code HEAD^", only_body)
        self.assertIn(":(exclude).github/workflows/astra-sol-puzzle71-current-review.yml", only_body)

    def test_workflow_pins_match_live_blobs(self) -> None:
        for path, digest in PINS:
            self.assertIn(digest, self.text, path)
            hashed = git(ROOT, "hash-object", path).stdout.strip()
            self.assertEqual(hashed, digest, path)

    def test_depth1_cannot_resolve_parent_depth2_proves_workflow_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            src.mkdir()
            git(src, "init", "-b", "carrier")
            git(src, "config", "user.name", "puzzle71-review")
            git(src, "config", "user.email", "puzzle71-review@commons.local")
            workflow = src / WORKFLOW_REL
            workflow.parent.mkdir(parents=True)
            (src / "keep.txt").write_text("base\n", encoding="utf-8")
            workflow.write_text("name: before\n", encoding="utf-8")
            git(src, "add", ".")
            git(src, "commit", "-m", "base")
            workflow.write_text("name: after\n", encoding="utf-8")
            git(src, "add", WORKFLOW_REL)
            git(src, "commit", "-m", "carrier")

            depth1 = Path(tmp) / "depth1"
            git(Path(tmp), "clone", "--no-local", "--depth", "1", str(src), str(depth1))
            missing = git(depth1, "rev-parse", "--verify", "HEAD^", check=False)
            self.assertNotEqual(missing.returncode, 0, missing.stderr)
            diff1 = git(
                depth1,
                "diff",
                "--exit-code",
                "HEAD^",
                "--",
                ".",
                f":(exclude){WORKFLOW_REL}",
                check=False,
            )
            self.assertNotEqual(diff1.returncode, 0, diff1.stderr)
            self.assertRegex(diff1.stderr, r"bad revision|unknown revision|Needed a single revision")

            depth2 = Path(tmp) / "depth2"
            git(Path(tmp), "clone", "--no-local", "--depth", "2", str(src), str(depth2))
            git(depth2, "rev-parse", "--verify", "HEAD^")
            proof = git(
                depth2,
                "diff",
                "--exit-code",
                "HEAD^",
                "--",
                ".",
                f":(exclude){WORKFLOW_REL}",
            )
            self.assertEqual(proof.returncode, 0, proof.stdout + proof.stderr)

            (src / "keep.txt").write_text("sneak\n", encoding="utf-8")
            git(src, "add", "keep.txt")
            git(src, "commit", "-m", "sneak")
            sneaked = Path(tmp) / "sneaked"
            git(Path(tmp), "clone", "--no-local", "--depth", "2", str(src), str(sneaked))
            dirty = git(
                sneaked,
                "diff",
                "--exit-code",
                "HEAD^",
                "--",
                ".",
                f":(exclude){WORKFLOW_REL}",
                check=False,
            )
            self.assertEqual(dirty.returncode, 1, dirty.stderr)
            self.assertIn("keep.txt", dirty.stdout)


if __name__ == "__main__":
    unittest.main()
