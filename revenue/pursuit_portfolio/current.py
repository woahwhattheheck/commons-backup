"""Deterministic signed-current adapter over the v2 portfolio core.

Production current authority does not live in this module.  The explicit-time
helpers below are replay/test machinery consumed by the isolated fixed-host
worker.  Public current compile/verify entrypoints fail closed so an importing
caller cannot supply a key, path selector, clock, or Python helper and obtain a
production host seal.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping

from .core import (
    MAX_FILE_BYTES,
    CompiledPortfolio,
    PortfolioError,
    compile_portfolio,
    load_json_bytes,
    normalize_input,
    normalize_upstream_authority,
    verify_compiled,
)

KEY_SCHEMA = "pursuit-portfolio-allocation/authority-key/v1"
CURRENT_RECEIPT_SCHEMA = "pursuit-portfolio-allocation/current-receipt/v2"
MAX_AUTHORITY_BYTES = 512 * 1024
MAX_KEY_BYTES = 4096
_SHA = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$")
_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_KEY_KEYS = frozenset({"schema", "key_id", "key_hex"})
_CURRENT_RECEIPT_KEYS = frozenset(
    {
        "authority_key_id",
        "authority_sha256",
        "core_receipt_sha256",
        "evaluated_at",
        "input_sha256",
        "receipt_sha256",
        "schema",
    }
)


@dataclass(frozen=True)
class AuthorityKey:
    key_id: str
    key: bytes


@dataclass(frozen=True)
class AuthorizedPortfolio:
    compiled: CompiledPortfolio
    authority: dict[str, Any]
    authority_bytes: bytes
    current_receipt: dict[str, Any]
    current_receipt_bytes: bytes


def _canonical(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PortfolioError("current-use payload is not canonical JSON") from exc


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _dt(value: str, where: str) -> datetime:
    if type(value) is not str or _TS.fullmatch(value) is None:
        raise PortfolioError(f"{where}: canonical UTC-second timestamp required")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise PortfolioError(f"{where}: invalid timestamp") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise PortfolioError(f"{where}: noncanonical timestamp")
    return parsed


def _exact(value: Any, keys: frozenset[str], where: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != set(keys):
        raise PortfolioError(f"{where}: exact key set required")
    return value


def _token(value: Any, where: str) -> str:
    if type(value) is not str or _TOKEN.fullmatch(value) is None:
        raise PortfolioError(f"{where}: bounded token required")
    return value


def _sha(value: Any, where: str) -> str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise PortfolioError(f"{where}: lowercase SHA-256 required")
    return value


def _stable_metadata(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_size),
        int(getattr(info, "st_mtime_ns", int(info.st_mtime * 1_000_000_000))),
        int(getattr(info, "st_ctime_ns", int(info.st_ctime * 1_000_000_000))),
    )


def _secure_dir_capable() -> bool:
    supports = getattr(os, "supports_dir_fd", set())
    return (
        os.open in supports
        and hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_NOFOLLOW")
    )


def _open_dir_chain(path: str | Path) -> int:
    """Open an absolute directory while rejecting every symlink component."""
    if not _secure_dir_capable():
        raise PortfolioError("secure directory-descriptor operations unsupported")
    absolute = os.path.abspath(os.fspath(path))
    drive, tail = os.path.splitdrive(absolute)
    if drive:
        raise PortfolioError("secure directory walk does not support drive paths")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(os.sep, flags)
    try:
        for part in (item for item in tail.split(os.sep) if item):
            if part in (".", ".."):
                raise PortfolioError("directory traversal component forbidden")
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except Exception:
        os.close(fd)
        raise


def _read_fd_twice(fd: int, maximum: int, where: str) -> bytes:
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode):
        raise PortfolioError(f"{where}: regular file required")
    if before.st_size < 0 or before.st_size > maximum:
        raise PortfolioError(f"{where}: file exceeds byte bound")

    def read_once() -> bytes:
        os.lseek(fd, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > maximum:
            raise PortfolioError(f"{where}: file exceeds byte bound")
        return raw

    first = read_once()
    middle = os.fstat(fd)
    second = read_once()
    after = os.fstat(fd)
    if (
        first != second
        or _stable_metadata(before) != _stable_metadata(middle)
        or _stable_metadata(middle) != _stable_metadata(after)
        or len(first) != before.st_size
    ):
        raise PortfolioError(f"{where}: file generation changed while reading")
    return first


def _read_relative(
    dir_fd: int,
    name: str,
    maximum: int,
    where: str,
    *,
    private: bool = False,
) -> bytes:
    if os.sep in name or (os.altsep and os.altsep in name) or name in (".", ".."):
        raise PortfolioError(f"{where}: invalid final path component")
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
    try:
        info = os.fstat(fd)
        if private and os.name == "posix" and stat.S_IMODE(info.st_mode) & 0o077:
            raise PortfolioError(f"{where}: owner-only permissions required")
        return _read_fd_twice(fd, maximum, where)
    finally:
        os.close(fd)


def read_regular_bytes(
    path: str | Path, maximum: int, where: str, *, private: bool = False
) -> bytes:
    absolute = os.path.abspath(os.fspath(path))
    parent, name = os.path.split(absolute)
    if not name:
        raise PortfolioError(f"{where}: file path required")
    parent_fd = _open_dir_chain(parent or os.sep)
    try:
        return _read_relative(parent_fd, name, maximum, where, private=private)
    finally:
        os.close(parent_fd)


def load_current_input(path: str | Path) -> dict[str, Any]:
    return load_json_bytes(read_regular_bytes(path, MAX_FILE_BYTES, "input"), "input")


def parse_authority_key(raw: bytes) -> AuthorityKey:
    value = _exact(load_json_bytes(raw, "authority key"), _KEY_KEYS, "authority key")
    if raw != _canonical(value):
        raise PortfolioError("authority key: persisted bytes must be canonical JSON")
    if value["schema"] != KEY_SCHEMA:
        raise PortfolioError("authority key: unsupported schema")
    key_id = _token(value["key_id"], "authority key.key_id")
    key_hex = _sha(value["key_hex"], "authority key.key_hex")
    key = bytes.fromhex(key_hex)
    if len(key) != 32:
        raise PortfolioError("authority key: exactly 32 bytes required")
    return AuthorityKey(key_id=key_id, key=key)


def load_authority_key(path: str | Path) -> AuthorityKey:
    return parse_authority_key(
        read_regular_bytes(path, MAX_KEY_BYTES, "authority key", private=True)
    )


def canonical_authority(value: Mapping[str, Any]) -> tuple[dict[str, Any], bytes]:
    normalized = normalize_upstream_authority(dict(value))
    return normalized, _canonical(normalized)


def _current_receipt(
    compiled: CompiledPortfolio, authority_bytes: bytes, key_id: str
) -> dict[str, Any]:
    base = {
        "authority_key_id": key_id,
        "authority_sha256": _digest(authority_bytes),
        "core_receipt_sha256": compiled.receipt["receipt_sha256"],
        "evaluated_at": compiled.result["evaluated_at"],
        "input_sha256": compiled.result["input_sha256"],
        "schema": CURRENT_RECEIPT_SCHEMA,
    }
    return {**base, "receipt_sha256": _digest(_canonical(base))}


def compile_authorized_at(
    source: Mapping[str, Any],
    authority: Mapping[str, Any],
    key: AuthorityKey,
    evaluated_at: str,
) -> AuthorizedPortfolio:
    """Deterministically compile one explicitly timed historical generation."""
    _dt(evaluated_at, "evaluated_at")
    normalized_source = normalize_input(dict(source))
    normalized_authority, authority_bytes = canonical_authority(authority)
    authority_sha = _digest(authority_bytes)
    compiled = compile_portfolio(
        normalized_source,
        upstream_authority=normalized_authority,
        trusted_upstream_authority_sha256=authority_sha,
        evaluated_at=evaluated_at,
    )
    receipt = _current_receipt(compiled, authority_bytes, key.key_id)
    return AuthorizedPortfolio(
        compiled=compiled,
        authority=normalized_authority,
        authority_bytes=authority_bytes,
        current_receipt=receipt,
        current_receipt_bytes=_canonical(receipt),
    )


def _parse_current_receipt(raw: bytes) -> dict[str, Any]:
    value = _exact(
        load_json_bytes(raw, "current receipt"),
        _CURRENT_RECEIPT_KEYS,
        "current receipt",
    )
    if raw != _canonical(value):
        raise PortfolioError("current receipt: noncanonical persisted bytes")
    if value["schema"] != CURRENT_RECEIPT_SCHEMA:
        raise PortfolioError("current receipt: unsupported schema")
    _token(value["authority_key_id"], "current receipt.authority_key_id")
    for name in (
        "authority_sha256",
        "core_receipt_sha256",
        "input_sha256",
        "receipt_sha256",
    ):
        _sha(value[name], f"current receipt.{name}")
    _dt(value["evaluated_at"], "current receipt.evaluated_at")
    base = dict(value)
    claimed = base.pop("receipt_sha256")
    if not hmac.compare_digest(claimed, _digest(_canonical(base))):
        raise PortfolioError("current receipt: self commitment mismatch")
    return value


def _decision_fingerprint(result: Mapping[str, Any]) -> bytes:
    rows = [
        {
            "allocation_state": row["allocation_state"],
            "individual_fit_counterfactual": row["individual_fit_counterfactual"],
            "opportunity_id": row["opportunity_id"],
            "reasons": row["reasons"],
            "upstream_state": row["upstream_state"],
        }
        for row in result["opportunities"]
    ]
    return _canonical(
        {
            "capacity": result["capacity"],
            "opportunities": rows,
            "policy_sha256": result["policy_sha256"],
            "selected_opportunity_ids": result["selected_opportunity_ids"],
            "selected_priority_units": result["selected_priority_units"],
            "upstream_authority_sha256": result["upstream_authority_sha256"],
        }
    )


def verify_authorized_at(
    result_raw: bytes,
    markdown_raw: bytes,
    receipt_raw: bytes,
    authority_raw: bytes,
    current_receipt_raw: bytes,
    key: AuthorityKey,
    trusted_now: str,
) -> dict[str, Any]:
    """Verify history, then recompute current semantics at explicit trusted UTC."""
    _dt(trusted_now, "trusted_now")
    authority_value = load_json_bytes(authority_raw, "upstream authority")
    normalized_authority, canonical_authority_bytes = canonical_authority(authority_value)
    if authority_raw != canonical_authority_bytes:
        raise PortfolioError("upstream authority: noncanonical persisted bytes")
    authority_sha = _digest(authority_raw)
    history = verify_compiled(
        result_raw,
        markdown_raw,
        receipt_raw,
        trusted_upstream_authority_sha256=authority_sha,
    )
    result = load_json_bytes(result_raw, "result")
    if result.get("normalized_upstream_authority") != normalized_authority:
        raise PortfolioError("result: embedded authority generation mismatch")
    current_receipt = _parse_current_receipt(current_receipt_raw)
    if current_receipt["authority_key_id"] != key.key_id:
        raise PortfolioError("current receipt: authority key mismatch")
    if current_receipt["authority_sha256"] != authority_sha:
        raise PortfolioError("current receipt: authority generation mismatch")
    if current_receipt["core_receipt_sha256"] != history["receipt_sha256"]:
        raise PortfolioError("current receipt: core receipt mismatch")
    if current_receipt["input_sha256"] != history["input_sha256"]:
        raise PortfolioError("current receipt: input mismatch")
    if current_receipt["evaluated_at"] != result.get("evaluated_at"):
        raise PortfolioError("current receipt: evaluation-time mismatch")
    source = result.get("normalized_input")
    if type(source) is not dict:
        raise PortfolioError("result: embedded normalized input required")
    current = compile_authorized_at(
        source, normalized_authority, key, trusted_now
    )
    if _decision_fingerprint(result) != _decision_fingerprint(current.compiled.result):
        raise PortfolioError("current verification: allocation decision is stale")
    return {
        "authority_sha256": authority_sha,
        "historical_integrity_verified": True,
        "original_evaluated_at": result["evaluated_at"],
        "selected_opportunity_ids": result["selected_opportunity_ids"],
        "selected_priority_units": result["selected_priority_units"],
        "verified_at": trusted_now,
        "verified_current": True,
    }


def compile_authorized_current(*args: Any, **kwargs: Any) -> Any:
    del args, kwargs
    raise PortfolioError(
        "production current compile requires the fixed-host fresh-process boundary"
    )


def verify_authorized_current(*args: Any, **kwargs: Any) -> Any:
    del args, kwargs
    raise PortfolioError(
        "production current verify requires the fixed-host fresh-process boundary"
    )


# Compatibility aliases are explicitly timed replay helpers, never current authority.
_compile_authorized_at = compile_authorized_at
_verify_authorized_at = verify_authorized_at
