#!/usr/bin/env python3
"""Build a lossless, read-only ledger of remote branch truth deltas.

The collector freezes one base commit, compares every remote branch with that
commit, and emits enough exact evidence to deduplicate history without moving a
ref.  It intentionally performs no fetch, checkout, merge, push, delete, reset,
or other repository mutation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


SCHEMA_VERSION = "commons.branch-truth-delta.v1"
ZERO_SHA = "0" * 40
COMPLETE = "COMPLETE"
PARTIAL = "PARTIAL"


class GitError(RuntimeError):
    """Raised when a read-only Git query fails."""


def _git(
    repo: Path,
    *args: str,
    input_bytes: bytes | None = None,
    check: bool = True,
) -> bytes:
    command = ["git", "-C", str(repo), *args]
    result = subprocess.run(
        command,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise GitError(f"{' '.join(command)} failed ({result.returncode}): {detail}")
    return result.stdout


def _git_text(repo: Path, *args: str, check: bool = True) -> str:
    return _git(repo, *args, check=check).decode("utf-8", "surrogateescape").strip()


def _sha256_lines(values: Iterable[str]) -> str | None:
    rows = list(values)
    if not rows:
        return None
    return hashlib.sha256(("\n".join(rows) + "\n").encode("ascii")).hexdigest()


def _resolve_base(repo: Path, remote: str, base: str) -> tuple[str, str]:
    candidates = [base]
    if "/" not in base:
        candidates.insert(0, f"{remote}/{base}")
    for candidate in candidates:
        sha = _git_text(repo, "rev-parse", "--verify", f"{candidate}^{{commit}}", check=False)
        if sha:
            return candidate, sha
    raise GitError(f"cannot resolve base {base!r} (tried {', '.join(candidates)})")


def _remote_refs(repo: Path, remote: str) -> list[dict[str, str]]:
    record_sep = "\x1e"
    field_sep = "\x1f"
    fmt = field_sep.join(
        [
            "%(refname:short)",
            "%(objectname)",
            "%(tree)",
            "%(committerdate:iso8601-strict)",
            "%(subject)",
        ]
    ) + record_sep
    raw = _git_text(repo, "for-each-ref", f"--format={fmt}", f"refs/remotes/{remote}")
    refs: list[dict[str, str]] = []
    for record in raw.split(record_sep):
        record = record.strip("\r\n")
        if not record:
            continue
        fields = record.split(field_sep)
        if len(fields) != 5:
            raise GitError(f"unexpected for-each-ref record with {len(fields)} fields")
        ref, head, tree, committed_at, subject = fields
        # for-each-ref includes the symbolic remote HEAD as a short name.
        if ref == remote:
            continue
        refs.append(
            {
                "ref": ref,
                "branch": ref.removeprefix(f"{remote}/"),
                "head_sha": head,
                "tree_sha": tree,
                "committed_at": committed_at,
                "subject": subject,
            }
        )
    return sorted(refs, key=lambda row: row["ref"])


def _merged_refs(repo: Path, remote: str, base_sha: str) -> set[str]:
    raw = _git_text(
        repo,
        "for-each-ref",
        "--format=%(refname:short)",
        f"--merged={base_sha}",
        f"refs/remotes/{remote}",
    )
    return {line.strip() for line in raw.splitlines() if line.strip()}


def _changed_path_blobs(repo: Path, merge_base: str, head_sha: str) -> dict[str, dict[str, Any]]:
    raw = _git(
        repo,
        "diff",
        "--raw",
        "-z",
        "--no-abbrev",
        "--no-renames",
        merge_base,
        head_sha,
    )
    if not raw:
        return {}
    fields = raw.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) % 2:
        raise GitError("unexpected NUL-delimited raw diff")
    changed: dict[str, dict[str, Any]] = {}
    for index in range(0, len(fields), 2):
        metadata = fields[index].decode("ascii", "strict")
        path = fields[index + 1].decode("utf-8", "surrogateescape")
        parts = metadata.removeprefix(":").split()
        if len(parts) != 5:
            raise GitError(f"unexpected raw diff metadata: {metadata!r}")
        old_mode, new_mode, old_blob, new_blob, status = parts
        changed[path] = {
            "status": status,
            "old_blob": None if old_blob == ZERO_SHA else old_blob,
            "blob": None if new_blob == ZERO_SHA else new_blob,
            "old_mode": old_mode,
            "mode": new_mode,
        }
    return changed


def _patch_ids(repo: Path, merge_base: str, head_sha: str) -> list[dict[str, str]]:
    log = subprocess.Popen(
        [
            "git",
            "-C",
            str(repo),
            "log",
            "--reverse",
            "--no-merges",
            "--no-ext-diff",
            "--pretty=format:commit %H",
            "-p",
            f"{merge_base}..{head_sha}",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert log.stdout is not None
    patch = subprocess.run(
        ["git", "-C", str(repo), "patch-id", "--stable"],
        stdin=log.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    log.stdout.close()
    assert log.stderr is not None
    log_stderr = log.stderr.read()
    log.stderr.close()
    log_returncode = log.wait()
    if log_returncode:
        raise GitError(f"git log for patch-id failed: {log_stderr.decode('utf-8', 'replace').strip()}")
    if patch.returncode:
        raise GitError(f"git patch-id failed: {patch.stderr.decode('utf-8', 'replace').strip()}")
    rows: list[dict[str, str]] = []
    for line in patch.stdout.decode("ascii", "strict").splitlines():
        patch_id, commit_sha = line.split()
        rows.append({"patch_id": patch_id, "commit_sha": commit_sha})
    return rows


def _cherry(repo: Path, base_sha: str, head_sha: str) -> tuple[list[str], list[str]]:
    raw = _git_text(repo, "cherry", base_sha, head_sha)
    unique: list[str] = []
    equivalent: list[str] = []
    for line in raw.splitlines():
        marker, commit_sha = line.split(maxsplit=1)
        (unique if marker == "+" else equivalent).append(commit_sha)
    return unique, equivalent


def _load_pr_map(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("PR map must be a JSON object keyed by branch name")
    return payload


def _active_pr(pr_map: dict[str, Any], remote: str, ref: str, branch: str) -> Any:
    return pr_map.get(ref, pr_map.get(branch, pr_map.get(f"refs/heads/{branch}")))


def _resume_index(payload: Mapping[str, Any] | None) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    """Index only complete observations; partial evidence is never reusable."""
    if not payload:
        return {}
    ledgers = payload.get("repositories")
    if not isinstance(ledgers, list):
        ledgers = [payload]
    index: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for ledger in ledgers:
        if not isinstance(ledger, Mapping):
            continue
        repo_id = str(ledger.get("repo") or ledger.get("repository") or "")
        default_head = str(ledger.get("default_head_sha") or ledger.get("base_sha") or "")
        for row in ledger.get("branches", []):
            if not isinstance(row, dict) or row.get("comparison_completeness") != COMPLETE:
                continue
            key = (
                str(row.get("repo") or repo_id),
                str(row.get("ref") or ""),
                str(row.get("head_sha") or ""),
                str(row.get("default_head_sha") or row.get("base_sha") or default_head),
            )
            if all(key):
                index[key] = row
    return index


def _mutable_evidence(pr_data: Any) -> dict[str, Any]:
    data = pr_data if isinstance(pr_data, Mapping) else {}
    return {
        "active_pr": pr_data,
        "check_head_sha": data.get("check_head_sha"),
        "check_conclusions": data.get("check_conclusions", []),
        "main_landing_evidence": data.get("main_landing_evidence"),
    }


def _current_delta_state(row: Mapping[str, Any], pr_data: Any) -> str:
    """Overlay mutable collision evidence on the reusable content comparison."""
    if row.get("comparison_completeness") != COMPLETE:
        return "UNMEASURED"
    if row.get("is_ancestor") is True:
        content_state = "ANCESTRAL"
    elif not row.get("unique_commit_ids") and row.get("patch_equivalent_commit_ids"):
        content_state = "LANDED"
    elif not row.get("unique_commit_ids") and not row.get("changed_path_blob_map"):
        content_state = "EQUIVALENT"
    else:
        content_state = "UNIQUE"
    if (
        content_state == "UNIQUE"
        and isinstance(pr_data, Mapping)
        and pr_data.get("collision_state") == "CONFLICT"
    ):
        return "CONFLICT"
    return content_state


def collect_remote_branches(
    repo: Path,
    *,
    remote: str = "origin",
    base: str = "main",
    pr_map: dict[str, Any] | None = None,
    resume: Mapping[str, Any] | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Collect a frozen remote-branch ledger without modifying the repository."""
    repo = repo.resolve()
    base_ref, base_sha = _resolve_base(repo, remote, base)
    base_tree = _git_text(repo, "show", "-s", "--format=%T", base_sha)
    repo_id = _git_text(repo, "remote", "get-url", remote, check=False) or str(repo)
    refs = [row for row in _remote_refs(repo, remote) if row["head_sha"] != base_sha or row["ref"] != base_ref]
    # Explicitly exclude the named base branch even when another branch happens to share its head.
    refs = [row for row in refs if row["ref"] != base_ref]
    merged = _merged_refs(repo, remote, base_sha)
    pr_map = pr_map or {}
    reusable = _resume_index(resume)
    reused_count = 0

    for row in refs:
        head = row["head_sha"]
        row.update({"repo": repo_id, "default_head_sha": base_sha, "base_sha": base_sha})
        pr_data = _active_pr(pr_map, remote, row["ref"], row["branch"])
        key = (repo_id, row["ref"], head, base_sha)
        prior = reusable.get(key)
        if prior:
            immutable_keys = {
                "merge_base_sha",
                "ahead",
                "behind",
                "is_ancestor",
                "unique_commit_ids",
                "patch_equivalent_commit_ids",
                "patches",
                "patch_set_digest",
                "changed_path_blob_map",
                "changed_path_blob_digest",
                "fingerprint",
                "comparison_completeness",
                "comparison_errors",
            }
            row.update({key_name: prior.get(key_name) for key_name in immutable_keys})
            row["resumed_from_complete_observation"] = True
            reused_count += 1
        else:
            try:
                counts = _git_text(repo, "rev-list", "--left-right", "--count", f"{base_sha}...{head}")
                behind_text, ahead_text = counts.split()
                ancestor = row["ref"] in merged
                if ancestor:
                    # A remote head already reachable from default needs no patch
                    # generation or blob materialization to prove ancestry.
                    merge_base = head
                    unique_commits: list[str] = []
                    equivalent_commits: list[str] = []
                    patches: list[dict[str, str]] = []
                    changed: dict[str, dict[str, Any]] = {}
                else:
                    merge_base = _git_text(repo, "merge-base", base_sha, head)
                    unique_commits, equivalent_commits = _cherry(repo, base_sha, head)
                    patches = _patch_ids(repo, merge_base, head)
                    changed = _changed_path_blobs(repo, merge_base, head)
                patch_digest = _sha256_lines(item["patch_id"] for item in patches)
                content_digest = hashlib.sha256(
                    json.dumps(changed, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest()
                combined_digest = hashlib.sha256(
                    f"patch={patch_digest or ''}\ncontent={content_digest}\n".encode("ascii")
                ).hexdigest()
                row.update(
                    {
                        "merge_base_sha": merge_base,
                        "ahead": int(ahead_text),
                        "behind": int(behind_text),
                        "is_ancestor": ancestor,
                        "unique_commit_ids": unique_commits,
                        "patch_equivalent_commit_ids": equivalent_commits,
                        "patches": patches,
                        "patch_set_digest": patch_digest,
                        "changed_path_blob_map": changed,
                        "changed_path_blob_digest": content_digest,
                        "fingerprint": {
                            "algorithm": "sha256(stable-patch-id-sequence+canonical-path-blob-map)",
                            "digest": combined_digest,
                            "completeness": COMPLETE,
                        },
                        "comparison_completeness": COMPLETE,
                        "comparison_errors": [],
                        "resumed_from_complete_observation": False,
                    }
                )
            except Exception as exc:  # Preserve the ref and fail classification closed.
                row.update(
                    {
                        "merge_base_sha": None,
                        "ahead": None,
                        "behind": None,
                        "is_ancestor": None,
                        "unique_delta_state": "UNMEASURED",
                        "unique_commit_ids": [],
                        "patch_equivalent_commit_ids": [],
                        "patches": [],
                        "patch_set_digest": None,
                        "changed_path_blob_map": {},
                        "changed_path_blob_digest": None,
                        "fingerprint": {
                            "algorithm": "sha256(stable-patch-id-sequence+canonical-path-blob-map)",
                            "digest": None,
                            "completeness": PARTIAL,
                        },
                        "comparison_completeness": PARTIAL,
                        "comparison_errors": [f"{type(exc).__name__}: {exc}"],
                        "resumed_from_complete_observation": False,
                    }
                )
        row["unique_delta_state"] = _current_delta_state(row, pr_data)
        row.update(_mutable_evidence(pr_data))
        if progress:
            progress(dict(row))

    cluster_specs = [
        ("head_sha", "exact_head_cluster"),
        ("tree_sha", "exact_tree_cluster"),
        ("patch_set_digest", "patch_set_cluster"),
    ]
    clusters: dict[str, list[dict[str, Any]]] = {}
    for value_key, output_key in cluster_specs:
        groups: defaultdict[str, list[str]] = defaultdict(list)
        for row in refs:
            value = row.get(value_key)
            if value:
                groups[value].append(row["ref"])
        duplicate_groups = {value: sorted(names) for value, names in groups.items() if len(names) > 1}
        clusters[output_key] = [
            {value_key: value, "refs": names}
            for value, names in sorted(duplicate_groups.items())
        ]
        for row in refs:
            row[output_key] = duplicate_groups.get(row.get(value_key), [])

    state_counts: defaultdict[str, int] = defaultdict(int)
    for row in refs:
        state_counts[row["unique_delta_state"]] += 1
    summary = {
        "remote_branch_count": len(refs),
        "ancestor_count": sum(1 for row in refs if row["is_ancestor"] is True),
        "nonancestor_count": sum(1 for row in refs if row["is_ancestor"] is False),
        "unmeasured_count": sum(1 for row in refs if row["comparison_completeness"] != COMPLETE),
        "resumed_complete_observation_count": reused_count,
        "active_pr_count": sum(1 for row in refs if row["active_pr"]),
        "state_counts": dict(sorted(state_counts.items())),
        "duplicate_head_group_count": len(clusters["exact_head_cluster"]),
        "duplicate_tree_group_count": len(clusters["exact_tree_cluster"]),
        "duplicate_patch_set_group_count": len(clusters["patch_set_cluster"]),
    }
    return {
        "schema": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo": repo_id,
        "repository": str(repo),
        "remote": remote,
        "base_ref": base_ref,
        "base_sha": base_sha,
        "default_head_sha": base_sha,
        "base_tree_sha": base_tree,
        "summary": summary,
        "clusters": clusters,
        "branches": refs,
        "dirty_worktrees": [],
    }


def collect_repositories(
    repos: Sequence[Path],
    *,
    remote: str = "origin",
    base: str = "main",
    pr_map: dict[str, Any] | None = None,
    resume: Mapping[str, Any] | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Collect multiple repositories into one resumable envelope."""
    ledgers = [
        collect_remote_branches(
            repo,
            remote=remote,
            base=base,
            pr_map=pr_map,
            resume=resume,
            progress=progress,
        )
        for repo in repos
    ]
    return {
        "schema": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "repository_count": len(ledgers),
            "remote_branch_count": sum(item["summary"]["remote_branch_count"] for item in ledgers),
            "unmeasured_count": sum(item["summary"]["unmeasured_count"] for item in ledgers),
            "resumed_complete_observation_count": sum(
                item["summary"]["resumed_complete_observation_count"] for item in ledgers
            ),
        },
        "repositories": ledgers,
    }


def collect_dirty_worktree(path: Path) -> dict[str, Any]:
    """Record exact staged/unstaged/untracked blobs without writing Git objects."""
    path = path.resolve()
    root = Path(_git_text(path, "rev-parse", "--show-toplevel"))
    branch = _git_text(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False) or None
    head = _git_text(root, "rev-parse", "HEAD")
    upstream = _git_text(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", check=False) or None
    raw = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    entries: list[dict[str, Any]] = []
    fields = raw.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    index = 0
    while index < len(fields):
        record = fields[index].decode("utf-8", "surrogateescape")
        status = record[:2]
        relpath = record[3:]
        index += 1
        if status[0] in {"R", "C"} and index < len(fields):
            source_path = fields[index].decode("utf-8", "surrogateescape")
            index += 1
        else:
            source_path = None
        index_line = _git_text(root, "ls-files", "-s", "--", relpath, check=False)
        index_blob = index_line.split()[1] if index_line else None
        worktree_blob = _git_text(root, "hash-object", "--", relpath, check=False) or None
        entries.append(
            {
                "path": relpath,
                "source_path": source_path,
                "index_status": status[0],
                "worktree_status": status[1],
                "index_blob": index_blob,
                "worktree_blob": worktree_blob,
            }
        )
    return {
        "kind": "dirty-local-provenance",
        "worktree": str(root),
        "branch": branch,
        "head_sha": head,
        "upstream": upstream,
        "entries": entries,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        action="append",
        help="repository to inventory (repeatable; defaults to current directory)",
    )
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--base", default="main")
    parser.add_argument("--pr-map", type=Path, help="JSON object keyed by branch/ref")
    parser.add_argument("--resume-from", type=Path, help="reuse matching COMPLETE observations from this ledger")
    parser.add_argument(
        "--dirty-worktree",
        type=Path,
        action="append",
        default=[],
        help="also record a dirty worktree as separate provenance (repeatable)",
    )
    parser.add_argument("--output", type=Path, help="write JSON here instead of stdout")
    return parser


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    resume = json.loads(args.resume_from.read_text(encoding="utf-8")) if args.resume_from else None
    checkpoint_rows: dict[tuple[str, str], dict[str, Any]] = {}
    for key, row in _resume_index(resume).items():
        checkpoint_rows[(key[0], key[1])] = row

    def checkpoint(row: dict[str, Any]) -> None:
        if not args.output:
            return
        checkpoint_rows[(row["repo"], row["ref"])] = row
        grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        for (repo_id, _ref), observation in checkpoint_rows.items():
            grouped[repo_id].append(observation)
        _write_json_atomic(
            args.output,
            {
                "schema": SCHEMA_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "checkpoint_state": "IN_PROGRESS",
                "repositories": [
                    {
                        "repo": repo_id,
                        "default_head_sha": rows[0]["default_head_sha"],
                        "branches": sorted(rows, key=lambda item: item["ref"]),
                    }
                    for repo_id, rows in sorted(grouped.items())
                ],
            },
        )

    ledger = collect_repositories(
        args.repo or [Path.cwd()],
        remote=args.remote,
        base=args.base,
        pr_map=_load_pr_map(args.pr_map),
        resume=resume,
        progress=checkpoint,
    )
    ledger["dirty_worktrees"] = [collect_dirty_worktree(path) for path in args.dirty_worktree]
    if args.output:
        ledger["checkpoint_state"] = "COMPLETE"
        _write_json_atomic(args.output, ledger)
    else:
        sys.stdout.write(json.dumps(ledger, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
