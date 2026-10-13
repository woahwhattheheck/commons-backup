#!/usr/bin/env python3
"""Support-only E184 topology adapter for the 12a3 checker chassis.

Production integration MUST supply the checker-owned `_bindings`,
`_final_function`, `_final_class`, `_class_methods`, `_function_local_names`,
and `_live_nodes_block`.  This donor deliberately does not own liveness.
"""
from __future__ import annotations

import ast
import re
from collections.abc import Callable, Iterable

_PARENT = re.compile(r"^_(?:V[0-9A-Z]+|SALE)_PARENT$")
_FN = (ast.FunctionDef, ast.AsyncFunctionDef)


class E184ProofError(ValueError):
    pass


def _req(cond: object, msg: str) -> None:
    if not cond:
        raise E184ProofError(msg)


class _LiveExprCalls(ast.NodeVisitor):
    """Collect calls in one live statement without stealing statement liveness.

    Child statements are never traversed here: the checker-owned live-node walker
    decides which statements execute. Nested lexical scopes are pruned. Generator
    construction evaluates only its first iterable eagerly; elt/filters/later
    iterators remain deferred until iteration and cannot certify a bridge edge.
    """

    def __init__(self) -> None:
        self.calls: list[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> None:
        self.calls.append(node)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        if node.generators:
            self.visit(node.generators[0].iter)

    # Eager comprehensions have their own binding scopes. Canonical bridge edges
    # do not use them, so refusing them is safer than guessing through shadowing.
    def visit_ListComp(self, node: ast.ListComp) -> None:
        return

    def visit_SetComp(self, node: ast.SetComp) -> None:
        return

    def visit_DictComp(self, node: ast.DictComp) -> None:
        return

    def generic_visit(self, node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.stmt):
                continue
            self.visit(child)


def _live_calls(fn: ast.FunctionDef | ast.AsyncFunctionDef,
                live_nodes_block: Callable[[Iterable[ast.stmt]], Iterable[ast.AST]]) -> list[ast.Call]:
    """Use checker-owned statement liveness, with scope/deferred-expression pruning."""
    out: list[ast.Call] = []
    seen: set[int] = set()
    for node in live_nodes_block(fn.body):
        if not isinstance(node, ast.stmt):
            continue
        visitor = _LiveExprCalls()
        visitor.visit(node)
        for call in visitor.calls:
            if id(call) not in seen:
                seen.add(id(call))
                out.append(call)
    return out


def _name_calls(fn: ast.FunctionDef | ast.AsyncFunctionDef, name: str,
                live_nodes_block, function_local_names) -> list[ast.Call]:
    if name in function_local_names(fn):
        return []
    return [c for c in _live_calls(fn, live_nodes_block)
            if isinstance(c.func, ast.Name) and c.func.id == name]


def _exact_policy_return(fn: ast.FunctionDef | ast.AsyncFunctionDef,
                         live_nodes_block) -> bool:
    hits = []
    for node in live_nodes_block(fn.body):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not (isinstance(call.func, ast.Attribute) and call.func.attr == "act"
                and isinstance(call.func.value, ast.Name) and call.func.value.id == "_POLICY"
                and len(call.args) == 1 and not call.keywords
                and isinstance(call.args[0], ast.Name) and call.args[0].id == "observation"):
            continue
        hits.append(node)
    return len(hits) == 1


def _exact_native_delegate_prefix(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    if not body or not isinstance(body[0], ast.If):
        return False
    gate = body[0]
    test = gate.test
    if not (isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name) and test.left.id == "step"
            and len(test.ops) == 1 and isinstance(test.ops[0], ast.Lt)
            and len(test.comparators) == 1
            and isinstance(test.comparators[0], ast.Name)
            and test.comparators[0].id == "ADVANCE_START"
            and not gate.orelse and len(gate.body) == 1):
        return False
    ret = gate.body[0]
    if not isinstance(ret, ast.Return) or not isinstance(ret.value, ast.Call):
        return False
    call = ret.value
    return (isinstance(call.func, ast.Name) and call.func.id == "_SALE_NATIVE_ADVANCE"
            and not call.keywords
            and [a.id if isinstance(a, ast.Name) else None for a in call.args]
                == ["action", "view", "state", "tape", "step"])


def _capture_native_advance(tree: ast.Module, bindings_fn) -> tuple[ast.AST, ast.AST]:
    """Bind `_SALE_NATIVE_ADVANCE` to the unique live pre-E184 advance_sales def."""
    captures: list[tuple[int, ast.Assign]] = []
    for i, stmt in enumerate(tree.body):
        if isinstance(stmt, ast.Assign):
            target_names = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
            if "_SALE_NATIVE_ADVANCE" in target_names:
                captures.append((i, stmt))
        elif isinstance(stmt, (ast.AnnAssign, ast.AugAssign, ast.Delete, ast.Import, ast.ImportFrom,
                               ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith,
                               ast.Try, getattr(ast, "TryStar", ast.Try), ast.Match)):
            # Let the checker binding model invalidate ambiguous final state; exact capture
            # syntax below is still required, so no compound form can become authority.
            pass
    _req(len(captures) == 1, "E184: expected one exact _SALE_NATIVE_ADVANCE capture")
    index, stmt = captures[0]
    _req(len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name)
         and stmt.targets[0].id == "_SALE_NATIVE_ADVANCE"
         and isinstance(stmt.value, ast.Name) and stmt.value.id == "advance_sales",
         "E184: native advance capture must be exact _SALE_NATIVE_ADVANCE = advance_sales")

    before = bindings_fn(tree.body[:index]).get("advance_sales")
    final_bindings = bindings_fn(tree.body)
    captured = final_bindings.get("_SALE_NATIVE_ADVANCE")
    final = final_bindings.get("advance_sales")
    _req(isinstance(before, _FN), "E184: capture has no unambiguous pre-E184 advance_sales")
    _req(captured is before, "E184: native alias does not preserve capture-time advance_sales identity")
    _req(isinstance(final, _FN) and final is not before,
         "E184: final advance_sales must be a distinct post-capture definition")
    _req(getattr(final, "lineno", 0) > getattr(stmt, "lineno", 0) > getattr(before, "lineno", 0),
         "E184: advance_sales capture/redefinition source order is broken")
    return before, final


