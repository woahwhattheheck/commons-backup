from __future__ import annotations

import os
import stat
from pathlib import Path

from .gate import GateError


def read_bounded_regular(path: str | Path, max_bytes: int) -> bytes:
    """Read one stable regular-file generation through a retained descriptor.

    The generation fingerprint includes mode and ctime in addition to device,
    inode, size, and mtime so a same-inode/same-size rewrite cannot hide by
    restoring the original mtime before the post-read check.
    """
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    fd = os.open(Path(path), flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise GateError("input_not_regular")
        if before.st_size > max_bytes:
            raise GateError("input_too_large")
        out = bytearray()
        while True:
            remaining = max_bytes + 1 - len(out)
            if remaining <= 0:
                raise GateError("input_too_large")
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            out.extend(chunk)
            if len(out) > max_bytes:
                raise GateError("input_too_large")
        after = os.fstat(fd)
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            getattr(before, "st_mtime_ns", None),
            getattr(before, "st_ctime_ns", None),
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            getattr(after, "st_mtime_ns", None),
            getattr(after, "st_ctime_ns", None),
        )
        if identity_before != identity_after or after.st_size != len(out):
            raise GateError("input_changed_during_read")
        return bytes(out)
    finally:
        os.close(fd)
