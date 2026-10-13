"""Fixed-root retained authority storage with identity-safe publication."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Optional

from .core import (
    ActiveKey,
    AuthorityUnavailable,
    InputError,
    KEY_POINTER_SCHEMA,
    MAX_JSON_BYTES,
    _expect_exact_fields,
    _expect_key_id,
    _expect_object,
    _expect_slug,
    strict_json_loads,
)


def _authority_root() -> Path:
    if os.name == "nt":
        raise AuthorityUnavailable(
            "Windows retained-authority custody is unsupported until handle-bound "
            "reparse-point and ACL verification is implemented"
        )
    return Path("/var/lib/commons/organization-contact-pressure")


def _open_flags_read() -> int:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    return flags


def _directory_flags() -> int:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    return flags


def _open_no_symlink_path(path: Path, flags: int, mode: int = 0o600) -> tuple[int, Optional[int], str]:
    """Open a path without following any POSIX path-component symlink.

    The returned parent descriptor remains open so a create caller can fsync the
    directory. Windows lacks compatible ``dir_fd`` semantics; the public retained-
    authority entrypoint fails closed on Windows before this fallback can establish
    production authority.
    """
    candidate = Path(path)
    if not candidate.name or candidate.name in {".", ".."}:
        raise OSError("path has no safe final component")
    if os.name == "nt":
        absolute = candidate.absolute()
        for component in (absolute,) + tuple(absolute.parents):
            if component.is_symlink():
                raise OSError("symlink path component rejected")
        return os.open(candidate, flags, mode), None, candidate.name

    parts = candidate.parts
    if candidate.is_absolute():
        parent_fd = os.open(os.sep, _directory_flags())
        components = parts[1:]
    else:
        parent_fd = os.open(".", _directory_flags())
        components = parts
    if not components:
        os.close(parent_fd)
        raise OSError("path has no components")
    try:
        for component in components[:-1]:
            if component in {"", ".", ".."}:
                raise OSError("unsafe path component")
            next_fd = os.open(component, _directory_flags(), dir_fd=parent_fd)
            try:
                if not stat.S_ISDIR(os.fstat(next_fd).st_mode):
                    raise OSError("path component is not a directory")
            except Exception:
                os.close(next_fd)
                raise
            os.close(parent_fd)
            parent_fd = next_fd
        final_name = components[-1]
        if final_name in {"", ".", ".."} or os.sep in final_name:
            raise OSError("unsafe final path component")
        fd = os.open(final_name, flags, mode, dir_fd=parent_fd)
        return fd, parent_fd, final_name
    except Exception:
        os.close(parent_fd)
        raise


def _read_bounded_fd(fd: int, *, limit: int) -> bytes:
    chunks: list[bytes] = []
    remaining = limit + 1
    while remaining:
        chunk = os.read(fd, min(65536, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    data = b"".join(chunks)
    if len(data) > limit:
        raise AuthorityUnavailable("retained file exceeds limit")
    return data


def _read_open_regular_file(fd: int, *, display_name: str, limit: int, private: bool) -> bytes:
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        raise AuthorityUnavailable(f"retained file is not regular: {display_name}")
    if info.st_size < 0 or info.st_size > limit:
        raise AuthorityUnavailable(f"retained file size invalid: {display_name}")
    if private and os.name != "nt" and (stat.S_IMODE(info.st_mode) & 0o077):
        raise AuthorityUnavailable(f"retained file permissions are not private: {display_name}")
    data = _read_bounded_fd(fd, limit=limit)
    if len(data) != info.st_size:
        raise AuthorityUnavailable(f"retained file changed during read: {display_name}")
    after = os.fstat(fd)
    if (
        after.st_dev != info.st_dev
        or after.st_ino != info.st_ino
        or after.st_size != info.st_size
        or after.st_mtime_ns != info.st_mtime_ns
    ):
        raise AuthorityUnavailable(f"retained file changed during read: {display_name}")
    return data


def _read_regular_file(path: Path, *, limit: int, private: bool) -> bytes:
    try:
        fd, parent_fd, _ = _open_no_symlink_path(path, _open_flags_read())
    except OSError as exc:
        raise AuthorityUnavailable(f"cannot open retained file: {path.name}") from exc
    if parent_fd is not None:
        os.close(parent_fd)
    try:
        return _read_open_regular_file(fd, display_name=path.name, limit=limit, private=private)
    finally:
        os.close(fd)


def _open_directory_fd(path: Path) -> int:
    try:
        fd, parent_fd, _ = _open_no_symlink_path(path, _directory_flags())
    except OSError as exc:
        raise AuthorityUnavailable(f"cannot open retained directory: {path.name}") from exc
    if parent_fd is not None:
        os.close(parent_fd)
    try:
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            raise AuthorityUnavailable(f"retained path is not a directory: {path.name}")
    except Exception:
        os.close(fd)
        raise
    return fd


def _read_regular_file_at(parent_fd: int, name: str, *, limit: int, private: bool) -> bytes:
    if not name or name in {".", ".."} or os.sep in name or (os.altsep and os.altsep in name):
        raise AuthorityUnavailable("unsafe retained entry name")
    try:
        fd = os.open(name, _open_flags_read(), dir_fd=parent_fd)
    except OSError as exc:
        raise AuthorityUnavailable(f"cannot open retained file: {name}") from exc
    try:
        return _read_open_regular_file(fd, display_name=name, limit=limit, private=private)
    finally:
        os.close(fd)


def _read_request_file(path: Path, *, limit: int = MAX_JSON_BYTES) -> bytes:
    try:
        fd, parent_fd, _ = _open_no_symlink_path(path, _open_flags_read())
    except OSError as exc:
        raise InputError(f"cannot open request file: {path}") from exc
    if parent_fd is not None:
        os.close(parent_fd)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise InputError("request must be a regular non-symlink file")
        if info.st_size < 0 or info.st_size > limit:
            raise InputError("request file exceeds size limit")
        data = b""
        while len(data) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(data)))
            if not chunk:
                break
            data += chunk
        if len(data) > limit or len(data) != info.st_size:
            raise InputError("request file changed or exceeded size limit")
        return data
    finally:
        os.close(fd)


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return left.st_dev == right.st_dev and left.st_ino == right.st_ino


def _verify_published_path(path: Path, authored: os.stat_result, expected: bytes) -> None:
    """Prove the requested lexical path still names the exact authored inode/bytes."""
    try:
        visible_fd, visible_parent_fd, _ = _open_no_symlink_path(path, _open_flags_read())
    except OSError as exc:
        raise InputError("output publication path no longer resolves safely") from exc
    if visible_parent_fd is not None:
        os.close(visible_parent_fd)
    try:
        before = os.fstat(visible_fd)
        if not stat.S_ISREG(before.st_mode) or not _same_identity(authored, before):
            raise InputError("output publication identity changed")
        if before.st_size != len(expected):
            raise InputError("output publication size changed")
        chunks: list[bytes] = []
        remaining = len(expected) + 1
        while remaining:
            chunk = os.read(visible_fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        observed = b"".join(chunks)
        after = os.fstat(visible_fd)
        if not _same_identity(authored, after) or before.st_size != after.st_size:
            raise InputError("output publication identity changed during verification")
        if observed != expected:
            raise InputError("output publication bytes changed")
    finally:
        os.close(visible_fd)


def _write_exclusive(path: Path, data: bytes) -> None:
    """Publish once; on any post-create failure leave the pathname untouched.

    Once O_EXCL has made a public directory entry, this process deliberately has no
    exceptional-path pathname deletion authority. A later peer may replace that entry,
    and any check-then-unlink cleanup would be a race capable of deleting the peer's
    successor. Ambiguous/partial authored output is therefore left for explicit owner
    reconciliation rather than being unlinked by this call.
    """
    if not isinstance(data, bytes):
        raise TypeError("output data must be bytes")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd, parent_fd, _ = _open_no_symlink_path(path, flags, 0o600)
    except OSError as exc:
        raise InputError("output path is unsafe, missing, or already exists") from exc

    authored = os.fstat(fd)
    failure: Optional[BaseException] = None
    try:
        offset = 0
        while offset < len(data):
            written = os.write(fd, data[offset:])
            if written <= 0:
                raise OSError("short write")
            offset += written
        os.fsync(fd)
        if parent_fd is not None:
            os.fsync(parent_fd)
        _verify_published_path(path, authored, data)
    except BaseException as exc:
        failure = exc
    finally:
        try:
            os.close(fd)
        finally:
            if parent_fd is not None:
                os.close(parent_fd)

    if failure is not None:
        if isinstance(failure, (KeyboardInterrupt, SystemExit)):
            raise failure
        if isinstance(failure, InputError):
            raise failure
        raise InputError("output publication failed or became ambiguous") from failure


def _load_key_by_id(root: Path, key_id: str) -> bytes:
    _expect_key_id(key_id)
    raw = _read_regular_file(root / "keys" / f"{key_id}.key", limit=128, private=True)
    stripped = raw.strip()
    if len(stripped) != 64:
        raise AuthorityUnavailable("verifier key must be exactly 32 bytes encoded as hex")
    try:
        key = bytes.fromhex(stripped.decode("ascii"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise AuthorityUnavailable("verifier key encoding is invalid") from exc
    if len(key) != 32:
        raise AuthorityUnavailable("verifier key length is invalid")
    return key


def _load_active_key(root: Path) -> ActiveKey:
    raw = _read_regular_file(root / "active-key.json", limit=4096, private=True)
    try:
        pointer = _expect_object(strict_json_loads(raw), "active key pointer")
        _expect_exact_fields(pointer, {"schema", "key_id", "verifier_id"}, "active key pointer")
        if pointer["schema"] != KEY_POINTER_SCHEMA:
            raise InputError("unsupported key pointer schema")
        key_id = _expect_key_id(pointer["key_id"])
        verifier_id = _expect_slug(pointer["verifier_id"], "verifier_id")
    except InputError as exc:
        raise AuthorityUnavailable("active key pointer is malformed") from exc
    return ActiveKey(key_id=key_id, verifier_id=verifier_id, key=_load_key_by_id(root, key_id))
