from __future__ import annotations

import json
from typing import Any


class StrictJSONError(ValueError):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise StrictJSONError(f"duplicate key: {key}")
        out[key] = value
    return out


def loads(text: str) -> Any:
    def bad_constant(value: str) -> None:
        raise StrictJSONError(f"non-finite number: {value}")

    try:
        return json.loads(text, object_pairs_hook=_pairs, parse_constant=bad_constant)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise StrictJSONError(str(exc)) from exc
