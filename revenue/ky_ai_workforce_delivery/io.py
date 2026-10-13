from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

from .model import BundleError

def read_plain_file(path: Path) -> bytes:
    try:
        before = os.lstat(path)
    except OSError as exc:
        raise BundleError(f"cannot stat input: {path}") from exc
    if not stat.S_ISREG(before.st_mode):
        raise BundleError(f"input must be an ordinary regular file: {path}")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise BundleError(f"cannot open input as a plain file: {path}") from exc
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise BundleError(f"input must be a regular file: {path}")
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise BundleError(f"input identity changed while opening: {path}")
        chunks: list[bytes] = []
        while True:
            part = os.read(fd, 1024 * 1024)
            if not part:
                break
            chunks.append(part)
        after = os.fstat(fd)
        if (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise BundleError(f"input changed while reading: {path}")
        return b"".join(chunks)
    finally:
        os.close(fd)


def paths_alias(left: Path, right: Path) -> bool:
    if left.resolve(strict=False) == right.resolve(strict=False):
        return True
    try:
        return os.path.samefile(left, right)
    except (FileNotFoundError, OSError):
        return False


def atomic_write(path: Path, payload: bytes) -> None:
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = os.lstat(path)
    except FileNotFoundError:
        existing = None
    except OSError as exc:
        raise BundleError(f"cannot stat output: {path}") from exc
    if existing is not None and not stat.S_ISREG(existing.st_mode):
        raise BundleError(f"output must be an ordinary regular file or absent: {path}")
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    except Exception:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
        raise

