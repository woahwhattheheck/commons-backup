"""Internal CURRENT runtime used only by the direct isolated CLI boundary.

Importing this module inside an arbitrary existing interpreter does not itself
establish production authority. The supported boundary is direct ``cli.py``
startup under ``python -I -S`` before caller-authored Python executes.
"""
from __future__ import annotations

from typing import Any

from . import _guard_core as _core
from . import current_impl as _impl


def _bind_internal_engine() -> None:
    # current_impl imports the public fail-closed guard by default. Rebind the
    # module's guard namespace to the deterministic core. Do not replace
    # current_impl._core: that helper inspects evaluate() and must keep its
    # four-argument wrapper shape.
    _impl.guard = _core


def compile_current(
    intent_raw: dict[str, Any], evidence_raw: dict[str, Any]
) -> dict[str, Any]:
    _bind_internal_engine()
    return _impl.compile_current(intent_raw, evidence_raw)


def compile_current_bytes(intent_bytes: bytes, evidence_bytes: bytes) -> dict[str, Any]:
    _bind_internal_engine()
    return _impl.compile_current_bytes(intent_bytes, evidence_bytes)


def verify_current(
    intent_raw: dict[str, Any],
    evidence_raw: dict[str, Any],
    receipt_raw: dict[str, Any],
) -> dict[str, Any]:
    _bind_internal_engine()
    return _impl.verify_current(intent_raw, evidence_raw, receipt_raw)


def verify_current_bytes(
    intent_bytes: bytes, evidence_bytes: bytes, receipt_bytes: bytes
) -> dict[str, Any]:
    _bind_internal_engine()
    return _impl.verify_current_bytes(intent_bytes, evidence_bytes, receipt_bytes)


def main(argv: list[str] | None = None) -> int:
    _bind_internal_engine()
    return _impl.main(argv)
