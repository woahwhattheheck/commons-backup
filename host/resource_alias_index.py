#!/usr/bin/env python3
"""Build a deterministic content-addressed alias index for tracked Git blobs.

Git already stores identical content once. This tool makes the logical aliases
explicit for consumers without deleting files, rewriting history, or copying
blob contents. It reads only the named Git tree.

Use --tree-only in a partial clone to inventory aliases without hydrating blobs
for their sizes. That output has exact path counts and unmeasured byte totals.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "commons-resource-alias-index/v1"
TREE_SCHEMA = "commons-resource-alias-index/tree-v1"
OBJECT_ID_RE = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")


class AliasIndexError(ValueError):
    """The Git inventory or checked snapshot is not internally consistent."""


def canonical_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def parse_ls_tree(raw: bytes) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            fields = metadata.decode("ascii").split()
            if len(fields) not in (3, 4):
                raise ValueError("unexpected ls-tree field count")
            mode, object_type, oid = fields[:3]
            raw_size = fields[3] if len(fields) == 4 else None
        except (ValueError, UnicodeDecodeError) as exc:
            raise AliasIndexError("malformed git ls-tree record") from exc
        if object_type != "blob":
            continue
        try:
            size = int(raw_size) if raw_size is not None else None
        except ValueError as exc:
            raise AliasIndexError(f"blob {oid} has non-integer size") from exc
        path = raw_path.decode("utf-8", "surrogateescape")
        entries.append({"mode": mode, "path": path, "sha": oid, "size": size})
    return entries


def build_alias_index(
    entries: Iterable[dict[str, Any]],
    *,
    source_commit: str,
    source_tree: str,
    tree_only: bool = False,
) -> dict[str, Any]:
    by_oid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_paths: set[str] = set()
    blob_count = 0

    for raw in entries:
        path = str(raw["path"])
        oid = str(raw["sha"]).lower()
        if not tree_only and (type(raw.get("size")) is not int or raw["size"] < 0):
            raise AliasIndexError(f"missing or invalid measured blob size: {path}")
        size = None if tree_only else raw["size"]
        mode = str(raw.get("mode") or "100644")
        if path in seen_paths:
            raise AliasIndexError(f"duplicate tracked path: {path}")
        if not OBJECT_ID_RE.fullmatch(oid):
            raise AliasIndexError(f"invalid Git object id: {oid}")
        seen_paths.add(path)
        blob_count += 1
        by_oid[oid].append({"mode": mode, "path": path, "size": size})

    groups: list[dict[str, Any]] = []
    for oid, members in sorted((oid, members) for oid, members in by_oid.items() if len(members) > 1):
        sizes = {member["size"] for member in members}
        if len(sizes) != 1:
            raise AliasIndexError(f"content address {oid} has inconsistent sizes")
        size = sizes.pop()
        members.sort(key=lambda item: item["path"])
        canonical = members[0]
        groups.append(
            {
                "content_address": f"git_blob:{oid}",
                "size": size,
                "path_count": len(members),
                "canonical_path": canonical["path"],
                "canonical_mode": canonical["mode"],
                "aliases": [
                    {"path": member["path"], "mode": member["mode"]}
                    for member in members[1:]
                ],
                "logical_bytes": None if tree_only else size * len(members),
                "alias_bytes": None if tree_only else size * (len(members) - 1),
            }
        )

    logical_files = sum(group["path_count"] for group in groups)
    alias_paths = sum(group["path_count"] - 1 for group in groups)
    result = {
        "schema": TREE_SCHEMA if tree_only else SCHEMA,
        "source_commit": source_commit,
        "source_tree": source_tree,
        "scope": "all tracked Git blobs",
        "truth": {
            "git_blob_object_ids_are_content_addresses": True,
            "logical_aliases_are_not_new_physical_git_capacity": True,
            "deletions_performed": 0,
            "history_rewrites_performed": 0,
            "blob_contents_copied": 0,
        },
        "summary": {
            "tracked_blobs": blob_count,
            "unique_content_addresses": len(by_oid),
            "duplicate_groups": len(groups),
            "logical_files_in_duplicate_groups": logical_files,
            "extra_alias_paths": alias_paths,
            "logical_duplicate_bytes": None if tree_only else sum(group["logical_bytes"] for group in groups),
            "alias_bytes": None if tree_only else sum(group["alias_bytes"] for group in groups),
        },
        "groups": groups,
    }
    if tree_only:
        result["truth"]["blob_sizes_measured"] = False
        result["truth"]["lazy_blob_fetch_enabled"] = False
    return result


def git_output(*args: str, no_lazy_fetch: bool = False) -> bytes:
    try:
        return subprocess.check_output(
            ["git", *args],
            stderr=subprocess.PIPE,
            env=dict(os.environ, GIT_NO_LAZY_FETCH="1") if no_lazy_fetch else None,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", b"").decode("utf-8", "replace").strip()
        raise AliasIndexError(f"git {' '.join(args)} failed: {detail}") from exc


def scan_git(ref: str, *, tree_only: bool = False) -> dict[str, Any]:
    commit = git_output("rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}", no_lazy_fetch=tree_only).decode("ascii").strip()
    tree = git_output("rev-parse", f"{commit}^{{tree}}", no_lazy_fetch=tree_only).decode("ascii").strip()
    options = [] if tree_only else ["-l"]
    raw = git_output("ls-tree", "-r", *options, "-z", "--full-tree", commit, no_lazy_fetch=tree_only)
    return build_alias_index(
        parse_ls_tree(raw),
        source_commit=commit,
        source_tree=tree,
        tree_only=tree_only,
    )


def check_snapshot(path: Path) -> dict[str, Any]:
    expected = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(expected, dict) or expected.get("schema") not in (SCHEMA, TREE_SCHEMA):
        raise AliasIndexError(f"{path} is not a supported resource alias index")
    source_commit = expected.get("source_commit")
    if not isinstance(source_commit, str) or not source_commit:
        raise AliasIndexError(f"{path} has no source_commit")
    actual = scan_git(source_commit, tree_only=expected["schema"] == TREE_SCHEMA)
    if actual != expected:
        raise AliasIndexError(f"{path} differs from source commit {source_commit}")
    return actual


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD", help="Git commit or ref to scan")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", type=Path, help="verify a pinned snapshot using its recorded measurement mode")
    parser.add_argument("--output", type=Path, help="write instead of stdout")
    mode.add_argument("--tree-only", action="store_true",
                      help="read tree metadata without downloading blobs; byte sizes remain null")
    return parser


def write_output(path: Path, text: str) -> None:
    # Follow an existing output link as write_text did, then publish atomically.
    try:
        path = path.resolve()
    except RuntimeError as exc:
        raise AliasIndexError("output path cannot be resolved") from exc
    try:
        existing = path.stat()
    except FileNotFoundError:
        mode = None
    else:
        if not stat.S_ISREG(existing.st_mode):
            path.write_text(text, encoding="utf-8")
            return
        mode = stat.S_IMODE(existing.st_mode)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".alias-index-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            if mode is not None:
                os.chmod(temporary, mode)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = check_snapshot(args.check) if args.check else scan_git(args.ref, tree_only=args.tree_only)
        if args.check:
            summary = result["summary"]
            print(
                "MATCH "
                f"{summary['tracked_blobs']} blobs "
                f"{summary['duplicate_groups']} groups "
                f"{summary['extra_alias_paths']} aliases "
                f"{summary['alias_bytes'] if summary['alias_bytes'] is not None else 'UNMEASURED'} alias-bytes"
            )
            return 0
        rendered = canonical_text(result)
        if args.output:
            write_output(args.output, rendered)
        else:
            sys.stdout.write(rendered)
        return 0
    except (AliasIndexError, OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"resource-alias-index: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
