from __future__ import annotations

import json
import math
from typing import Any

MAX_SAFE_INTEGER = (1 << 53) - 1


class StrictJsonError(ValueError):
    pass


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise StrictJsonError(f"duplicate key: {key}")
        if key in {"__proto__", "prototype", "constructor"}:
            raise StrictJsonError(f"reserved key: {key}")
        out[key] = value
    return out


def _reject_constant(value: str) -> None:
    raise StrictJsonError(f"non-finite number: {value}")


def validate_json_value(value: Any, *, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int) and not isinstance(value, bool):
        if not -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER:
            raise StrictJsonError(f"integer outside interoperable range at {path}")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise StrictJsonError(f"non-finite number at {path}")
        raise StrictJsonError(f"floating point values are not canonical at {path}")
    if isinstance(value, list):
        for index, item in enumerate(value):
            validate_json_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise StrictJsonError(f"non-string object key at {path}")
            if key in {"__proto__", "prototype", "constructor"}:
                raise StrictJsonError(f"reserved key at {path}.{key}")
            validate_json_value(item, path=f"{path}.{key}")
        return
    raise StrictJsonError(f"unsupported value type at {path}: {type(value).__name__}")


def loads_strict(text: str) -> Any:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_constant,
        )
    except StrictJsonError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise StrictJsonError(str(exc)) from exc
    validate_json_value(value)
    return value


def canonical_json(value: Any) -> str:
    validate_json_value(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
