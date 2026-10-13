"""Fixed-host trust components used by the isolated current worker.

Every production acquisition derives the POSIX effective-account root inside the
fresh process, retains one validated authority-root directory descriptor through
both key and floor consumption, and checks owner/mode/link-count/stable-generation
properties for every leaf.  The complete key+floor pair is fenced across each
current compile or verify operation.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import re
import stat
from typing import Any

from .core import PortfolioError, load_json_bytes
from .current import (
    AuthorizedPortfolio,
    AuthorityKey,
    MAX_KEY_BYTES,
    _canonical,
    _open_dir_chain,
    _read_fd_twice,
    parse_authority_key,
)
from .floor import (
    AuthorityFloor,
    MAX_FLOOR_BYTES,
    parse_authority_floor,
)

HOST_SEAL_SCHEMA = "pursuit-portfolio-allocation/host-seal/v2"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_HOST_SEAL_KEYS = frozenset(
    {
        "authority_floor_generation",
        "authority_floor_sha256",
        "authority_sha256",
        "current_receipt_sha256",
        "evaluated_at",
        "hmac_sha256",
        "input_sha256",
        "key_id",
        "markdown_sha256",
        "receipt_file_sha256",
        "result_sha256",
        "schema",
    }
)


@dataclass(frozen=True)
class HostAuthorizedPortfolio:
    authorized: AuthorizedPortfolio
    host_seal: dict[str, Any]
    host_seal_bytes: bytes


@dataclass(frozen=True)
class HostAuthoritySnapshot:
    key: AuthorityKey
    key_raw: bytes
    floor: AuthorityFloor


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def effective_account_home() -> Path:
    if os.name != "posix":
        raise PortfolioError(
            "host trust root requires POSIX effective-account authority"
        )
    try:
        import pwd
        entry = pwd.getpwuid(os.geteuid())
    except (ImportError, KeyError) as exc:
        raise PortfolioError(
            "host trust root: effective account database unavailable"
        ) from exc
    home = Path(entry.pw_dir)
    if not home.is_absolute():
        raise PortfolioError(
            "host trust root: effective account home must be absolute"
        )
    try:
        info = os.lstat(home)
    except OSError as exc:
        raise PortfolioError(
            "host trust root: effective account home unavailable"
        ) from exc
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise PortfolioError(
            "host trust root: effective account home must be a real directory"
        )
    if int(info.st_uid) != int(os.geteuid()):
        raise PortfolioError(
            "host trust root: effective account home ownership mismatch"
        )
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise PortfolioError(
            "host trust root: effective account home must not be group/world writable"
        )
    return home


def fixed_host_root() -> Path:
    return effective_account_home() / ".config" / "commons" / "pursuit-portfolio"


def _open_validated_host_parent(path: Path, where: str) -> int:
    try:
        fd = _open_dir_chain(path.parent)
    except PortfolioError:
        raise
    except OSError as exc:
        raise PortfolioError(
            f"{where}: retained host directory unavailable"
        ) from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode):
            raise PortfolioError(
                f"{where}: retained host parent must be a directory"
            )
        if os.name != "posix":
            raise PortfolioError(
                f"{where}: POSIX retained host authority required"
            )
        if int(info.st_uid) != int(os.geteuid()):
            raise PortfolioError(
                f"{where}: retained host directory ownership mismatch"
            )
        if stat.S_IMODE(info.st_mode) & 0o022:
            raise PortfolioError(
                f"{where}: retained host directory must not be group/world writable"
            )
    except Exception:
        os.close(fd)
        raise
    return fd


def _validate_private_leaf(info: os.stat_result, where: str) -> None:
    if not stat.S_ISREG(info.st_mode):
        raise PortfolioError(f"{where}: regular file required")
    if os.name != "posix":
        raise PortfolioError(f"{where}: POSIX retained host authority required")
    if int(info.st_uid) != int(os.geteuid()):
        raise PortfolioError(f"{where}: effective-UID ownership required")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise PortfolioError(f"{where}: owner-only permissions required")
    if int(info.st_nlink) != 1:
        raise PortfolioError(f"{where}: single-link retained file required")


def _read_validated_host_leaf(
    path: Path, dir_fd: int, maximum: int, where: str
) -> bytes:
    name = path.name
    if (
        not name
        or os.sep in name
        or (os.altsep and os.altsep in name)
        or name in (".", "..")
    ):
        raise PortfolioError(f"{where}: invalid final path component")
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
    except OSError as exc:
        raise PortfolioError(f"{where}: retained host file unavailable") from exc
    try:
        before = os.fstat(fd)
        _validate_private_leaf(before, where)
        raw = _read_fd_twice(fd, maximum, where)
        after = os.fstat(fd)
        _validate_private_leaf(after, where)
        if (int(before.st_dev), int(before.st_ino)) != (
            int(after.st_dev), int(after.st_ino)
        ):
            raise PortfolioError(
                f"{where}: retained file generation changed while reading"
            )
        return raw
    finally:
        os.close(fd)


def read_host_leaf(path: str | Path, maximum: int, where: str) -> bytes:
    candidate = Path(path)
    parent_fd = _open_validated_host_parent(candidate, where)
    try:
        return _read_validated_host_leaf(
            candidate, parent_fd, maximum, where
        )
    finally:
        os.close(parent_fd)


def load_host_key_from(path: str | Path) -> AuthorityKey:
    return parse_authority_key(
        read_host_leaf(path, MAX_KEY_BYTES, "authority key")
    )


def load_host_floor_from(
    path: str | Path, key: AuthorityKey, trusted_now: str
) -> AuthorityFloor:
    return parse_authority_floor(
        read_host_leaf(path, MAX_FLOOR_BYTES, "authority floor"),
        key,
        trusted_now,
    )


def load_host_authority_from(
    root: str | Path, trusted_now: str
) -> HostAuthoritySnapshot:
    """Read key and floor through one retained authority-root generation."""
    authority_root = Path(root)
    key_path = authority_root / "authority-key.json"
    floor_path = authority_root / "authority-floor.json"
    root_fd = _open_validated_host_parent(key_path, "host authority root")
    try:
        key_raw = _read_validated_host_leaf(
            key_path, root_fd, MAX_KEY_BYTES, "authority key"
        )
        key = parse_authority_key(key_raw)
        floor_raw = _read_validated_host_leaf(
            floor_path, root_fd, MAX_FLOOR_BYTES, "authority floor"
        )
        floor = parse_authority_floor(floor_raw, key, trusted_now)
        return HostAuthoritySnapshot(key=key, key_raw=key_raw, floor=floor)
    finally:
        os.close(root_fd)


def load_host_authority(trusted_now: str) -> HostAuthoritySnapshot:
    return load_host_authority_from(fixed_host_root(), trusted_now)


def load_host_key() -> AuthorityKey:
    return load_host_key_from(fixed_host_root() / "authority-key.json")


def load_host_floor(key: AuthorityKey, trusted_now: str) -> AuthorityFloor:
    return load_host_floor_from(
        fixed_host_root() / "authority-floor.json", key, trusted_now
    )


def seal_base(
    value: AuthorizedPortfolio, key: AuthorityKey, floor: AuthorityFloor
) -> dict[str, Any]:
    return {
        "authority_floor_generation": floor.generation,
        "authority_floor_sha256": _digest(floor.raw),
        "authority_sha256": _digest(value.authority_bytes),
        "current_receipt_sha256": _digest(value.current_receipt_bytes),
        "evaluated_at": value.compiled.result["evaluated_at"],
        "input_sha256": value.compiled.result["input_sha256"],
        "key_id": key.key_id,
        "markdown_sha256": _digest(value.compiled.markdown_bytes),
        "receipt_file_sha256": _digest(value.compiled.receipt_bytes),
        "result_sha256": _digest(value.compiled.result_bytes),
        "schema": HOST_SEAL_SCHEMA,
    }


def seal(
    value: AuthorizedPortfolio, key: AuthorityKey, floor: AuthorityFloor
) -> dict[str, Any]:
    base = seal_base(value, key, floor)
    return {
        **base,
        "hmac_sha256": hmac.new(
            key.key, _canonical(base), hashlib.sha256
        ).hexdigest(),
    }


def parse_host_seal(raw: bytes) -> dict[str, Any]:
    value = load_json_bytes(raw, "host seal")
    if type(value) is not dict or set(value) != set(_HOST_SEAL_KEYS):
        raise PortfolioError("host seal: exact key set required")
    if raw != _canonical(value):
        raise PortfolioError("host seal: noncanonical persisted bytes")
    if value["schema"] != HOST_SEAL_SCHEMA:
        raise PortfolioError("host seal: unsupported schema")
    if type(value["key_id"]) is not str or not value["key_id"]:
        raise PortfolioError("host seal: key_id required")
    if type(value["evaluated_at"]) is not str or not value["evaluated_at"]:
        raise PortfolioError("host seal: evaluated_at required")
    generation = value["authority_floor_generation"]
    if (
        type(generation) is not int
        or type(generation) is bool
        or not 1 <= generation <= 10**12
    ):
        raise PortfolioError("host seal: invalid authority_floor_generation")
    for name in (
        "authority_floor_sha256",
        "authority_sha256",
        "current_receipt_sha256",
        "hmac_sha256",
        "input_sha256",
        "markdown_sha256",
        "receipt_file_sha256",
        "result_sha256",
    ):
        if type(value[name]) is not str or _SHA.fullmatch(value[name]) is None:
            raise PortfolioError(f"host seal: invalid {name}")
    return value


def same_floor(before: AuthorityFloor, after: AuthorityFloor) -> None:
    if not hmac.compare_digest(before.raw, after.raw):
        raise PortfolioError(
            "authority floor: generation changed during current-use operation"
        )


def same_host_authority(
    before: HostAuthoritySnapshot, after: HostAuthoritySnapshot
) -> None:
    if not hmac.compare_digest(before.key_raw, after.key_raw):
        raise PortfolioError(
            "authority key: generation changed during current-use operation"
        )
    same_floor(before.floor, after.floor)


# Compatibility aliases used by focused tests and the worker.
_digest = _digest
_effective_account_home = effective_account_home
_open_validated_host_parent = _open_validated_host_parent
_read_validated_host_leaf = _read_validated_host_leaf
_load_host_key = load_host_key
_load_host_floor = load_host_floor
_load_host_key_from = load_host_key_from
_load_host_floor_from = load_host_floor_from
_load_host_authority = load_host_authority
_load_host_authority_from = load_host_authority_from
_seal_base = seal_base
_seal = seal
_parse_host_seal = parse_host_seal
_same_floor = same_floor
_same_host_authority = same_host_authority
