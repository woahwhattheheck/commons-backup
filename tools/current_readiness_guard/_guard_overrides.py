from __future__ import annotations

import os
import stat
from pathlib import Path, PurePosixPath

from ._analyzer import analyze_source as _analyze_source_base
from ._model import Finding, PolicyError
from ._review_closure_v2 import additional_findings

MAX_SOURCE_BYTES = 2_000_000


def analyze_source(source: str | bytes, *, path: str = "<memory>") -> list[Finding]:
    return sorted(set([*_analyze_source_base(source, path=path), *additional_findings(source, path=path)]))


def _generation(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _revalidate_visible_chain(
    root: Path,
    directory_parts: tuple[str, ...],
    expected_directories: tuple[tuple[int, ...], ...],
    leaf: str,
    expected_leaf: tuple[int, ...],
) -> None:
    directory_flag = getattr(os, "O_DIRECTORY", 0)
    nofollow_flag = getattr(os, "O_NOFOLLOW", 0)
    opened: list[int] = []
    try:
        current_fd = os.open(root, os.O_RDONLY | directory_flag | nofollow_flag)
        opened.append(current_fd)
        if not expected_directories or _generation(os.fstat(current_fd)) != expected_directories[0]:
            raise PolicyError("source ancestor generation changed while reading")
        for index, part in enumerate(directory_parts, start=1):
            next_fd = os.open(
                part,
                os.O_RDONLY | directory_flag | nofollow_flag,
                dir_fd=current_fd,
            )
            opened.append(next_fd)
            current_fd = next_fd
            if index >= len(expected_directories) or _generation(os.fstat(current_fd)) != expected_directories[index]:
                raise PolicyError("source ancestor generation changed while reading")
        visible_leaf = os.stat(leaf, dir_fd=current_fd, follow_symlinks=False)
        if _generation(visible_leaf) != expected_leaf:
            raise PolicyError("source generation changed while reading")
    except OSError as exc:
        raise PolicyError(f"source ancestor revalidation failure: {exc}") from exc
    finally:
        for fd in reversed(opened):
            os.close(fd)


def read_source(root: Path, relative: PurePosixPath) -> bytes:
    directory_flag = getattr(os, "O_DIRECTORY", 0)
    nofollow_flag = getattr(os, "O_NOFOLLOW", 0)
    nonblock_flag = getattr(os, "O_NONBLOCK", 0)
    opened_directories: list[int] = []
    directory_generations: list[tuple[int, ...]] = []
    file_fd: int | None = None
    try:
        current_fd = os.open(root, os.O_RDONLY | directory_flag | nofollow_flag)
        opened_directories.append(current_fd)
        directory_generations.append(_generation(os.fstat(current_fd)))
        parts = relative.parts
        if not parts:
            raise PolicyError("source path is empty")
        for part in parts[:-1]:
            next_fd = os.open(
                part,
                os.O_RDONLY | directory_flag | nofollow_flag,
                dir_fd=current_fd,
            )
            opened_directories.append(next_fd)
            current_fd = next_fd
            directory_generations.append(_generation(os.fstat(current_fd)))
        leaf = parts[-1]
        visible_before = os.stat(leaf, dir_fd=current_fd, follow_symlinks=False)
        if stat.S_ISLNK(visible_before.st_mode):
            raise PolicyError(f"source path contains symlink: {relative.as_posix()}")
        file_fd = os.open(
            leaf,
            os.O_RDONLY | nofollow_flag | nonblock_flag,
            dir_fd=current_fd,
        )
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode):
            raise PolicyError("source is not a regular file")
        if before.st_size > MAX_SOURCE_BYTES:
            raise PolicyError(f"source exceeds {MAX_SOURCE_BYTES} bytes")
        chunks: list[bytes] = []
        remaining = MAX_SOURCE_BYTES + 1
        while remaining:
            chunk = os.read(file_fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(file_fd)
        visible_after = os.stat(leaf, dir_fd=current_fd, follow_symlinks=False)
        if len(raw) > MAX_SOURCE_BYTES:
            raise PolicyError(f"source exceeds {MAX_SOURCE_BYTES} bytes")
        if (
            _generation(visible_before) != _generation(before)
            or _generation(before) != _generation(after)
            or _generation(after) != _generation(visible_after)
        ):
            raise PolicyError("source generation changed while reading")
        if len(raw) != before.st_size:
            raise PolicyError("source length changed while reading")
        _revalidate_visible_chain(
            root,
            tuple(parts[:-1]),
            tuple(directory_generations),
            leaf,
            _generation(after),
        )
        return raw
    except (OSError, PolicyError) as exc:
        if isinstance(exc, PolicyError):
            raise
        raise PolicyError(f"source open/read failure: {exc}") from exc
    finally:
        if file_fd is not None:
            os.close(file_fd)
        for fd in reversed(opened_directories):
            os.close(fd)


__all__ = ["analyze_source", "read_source"]
