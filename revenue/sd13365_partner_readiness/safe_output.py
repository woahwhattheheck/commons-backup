#!/usr/bin/env python3
"""Symlink- and parent-swap-safe atomic byte output for SD13365 receipts."""
from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path


class OutputCustodyError(ValueError):
    """Raised when an authority-bearing output path cannot be held safely."""


def _directory_flags() -> int:
    directory = getattr(os, "O_DIRECTORY", None)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if type(directory) is not int or directory == 0:
        raise OutputCustodyError("platform lacks O_DIRECTORY; refusing output")
    if type(nofollow) is not int or nofollow == 0:
        raise OutputCustodyError("platform lacks O_NOFOLLOW; refusing output")
    return os.O_RDONLY | directory | nofollow | getattr(os, "O_CLOEXEC", 0)


def _walk_parent(parent: Path) -> int:
    """Open an already-existing parent chain no-follow and retain its final dirfd.

    Authority-bearing publication deliberately does not create missing directory
    components. There is no portable atomic mkdir+open primitive that proves a
    later no-follow open is the exact directory generation just created rather
    than an ordinary-directory substitution at the same name. Callers that need
    new directories must create them before entering this publication boundary.
    """
    parent = Path(parent)
    flags = _directory_flags()
    try:
        if parent.is_absolute():
            fd = os.open(os.path.sep, flags)
            parts = parent.parts[1:]
        else:
            fd = os.open(".", flags)
            parts = parent.parts
    except (OSError, TypeError, NotImplementedError) as exc:
        raise OutputCustodyError(f"cannot open output path anchor: {exc}") from exc

    try:
        for component in parts:
            if component in ("", "."):
                continue
            if component == "..":
                raise OutputCustodyError("parent traversal '..' is not allowed for output")
            try:
                next_fd = os.open(component, flags, dir_fd=fd)
            except FileNotFoundError as exc:
                raise OutputCustodyError(
                    f"output parent component {component!r} does not already exist"
                ) from exc
            except (OSError, TypeError, NotImplementedError) as exc:
                raise OutputCustodyError(
                    f"output directory component {component!r} is not a safe ordinary directory: {exc}"
                ) from exc
            os.close(fd)
            fd = next_fd
        return fd
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def _identity(fd: int) -> tuple[int, int]:
    try:
        info = os.fstat(fd)
    except OSError as exc:
        raise OutputCustodyError(f"cannot stat retained output directory: {exc}") from exc
    if not stat.S_ISDIR(info.st_mode):
        raise OutputCustodyError("retained output parent is not a directory")
    return info.st_dev, info.st_ino


def _verify_parent_identity(parent: Path, expected: tuple[int, int]) -> None:
    """Fail if the requested parent pathname no longer names the retained directory."""
    verify_fd = _walk_parent(parent)
    try:
        if _identity(verify_fd) != expected:
            raise OutputCustodyError("output parent identity changed during write")
    finally:
        os.close(verify_fd)


def _reject_existing_symlink(name: str, dir_fd: int) -> None:
    try:
        info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    except (OSError, TypeError, NotImplementedError) as exc:
        raise OutputCustodyError(f"cannot inspect output target: {exc}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise OutputCustodyError("refusing to replace a symlink output")
    if stat.S_ISDIR(info.st_mode):
        raise OutputCustodyError("refusing to replace an output directory")


def _create_temp(name: str, dir_fd: int) -> tuple[int, str]:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if type(nofollow) is not int or nofollow == 0:
        raise OutputCustodyError("platform lacks O_NOFOLLOW; refusing output")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow | getattr(os, "O_CLOEXEC", 0)
    for _ in range(8):
        temporary = f".{name}.{secrets.token_hex(16)}.tmp"
        try:
            return os.open(temporary, flags, 0o600, dir_fd=dir_fd), temporary
        except FileExistsError:
            continue
        except (OSError, TypeError, NotImplementedError) as exc:
            raise OutputCustodyError(f"cannot create retained-dirfd temp output: {exc}") from exc
    raise OutputCustodyError("cannot allocate unique temp output")


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Atomically replace one file without re-resolving a mutable parent pathname."""
    path = Path(path)
    if path.name in ("", ".", ".."):
        raise OutputCustodyError("output filename is invalid")
    parent = path.parent
    dir_fd = _walk_parent(parent)
    temp_name: str | None = None
    try:
        parent_identity = _identity(dir_fd)
        _reject_existing_symlink(path.name, dir_fd)
        temp_fd, temp_name = _create_temp(path.name, dir_fd)
        try:
            view = memoryview(payload)
            while view:
                written = os.write(temp_fd, view)
                if written <= 0:
                    raise OutputCustodyError("short write while materializing output")
                view = view[written:]
            os.fsync(temp_fd)
        finally:
            os.close(temp_fd)

        # The first fence catches movement before commit. The second catches the
        # remaining verification->replace window; safety itself still comes from
        # committing only through the retained directory descriptor.
        _verify_parent_identity(parent, parent_identity)
        try:
            os.replace(temp_name, path.name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
            temp_name = None
            os.fsync(dir_fd)
        except (OSError, TypeError, NotImplementedError) as exc:
            raise OutputCustodyError(f"cannot commit retained-dirfd output: {exc}") from exc
        _verify_parent_identity(parent, parent_identity)
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name, dir_fd=dir_fd)
            except FileNotFoundError:
                pass
            except (OSError, TypeError, NotImplementedError):
                pass
        os.close(dir_fd)
