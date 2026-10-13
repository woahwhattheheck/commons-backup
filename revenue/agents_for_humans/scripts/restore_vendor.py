"""Restore attributed vendor copies to exact SOURCE_MANIFEST Git blobs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Callable

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")


def blob_id(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def safe_local_path(package_root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"unsafe manifest local_path: {relative}")
    root = package_root.resolve()
    path = (root / rel).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"manifest local_path escapes package: {relative}")
    return path


def read_git_blob(repo_root: Path, sha: str) -> bytes:
    sha = sha.lower()
    if not _SHA1_RE.fullmatch(sha):
        raise ValueError(f"invalid manifest git_blob: {sha}")
    proc = subprocess.run(
        ["git", "cat-file", "blob", sha],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"pinned Git blob unavailable {sha}: {detail}")
    if blob_id(proc.stdout) != sha:
        raise RuntimeError(f"Git returned bytes that do not match pinned blob {sha}")
    return proc.stdout


def reconcile(
    *,
    package_root: Path = PACKAGE_ROOT,
    repo_root: Path = REPO_ROOT,
    manifest_path: Path | None = None,
    apply: bool = False,
    blob_reader: Callable[[Path, str], bytes] = read_git_blob,
) -> list[str]:
    package_root = package_root.resolve()
    repo_root = repo_root.resolve()
    manifest_path = manifest_path or package_root / "SOURCE_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    changed: list[str] = []

    for item in manifest["upstream_files"]:
        relative = item["local_path"]
        sha = str(item["git_blob"]).lower()
        if not _SHA1_RE.fullmatch(sha):
            raise ValueError(f"invalid manifest git_blob: {sha}")
        local = safe_local_path(package_root, relative)
        pinned = blob_reader(repo_root, sha)
        if blob_id(pinned) != sha:
            raise RuntimeError(f"blob reader returned bytes that do not match {sha}")
        current = local.read_bytes() if local.is_file() else None
        if current == pinned:
            continue
        changed.append(str(local.relative_to(repo_root)).replace("\\", "/"))
        if apply:
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(pinned)
            if blob_id(local.read_bytes()) != sha:
                raise RuntimeError(f"restore verification failed: {relative}")

    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="restore drifted manifest-owned files from their pinned Git blobs",
    )
    args = parser.parse_args()
    changed = reconcile(apply=args.apply)
    state = "RESTORED" if args.apply and changed else "DRIFT" if changed else "CLEAN"
    print(json.dumps({"state": state, "changed": changed}, sort_keys=True))
    return 0 if args.apply or not changed else 1


if __name__ == "__main__":
    raise SystemExit(main())
