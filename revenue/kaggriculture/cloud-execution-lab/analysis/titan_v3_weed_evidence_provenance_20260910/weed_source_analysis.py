# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import ast
from typing import Any

from weed_ast import (
    _ancestor_map,
    _attr_path,
    _call_guarded_by_any_bit,
    _call_guarded_by_bit,
    _find_class,
    _find_method,
    _function_arg_names,
    _spatial_disable_guard_indices,
    _stores_self_attribute,
    _stores_self_attribute_from_symbol,
    _top_level_index,
)

def analyze_spatial(source: bytes) -> dict[str, Any]:
    facts: dict[str, Any] = {
        "parse_ok": False,
        "class_found": False,
        "constructor_declares_weed_bit": False,
        "constructor_stores_weed_bit": False,
        "constructor_symbolically_wires_weed_bit": False,
        "transform_found": False,
        "weed_call_count": 0,
        "weed_call_lines": [],
        "independently_guarded_call_count": 0,
        "path_or_tempo_guarded_call_count": 0,
        "unguarded_call_count": 0,
        "all_weed_calls_independently_guarded": False,
        "all_weed_calls_path_or_tempo_guarded": False,
        "spatial_disable_guard_lines": [],
        "weed_call_precedes_spatial_disable_return": False,
        "errors": [],
    }
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as exc:
        facts["errors"].append(f"spatial source is not UTF-8: {exc}")
        return facts
    try:
        module = ast.parse(text, filename="spatial_tempo.py")
    except SyntaxError as exc:
        facts["errors"].append(f"spatial source parse failure: {exc.msg} at {exc.lineno}:{exc.offset}")
        return facts
    facts["parse_ok"] = True
    cls = _find_class(module, "SpatialTempo")
    facts["class_found"] = cls is not None
    if cls is None:
        facts["errors"].append("SpatialTempo class missing")
        return facts
    init = _find_method(cls, "__init__")
    facts["constructor_declares_weed_bit"] = "weed_continuation" in _function_arg_names(init)
    facts["constructor_stores_weed_bit"] = _stores_self_attribute(init, "weed_continuation")
    facts["constructor_symbolically_wires_weed_bit"] = _stores_self_attribute_from_symbol(
        init, "weed_continuation"
    )
    transform = _find_method(cls, "transform")
    facts["transform_found"] = transform is not None
    if transform is None:
        facts["errors"].append("SpatialTempo.transform missing")
        return facts

    parents = _ancestor_map(transform)
    calls = [
        node
        for node in ast.walk(transform)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_continue_weed"
    ]
    facts["weed_call_count"] = len(calls)
    facts["weed_call_lines"] = sorted(getattr(call, "lineno", -1) for call in calls)
    independent = [
        call for call in calls if _call_guarded_by_bit(call, transform, parents, "weed_continuation")
    ]
    coupled = [
        call
        for call in calls
        if _call_guarded_by_any_bit(call, transform, parents, ("pathing", "tempo"))
    ]
    facts["independently_guarded_call_count"] = len(independent)
    facts["path_or_tempo_guarded_call_count"] = len(coupled)
    facts["unguarded_call_count"] = len(calls) - len(independent)
    facts["all_weed_calls_independently_guarded"] = bool(calls) and len(independent) == len(calls)
    facts["all_weed_calls_path_or_tempo_guarded"] = bool(calls) and len(coupled) == len(calls)

    disable_indices = _spatial_disable_guard_indices(transform)
    facts["spatial_disable_guard_lines"] = [getattr(transform.body[i], "lineno", -1) for i in disable_indices]
    for call in calls:
        call_index = _top_level_index(transform, call)
        if call_index is not None and any(call_index < guard_index for guard_index in disable_indices):
            facts["weed_call_precedes_spatial_disable_return"] = True
            break
    return facts


def _class_field_names(cls: ast.ClassDef | None) -> set[str]:
    if cls is None:
        return set()
    names: set[str] = set()
    for stmt in cls.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            names.add(stmt.target.id)
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def _symbolically_references_bit(node: ast.AST, bit: str) -> bool:
    for child in ast.walk(node):
        path = _attr_path(child) if isinstance(child, ast.Attribute) else None
        if path and path[-1] == bit:
            return True
        if isinstance(child, ast.Subscript):
            key = child.slice
            if isinstance(key, ast.Constant) and key.value == bit:
                return True
    return False


def analyze_runtime(source: bytes) -> dict[str, Any]:
    facts: dict[str, Any] = {
        "parse_ok": False,
        "features_class_found": False,
        "features_declares_weed_bit": False,
        "spatialtempo_call_count": 0,
        "spatialtempo_call_lines": [],
        "weed_keyword_call_count": 0,
        "symbolic_weed_keyword_call_count": 0,
        "all_spatialtempo_calls_wire_weed_bit": False,
        "errors": [],
    }
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as exc:
        facts["errors"].append(f"runtime source is not UTF-8: {exc}")
        return facts
    try:
        module = ast.parse(text, filename="titan_runtime.py")
    except SyntaxError as exc:
        facts["errors"].append(f"runtime source parse failure: {exc.msg} at {exc.lineno}:{exc.offset}")
        return facts
    facts["parse_ok"] = True
    features = _find_class(module, "Features")
    facts["features_class_found"] = features is not None
    facts["features_declares_weed_bit"] = "weed_continuation" in _class_field_names(features)

    calls: list[ast.Call] = []
    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        path = _attr_path(node.func) if isinstance(node.func, ast.Attribute) else None
        name = node.func.id if isinstance(node.func, ast.Name) else (path[-1] if path else None)
        if name == "SpatialTempo":
            calls.append(node)
    facts["spatialtempo_call_count"] = len(calls)
    facts["spatialtempo_call_lines"] = sorted(getattr(call, "lineno", -1) for call in calls)
    keyword_count = 0
    symbolic_count = 0
    for call in calls:
        keyword = next((kw for kw in call.keywords if kw.arg == "weed_continuation"), None)
        if keyword is not None:
            keyword_count += 1
            if _symbolically_references_bit(keyword.value, "weed_continuation"):
                symbolic_count += 1
    facts["weed_keyword_call_count"] = keyword_count
    facts["symbolic_weed_keyword_call_count"] = symbolic_count
    facts["all_spatialtempo_calls_wire_weed_bit"] = bool(calls) and symbolic_count == len(calls)
    if not calls:
        facts["errors"].append("SpatialTempo construction missing")
    return facts
