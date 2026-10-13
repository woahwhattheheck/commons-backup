#!/usr/bin/env python3
"""Fail-closed moving-main preimage proof for non-force branch refreshes.

This helper is intentionally read-only. It resolves three commit revisions, proves
that the candidate head descends its declared base, checks that candidate changes
are confined to caller-owned paths, and compares the original base blob for each
owned path with the same path on current main.

Use the default preflight verdict before composing current main into a candidate.
After a non-force composition, rerun with ``--require-composed`` to require that
the candidate contains current main and that current-main -> head differs only on
owned paths.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Iterable, Sequence

SCHEMA = "commons-moving-main-preimage-v1"
MISSING = "<missing>"


class ProofError(RuntimeError):
    """Raised when git cannot prove a required fact."""


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
        raise ProofError(f"git {' '.join(args)}: {detail}")
    return proc


def resolve_commit(repo: Path, rev: str) -> str:
    if not rev or rev.startswith("-"):
        raise ProofError(f"invalid revision: {rev!r}")
    proc = _git(repo, "rev-parse", "--verify", f"{rev}^{{commit}}")
    sha = proc.stdout.strip()
    if not sha:
        raise ProofError(f"revision did not resolve to a commit: {rev!r}")
    return sha


def _is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    proc = _git(repo, "merge-base", "--is-ancestor", ancestor, descendant, check=False)
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    detail = proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
    raise ProofError(f"git merge-base --is-ancestor {ancestor} {descendant}: {detail}")


def _changed_paths(repo: Path, left: str, right: str) -> list[str]:
    out = _git(repo, "diff", "--name-only", "--no-renames", left, right, "--").stdout
    return sorted({line for line in out.splitlines() if line})


def _blob(repo: Path, rev: str, path: str) -> str:
    # cat-file -e distinguishes a missing path from other git failures without
    # reading file content or touching the working tree.
    spec = f"{rev}:{path}"
    exists = _git(repo, "cat-file", "-e", spec, check=False)
    if exists.returncode in (1, 128):
        # Confirm that the revision itself is valid; path absence is an ordinary
        # preimage value and compares equal to absence on another commit.
        resolve_commit(repo, rev)
        return MISSING
    if exists.returncode != 0:
        detail = exists.stderr.strip() or exists.stdout.strip() or f"exit {exists.returncode}"
        raise ProofError(f"git cat-file -e {spec}: {detail}")
    return _git(repo, "rev-parse", "--verify", spec).stdout.strip()


def _ahead_behind(repo: Path, current_main: str, head: str) -> tuple[int, int]:
    out = _git(
        repo,
        "rev-list",
        "--left-right",
        "--count",
        f"{current_main}...{head}",
    ).stdout.strip()
    parts = out.split()
    if len(parts) != 2:
        raise ProofError(f"unexpected rev-list output: {out!r}")
    return int(parts[0]), int(parts[1])


def _normalize_owned(paths: Iterable[str]) -> list[str]:
    rows: list[str] = []
    for raw in paths:
        value = raw.strip()
        if not value:
            continue
        if value.startswith("/") or value == ".." or value.startswith("../") or "/../" in value:
            raise ProofError(f"owned path must be repository-relative: {raw!r}")
        rows.append(value)
    result = sorted(set(rows))
    if not result:
        raise ProofError("at least one --owned-path is required")
    return result


def analyze(
    repo: Path,
    base_rev: str,
    head_rev: str,
    current_main_rev: str,
    owned_paths: Iterable[str],
) -> dict:
    repo = repo.resolve()
    if not (repo / ".git").exists() and _git(repo, "rev-parse", "--git-dir", check=False).returncode != 0:
        raise ProofError(f"not a git repository: {repo}")

    owned = _normalize_owned(owned_paths)
    base = resolve_commit(repo, base_rev)
    head = resolve_commit(repo, head_rev)
    current_main = resolve_commit(repo, current_main_rev)

    descends_base = _is_ancestor(repo, base, head)
    candidate_paths = _changed_paths(repo, base, head)
    unowned_candidate_paths = sorted(set(candidate_paths) - set(owned))

    owned_rows = []
    collisions = []
    for path in owned:
        base_blob = _blob(repo, base, path)
        main_blob = _blob(repo, current_main, path)
        equal = base_blob == main_blob
        row = {
            "path": path,
            "base_blob": base_blob,
            "current_main_blob": main_blob,
            "preimage_equal": equal,
        }
        owned_rows.append(row)
        if not equal:
            collisions.append(path)

    behind_by, ahead_by = _ahead_behind(repo, current_main, head)
    current_main_to_head_paths = _changed_paths(repo, current_main, head)
    current_main_to_head_unowned = sorted(set(current_main_to_head_paths) - set(owned))

    pre_refresh_safe = bool(descends_base and not unowned_candidate_paths and not collisions)
    composed_scope_safe = bool(
        descends_base
        and not collisions
        and behind_by == 0
        and not current_main_to_head_unowned
        and set(current_main_to_head_paths).issubset(set(owned))
    )

    return {
        "schema": SCHEMA,
        "repo": str(repo),
        "resolved": {
            "base": base,
            "head": head,
            "current_main": current_main,
        },
        "candidate_descends_base": descends_base,
        "owned_paths": owned_rows,
        "candidate_delta": {
            "base_to_head_paths": candidate_paths,
            "unowned_paths": unowned_candidate_paths,
        },
        "moving_main": {
            "owned_preimage_collisions": collisions,
            "behind_by": behind_by,
            "ahead_by": ahead_by,
            "current_main_to_head_paths": current_main_to_head_paths,
            "current_main_to_head_unowned_paths": current_main_to_head_unowned,
        },
        "verdict": {
            "pre_refresh_safe": pre_refresh_safe,
            "post_refresh_exact": composed_scope_safe,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."), help="git checkout (default: .)")
    parser.add_argument("--base", required=True, help="candidate's declared original base revision")
    parser.add_argument("--head", required=True, help="candidate head revision")
    parser.add_argument("--current-main", required=True, help="fresh current main revision")
    parser.add_argument(
        "--owned-path",
        action="append",
        default=[],
        help="path owned by the candidate; repeat for multiple paths",
    )
    parser.add_argument(
        "--require-composed",
        action="store_true",
        help="exit nonzero unless head contains current main and current-main->head differs only on owned paths",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        receipt = analyze(args.repo, args.base, args.head, args.current_main, args.owned_path)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        verdict = receipt["verdict"]
        ok = verdict["post_refresh_exact"] if args.require_composed else verdict["pre_refresh_safe"]
        return 0 if ok else 2
    except ProofError as exc:
        print(json.dumps({"schema": SCHEMA, "error": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
