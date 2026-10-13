from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "reconciliation-proof/v1"
RECEIPT_SCHEMA = "reconciliation-proof-receipt/v1"
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_RECORDS_PER_SIDE = 25_000
MAX_FIELDS_PER_RECORD = 256
MAX_TEXT_BYTES = 16_384
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FIELD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_PROFILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")

class ProofError(ValueError):
    """Input cannot be represented safely under the v1 proof contract."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ProofError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ProofError(f"non-finite JSON number: {token}")
            ),
        )
    except ProofError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ProofError(f"invalid JSON: {exc}") from exc


def read_json_file(path: str | os.PathLike[str], *, max_bytes: int = MAX_FILE_BYTES) -> Any:
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ProofError("max_bytes must be a positive integer")
    p = Path(path)
    try:
        meta = p.lstat()
    except OSError as exc:
        raise ProofError(f"cannot stat {p}: {exc}") from exc
    if stat.S_ISLNK(meta.st_mode):
        raise ProofError(f"symlink input refused: {p}")
    if not stat.S_ISREG(meta.st_mode):
        raise ProofError(f"ordinary file required: {p}")
    if meta.st_size > max_bytes:
        raise ProofError(f"input exceeds {max_bytes} bytes: {p}")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(p, flags)
        try:
            opened = os.fstat(fd)
            if not stat.S_ISREG(opened.st_mode):
                raise ProofError(f"ordinary file required after open: {p}")
            # Bind the descriptor to the path object inspected before open. This
            # also closes the symlink/replacement race on platforms without
            # O_NOFOLLOW when stable inode/device identities are available.
            if meta.st_ino and opened.st_ino and (meta.st_dev, meta.st_ino) != (opened.st_dev, opened.st_ino):
                raise ProofError(f"input changed between stat and open: {p}")
            if opened.st_size > max_bytes:
                raise ProofError(f"input exceeds {max_bytes} bytes after open: {p}")
            chunks: list[bytes] = []
            remaining = max_bytes + 1
            while remaining:
                chunk = os.read(fd, min(64 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
        finally:
            os.close(fd)
    except ProofError:
        raise
    except OSError as exc:
        raise ProofError(f"cannot read {p}: {exc}") from exc
    if len(raw) > max_bytes:
        raise ProofError(f"input exceeds {max_bytes} bytes while reading: {p}")
    try:
        return loads_strict(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ProofError(f"input is not UTF-8: {p}") from exc


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ProofError(f"value is not canonical JSON: {exc}") from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _parse_utc_z(value: Any, *, field: str) -> datetime:
    if type(value) is not str or not value or len(value) > 40:
        raise ProofError(f"{field} must be a canonical UTC timestamp string")
    if not value.endswith("Z"):
        raise ProofError(f"{field} must end in Z")
    try:
        dt = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ProofError(f"{field} is not an ISO-8601 timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(dt):
        raise ProofError(f"{field} must be UTC")
    if dt.microsecond:
        raise ProofError(f"{field} must have whole-second precision")
    canonical = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    if value != canonical:
        raise ProofError(f"{field} must use canonical YYYY-MM-DDTHH:MM:SSZ form")
    return dt


def _text(value: Any, *, field: str, max_bytes: int = MAX_TEXT_BYTES) -> str:
    if type(value) is not str or not value:
        raise ProofError(f"{field} must be a non-empty string")
    if "\x00" in value or any(ord(ch) < 0x20 and ch not in "\t\n\r" for ch in value):
        raise ProofError(f"{field} contains control characters")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ProofError(f"{field} contains invalid Unicode") from exc
    if len(encoded) > max_bytes:
        raise ProofError(f"{field} exceeds {max_bytes} UTF-8 bytes")
    return value


def _json_value(value: Any, *, field: str, depth: int = 0) -> Any:
    if depth > 8:
        raise ProofError(f"{field} exceeds maximum nesting depth")
    if value is None or type(value) is bool or type(value) is str:
        if type(value) is str:
            _text(value, field=field)
        return value
    if type(value) is int:
        if abs(value) > 10**18:
            raise ProofError(f"{field} integer is outside supported range")
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ProofError(f"{field} must be finite")
        return value
    if type(value) is list:
        if len(value) > 1024:
            raise ProofError(f"{field} list is too large")
        return [_json_value(v, field=f"{field}[]", depth=depth + 1) for v in value]
    if type(value) is dict:
        if len(value) > 1024:
            raise ProofError(f"{field} object is too large")
        out: dict[str, Any] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise ProofError(f"{field} keys must be strings")
            _text(key, field=f"{field}.key", max_bytes=256)
            out[key] = _json_value(item, field=f"{field}.{key}", depth=depth + 1)
        return out
    raise ProofError(f"{field} contains unsupported JSON type {type(value).__name__}")


def _field_names(value: Any, *, field: str) -> tuple[str, ...]:
    if type(value) is not list:
        raise ProofError(f"{field} must be a list")
    seen: set[str] = set()
    out: list[str] = []
    for item in value:
        if type(item) is not str or not _FIELD_RE.fullmatch(item):
            raise ProofError(f"{field} contains invalid field name")
        if item in seen:
            raise ProofError(f"{field} contains duplicate {item}")
        seen.add(item)
        out.append(item)
    return tuple(sorted(out))


def validate_spec(spec: Any) -> dict[str, Any]:
    if type(spec) is not dict:
        raise ProofError("spec must be an object")
    allowed = {
        "schema",
        "profile",
        "required_fields",
        "ignored_fields",
        "require_evidence_identity",
        "require_version_identity",
        "max_records_per_side",
    }
    unknown = sorted(set(spec) - allowed)
    if unknown:
        raise ProofError(f"spec contains unknown fields: {', '.join(unknown)}")
    if spec.get("schema") != SCHEMA:
        raise ProofError(f"spec.schema must equal {SCHEMA}")
    profile = spec.get("profile")
    if type(profile) is not str or not _PROFILE_RE.fullmatch(profile):
        raise ProofError("spec.profile is invalid")
    required = _field_names(spec.get("required_fields", []), field="spec.required_fields")
    ignored = _field_names(spec.get("ignored_fields", []), field="spec.ignored_fields")
    overlap = sorted(set(required) & set(ignored))
    if overlap:
        raise ProofError(f"required_fields cannot be ignored: {', '.join(overlap)}")
    evidence_identity = spec.get("require_evidence_identity", False)
    version_identity = spec.get("require_version_identity", True)
    if type(evidence_identity) is not bool or type(version_identity) is not bool:
        raise ProofError("identity options must be booleans")
    max_records = spec.get("max_records_per_side", MAX_RECORDS_PER_SIDE)
    if type(max_records) is not int or not (1 <= max_records <= MAX_RECORDS_PER_SIDE):
        raise ProofError(f"max_records_per_side must be 1..{MAX_RECORDS_PER_SIDE}")
    return {
        "schema": SCHEMA,
        "profile": profile,
        "required_fields": list(required),
        "ignored_fields": list(ignored),
        "require_evidence_identity": evidence_identity,
        "require_version_identity": version_identity,
        "max_records_per_side": max_records,
    }


