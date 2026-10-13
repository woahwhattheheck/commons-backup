"""Descriptor-relative, no-follow file custody for the parity diagnostic."""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

from errors import ParityError


def _require_secure_io() -> None:
    required_flags = ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK")
    if any(not hasattr(os, name) for name in required_flags):
        raise ParityError("descriptor-relative no-follow file custody is unavailable on this platform")
    supports_dir_fd = getattr(os, "supports_dir_fd", set())
    if any(fn not in supports_dir_fd for fn in (os.open, os.stat)):
        raise ParityError("descriptor-relative file custody is unavailable on this platform")


def _identity(st: os.stat_result) -> tuple[int, int]:
    return (st.st_dev, st.st_ino)


def _open_parent_dir(path: Path) -> tuple[int, str, tuple[int, int]]:
    """Open every ancestor without following symlinks and retain the final parent."""
    _require_secure_io()
    absolute = Path(os.path.abspath(os.fspath(path)))
    parts = absolute.parts
    if len(parts) < 2:
        raise ParityError(f"invalid file path: {path}")
    name = parts[-1]
    if name in ("", ".", ".."):
        raise ParityError(f"invalid final path component: {path}")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        current = os.open(parts[0], flags)
    except OSError as exc:
        raise ParityError(f"cannot open filesystem root for {path}: {exc}") from exc
    try:
        for component in parts[1:-1]:
            if component in ("", ".", ".."):
                raise ParityError(f"unsafe ancestor component in path: {path}")
            try:
                nxt = os.open(component, flags, dir_fd=current)
            except OSError as exc:
                raise ParityError(f"cannot open output/input ancestor without following symlink: {path}: {exc}") from exc
            os.close(current)
            current = nxt
        identity = _identity(os.fstat(current))
        return current, name, identity
    except Exception:
        os.close(current)
        raise


def _visible_parent_matches(path: Path, expected: tuple[int, int]) -> bool:
    try:
        fd, _, identity = _open_parent_dir(path)
    except ParityError:
        return False
    try:
        return identity == expected
    finally:
        os.close(fd)


def read_bounded_regular(path: Path, max_bytes: int) -> bytes:
    parent_fd, name, parent_identity = _open_parent_dir(path)
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        try:
            fd = os.open(name, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise ParityError(f"cannot open regular input without following symlink: {path}: {exc}") from exc
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise ParityError(f"input is not regular file: {path}")
            if before.st_size > max_bytes:
                raise ParityError(f"input exceeds {max_bytes} bytes: {path}")
            data = bytearray()
            while len(data) <= max_bytes:
                chunk = os.read(fd, min(131072, max_bytes + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            after = os.fstat(fd)
            fingerprint_before = (before.st_dev, before.st_ino, before.st_mode, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            fingerprint_after = (after.st_dev, after.st_ino, after.st_mode, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
            if fingerprint_before != fingerprint_after or len(data) != after.st_size:
                raise ParityError(f"input changed while reading: {path}")
            if len(data) > max_bytes:
                raise ParityError(f"input exceeds {max_bytes} bytes: {path}")
            try:
                visible_leaf = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except OSError as exc:
                raise ParityError(f"input final component changed while reading: {path}: {exc}") from exc
            if _identity(visible_leaf) != _identity(after) or not stat.S_ISREG(visible_leaf.st_mode):
                raise ParityError(f"input final component identity changed while reading: {path}")
            if not _visible_parent_matches(path, parent_identity):
                raise ParityError(f"input ancestor generation changed while reading: {path}")
            return bytes(data)
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def _reserve_output(path: Path) -> dict[str, Any]:
    parent_fd, name, parent_identity = _open_parent_dir(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        try:
            fd = os.open(name, flags, 0o600, dir_fd=parent_fd)
        except OSError as exc:
            raise ParityError(f"output must be new ordinary file: {path}: {exc}") from exc
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            os.close(fd)
            raise ParityError(f"output is not ordinary file: {path}")
        return {
            "path": path,
            "parent_fd": parent_fd,
            "parent_identity": parent_identity,
            "name": name,
            "fd": fd,
            "file_identity": _identity(st),
        }
    except Exception:
        os.close(parent_fd)
        raise


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    offset = 0
    while offset < len(view):
        written = os.write(fd, view[offset:])
        if written <= 0:
            raise ParityError("short output write")
        offset += written
    os.fsync(fd)


def _cleanup_reserved(item: dict[str, Any]) -> None:
    """Retire only the inode we still own; never pathname-delete during rollback.

    POSIX has no portable atomic "unlink this name only if it still names this
    inode" primitive exposed here. A stat(name)->unlink(name) cleanup is therefore
    unsafe under same-directory substitution. We fail visibly instead: truncate
    the retained owned descriptor best-effort and leave any surviving directory
    entry as a zero-byte tombstone for explicit operator cleanup. If an attacker
    has renamed the owned inode and installed a foreign successor at the original
    name, only the renamed owned inode is truncated; the foreign path is untouched.
    """
    try:
        try:
            os.ftruncate(item["fd"], 0)
            os.fsync(item["fd"])
        except OSError:
            pass
    finally:
        try:
            os.close(item["fd"])
        except OSError:
            pass
        try:
            os.close(item["parent_fd"])
        except OSError:
            pass


def _validate_reserved(item: dict[str, Any], expected_size: int) -> None:
    written = os.fstat(item["fd"])
    if _identity(written) != item["file_identity"] or not stat.S_ISREG(written.st_mode) or written.st_size != expected_size:
        raise ParityError(f"output inode/size changed during publication: {item['path']}")
    try:
        visible = os.stat(item["name"], dir_fd=item["parent_fd"], follow_symlinks=False)
    except OSError as exc:
        raise ParityError(f"output final component changed during publication: {item['path']}: {exc}") from exc
    if _identity(visible) != item["file_identity"] or not stat.S_ISREG(visible.st_mode) or visible.st_size != expected_size:
        raise ParityError(f"output final component identity/size changed during publication: {item['path']}")
    if not _visible_parent_matches(item["path"], item["parent_identity"]):
        raise ParityError(f"output ancestor generation changed during publication: {item['path']}")


def _validate_output_set(opened: list[dict[str, Any]], payloads: tuple[tuple[Path, bytes], ...]) -> None:
    """Validate every retained inode, visible leaf, and visible parent generation."""
    for item, (_, data) in zip(opened, payloads, strict=True):
        _validate_reserved(item, len(data))


def write_pair_exclusive(json_path: Path, json_data: bytes, md_path: Path, md_data: bytes) -> None:
    if os.path.abspath(os.fspath(json_path)) == os.path.abspath(os.fspath(md_path)):
        raise ParityError("report JSON and Markdown paths must differ")
    opened: list[dict[str, Any]] = []
    payloads = ((json_path, json_data), (md_path, md_data))
    try:
        # Reserve the complete output set before writing any bytes.
        for path, _ in payloads:
            opened.append(_reserve_output(path))
        for item, (_, data) in zip(opened, payloads, strict=True):
            _write_all(item["fd"], data)
        _validate_output_set(opened, payloads)
        # Persist directory entries while the retained directory generations are held.
        for item in opened:
            try:
                os.fsync(item["parent_fd"])
            except OSError:
                pass
        # Directory fsync may block, which creates one final substitution seam after
        # the pre-persistence checks. Revalidate the complete visible output set
        # immediately after persistence and before descriptor close/success.
        _validate_output_set(opened, payloads)
    except Exception:
        for item in reversed(opened):
            _cleanup_reserved(item)
        raise
    else:
        for item in opened:
            os.close(item["fd"])
            os.close(item["parent_fd"])
