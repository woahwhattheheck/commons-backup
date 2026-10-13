"""Bounded canonical JSON primitives for verifier-owned artifact boundaries.

The library is intentionally dependency-free. It accepts only exact built-in
JSON shapes, freezes direct objects into a verifier-owned generation, and
accounts for canonical serialized byte work before calling json.dumps().
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import math
from typing import Any, Iterable


class BoundaryError(ValueError):
    """Stable fail-closed error raised by this boundary."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


# CPython permits the integer-string conversion guard to be configured as low
# as 640 decimal digits. Keep public custom ceilings comfortably below that
# implementation floor so accepted integers are always conversion-safe.
MAX_SUPPORTED_INTEGER_ABS = (10**100) - 1


@dataclass(frozen=True)
class Limits:
    """Resource and semantic limits for one JSON generation.

    ``max_integer_abs`` is configurable up to 100 decimal digits. Larger
    ceilings are rejected as invalid limits before any decimal conversion.
    """

    max_depth: int = 64
    max_nodes: int = 200_000
    max_bytes: int = 4 * 1024 * 1024
    max_integer_abs: int = 10**15

    def __post_init__(self) -> None:
        if type(self.max_depth) is not int or self.max_depth < 1:
            raise BoundaryError("invalid_limits")
        if type(self.max_nodes) is not int or self.max_nodes < 1:
            raise BoundaryError("invalid_limits")
        if type(self.max_bytes) is not int or self.max_bytes < 2:
            raise BoundaryError("invalid_limits")
        if (
            type(self.max_integer_abs) is not int
            or self.max_integer_abs < 0
            or self.max_integer_abs > MAX_SUPPORTED_INTEGER_ABS
        ):
            raise BoundaryError("invalid_limits")


DEFAULT_LIMITS = Limits()


def _charge(total: int, amount: int, maximum: int) -> int:
    if amount < 0:
        raise BoundaryError("internal_budget_error")
    if amount > maximum - total:
        raise BoundaryError("too_large")
    return total + amount


def _json_string_utf8_length(value: str, remaining: int) -> int:
    """Return exact ensure_ascii=False JSON string byte length, bounded."""

    if type(value) is not str:
        raise BoundaryError("non_plain_json")

    total = 2
    if total > remaining:
        raise BoundaryError("too_large")

    for char in value:
        cp = ord(char)
        if 0xD800 <= cp <= 0xDFFF:
            raise BoundaryError("invalid_utf8")
        if char == '"' or char == "\\":
            width = 2
        elif char in "\b\t\n\f\r":
            width = 2
        elif cp < 0x20:
            width = 6
        elif cp <= 0x7F:
            width = 1
        elif cp <= 0x7FF:
            width = 2
        elif cp <= 0xFFFF:
            width = 3
        else:
            width = 4

        if width > remaining - total:
            raise BoundaryError("too_large")
        total += width

    return total


def _integer_token(token: str, maximum: int) -> int:
    negative = token.startswith("-")
    digits = token[1:] if negative else token
    if not digits or not digits.isdigit():
        raise BoundaryError("invalid_json")

    max_digits = len(str(maximum))
    if len(digits) > max_digits:
        raise BoundaryError("integer_out_of_range")

    try:
        value = int(token)
    except (TypeError, ValueError, OverflowError):
        raise BoundaryError("integer_out_of_range") from None
    if abs(value) > maximum:
        raise BoundaryError("integer_out_of_range")
    return value


