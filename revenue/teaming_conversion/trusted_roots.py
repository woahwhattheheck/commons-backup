from __future__ import annotations

import os
import stat
from pathlib import Path

from .common import ControlError, MAX_JSON_BYTES

_ROOTS_PATH = Path(__file__).with_name("trusted_roots.json")
_ROOTS_FLAGS = os.O_RDONLY
if hasattr(os, "O_CLOEXEC"):
    _ROOTS_FLAGS |= os.O_CLOEXEC
if hasattr(os, "O_NOFOLLOW"):
    _ROOTS_FLAGS |= os.O_NOFOLLOW


def load_current_roots_bytes(
    _path: Path = _ROOTS_PATH,
    _flags: int = _ROOTS_FLAGS,
    _open=os.open,
    _fstat=os.fstat,
    _read=os.read,
    _close=os.close,
    _is_regular=stat.S_ISREG,
    _max_json_bytes: int = MAX_JSON_BYTES,
) -> bytes:
    """Read the repository-owned current evidence-root registry.

    CURRENT path custody and the operating-system primitives are captured at
    import time.  Rebinding ``_ROOTS_PATH``, ``os`` helpers, or the exported
    loader after import therefore cannot redirect a call that already captured
    this function.  Historical/replay APIs accept explicit roots but label
    their output historical-only.
    """

    try:
        fd = _open(_path, _flags)
    except OSError as exc:
        raise ControlError("current trusted-root registry cannot be opened") from exc
    try:
        info = _fstat(fd)
        if not _is_regular(info.st_mode):
            raise ControlError("current trusted-root registry must be a regular file")
        if info.st_size > _max_json_bytes:
            raise ControlError("current trusted-root registry is too large")
        chunks: list[bytes] = []
        remaining = _max_json_bytes + 1
        while remaining:
            chunk = _read(fd, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > _max_json_bytes:
            raise ControlError("current trusted-root registry is too large")
        return data
    finally:
        _close(fd)
