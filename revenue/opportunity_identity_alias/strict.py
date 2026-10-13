"""Strict deterministic JSON primitives for opportunity identity facts."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

REGISTRY_SCHEMA = "opportunity-identity-alias-registry/v1"
OBSERVATION_SCHEMA = "opportunity-identity-alias-observation/v1"
RESULT_SCHEMA = "opportunity-identity-alias-result/v1"
ALIAS_TYPES = frozenset({"official_id", "authority_url"})
STATES = frozenset({"RESOLVED", "UNRESOLVED_ALIAS", "AMBIGUOUS_ALIAS_SET"})
MAX_JSON_BYTES = 256 * 1024
MAX_SAFE_INTEGER = (1 << 53) - 1
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class IdentityAliasError(ValueError):
    """Strict schema or semantic validation failure."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise IdentityAliasError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_json_loads(raw: str) -> Any:
    if type(raw) is not str:
        raise IdentityAliasError("JSON text must be str")
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                IdentityAliasError(f"non-finite JSON number: {token}")
            ),
            parse_float=lambda token: (_ for _ in ()).throw(
                IdentityAliasError(f"floating-point JSON number forbidden: {token}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise IdentityAliasError("invalid JSON") from exc
    validate_json_domain(value)
    return value


def validate_json_domain(value: Any, depth: int = 0, nodes: list[int] | None = None) -> None:
    if nodes is None:
        nodes = [0]
    nodes[0] += 1
    if nodes[0] > 20_000:
        raise IdentityAliasError("JSON value count exceeds limit")
    if depth > 24:
        raise IdentityAliasError("JSON nesting exceeds limit")
    if value is None or type(value) in (str, bool):
        return
    if type(value) is int:
        if abs(value) > MAX_SAFE_INTEGER:
            raise IdentityAliasError("integer exceeds exact JSON range")
        return
    if type(value) is float:
        raise IdentityAliasError("floating-point values forbidden")
    if type(value) is list:
        for item in value:
            validate_json_domain(item, depth + 1, nodes)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise IdentityAliasError("JSON object keys must be strings")
            validate_json_domain(item, depth + 1, nodes)
        return
    raise IdentityAliasError(f"unsupported JSON type: {type(value).__name__}")


def canonical_json(value: Any) -> bytes:
    validate_json_domain(value)
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise IdentityAliasError("value is not canonical JSON") from exc


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def exact_keys(value: Any, keys: set[str], label: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise IdentityAliasError(f"{label}: exact fields required")
    return value
