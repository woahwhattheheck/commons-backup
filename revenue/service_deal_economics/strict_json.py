from __future__ import annotations

import hashlib
import json
from typing import Any

from .engine import DealEconomicsError


def _reject_constant(value: str) -> None:
    raise DealEconomicsError(f"non-finite JSON number is not allowed: {value}")


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DealEconomicsError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _utf8_scalar(value: str, label: str) -> None:
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise DealEconomicsError(f"{label} contains non-UTF-8 scalar text") from exc


def _validate_json_scalars(value: Any, label: str = "JSON") -> None:
    """Reject scalar shapes that cannot participate in canonical UTF-8 JSON.

    JSON decoding can create lone-surrogate Python strings from escaped input.
    Those strings are not valid UTF-8 scalar text even though ``json.loads``
    accepts them. Walking the decoded value here keeps that failure inside the
    normal domain-error boundary instead of letting it escape later from a
    receipt hash or CLI print.
    """

    if value is None or type(value) in {bool, int, float}:
        return
    if type(value) is str:
        _utf8_scalar(value, label)
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _validate_json_scalars(item, f"{label}[{index}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise DealEconomicsError(f"{label} object keys must be strings")
            _utf8_scalar(key, f"{label} key")
            _validate_json_scalars(item, f"{label}.{key}")
        return
    raise DealEconomicsError(f"{label} contains unsupported scalar type")


def parse_strict_json(text: str) -> Any:
    if type(text) is not str:
        raise DealEconomicsError("JSON input must be text")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_constant,
        )
        _validate_json_scalars(value)
        return value
    except DealEconomicsError:
        raise
    except (
        json.JSONDecodeError,
        UnicodeDecodeError,
        UnicodeEncodeError,
        ValueError,
        TypeError,
        OverflowError,
        RecursionError,
    ) as exc:
        raise DealEconomicsError(f"invalid JSON: {exc}") from exc


def canonical_json(value: Any) -> str:
    try:
        _validate_json_scalars(value)
        rendered = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        # ``ensure_ascii=False`` can otherwise return a Python string carrying
        # lone surrogates. Force the same UTF-8 boundary used by receipts.
        rendered.encode("utf-8", "strict")
        return rendered
    except DealEconomicsError:
        raise
    except (
        UnicodeDecodeError,
        UnicodeEncodeError,
        ValueError,
        TypeError,
        OverflowError,
        RecursionError,
    ) as exc:
        raise DealEconomicsError(f"value cannot be canonicalized as UTF-8 JSON: {exc}") from exc


def digest(value: Any) -> str:
    try:
        return hashlib.sha256(canonical_json(value).encode("utf-8", "strict")).hexdigest()
    except DealEconomicsError:
        raise
    except (UnicodeError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise DealEconomicsError(f"value cannot be hashed canonically: {exc}") from exc
