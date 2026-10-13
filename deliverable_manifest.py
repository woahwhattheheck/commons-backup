#!/usr/bin/env python3
"""Build a deterministic sidecar manifest for a deliverable directory.

Every regular deliverable file is bound by normalized relative path, byte length,
and SHA-256. An explicit acceptance map is validated against that exact file set
and canonicalized into the receipt. The receipt itself must live outside the
bundle so it never becomes a self-referential input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


SCHEMA = "commons-deliverable-manifest/v1"


class ManifestError(ValueError):
    """Raised when a deterministic manifest cannot be proven."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ManifestError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _load_json(raw: bytes) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ManifestError("acceptance map is not UTF-8") from exc
    try:
        return json.loads(text, object_pairs_hook=_strict_object)
    except ManifestError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise ManifestError(f"invalid acceptance JSON: {exc}") from exc


def _normalize_rel_path(raw: str) -> str:
    if not isinstance(raw, str) or not raw:
        raise ManifestError("acceptance path must be a non-empty string")
    if "\\" in raw:
        raise ManifestError(f"acceptance path must use '/' separators: {raw!r}")
    path = PurePosixPath(raw)
    if path.is_absolute():
        raise ManifestError(f"acceptance path must be relative: {raw!r}")
    parts = path.parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ManifestError(f"acceptance path is non-canonical: {raw!r}")
    normalized = path.as_posix()
    if normalized != raw or "//" in raw:
        raise ManifestError(f"acceptance path is non-canonical: {raw!r}")
    return normalized


def _normalize_acceptance(raw: bytes, file_paths: set[str]) -> list[dict[str, Any]]:
    doc = _load_json(raw)
    if not isinstance(doc, dict) or set(doc) != {"criteria"}:
        raise ManifestError("acceptance map must be exactly {'criteria': [...]} ")
    criteria = doc["criteria"]
    if not isinstance(criteria, list) or not criteria:
        raise ManifestError("acceptance criteria must be a non-empty list")

    seen_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for item in criteria:
        if not isinstance(item, dict) or set(item) != {"id", "description", "paths"}:
            raise ManifestError("each criterion must contain exactly id, description, and paths")
        criterion_id = item["id"]
        description = item["description"]
        paths = item["paths"]
        if not isinstance(criterion_id, str) or not criterion_id.strip():
            raise ManifestError("criterion id must be a non-empty string")
        if criterion_id != criterion_id.strip():
            raise ManifestError(f"criterion id has surrounding whitespace: {criterion_id!r}")
        if criterion_id in seen_ids:
            raise ManifestError(f"duplicate criterion id {criterion_id!r}")
        seen_ids.add(criterion_id)
        if not isinstance(description, str) or not description.strip():
            raise ManifestError(f"criterion {criterion_id!r} description must be non-empty")
        if description != description.strip():
            raise ManifestError(f"criterion {criterion_id!r} description has surrounding whitespace")
        if not isinstance(paths, list) or not paths:
            raise ManifestError(f"criterion {criterion_id!r} paths must be a non-empty list")
        clean_paths: list[str] = []
        seen_paths: set[str] = set()
        for raw_path in paths:
            clean = _normalize_rel_path(raw_path)
            if clean in seen_paths:
                raise ManifestError(f"criterion {criterion_id!r} repeats path {clean!r}")
            seen_paths.add(clean)
            if clean not in file_paths:
                raise ManifestError(f"criterion {criterion_id!r} references absent file {clean!r}")
            clean_paths.append(clean)
        normalized.append(
            {
                "id": criterion_id,
                "description": description,
                "paths": sorted(clean_paths),
            }
        )
    normalized.sort(key=lambda item: item["id"])
    return normalized


def _root_identity(root: Path) -> tuple[int, int]:
    try:
        root_stat = root.lstat()
    except FileNotFoundError as exc:
        raise ManifestError(f"deliverable root does not exist: {root}") from exc
    except OSError as exc:
        raise ManifestError(f"cannot inspect deliverable root {root}: {exc}") from exc
    if stat.S_ISLNK(root_stat.st_mode):
        raise ManifestError("deliverable root must not be a symlink")
    if not stat.S_ISDIR(root_stat.st_mode):
        raise ManifestError("deliverable root must be a directory")
    return (root_stat.st_dev, root_stat.st_ino)


def _walk_error(exc: OSError) -> None:
    raise ManifestError(f"cannot enumerate deliverable subtree: {exc}") from exc


