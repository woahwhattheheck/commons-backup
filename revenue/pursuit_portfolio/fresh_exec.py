"""Import-time POSIX fork/exec capability for isolated current authority."""
from __future__ import annotations

import os
from typing import Any

from .core import PortfolioError

WORKER_LIMIT = 32 * 1024 * 1024


def make_worker_call(
    executable: str,
    bootstrap: str,
    *,
    _pipe=os.pipe,
    _fork=os.fork if hasattr(os, "fork") else None,
    _dup2=os.dup2,
    _close=os.close,
    _read=os.read,
    _write=os.write,
    _waitpid=os.waitpid,
    _execve=os.execve,
    _exit=os._exit,
    _wifexited=os.WIFEXITED,
    _wexitstatus=os.WEXITSTATUS,
    _error=PortfolioError,
    _limit=WORKER_LIMIT,
) -> Any:
    """Capture one immutable process-launch graph before caller mutation."""
    if _fork is None:
        def unsupported(_: bytes, *, _error=_error) -> bytes:
            raise _error("fresh-process current authority requires POSIX fork/exec")
        return unsupported

    environment = {"LANG": "C", "LC_ALL": "C", "PYTHONHASHSEED": "0"}
    argv = (executable, "-I", "-c", bootstrap)

    def write_all(fd: int, data: bytes) -> None:
        view = memoryview(data)
        while view:
            written = _write(fd, view)
            if written <= 0:
                raise _error("fresh worker request write failed")
            view = view[written:]

    def call(request: bytes) -> bytes:
        if type(request) is not bytes or len(request) > _limit:
            raise _error("fresh worker request exceeds byte bound")
        in_r = in_w = out_r = out_w = -1
        try:
            in_r, in_w = _pipe()
            out_r, out_w = _pipe()
            pid = _fork()
        except BaseException:
            for fd in (in_r, in_w, out_r, out_w):
                if fd >= 0:
                    try:
                        _close(fd)
                    except OSError:
                        pass
            raise

        if pid == 0:  # pragma: no cover - observed through parent boundary
            try:
                _close(in_w)
                _close(out_r)
                _dup2(in_r, 0)
                _dup2(out_w, 1)
                _dup2(out_w, 2)
                if in_r not in (0, 1, 2):
                    _close(in_r)
                if out_w not in (0, 1, 2):
                    _close(out_w)
                _execve(executable, list(argv), environment)
            except BaseException as exc:
                try:
                    _write(
                        2,
                        f"fresh worker exec failed: {type(exc).__name__}\n".encode(),
                    )
                except BaseException:
                    pass
                _exit(127)

        _close(in_r)
        _close(out_w)
        chunks: list[bytes] = []
        total = 0
        pending: BaseException | None = None
        try:
            try:
                write_all(in_w, request)
            finally:
                _close(in_w)
                in_w = -1
            while True:
                chunk = _read(out_r, 65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > _limit:
                    raise _error("fresh worker response exceeds byte bound")
                chunks.append(chunk)
        except BaseException as exc:
            pending = exc
        finally:
            if in_w >= 0:
                try:
                    _close(in_w)
                except OSError:
                    pass
            _close(out_r)
            _, status = _waitpid(pid, 0)
        if pending is not None:
            raise pending

        raw = b"".join(chunks)
        if not _wifexited(status) or _wexitstatus(status) != 0:
            detail = raw[:2048].decode("utf-8", errors="replace").strip()
            raise _error("fresh worker failed" + (f": {detail}" if detail else ""))
        return raw

    return call
