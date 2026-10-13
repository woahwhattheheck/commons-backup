from __future__ import annotations

import os
import stat
from pathlib import Path

from .common import ControlError, MAX_JSON_BYTES


def _open_parent_directory(path: Path) -> tuple[int, str]:
    absolute = path.absolute()
    parts = absolute.parts
    if not parts:
        raise ControlError("path is empty")
    name = parts[-1]
    if name in {"", ".", ".."}:
        raise ControlError("path has an unsafe final component")
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if absolute.anchor:
        fd = os.open(absolute.anchor, flags)
        start = 1
    else:
        fd = os.open(".", flags)
        start = 0
    try:
        for part in parts[start:-1]:
            if part in {"", "."}:
                continue
            if part == "..":
                raise ControlError("parent traversal is not allowed")
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd, name
    except Exception:
        os.close(fd)
        raise


def read_bounded_regular(path: str | os.PathLike[str], *, max_bytes: int = MAX_JSON_BYTES) -> bytes:
    parent_fd, name = _open_parent_directory(Path(path))
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        try:
            fd = os.open(name, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise ControlError(f"cannot open regular input: {path}") from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise ControlError(f"input is not a regular file: {path}")
            if info.st_size > max_bytes:
                raise ControlError(f"input exceeds {max_bytes} bytes: {path}")
            chunks: list[bytes] = []
            remaining = max_bytes + 1
            while remaining:
                chunk = os.read(fd, min(65_536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
            if len(data) > max_bytes:
                raise ControlError(f"input exceeds {max_bytes} bytes: {path}")
            return data
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def _write_exclusive(path: str | os.PathLike[str], data: bytes) -> None:
    if type(data) is not bytes:
        raise ControlError("output payload must be bytes")
    parent_fd, name = _open_parent_directory(Path(path))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        try:
            fd = os.open(name, flags, 0o600, dir_fd=parent_fd)
        except OSError as exc:
            raise ControlError(f"output already exists or is unsafe: {path}") from exc
        try:
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise ControlError(f"short write for output: {path}")
                view = view[written:]
            os.fsync(fd)
        except Exception:
            try:
                os.unlink(name, dir_fd=parent_fd)
            except OSError:
                pass
            raise
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def write_exclusive_pair(
    json_path: str | os.PathLike[str],
    json_bytes: bytes,
    markdown_path: str | os.PathLike[str],
    markdown_bytes: bytes,
) -> None:
    _write_exclusive(json_path, json_bytes)
    try:
        _write_exclusive(markdown_path, markdown_bytes)
    except Exception:
        parent_fd, name = _open_parent_directory(Path(json_path))
        try:
            try:
                os.unlink(name, dir_fd=parent_fd)
            except OSError:
                pass
        finally:
            os.close(parent_fd)
        raise
