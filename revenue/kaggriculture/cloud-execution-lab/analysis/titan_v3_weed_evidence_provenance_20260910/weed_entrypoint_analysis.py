# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import ast
from typing import Any

from weed_ast import _attr_path, _function_arg_names

def _find_function(
    module: ast.Module, name: str
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    return next(
        (
            node
            for node in module.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        ),
        None,
    )


def _call_terminal_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        path = _attr_path(call.func)
        return path[-1] if path else call.func.attr
    return None


def _references_name(node: ast.AST, name: str) -> bool:
    return any(isinstance(child, ast.Name) and child.id == name for child in ast.walk(node))


def _contains_string(node: ast.AST, value: str) -> bool:
    return any(
        isinstance(child, ast.Constant) and child.value == value for child in ast.walk(node)
    )


def _contains_call_named(node: ast.AST, name: str) -> bool:
    return any(
        isinstance(child, ast.Call) and _call_terminal_name(child) == name
        for child in ast.walk(node)
    )


def _contains_call_path(node: ast.AST, path: tuple[str, ...]) -> bool:
    return any(
        isinstance(child, ast.Call) and _attr_path(child.func) == path
        for child in ast.walk(node)
    )


def _root_name(node: ast.AST) -> str | None:
    cursor = node
    while isinstance(cursor, (ast.Attribute, ast.Subscript)):
        cursor = cursor.value
    return cursor.id if isinstance(cursor, ast.Name) else None


def _imports_json(scope: ast.AST) -> bool:
    for node in ast.walk(scope):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "json" and alias.asname in (None, "json"):
                    return True
    return False


def _mutation_lines(fn: ast.AST | None, name: str) -> list[int]:
    """Find visible rebinding or in-place mutation of a bound mapping.

    The proof deliberately recognizes only an untouched mapping. Passing the
    mapping through an arbitrary helper would not establish byte-equivalent
    feature data and is therefore rejected elsewhere as a missing direct edge.
    """

    if fn is None:
        return []
    mutators = {
        "clear",
        "pop",
        "popitem",
        "setdefault",
        "update",
        "__setitem__",
        "__delitem__",
        "__ior__",
    }
    lines: set[int] = set()
    for node in ast.walk(fn):
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets.extend(node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets.append(node.target)
        elif isinstance(node, ast.NamedExpr):
            targets.append(node.target)
        elif isinstance(node, ast.Delete):
            targets.extend(node.targets)
        for target in targets:
            if _root_name(target) == name:
                lines.add(getattr(node, "lineno", -1))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in mutators
            and _root_name(node.func.value) == name
        ):
            lines.add(getattr(node, "lineno", -1))
    return sorted(lines)


def _assigned_value(node: ast.AST, name: str) -> ast.AST | None:
    if isinstance(node, ast.Assign):
        if any(
            isinstance(child, ast.Name) and child.id == name
            for target in node.targets
            for child in ast.walk(target)
        ):
            return node.value
    elif isinstance(node, ast.AnnAssign):
        if any(
            isinstance(child, ast.Name) and child.id == name for child in ast.walk(node.target)
        ):
            return node.value
    elif isinstance(node, ast.NamedExpr):
        if isinstance(node.target, ast.Name) and node.target.id == name:
            return node.value
    return None


def analyze_entrypoint(source: bytes) -> dict[str, Any]:
    """Prove untouched bound JSON reaches ``Features(**feature_data)``."""

    facts: dict[str, Any] = {
        "parse_ok": False,
        "json_import_found": False,
        "json_rebinding_lines": [],
        "new_instance_found": False,
        "new_instance_declares_feature_data": False,
        "new_instance_feature_data_mutation_lines": [],
        "features_call_count": 0,
        "expanded_feature_data_call_count": 0,
        "all_features_calls_expand_feature_data": False,
        "agent_found": False,
        "feature_data_assignment_count": 0,
        "feature_data_mutation_lines": [],
        "config_loader_assignment_count": 0,
        "config_loader_lines": [],
        "new_instance_call_count": 0,
        "new_instance_forward_call_count": 0,
        "new_instance_forward_lines": [],
        "all_new_instance_calls_forward_feature_data": False,
        "forwarding_occurs_after_config_load": False,
        "end_to_end_config_to_features": False,
        "errors": [],
    }
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as exc:
        facts["errors"].append(f"entrypoint source is not UTF-8: {exc}")
        return facts
    try:
        module = ast.parse(text, filename="main.py")
    except SyntaxError as exc:
        facts["errors"].append(
            f"entrypoint source parse failure: {exc.msg} at {exc.lineno}:{exc.offset}"
        )
        return facts
    facts["parse_ok"] = True
    facts["json_import_found"] = _imports_json(module)
    facts["json_rebinding_lines"] = _mutation_lines(module, "json")

    new_instance = _find_function(module, "_new_instance")
    facts["new_instance_found"] = new_instance is not None
    facts["new_instance_declares_feature_data"] = (
        "feature_data" in _function_arg_names(new_instance)
    )
    new_instance_mutations = _mutation_lines(new_instance, "feature_data")
    facts["new_instance_feature_data_mutation_lines"] = new_instance_mutations
    feature_calls = (
        [
            node
            for node in ast.walk(new_instance)
            if isinstance(node, ast.Call) and _call_terminal_name(node) == "Features"
        ]
        if new_instance is not None
        else []
    )
    facts["features_call_count"] = len(feature_calls)
    expanded_calls = [
        call
        for call in feature_calls
        if any(
            keyword.arg is None
            and isinstance(keyword.value, ast.Name)
            and keyword.value.id == "feature_data"
            for keyword in call.keywords
        )
    ]
    facts["expanded_feature_data_call_count"] = len(expanded_calls)
    facts["all_features_calls_expand_feature_data"] = bool(feature_calls) and len(
        expanded_calls
    ) == len(feature_calls)

    agent = _find_function(module, "agent")
    facts["agent_found"] = agent is not None
    feature_assignments: list[ast.AST] = []
    config_assignments: list[ast.AST] = []
    new_instance_calls: list[ast.Call] = []
    forward_calls: list[ast.Call] = []
    if agent is not None:
        for node in ast.walk(agent):
            assigned = _assigned_value(node, "feature_data")
            if assigned is not None:
                feature_assignments.append(node)
                if (
                    _contains_string(assigned, "TITAN-CONFIG.json")
                    and _contains_call_path(assigned, ("json", "loads"))
                    and _contains_call_named(assigned, "read_text")
                ):
                    config_assignments.append(node)
            if isinstance(node, ast.Call) and _call_terminal_name(node) == "_new_instance":
                new_instance_calls.append(node)
                values = [*node.args, *(kw.value for kw in node.keywords)]
                if any(
                    isinstance(value, ast.Name) and value.id == "feature_data"
                    for value in values
                ):
                    forward_calls.append(node)
    mutations = _mutation_lines(agent, "feature_data")
    # The one loader assignment is an expected binding, not post-load drift.
    loader_lines = {getattr(node, "lineno", -1) for node in config_assignments}
    post_load_mutations = [line for line in mutations if line not in loader_lines]
    facts["feature_data_assignment_count"] = len(feature_assignments)
    facts["feature_data_mutation_lines"] = post_load_mutations
    facts["config_loader_assignment_count"] = len(config_assignments)
    facts["config_loader_lines"] = sorted(loader_lines)
    facts["new_instance_call_count"] = len(new_instance_calls)
    facts["new_instance_forward_call_count"] = len(forward_calls)
    forward_lines = sorted(getattr(node, "lineno", -1) for node in forward_calls)
    facts["new_instance_forward_lines"] = forward_lines
    facts["all_new_instance_calls_forward_feature_data"] = bool(new_instance_calls) and len(
        forward_calls
    ) == len(new_instance_calls)
    facts["forwarding_occurs_after_config_load"] = bool(loader_lines and forward_lines) and (
        min(forward_lines) > max(loader_lines)
    )

    facts["end_to_end_config_to_features"] = bool(
        facts["json_import_found"]
        and not facts["json_rebinding_lines"]
        and facts["new_instance_declares_feature_data"]
        and not new_instance_mutations
        and facts["all_features_calls_expand_feature_data"]
        and len(feature_assignments) == 1
        and len(config_assignments) == 1
        and not post_load_mutations
        and facts["all_new_instance_calls_forward_feature_data"]
        and facts["forwarding_occurs_after_config_load"]
    )
    if not facts["json_import_found"]:
        facts["errors"].append("an unaliased json module import is required")
    if facts["json_rebinding_lines"]:
        facts["errors"].append("json is rebound; json.loads identity is not proven")
    if new_instance is None:
        facts["errors"].append("_new_instance function missing")
    if not feature_calls:
        facts["errors"].append("Features construction missing from _new_instance")
    if new_instance_mutations:
        facts["errors"].append(
            "_new_instance mutates or rebinds feature_data before Features expansion"
        )
    if agent is None:
        facts["errors"].append("agent function missing")
    if len(feature_assignments) != 1:
        facts["errors"].append(
            "feature_data must have exactly one assignment in agent"
        )
    if len(config_assignments) != 1:
        facts["errors"].append(
            "feature_data must have one visible TITAN-CONFIG.json json.loads/read_text assignment"
        )
    if post_load_mutations:
        facts["errors"].append(
            "feature_data is mutated or rebound after the config load"
        )
    if not new_instance_calls:
        facts["errors"].append("agent does not call _new_instance")
    elif not facts["all_new_instance_calls_forward_feature_data"]:
        facts["errors"].append(
            "every _new_instance call must receive feature_data directly"
        )
    if forward_calls and not facts["forwarding_occurs_after_config_load"]:
        facts["errors"].append(
            "feature_data forwarding does not occur after the config load"
        )
    return facts
