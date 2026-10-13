# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import ast
from typing import Iterable, Mapping, Sequence

def _attr_path(node: ast.AST) -> tuple[str, ...] | None:
    parts: list[str] = []
    cursor: ast.AST = node
    while isinstance(cursor, ast.Attribute):
        parts.append(cursor.attr)
        cursor = cursor.value
    if isinstance(cursor, ast.Name):
        parts.append(cursor.id)
        return tuple(reversed(parts))
    return None


def _is_attr(node: ast.AST, terminal: str) -> bool:
    path = _attr_path(node)
    return bool(path and path[-1] == terminal)


def _is_true(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _is_false(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def _comparison_implies(node: ast.Compare, bit: str, value: bool) -> bool:
    if len(node.ops) != 1 or len(node.comparators) != 1:
        return False
    left, right = node.left, node.comparators[0]
    op = node.ops[0]

    def side_pair(a: ast.AST, b: ast.AST) -> bool:
        return _is_attr(a, bit) and (_is_true(b) if value else _is_false(b))

    equal = isinstance(op, (ast.Eq, ast.Is))
    unequal = isinstance(op, (ast.NotEq, ast.IsNot))
    if equal:
        return side_pair(left, right) or side_pair(right, left)
    if unequal:
        opposite = not value
        return (
            _is_attr(left, bit) and (_is_true(right) if opposite else _is_false(right))
        ) or (
            _is_attr(right, bit) and (_is_true(left) if opposite else _is_false(left))
        )
    return False


def implies_bit(node: ast.AST, bit: str, value: bool) -> bool:
    """Return whether truth of *node* guarantees ``bit is value``.

    This intentionally accepts only simple, auditable Boolean forms.  Unknown
    forms fail closed rather than being treated as a proof.
    """

    if _is_attr(node, bit):
        return value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return implies_bit(node.operand, bit, not value)
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            # Every child is true, so one proving the bit is enough.
            return any(implies_bit(v, bit, value) for v in node.values)
        if isinstance(node.op, ast.Or):
            # Any child may be the true branch, so every branch must prove it.
            return bool(node.values) and all(implies_bit(v, bit, value) for v in node.values)
    if isinstance(node, ast.Compare):
        return _comparison_implies(node, bit, value)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "bool":
        return len(node.args) == 1 and implies_bit(node.args[0], bit, value)
    return False


def _contains_call(node: ast.AST, method: str) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
            if child.func.attr == method:
                return True
    return False


def _contains_return(node: ast.AST) -> bool:
    return any(isinstance(child, ast.Return) for child in ast.walk(node))


def _find_class(module: ast.Module, name: str) -> ast.ClassDef | None:
    return next(
        (node for node in module.body if isinstance(node, ast.ClassDef) and node.name == name),
        None,
    )


def _find_method(cls: ast.ClassDef | None, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    if cls is None:
        return None
    return next(
        (
            node
            for node in cls.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        ),
        None,
    )


def _function_arg_names(fn: ast.FunctionDef | ast.AsyncFunctionDef | None) -> set[str]:
    if fn is None:
        return set()
    args = [*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs]
    if fn.args.vararg:
        args.append(fn.args.vararg)
    if fn.args.kwarg:
        args.append(fn.args.kwarg)
    return {arg.arg for arg in args}


def _stores_self_attribute(fn: ast.AST | None, name: str) -> bool:
    if fn is None:
        return False
    for node in ast.walk(fn):
        targets: list[ast.AST] = []
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            if isinstance(node, ast.Assign):
                targets.extend(node.targets)
            else:
                targets.append(node.target)
        for target in targets:
            for item in ast.walk(target):
                if isinstance(item, ast.Attribute) and _attr_path(item) == ("self", name):
                    return True
    return False


def _stores_self_attribute_from_symbol(
    fn: ast.FunctionDef | ast.AsyncFunctionDef | None, name: str
) -> bool:
    """Prove ``self.<name>`` receives a value derived from argument ``name``."""

    if fn is None or name not in _function_arg_names(fn):
        return False
    for node in ast.walk(fn):
        targets: list[ast.AST] = []
        value: ast.AST | None = None
        if isinstance(node, ast.Assign):
            targets.extend(node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets.append(node.target)
            value = node.value
        if value is None:
            continue
        target_matches = any(
            isinstance(item, ast.Attribute) and _attr_path(item) == ("self", name)
            for target in targets
            for item in ast.walk(target)
        )
        if target_matches and any(
            isinstance(item, ast.Name) and item.id == name for item in ast.walk(value)
        ):
            return True
    return False


def _top_level_index(fn: ast.FunctionDef | ast.AsyncFunctionDef, node: ast.AST) -> int | None:
    for index, stmt in enumerate(fn.body):
        if stmt is node or any(desc is node for desc in ast.walk(stmt)):
            return index
    return None


def _ancestor_map(root: ast.AST) -> dict[ast.AST, ast.AST]:
    result: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(root):
        for child in ast.iter_child_nodes(parent):
            result[child] = parent
    return result


def _node_is_within(node: ast.AST, candidates: Sequence[ast.stmt]) -> bool:
    return any(candidate is node or any(desc is node for desc in ast.walk(candidate)) for candidate in candidates)


def _call_guarded_by_bit(
    call: ast.Call,
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    parents: Mapping[ast.AST, ast.AST],
    bit: str,
) -> bool:
    cursor: ast.AST = call
    while cursor in parents and parents[cursor] is not fn:
        parent = parents[cursor]
        if isinstance(parent, ast.If):
            if cursor is parent.test or any(desc is cursor for desc in ast.walk(parent.test)):
                if implies_bit(parent.test, bit, True):
                    return True
            elif _node_is_within(cursor, parent.body) and implies_bit(parent.test, bit, True):
                return True
            # Calls in ``else`` are deliberately not inferred from the inverse.
        cursor = parent

    call_index = _top_level_index(fn, call)
    if call_index is None:
        return False
    for stmt in fn.body[:call_index]:
        if not isinstance(stmt, ast.If):
            continue
        if implies_bit(stmt.test, bit, False) and _contains_return(ast.Module(body=stmt.body, type_ignores=[])):
            return True
    return False


def implies_any_bit_true(node: ast.AST, bits: Iterable[str]) -> bool:
    """Return whether truth of *node* guarantees at least one named bit is true."""

    names = tuple(bits)
    if any(_is_attr(node, bit) for bit in names):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return False
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return any(implies_any_bit_true(value, names) for value in node.values)
        if isinstance(node.op, ast.Or):
            return bool(node.values) and all(
                implies_any_bit_true(value, names) for value in node.values
            )
    if isinstance(node, ast.Compare):
        return any(_comparison_implies(node, bit, True) for bit in names)
    return False


def _call_guarded_by_any_bit(
    call: ast.Call,
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    parents: Mapping[ast.AST, ast.AST],
    bits: Iterable[str],
) -> bool:
    names = tuple(bits)
    cursor: ast.AST = call
    while cursor in parents and parents[cursor] is not fn:
        parent = parents[cursor]
        if isinstance(parent, ast.If):
            if cursor is parent.test or any(desc is cursor for desc in ast.walk(parent.test)):
                if implies_any_bit_true(parent.test, names):
                    return True
            elif _node_is_within(cursor, parent.body) and implies_any_bit_true(parent.test, names):
                return True
        cursor = parent

    call_index = _top_level_index(fn, call)
    if call_index is None:
        return False
    for stmt in fn.body[:call_index]:
        if not isinstance(stmt, ast.If):
            continue
        if (
            all(implies_bit(stmt.test, bit, False) for bit in names)
            and _contains_return(ast.Module(body=stmt.body, type_ignores=[]))
        ):
            return True
    return False


def _spatial_disable_guard_indices(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[int]:
    indices: list[int] = []
    for index, stmt in enumerate(fn.body):
        if not isinstance(stmt, ast.If) or not _contains_return(ast.Module(body=stmt.body, type_ignores=[])):
            continue
        # The guard is recognized only when the true branch proves both bits off.
        if implies_bit(stmt.test, "pathing", False) and implies_bit(stmt.test, "tempo", False):
            indices.append(index)
    return indices
