# SPDX-License-Identifier: Apache-2.0
"""Static, fail-closed R04 route forcing for the TITAN V5 route matrices.

The caller must first reproduce the exact production-v3 package. This module
changes only one authenticated R04 plan-selection RHS: either the observation-
selected step-144 SHOP_PLANS assignment or the hard terminal step-648 plan-2
assignment. The other selection boundary remains source-identical.
"""
from __future__ import annotations

import ast

ROUTE_STEP = 144
FINAL_PLAN_STEP = 648
TERMINAL_PLAN = 2
PLAN_COUNT = 13
SUPPORTED_SELECTION_STEPS = (ROUTE_STEP, FINAL_PLAN_STEP)


def _plain_int(value, name):
    if type(value) is not int:
        raise ValueError(f"{name} must be a plain int")
    return value


def _name_constant(tree, name, expected):
    matches = []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == name:
            matches.append(node.value)
    if len(matches) != 1:
        raise ValueError(f"expected one {name} assignment")
    value = matches[0]
    if not isinstance(value, ast.Constant) or type(value.value) is not int:
        raise ValueError(f"{name} must be a literal plain int")
    if value.value != expected:
        raise ValueError(f"unexpected {name}: {value.value!r}")


def _plan_target(node):
    return isinstance(node, ast.Attribute) and node.attr == "plan"


def _shop_lookup(node):
    if isinstance(node, ast.Subscript):
        return isinstance(node.value, ast.Name) and node.value.id == "SHOP_PLANS"
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "get"
        and isinstance(func.value, ast.Name)
        and func.value.id == "SHOP_PLANS"
    )


def _if_guard_uses(node, parent, name):
    current = node
    while current in parent:
        current = parent[current]
        if isinstance(current, ast.If):
            return any(
                isinstance(child, ast.Name) and child.id == name
                for child in ast.walk(current.test)
            )
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            break
    return False


def _parent_index(tree):
    parent = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node
    return parent


def _plan_assignments(tree):
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and _plan_target(node.targets[0])
    ]


def _contract(tree):
    _name_constant(tree, "ROUTE_STEP", ROUTE_STEP)
    _name_constant(tree, "FINAL_PLAN_STEP", FINAL_PLAN_STEP)
    parent = _parent_index(tree)
    assignments = _plan_assignments(tree)

    route = [
        node for node in assignments
        if _shop_lookup(node.value)
        and _if_guard_uses(node, parent, "ROUTE_STEP")
    ]
    all_lookups = [node for node in assignments if _shop_lookup(node.value)]
    if len(route) != 1 or len(all_lookups) != 1:
        raise ValueError("expected one step-144 SHOP_PLANS assignment")

    terminal = [
        node for node in assignments
        if isinstance(node.value, ast.Constant)
        and type(node.value.value) is int
        and node.value.value == TERMINAL_PLAN
        and _if_guard_uses(node, parent, "FINAL_PLAN_STEP")
    ]
    if len(terminal) != 1:
        raise ValueError("expected one terminal plan-2 assignment")
    return route[0], terminal[0]


def _byte_offsets(source, node):
    if node.end_lineno is None or node.end_col_offset is None:
        raise ValueError("Python AST is missing end positions")
    if node.lineno != node.end_lineno:
        raise ValueError("plan expression must remain one line")
    lines = source.splitlines(keepends=True)
    if node.lineno < 1 or node.lineno > len(lines):
        raise ValueError("invalid plan expression line")
    prefix = b"".join(lines[: node.lineno - 1])
    line = lines[node.lineno - 1]
    start = len(prefix) + node.col_offset
    end = len(prefix) + node.end_col_offset
    if start < len(prefix) or end > len(prefix) + len(line) or start >= end:
        raise ValueError("invalid plan expression byte span")
    return start, end


def _constant_under(assignments, parent, guard, value):
    return [
        node for node in assignments
        if isinstance(node.value, ast.Constant)
        and type(node.value.value) is int
        and node.value.value == value
        and _if_guard_uses(node, parent, guard)
    ]


def force_plan_at(router_source, plan_index, selection_step):
    """Return router bytes with only one authenticated plan-selection RHS forced."""
    plan_index = _plain_int(plan_index, "plan_index")
    selection_step = _plain_int(selection_step, "selection_step")
    if plan_index < 0 or plan_index >= PLAN_COUNT:
        raise ValueError(f"plan_index must be in 0..{PLAN_COUNT - 1}")
    if selection_step not in SUPPORTED_SELECTION_STEPS:
        raise ValueError(
            f"selection_step must be one of {SUPPORTED_SELECTION_STEPS!r}"
        )
    if not isinstance(router_source, (bytes, bytearray)):
        raise TypeError("router_source must be bytes")
    source = bytes(router_source)
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("router source must be UTF-8") from exc

    tree = ast.parse(text, filename="r04_full_router.py")
    route, terminal = _contract(tree)
    target = route if selection_step == ROUTE_STEP else terminal
    start, end = _byte_offsets(source, target.value)
    replacement = str(plan_index).encode("ascii")
    changed = source[:start] + replacement + source[end:]

    changed_tree = ast.parse(changed.decode("utf-8"), filename="r04_full_router.py")
    _name_constant(changed_tree, "ROUTE_STEP", ROUTE_STEP)
    _name_constant(changed_tree, "FINAL_PLAN_STEP", FINAL_PLAN_STEP)
    changed_parent = _parent_index(changed_tree)
    changed_assignments = _plan_assignments(changed_tree)

    if selection_step == ROUTE_STEP:
        forced = _constant_under(
            changed_assignments, changed_parent, "ROUTE_STEP", plan_index
        )
        if len(forced) != 1:
            raise ValueError("forced route assignment did not survive static verification")
        terminal_after = _constant_under(
            changed_assignments, changed_parent, "FINAL_PLAN_STEP", TERMINAL_PLAN
        )
        if len(terminal_after) != 1:
            raise ValueError("terminal plan-2 assignment drifted")
    else:
        route_after = [
            node for node in changed_assignments
            if _shop_lookup(node.value)
            and _if_guard_uses(node, changed_parent, "ROUTE_STEP")
        ]
        all_lookups = [node for node in changed_assignments if _shop_lookup(node.value)]
        if len(route_after) != 1 or len(all_lookups) != 1:
            raise ValueError("step-144 SHOP_PLANS assignment drifted")
        terminal_after = _constant_under(
            changed_assignments, changed_parent, "FINAL_PLAN_STEP", plan_index
        )
        if len(terminal_after) != 1:
            raise ValueError("forced terminal assignment did not survive static verification")
    return changed


def force_plan(router_source, plan_index):
    """Backward-compatible step-144 route forcing."""
    return force_plan_at(router_source, plan_index, ROUTE_STEP)


def force_terminal_plan(router_source, plan_index):
    """Force only the hard step-648 terminal route selection."""
    return force_plan_at(router_source, plan_index, FINAL_PLAN_STEP)
