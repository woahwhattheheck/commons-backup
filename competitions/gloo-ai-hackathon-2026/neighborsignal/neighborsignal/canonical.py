from __future__ import annotations

import hashlib
import json
from typing import Any


class CanonicalError(ValueError):
    pass


def _check(value: Any, path: str = "$", *, reject_float: bool = True) -> None:
    if value is None or isinstance(value, (bool, str, int)):
        return
    if isinstance(value, float):
        if reject_float:
            raise CanonicalError(f"floats are not permitted at {path}; use integer/string facts")
        return
    if isinstance(value, list):
        for i, item in enumerate(value):
            _check(item, f"{path}[{i}]", reject_float=reject_float)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise CanonicalError(f"object key must be a non-empty string at {path}")
            _check(item, f"{path}.{key}", reject_float=reject_float)
        return
    raise CanonicalError(f"unsupported type at {path}: {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    _check(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
