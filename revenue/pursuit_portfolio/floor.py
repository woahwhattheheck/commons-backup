"""Explicit-time parser for the separately retained latest-authority floor."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from pathlib import Path
from typing import Any

from .core import PortfolioError, load_json_bytes
from .current import AuthorityKey, _canonical, _dt, _sha, _token, read_regular_bytes

FLOOR_SCHEMA = "pursuit-portfolio-allocation/authority-floor/v1"
MAX_FLOOR_BYTES = 16 * 1024
_FLOOR_KEYS = frozenset(
    {
        "authority_sha256",
        "generation",
        "hmac_sha256",
        "key_id",
        "schema",
        "updated_at",
    }
)


@dataclass(frozen=True)
class AuthorityFloor:
    authority_sha256: str
    generation: int
    key_id: str
    updated_at: str
    value: dict[str, Any]
    raw: bytes


def _unsigned(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "authority_sha256": value["authority_sha256"],
        "generation": value["generation"],
        "key_id": value["key_id"],
        "schema": value["schema"],
        "updated_at": value["updated_at"],
    }


def _normalize(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value) != set(_FLOOR_KEYS):
        raise PortfolioError("authority floor: exact key set required")
    if value["schema"] != FLOOR_SCHEMA:
        raise PortfolioError("authority floor: unsupported schema")
    generation = value["generation"]
    if type(generation) is not int or type(generation) is bool or not 1 <= generation <= 10**12:
        raise PortfolioError("authority floor.generation: positive bounded integer required")
    updated_at = value["updated_at"]
    _dt(updated_at, "authority floor.updated_at")
    return {
        "authority_sha256": _sha(
            value["authority_sha256"], "authority floor.authority_sha256"
        ),
        "generation": generation,
        "hmac_sha256": _sha(value["hmac_sha256"], "authority floor.hmac_sha256"),
        "key_id": _token(value["key_id"], "authority floor.key_id"),
        "schema": FLOOR_SCHEMA,
        "updated_at": updated_at,
    }


def parse_authority_floor(
    raw: bytes, key: AuthorityKey, trusted_now: str
) -> AuthorityFloor:
    value = _normalize(load_json_bytes(raw, "authority floor"))
    if raw != _canonical(value):
        raise PortfolioError("authority floor: persisted bytes must be canonical JSON")
    if value["key_id"] != key.key_id:
        raise PortfolioError("authority floor: key_id mismatch")
    if _dt(value["updated_at"], "authority floor.updated_at") > _dt(
        trusted_now, "trusted_now"
    ):
        raise PortfolioError("authority floor: future-updated generation")
    expected = hmac.new(
        key.key, _canonical(_unsigned(value)), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(value["hmac_sha256"], expected):
        raise PortfolioError("authority floor: HMAC mismatch")
    return AuthorityFloor(
        authority_sha256=value["authority_sha256"],
        generation=value["generation"],
        key_id=value["key_id"],
        updated_at=value["updated_at"],
        value=value,
        raw=raw,
    )


def load_authority_floor_at(
    path: str | Path, key: AuthorityKey, trusted_now: str
) -> AuthorityFloor:
    return parse_authority_floor(
        read_regular_bytes(
            path, MAX_FLOOR_BYTES, "authority floor", private=True
        ),
        key,
        trusted_now,
    )


def load_authority_floor(*args: Any, **kwargs: Any) -> Any:
    del args, kwargs
    raise PortfolioError(
        "production floor acquisition requires the fixed-host fresh-process boundary"
    )


def require_current_authority(
    floor: AuthorityFloor, authority_raw: bytes
) -> None:
    observed = hashlib.sha256(authority_raw).hexdigest()
    if not hmac.compare_digest(observed, floor.authority_sha256):
        raise PortfolioError(
            "authority floor: packaged upstream authority is superseded or not the retained current generation"
        )


# Compatibility aliases for explicit-time replay tests.
_load_authority_floor_at = load_authority_floor_at
