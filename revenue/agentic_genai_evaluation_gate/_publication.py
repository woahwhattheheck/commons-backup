"""Anonymous-inode, single-output publication for gate artifacts."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from .gate import EvidenceError

_READ_CHUNK = 64 * 1024


def _require_descriptor_publication_support() -> tuple[int, int, int]:
    directory_flag = getattr(os, "O_DIRECTORY", 0)
    nofollow_flag = getattr(os, "O_NOFOLLOW", 0)
    tmpfile_flag = getattr(os, "O_TMPFILE", 0)
    supports_dir_fd = (
        os.open in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
        and os.link in os.supports_dir_fd
    )
    if (
        not directory_flag
        or not nofollow_flag
        or not tmpfile_flag
        or not supports_dir_fd
        or not Path("/proc/self/fd").is_dir()
    ):
        raise EvidenceError(
            "anonymous descriptor-relative publication is unsupported on this host"
        )
    return directory_flag, nofollow_flag, tmpfile_flag


def _open_parent_no_follow(parent: Path) -> int:
    directory_flag, nofollow_flag, _ = _require_descriptor_publication_support()
    flags = os.O_RDONLY | directory_flag | nofollow_flag
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY

    if parent.is_absolute():
        current = os.open(os.path.sep, flags)
        parts = parent.parts[1:]
    else:
        current = os.open(".", flags)
        parts = parent.parts

    try:
        for part in parts:
            if part in ("", "."):
                continue
            if part == "..":
                raise EvidenceError("output parent may not contain '..'")
            next_fd = os.open(part, flags, dir_fd=current)
            os.close(current)
            current = next_fd
        return current
    except BaseException:
        os.close(current)
        raise


@dataclass
class _PublicationTarget:
    path: Path
    parent_fd: int
    parent_identity: tuple[int, int]
    name: str
    data: bytes
    file_fd: int | None = None


def _target_key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _assert_absent(parent_fd: int, name: str, path: Path) -> None:
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise FileExistsError(f"{path}: output already exists")


def _drain_write(fd: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(fd, data[offset:])
        if written <= 0:
            raise OSError("short write")
        offset += written


def _fingerprint(
    info: os.stat_result,
) -> tuple[int, int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_nlink,
    )


def _read_fd_exact(fd: int, expected_size: int) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET)
    data = bytearray()
    while len(data) <= expected_size:
        chunk = os.read(
            fd,
            min(_READ_CHUNK, expected_size + 1 - len(data)),
        )
        if not chunk:
            break
        data.extend(chunk)
    return bytes(data)


def _verify_exact_bytes(
    target: _PublicationTarget,
    *,
    expected_links: int,
) -> os.stat_result:
    if target.file_fd is None:
        raise EvidenceError(f"{target.path}: internal publication state error")
    before = os.fstat(target.file_fd)
    if not stat.S_ISREG(before.st_mode):
        raise EvidenceError(f"{target.path}: staged object is not regular")
    if before.st_nlink != expected_links:
        raise EvidenceError(
            f"{target.path}: unexpected retained link count {before.st_nlink}"
        )
    if before.st_size != len(target.data):
        raise EvidenceError(f"{target.path}: staged size mismatch")

    published = _read_fd_exact(target.file_fd, len(target.data))
    after = os.fstat(target.file_fd)
    if _fingerprint(after) != _fingerprint(before):
        raise EvidenceError(
            f"{target.path}: retained generation changed during readback"
        )
    if published != target.data:
        raise EvidenceError(
            f"{target.path}: published bytes differ from requested bytes"
        )
    return after


def _revalidate_target(target: _PublicationTarget, *, final: bool) -> None:
    if not final:
        _verify_exact_bytes(target, expected_links=0)
        return

    retained = _verify_exact_bytes(target, expected_links=1)
    reopened = _open_parent_no_follow(target.path.parent)
    try:
        reopened_info = os.fstat(reopened)
        if (
            reopened_info.st_dev,
            reopened_info.st_ino,
        ) != target.parent_identity:
            raise EvidenceError(
                f"{target.path}: visible parent identity changed during publication"
            )
        visible = os.stat(
            target.name,
            dir_fd=reopened,
            follow_symlinks=False,
        )
        if not stat.S_ISREG(visible.st_mode) or visible.st_nlink != 1:
            raise EvidenceError(
                f"{target.path}: final output is not a single-link regular file"
            )
        if _fingerprint(visible) != _fingerprint(retained):
            raise EvidenceError(
                f"{target.path}: final visible generation changed"
            )
        os.fsync(reopened)
    finally:
        os.close(reopened)


def _preflight(outputs: Sequence[tuple[Path, bytes]]) -> _PublicationTarget:
    if not outputs:
        raise EvidenceError("no publication output requested")

    keys: set[str] = set()
    targets: list[_PublicationTarget] = []
    try:
        for raw_path, data in outputs:
            path = Path(raw_path)
            if not path.name or path.name in {".", ".."}:
                raise EvidenceError(f"{path}: invalid output basename")
            key = _target_key(path)
            if key in keys:
                raise EvidenceError(f"{path}: duplicate output target")
            keys.add(key)

            parent_fd = _open_parent_no_follow(path.parent)
            parent_info = os.fstat(parent_fd)
            target = _PublicationTarget(
                path=path,
                parent_fd=parent_fd,
                parent_identity=(parent_info.st_dev, parent_info.st_ino),
                name=path.name,
                data=data,
            )
            targets.append(target)
            _assert_absent(parent_fd, path.name, path)

        if len(targets) != 1:
            raise EvidenceError(
                "multi-output publication is unsupported; use one transaction per artifact"
            )
        target = targets.pop()
        return target
    finally:
        for target in targets:
            os.close(target.parent_fd)


def _commit_link(target: _PublicationTarget) -> None:
    if target.file_fd is None:
        raise EvidenceError(f"{target.path}: internal publication state error")
    os.link(
        f"/proc/self/fd/{target.file_fd}",
        target.name,
        dst_dir_fd=target.parent_fd,
        follow_symlinks=True,
    )


def _publish_exclusive(
    outputs: Sequence[tuple[Path, bytes]],
    *,
    revalidator: Callable[..., None] | None = None,
    linker: Callable[[_PublicationTarget], None] | None = None,
) -> None:
    """Publish exactly one artifact through an anonymous retained inode.

    The payload is written, made durable, and exact-byte checked while it has no
    pathname. One hard-link operation is the namespace commit. Late destination
    occupation therefore fails before any caller payload becomes visible.
    Failure never triggers pathname deletion.
    """
    target = _preflight(outputs)
    validate = _revalidate_target if revalidator is None else revalidator
    commit = _commit_link if linker is None else linker
    try:
        _, _, tmpfile_flag = _require_descriptor_publication_support()
        flags = os.O_RDWR | tmpfile_flag
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        target.file_fd = os.open(
            ".",
            flags,
            0o600,
            dir_fd=target.parent_fd,
        )
        _drain_write(target.file_fd, target.data)
        os.fsync(target.file_fd)
        validate(target, final=False)

        reopened = _open_parent_no_follow(target.path.parent)
        try:
            reopened_info = os.fstat(reopened)
            if (
                reopened_info.st_dev,
                reopened_info.st_ino,
            ) != target.parent_identity:
                raise EvidenceError(
                    f"{target.path}: visible parent identity changed before commit"
                )
            _assert_absent(reopened, target.name, target.path)
        finally:
            os.close(reopened)

        commit(target)
        validate(target, final=True)
        os.fsync(target.parent_fd)
        validate(target, final=True)
    finally:
        if target.file_fd is not None:
            os.close(target.file_fd)
        os.close(target.parent_fd)
