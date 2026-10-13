#!/usr/bin/env python3
"""Fail closed unless Git work is clean and the landed commit is on target."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def exists(repo: Path, revision: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", revision],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc.returncode == 0


def is_ancestor(repo: Path, older: str, newer: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", older, newer],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--target-ref", default="origin/main")
    parser.add_argument("--expected-commit", help="Landed/merge commit; defaults to HEAD")
    parser.add_argument("--required-path", action="append", default=[])
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    result: dict[str, object] = {
        "repo": str(repo),
        "target_ref": args.target_ref,
        "checks": {},
        "errors": [],
    }
    checks = result["checks"]
    errors = result["errors"]

    try:
        root = Path(git(repo, "rev-parse", "--show-toplevel")).resolve()
        result["repo"] = str(root)
        repo = root

        if args.fetch:
            remote = args.target_ref.split("/", 1)[0]
            git(repo, "fetch", "--prune", remote)
            checks["fetched"] = remote

        dirty = [line for line in git(repo, "status", "--porcelain=v1", "--untracked-files=all").splitlines() if line]
        checks["clean"] = not dirty
        if dirty:
            errors.append("worktree has tracked or untracked changes")
            result["dirty_entries"] = dirty

        head = git(repo, "rev-parse", "HEAD")
        result["head"] = head
        result["branch"] = git(repo, "branch", "--show-current") or "DETACHED"

        checks["target_exists"] = exists(repo, args.target_ref)
        if not checks["target_exists"]:
            errors.append(f"target ref does not exist: {args.target_ref}")
        else:
            target_head = git(repo, "rev-parse", args.target_ref)
            result["target_head"] = target_head
            expected = args.expected_commit or head
            if not exists(repo, expected):
                checks["expected_commit_exists"] = False
                errors.append(f"expected commit does not exist: {expected}")
            else:
                expected = git(repo, "rev-parse", expected)
                result["expected_commit"] = expected
                checks["expected_commit_exists"] = True
                checks["landed_ancestry"] = is_ancestor(repo, expected, target_head)
                if not checks["landed_ancestry"]:
                    errors.append("expected commit is not an ancestor of target head")

            path_results = {}
            for required_path in args.required_path:
                normalized = required_path.replace("\\", "/").lstrip("/")
                path_results[normalized] = exists(repo, f"{args.target_ref}:{normalized}")
                if not path_results[normalized]:
                    errors.append(f"required path missing from target: {normalized}")
            checks["required_paths"] = path_results

        result["state"] = "LANDED" if not errors else "UNFINISHED"
    except Exception as exc:
        errors.append(str(exc))
        result["state"] = "UNFINISHED"

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["state"] == "LANDED" else 2


if __name__ == "__main__":
    sys.exit(main())

