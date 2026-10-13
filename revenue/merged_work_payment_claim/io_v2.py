from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

from .codec_v2 import ClaimError, MAX_BYTES, strict_loads


def read_regular(path: Path) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise ClaimError(f"read {path}: {exc}") from exc
    if not stat.S_ISREG(before.st_mode):
        raise ClaimError(f"read {path}: regular file required")
    flags = os.O_RDONLY | (getattr(os, "O_NOFOLLOW", 0))
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ClaimError(f"read {path}: {exc}") from exc
    try:
        current = os.fstat(fd)
        if not stat.S_ISREG(current.st_mode) or (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino):
            raise ClaimError(f"read {path}: file identity changed")
        data = os.read(fd, MAX_BYTES + 1)
        if len(data) > MAX_BYTES or os.read(fd, 1):
            raise ClaimError(f"read {path}: file too large")
        return data
    finally:
        os.close(fd)


def load_json_file(path: Path) -> Any:
    try:
        return strict_loads(read_regular(path).decode("utf-8", "strict"))
    except UnicodeDecodeError as exc:
        raise ClaimError(f"read {path}: UTF-8 required") from exc


def write_exclusive(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise ClaimError(f"write {path}: {exc}") from exc
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise ClaimError(f"write {path}: short write")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
