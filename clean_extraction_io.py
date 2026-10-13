"""Stable file I/O and fresh-tree hashing for clean extraction replay."""
from __future__ import annotations

import errno
import hashlib
import os
import stat
import tempfile
from pathlib import Path

from clean_extraction_manifest import ReplayError


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_read(path: Path, limit: int, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ReplayError(f"cannot open {label} safely: {exc}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ReplayError(f"invalid or oversized {label}")
        parts = []
        total = 0
        while True:
            chunk = os.read(fd, min(1 << 20, limit - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise ReplayError(f"{label} exceeds byte limit")
            parts.append(chunk)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    identity = lambda value: (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
    )
    if identity(before) != identity(after) or total != after.st_size:
        raise ReplayError(f"{label} changed while reading")
    return b"".join(parts)


def hash_fresh(root: Path):
    rows, folded = [], {}

    def walk_error(exc):
        raise ReplayError(f"fresh extraction enumeration failed: {exc}") from exc

    for current, dirs, files in os.walk(
        root, topdown=True, followlinks=False, onerror=walk_error
    ):
        current_path = Path(current)
        for name in dirs:
            path = current_path / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise ReplayError("unsafe extracted directory")
        for name in files:
            path = current_path / name
            info = path.lstat()
            rel = path.relative_to(root).as_posix()
            fold = rel.casefold()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise ReplayError("unsafe extracted file")
            if fold in folded and folded[fold] != rel:
                raise ReplayError("case-fold ambiguous extracted paths")
            folded[fold] = rel
            data = stable_read(path, 1 << 62, "extracted file")
            rows.append({"path": rel, "bytes": len(data), "sha256": sha256(data)})
    return sorted(rows, key=lambda row: row["path"])


def write_new(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temp = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp, path)
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                raise ReplayError("receipt output already exists") from exc
            raise ReplayError(f"cannot publish receipt: {exc}") from exc
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
