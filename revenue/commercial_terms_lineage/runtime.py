"""Production runtime boundary for commercial terms lineage.

The deterministic engine in ``lineage.py`` accepts an explicit trusted time so its
state machine can be tested and historically replayed. This module is the public
*current* surface: it owns current UTC, applies the stricter production-current
policy guard, and uses stable descriptor-based file ingress. Callers cannot backdate
or forward-date a current compile/verification.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import stat
from typing import Any, Mapping

try:
    from .lineage import (
        MAX_FILE_BYTES,
        TermsLineageError,
        loads_strict,
        verify_review as _verify_review_at,
    )
    from .policy import compile_current_state as _compile_current_state
except ImportError:  # direct execution/tests from package directory
    from lineage import (  # type: ignore
        MAX_FILE_BYTES,
        TermsLineageError,
        loads_strict,
        verify_review as _verify_review_at,
    )
    from policy import compile_current_state as _compile_current_state  # type: ignore


def _utc_now() -> datetime:
    """Process-owned current UTC. Tests may patch this private seam."""
    return datetime.now(timezone.utc)


def compile_current(
    authority: Mapping[str, Any],
    review: Mapping[str, Any],
    *,
    previous_authority: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile current owner-review state using process-owned UTC + policy guard."""
    return _compile_current_state(
        authority,
        review,
        as_of=_utc_now(),
        previous_authority=previous_authority,
    )


def verify_current(
    authority: Mapping[str, Any],
    review: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    previous_authority: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify historical receipt integrity, then return freshly recomputed current state.

    A byte-identical receipt can be historically valid while its source/decision TTL
    has since expired. The public current verifier therefore proves the supplied
    receipt first, then recompiles the same retained authority/review at one
    process-owned current UTC sample. It never returns an old CLEAR as current.
    """
    now = _utc_now().astimezone(timezone.utc).replace(microsecond=0)
    _verify_review_at(
        authority,
        review,
        receipt,
        previous_authority=previous_authority,
        trusted_now=now,
    )
    return _compile_current_state(
        authority,
        review,
        as_of=now,
        previous_authority=previous_authority,
    )


def _generation(info: os.stat_result) -> tuple[int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        getattr(info, "st_mtime_ns", int(info.st_mtime * 1_000_000_000)),
    )


def read_json_file(path: str | os.PathLike[str], *, max_bytes: int = MAX_FILE_BYTES) -> Any:
    """Read one stable ordinary-file generation, rejecting path or in-read swaps."""
    p = Path(path)
    try:
        before_path = os.lstat(p)
    except OSError as exc:
        raise TermsLineageError(f"cannot stat input: {p}") from exc
    if stat.S_ISLNK(before_path.st_mode) or not stat.S_ISREG(before_path.st_mode):
        raise TermsLineageError("input must be an ordinary non-symlink file")

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(p, flags)
    except OSError as exc:
        raise TermsLineageError(f"cannot open input: {p}") from exc
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise TermsLineageError("input changed to non-regular file")
        if (opened.st_dev, opened.st_ino) != (before_path.st_dev, before_path.st_ino):
            raise TermsLineageError("input path generation changed before open")

        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining > 0:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > max_bytes or os.read(fd, 1):
            raise TermsLineageError("input exceeds byte limit")

        finished = os.fstat(fd)
        if _generation(finished) != _generation(opened):
            raise TermsLineageError("input changed while being read")
    finally:
        os.close(fd)

    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise TermsLineageError("input must be strict UTF-8") from exc
    return loads_strict(text)


def write_exclusive(path: str | os.PathLike[str], content: str) -> None:
    """Create one output without following/overwriting the final path; handle short writes."""
    p = Path(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(p, flags, 0o600)
    except FileExistsError as exc:
        raise TermsLineageError(f"refusing to overwrite output: {p}") from exc
    except OSError as exc:
        raise TermsLineageError(f"cannot create output: {p}") from exc
    try:
        payload = content.encode("utf-8")
        view = memoryview(payload)
        written = 0
        while written < len(payload):
            count = os.write(fd, view[written:])
            if count <= 0:
                raise TermsLineageError("short write while creating output")
            written += count
        os.fsync(fd)
    finally:
        os.close(fd)
