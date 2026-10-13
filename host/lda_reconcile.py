#!/usr/bin/env python3
"""Compare tracked Android source trees without copying archives or build output."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_SCOPES = (
    "app/build.gradle",
    "app/src/main",
    "app/src/test",
    "build.gradle",
    "gradle.properties",
    "settings.gradle",
)


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args])


def resolve(repo: Path, ref: str) -> str:
    return _git(repo, "rev-parse", ref).decode("ascii").strip()


def repository_identity(repo: Path) -> str:
    try:
        remote = _git(repo, "config", "--get", "remote.origin.url").decode("utf-8").strip()
    except subprocess.CalledProcessError:
        remote = ""
    return remote or str(repo)


def tracked_blobs(repo: Path, ref: str, prefix: str = "") -> dict[str, str]:
    prefix = prefix.strip("/")
    args = ["ls-tree", "-r", "-z", ref]
    if prefix:
        args.extend(["--", prefix])
    raw = _git(repo, *args)
    blobs: dict[str, str] = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        left, path_raw = record.split(b"\t", 1)
        _mode, kind, sha = left.decode("ascii").split(" ")
        if kind != "blob":
            continue
        path = path_raw.decode("utf-8", "surrogateescape").replace("\\", "/")
        if prefix:
            if path == prefix:
                logical = Path(path).name
            elif path.startswith(prefix + "/"):
                logical = path[len(prefix) + 1 :]
            else:
                continue
        else:
            logical = path
        blobs[logical] = sha
    return blobs


def _in_scope(path: str, scopes: Iterable[str]) -> bool:
    return any(path == scope or path.startswith(scope.rstrip("/") + "/") for scope in scopes)


def recommendation(path: str, status: str) -> str:
    if status == "same":
        return "already-aligned"
    if status == "commons_only":
        return "retain-commons"
    if status == "source_only" and path.startswith("app/src/test/"):
        return "candidate-test"
    if status == "source_only" and path.endswith("data_extraction_rules.xml"):
        return "candidate-resource"
    if status == "source_only":
        return "review-candidate"
    return "review-semantic-diff"


def compare(
    commons_repo: Path,
    commons_ref: str,
    commons_prefix: str,
    source_repo: Path,
    source_ref: str,
    source_prefix: str,
    scopes: Iterable[str] = DEFAULT_SCOPES,
) -> dict:
    scopes = tuple(scopes)
    commons_sha = resolve(commons_repo, commons_ref)
    source_sha = resolve(source_repo, source_ref)
    commons = {
        path: sha
        for path, sha in tracked_blobs(commons_repo, commons_sha, commons_prefix).items()
        if _in_scope(path, scopes)
    }
    source = {
        path: sha
        for path, sha in tracked_blobs(source_repo, source_sha, source_prefix).items()
        if _in_scope(path, scopes)
    }
    records = []
    for path in sorted(commons.keys() | source.keys()):
        left = commons.get(path)
        right = source.get(path)
        if left is None:
            status = "source_only"
        elif right is None:
            status = "commons_only"
        elif left == right:
            status = "same"
        else:
            status = "different"
        records.append(
            {
                "path": path,
                "status": status,
                "commons_blob": left,
                "source_blob": right,
                "recommendation": recommendation(path, status),
            }
        )
    counts = Counter(record["status"] for record in records)
    return {
        "schema": "commons.lda-reconciliation/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": list(scopes),
        "commons": {
            "repository": repository_identity(commons_repo),
            "ref": commons_ref,
            "commit": commons_sha,
            "prefix": commons_prefix,
        },
        "source": {
            "repository": repository_identity(source_repo),
            "ref": source_ref,
            "commit": source_sha,
            "prefix": source_prefix,
        },
        "summary": {
            "total": len(records),
            "same": counts["same"],
            "different": counts["different"],
            "commons_only": counts["commons_only"],
            "source_only": counts["source_only"],
        },
        "records": records,
    }


def render_markdown(manifest: dict) -> str:
    summary = manifest["summary"]
    lines = [
        "# Agentic handset operator — selective reconciliation",
        "",
        "This is a tracked-source comparison, not a filesystem dump. Build products, model files, archives,",
        "local properties, device state, and untracked work are outside the comparison by construction.",
        "",
        f"- Commons: `{manifest['commons']['commit']}` under `{manifest['commons']['prefix']}/`",
        f"- Source: `{manifest['source']['commit']}`",
        f"- Scope: {', '.join(f'`{scope}`' for scope in manifest['scope'])}",
        f"- Result: {summary['same']} same, {summary['different']} different, "
        f"{summary['source_only']} source-only, {summary['commons_only']} Commons-only",
        "",
        "## Selective queue",
        "",
        "| status | recommendation | path |",
        "|---|---|---|",
    ]
    for record in manifest["records"]:
        if record["status"] == "same":
            continue
        lines.append(
            f"| {record['status']} | {record['recommendation']} | `{record['path']}` |"
        )
    lines.extend(
        [
            "",
            "## Landing rule",
            "",
            "Review semantic diffs individually. Candidate tests and the Android data-extraction resource are the",
            "smallest safe imports. Do not bulk-copy the source repository or its archive/build directories.",
            "The physical phone remains outside this work; emulator integration is a later phase.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commons-repo", type=Path, required=True)
    parser.add_argument("--commons-ref", default="HEAD")
    parser.add_argument("--commons-prefix", default="lda")
    parser.add_argument("--source-repo", type=Path, required=True)
    parser.add_argument("--source-ref", default="HEAD")
    parser.add_argument("--source-prefix", default="")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args(argv)
    manifest = compare(
        args.commons_repo,
        args.commons_ref,
        args.commons_prefix,
        args.source_repo,
        args.source_ref,
        args.source_prefix,
    )
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(render_markdown(manifest), encoding="utf-8")
    if not args.json and not args.markdown:
        print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
