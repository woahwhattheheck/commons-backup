"""Pinned host trust root for organization pressure attestations.

The supported acquire path has no caller-selectable verifier.  The public key is read
from one fixed host path whose directory and file must be root-owned, non-writable by
group/other, and stable across a no-follow retained-descriptor read.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

from .strict import parse_json_strict

TRUST_ROOT_SCHEMA = "commons.organization-pressure-trust-root/v1"
TRUST_ROOT_PATH = Path("/etc/tokenjunkielabs/organization-pressure-rsa-public.json")
MAX_TRUST_ROOT_BYTES = 8192


def _secure_mode(st, label: str) -> None:
    if not hasattr(st, "st_uid"):
        raise RuntimeError("%s ownership cannot be verified on this platform" % label)
    if st.st_uid != 0:
        raise ValueError("%s must be root-owned" % label)
    if stat.S_IMODE(st.st_mode) & 0o022:
        raise ValueError("%s must not be group/world writable" % label)


def _read_trust_root_bytes() -> bytes:
    path = TRUST_ROOT_PATH
    if not path.is_absolute() or path.name in ("", ".", ".."):
        raise RuntimeError("pressure trust-root path is invalid")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise RuntimeError("pressure trust root requires O_NOFOLLOW and O_DIRECTORY")

    dir_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    dir_fd = os.open(str(path.parent), dir_flags)
    try:
        directory = os.fstat(dir_fd)
        if not stat.S_ISDIR(directory.st_mode):
            raise ValueError("pressure trust-root parent must be a directory")
        _secure_mode(directory, "pressure trust-root parent")

        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("pressure trust root must be a regular file")
            if before.st_nlink != 1:
                raise ValueError("pressure trust root must have exactly one hard link")
            _secure_mode(before, "pressure trust root")
            if before.st_size > MAX_TRUST_ROOT_BYTES:
                raise ValueError("pressure trust root is oversized")

            chunks = []
            remaining = MAX_TRUST_ROOT_BYTES + 1
            while remaining > 0:
                block = os.read(fd, min(65536, remaining))
                if not block:
                    break
                chunks.append(block)
                remaining -= len(block)
            raw = b"".join(chunks)
            if len(raw) > MAX_TRUST_ROOT_BYTES:
                raise ValueError("pressure trust root is oversized")

            after = os.fstat(fd)
            before_id = (
                before.st_dev, before.st_ino, before.st_mode, before.st_uid,
                before.st_nlink, before.st_size, before.st_mtime_ns, before.st_ctime_ns,
            )
            after_id = (
                after.st_dev, after.st_ino, after.st_mode, after.st_uid,
                after.st_nlink, after.st_size, after.st_mtime_ns, after.st_ctime_ns,
            )
            if before_id != after_id or len(raw) != after.st_size:
                raise ValueError("pressure trust root changed during read")
        finally:
            os.close(fd)

        visible = os.stat(path.name, dir_fd=dir_fd, follow_symlinks=False)
        if not stat.S_ISREG(visible.st_mode):
            raise ValueError("pressure trust root visible path is not regular")
        _secure_mode(visible, "pressure trust root visible path")
        if (
            visible.st_dev, visible.st_ino, visible.st_size, visible.st_mtime_ns
        ) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ):
            raise ValueError("pressure trust-root pathname generation changed")
        return raw
    finally:
        os.close(dir_fd)


def parse_pressure_trust_root(value):
    if type(value) is not dict:
        raise ValueError("pressure trust root must be an object")
    expected = {"schema", "algorithm", "keyId", "modulusHex", "exponent"}
    if set(value) != expected:
        raise ValueError("pressure trust-root keys mismatch")
    if value["schema"] != TRUST_ROOT_SCHEMA:
        raise ValueError("unsupported pressure trust-root schema")
    if value["algorithm"] != "RS256-PKCS1-v1_5":
        raise ValueError("unsupported pressure trust-root algorithm")
    if type(value["exponent"]) is not int:
        raise ValueError("pressure trust-root exponent must be integer")

    # Lazy import avoids a module cycle: core calls this loader only after core import.
    from .core import RsaPublicKey
    return RsaPublicKey.from_hex(
        key_id=value["keyId"],
        modulus_hex=value["modulusHex"],
        exponent=value["exponent"],
    )


def load_pressure_verifier():
    try:
        text = _read_trust_root_bytes().decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise ValueError("pressure trust root must be UTF-8") from exc
    return parse_pressure_trust_root(parse_json_strict(text))
