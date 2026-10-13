"""Crash-released, nonblocking process locks for the existing swarm workers."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path


class LockUnavailable(RuntimeError):
    """The lock road failed; this is different from another live lock holder."""


def take(path):
    """Return an acquired handle, None for contention, or raise unavailable.

    Match command_center.core's refresh-lock implementation: lock one byte
    with msvcrt on Windows, and use flock on Unix. Closing the handle or exiting
    releases custody; a retained filename is never evidence of a live holder.
    """
    handle = None
    try:
        handle = Path(path).open("a+b")
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (11, 13, 35, 36) or getattr(exc, "winerror", None) in (33, 36):
                handle.close()
                return None
            raise
        return handle
    except (OSError, ImportError) as exc:
        if handle is not None:
            handle.close()
        raise LockUnavailable("Process lock unavailable") from exc


def release(handle):
    try:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


@contextmanager
def held(path):
    """Yield acquired/busy/unavailable and release acquired custody on exit."""
    try:
        handle = take(path)
    except LockUnavailable:
        yield "unavailable"
        return
    if handle is None:
        yield "busy"
        return
    try:
        yield "acquired"
    finally:
        release(handle)