def _pairs_without_duplicates(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise BoundaryError("duplicate_key")
        out[key] = value
    return out


def _scalar_length(value: Any, limits: Limits, remaining: int) -> int:
    if value is None:
        return 4
    if type(value) is bool:
        return 4 if value else 5
    if type(value) is int:
        if abs(value) > limits.max_integer_abs:
            raise BoundaryError("integer_out_of_range")
        return len(str(value))
    if type(value) is float:
        if not math.isfinite(value):
            raise BoundaryError("nonfinite_number")
        try:
            payload = json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8", "strict")
        except (TypeError, ValueError, OverflowError, UnicodeEncodeError):
            raise BoundaryError("canonicalization_failed") from None
        return len(payload)
    if type(value) is str:
        return _json_string_utf8_length(value, remaining)
    raise BoundaryError("non_plain_json")


def _freeze_and_measure(value: Any, limits: Limits) -> tuple[Any, int]:
    """Freeze one admitted generation and return its canonical byte count.

    Container snapshots are bounded before allocation and every serialized
    occurrence is frozen independently. The later serializer therefore never
    rereads caller-owned mutable containers.
    """

    nodes = 0
    total = 0
    active: set[int] = set()
    root: list[Any] = [None]
    stack: list[tuple[Any, int, Any, Any, int]] = [(value, 1, root, 0, 0)]

    while stack:
        current, depth, parent, slot, state = stack.pop()
        if state:
            active.remove(id(current))
            continue

        nodes += 1
        if nodes > limits.max_nodes:
            raise BoundaryError("too_complex")

        current_type = type(current)

        if current_type is list:
            if depth > limits.max_depth:
                raise BoundaryError("too_deep")
            ident = id(current)
            if ident in active:
                raise BoundaryError("cycle")

            member_count = len(current)
            if member_count > limits.max_nodes - nodes:
                raise BoundaryError("too_complex")
            total = _charge(
                total,
                2 + max(0, member_count - 1),
                limits.max_bytes,
            )

            snapshot = tuple(current)
            if len(snapshot) != member_count:
                raise BoundaryError("concurrent_mutation")
            frozen: list[Any] = [None] * member_count
            parent[slot] = frozen

            active.add(ident)
            stack.append((current, depth, None, None, 1))
            for index in range(member_count - 1, -1, -1):
                stack.append((snapshot[index], depth + 1, frozen, index, 0))
            continue

        if current_type is dict:
            if depth > limits.max_depth:
                raise BoundaryError("too_deep")
            ident = id(current)
            if ident in active:
                raise BoundaryError("cycle")

            member_count = len(current)
            remaining_nodes = limits.max_nodes - nodes
            if member_count > remaining_nodes // 2:
                raise BoundaryError("too_complex")
            total = _charge(
                total,
                2 + max(0, member_count - 1) + member_count,
                limits.max_bytes,
            )

            try:
                snapshot = tuple(current.items())
            except RuntimeError:
                raise BoundaryError("concurrent_mutation") from None
            if len(snapshot) != member_count:
                raise BoundaryError("concurrent_mutation")

            frozen_dict: dict[str, Any] = {}
            parent[slot] = frozen_dict
            active.add(ident)
            stack.append((current, depth, None, None, 1))

            for key, _ in snapshot:
                if type(key) is not str:
                    raise BoundaryError("non_string_key")
                nodes += 1
                if nodes > limits.max_nodes:
                    raise BoundaryError("too_complex")
                key_len = _json_string_utf8_length(
                    key,
                    limits.max_bytes - total,
                )
                total = _charge(total, key_len, limits.max_bytes)

            for key, child in reversed(snapshot):
                stack.append((child, depth + 1, frozen_dict, key, 0))
            continue

        scalar_len = _scalar_length(current, limits, limits.max_bytes - total)
        total = _charge(total, scalar_len, limits.max_bytes)
        parent[slot] = current

    return root[0], total


def canonical_bytes(value: Any, *, limits: Limits = DEFAULT_LIMITS) -> bytes:
    """Return deterministic canonical JSON bytes after bounded admission."""

    frozen, expected_length = _freeze_and_measure(value, limits)
    try:
        text = json.dumps(
            frozen,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        payload = text.encode("utf-8", "strict")
    except RecursionError:
        raise BoundaryError("canonicalization_failed") from None
    except UnicodeEncodeError:
        raise BoundaryError("invalid_utf8") from None
    except (TypeError, ValueError, OverflowError):
        raise BoundaryError("canonicalization_failed") from None

    if len(payload) != expected_length:
        raise BoundaryError("canonical_length_drift")
    if len(payload) > limits.max_bytes:
        raise BoundaryError("too_large")
    return payload


def loads_strict(data: str | bytes, *, limits: Limits = DEFAULT_LIMITS) -> Any:
    """Parse JSON text/bytes and apply the same bounded canonical contract."""

    if type(data) is bytes:
        if len(data) > limits.max_bytes:
            raise BoundaryError("too_large")
        try:
            text = data.decode("utf-8", "strict")
        except UnicodeDecodeError:
            raise BoundaryError("invalid_utf8") from None
    elif type(data) is str:
        if len(data) > limits.max_bytes:
            raise BoundaryError("too_large")
        try:
            raw = data.encode("utf-8", "strict")
        except UnicodeEncodeError:
            raise BoundaryError("invalid_utf8") from None
        if len(raw) > limits.max_bytes:
            raise BoundaryError("too_large")
        text = data
    else:
        raise BoundaryError("invalid_input_type")

    def parse_int(token: str) -> int:
        return _integer_token(token, limits.max_integer_abs)

    def parse_constant(_: str) -> Any:
        raise BoundaryError("nonfinite_number")

    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs_without_duplicates,
            parse_int=parse_int,
            parse_constant=parse_constant,
        )
    except BoundaryError:
        raise
    except RecursionError:
        raise BoundaryError("too_deep") from None
    except json.JSONDecodeError:
        raise BoundaryError("invalid_json") from None
    except (TypeError, ValueError, OverflowError):
        raise BoundaryError("invalid_json") from None

    canonical_bytes(value, limits=limits)
    return value


def canonical_equal(
    left: Any,
    right: Any,
    *,
    limits: Limits = DEFAULT_LIMITS,
) -> bool:
    """Type-sensitive canonical JSON identity comparison."""

    return hmac.compare_digest(
        canonical_bytes(left, limits=limits),
        canonical_bytes(right, limits=limits),
    )


def canonical_sha256(value: Any, *, limits: Limits = DEFAULT_LIMITS) -> str:
    """SHA-256 of admitted canonical JSON bytes."""

    return hashlib.sha256(canonical_bytes(value, limits=limits)).hexdigest()
