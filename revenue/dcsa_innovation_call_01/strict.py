"""Strict JSON and file-custody helpers for the DCSA pursuit carrier."""
from __future__ import annotations

import datetime as dt
import errno
import json
import os
import stat
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence, Tuple

MAX_INPUT_BYTES = 4 * 1024 * 1024
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_SET_BYTES = 32 * 1024 * 1024
UTC = dt.timezone.utc


class DcsaError(Exception):
    pass


class ValidationError(DcsaError):
    pass


class CustodyError(DcsaError):
    pass


def _pairs_to_dict(pairs: Sequence[Tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValidationError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_constant(token: str) -> None:
    raise ValidationError(f"non-finite JSON number is forbidden: {token}")


def strict_json_loads(data: bytes | str) -> Any:
    if isinstance(data, bytes):
        try:
            text = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ValidationError("JSON input is not strict UTF-8") from exc
    elif isinstance(data, str):
        text = data
    else:
        raise ValidationError("JSON input must be bytes or text")
    try:
        return json.loads(text, object_pairs_hook=_pairs_to_dict, parse_constant=_reject_constant)
    except ValidationError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValidationError("JSON input is malformed") from exc


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValidationError("value is not canonical-JSON serializable") from exc


def require_exact_keys(value: Any, expected: Iterable[str], *, field: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        raise ValidationError(f"{field} must be a plain JSON object")
    expected_set = set(expected)
    actual_set = set(value)
    missing = sorted(expected_set - actual_set)
    extra = sorted(actual_set - expected_set)
    if missing or extra:
        raise ValidationError(f"{field} has an invalid schema; missing={missing}, extra={extra}")
    return value


def require_plain_list(value: Any, *, field: str) -> list[Any]:
    if type(value) is not list:
        raise ValidationError(f"{field} must be a JSON array")
    return value


def require_string(value: Any, *, field: str, minimum: int = 1, maximum: int = 512) -> str:
    if type(value) is not str:
        raise ValidationError(f"{field} must be a string")
    if not minimum <= len(value) <= maximum:
        raise ValidationError(f"{field} length must be between {minimum} and {maximum}")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValidationError(f"{field} contains a control character")
    return value


def require_bool(value: Any, *, field: str) -> bool:
    if type(value) is not bool:
        raise ValidationError(f"{field} must be a JSON boolean")
    return value


def require_int(value: Any, *, field: str, minimum: int = 0, maximum: int = 2**31 - 1) -> int:
    if type(value) is not int:
        raise ValidationError(f"{field} must be an integer")
    if not minimum <= value <= maximum:
        raise ValidationError(f"{field} must be between {minimum} and {maximum}")
    return value


def require_hex64(value: Any, *, field: str) -> str:
    text = require_string(value, field=field, minimum=64, maximum=64)
    if any(ch not in "0123456789abcdef" for ch in text):
        raise ValidationError(f"{field} must be 64 lowercase hexadecimal characters")
    return text


def require_nullable_hex64(value: Any, *, field: str) -> str | None:
    return None if value is None else require_hex64(value, field=field)


def parse_utc(value: Any, *, field: str) -> dt.datetime:
    text = require_string(value, field=field, minimum=20, maximum=20)
    if not text.endswith("Z"):
        raise ValidationError(f"{field} must use canonical UTC seconds")
    try:
        parsed = dt.datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ValidationError(f"{field} is not a valid timestamp") from exc
    if parsed.tzinfo is None or parsed.microsecond != 0:
        raise ValidationError(f"{field} must use canonical UTC seconds")
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != text:
        raise ValidationError(f"{field} must be canonical UTC")
    return parsed.astimezone(UTC)


def format_utc(value: dt.datetime) -> str:
    if not isinstance(value, dt.datetime) or value.tzinfo is None:
        raise ValidationError("timestamp must be timezone-aware")
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _path_parts(path: Path) -> tuple[Path, list[str]]:
    if path.is_absolute():
        root, parts = Path(path.anchor), list(path.parts[1:])
    else:
        root, parts = Path("."), list(path.parts)
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise CustodyError("path must not contain empty, dot, or dot-dot components")
    return root, parts


def _open_parent_dir(path: Path) -> tuple[int, str]:
    root, parts = _path_parts(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(str(root), flags)
    except OSError as exc:
        raise CustodyError("could not open path root") from exc
    try:
        for component in parts[:-1]:
            try:
                next_fd = os.open(component, flags, dir_fd=fd)
            except OSError as exc:
                raise CustodyError("path ancestor is missing, non-directory, or symlinked") from exc
            os.close(fd)
            fd = next_fd
        return fd, parts[-1]
    except Exception:
        os.close(fd)
        raise


def _metadata_tuple(st: os.stat_result) -> tuple[int, int, int, int, int, int, int, int]:
    return (int(st.st_dev), int(st.st_ino), int(st.st_mode), int(st.st_nlink), int(st.st_uid), int(st.st_size), int(st.st_mtime_ns), int(st.st_ctime_ns))


def read_bounded_regular_file(path: str | os.PathLike[str], *, limit: int = MAX_INPUT_BYTES) -> bytes:
    if type(limit) is not int or isinstance(limit, bool) or limit < 1:
        raise ValidationError("file limit must be a positive integer")
    parent_fd, name = _open_parent_dir(Path(path))
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        try:
            fd = os.open(name, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise CustodyError("input is missing, inaccessible, or symlinked") from exc
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise CustodyError("input must be a regular file")
            if before.st_nlink < 1 or before.st_size > limit:
                raise CustodyError("input is unstable or exceeds the byte limit")
            chunks: list[bytes] = []
            remaining = limit + 1
            while remaining > 0:
                chunk = os.read(fd, min(64 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
            if len(data) > limit:
                raise CustodyError("input exceeds the byte limit")
            after = os.fstat(fd)
            if _metadata_tuple(before) != _metadata_tuple(after):
                raise CustodyError("input file generation changed during capture")
            visible = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if stat.S_ISLNK(visible.st_mode) or (visible.st_dev, visible.st_ino) != (after.st_dev, after.st_ino):
                raise CustodyError("input pathname no longer names the captured generation")
            if len(data) != after.st_size:
                raise CustodyError("captured byte count does not match the stable file size")
            return data
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def read_root_owned_regular_file(path: str | os.PathLike[str], *, limit: int = MAX_INPUT_BYTES) -> bytes:
    if os.name != "posix":
        raise CustodyError("current host trust is supported only on POSIX")
    if type(limit) is not int or isinstance(limit, bool) or limit < 1:
        raise ValidationError("file limit must be a positive integer")
    parent_fd, name = _open_parent_dir(Path(path))
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        try:
            fd = os.open(name, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise CustodyError("fixed host trust is missing, inaccessible, or symlinked") from exc
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise CustodyError("fixed host trust must be one regular-file generation")
            if before.st_uid != 0:
                raise CustodyError("fixed host trust must be root-owned")
            if stat.S_IMODE(before.st_mode) & 0o022:
                raise CustodyError("fixed host trust must not be group/other writable")
            if before.st_size > limit:
                raise CustodyError("fixed host trust exceeds the byte limit")
            chunks: list[bytes] = []
            remaining = limit + 1
            while remaining > 0:
                chunk = os.read(fd, min(64 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
            if len(data) > limit:
                raise CustodyError("fixed host trust exceeds the byte limit")
            after = os.fstat(fd)
            if _metadata_tuple(before) != _metadata_tuple(after):
                raise CustodyError("fixed host trust changed during capture")
            try:
                visible = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except OSError as exc:
                raise CustodyError("fixed host trust pathname changed after capture") from exc
            if stat.S_ISLNK(visible.st_mode) or (visible.st_dev, visible.st_ino) != (after.st_dev, after.st_ino):
                raise CustodyError("fixed host trust pathname no longer names the captured generation")
            if len(data) != after.st_size:
                raise CustodyError("captured byte count does not match fixed host file size")
            return data
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def _rollback_created_outputs(created: list[tuple[int, str, int, int]]) -> list[str]:
    errors: list[str] = []
    touched_parents: set[tuple[int, int]] = set()
    for parent_fd, name, device, inode in reversed(created):
        try:
            visible = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            continue
        except OSError as exc:
            errors.append(f"could not inspect rollback target {name!r}: {exc}")
            continue
        if stat.S_ISLNK(visible.st_mode) or (visible.st_dev, visible.st_ino) != (device, inode):
            errors.append(f"rollback target {name!r} no longer names the created generation")
            continue
        try:
            os.unlink(name, dir_fd=parent_fd)
            parent_st = os.fstat(parent_fd)
            touched_parents.add((int(parent_st.st_dev), int(parent_st.st_ino)))
        except OSError as exc:
            errors.append(f"could not remove created output {name!r}: {exc}")
    synced: set[tuple[int, int]] = set()
    for parent_fd, _name, _device, _inode in created:
        try:
            parent_st = os.fstat(parent_fd)
            key = (int(parent_st.st_dev), int(parent_st.st_ino))
            if key in touched_parents and key not in synced:
                os.fsync(parent_fd)
                synced.add(key)
        except OSError as exc:
            errors.append(f"could not fsync rollback parent: {exc}")
    return errors


def write_exclusive_regular_files(outputs: Mapping[str | os.PathLike[str], bytes], *, limit: int = MAX_OUTPUT_BYTES, total_limit: int = MAX_OUTPUT_SET_BYTES) -> None:
    if not isinstance(outputs, Mapping) or not outputs:
        raise ValidationError("output set must be a non-empty mapping")
    if type(limit) is not int or isinstance(limit, bool) or limit < 1:
        raise ValidationError("output limit must be a positive integer")
    if type(total_limit) is not int or isinstance(total_limit, bool) or total_limit < 1:
        raise ValidationError("output-set limit must be a positive integer")

    entries: list[tuple[int, str, bytes, tuple[int, int, str]]] = []
    parent_fds: list[int] = []
    destination_keys: set[tuple[int, int, str]] = set()
    total = 0
    try:
        for raw_path, data in outputs.items():
            if not isinstance(data, bytes):
                raise ValidationError("every output value must be bytes")
            if len(data) > limit:
                raise CustodyError("output exceeds the per-file byte limit")
            total += len(data)
            if total > total_limit:
                raise CustodyError("output set exceeds the aggregate byte limit")
            try:
                path = Path(raw_path)
            except TypeError as exc:
                raise ValidationError("every output destination must be path-like") from exc
            parent_fd, name = _open_parent_dir(path)
            parent_fds.append(parent_fd)
            parent_st = os.fstat(parent_fd)
            key = (int(parent_st.st_dev), int(parent_st.st_ino), name)
            if key in destination_keys:
                raise CustodyError("output destinations must be unique")
            destination_keys.add(key)
            try:
                os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            except OSError as exc:
                if exc.errno != errno.ENOENT:
                    raise CustodyError("output destination could not be preflighted") from exc
            else:
                raise CustodyError("output already exists")
            entries.append((parent_fd, name, data, key))

        created: list[tuple[int, str, int, int]] = []
        try:
            for parent_fd, name, data, _key in entries:
                flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                try:
                    fd = os.open(name, flags, 0o600, dir_fd=parent_fd)
                except OSError as exc:
                    raise CustodyError("output creation failed after preflight") from exc
                try:
                    created_st = os.fstat(fd)
                    created.append((parent_fd, name, int(created_st.st_dev), int(created_st.st_ino)))
                    view = memoryview(data)
                    written = 0
                    while written < len(view):
                        count = os.write(fd, view[written:])
                        if count <= 0:
                            raise CustodyError("short output write made no progress")
                        written += count
                    os.fsync(fd)
                    written_st = os.fstat(fd)
                    if not stat.S_ISREG(written_st.st_mode) or written_st.st_nlink != 1:
                        raise CustodyError("created output must remain one regular-file generation")
                    if written_st.st_size != len(data):
                        raise CustodyError("created output byte count does not match")
                    os.lseek(fd, 0, os.SEEK_SET)
                    readback_chunks: list[bytes] = []
                    remaining = len(data) + 1
                    while remaining > 0:
                        chunk = os.read(fd, min(64 * 1024, remaining))
                        if not chunk:
                            break
                        readback_chunks.append(chunk)
                        remaining -= len(chunk)
                    readback = b"".join(readback_chunks)
                    if readback != data:
                        raise CustodyError("created output failed exact-byte readback")
                    final_st = os.fstat(fd)
                    if _metadata_tuple(written_st) != _metadata_tuple(final_st):
                        raise CustodyError("created output changed during exact-byte readback")
                    visible = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                    if stat.S_ISLNK(visible.st_mode) or (visible.st_dev, visible.st_ino) != (final_st.st_dev, final_st.st_ino):
                        raise CustodyError("visible output pathname does not name the created generation")
                finally:
                    os.close(fd)

            synced: set[tuple[int, int]] = set()
            for parent_fd, _name, _data, _key in entries:
                parent_st = os.fstat(parent_fd)
                parent_key = (int(parent_st.st_dev), int(parent_st.st_ino))
                if parent_key not in synced:
                    os.fsync(parent_fd)
                    synced.add(parent_key)
        except BaseException as exc:
            rollback_errors = _rollback_created_outputs(created)
            if rollback_errors:
                raise CustodyError("output-set failure left an incomplete rollback: " + "; ".join(rollback_errors)) from exc
            raise
    finally:
        for parent_fd in reversed(parent_fds):
            os.close(parent_fd)


def write_exclusive_regular_file(path: str | os.PathLike[str], data: bytes, *, limit: int = MAX_OUTPUT_BYTES) -> None:
    write_exclusive_regular_files({path: data}, limit=limit, total_limit=limit)
