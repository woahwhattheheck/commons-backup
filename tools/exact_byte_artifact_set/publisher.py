"""Atomic exact-byte publication for small artifact sets.

The canonical publication event is one no-clobber directory rename. This module
proves exact bytes for the staged directory generation at that commit point; it
does not claim that an equivalent-authority actor cannot mutate the committed
generation later.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import re
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

RECEIPT_SCHEMA = "exact-byte-artifact-set-receipt/v2"
MAX_FILES = 64
MAX_LEAF_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
RENAME_NOREPLACE = 1
_SAFE_LEAF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


class PublicationError(RuntimeError):
    """Publication failed before a success receipt could be issued."""


class PartialPublicationError(PublicationError):
    """Publication failed after a staging generation was allocated.

    No pathname cleanup is attempted. ``publication_committed`` tells callers
    whether the atomic target-directory rename had already succeeded.
    """

    def __init__(
        self,
        message: str,
        created_leaves: tuple[str, ...],
        staging_name: str,
        publication_committed: bool,
    ):
        super().__init__(message)
        self.created_leaves = created_leaves
        self.staging_name = staging_name
        self.publication_committed = publication_committed


@dataclass(frozen=True)
class _FileGeneration:
    dev: int
    ino: int
    mode: int
    size: int
    mtime_ns: int
    ctime_ns: int

    @classmethod
    def from_stat(cls, value: os.stat_result) -> "_FileGeneration":
        return cls(
            dev=value.st_dev,
            ino=value.st_ino,
            mode=value.st_mode,
            size=value.st_size,
            mtime_ns=value.st_mtime_ns,
            ctime_ns=value.st_ctime_ns,
        )


@dataclass(frozen=True)
class _DirGeneration:
    dev: int
    ino: int
    mode: int

    @classmethod
    def from_stat(cls, value: os.stat_result) -> "_DirGeneration":
        return cls(dev=value.st_dev, ino=value.st_ino, mode=value.st_mode)


def _required_platform_flags() -> tuple[int, int]:
    missing = [name for name in ("O_DIRECTORY", "O_NOFOLLOW") if not hasattr(os, name)]
    if missing or os.open not in getattr(os, "supports_dir_fd", set()):
        detail = ", ".join(missing) if missing else "dir_fd os.open"
        raise PublicationError(f"required retained-directory primitives unavailable: {detail}")
    return os.O_DIRECTORY, os.O_NOFOLLOW


def _safe_leaf_name(name: object) -> str:
    if not isinstance(name, str) or not _SAFE_LEAF.fullmatch(name):
        raise PublicationError(f"unsafe leaf name: {name!r}")
    if name in {".", ".."} or "/" in name or "\\" in name or "\x00" in name:
        raise PublicationError(f"unsafe leaf name: {name!r}")
    return name


def _normalize_artifacts(artifacts: Mapping[str, bytes]) -> tuple[tuple[str, bytes], ...]:
    if not isinstance(artifacts, Mapping):
        raise PublicationError("artifacts must be a mapping of leaf name to exact bytes")
    if not artifacts:
        raise PublicationError("artifact set must be non-empty")
    if len(artifacts) > MAX_FILES:
        raise PublicationError(f"artifact set exceeds {MAX_FILES} leaves")

    normalized: list[tuple[str, bytes]] = []
    total = 0
    seen: set[str] = set()
    for raw_name, raw_bytes in artifacts.items():
        name = _safe_leaf_name(raw_name)
        if name in seen:
            raise PublicationError(f"duplicate artifact leaf name: {name}")
        seen.add(name)
        if type(raw_bytes) is not bytes:
            raise PublicationError(f"artifact {name!r} must be exact bytes")
        if len(raw_bytes) > MAX_LEAF_BYTES:
            raise PublicationError(f"artifact {name!r} exceeds {MAX_LEAF_BYTES} bytes")
        total += len(raw_bytes)
        if total > MAX_TOTAL_BYTES:
            raise PublicationError(f"artifact set exceeds {MAX_TOTAL_BYTES} bytes")
        normalized.append((name, raw_bytes))
    normalized.sort(key=lambda item: item[0])
    return tuple(normalized)


def _split_path(path: Path) -> tuple[bool, tuple[str, ...]]:
    text = os.fspath(path)
    if not isinstance(text, str) or not text:
        raise PublicationError("directory path must be non-empty text")
    raw_parts = Path(text).parts
    if any(part == os.pardir for part in raw_parts):
        raise PublicationError("directory path may not contain '..'")
    absolute = os.path.isabs(text)
    norm = os.path.normpath(text)
    if norm == os.curdir:
        return absolute, ()
    if absolute:
        parts = tuple(part for part in Path(norm).parts if part not in (os.sep, ""))
    else:
        parts = tuple(part for part in Path(norm).parts if part not in ("", os.curdir))
    return absolute, parts


def _open_retained_directory(path: Path) -> tuple[int, _DirGeneration]:
    o_directory, o_nofollow = _required_platform_flags()
    absolute, parts = _split_path(path)
    flags = os.O_RDONLY | o_directory | o_nofollow | getattr(os, "O_CLOEXEC", 0)
    current_fd = os.open(os.sep if absolute else os.curdir, flags)
    try:
        for component in parts:
            next_fd = os.open(component, flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        st = os.fstat(current_fd)
        if not stat.S_ISDIR(st.st_mode):
            raise PublicationError("retained generation is not a directory")
        return current_fd, _DirGeneration.from_stat(st)
    except BaseException:
        os.close(current_fd)
        raise


def _assert_dir_generation(fd: int, expected: _DirGeneration) -> None:
    actual = _DirGeneration.from_stat(os.fstat(fd))
    if actual != expected or not stat.S_ISDIR(actual.mode):
        raise PublicationError("retained directory generation changed")


def _assert_directory_path(path: Path, fd: int, expected: _DirGeneration) -> None:
    try:
        visible = os.lstat(path)
    except OSError as exc:
        raise PublicationError(f"directory path changed before publication: {path}") from exc
    held = _DirGeneration.from_stat(os.fstat(fd))
    current = _DirGeneration.from_stat(visible)
    if stat.S_ISLNK(visible.st_mode) or held != expected or current != expected:
        raise PublicationError(f"directory path changed before publication: {path}")


def _require_absent_at(parent_fd: int, name: str, label: str) -> None:
    try:
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    kind = "symlink" if stat.S_ISLNK(current.st_mode) else "entry"
    raise FileExistsError(f"refusing existing {kind} at {label}: {name}")


def _create_stage(parent_fd: int) -> tuple[str, int, _DirGeneration]:
    o_directory, o_nofollow = _required_platform_flags()
    flags = os.O_RDONLY | o_directory | o_nofollow | getattr(os, "O_CLOEXEC", 0)
    for _ in range(32):
        name = f".exact-byte-stage-{secrets.token_hex(16)}"
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            continue
        try:
            fd = os.open(name, flags, dir_fd=parent_fd)
            try:
                held = _DirGeneration.from_stat(os.fstat(fd))
                visible = _DirGeneration.from_stat(
                    os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                )
                if held != visible or not stat.S_ISDIR(held.mode):
                    raise PublicationError("staging directory changed during acquisition")
                return name, fd, held
            except BaseException:
                os.close(fd)
                raise
        except BaseException as exc:
            raise PartialPublicationError(str(exc), (), name, False) from exc
    raise FileExistsError("could not allocate unique staging directory")


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    offset = 0
    while offset < len(view):
        written = os.write(fd, view[offset:])
        if written <= 0:
            raise PublicationError("short write made no progress")
        offset += written


def _retained_bytes_match(fd: int, expected: bytes) -> bool:
    os.lseek(fd, 0, os.SEEK_SET)
    offset = 0
    while offset < len(expected):
        chunk = os.read(fd, min(65536, len(expected) - offset))
        if not chunk or chunk != expected[offset:offset + len(chunk)]:
            return False
        offset += len(chunk)
    return not os.read(fd, 1)


def _assert_retained_bytes(fd: int, expected: bytes, final_generation: _FileGeneration) -> None:
    before = _FileGeneration.from_stat(os.fstat(fd))
    if before != final_generation:
        raise PublicationError("retained artifact metadata changed before byte verification")
    matches = _retained_bytes_match(fd, expected)
    after = _FileGeneration.from_stat(os.fstat(fd))
    if after != before:
        raise PublicationError("retained artifact generation changed during byte verification")
    if not matches:
        raise PublicationError("retained artifact bytes differ from expected bytes")


def _assert_visible_identity(
    directory_fd: int, name: str, expected: _FileGeneration, expected_size: int
) -> None:
    try:
        visible = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise PublicationError(f"artifact disappeared from staging generation: {name}") from exc
    if not stat.S_ISREG(visible.st_mode):
        raise PublicationError(f"staged artifact is not a regular file: {name}")
    if (visible.st_dev, visible.st_ino, visible.st_mode, visible.st_size) != (
        expected.dev,
        expected.ino,
        expected.mode,
        expected_size,
    ):
        raise PublicationError(f"staged artifact no longer names retained generation: {name}")


def _assert_visible_directory_identity(
    parent_fd: int, name: str, held_fd: int, expected: _DirGeneration
) -> None:
    try:
        visible = _DirGeneration.from_stat(os.stat(name, dir_fd=parent_fd, follow_symlinks=False))
    except OSError as exc:
        raise PublicationError(f"published directory generation is not visible: {name}") from exc
    held = _DirGeneration.from_stat(os.fstat(held_fd))
    if visible != expected or held != expected or not stat.S_ISDIR(visible.mode):
        raise PublicationError(f"published directory generation changed: {name}")


def _fsync_directory(dir_fd: int) -> None:
    os.fsync(dir_fd)


def _rename_noreplace(src_dir_fd: int, src_name: str, dst_dir_fd: int, dst_name: str) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise OSError(errno.ENOSYS, "renameat2(RENAME_NOREPLACE) unavailable")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    rc = renameat2(
        src_dir_fd,
        os.fsencode(src_name),
        dst_dir_fd,
        os.fsencode(dst_name),
        RENAME_NOREPLACE,
    )
    if rc != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err), dst_name)


def _receipt(normalized: tuple[tuple[str, bytes], ...]) -> dict[str, object]:
    artifact_rows = [
        {
            "name": name,
            "length": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        for name, payload in normalized
    ]
    projection = {
        "schema": RECEIPT_SCHEMA,
        "linearization": "RENAME_NOREPLACE_DIRECTORY_GENERATION",
        "post_commit_stability_proven": False,
        "artifacts": artifact_rows,
    }
    canonical = json.dumps(
        projection, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return {
        **projection,
        "publication_committed": True,
        "artifact_set_sha256": hashlib.sha256(canonical).hexdigest(),
    }


def publish_artifact_set(
    output_dir: str | os.PathLike[str], artifacts: Mapping[str, bytes]
) -> dict[str, object]:
    """Atomically commit one exact staged directory generation at ``output_dir``.

    ``output_dir`` must be absent and its parent must already exist. The parent
    generation is a trust boundary: a same-authority actor able to substitute the
    parent or staging entries during this transaction is outside the claimed
    authority. No pathname cleanup is attempted after staging begins.
    """

    normalized = _normalize_artifacts(artifacts)
    target = Path(output_dir)
    target_name = _safe_leaf_name(target.name)
    parent = target.parent

    parent_fd = -1
    stage_fd = -1
    stage_name = ""
    retained: dict[str, tuple[int, bytes, _FileGeneration]] = {}
    created: list[str] = []
    committed = False
    try:
        parent_fd, parent_generation = _open_retained_directory(parent)
        _assert_directory_path(parent, parent_fd, parent_generation)
        _require_absent_at(parent_fd, target_name, "output directory")

        stage_name, stage_fd, stage_generation = _create_stage(parent_fd)
        flags = (
            os.O_CREAT
            | os.O_EXCL
            | os.O_RDWR
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0)
        )
        for name, payload in normalized:
            fd = os.open(name, flags, 0o600, dir_fd=stage_fd)
            created.append(name)
            try:
                _write_all(fd, payload)
                os.fsync(fd)
                generation = _FileGeneration.from_stat(os.fstat(fd))
                if not stat.S_ISREG(generation.mode) or generation.size != len(payload):
                    raise PublicationError(f"retained artifact has unexpected metadata: {name}")
                retained[name] = (fd, payload, generation)
            except BaseException:
                os.close(fd)
                raise

        _fsync_directory(stage_fd)
        _assert_dir_generation(stage_fd, stage_generation)
        for name in (name for name, _payload in normalized):
            fd, payload, generation = retained[name]
            _assert_retained_bytes(fd, payload, generation)
            _assert_visible_identity(stage_fd, name, generation, len(payload))
        _assert_dir_generation(stage_fd, stage_generation)

        # The trusted parent + one no-clobber directory rename provide the
        # set-level linearization point that finite per-leaf verification cannot.
        _assert_directory_path(parent, parent_fd, parent_generation)
        _require_absent_at(parent_fd, target_name, "output directory")
        _assert_visible_directory_identity(parent_fd, stage_name, stage_fd, stage_generation)
        _rename_noreplace(parent_fd, stage_name, parent_fd, target_name)
        committed = True

        # Durability/readback after the linearization point may fail closed, but
        # the committed generation is never destructively rolled back.
        _fsync_directory(parent_fd)
        _assert_dir_generation(parent_fd, parent_generation)
        _assert_directory_path(parent, parent_fd, parent_generation)
        _assert_visible_directory_identity(parent_fd, target_name, stage_fd, stage_generation)
        return _receipt(normalized)
    except BaseException as exc:
        if stage_name and not isinstance(exc, PartialPublicationError):
            raise PartialPublicationError(
                str(exc), tuple(created), stage_name, committed
            ) from exc
        raise
    finally:
        for fd, _payload, _generation in retained.values():
            try:
                os.close(fd)
            except OSError:
                pass
        if stage_fd >= 0:
            try:
                os.close(stage_fd)
            except OSError:
                pass
        if parent_fd >= 0:
            try:
                os.close(parent_fd)
            except OSError:
                pass
