"""Hardened public authority boundary for the NUMIH retained-byte compiler.

The reviewed v2 computation is retained byte-for-byte in ``_compiler_core.py``.
This facade closes public rendering and hostile-JSON error-boundary gaps without
changing the packet-readiness policy or retained-byte evidence semantics.
"""
from __future__ import annotations

import json
import math
import unicodedata
from collections import OrderedDict
from typing import Any

from . import _compiler_core as _core

# Preserve the reviewed implementation surface for source-compatible callers.
for _name in dir(_core):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_core, _name)

ValidationError = _core.ValidationError
_ORIGINAL_STR = _core._str
_ORIGINAL_RENDER = _core.render_markdown

_MAX_JSON_DEPTH = 200
_MAX_JSON_NODES = 100_000
_MAX_INTEGER_BITS = 16_384
_MAX_RENDER_CONTEXTS = 64
_RENDER_CONTEXTS: "OrderedDict[int, tuple[Any, Any | None, str]]" = OrderedDict()

# Numeric entities avoid Markdown backslash behavior differences across renderers.
_MD_ENTITIES = {
    "&": "&#38;",
    "\\": "&#92;",
    "`": "&#96;",
    "*": "&#42;",
    "_": "&#95;",
    "{": "&#123;",
    "}": "&#125;",
    "[": "&#91;",
    "]": "&#93;",
    "(": "&#40;",
    ")": "&#41;",
    "#": "&#35;",
    "+": "&#43;",
    "-": "&#45;",
    ".": "&#46;",
    "!": "&#33;",
    "|": "&#124;",
    "<": "&#60;",
    ">": "&#62;",
    "~": "&#126;",
}


def _validate_text_scalar(value: str, path: str) -> str:
    for index, char in enumerate(value):
        code = ord(char)
        category = unicodedata.category(char)
        if 0xD800 <= code <= 0xDFFF:
            raise ValidationError(
                f"{path}[{index}] contains a non-scalar Unicode surrogate"
            )
        if code < 0x20 or 0x7F <= code <= 0x9F or category in {"Cf", "Zl", "Zp"}:
            raise ValidationError(
                f"{path}[{index}] contains a disallowed control, format control, or line separator"
            )
    return value


def _validate_json_tree(value: Any, path: str = "$") -> Any:
    """Validate JSON values iteratively so hostile depth cannot escape raw errors."""
    stack: list[tuple[Any, str, int]] = [(value, path, 0)]
    nodes = 0
    while stack:
        current, current_path, depth = stack.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES:
            raise ValidationError("JSON value exceeds node limit")
        if depth > _MAX_JSON_DEPTH:
            raise ValidationError("JSON nesting limit exceeded")

        if current is None or type(current) is bool:
            continue
        if type(current) is int:
            if current.bit_length() > _MAX_INTEGER_BITS:
                raise ValidationError(f"{current_path} integer exceeds bit limit")
            continue
        if type(current) is float:
            if not math.isfinite(current):
                raise ValidationError(f"{current_path} must be finite")
            continue
        if type(current) is str:
            _validate_text_scalar(current, current_path)
            continue
        if type(current) is list:
            for index in range(len(current) - 1, -1, -1):
                stack.append((current[index], f"{current_path}[{index}]", depth + 1))
            continue
        if type(current) is dict:
            for key, item in reversed(list(current.items())):
                if type(key) is not str:
                    raise ValidationError(f"{current_path} object key must be a string")
                _validate_text_scalar(key, current_path + ".<key>")
                stack.append((item, f"{current_path}.{key}", depth + 1))
            continue
        raise ValidationError(
            f"{current_path} contains non-JSON value type {type(current).__name__}"
        )
    return value


def _pairs_scalar_safe(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicates without reflecting an unvalidated decoded key."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError("duplicate JSON key")
        result[key] = value
    return result


def loads_strict(text: str) -> Any:
    if type(text) is not str:
        raise ValidationError("strict JSON input must be text")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs_scalar_safe,
            parse_constant=_core._constant,
        )
    except ValidationError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError, TypeError, UnicodeError) as exc:
        raise ValidationError(f"strict JSON parse failed: {exc}") from None
    return _validate_json_tree(value)


def canonical_json(value: Any) -> str:
    _validate_json_tree(value)
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (RecursionError, ValueError, TypeError, UnicodeError) as exc:
        raise ValidationError(f"canonical JSON encoding failed: {exc}") from None


def _strict_str(value: Any, path: str, *, empty: bool = False) -> str:
    text = _ORIGINAL_STR(value, path, empty=empty)
    return _validate_text_scalar(text, path)


def _remember_render_context(
    result: dict[str, Any], packet: Any, evidence_bundle: Any | None
) -> None:
    key = id(result)
    _RENDER_CONTEXTS[key] = (
        packet,
        evidence_bundle,
        _core.digest_json(result),
    )
    _RENDER_CONTEXTS.move_to_end(key)
    while len(_RENDER_CONTEXTS) > _MAX_RENDER_CONTEXTS:
        _RENDER_CONTEXTS.popitem(last=False)


def compile_packet(packet: Any, evidence_bundle: Any | None = None) -> dict[str, Any]:
    """Compile with the reviewed core and retain bounded in-process render provenance."""
    result = _core.compile_packet(packet, evidence_bundle)
    _remember_render_context(result, packet, evidence_bundle)
    return result


def _md(value: str) -> str:
    return value.translate(str.maketrans(_MD_ENTITIES))


def _markdown_tree(value: Any) -> Any:
    if type(value) is str:
        return _md(value)
    if type(value) is list:
        return [_markdown_tree(item) for item in value]
    if type(value) is dict:
        return {key: _markdown_tree(item) for key, item in value.items()}
    return value


def render_markdown(
    packet_or_result: Any,
    result: dict[str, Any] | None = None,
    evidence_bundle: Any | None = None,
) -> str:
    """Render only a receipt-valid result bound to its exact packet and bundle.

    Preferred public form is ``render_markdown(packet, result, evidence_bundle)``.
    The one-argument compatibility form is accepted only for the exact result
    object returned by this facade's ``compile_packet`` in the current process;
    arbitrary or deserialized result dictionaries cannot mint render authority.
    """
    if result is None:
        candidate = packet_or_result
        if type(candidate) is not dict:
            raise ValidationError("render requires a compiled result object")
        context = _RENDER_CONTEXTS.get(id(candidate))
        if context is None:
            raise ValidationError(
                "unbound result cannot render; provide packet, result, and evidence bundle"
            )
        packet, evidence_bundle, expected_digest = context
        if _core.digest_json(candidate) != expected_digest:
            raise ValidationError("tampered result cannot render")
        result = candidate
    else:
        packet = packet_or_result

    if not _core.verify_result(packet, result, evidence_bundle):
        raise ValidationError("result verification failed; refusing Markdown render")
    return _ORIGINAL_RENDER(_markdown_tree(result))


# Patch the retained core's dynamic global seams so *all* supported compilation,
# verification, receipt hashing, and field validation share the hardened boundary.
_core.loads_strict = loads_strict
_core.canonical_json = canonical_json
_core._str = _strict_str
_core.render_markdown = render_markdown
