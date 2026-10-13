from __future__ import annotations

import json
import math
import os
import stat
from pathlib import Path
from typing import Any, Union

MAX_JSON_BYTES = 256 * 1024


def _pairs_no_dupes(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key: {key!r}")
        out[key] = value
    return out


def parse_json_strict(raw: str) -> Any:
    def bad_constant(value: str):
        raise ValueError(f"non-finite JSON number: {value}")

    value = json.loads(raw, object_pairs_hook=_pairs_no_dupes, parse_constant=bad_constant)
    _reject_non_finite(value)
    return value


def _reject_non_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite number")
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise ValueError("JSON object key must be string")
            _reject_non_finite(v)
    elif isinstance(value, list):
        for item in value:
            _reject_non_finite(item)


def read_regular_text(path: Union[str, os.PathLike], *, max_bytes: int = MAX_JSON_BYTES) -> str:
    p = Path(path)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(p, flags)
    try:
        st1 = os.fstat(fd)
        if not stat.S_ISREG(st1.st_mode):
            raise ValueError("input must be a regular file")
        if st1.st_size > max_bytes:
            raise ValueError("input too large")
        chunks = []
        remaining = max_bytes + 1
        while remaining > 0:
            data = os.read(fd, min(65536, remaining))
            if not data:
                break
            chunks.append(data)
            remaining -= len(data)
        raw = b"".join(chunks)
        if len(raw) > max_bytes:
            raise ValueError("input too large")
        st2 = os.fstat(fd)
        if (st1.st_dev, st1.st_ino, st1.st_size, st1.st_mtime_ns) != (
            st2.st_dev,
            st2.st_ino,
            st2.st_size,
            st2.st_mtime_ns,
        ):
            raise ValueError("input changed during read")
        return raw.decode("utf-8", "strict")
    finally:
        os.close(fd)


def write_exclusive(path: Union[str, os.PathLike], data: bytes) -> None:
    p = Path(path)
    parent = p.parent
    parent.mkdir(parents=True, exist_ok=True)
    # Refuse symlinked existing final path and never overwrite anything.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(p, flags, 0o600)
    try:
        offset = 0
        while offset < len(data):
            offset += os.write(fd, data[offset:])
        os.fsync(fd)
    finally:
        os.close(fd)
