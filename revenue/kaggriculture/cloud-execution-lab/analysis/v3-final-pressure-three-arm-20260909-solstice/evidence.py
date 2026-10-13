"""Immutable input and archive-custody primitives for the SOLSTICE panel."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import tarfile
from typing import Any, Mapping


class EvidenceError(ValueError):
    """Raised when experiment inputs or results cannot support attribution."""


@dataclass(frozen=True)
class Snapshot:
    data: bytes
    sha256: str


def snapshot(path: Path, *, max_bytes: int | None = None) -> Snapshot:
    """Open once without following links, read once, and hash those exact bytes."""
    path = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise EvidenceError(f"Cannot open regular file: {path}: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise EvidenceError(f"Expected regular file: {path}")
        if max_bytes is not None and before.st_size > max_bytes:
            raise EvidenceError(f"File exceeds {max_bytes} bytes: {path}")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            block = os.read(descriptor, min(1 << 20, remaining))
            if not block:
                raise EvidenceError(f"Short file read: {path}")
            chunks.append(block)
            remaining -= len(block)
        if os.read(descriptor, 1):
            raise EvidenceError(f"File grew while reading: {path}")
        after = os.fstat(descriptor)
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        if identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise EvidenceError(f"File changed while reading: {path}")
        data = b"".join(chunks)
    finally:
        os.close(descriptor)
    return Snapshot(data=data, sha256=hashlib.sha256(data).hexdigest())


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def strict_json_bytes(data: bytes, *, label: str) -> Any:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvidenceError(f"{label} is not UTF-8") from exc
    try:
        return json.loads(text, object_pairs_hook=_strict_object)
    except EvidenceError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise EvidenceError(f"Invalid JSON in {label}: {exc}") from exc


def read_json(path: Path, *, max_bytes: int = 1 << 20) -> tuple[Any, Snapshot]:
    snap = snapshot(path, max_bytes=max_bytes)
    return strict_json_bytes(snap.data, label=str(path)), snap


def write_json(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode("utf-8") + b"\n"
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def valid_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def safe_extract(
    archive: Path,
    destination: Path,
    *,
    max_members: int = 10_000,
    max_member_bytes: int = 16 << 20,
    max_total_bytes: int = 128 << 20,
) -> list[str]:
    """Extract only bounded, unique, in-root regular files/directories."""
    archive = Path(archive)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    seen: set[str] = set()
    kinds: dict[str, str] = {}
    regular: list[str] = []
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        if len(members) > max_members:
            raise EvidenceError(f"Archive has too many members: {len(members)}")
        total_bytes = 0
        normalized: list[tuple[tarfile.TarInfo, str]] = []
        for member in members:
            name = member.name
            raw = name[:-1] if member.isdir() and name.endswith("/") else name
            parts = raw.split("/") if isinstance(raw, str) else []
            if (
                not raw
                or raw.startswith("/")
                or "\\" in raw
                or any(part in ("", ".", "..") for part in parts)
            ):
                raise EvidenceError(f"Unsafe archive path: {name!r}")
            if raw in seen:
                raise EvidenceError(f"Duplicate or aliased archive member: {name!r}")
            seen.add(raw)
            if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                raise EvidenceError(f"Unsupported archive member type: {name!r}")
            if not (member.isdir() or member.isfile()):
                raise EvidenceError(f"Unsupported archive member: {name!r}")
            if member.size < 0 or member.size > max_member_bytes:
                raise EvidenceError(f"Archive member size is unsafe: {name!r}")
            if member.isfile():
                total_bytes += member.size
                if total_bytes > max_total_bytes:
                    raise EvidenceError("Archive uncompressed payload exceeds limit")
            target = (destination / raw).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise EvidenceError(f"Archive path escapes destination: {name!r}") from exc
            kind = "dir" if member.isdir() else "file"
            if raw in kinds:
                raise EvidenceError(f"Archive file/directory collision: {name!r}")
            for index in range(1, len(parts)):
                parent_name = "/".join(parts[:index])
                if kinds.get(parent_name) == "file":
                    raise EvidenceError(f"Archive member descends from file: {name!r}")
            if kind == "file" and any(existing.startswith(raw + "/") for existing in kinds):
                raise EvidenceError(f"Archive file shadows directory: {name!r}")
            kinds[raw] = kind
            normalized.append((member, raw))
        for member, raw in normalized:
            target = destination / raw
            if member.isdir():
                target.mkdir(parents=True, exist_ok=False)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = bundle.extractfile(member)
            if source is None:
                raise EvidenceError(f"Cannot read archive member: {member.name!r}")
            data = source.read(max_member_bytes + 1)
            if len(data) != member.size:
                raise EvidenceError(f"Archive member read mismatch: {member.name!r}")
            target.write_bytes(data)
            regular.append(raw)
    return regular


def tree_manifest(root: Path) -> dict[str, dict[str, Any]]:
    """Hash every regular file below ``root`` and reject links/special files."""
    root = Path(root).resolve()
    output: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise EvidenceError(f"Variant contains symlink: {relative}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise EvidenceError(f"Variant contains special file: {relative}")
        snap = snapshot(path)
        output[relative] = {"sha256": snap.sha256, "bytes": len(snap.data)}
    return output


def changed_paths(reference: Mapping[str, Any], candidate: Mapping[str, Any]) -> list[str]:
    names = set(reference) | set(candidate)
    return sorted(name for name in names if reference.get(name) != candidate.get(name))


def manifest_sha256(manifest: Mapping[str, Any]) -> str:
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest()
