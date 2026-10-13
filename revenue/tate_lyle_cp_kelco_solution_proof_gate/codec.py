from __future__ import annotations

import hashlib
import json
import re
from typing import Any

AUTHORITY = "READY_FOR_OWNER_INTEGRATION_REVIEW"
RECORD_SCHEMA = "tate-lyle-cp-kelco-solution-pack/v2"
BATCH_SCHEMA = "tate-lyle-cp-kelco-solution-batch/v2"
REFERENCE_SCHEMA = "tate-lyle-cp-kelco-reference-set/v2"
MANIFEST_SCHEMA = "tate-lyle-cp-kelco-solution-manifest/v2"
RECEIPT_SCHEMA = "tate-lyle-cp-kelco-solution-receipt/v2"
MAX_RECORDS = 500
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class GateInputError(ValueError):
    pass


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(obj: Any) -> str:
    return hashlib.sha256(_canonical(obj)).hexdigest()


def _dict(obj: Any, name: str) -> dict[str, Any]:
    if type(obj) is not dict:
        raise GateInputError(f"{name} must be an object")
    return obj


def _keys(obj: dict[str, Any], expected: set[str], name: str) -> None:
    if set(obj) != expected:
        raise GateInputError(f"{name} field set is not exact")


def _str(obj: Any, name: str) -> str:
    if type(obj) is not str or not obj:
        raise GateInputError(f"{name} must be a non-empty string")
    return obj


def _hex64(obj: Any, name: str) -> str:
    value = _str(obj, name)
    if _HEX64.fullmatch(value) is None:
        raise GateInputError(f"{name} must be lowercase sha256")
    return value
