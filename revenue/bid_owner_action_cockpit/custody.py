"""POSIX descriptor-anchored local I/O; no network or action authority.

All output names are reserved before content is written. This is not a crash-
atomic multi-file transaction or protection from arbitrary same-user code.
"""
from __future__ import annotations

import os
import stat
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass

from .core import ValidationError

MAX_INPUT_BYTES = 2_000_000
_DIR_FD_FUNCTIONS = (os.open, os.stat, os.unlink)
_STAT = os.stat


def _require_primitives() -> None:
    if (os.name != "posix"
            or not all(getattr(os, flag, 0) for flag in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK"))
            or not all(fn in os.supports_dir_fd for fn in _DIR_FD_FUNCTIONS)
            or _STAT not in os.supports_follow_symlinks):
        raise ValidationError("descriptor-relative no-follow I/O is unavailable on this platform")


def _identity(st):
    return st.st_dev, st.st_ino


def _fingerprint(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_size,
            st.st_mtime_ns, st.st_ctime_ns)


@dataclass
class _Parent:
    fd: int
    name: str
    # Every parent -> child binding stays anchored to the initial root/cwd FD.
    links: list[tuple[int, str, int]]

    def check(self) -> None:
        for parent_fd, component, child_fd in self.links:
            entry = os.stat(component, dir_fd=parent_fd, follow_symlinks=False)
            opened = os.fstat(child_fd)
            if not stat.S_ISDIR(entry.st_mode) or _identity(entry) != _identity(opened):
                raise ValidationError("directory generation changed during I/O")


@contextmanager
def _parent(path):
    _require_primitives()
    path = os.fspath(path)
    if type(path) is not str or not path or "\0" in path:
        raise ValidationError("path must be a nonempty text pathname without NUL")
    if path.startswith("//") or path.endswith("/"):
        raise ValidationError("ambiguous root or directory-only path")
    components = path.split("/")
    if components[-1] in {"", ".", ".."}:
        raise ValidationError("directory-only path is unsupported")
    name = components[-1]
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    fds = []
    links = []
    try:
        root = os.open("/" if path.startswith("/") else ".", flags)
        fds.append(root)
        for component in components[:-1]:
            if component in {"", "."}:
                continue
            child = os.open(component, flags, dir_fd=fds[-1])
            links.append((fds[-1], component, child))
            fds.append(child)
        retained = _Parent(fds[-1], name, links)
        retained.check()
        yield retained
    except OSError as exc:
        raise ValidationError(f"retained pathname I/O failed: {exc.strerror}") from exc
    finally:
        for fd in reversed(fds):
            os.close(fd)


def read_regular(path, limit: int = MAX_INPUT_BYTES) -> bytes:
    if type(limit) is not int or not 0 <= limit <= MAX_INPUT_BYTES:
        raise ValidationError("invalid input byte limit")
    with _parent(path) as parent:
        inspected = os.stat(parent.name, dir_fd=parent.fd, follow_symlinks=False)
        # Refuse FIFO/device inputs before open (including on no-writer FIFOs).
        if not stat.S_ISREG(inspected.st_mode):
            raise ValidationError("input is not a regular file")
        if inspected.st_size > limit:
            raise ValidationError(f"input exceeds {limit} bytes")
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(parent.name, flags, dir_fd=parent.fd)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or _fingerprint(before) != _fingerprint(inspected):
                raise ValidationError("input generation changed before read")
            chunks, total = [], 0
            while True:
                chunk = os.read(fd, min(65536, limit + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > limit:
                    raise ValidationError(f"input exceeds {limit} bytes")
            after = os.fstat(fd)
            visible = os.stat(parent.name, dir_fd=parent.fd, follow_symlinks=False)
            parent.check()
            if (_fingerprint(before) != _fingerprint(after)
                    or _fingerprint(after) != _fingerprint(visible)
                    or total != after.st_size):
                raise ValidationError("input generation changed during read")
            return b"".join(chunks)
        finally:
            os.close(fd)


def write_bundle(outputs) -> None:
    """Publish one or more (path, bytes) pairs, without overwriting any entry.

    All files and ancestor FDs remain open through validation and rollback.
    Cleanup checks the retained directory's entry identity before unlinking;
    it never resolves a replacement parent by pathname.
    """
    outputs = list(outputs)
    if not outputs or len(outputs) > 16 or any(type(data) is not bytes for _, data in outputs):
        raise ValidationError("output bundle requires 1..16 byte payloads")
    reserved = []
    success = False
    with ExitStack() as stack:
        try:
            # No writes until EVERY requested output has an exclusive reservation.
            for path, data in outputs:
                parent = stack.enter_context(_parent(path))
                flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
                fd = os.open(parent.name, flags, 0o600, dir_fd=parent.fd)
                try:
                    created = os.fstat(fd)
                    if not stat.S_ISREG(created.st_mode):
                        raise ValidationError("output is not a regular file")
                except BaseException:
                    os.close(fd)
                    raise
                reserved.append((parent, fd, _identity(created), data))
            for parent, fd, identity, data in reserved:
                parent.check()
                view = memoryview(data)
                offset = 0
                while offset < len(view):
                    written = os.write(fd, view[offset:])
                    if written <= 0:
                        raise ValidationError("short output write")
                    offset += written
                os.fsync(fd)
            # Validate every published generation after all payloads were written.
            for parent, fd, identity, data in reserved:
                before = os.fstat(fd)
                if _identity(before) != identity or before.st_size != len(data):
                    raise ValidationError("output generation or size changed")
                os.lseek(fd, 0, os.SEEK_SET)
                offset = 0
                while offset < len(data):
                    chunk = os.read(fd, min(65536, len(data) - offset))
                    if not chunk or chunk != data[offset:offset + len(chunk)]:
                        raise ValidationError("output bytes changed")
                    offset += len(chunk)
                after = os.fstat(fd)
                visible = os.stat(parent.name, dir_fd=parent.fd, follow_symlinks=False)
                if _fingerprint(before) != _fingerprint(after) or _fingerprint(after) != _fingerprint(visible):
                    raise ValidationError("output entry no longer names authored generation")
                parent.check()
                os.fsync(parent.fd)
            success = True
        except OSError as exc:
            raise ValidationError(f"output publication failed: {exc.strerror}") from exc
        finally:
            # Keep file FDs open until cleanup so their inode identities cannot recycle.
            for parent, fd, identity, _ in reversed(reserved):
                try:
                    if not success:
                        try:
                            entry = os.stat(parent.name, dir_fd=parent.fd, follow_symlinks=False)
                            if stat.S_ISREG(entry.st_mode) and _identity(entry) == identity:
                                os.unlink(parent.name, dir_fd=parent.fd)
                        except OSError:
                            pass
                finally:
                    os.close(fd)


def write_exclusive(path, data: bytes) -> None:
    write_bundle([(path, data)])
