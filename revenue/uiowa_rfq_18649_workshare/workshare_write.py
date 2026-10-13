#!/usr/bin/env python3
"""Descriptor-relative, generation-fenced output publication."""
from __future__ import annotations

import errno
import os
from pathlib import Path
import stat
from typing import Iterable

from workshare_contract import ContractError



def _directory_fingerprint(st: os.stat_result) -> tuple[int, int, int]:
    return (stat.S_IFMT(st.st_mode), st.st_dev, st.st_ino)


def _open_parent_chain(path: Path) -> tuple[str, list[int], list[tuple[int, str, int, tuple[int, int, int]]]]:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ContractError("safe descriptor-relative output publication is unavailable")
    final_name = path.name
    if final_name in {"", ".", ".."}:
        raise ContractError("output filename is invalid")

    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0)
    if path.is_absolute():
        start = os.open("/", flags)
        components = list(path.parent.parts)[1:]
    else:
        start = os.open(".", flags)
        components = list(path.parent.parts)
    fds = [start]
    links: list[tuple[int, str, int, tuple[int, int, int]]] = []
    try:
        for component in components:
            if component in {"", "."}:
                continue
            if component == "..":
                raise ContractError("output parent traversal is forbidden")
            child_flags = flags | os.O_NOFOLLOW
            try:
                child = os.open(component, child_flags, dir_fd=fds[-1])
            except OSError as exc:
                raise ContractError(f"cannot open output parent component safely: {component}: {exc.strerror}") from exc
            child_stat = os.fstat(child)
            if not stat.S_ISDIR(child_stat.st_mode):
                os.close(child)
                raise ContractError(f"output parent component is not directory: {component}")
            links.append((fds[-1], component, child, _directory_fingerprint(child_stat)))
            fds.append(child)
        return final_name, fds, links
    except Exception:
        for fd in reversed(fds):
            try:
                os.close(fd)
            except OSError:
                pass
        raise


def _verify_parent_chain(links: Iterable[tuple[int, str, int, tuple[int, int, int]]]) -> None:
    for parent_fd, component, child_fd, initial in links:
        current_fd = os.fstat(child_fd)
        try:
            visible = os.stat(component, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise ContractError(f"output parent component disappeared: {component}") from exc
        if _directory_fingerprint(current_fd) != initial or _directory_fingerprint(visible) != initial:
            raise ContractError(f"output parent generation changed: {component}")


def _write_exclusive(path: Path, data: bytes) -> None:
    final_name, fds, links = _open_parent_chain(path)
    parent_fd = fds[-1]
    file_fd: int | None = None
    try:
        try:
            os.stat(final_name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ContractError(f"refusing existing output path: {path}")

        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        try:
            file_fd = os.open(final_name, flags, 0o600, dir_fd=parent_fd)
        except OSError as exc:
            if exc.errno in {errno.EEXIST, errno.ELOOP}:
                raise ContractError(f"refusing existing output path: {path}") from exc
            raise ContractError(f"cannot create output safely: {path}: {exc.strerror}") from exc
        created = os.fstat(file_fd)
        if not stat.S_ISREG(created.st_mode):
            raise ContractError(f"created output is not regular file: {path}")
        offset = 0
        while offset < len(data):
            written = os.write(file_fd, data[offset:])
            if written <= 0:
                raise ContractError(f"short write made no progress: {path}")
            offset += written
        os.fsync(file_fd)
        final_fd_stat = os.fstat(file_fd)
        visible = os.stat(final_name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(visible.st_mode):
            raise ContractError(f"visible output is not regular file: {path}")
        expected_identity = (final_fd_stat.st_dev, final_fd_stat.st_ino, final_fd_stat.st_size)
        visible_identity = (visible.st_dev, visible.st_ino, visible.st_size)
        if expected_identity != visible_identity or final_fd_stat.st_size != len(data):
            raise ContractError(f"output pathname no longer names created generation: {path}")
        _verify_parent_chain(links)
        os.fsync(parent_fd)
    finally:
        if file_fd is not None:
            try:
                os.close(file_fd)
            except OSError:
                pass
        for fd in reversed(fds):
            try:
                os.close(fd)
            except OSError:
                pass
        # Deliberately no pathname cleanup: after creation, a pathname may have
        # been replaced by a foreign generation. Truthful partial output is
        # safer than deleting a path we no longer own.


