from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping

SCHEMA_CORPUS = "nih.spark.dbgap.corpus/v1"
SCHEMA_RESOURCES = "nih.spark.dbgap.resources/v1"
SCHEMA_T1_QUERIES = "nih.spark.dbgap.track1-input/v1"
SCHEMA_T1_OUTPUT = "nih.spark.dbgap.track1-output/v1"
SCHEMA_T2_QUERIES = "nih.spark.dbgap.track2-input/v1"
SCHEMA_T2_OUTPUT = "nih.spark.dbgap.track2-output/v1"
SCHEMA_RUN_RECEIPT = "nih.spark.dbgap.run-receipt/v1"
ONT_NONE = "ONT_NONE"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ALLOWED_RESOURCE_KINDS = {"ONTOLOGY", "VOCABULARY", "PUBLIC_CORPUS", "SOFTWARE"}
_MAX_INPUT_BYTES = 16 * 1024 * 1024
_SUPPORTS_OPEN_DIRFD = os.open in os.supports_dir_fd
_SUPPORTS_STAT_DIRFD = os.stat in os.supports_dir_fd


class ContractError(ValueError):
    pass


def _reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json_strict_bytes(data: bytes) -> Any:
    if len(data) > _MAX_INPUT_BYTES:
        raise ContractError("input exceeds 16 MiB")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("input must be UTF-8") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_pairs,
            parse_constant=lambda x: (_ for _ in ()).throw(ContractError(f"non-finite JSON number: {x}")),
        )
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON: {exc.msg}") from exc
    return value


def _same_inode(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _file_generation(value: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
        value.st_nlink,
    )


def _directory_open_flags() -> int:
    if (
        not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_DIRECTORY")
        or not _SUPPORTS_OPEN_DIRFD
        or not _SUPPORTS_STAT_DIRFD
    ):
        raise ContractError("platform lacks descriptor-relative no-follow filesystem support")
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _open_parent_nofollow(path: str | Path) -> tuple[int, os.stat_result, str, str]:
    """Open every lexical ancestor without following symlinks and retain the parent fd."""
    raw = os.fspath(path)
    if not raw:
        raise ContractError("path must not be empty")
    absolute = os.path.abspath(raw)
    parent_path, name = os.path.split(absolute)
    if not name or name in (".", ".."):
        raise ContractError("path must name a file")
    flags = _directory_open_flags()
    try:
        fd = os.open(os.path.sep, flags)
    except OSError as exc:
        raise ContractError(f"cannot open filesystem root safely: {exc}") from exc
    try:
        relative_parent = os.path.relpath(parent_path, os.path.sep)
        if relative_parent != ".":
            for component in relative_parent.split(os.path.sep):
                if component in ("", ".", ".."):
                    raise ContractError("path contains invalid ancestor component")
                try:
                    child_fd = os.open(component, flags, dir_fd=fd)
                except OSError as exc:
                    raise ContractError(f"cannot open path ancestor safely: {exc}") from exc
                os.close(fd)
                fd = child_fd
        parent_state = os.fstat(fd)
        if not stat.S_ISDIR(parent_state.st_mode):
            raise ContractError("retained parent is not a directory")
        return fd, parent_state, parent_path, name
    except Exception:
        os.close(fd)
        raise


def _reopen_same_parent(parent_path: str, expected: os.stat_result) -> int:
    probe = os.path.join(parent_path, ".__spark_parent_probe__")
    fd, current, _, _ = _open_parent_nofollow(probe)
    if not _same_inode(current, expected):
        os.close(fd)
        raise ContractError("parent directory generation changed")
    return fd


def _read_bounded_fd(fd: int, *, limit: int = _MAX_INPUT_BYTES) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, min(1024 * 1024, limit + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            raise ContractError("input exceeds 16 MiB")
    return b"".join(chunks)


def load_json_strict(path: str | Path) -> Any:
    """Read exact JSON bytes from a descriptor-bound, generation-stable lexical path."""
    parent_fd, parent_state, parent_path, name = _open_parent_nofollow(path)
    fd: int | None = None
    try:
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        try:
            fd = os.open(name, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise ContractError(f"cannot open input safely: {exc}") from exc
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ContractError("input must remain an ordinary file")
        if before.st_size > _MAX_INPUT_BYTES:
            raise ContractError("input exceeds 16 MiB")

        first = _read_bounded_fd(fd)
        middle = os.fstat(fd)
        if _file_generation(before) != _file_generation(middle) or len(first) != middle.st_size:
            raise ContractError("input generation changed during read")

        second = _read_bounded_fd(fd)
        after = os.fstat(fd)
        if _file_generation(middle) != _file_generation(after) or second != first:
            raise ContractError("input generation changed during verification")

        check_fd = _reopen_same_parent(parent_path, parent_state)
        try:
            try:
                visible = os.stat(name, dir_fd=check_fd, follow_symlinks=False)
            except OSError as exc:
                raise ContractError(f"cannot re-stat input safely: {exc}") from exc
            if _file_generation(visible) != _file_generation(after):
                raise ContractError("input path generation changed after read")
        finally:
            os.close(check_fd)
        return load_json_strict_bytes(first)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent_fd)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def semantic_sha256(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def _exact_keys(obj: Mapping[str, Any], keys: set[str], where: str) -> None:
    actual = set(obj)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys)
        raise ContractError(f"{where} keys mismatch: missing={missing} extra={extra}")


def _string(value: Any, where: str, *, max_len: int = 4096, allow_empty: bool = False) -> str:
    if type(value) is not str:
        raise ContractError(f"{where} must be a string")
    if not allow_empty and not value:
        raise ContractError(f"{where} must be non-empty")
    if len(value) > max_len:
        raise ContractError(f"{where} too long")
    if _CONTROL_RE.search(value):
        raise ContractError(f"{where} contains control characters")
    return value


def _identifier(value: Any, where: str) -> str:
    text = _string(value, where, max_len=128)
    if not _ID_RE.fullmatch(text):
        raise ContractError(f"{where} is not a safe identifier")
    return text


def _sha(value: Any, where: str) -> str:
    text = _string(value, where, max_len=64)
    if not _SHA256_RE.fullmatch(text):
        raise ContractError(f"{where} must be lowercase SHA-256")
    return text


def _int(value: Any, where: str, *, minimum: int = 0, maximum: int = 2**53 - 1) -> int:
    if type(value) is not int:
        raise ContractError(f"{where} must be an integer (bool/float rejected)")
    if value < minimum or value > maximum:
        raise ContractError(f"{where} outside range")
    return value


def _array(value: Any, where: str, *, max_len: int = 100_000) -> list[Any]:
    if type(value) is not list:
        raise ContractError(f"{where} must be an array")
    if len(value) > max_len:
        raise ContractError(f"{where} too many items")
    return value


def _object(value: Any, where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ContractError(f"{where} must be an object")
    return value


def normalized_tokens(text: str) -> tuple[str, ...]:
    return tuple(token.lower() for token in _TOKEN_RE.findall(text) if token)


def text_digest(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))