def _scan(root: Path) -> list[tuple[str, Path, tuple[int, int, int, int]]]:
    _root_identity(root)
    found: list[tuple[str, Path, tuple[int, int, int, int]]] = []
    for current, dirnames, filenames in os.walk(
        root, topdown=True, followlinks=False, onerror=_walk_error
    ):
        current_path = Path(current)
        for name in list(dirnames):
            child = current_path / name
            mode = child.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise ManifestError(f"symlink directory is not allowed: {child.relative_to(root).as_posix()}")
            if not stat.S_ISDIR(mode):
                raise ManifestError(f"non-directory entry in directory set: {child.relative_to(root).as_posix()}")
        for name in filenames:
            child = current_path / name
            child_stat = child.lstat()
            mode = child_stat.st_mode
            rel = child.relative_to(root).as_posix()
            if stat.S_ISLNK(mode):
                raise ManifestError(f"symlink file is not allowed: {rel}")
            if not stat.S_ISREG(mode):
                raise ManifestError(f"non-regular file is not allowed: {rel}")
            identity = (child_stat.st_dev, child_stat.st_ino, child_stat.st_size, child_stat.st_mtime_ns)
            found.append((rel, child, identity))
    found.sort(key=lambda item: item[0])
    if not found:
        raise ManifestError("deliverable contains no regular files")
    return found


def _read_stable_file(
    path: Path, rel: str, expected_identity: tuple[int, int, int, int]
) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ManifestError(f"cannot open deliverable file safely: {rel}: {exc}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ManifestError(f"deliverable entry is no longer a regular file: {rel}")
        opened_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        if opened_identity != expected_identity:
            raise ManifestError(f"deliverable file changed after initial scan: {rel}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after:
        raise ManifestError(f"deliverable file changed while hashing: {rel}")
    data = b"".join(chunks)
    if len(data) != after.st_size:
        raise ManifestError(f"deliverable file length changed while hashing: {rel}")
    return data


def build_manifest(root: Path, acceptance_raw: bytes) -> dict[str, Any]:
    # Keep the final path component unresolved so every scan can reject a symlink root.
    root = root.absolute()
    root_before = _root_identity(root)
    first = _scan(root)
    file_entries: list[dict[str, Any]] = []
    for rel, path, identity in first:
        data = _read_stable_file(path, rel, identity)
        file_entries.append({"path": rel, "bytes": len(data), "sha256": _sha256(data)})

    second = _scan(root)
    root_after = _root_identity(root)
    if root_after != root_before:
        raise ManifestError("deliverable root identity changed while hashing")
    first_snapshot = [(rel, identity) for rel, _, identity in first]
    second_snapshot = [(rel, identity) for rel, _, identity in second]
    if first_snapshot != second_snapshot:
        raise ManifestError("deliverable file set or identity changed while hashing")

    file_paths = {entry["path"] for entry in file_entries}
    acceptance = _normalize_acceptance(acceptance_raw, file_paths)
    payload = {
        "schema": SCHEMA,
        "files": file_entries,
        "acceptance": acceptance,
    }
    return {**payload, "manifest_sha256": _sha256(_canonical_bytes(payload))}


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _write_new_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.link(tmp, path)
        except FileExistsError as exc:
            raise ManifestError(f"manifest output already exists: {path}") from exc
        except OSError as exc:
            raise ManifestError(f"cannot publish manifest output {path}: {exc}") from exc
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="deliverable directory to hash")
    parser.add_argument("--acceptance", required=True, type=Path, help="acceptance-map JSON")
    parser.add_argument("--output", required=True, type=Path, help="sidecar manifest path outside root")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root.absolute()
    acceptance = args.acceptance.absolute()
    output = args.output.absolute()

    # Bind the unresolved root pathname before any resolve() can dereference it.
    root_identity = _root_identity(root)
    root_resolved = root.resolve(strict=True)
    if _root_identity(root) != root_identity or _root_identity(root_resolved) != root_identity:
        raise ManifestError("deliverable root identity changed during path resolution")

    acceptance_resolved = acceptance.resolve()
    output_resolved = output.resolve()
    if output_resolved == acceptance_resolved:
        raise ManifestError("manifest output must not alias the acceptance input")
    if _is_within(output_resolved, root_resolved):
        raise ManifestError("manifest output must live outside the deliverable root")

    manifest = build_manifest(root, acceptance.read_bytes())
    if _root_identity(root) != root_identity:
        raise ManifestError("deliverable root identity changed before receipt publication")
    encoded = json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
    _write_new_atomic(output, (encoded + "\n").encode("utf-8"))
    print(manifest["manifest_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
