#!/usr/bin/env python3
"""Hardened EvidenceAAR entrypoint over the immutable deterministic engine.

The engine body is kept separately so Unicode-scalar ingress can be fenced at
one small, auditable boundary without changing its deterministic output graph.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

_ENGINE_PATH = Path(__file__).with_name("_engine.py")
_spec = importlib.util.spec_from_file_location("evidenceaar_engine", _ENGINE_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError("EvidenceAAR engine loader unavailable")
_impl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_impl)

_original_text = _impl._text
_original_pairs = _impl._pairs
_original_strict_json_loads = _impl.strict_json_loads


def _guard_scalar(value: str, field: str) -> None:
    try:
        value.encode("utf-8", "strict")
    except UnicodeError as exc:
        _impl._fail(f"{field}: invalid Unicode scalar: {exc}")


def _guard_tree(value: Any) -> None:
    stack: list[tuple[str, Any]] = [("input", value)]
    while stack:
        field, current = stack.pop()
        if type(current) is str:
            _guard_scalar(current, field)
        elif type(current) is list:
            stack.extend((f"{field}[{i}]", item) for i, item in enumerate(current))
        elif type(current) is dict:
            for key, item in current.items():
                _guard_scalar(key, f"{field} key")
                stack.append((f"{field}.{key}", item))


def _text(value: Any, field: str, *, max_chars: int, allow_empty: bool = False) -> str:
    if type(value) is str:
        _guard_scalar(value, field)
    return _original_text(value, field, max_chars=max_chars, allow_empty=allow_empty)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    for key, _ in pairs:
        _guard_scalar(key, "JSON key")
    return _original_pairs(pairs)


def strict_json_loads(raw: bytes | str) -> Any:
    if isinstance(raw, str):
        _guard_scalar(raw, "input")
    value = _original_strict_json_loads(raw)
    _guard_tree(value)
    return value


# Engine functions resolve globals in the engine module. Patch every ingress
# seam before exporting the engine API through this stable entrypoint.
_impl._text = _text
_impl._pairs = _pairs
_impl.strict_json_loads = strict_json_loads
for _name in dir(_impl):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_impl, _name)

if __name__ == "__main__":
    raise SystemExit(_impl.main())
