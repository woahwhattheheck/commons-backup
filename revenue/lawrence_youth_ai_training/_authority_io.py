from __future__ import annotations

import os
import stat
from pathlib import Path

from ._common import MAX_JSON_BYTES, SemanticAuthorityUnavailable

def _fixed_path_parts(path: Path) -> list[Path]:
    if not path.is_absolute():
        raise SemanticAuthorityUnavailable("authority path must be absolute")
    components = path.parts
    if any(component in {".", ".."} for component in components[1:]):
        raise SemanticAuthorityUnavailable("authority path must not contain dot segments")
    parts: list[Path] = []
    current = Path(path.anchor)
    for component in components[1:-1]:
        current = current / component
        parts.append(current)
    return parts


def _read_fixed_regular(path: Path, *, secret: bool) -> bytes:
    if os.name != "posix":
        raise SemanticAuthorityUnavailable("production authority custody requires POSIX")
    try:
        for ancestor in _fixed_path_parts(path):
            st = os.lstat(ancestor)
            if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode):
                raise SemanticAuthorityUnavailable("authority ancestor is not a real directory")
            if st.st_uid != 0 or st.st_mode & 0o022:
                raise SemanticAuthorityUnavailable("authority ancestor is not root-owned/non-writable")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
    except (OSError, SemanticAuthorityUnavailable) as exc:
        if isinstance(exc, SemanticAuthorityUnavailable):
            raise
        raise SemanticAuthorityUnavailable("fixed authority file is unavailable") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != 0:
            raise SemanticAuthorityUnavailable("authority file custody is invalid")
        if secret:
            if before.st_mode & 0o077:
                raise SemanticAuthorityUnavailable("authority key permissions are not private")
        elif before.st_mode & 0o022:
            raise SemanticAuthorityUnavailable("authority envelope is group/other writable")
        if before.st_size < 1 or before.st_size > MAX_JSON_BYTES:
            raise SemanticAuthorityUnavailable("authority file size is invalid")
        chunks: list[bytes] = []
        remaining = MAX_JSON_BYTES + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) != before.st_size or len(raw) > MAX_JSON_BYTES:
            raise SemanticAuthorityUnavailable("authority file changed or exceeded bounds")
        after = os.fstat(fd)
        fingerprint_before = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_nlink,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        fingerprint_after = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_nlink,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if fingerprint_before != fingerprint_after:
            raise SemanticAuthorityUnavailable("authority file changed during read")
        visible = os.lstat(path)
        if (visible.st_dev, visible.st_ino) != (after.st_dev, after.st_ino):
            raise SemanticAuthorityUnavailable("authority pathname changed during read")
        return raw
    except OSError as exc:
        raise SemanticAuthorityUnavailable("authority file read failed") from exc
    finally:
        os.close(fd)
