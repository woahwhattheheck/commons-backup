#!/usr/bin/env python3
"""Copy local Commons data to content-addressed cloud storage without deletion.

The source side is read-only.  Files are hashed in place, identical bytes are
uploaded once, and the manifest is uploaded only after every remote object has
been read back and verified.  This program intentionally has no delete, move,
prune, or garbage-collection operation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Any, Callable, Iterable


CHUNK_BYTES = 8 * 1024 * 1024
FORMAT = "COMMONS_CLOUD_EVACUATION_V1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _walk(root: Path) -> Iterable[tuple[Path, str | None]]:
    """Walk without following links or directory reparse points."""

    stack = [root]
    while stack:
        current = stack.pop()
        if current.is_symlink() or not current.is_dir():
            yield current, None
            continue
        try:
            children = sorted(current.iterdir(), key=lambda item: item.name, reverse=True)
        except OSError as exc:
            yield current, str(exc)
            continue
        stack.extend(children)


def build_inventory(roots: Iterable[Path]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    seen: set[str] = set()

    for supplied_root in roots:
        root = supplied_root.expanduser().absolute()
        root_key = str(root)
        if root_key in seen:
            continue
        seen.add(root_key)
        if not root.exists() and not root.is_symlink():
            errors.append({"path": root_key, "error": "root does not exist"})
            continue

        for path, walk_error in _walk(root):
            try:
                if walk_error is not None:
                    errors.append({"path": str(path), "error": walk_error})
                    continue
                relative = "." if path == root else path.relative_to(root).as_posix()
                metadata = path.lstat()
                common = {
                    "root": root_key,
                    "path": relative,
                    "mode": stat.S_IMODE(metadata.st_mode),
                    "mtime_ns": metadata.st_mtime_ns,
                }
                if path.is_symlink():
                    entries.append({**common, "kind": "symlink", "target": os.readlink(path)})
                elif path.is_file():
                    entries.append(
                        {
                            **common,
                            "kind": "file",
                            "bytes": metadata.st_size,
                            "sha256": sha256_file(path),
                        }
                    )
                elif path == root and not path.is_dir():
                    errors.append({"path": str(path), "error": "unsupported filesystem entry"})
            except (OSError, ValueError) as exc:
                errors.append({"path": str(path), "error": str(exc)})

    entries.sort(key=lambda item: (item["root"], item["path"]))
    unique = {
        item["sha256"]: item["bytes"]
        for item in entries
        if item["kind"] == "file"
    }
    inventory = {
        "format": FORMAT,
        "complete": not errors,
        "roots": sorted(seen),
        "entries": entries,
        "errors": errors,
        "file_count": sum(item["kind"] == "file" for item in entries),
        "source_bytes": sum(item.get("bytes", 0) for item in entries),
        "unique_object_count": len(unique),
        "unique_bytes": sum(unique.values()),
    }
    identity_source = json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()
    inventory["inventory_sha256"] = hashlib.sha256(identity_source).hexdigest()
    return inventory


def cloud_object_key(sha256: str) -> str:
    return f"objects/sha256/{sha256[:2]}/{sha256}"


def cloud_plan(inventory: dict[str, Any], remote: str) -> dict[str, Any]:
    objects: dict[str, dict[str, Any]] = {}
    for item in inventory["entries"]:
        if item["kind"] != "file":
            continue
        digest = item["sha256"]
        record = objects.setdefault(
            digest,
            {
                "sha256": digest,
                "bytes": item["bytes"],
                "remote": f"{remote.rstrip('/')}/{cloud_object_key(digest)}",
                "sources": [],
            },
        )
        record["sources"].append({"root": item["root"], "path": item["path"]})
    return {
        "format": FORMAT,
        "inventory_sha256": inventory["inventory_sha256"],
        "source_bytes": inventory["source_bytes"],
        "unique_bytes": inventory["unique_bytes"],
        "objects": sorted(objects.values(), key=lambda item: item["sha256"]),
    }


def _source_path(source: dict[str, str]) -> Path:
    root = Path(source["root"])
    return root if source["path"] == "." else root / source["path"]


def _run(command: list[str], *, input_bytes: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, input=input_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _remote_sha256(remote_path: str, runner: Callable[..., subprocess.CompletedProcess[bytes]]) -> str | None:
    result = runner(["rclone", "cat", remote_path])
    if result.returncode != 0:
        return None
    return hashlib.sha256(result.stdout).hexdigest()


def stage(
    inventory: dict[str, Any],
    remote: str,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = _run,
) -> dict[str, Any]:
    if not inventory.get("complete"):
        raise ValueError("inventory is incomplete; refusing to claim cloud completeness")

    plan = cloud_plan(inventory, remote)
    receipts: list[dict[str, Any]] = []
    for obj in plan["objects"]:
        remote_path = obj["remote"]
        remote_hash = _remote_sha256(remote_path, runner)
        if remote_hash != obj["sha256"]:
            source = _source_path(obj["sources"][0])
            if sha256_file(source) != obj["sha256"]:
                raise RuntimeError(f"source changed after inventory: {source}")
            copied = runner(["rclone", "copyto", str(source), remote_path, "--immutable", "--no-traverse"])
            if copied.returncode != 0:
                raise RuntimeError(
                    f"cloud copy failed for {source}: {copied.stderr.decode(errors='replace').strip()}"
                )
            remote_hash = _remote_sha256(remote_path, runner)
        if remote_hash != obj["sha256"]:
            raise RuntimeError(f"cloud hash readback failed for {remote_path}")
        receipts.append(
            {
                "remote": remote_path,
                "bytes": obj["bytes"],
                "sha256": obj["sha256"],
                "state": "HASH_VERIFIED",
                "source_count": len(obj["sources"]),
            }
        )

    manifest_bytes = (json.dumps(inventory, indent=2, sort_keys=True) + "\n").encode()
    manifest_remote = (
        f"{remote.rstrip('/')}/manifests/{inventory['inventory_sha256']}.json"
    )
    manifest_upload = runner(
        ["rclone", "rcat", manifest_remote, "--immutable"], input_bytes=manifest_bytes
    )
    if manifest_upload.returncode != 0:
        existing = _remote_sha256(manifest_remote, runner)
        expected = hashlib.sha256(manifest_bytes).hexdigest()
        if existing != expected:
            raise RuntimeError(
                "cloud manifest upload failed: "
                + manifest_upload.stderr.decode(errors="replace").strip()
            )
    manifest_readback = _remote_sha256(manifest_remote, runner)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_readback != manifest_sha256:
        raise RuntimeError("cloud manifest hash readback failed")

    return {
        "format": FORMAT,
        "inventory_sha256": inventory["inventory_sha256"],
        "source_bytes": inventory["source_bytes"],
        "unique_bytes": inventory["unique_bytes"],
        "cloud_objects": receipts,
        "manifest_remote": manifest_remote,
        "manifest_sha256": manifest_sha256,
        "cloud_complete": True,
        "local_sources_modified": False,
        "local_release_eligible": True,
        "local_release_performed": False,
    }


def _write_json(value: dict[str, Any], destination: str) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if destination == "-":
        sys.stdout.write(payload)
    else:
        Path(destination).write_text(payload, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory_parser = subparsers.add_parser("inventory", help="hash sources without modifying them")
    inventory_parser.add_argument("roots", nargs="+", type=Path)
    inventory_parser.add_argument("--output", default="-")

    plan_parser = subparsers.add_parser("plan", help="show content-addressed cloud objects")
    plan_parser.add_argument("roots", nargs="+", type=Path)
    plan_parser.add_argument("--remote", required=True)
    plan_parser.add_argument("--output", default="-")

    stage_parser = subparsers.add_parser("stage", help="copy, read back, and verify; never delete")
    stage_parser.add_argument("roots", nargs="+", type=Path)
    stage_parser.add_argument("--remote", required=True)
    stage_parser.add_argument("--output", default="-")

    args = parser.parse_args(argv)
    inventory = build_inventory(args.roots)
    if args.command == "inventory":
        value = inventory
    elif args.command == "plan":
        value = cloud_plan(inventory, args.remote)
    else:
        value = stage(inventory, args.remote)
    _write_json(value, args.output)
    return 0 if inventory["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
