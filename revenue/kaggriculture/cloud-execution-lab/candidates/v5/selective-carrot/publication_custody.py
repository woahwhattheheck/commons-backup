# SPDX-License-Identifier: Apache-2.0
"""Fail-closed create-exclusive publication for a small set of evidence files.

The helper reserves every final pathname before writing any payload. It is for
build/evidence publication, not gameplay. The contract is deliberately
cooperative-race safe: pre-existing finals are never overwritten and rollback
removes a path only when the final-path identity check still matches the inode
reserved by this call. Reservation fds stay open through those rollback checks
on POSIX so an unlinked owned inode cannot be recycled before the check. Windows
does not permit deletion through these open CRT descriptors, so rollback closes
them before the same identity-checked cleanup. This is not an atomic defense
against a hostile pathname replacement between that identity check and unlink.

Before success, every pathname is re-opened without following the final symlink
(where supported), re-authenticated against the reserved inode, and its exact
payload is verified.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
from typing import Iterable


@dataclass(frozen=True)
class _OwnedFile:
    path: Path
    fd: int
    dev: int
    ino: int
    payload: bytes


def _resolved(path: Path) -> Path:
    return path.expanduser().absolute().resolve(strict=False)


def _flags(base: int) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    # The Windows CRT defaults descriptors to text mode. Binary artifacts can
    # contain both newlines and byte 0x1a (DOS EOF), so every payload descriptor
    # must opt into byte-preserving I/O. O_BINARY is zero/absent on POSIX.
    return base | nofollow | getattr(os, "O_BINARY", 0)


def _os_path(path: Path) -> str:
    """Return an OS path that preserves Windows paths beyond MAX_PATH."""
    raw = os.path.abspath(os.fspath(path))
    if os.name != "nt" or raw.startswith("\\\\?\\"):
        return raw
    if raw.startswith("\\\\"):
        return "\\\\?\\UNC\\" + raw[2:]
    return "\\\\?\\" + raw


def _reserve(path: Path, payload: bytes) -> _OwnedFile:
    os.makedirs(_os_path(path.parent), exist_ok=True)
    fd = os.open(_os_path(path), _flags(os.O_WRONLY | os.O_CREAT | os.O_EXCL), 0o644)
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode):
        os.close(fd)
        raise OSError(f"reserved publication path is not regular: {path}")
    return _OwnedFile(path=path, fd=fd, dev=st.st_dev, ino=st.st_ino,
                      payload=payload)


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("short publication write")
        view = view[written:]
    os.fsync(fd)


def _path_identity(path: Path):
    try:
        st = os.lstat(_os_path(path))
    except FileNotFoundError:
        return None
    return st.st_dev, st.st_ino, st.st_mode


def _unlink_if_owned(owned: _OwnedFile) -> None:
    identity = _path_identity(owned.path)
    if identity is None:
        return
    dev, ino, _ = identity
    if (dev, ino) != (owned.dev, owned.ino):
        return
    try:
        os.unlink(_os_path(owned.path))
    except FileNotFoundError:
        pass


def _verify_final(owned: _OwnedFile) -> None:
    identity = _path_identity(owned.path)
    if identity is None:
        raise OSError(f"publication path disappeared: {owned.path}")
    dev, ino, mode = identity
    if not stat.S_ISREG(mode) or (dev, ino) != (owned.dev, owned.ino):
        raise OSError(f"publication path identity changed: {owned.path}")

    fd = os.open(_os_path(owned.path), _flags(os.O_RDONLY))
    try:
        st = os.fstat(fd)
        if (st.st_dev, st.st_ino) != (owned.dev, owned.ino):
            raise OSError(f"publication reopen identity changed: {owned.path}")
        body = bytearray()
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            body.extend(chunk)
    finally:
        os.close(fd)
    if len(body) != len(owned.payload):
        raise OSError(f"publication size mismatch: {owned.path}")
    if hashlib.sha256(body).digest() != hashlib.sha256(owned.payload).digest():
        raise OSError(f"publication digest mismatch: {owned.path}")

    final = _path_identity(owned.path)
    if final is None or final[:2] != (owned.dev, owned.ino) or not stat.S_ISREG(final[2]):
        raise OSError(f"publication path changed after verification: {owned.path}")


def _fsync_parents(paths: Iterable[Path]) -> None:
    # CPython's Windows ``os.open`` cannot open a directory descriptor, so it
    # cannot provide the POSIX directory-fsync durability step. The individual
    # files have already been fsynced and re-opened for exact identity/payload
    # verification. Keep that supported contract usable rather than rolling a
    # successful byte-exact publication back solely because the directory-handle
    # operation is unavailable on Windows.
    if os.name == "nt":
        return
    seen = set()
    for path in paths:
        parent = _resolved(path.parent)
        if parent in seen:
            continue
        seen.add(parent)
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        fd = os.open(parent, flags)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _close_owned(owned: Iterable[_OwnedFile]) -> None:
    for item in owned:
        try:
            os.close(item.fd)
        except OSError:
            pass


def publish_exclusive(files: Iterable[tuple[Path, bytes]]) -> None:
    """Publish all ``(path, payload)`` pairs as one create-exclusive transaction.

    All paths are reserved before any bytes are written. Inputs must name at
    least two distinct final paths; this helper is intentionally for related
    artifact+receipt style publication. On failure, rollback identity checks run
    while reservation fds are still open, and only matching pathnames are
    unlinked. On success, every final path is re-authenticated and
    payload-verified before parent directories are fsynced on platforms that
    expose directory descriptors. Windows fsyncs and verifies each file but
    cannot perform the POSIX directory-fsync step through ``os.open``.
    """
    requested = [(Path(path), bytes(payload)) for path, payload in files]
    if len(requested) < 2:
        raise ValueError("exclusive publication requires at least two files")
    resolved = [_resolved(path) for path, _ in requested]
    if len(set(resolved)) != len(resolved):
        raise ValueError("publication paths must be distinct")

    owned: list[_OwnedFile] = []
    try:
        for path, payload in requested:
            owned.append(_reserve(path, payload))
        for item in owned:
            _write_all(item.fd, item.payload)
        for item in owned:
            _verify_final(item)
        _fsync_parents(item.path for item in owned)
    except Exception:
        # POSIX keeps reservation fds open until after every rollback identity
        # check. Windows forbids unlinking these open files, and the handle lock
        # already blocks pathname replacement until close, so close first there.
        # Cleanup remains best-effort and never masks the publication failure.
        if os.name == "nt":
            _close_owned(owned)
            for item in reversed(owned):
                try:
                    _unlink_if_owned(item)
                except OSError:
                    pass
        else:
            try:
                for item in reversed(owned):
                    try:
                        _unlink_if_owned(item)
                    except OSError:
                        pass
            finally:
                _close_owned(owned)
        raise
    else:
        _close_owned(owned)
