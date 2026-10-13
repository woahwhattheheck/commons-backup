"""Deterministic state snapshots and no-mutation assertions for denied operations.

The helpers in this module are intentionally small and stdlib-only. They operate on
strict JSON-like state so a denial-path test can prove that a rejected operation did
not partially mutate a journal, ledger, cache, or other caller-owned mapping.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Any, Callable, TypeVar


class SnapshotError(ValueError):
    """Raised when a value cannot be represented as strict canonical JSON."""


@dataclass(frozen=True)
class JSONSnapshot:
    """Content-addressed snapshot of one strict JSON-like value."""

    sha256: str
    byte_length: int
    _payload: bytes = field(repr=False, compare=True)


T = TypeVar("T", bound=BaseException)
ExpectedException = type[T] | tuple[type[BaseException], ...]


def _validate_json(value: Any, *, path: str = "$", active: set[int] | None = None) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SnapshotError(f"{path}: non-finite numbers are not strict JSON")
        return

    if active is None:
        active = set()

    if isinstance(value, list):
        identity = id(value)
        if identity in active:
            raise SnapshotError(f"{path}: cyclic containers are not strict JSON")
        active.add(identity)
        try:
            for index, item in enumerate(value):
                _validate_json(item, path=f"{path}[{index}]", active=active)
        finally:
            active.remove(identity)
        return

    if isinstance(value, dict):
        identity = id(value)
        if identity in active:
            raise SnapshotError(f"{path}: cyclic containers are not strict JSON")
        active.add(identity)
        try:
            for key, item in value.items():
                if not isinstance(key, str):
                    raise SnapshotError(f"{path}: object keys must be strings")
                _validate_json(item, path=f"{path}.{key}", active=active)
        finally:
            active.remove(identity)
        return

    raise SnapshotError(f"{path}: unsupported JSON value type {type(value).__name__}")


def _canonical_json_bytes(value: Any) -> bytes:
    _validate_json(value)
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise SnapshotError("value is not strict canonical JSON") from exc
    return text.encode("utf-8")


def snapshot_json(value: Any) -> JSONSnapshot:
    """Return a deterministic content-addressed snapshot of ``value``."""

    payload = _canonical_json_bytes(value)
    return JSONSnapshot(
        sha256=hashlib.sha256(payload).hexdigest(),
        byte_length=len(payload),
        _payload=payload,
    )


def assert_json_unchanged(before: JSONSnapshot, value: Any, *, label: str = "state") -> None:
    """Assert that ``value`` is byte-identical to an earlier JSON snapshot."""

    if not isinstance(before, JSONSnapshot):
        raise TypeError("before must be a JSONSnapshot")
    try:
        after = snapshot_json(value)
    except SnapshotError as exc:
        raise AssertionError(f"{label} is no longer strict JSON") from exc
    if before._payload != after._payload:
        raise AssertionError(
            f"{label} mutated: sha256 {before.sha256} -> {after.sha256}; "
            f"bytes {before.byte_length} -> {after.byte_length}"
        )


def _normalize_expected(expected: ExpectedException) -> tuple[type[BaseException], ...]:
    candidates = expected if isinstance(expected, tuple) else (expected,)
    if not candidates:
        raise TypeError("expected_exception must not be empty")
    if any(not isinstance(item, type) or not issubclass(item, BaseException) for item in candidates):
        raise TypeError("expected_exception must contain exception classes")
    return candidates


def _expected_name(expected: tuple[type[BaseException], ...]) -> str:
    return " or ".join(item.__name__ for item in expected)


def assert_raises_without_mutation(
    expected_exception: ExpectedException,
    operation: Callable[[], Any],
    *states: Any,
    label: str = "state",
) -> BaseException:
    """Run a denied operation and prove every supplied state remains unchanged.

    Snapshots are taken before ``operation`` is invoked. If a state is not strict
    JSON at that point, the operation is never called. After execution, mutation is
    checked before exception correctness so partial writes cannot be hidden behind an
    otherwise expected denial error.
    """

    expected = _normalize_expected(expected_exception)
    if not callable(operation):
        raise TypeError("operation must be callable")
    if not states:
        raise ValueError("at least one state is required")

    before = tuple(snapshot_json(state) for state in states)
    caught: BaseException | None = None
    try:
        operation()
    except BaseException as exc:  # Assertion helper may intentionally expect any exception class.
        caught = exc

    mutation_failure: AssertionError | None = None
    for index, (snapshot, state) in enumerate(zip(before, states)):
        try:
            assert_json_unchanged(snapshot, state, label=f"{label}[{index}]")
        except AssertionError as exc:
            if mutation_failure is None:
                mutation_failure = exc

    if mutation_failure is not None:
        if caught is not None:
            raise mutation_failure from caught
        raise mutation_failure

    if caught is None:
        raise AssertionError(f"operation did not raise {_expected_name(expected)}")
    if not isinstance(caught, expected):
        raise AssertionError(
            f"operation raised {type(caught).__name__}, expected {_expected_name(expected)}"
        ) from caught
    return caught
