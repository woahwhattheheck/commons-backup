"""Sealed public API for the exact-head ship-fence evidence compiler.

The validated core is stored as non-importable ``_core.src``.  This module
hash-checks those bytes before executing them in a private namespace, then
exports only a sealed API.  There is no secondary ``_core.py`` module to call
around the seal.
"""
from __future__ import annotations

import hashlib as _loader_hashlib
import json as _loader_json
import re as _loader_re
from pathlib import Path as _Path
from types import MappingProxyType as _MappingProxyType
from typing import Any

_CORE_SOURCE_SHA256 = "6c6c2dc5703dabcd07dd73fb6097bb1060a6d256967a26dbc90228296203673b"

if "_TRUSTED_RUNTIME_MEMBERS" not in globals():
    _TRUSTED_RUNTIME_MEMBERS = _MappingProxyType({
        "hashlib.sha256": _loader_hashlib.sha256,
        "json.loads": _loader_json.loads,
        "json.dumps": _loader_json.dumps,
        "json.JSONDecodeError": _loader_json.JSONDecodeError,
        "re.compile": _loader_re.compile,
        "re.fullmatch": _loader_re.fullmatch,
    })

for _label, _current in (
    ("hashlib.sha256", _loader_hashlib.sha256),
    ("json.loads", _loader_json.loads),
    ("json.dumps", _loader_json.dumps),
    ("json.JSONDecodeError", _loader_json.JSONDecodeError),
    ("re.compile", _loader_re.compile),
    ("re.fullmatch", _loader_re.fullmatch),
):
    if _current is not _TRUSTED_RUNTIME_MEMBERS[_label]:
        raise ImportError(f"exact-head ship-fence runtime member changed: {_label}")
del _label, _current
# importlib.reload() reuses the module dictionary.  Remove legacy helper names
# that are intentionally not part of this public module's semantic graph.
for _stale_name in ("_build", "_class", "_sha"):
    globals().pop(_stale_name, None)
del _stale_name

_AUTHORITY_LITERAL = {
    "merge_authorized": False,
    "ref_mutation_authorized": False,
    "review_mutation_authorized": False,
    "provider_mutation_authorized": False,
    "outbound_authorized": False,
    "spend_authorized": False,
    "payment_authorized": False,
    "revenue_recognition_authorized": False,
}


