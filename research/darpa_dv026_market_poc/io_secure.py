from __future__ import annotations

import os
from pathlib import Path
import stat

try:
    from .contract import ContractError
except ImportError:
    from contract import ContractError

MAX_INPUT = 2 * 1024 * 1024

def _read_regular(path: Path) -> bytes:
    initial = path.lstat()
    if stat.S_ISLNK(initial.st_mode) or not stat.S_ISREG(initial.st_mode):
        raise ContractError(f"input must be ordinary regular file: {path}")
    if initial.st_size > MAX_INPUT:
        raise ContractError(f"input exceeds {MAX_INPUT} bytes")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        initial_fp = (initial.st_dev, initial.st_ino, initial.st_size, initial.st_mtime_ns, initial.st_ctime_ns, initial.st_mode)
        before_fp = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns, before.st_mode)
        if initial_fp != before_fp:
            raise ContractError("input generation changed before open")
        raw = b""
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            raw += chunk
            if len(raw) > MAX_INPUT:
                raise ContractError("input grew beyond size limit")
        after = os.fstat(fd)
        fp_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns, before.st_mode)
        fp_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_mode)
        if fp_before != fp_after or len(raw) != before.st_size:
            raise ContractError("input generation changed during read")
        return raw
    finally:
        os.close(fd)


def _write_exclusive(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise ContractError(f"refuse existing output: {path}")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    ok = False
    st = None
    try:
        view = memoryview(raw)
        while view:
            n = os.write(fd, view)
            if n <= 0:
                raise OSError("short output write")
            view = view[n:]
        os.fsync(fd)
        st = os.fstat(fd)
        visible = path.lstat()
        if not stat.S_ISREG(visible.st_mode) or (st.st_dev, st.st_ino, st.st_size) != (visible.st_dev, visible.st_ino, visible.st_size):
            raise ContractError("visible output generation mismatch")
        ok = True
    finally:
        os.close(fd)
        if not ok:
            try:
                visible = path.lstat()
                if st is not None and visible.st_dev == st.st_dev and visible.st_ino == st.st_ino:
                    path.unlink()
            except Exception:
                pass