def e184_policy_roots_12a3(
    tree: ast.Module,
    *,
    bindings_fn,
    final_function_fn,
    final_class_fn,
    class_methods_fn,
    function_local_names,
    live_nodes_block,
) -> tuple[ast.AST, ast.AST]:
    """Return authenticated extra positive-seam roots: Policy.act + native advance_sales.

    This function proves only source-order identity/topology. The caller must keep
    12a3's own liveness/outcome engine and use the returned roots only as additional
    production-reachable surfaces for matching positive seams.
    """
    module = bindings_fn(tree.body)
    v3 = final_function_fn(tree, "v3_agent")
    core = final_function_fn(tree, "_v3_core")
    stack = final_function_fn(tree, "_v3_stack")

    _req(len(_name_calls(v3, "_v3_core", live_nodes_block, function_local_names)) == 1,
         "E184: v3_agent must have exactly one live global _v3_core edge")
    _req(len(_name_calls(core, "_v3_stack", live_nodes_block, function_local_names)) == 1,
         "E184: _v3_core must have exactly one live global _v3_stack edge")
    _req(len(_name_calls(stack, "POLICY_AGENT", live_nodes_block, function_local_names)) == 1,
         "E184: _v3_stack must have exactly one live global POLICY_AGENT edge")

    policy_agent = module.get("POLICY_AGENT")
    _req(isinstance(policy_agent, _FN), "E184: POLICY_AGENT is not an unambiguous captured function")

    parent_names = {name for name, value in module.items()
                    if _PARENT.fullmatch(name) and isinstance(value, _FN)}
    current = policy_agent
    seen: set[int] = set()
    while not _exact_policy_return(current, live_nodes_block):
        _req(id(current) not in seen, "E184: generated parent chain cycle")
        seen.add(id(current))
        locals_ = function_local_names(current)
        calls = [c for c in _live_calls(current, live_nodes_block)
                 if isinstance(c.func, ast.Name) and c.func.id in parent_names
                 and c.func.id not in locals_]
        names = {c.func.id for c in calls}
        _req(len(calls) == 1 and len(names) == 1,
             f"E184: {current.name} must have exactly one live generated-parent edge")
        parent_name = next(iter(names))
        target = module.get(parent_name)
        _req(isinstance(target, _FN) and target is not current,
             f"E184: {parent_name} does not resolve to captured parent function identity")
        current = target
    original_agent = current

    policy_cls = final_class_fn(tree, "Policy")
    methods = class_methods_fn(policy_cls)
    act = methods.get("act")
    _req(isinstance(act, _FN) and not act.decorator_list,
         "E184: Policy.act must be one live undecorated method")
    _req(len(_name_calls(act, "advance_sales", live_nodes_block, function_local_names)) == 1,
         "E184: Policy.act must have exactly one live global advance_sales edge")

    native, final_advance = _capture_native_advance(tree, bindings_fn)
    _req(final_function_fn(tree, "advance_sales") is final_advance,
         "E184: final advance_sales identity drift")
    _req(_exact_native_delegate_prefix(final_advance),
         "E184: final advance_sales lacks exact pre-ADVANCE_START native delegation prefix")

    # The oldest captured agent must actually be the Policy bridge, not merely a
    # wrapper whose parent chain happened to terminate for another reason.
    _req(_exact_policy_return(original_agent, live_nodes_block),
         "E184: generated parent chain does not terminate at _POLICY.act(observation)")
    return act, native