def _load_generation():
    core_path = _Path(__file__).with_name("_core.src")
    source = core_path.read_bytes()
    if _TRUSTED_RUNTIME_MEMBERS["hashlib.sha256"](source).hexdigest() != _CORE_SOURCE_SHA256:
        raise ImportError("exact-head ship-fence core source digest mismatch")

    namespace: dict[str, Any] = {
        "__name__": f"{__name__}._sealed_core_image",
        "__file__": str(core_path),
        "__package__": __package__,
        "__builtins__": __builtins__,
    }
    exec(compile(source, str(core_path), "exec"), namespace, namespace)

    error = namespace["EvidenceError"]
    if namespace.get("AUTHORITY") != _AUTHORITY_LITERAL:
        raise ImportError("exact-head ship-fence core authority source mismatch")
    namespace["AUTHORITY"] = _MappingProxyType(dict(_AUTHORITY_LITERAL))

    raw_parse = namespace["parse_json_bytes"]
    raw_canonical = namespace["canonical_json_bytes"]
    raw_compile = namespace["compile_current"]
    raw_verify = namespace["verify_current"]
    raw_render = namespace["render_markdown"]
    raw_array = namespace["_arr"]
    raw_sha = namespace["_sha"]
    raw_name = namespace["_name"]
    clock = namespace["_CURRENT_CLOCK"]
    authority_literal = dict(_AUTHORITY_LITERAL)
    pattern_type = type(namespace["SHA"])

    def freeze(value: Any):
        t = type(value)
        if value is None or t in (bool, int, str):
            return (t.__name__, value)
        if t is dict:
            return ("dict", tuple(sorted((k, freeze(v)) for k, v in value.items())))
        if t is set:
            return ("set", tuple(sorted(freeze(v) for v in value)))
        if t is tuple:
            return ("tuple", tuple(freeze(v) for v in value))
        if t is list:
            return ("list", tuple(freeze(v) for v in value))
        if t is _MappingProxyType:
            return ("mappingproxy", freeze(dict(value)))
        if isinstance(value, pattern_type):
            return ("regex", value.pattern, value.flags)
        return ("identity", id(value))

    private_callables = {
        name: value
        for name, value in namespace.items()
        if name.startswith("_") and callable(value)
    }
    constant_snapshot = {
        name: freeze(value)
        for name, value in namespace.items()
        if name.isupper()
    }
    imported_bindings = {
        name: namespace[name]
        for name in ("datetime", "timezone", "hashlib", "json", "re")
    }
    runtime_members = {
        "hashlib.sha256": (namespace["hashlib"], "sha256", _TRUSTED_RUNTIME_MEMBERS["hashlib.sha256"]),
        "json.loads": (namespace["json"], "loads", _TRUSTED_RUNTIME_MEMBERS["json.loads"]),
        "json.dumps": (namespace["json"], "dumps", _TRUSTED_RUNTIME_MEMBERS["json.dumps"]),
        "json.JSONDecodeError": (namespace["json"], "JSONDecodeError", _TRUSTED_RUNTIME_MEMBERS["json.JSONDecodeError"]),
        "re.compile": (namespace["re"], "compile", _TRUSTED_RUNTIME_MEMBERS["re.compile"]),
        "re.fullmatch": (namespace["re"], "fullmatch", _TRUSTED_RUNTIME_MEMBERS["re.fullmatch"]),
    }

    def integrity() -> None:
        for name, value in private_callables.items():
            if namespace.get(name) is not value:
                raise error(f"core semantic binding changed: {name}")
        for name, snapshot in constant_snapshot.items():
            if freeze(namespace.get(name)) != snapshot:
                raise error(f"core constant changed: {name}")
        for name, value in imported_bindings.items():
            if namespace.get(name) is not value:
                raise error(f"core runtime binding changed: {name}")
        for label, (owner, attr, value) in runtime_members.items():
            if getattr(owner, attr, None) is not value:
                raise error(f"core runtime member changed: {label}")

    def reviewer_guard(snapshot: Any) -> None:
        if type(snapshot) is not dict:
            return  # The core supplies the canonical root-schema error.
        # Apply the existing core limits/types before comparisons or casefold.
        # This guard must not walk an oversized list or invoke non-JSON methods.
        rows = raw_array(snapshot.get("reviews"), "reviews", 64)
        current_head = raw_sha(snapshot.get("current_pr_head"), "current_pr_head")
        seen: set[str] = set()
        for index, row in enumerate(rows):
            if type(row) is not dict:
                continue  # Full row-schema validation remains in the core.
            head = raw_sha(row.get("head_sha"), f"reviews[{index}].head_sha")
            reviewer = raw_name(row.get("reviewer"), f"reviews[{index}].reviewer")
            if head != current_head:
                continue
            identity = reviewer.casefold()
            if identity in seen:
                raise error("reviews: duplicate current-head reviewer identity")
            seen.add(identity)

    def parse_json_bytes(data: bytes):
        integrity()
        out = raw_parse(data)
        integrity()
        return out

    def canonical_json_bytes(value: Any) -> bytes:
        integrity()
        out = raw_canonical(value)
        integrity()
        return out

    def compile_current(snapshot: Any) -> dict:
        integrity()
        reviewer_guard(snapshot)
        report = raw_compile(snapshot, _clock=clock)
        integrity()
        if report.get("authority") != authority_literal:
            raise error("authority ceiling widened")
        return report

    def verify_current(report: Any, snapshot: Any) -> bool:
        try:
            integrity()
            reviewer_guard(snapshot)
            if type(report) is not dict or report.get("authority") != authority_literal:
                return False
            ok = raw_verify(report, snapshot, _clock=clock)
            integrity()
            return bool(ok and report.get("authority") == authority_literal)
        except error:
            return False

    def render_markdown(report: Any) -> str:
        integrity()
        if type(report) is not dict or report.get("authority") != authority_literal:
            raise error("authority ceiling widened")
        out = raw_render(report)
        integrity()
        return out

    presentation_clock = clock
    return {
        "AUTHORITY": _MappingProxyType(dict(authority_literal)),
        "EvidenceError": error,
        "SCHEMA_VERSION": namespace["SCHEMA_VERSION"],
        "TOOL_ID": namespace["TOOL_ID"],
        "MAX_JSON_BYTES": namespace["MAX_JSON_BYTES"],
        "_CURRENT_CLOCK": presentation_clock,
        "parse_json_bytes": parse_json_bytes,
        "canonical_json_bytes": canonical_json_bytes,
        "compile_current": compile_current,
        "verify_current": verify_current,
        "render_markdown": render_markdown,
    }


_exports = _load_generation()
globals().update(_exports)
del _exports

__all__ = [
    "AUTHORITY", "EvidenceError", "SCHEMA_VERSION", "TOOL_ID",
    "canonical_json_bytes", "compile_current", "parse_json_bytes",
    "render_markdown", "verify_current",
]
