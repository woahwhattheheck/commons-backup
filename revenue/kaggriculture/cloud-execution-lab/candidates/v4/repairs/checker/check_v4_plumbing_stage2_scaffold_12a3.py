#!/usr/bin/env python3
"""Fail closed if a TITAN V4 recompose drops or disconnects landed plumbing.

V1 is deliberately bootstrap-only: every V4 key must still materialize OFF.  A later
promotion must evolve this guard explicitly.  The checker recognizes only the narrow
Python shapes emitted by the canonical V3/V4 builders; ambiguous bindings, decorators,
control flow, call provenance, or value flow are rejected rather than guessed through.
"""
from __future__ import annotations

# Direct-script import custody: sys is builtin; remove candidates/v3 before any
# importable stdlib name can be shadowed by a candidate sibling.
import sys as _titan_bootstrap_sys
if _titan_bootstrap_sys.path:
    del _titan_bootstrap_sys.path[0]

import argparse
import ast
import json
from pathlib import Path
from typing import Iterable, Iterator, NoReturn

HERE = Path(__file__).resolve().parent
APPLY_V4 = HERE / "apply_v4.py"
_UNKNOWN = object()
_DEFERRED = (ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_TERMINATORS = (ast.Return, ast.Raise, ast.Break, ast.Continue)


def _fail(message: str) -> NoReturn:
    raise SystemExit(message)


def _require(cond: object, message: str) -> None:
    if not cond:
        _fail(message)


def _literal(node: ast.AST) -> object:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return _UNKNOWN


def _static_truth(node: ast.AST) -> bool | None:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        value = _static_truth(node.operand)
        return None if value is None else not value
    if isinstance(node, ast.BoolOp):
        values = [_static_truth(x) for x in node.values]
        if isinstance(node.op, ast.And):
            if any(v is False for v in values):
                return False
            return True if values and all(v is True for v in values) else None
        if isinstance(node.op, ast.Or):
            if any(v is True for v in values):
                return True
            return False if values and all(v is False for v in values) else None
    if isinstance(node, ast.Compare):
        raw = [node.left, *node.comparators]
        values = [_literal(x) for x in raw]
        if any(v is _UNKNOWN for v in values):
            return None
        left = values[0]
        try:
            for op, right in zip(node.ops, values[1:]):
                if isinstance(op, ast.Eq): ok = left == right
                elif isinstance(op, ast.NotEq): ok = left != right
                elif isinstance(op, ast.Lt): ok = left < right
                elif isinstance(op, ast.LtE): ok = left <= right
                elif isinstance(op, ast.Gt): ok = left > right
                elif isinstance(op, ast.GtE): ok = left >= right
                elif isinstance(op, ast.Is): ok = left is right
                elif isinstance(op, ast.IsNot): ok = left is not right
                elif isinstance(op, ast.In): ok = left in right
                elif isinstance(op, ast.NotIn): ok = left not in right
                else: return None
                if not ok:
                    return False
                left = right
            return True
        except Exception:
            return None
    value = _literal(node)
    if value is _UNKNOWN:
        return None
    try:
        return bool(value)
    except Exception:
        return None


def _target_names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        out: set[str] = set()
        for item in target.elts:
            out.update(_target_names(item))
        return out
    if isinstance(target, ast.Starred):
        return _target_names(target.value)
    return set()


def _pattern_names(pattern: ast.AST) -> set[str]:
    out: set[str] = set()
    if isinstance(pattern, ast.MatchAs):
        if pattern.name:
            out.add(pattern.name)
        if pattern.pattern is not None:
            out.update(_pattern_names(pattern.pattern))
    elif isinstance(pattern, ast.MatchStar):
        if pattern.name:
            out.add(pattern.name)
    elif isinstance(pattern, ast.MatchMapping):
        if pattern.rest:
            out.add(pattern.rest)
        for child in pattern.patterns:
            out.update(_pattern_names(child))
    elif isinstance(pattern, ast.MatchSequence):
        for child in pattern.patterns:
            out.update(_pattern_names(child))
    elif isinstance(pattern, ast.MatchClass):
        for child in (*pattern.patterns, *pattern.kwd_patterns):
            out.update(_pattern_names(child))
    elif isinstance(pattern, ast.MatchOr):
        for child in pattern.patterns:
            out.update(_pattern_names(child))
    return out


def _namedexpr_names(expr: ast.AST) -> set[str]:
    out: set[str] = set()
    def walk(node: ast.AST) -> None:
        if isinstance(node, _DEFERRED):
            return
        if isinstance(node, ast.NamedExpr):
            out.update(_target_names(node.target))
            walk(node.value)
            return
        for child in ast.iter_child_nodes(node):
            walk(child)
    walk(expr)
    return out


def _bound_names_in_statements(statements: Iterable[ast.stmt]) -> set[str]:
    """Lexical bindings, excluding nested defs/classes and comprehension scopes."""
    out: set[str] = set()
    def visit(stmt: ast.stmt) -> None:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(stmt.name)
            for deco in stmt.decorator_list:
                out.update(_namedexpr_names(deco))
            return
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets: out.update(_target_names(target))
            out.update(_namedexpr_names(stmt.value)); return
        if isinstance(stmt, (ast.AnnAssign, ast.AugAssign)):
            out.update(_target_names(stmt.target))
            if getattr(stmt, "value", None) is not None: out.update(_namedexpr_names(stmt.value))
            return
        if isinstance(stmt, ast.Delete):
            for target in stmt.targets: out.update(_target_names(target))
            return
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            for alias in stmt.names: out.add(alias.asname or alias.name.split(".", 1)[0])
            return
        if isinstance(stmt, (ast.For, ast.AsyncFor)):
            out.update(_target_names(stmt.target)); out.update(_namedexpr_names(stmt.iter))
            for child in (*stmt.body, *stmt.orelse): visit(child)
            return
        if isinstance(stmt, ast.If):
            out.update(_namedexpr_names(stmt.test))
            for child in (*stmt.body, *stmt.orelse): visit(child)
            return
        if isinstance(stmt, ast.While):
            out.update(_namedexpr_names(stmt.test))
            for child in (*stmt.body, *stmt.orelse): visit(child)
            return
        if isinstance(stmt, (ast.With, ast.AsyncWith)):
            for item in stmt.items:
                out.update(_namedexpr_names(item.context_expr))
                if item.optional_vars is not None: out.update(_target_names(item.optional_vars))
            for child in stmt.body: visit(child)
            return
        if isinstance(stmt, (ast.Try, getattr(ast, "TryStar", ast.Try))):
            for child in (*stmt.body, *stmt.orelse, *stmt.finalbody): visit(child)
            for handler in stmt.handlers:
                if handler.name: out.add(handler.name)
                if handler.type is not None: out.update(_namedexpr_names(handler.type))
                for child in handler.body: visit(child)
            return
        if isinstance(stmt, ast.Match):
            out.update(_namedexpr_names(stmt.subject))
            for case in stmt.cases:
                out.update(_pattern_names(case.pattern))
                if case.guard is not None: out.update(_namedexpr_names(case.guard))
                for child in case.body: visit(child)
            return
        for child in ast.iter_child_nodes(stmt):
            if isinstance(child, ast.expr): out.update(_namedexpr_names(child))
    for stmt in statements: visit(stmt)
    return out


def _process_bindings(statements: Iterable[ast.stmt], bindings: dict[str, object]) -> None:
    """Final binding model for simple module/class code. Unknown compounds invalidate."""
    for stmt in statements:
        if isinstance(stmt, ast.If):
            truth = _static_truth(stmt.test)
            if truth is True:
                _process_bindings(stmt.body, bindings)
            elif truth is False:
                _process_bindings(stmt.orelse, bindings)
            else:
                for name in _bound_names_in_statements((*stmt.body, *stmt.orelse)):
                    bindings[name] = _UNKNOWN
            for name in _namedexpr_names(stmt.test): bindings[name] = _UNKNOWN
            continue
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bindings[stmt.name] = stmt; continue
        if isinstance(stmt, ast.Assign):
            value: object = stmt.value
            if isinstance(stmt.value, ast.Name) and stmt.value.id in bindings:
                value = bindings[stmt.value.id]
            for target in stmt.targets:
                names = _target_names(target)
                if isinstance(target, ast.Name): bindings[target.id] = value
                else:
                    for name in names: bindings[name] = _UNKNOWN
            for name in _namedexpr_names(stmt.value): bindings[name] = _UNKNOWN
            continue
        if isinstance(stmt, ast.AnnAssign):
            if isinstance(stmt.target, ast.Name) and stmt.value is not None:
                value: object = stmt.value
                if isinstance(stmt.value, ast.Name) and stmt.value.id in bindings: value = bindings[stmt.value.id]
                bindings[stmt.target.id] = value
            else:
                for name in _target_names(stmt.target): bindings[name] = _UNKNOWN
            continue
        if isinstance(stmt, (ast.AugAssign, ast.Delete)):
            targets = (stmt.target,) if isinstance(stmt, ast.AugAssign) else stmt.targets
            for target in targets:
                for name in _target_names(target): bindings[name] = _UNKNOWN
            continue
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            for alias in stmt.names: bindings[alias.asname or alias.name.split(".", 1)[0]] = _UNKNOWN
            continue
        if isinstance(stmt, (ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith,
                             ast.Try, getattr(ast, "TryStar", ast.Try), ast.Match)):
            for name in _bound_names_in_statements((stmt,)): bindings[name] = _UNKNOWN
            continue
        for name in _bound_names_in_statements((stmt,)): bindings[name] = _UNKNOWN


def _bindings(statements: Iterable[ast.stmt]) -> dict[str, object]:
    out: dict[str, object] = {}
    _process_bindings(statements, out)
    return out


def _final_class(tree: ast.Module, name: str) -> ast.ClassDef:
    node = _bindings(tree.body).get(name)
    _require(isinstance(node, ast.ClassDef), f"materialized runtime has no unambiguous live {name} class")
    return node


def _final_function(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    node = _bindings(tree.body).get(name)
    _require(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)), f"no unambiguous live {name}()")
    _require(not node.decorator_list, f"{name}(): decorators are not allowed")
    return node


def _class_methods(cls: ast.ClassDef) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {k: v for k, v in _bindings(cls.body).items()
            if isinstance(v, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _expr_nodes(node: ast.AST) -> Iterator[ast.AST]:
    if isinstance(node, _DEFERRED):
        return
    yield node
    if isinstance(node, ast.BoolOp):
        for value in node.values:
            yield from _expr_nodes(value)
            truth = _static_truth(value)
            if isinstance(node.op, ast.And) and truth is False: break
            if isinstance(node.op, ast.Or) and truth is True: break
        return
    if isinstance(node, ast.IfExp):
        yield from _expr_nodes(node.test)
        truth = _static_truth(node.test)
        if truth is True: yield from _expr_nodes(node.body)
        elif truth is False: yield from _expr_nodes(node.orelse)
        else:
            yield from _expr_nodes(node.body); yield from _expr_nodes(node.orelse)
        return
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, *_DEFERRED)): continue
        yield from _expr_nodes(child)


def _known_empty_iter(node: ast.AST) -> bool:
    value = _literal(node)
    return value is not _UNKNOWN and isinstance(value, (tuple, list, set, frozenset, dict, str, bytes)) and not value


def _ordinary_literal_iter(node: ast.AST) -> bool:
    value = _literal(node)
    return value is not _UNKNOWN and isinstance(value, (tuple, list, set, frozenset, dict, str, bytes))


def _loop_has_break(statements: Iterable[ast.stmt]) -> bool:
    class BreakFinder(ast.NodeVisitor):
        found = False
        def visit_Break(self, node: ast.Break) -> None:
            self.found = True
        def visit_For(self, node: ast.For) -> None:
            return
        def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
            return
        def visit_While(self, node: ast.While) -> None:
            return
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            return
        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            return
        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            return
    finder = BreakFinder()
    for child in statements:
        finder.visit(child)
        if finder.found:
            return True
    return False


def _stmt_definitely_terminates(stmt: ast.stmt) -> bool:
    if isinstance(stmt, _TERMINATORS): return True
    if isinstance(stmt, ast.If):
        truth = _static_truth(stmt.test)
        if truth is True: return _block_definitely_terminates(stmt.body)
        if truth is False: return _block_definitely_terminates(stmt.orelse)
        return bool(stmt.body and stmt.orelse and _block_definitely_terminates(stmt.body)
                    and _block_definitely_terminates(stmt.orelse))
    if isinstance(stmt, ast.While):
        truth = _static_truth(stmt.test)
        if truth is False:
            return _block_definitely_terminates(stmt.orelse)
        if truth is True and not _loop_has_break(stmt.body):
            return True
        return False
    if isinstance(stmt, ast.AsyncFor) and _ordinary_literal_iter(stmt.iter):
        return True  # sync literal has no __aiter__; TypeError occurs before loop/tail
    if isinstance(stmt, (ast.Try, getattr(ast, "TryStar", ast.Try))):
        if _block_definitely_terminates(stmt.finalbody):
            return True
        if not stmt.handlers and _block_definitely_terminates(stmt.body):
            return True
    # With/AsyncWith are intentionally not propagated: __exit__/__aexit__ may
    # suppress a body exception, so a body raise cannot prove the tail dead.
    return False


def _block_definitely_terminates(statements: Iterable[ast.stmt]) -> bool:
    for stmt in statements:
        if _stmt_definitely_terminates(stmt): return True
    return False


def _live_nodes_block(statements: Iterable[ast.stmt]) -> Iterator[ast.AST]:
    """Execution-order conservative walk; dead proof sites are never yielded."""
    for stmt in statements:
        yield stmt
        if isinstance(stmt, ast.If):
            yield from _expr_nodes(stmt.test)
            truth = _static_truth(stmt.test)
            if truth is True: yield from _live_nodes_block(stmt.body)
            elif truth is False: yield from _live_nodes_block(stmt.orelse)
            else:
                yield from _live_nodes_block(stmt.body); yield from _live_nodes_block(stmt.orelse)
        elif isinstance(stmt, ast.While):
            yield from _expr_nodes(stmt.test)
            truth = _static_truth(stmt.test)
            if truth is False: yield from _live_nodes_block(stmt.orelse)
            else:
                yield from _live_nodes_block(stmt.body); yield from _live_nodes_block(stmt.orelse)
        elif isinstance(stmt, ast.For):
            yield from _expr_nodes(stmt.iter)
            if _known_empty_iter(stmt.iter): yield from _live_nodes_block(stmt.orelse)
            else:
                yield from _live_nodes_block(stmt.body); yield from _live_nodes_block(stmt.orelse)
        elif isinstance(stmt, ast.AsyncFor):
            yield from _expr_nodes(stmt.iter)
            if not _ordinary_literal_iter(stmt.iter):
                # We do not use AsyncFor body/else as positive proof: async protocol is opaque.
                pass
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            for item in stmt.items: yield from _expr_nodes(item.context_expr)
            yield from _live_nodes_block(stmt.body)
        elif isinstance(stmt, (ast.Try, getattr(ast, "TryStar", ast.Try))):
            yield from _live_nodes_block(stmt.body)
            # Exception handlers are not positive-proof sites: without exception
            # provenance, a handler may be statically dead for the candidate seam.
            yield from _live_nodes_block(stmt.orelse); yield from _live_nodes_block(stmt.finalbody)
        elif isinstance(stmt, ast.Match):
            yield from _expr_nodes(stmt.subject)
            # Guards/pattern dispatch are not statically exclusive; each case is a possible live path.
            for case in stmt.cases:
                if case.guard is not None: yield from _expr_nodes(case.guard)
                yield from _live_nodes_block(case.body)
        elif isinstance(stmt, (ast.Return, ast.Raise)):
            if isinstance(stmt, ast.Return) and stmt.value is not None: yield from _expr_nodes(stmt.value)
            if isinstance(stmt, ast.Raise):
                if stmt.exc is not None: yield from _expr_nodes(stmt.exc)
                if stmt.cause is not None: yield from _expr_nodes(stmt.cause)
        elif not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for child in ast.iter_child_nodes(stmt):
                if not isinstance(child, ast.stmt): yield from _expr_nodes(child)
        if _stmt_definitely_terminates(stmt): break


def _scope_declarations(fn: ast.FunctionDef | ast.AsyncFunctionDef, kind: type[ast.AST]) -> set[str]:
    """Global/nonlocal declarations in this function only, never nested scopes."""
    out: set[str] = set()

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            return
        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            return
        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            return
        def visit_Global(self, node: ast.Global) -> None:
            if kind is ast.Global:
                out.update(node.names)
        def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
            if kind is ast.Nonlocal:
                out.update(node.names)

    visitor = Visitor()
    for stmt in fn.body:
        visitor.visit(stmt)
    return out


def _function_globals(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    return _scope_declarations(fn, ast.Global)


def _function_nonlocals(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    return _scope_declarations(fn, ast.Nonlocal)


def _function_local_names(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    out = {a.arg for a in (*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs)}
    if fn.args.vararg: out.add(fn.args.vararg.arg)
    if fn.args.kwarg: out.add(fn.args.kwarg.arg)
    out.update(_bound_names_in_statements(fn.body))
    out.difference_update(_function_globals(fn)); out.difference_update(_function_nonlocals(fn))
    return out


def _module_binds(tree: ast.Module, name: str) -> bool:
    return name in _bound_names_in_statements(tree.body)


def _class_binds(cls: ast.ClassDef, name: str) -> bool:
    return name in _bound_names_in_statements(cls.body)


def _builtin_name_unshadowed(tree: ast.Module, fn: ast.FunctionDef | ast.AsyncFunctionDef | None, name: str,
                             cls: ast.ClassDef | None = None) -> bool:
    if _module_binds(tree, name): return False
    if cls is not None and _class_binds(cls, name): return False
    if fn is not None and name in _function_local_names(fn): return False
    return True


def _safe_agent_method_decorator(tree: ast.Module, cls: ast.ClassDef,
                                 fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    if not fn.decorator_list:
        return True
    # Exact canonical generated shape observed in the successful package artifact.
    if fn.name not in {"_seller_state", "_seller_public_observation"} or len(fn.decorator_list) != 1:
        return False
    deco = fn.decorator_list[0]
    return (isinstance(deco, ast.Name) and deco.id == "staticmethod"
            and _builtin_name_unshadowed(tree, fn, "staticmethod", cls))


def _reachable_agent_methods(tree: ast.Module, agent: ast.ClassDef) -> set[ast.FunctionDef | ast.AsyncFunctionDef]:
    methods = _class_methods(agent)
    root = methods.get("act")
    _require(root is not None, "materialized TitanAgent has no live act()")
    reachable: set[ast.FunctionDef | ast.AsyncFunctionDef] = set()
    stack = [root]
    while stack:
        fn = stack.pop()
        if fn in reachable: continue
        _require(_safe_agent_method_decorator(tree, agent, fn),
                 f"reachable TitanAgent method {fn.name} has an untrusted decorator")
        reachable.add(fn)
        for node in _live_nodes_block(fn.body):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute): continue
            owner = node.func.value
            if not (isinstance(owner, ast.Name) and owner.id == "self"): continue
            target = methods.get(node.func.attr)
            if target is not None and target not in reachable: stack.append(target)
    return reachable


def _reachable_top_functions(tree: ast.Module, root_name: str) -> set[ast.FunctionDef | ast.AsyncFunctionDef]:
    module = _bindings(tree.body)
    root = module.get(root_name)
    _require(isinstance(root, (ast.FunctionDef, ast.AsyncFunctionDef)), f"router root {root_name} is not live")
    reachable: set[ast.FunctionDef | ast.AsyncFunctionDef] = set(); stack = [root]
    while stack:
        fn = stack.pop()
        if fn in reachable: continue
        _require(not fn.decorator_list, f"reachable router function {fn.name} may not be decorated")
        reachable.add(fn)
        locals_ = _function_local_names(fn)
        for node in _live_nodes_block(fn.body):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name): continue
            if node.func.id in locals_: continue
            target = module.get(node.func.id)
            if isinstance(target, (ast.FunctionDef, ast.AsyncFunctionDef)) and target not in reachable:
                stack.append(target)
    return reachable


def _is_self_features(node: ast.AST) -> bool:
    return (isinstance(node, ast.Attribute) and node.attr == "features"
            and isinstance(node.value, ast.Name) and node.value.id == "self")


def _is_self_feature(node: ast.AST, key: str) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == key and _is_self_features(node.value)


def _builtin_bool_of(tree: ast.Module, fn: ast.FunctionDef | ast.AsyncFunctionDef,
                     node: ast.AST, value_pred) -> bool:
    if value_pred(node): return True
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "bool"
            and len(node.args) == 1 and not node.keywords and value_pred(node.args[0])
            and _builtin_name_unshadowed(tree, fn, "bool"))


def _requires_flag_true(node: ast.AST, flag: str) -> bool:
    if isinstance(node, ast.Name): return node.id == flag
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not): return False
    if isinstance(node, ast.BoolOp):
        vals = [_requires_flag_true(x, flag) for x in node.values]
        if isinstance(node.op, ast.And): return any(vals)
        if isinstance(node.op, ast.Or): return bool(vals) and all(vals)
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
        left, right, op = node.left, node.comparators[0], node.ops[0]
        if isinstance(left, ast.Name) and left.id == flag and isinstance(right, ast.Constant):
            if isinstance(op, (ast.Is, ast.Eq)) and right.value is True: return True
        if isinstance(right, ast.Name) and right.id == flag and isinstance(left, ast.Constant):
            if isinstance(op, (ast.Is, ast.Eq)) and left.value is True: return True
    return False


def _matching_module_call_effect(node: ast.stmt, module: str) -> bool:
    calls: list[ast.Call] = []
    for child in _live_nodes_block((node,)):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
            if isinstance(child.func.value, ast.Name) and child.func.value.id == module:
                calls.append(child)
    if not calls: return False
    parents = {c: p for p in ast.walk(node) for c in ast.iter_child_nodes(p)}
    for call in calls:
        attr = call.func.attr
        cur: ast.AST = call
        while cur in parents and isinstance(parents[cur], ast.Call) and parents[cur].func is cur:
            cur = parents[cur]
        parent = parents.get(cur)
        if attr.startswith("invalidate_") and isinstance(parent, ast.Expr): return True
        if isinstance(parent, (ast.Assign, ast.AnnAssign, ast.NamedExpr, ast.Return)): return True
    return False


def _block_imports_module(statements: Iterable[ast.stmt], module: str) -> bool:
    for stmt in statements:
        if isinstance(stmt, ast.Import):
            if any(a.name == module and (a.asname is None or a.asname == module) for a in stmt.names): return True
        if isinstance(stmt, ast.If):
            truth = _static_truth(stmt.test)
            branches = [stmt.body] if truth is True else [stmt.orelse] if truth is False else [stmt.body, stmt.orelse]
            if any(_block_imports_module(b, module) for b in branches): return True
    return False


def _router_feature_seam(router: ast.Module, root_name: str, flag: str, module: str) -> bool:
    for fn in _reachable_top_functions(router, root_name):
        for node in _live_nodes_block(fn.body):
            if not isinstance(node, (ast.If, ast.While)): continue
            if _static_truth(node.test) is not None or not _requires_flag_true(node.test, flag): continue
            if not _block_imports_module(node.body, module): continue
            if any(_matching_module_call_effect(stmt, module) for stmt in node.body): return True
    return False


def _is_none_guard(test: ast.AST, name: str) -> bool:
    return (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) and test.left.id == name
            and len(test.ops) == 1 and isinstance(test.ops[0], ast.IsNot)
            and len(test.comparators) == 1 and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value is None)


def _flag_targets(stmt: ast.stmt, flag: str) -> bool:
    if isinstance(stmt, ast.Assign):
        return any(flag in _target_names(t) for t in stmt.targets)
    if isinstance(stmt, (ast.AnnAssign, ast.AugAssign)):
        return flag in _target_names(stmt.target)
    if isinstance(stmt, ast.Delete):
        return any(flag in _target_names(t) for t in stmt.targets)
    return False


def _name_written_in(fn: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> bool:
    # Parameters are not included here; any body-level lexical binding is a rebind.
    return name in _bound_names_in_statements(fn.body)


def _install_setter_ok(router: ast.Module, install: ast.FunctionDef | ast.AsyncFunctionDef,
                       flag: str, suffix: str) -> bool:
    if _name_written_in(install, suffix):
        return False
    writes = [n for n in _live_nodes_block(install.body)
              if isinstance(n, ast.stmt) and _flag_targets(n, flag)]
    if len(writes) != 1:
        return False
    for stmt in install.body:
        if not isinstance(stmt, ast.If) or not _is_none_guard(stmt.test, suffix):
            continue
        if len(stmt.body) != 1:
            return False
        child = stmt.body[0]
        if child is not writes[0] or not isinstance(child, (ast.Assign, ast.AnnAssign)):
            return False
        targets = child.targets if isinstance(child, ast.Assign) else (child.target,)
        if not any(isinstance(t, ast.Name) and t.id == flag for t in targets):
            return False
        value = child.value
        return (value is not None and _builtin_bool_of(
            router, install, value, lambda n: isinstance(n, ast.Name) and n.id == suffix))
    return False


def _global_declared(fn: ast.FunctionDef | ast.AsyncFunctionDef, flag: str) -> bool:
    return any(isinstance(s, ast.Global) and flag in s.names for s in fn.body)


def _install_root(install: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    returns = [n for n in _live_nodes_block(install.body) if isinstance(n, ast.Return)]
    if not returns: return None
    names = {r.value.id for r in returns if isinstance(r.value, ast.Name)}
    if len(names) != 1 or len(names) != len({r.value.id if isinstance(r.value, ast.Name) else None for r in returns}):
        return None
    root = next(iter(names))
    if root in _function_local_names(install):
        return None
    return root


def _branch_constraints(node: ast.AST, parent: dict[ast.AST, ast.AST]) -> dict[int, str]:
    """Mutually-exclusive path labels from the function root to *node*."""
    out: dict[int, str] = {}
    cur: ast.AST = node
    while cur in parent:
        p = parent[cur]
        if isinstance(p, ast.If):
            if cur in p.body:
                out[id(p)] = "body"
            elif cur in p.orelse:
                out[id(p)] = "else"
        elif isinstance(p, ast.Match):
            for idx, case in enumerate(p.cases):
                if cur is case or (isinstance(cur, ast.stmt) and cur in case.body):
                    out[id(p)] = f"case{idx}"
                    break
        elif isinstance(p, (ast.Try, getattr(ast, "TryStar", ast.Try))):
            if cur in p.body or cur in p.orelse:
                out[id(p)] = "normal"
            elif isinstance(cur, ast.ExceptHandler):
                out[id(p)] = f"handler{p.handlers.index(cur)}"
            # finally is compatible with every path, so it has no exclusive label.
        cur = p
    return out


def _paths_compatible(*paths: dict[int, str]) -> bool:
    seen: dict[int, str] = {}
    for path in paths:
        for controller, branch in path.items():
            prior = seen.get(controller)
            if prior is not None and prior != branch:
                return False
            seen[controller] = branch
    return True


def _node_write_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Assign):
        out: set[str] = set()
        for target in node.targets:
            out.update(_target_names(target))
        return out
    if isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        return _target_names(node.target)
    if isinstance(node, ast.Delete):
        out: set[str] = set()
        for target in node.targets:
            out.update(_target_names(target))
        return out
    if isinstance(node, ast.NamedExpr):
        return _target_names(node.target)
    return set()


def _assigned_call_feeds_return(fn: ast.FunctionDef | ast.AsyncFunctionDef, call: ast.Call,
                                parent: dict[ast.AST, ast.AST]) -> bool:
    """Prove a trusted call's result reaches a return without a compatible later clobber."""
    cur: ast.AST = call
    while cur in parent and isinstance(parent[cur], ast.Call) and parent[cur].func is cur:
        cur = parent[cur]
    holder = parent.get(cur)
    if isinstance(holder, ast.Return):
        return True
    name: str | None = None
    if isinstance(holder, ast.Assign) and len(holder.targets) == 1 and isinstance(holder.targets[0], ast.Name):
        name = holder.targets[0].id
    elif isinstance(holder, ast.AnnAssign) and isinstance(holder.target, ast.Name):
        name = holder.target.id
    if name is None:
        return False

    start_line = getattr(holder, "lineno", -1)
    call_path = _branch_constraints(holder, parent)
    live = list(_live_nodes_block(fn.body))
    returns = [n for n in live if isinstance(n, ast.Return) and isinstance(n.value, ast.Name)
               and n.value.id == name and getattr(n, "lineno", -1) > start_line]
    writes = [n for n in live if name in _node_write_names(n) and n is not holder
              and getattr(n, "lineno", -1) > start_line]
    for ret in returns:
        ret_path = _branch_constraints(ret, parent)
        if not _paths_compatible(call_path, ret_path):
            continue
        ret_line = getattr(ret, "lineno", 10**9)
        clobbered = False
        for write in writes:
            line = getattr(write, "lineno", -1)
            if line >= ret_line:
                continue
            write_path = _branch_constraints(write, parent)
            if _paths_compatible(call_path, ret_path, write_path):
                clobbered = True
                break
        if not clobbered:
            return True
    return False


def _trusted_runtime_install_calls(runtime: ast.Module, fn: ast.FunctionDef | ast.AsyncFunctionDef,
                                   key: str, suffix: str) -> tuple[bool, bool]:
    """Return (saw sealed trusted action-flow call, saw ambiguity/clobber poison)."""
    parent = {c: p for p in ast.walk(fn) for c in ast.iter_child_nodes(p)}
    bool_ok = _builtin_name_unshadowed(runtime, fn, "bool")
    exact = False
    poison = False

    def scan(statements: Iterable[ast.stmt], trusted: set[str]) -> None:
        nonlocal exact, poison
        active = set(trusted)
        for stmt in statements:
            if isinstance(stmt, ast.ImportFrom) and stmt.level == 0 and stmt.module == "r04_full_router":
                for alias in stmt.names:
                    bound = alias.asname or alias.name
                    if alias.name == "install":
                        active.add(bound)
                    elif bound in active:
                        active.discard(bound)
                continue
            if isinstance(stmt, ast.If):
                truth = _static_truth(stmt.test)
                branches = [stmt.body] if truth is True else [stmt.orelse] if truth is False else [stmt.body, stmt.orelse]
                for branch in branches:
                    scan(branch, set(active))
                for name in list(active):
                    if any(name in _bound_names_in_statements(branch) for branch in branches):
                        active.discard(name)
                continue
            if isinstance(stmt, (ast.Try, getattr(ast, "TryStar", ast.Try))):
                scan(stmt.body, set(active))
                scan(stmt.orelse, set(active))
                scan(stmt.finalbody, set(active))
                for name in list(active):
                    all_parts = [*stmt.body, *stmt.orelse, *stmt.finalbody,
                                 *(x for h in stmt.handlers for x in h.body)]
                    if name in _bound_names_in_statements(all_parts):
                        active.discard(name)
                continue
            if isinstance(stmt, (ast.With, ast.AsyncWith)):
                scan(stmt.body, set(active))
            for node in _live_nodes_block((stmt,)):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id not in active:
                    continue
                if any(isinstance(a, ast.Starred) for a in node.args) or any(k.arg is None for k in node.keywords):
                    poison = True
                    continue
                kws = [k for k in node.keywords if k.arg == suffix]
                if not kws:
                    continue
                if len(kws) != 1:
                    poison = True
                    continue
                value = kws[0].value
                value_ok = (_is_self_feature(value, key)
                            or (bool_ok and isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                                and value.func.id == "bool" and len(value.args) == 1 and not value.keywords
                                and _is_self_feature(value.args[0], key)))
                if not value_ok:
                    poison = True
                elif _assigned_call_feeds_return(fn, node, parent):
                    exact = True
                else:
                    poison = True
            for name in list(active):
                if name in _bound_names_in_statements((stmt,)):
                    active.discard(name)
            if _stmt_definitely_terminates(stmt):
                break

    scan(fn.body, set())
    return exact, poison

def _runtime_install_wired(runtime: ast.Module, reachable: Iterable[ast.FunctionDef | ast.AsyncFunctionDef],
                           key: str, suffix: str) -> bool:
    exact = False
    for fn in reachable:
        ok, poison = _trusted_runtime_install_calls(runtime, fn, key, suffix)
        if poison: return False
        exact = exact or ok
    return exact


def _feature_defaults(features: ast.ClassDef) -> dict[str, object]:
    out: dict[str, object] = {}
    for name, value in _bindings(features.body).items():
        if isinstance(value, ast.AST) and not isinstance(value, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            lit = _literal(value)
            if lit is not _UNKNOWN: out[name] = lit
    return out


def _contains_self_features(node: ast.AST) -> bool:
    return any(_is_self_features(n) for n in ast.walk(node))


def _slice_string(node: ast.Subscript) -> str | None:
    return node.slice.value if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str) else None


def _self_dict_proxy(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute) and node.attr == "__dict__":
        return isinstance(node.value, ast.Name) and node.value.id == "self"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "vars":
        return len(node.args) == 1 and isinstance(node.args[0], ast.Name) and node.args[0].id == "self" and not node.keywords
    return False


def _proxy_escape_owner(node: ast.AST, feature_aliases: set[str] | None = None) -> str | None:
    """Return protected instance whose vars/__dict__ proxy escapes, else None."""
    aliases = feature_aliases or set()
    owner: ast.AST | None = None
    if isinstance(node, ast.Attribute) and node.attr == "__dict__":
        owner = node.value
    elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
          and node.func.id == "vars" and len(node.args) == 1 and not node.keywords):
        owner = node.args[0]
    if owner is None:
        return None
    if isinstance(owner, ast.Name) and owner.id == "self":
        return "self"
    if _is_self_features(owner):
        return "self.features"
    if isinstance(owner, ast.Name) and owner.id in aliases:
        return "self.features"
    return None


def _exact_agent_ctor(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Authenticate the canonical constructor parameter binding and root assignment."""
    if not isinstance(fn, ast.FunctionDef) or fn.decorator_list:
        return False
    a = fn.args
    if a.posonlyargs or a.vararg is not None or a.kwarg is not None:
        return False
    if [arg.arg for arg in a.args] != ["self", "features"]:
        return False
    if [arg.arg for arg in a.kwonlyargs] != ["fourth_quadrant_admission"]:
        return False
    if len(a.defaults) != 1 or not (isinstance(a.defaults[0], ast.Constant) and a.defaults[0].value is None):
        return False
    if len(a.kw_defaults) != 1 or not (isinstance(a.kw_defaults[0], ast.Constant) and a.kw_defaults[0].value is None):
        return False
    if "Features" in _function_local_names(fn):
        return False
    if not fn.body:
        return False
    first = fn.body[0]
    if not isinstance(first, ast.Assign) or len(first.targets) != 1:
        return False
    target = first.targets[0]
    value = first.value
    return (
        _is_self_features(target) and isinstance(target.ctx, ast.Store)
        and isinstance(value, ast.BoolOp) and isinstance(value.op, ast.Or)
        and len(value.values) == 2
        and isinstance(value.values[0], ast.Name) and value.values[0].id == "features"
        and isinstance(value.values[1], ast.Call) and isinstance(value.values[1].func, ast.Name)
        and value.values[1].func.id == "Features" and not value.values[1].args and not value.values[1].keywords
    )


def _unsafe_runtime_mutation(fn: ast.FunctionDef | ast.AsyncFunctionDef, key: str,
                             protected_methods: set[str]) -> str | None:
    parent_map = {c: p for p in ast.walk(fn) for c in ast.iter_child_nodes(p)}
    aliases: set[str] = set()
    root_writes: list[ast.Attribute] = []
    for node in _live_nodes_block(fn.body):
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del)) and _is_self_features(node):
            root_writes.append(node)

    allowed_root: ast.Attribute | None = None
    if fn.name == "__init__" and len(root_writes) == 1 and "Features" not in _function_local_names(fn):
        node = root_writes[0]
        parent = parent_map.get(node)
        value = parent.value if isinstance(parent, (ast.Assign, ast.AnnAssign)) else None
        if (isinstance(node.ctx, ast.Store) and isinstance(value, ast.BoolOp)
                and isinstance(value.op, ast.Or) and len(value.values) == 2
                and isinstance(value.values[0], ast.Name) and value.values[0].id == "features"
                and isinstance(value.values[1], ast.Call) and isinstance(value.values[1].func, ast.Name)
                and value.values[1].func.id == "Features"
                and not value.values[1].args and not value.values[1].keywords):
            allowed_root = node

    if root_writes and (allowed_root is None or len(root_writes) != 1):
        return "rebind/delete self.features"

    for node in _live_nodes_block(fn.body):
        if isinstance(node, ast.Assign) and _contains_self_features(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    aliases.add(target.id)
        elif isinstance(node, ast.AnnAssign) and node.value is not None and _contains_self_features(node.value):
            if isinstance(node.target, ast.Name):
                aliases.add(node.target.id)
        elif isinstance(node, ast.NamedExpr) and _contains_self_features(node.value):
            if isinstance(node.target, ast.Name):
                aliases.add(node.target.id)

        escaped = _proxy_escape_owner(node, aliases)
        if escaped is not None:
            return f"{escaped} vars/__dict__ proxy escape"

        if isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del)):
            if _is_self_features(node):
                if node is allowed_root:
                    continue
                return "rebind/delete self.features"
            if _is_self_feature(node, key):
                return f"mutate self.features.{key}"
            if isinstance(node.value, ast.Name) and node.value.id in aliases and node.attr == key:
                return f"mutate alias.{key}"
            if isinstance(node.value, ast.Name) and node.value.id == "self" and node.attr in protected_methods:
                return f"shadow self.{node.attr}"

        if isinstance(node, ast.Subscript) and isinstance(node.ctx, (ast.Store, ast.Del)):
            if _self_dict_proxy(node.value) and _slice_string(node) == "features":
                return "mutate self.__dict__/vars(self)['features']"
            if _contains_self_features(node):
                return "mutate self.features proxy/subscript"
            if isinstance(node.value, ast.Name) and node.value.id in aliases:
                return "mutate features alias subscript"

        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in {"setattr", "delattr"} and len(node.args) >= 2:
                owner, attr = node.args[0], node.args[1]
                attr_name = attr.value if isinstance(attr, ast.Constant) and isinstance(attr.value, str) else None
                if isinstance(owner, ast.Name) and owner.id == "self":
                    if attr_name is None or attr_name == "features" or attr_name in protected_methods:
                        return f"{node.func.id}(self,{attr_name or 'dynamic'})"
                if _is_self_features(owner) or (isinstance(owner, ast.Name) and owner.id in aliases):
                    if attr_name is None or attr_name == key:
                        return f"{node.func.id}(features,{attr_name or 'dynamic'})"
            if isinstance(node.func, ast.Attribute) and node.func.attr in {"__setattr__", "__delattr__"}:
                # self.__setattr__('features', value) / self.__delattr__('features')
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "self" and node.args:
                    attr = node.args[0]
                    if isinstance(attr, ast.Constant) and (attr.value == "features" or attr.value in protected_methods):
                        return f"self.{node.func.attr}({attr.value})"
                # object.__setattr__(self, 'features', value) and matching delete shape.
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "object" and len(node.args) >= 2:
                    owner, attr = node.args[0], node.args[1]
                    attr_name = attr.value if isinstance(attr, ast.Constant) and isinstance(attr.value, str) else None
                    if isinstance(owner, ast.Name) and owner.id == "self":
                        if attr_name is None or attr_name == "features" or attr_name in protected_methods:
                            return f"object.{node.func.attr}(self,{attr_name or 'dynamic'})"
                    if _is_self_features(owner) or (isinstance(owner, ast.Name) and owner.id in aliases):
                        if attr_name is None or attr_name == key:
                            return f"object.{node.func.attr}(features,{attr_name or 'dynamic'})"
    return None


def _unsafe_features_mutation(fn: ast.FunctionDef | ast.AsyncFunctionDef, key: str) -> str | None:
    aliases: set[str] = {"self"}
    for node in _live_nodes_block(fn.body):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name) and node.value.id in aliases:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    aliases.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.value, ast.Name) and node.value.id in aliases:
            if isinstance(node.target, ast.Name):
                aliases.add(node.target.id)

        escaped = _proxy_escape_owner(node, aliases - {"self"})
        if escaped == "self":
            return "Features vars/__dict__ proxy escape"

        if isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del)):
            if isinstance(node.value, ast.Name) and node.value.id in aliases and node.attr == key:
                return f"mutate Features.{key}"
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, (ast.Store, ast.Del)):
            owner = node.value
            if isinstance(owner, ast.Attribute) and owner.attr == "__dict__" and isinstance(owner.value, ast.Name) and owner.value.id in aliases:
                if _slice_string(node) == key:
                    return f"mutate Features.__dict__[{key}]"
            if isinstance(owner, ast.Call) and isinstance(owner.func, ast.Name) and owner.func.id == "vars" and len(owner.args) == 1:
                if isinstance(owner.args[0], ast.Name) and owner.args[0].id in aliases and _slice_string(node) == key:
                    return f"mutate vars(Features)[{key}]"
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in {"setattr", "delattr"} and len(node.args) >= 2:
                if isinstance(node.args[0], ast.Name) and node.args[0].id in aliases:
                    attr_name = node.args[1].value if isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str) else None
                    if attr_name is None or attr_name == key:
                        return f"{node.func.id}(Features,{attr_name or 'dynamic'})"
            if isinstance(node.func, ast.Attribute) and node.func.attr in {"__setattr__", "__delattr__"}:
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "object" and len(node.args) >= 2:
                    if isinstance(node.args[0], ast.Name) and node.args[0].id in aliases:
                        attr_name = node.args[1].value if isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str) else None
                        if attr_name is None or attr_name == key:
                            return f"object.{node.func.attr}(Features,{attr_name or 'dynamic'})"
    return None

def _post_class_attribute_write(tree: ast.Module, clsname: str, attrs: set[str]) -> str | None:
    seen_class = False
    for stmt in tree.body:
        if isinstance(stmt, ast.ClassDef) and stmt.name == clsname:
            seen_class = True
            continue
        if not seen_class:
            continue
        for node in ast.walk(stmt):
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del)):
                if isinstance(node.value, ast.Name) and node.value.id == clsname and node.attr in attrs:
                    return node.attr
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in {"setattr", "delattr"} and len(node.args) >= 2
                    and isinstance(node.args[0], ast.Name) and node.args[0].id == clsname):
                name = node.args[1].value if isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str) else None
                if name is None or name in attrs:
                    return name or "<dynamic>"
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in {"object", "type"}
                    and node.func.attr in {"__setattr__", "__delattr__"}
                    and len(node.args) >= 2
                    and isinstance(node.args[0], ast.Name) and node.args[0].id == clsname):
                name = node.args[1].value if isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str) else None
                if name is None or name in attrs:
                    return name or "<dynamic>"
    return None


def _trusted_dataclass_before(tree: ast.Module, cls: ast.ClassDef) -> bool:
    trusted = False
    for stmt in tree.body:
        if stmt is cls:
            break
        if (isinstance(stmt, ast.ImportFrom) and stmt.level == 0 and stmt.module == "dataclasses"
                and any(a.name == "dataclass" and (a.asname is None or a.asname == "dataclass")
                        for a in stmt.names)):
            trusted = True
            continue
        if "dataclass" in _bound_names_in_statements((stmt,)):
            trusted = False
    return trusted


def _safe_features_decorator(tree: ast.Module, cls: ast.ClassDef) -> bool:
    if not cls.decorator_list:
        return True
    if len(cls.decorator_list) != 1 or not _trusted_dataclass_before(tree, cls):
        return False
    deco = cls.decorator_list[0]
    # Canonical generated Features is exactly @dataclass(frozen=True).
    return (isinstance(deco, ast.Call) and isinstance(deco.func, ast.Name)
            and deco.func.id == "dataclass" and not deco.args and len(deco.keywords) == 1
            and deco.keywords[0].arg == "frozen" and isinstance(deco.keywords[0].value, ast.Constant)
            and deco.keywords[0].value.value is True)


def _plain_class(cls: ast.ClassDef) -> bool:
    return not cls.bases and not cls.keywords


def _canonical_archive_member_bytes(data: bytes, name: str) -> bytes:
    import io
    import tarfile
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        matches = []
        for member in tar.getmembers():
            normalized = member.name[2:] if member.name.startswith("./") else member.name
            if member.isfile() and normalized == name:
                matches.append(member)
        _require(len(matches) == 1, f"canonical archive must contain exactly one {name}")
        handle = tar.extractfile(matches[0])
        _require(handle is not None, f"canonical archive {name} is unreadable")
        return handle.read()


def _canonical_oracle_snapshot() -> tuple[Path, bytes, Path, bytes, bytes]:
    """Authenticate the frozen bootstrap oracle before candidate apply_v4 is imported."""
    import hashlib
    manifest_path = HERE / "V3-MANIFEST.json"
    archive_path = HERE.parent.parent / "exports" / "titan-current.tar.gz"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    pinned = manifest.get("base", {}).get("sha256")
    _require(type(pinned) is str and len(pinned) == 64,
             "V3-MANIFEST.json has no valid canonical base sha256")
    archive_bytes = archive_path.read_bytes()
    _require(hashlib.sha256(archive_bytes).hexdigest() == pinned,
             "canonical archive does not match predecessor-frozen manifest pin")
    canonical_main = _canonical_archive_member_bytes(archive_bytes, "main.py")
    return archive_path, archive_bytes, manifest_path, manifest_bytes, canonical_main


def _entrypoint_bytes_ok(materialized: bytes, canonical: bytes) -> bool:
    # Bootstrap-OFF V1 freezes the final observation point rather than trying to
    # infer arbitrary constructor dataflow through candidate-controlled overlay/apply_v4.
    return materialized == canonical



# ---------------------------------------------------------------------------
# Static, checker-owned apply_v4 materialization. HEAD apply_v4.py is data only.
# The predecessor recipe is frozen by exact build_v3 Git blob + manifest pins.
_BUILD_V3_GIT_BLOB_SHA1 = "07f55ef782be73c1d44d0dc045d3681d01ab1cfd"
_V3_BASE_SHA256 = "5f6a4153e502713b9467776eafe7464af650584149173ce7507a31a1b2af60f1"
_APPLY_V3_SHA256 = "0ea2e80a74f3ce4b7409f1ed42735945ab6b9d5040b8885ae6c585c320a464e2"
_V31_TREE_COMMIT = "a90d888f03987ef0b35cfd20ec3519c6144db08a"
_STATIC_PATCH_ORDER = ("r04_full_router.py", "titan_runtime.py")
_STATIC_PATCH_VARS = {"r04_full_router.py": "router", "titan_runtime.py": "runtime"}
_RESERVED_PATCH_NAMES = frozenset({
    "src", "read", "write", "_replace_once", "KEYS", "io", "json", "os",
    "cfg_path", "data", "key", "handle",
})


class _StaticApplyError(ValueError):
    pass


def _sreq(cond: object, message: str) -> None:
    if not cond:
        raise _StaticApplyError(message)


def _git_blob_sha1(data: bytes) -> str:
    import hashlib
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def _ast_shape(node: ast.AST) -> str:
    return ast.dump(node, annotate_fields=True, include_attributes=False)


def _one_stmt(source: str) -> ast.stmt:
    tree = ast.parse(source)
    _sreq(len(tree.body) == 1, "internal static template must contain one statement")
    return tree.body[0]


_STATIC_REPLACE_TEMPLATE = _one_stmt('''def _replace_once(text, old, new, label):
    count = text.count(old)
    assert count == 1, "%s: expected 1 match, found %d" % (label, count)
    return text.replace(old, new)
''')
_STATIC_READ_TEMPLATE = _one_stmt('''def read(name):
    return io.open(os.path.join(src, name), encoding="utf-8", newline="").read()
''')
_STATIC_WRITE_TEMPLATE = _one_stmt('''def write(name, text):
    with io.open(os.path.join(src, name), "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
''')
_STATIC_CONFIG_TAIL = ast.parse('''cfg_path = os.path.join(src, "TITAN-CONFIG.json")
data = json.loads(io.open(cfg_path, encoding="utf-8").read())
for key in KEYS:
    assert key not in data, key
    data[key] = False
with io.open(cfg_path, "w", encoding="utf-8", newline="\\n") as handle:
    handle.write(json.dumps(data, indent=2) + "\\n")
return src
''').body


def _static_literal_str(node: ast.AST, what: str) -> str:
    _sreq(isinstance(node, ast.Constant) and type(node.value) is str,
          f"{what} must be a literal string")
    return node.value


def _static_safe_path(value: str, what: str) -> str:
    from pathlib import PurePosixPath
    _sreq("\\" not in value and "\x00" not in value, f"{what}: unsafe path")
    path = PurePosixPath(value)
    _sreq(not path.is_absolute() and path.parts and all(x not in ("", ".", "..") for x in path.parts),
          f"{what}: unsafe package-relative path {value!r}")
    return path.as_posix()


def _static_plain_function(fn: ast.FunctionDef, name: str, params: tuple[str, ...]) -> None:
    _sreq(fn.name == name and not fn.decorator_list and fn.returns is None
          and getattr(fn, "type_comment", None) is None
          and not getattr(fn, "type_params", ()),
          f"{name}: function metadata is not canonical")
    args = fn.args
    _sreq(not args.posonlyargs and tuple(a.arg for a in args.args) == params
          and args.vararg is None and args.kwarg is None and not args.kwonlyargs
          and not args.defaults and not args.kw_defaults
          and all(a.annotation is None for a in args.args),
          f"{name}: signature is not canonical")


def _static_direct_call(node: ast.AST, name: str, argc: int) -> list[ast.AST]:
    _sreq(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name,
          f"expected direct {name}(...)")
    _sreq(not node.keywords and len(node.args) == argc, f"{name}: bad call shape")
    return list(node.args)


def _parse_static_apply_v4(source: str, *, filename: str = "apply_v4.py") -> tuple[tuple[str, ...], tuple[tuple[str, tuple[tuple[str, str, str], ...]], ...]]:
    # Parse the deliberately tiny declarative apply_v4 language. Never execute it.
    try:
        module = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        raise _StaticApplyError(f"{filename}: syntax error: {exc}") from exc
    body = list(module.body)
    if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
            and type(body[0].value.value) is str):
        body.pop(0)

    _sreq(len(body) == 6, "apply_v4 top level must be exactly imports, KEYS, helper, apply")
    for stmt, expected in zip(body[:3], ("io", "json", "os")):
        _sreq(isinstance(stmt, ast.Import) and len(stmt.names) == 1
              and stmt.names[0].name == expected and stmt.names[0].asname is None,
              "apply_v4 imports must be exactly unaliased io/json/os")

    key_stmt = body[3]
    _sreq(isinstance(key_stmt, ast.Assign) and len(key_stmt.targets) == 1
          and isinstance(key_stmt.targets[0], ast.Name) and key_stmt.targets[0].id == "KEYS"
          and isinstance(key_stmt.value, ast.Tuple),
          "KEYS must be one literal tuple assignment")
    keys = tuple(_static_literal_str(x, "KEYS item") for x in key_stmt.value.elts)
    _sreq(keys and len(keys) == len(set(keys)), "KEYS must be nonempty and unique")
    _sreq(all(k.startswith("r04_") and k.removeprefix("r04_").isidentifier() for k in keys),
          "KEYS contains invalid V4 key")

    helper, fn = body[4], body[5]
    _sreq(isinstance(helper, ast.FunctionDef) and isinstance(fn, ast.FunctionDef),
          "_replace_once/apply must be plain functions")
    _static_plain_function(helper, "_replace_once", ("text", "old", "new", "label"))
    _sreq(_ast_shape(helper) == _ast_shape(_STATIC_REPLACE_TEMPLATE),
          "_replace_once is not canonical")
    _static_plain_function(fn, "apply", ("src",))

    stmts = list(fn.body)
    _sreq(len(stmts) >= 8, "apply body too short")
    _sreq(isinstance(stmts[0], ast.FunctionDef) and isinstance(stmts[1], ast.FunctionDef),
          "apply must begin with canonical read/write helpers")
    _static_plain_function(stmts[0], "read", ("name",))
    _static_plain_function(stmts[1], "write", ("name", "text"))
    _sreq(_ast_shape(stmts[0]) == _ast_shape(_STATIC_READ_TEMPLATE)
          and _ast_shape(stmts[1]) == _ast_shape(_STATIC_WRITE_TEMPLATE),
          "read/write helpers are not canonical")

    tailn = len(_STATIC_CONFIG_TAIL)
    _sreq(len(stmts) > 2 + tailn, "apply must contain at least one patch group")
    _sreq([_ast_shape(x) for x in stmts[-tailn:]] == [_ast_shape(x) for x in _STATIC_CONFIG_TAIL],
          "TITAN-CONFIG trailer is not canonical literal-False insertion")
    middle = stmts[2:-tailn]

    groups: list[tuple[str, tuple[tuple[str, str, str], ...]]] = []
    seen_paths: set[str] = set()
    seen_labels: set[str] = set()
    i = 0
    while i < len(middle):
        stmt = middle[i]
        _sreq(isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
              and isinstance(stmt.targets[0], ast.Name),
              f"patch group {len(groups)} must begin with name = read(...)")
        variable = stmt.targets[0].id
        _sreq(variable not in _RESERVED_PATCH_NAMES,
              f"patch variable {variable!r} shadows static grammar/control binding")
        args = _static_direct_call(stmt.value, "read", 1)
        path = _static_safe_path(_static_literal_str(args[0], "read path"), "read path")
        _sreq(path in _STATIC_PATCH_VARS, f"patch path outside generated V4 surfaces: {path!r}")
        _sreq(variable == _STATIC_PATCH_VARS[path],
              f"{path}: patch variable must be {_STATIC_PATCH_VARS[path]!r}")
        _sreq(path != "TITAN-CONFIG.json", "TITAN-CONFIG may change only in canonical trailer")
        _sreq(path not in seen_paths, f"duplicate patch group for {path}")
        seen_paths.add(path)
        i += 1

        edits: list[tuple[str, str, str]] = []
        while i < len(middle) and isinstance(middle[i], ast.Assign):
            rep = middle[i]
            _sreq(len(rep.targets) == 1 and isinstance(rep.targets[0], ast.Name)
                  and rep.targets[0].id == variable,
                  "replacement must reassign the live patch variable")
            rargs = _static_direct_call(rep.value, "_replace_once", 4)
            _sreq(isinstance(rargs[0], ast.Name) and rargs[0].id == variable,
                  "replacement must consume the same live patch variable")
            old = _static_literal_str(rargs[1], "replacement old")
            new = _static_literal_str(rargs[2], "replacement new")
            label = _static_literal_str(rargs[3], "replacement label")
            _sreq(old and old != new and label, "replacement anchor/new/label is invalid")
            _sreq(label not in seen_labels, f"duplicate replacement label {label!r}")
            seen_labels.add(label)
            edits.append((old, new, label))
            i += 1
        _sreq(edits, f"{path}: patch group needs at least one exact replacement")
        _sreq(i < len(middle) and isinstance(middle[i], ast.Expr), f"{path}: missing paired write")
        wargs = _static_direct_call(middle[i].value, "write", 2)
        outpath = _static_safe_path(_static_literal_str(wargs[0], "write path"), "write path")
        _sreq(outpath == path and isinstance(wargs[1], ast.Name) and wargs[1].id == variable,
              f"{path}: write must use same literal path/live variable")
        i += 1
        groups.append((path, tuple(edits)))

    _sreq(tuple(path for path, _ in groups) == _STATIC_PATCH_ORDER,
          f"apply_v4 patch sections must be exact order {_STATIC_PATCH_ORDER!r}")
    return keys, tuple(groups)


def _interpret_static_apply_v4(package: dict[str, bytes], program: tuple[tuple[str, ...], tuple[tuple[str, tuple[tuple[str, str, str], ...]], ...]]) -> dict[str, bytes]:
    keys, groups = program
    out = dict(package)
    for path, edits in groups:
        _sreq(path in out and type(out[path]) is bytes, f"missing/non-byte package file {path!r}")
        try:
            text = out[path].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise _StaticApplyError(f"{path}: not UTF-8") from exc
        for old, new, label in edits:
            count = text.count(old)
            _sreq(count == 1, f"{label}: expected exactly one anchor, found {count}")
            text = text.replace(old, new)
        out[path] = text.encode("utf-8")

    cfg = "TITAN-CONFIG.json"
    _sreq(cfg in out and type(out[cfg]) is bytes, "missing TITAN-CONFIG.json")
    try:
        data = json.loads(out[cfg].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _StaticApplyError("invalid TITAN-CONFIG.json") from exc
    _sreq(type(data) is dict, "TITAN-CONFIG.json root must be an object")
    for key in keys:
        _sreq(key not in data, f"{key}: already exists before V4 static patch")
        data[key] = False
    out[cfg] = (json.dumps(data, indent=2) + "\n").encode("utf-8")
    return out


def _decode_canonical_python_bytes(raw: bytes, name: str) -> str:
    """Require one unambiguous UTF-8 interpretation for checker and CPython."""
    import codecs
    import io
    import tokenize
    _require(not raw.startswith(codecs.BOM_UTF8), f"{name}: UTF-8 BOM is forbidden")
    try:
        enc, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
    except SyntaxError as exc:
        _fail(f"{name}: invalid source encoding declaration: {exc}")
    norm = enc.lower().replace("_", "-")
    _require(norm in {"utf-8", "utf8"}, f"{name}: source encoding must be UTF-8, got {enc!r}")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        _fail(f"{name}: invalid UTF-8: {exc}")


_SOURCE_PREFIX = "revenue/kaggriculture/cloud-execution-lab/candidates/v3"
_OVERLAY_PREFIX = _SOURCE_PREFIX + "/overlay"
_REGULAR_GIT_MODES = frozenset({"100644", "100755"})
_PROTECTED_SOURCE_ROOTS = frozenset({
    "argparse", "ast", "json", "pathlib", "typing", "copy", "symtable", "dataclasses",
    "gzip", "hashlib", "io", "os", "shutil", "sys", "tarfile", "tempfile",
    "subprocess", "tokenize", "codecs", "stat", "apply_v3", "apply_v4", "build_v3",
    "sitecustomize", "usercustomize",
})
_AUTHORIZED_SOURCE_ROOTS = {
    "apply_v3": "apply_v3.py", "apply_v4": "apply_v4.py", "build_v3": "build_v3.py",
}


def _git_repo() -> Path:
    import subprocess
    try:
        raw = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as exc:
        _fail(f"cannot locate authenticated Git checkout: {exc.output!r}")
    return Path(raw.decode("utf-8").strip())


def _git_out(repo: Path, *args: str) -> bytes:
    import subprocess
    try:
        return subprocess.check_output(["git", *args], cwd=repo, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as exc:
        _fail(f"git {' '.join(args)} failed: {exc.output.decode('utf-8', 'replace')}")


def _git_blob_at(repo: Path, revision: str, path: str) -> bytes:
    return _git_out(repo, "cat-file", "blob", f"{revision}:{path}")


def _ls_tree_entries(repo: Path, revision: str, prefix: str) -> list[tuple[str, str, str, str]]:
    raw = _git_out(repo, "ls-tree", "-r", "-z", "--full-tree", revision, "--", prefix)
    out: list[tuple[str, str, str, str]] = []
    lead = prefix.rstrip("/") + "/"
    for rec in raw.split(b"\0"):
        if not rec:
            continue
        try:
            meta, path_b = rec.split(b"\t", 1)
            mode_b, kind_b, oid_b = meta.split(b" ", 2)
            mode, kind, oid = mode_b.decode("ascii"), kind_b.decode("ascii"), oid_b.decode("ascii")
            path = path_b.decode("utf-8")
        except Exception as exc:
            _fail(f"malformed git ls-tree record: {exc}")
        _require(path.startswith(lead), f"git tree entry escaped prefix: {path!r}")
        rel = path[len(lead):]
        _static_safe_path(rel, "Git tree path")
        out.append((rel, mode, kind, oid))
    return out


def _assert_source_root_custody(repo: Path, head_sha: str) -> None:
    entries = _ls_tree_entries(repo, head_sha, _SOURCE_PREFIX)
    exact: set[str] = set()
    for rel, mode, kind, _oid in entries:
        first = rel.split("/", 1)[0]
        root = first if "/" in rel else first.split(".", 1)[0]
        if root not in _PROTECTED_SOURCE_ROOTS:
            continue
        allowed = _AUTHORIZED_SOURCE_ROOTS.get(root)
        _require(allowed is not None and rel == allowed,
                 f"candidate-root import shadow for {root!r}: {rel!r}")
        _require(kind == "blob" and mode in _REGULAR_GIT_MODES,
                 f"authorized source {rel!r} must be regular Git blob")
        exact.add(root)
    _require(set(_AUTHORIZED_SOURCE_ROOTS) <= exact,
             "required predecessor/apply source missing from candidate root")


def _overlay_git_snapshot(repo: Path, revision: str) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for rel, mode, kind, oid in _ls_tree_entries(repo, revision, _OVERLAY_PREFIX):
        # Frozen build_v3 ignores these products. Everything else must be a regular blob.
        parts = rel.split("/")
        if "__pycache__" in parts or rel.endswith(".pyc"):
            continue
        _require(kind == "blob" and mode in _REGULAR_GIT_MODES,
                 f"overlay member must be regular Git blob: {rel!r} mode={mode} kind={kind}")
        _require(rel not in out, f"duplicate overlay member {rel!r}")
        out[rel] = _git_out(repo, "cat-file", "blob", oid)
    return out


def _validated_head_overlay(repo: Path, base_sha: str, head_sha: str,
                            canonical_members: set[str]) -> dict[str, bytes]:
    base = _overlay_git_snapshot(repo, base_sha)
    head = _overlay_git_snapshot(repo, head_sha)
    missing = sorted(set(base) - set(head))
    _require(not missing, "HEAD removed predecessor overlay member(s): " + ", ".join(missing))
    changed = sorted(name for name in base if head[name] != base[name])
    _require(not changed, "HEAD changed predecessor overlay bytes: " + ", ".join(changed))
    for rel in sorted(set(head) - set(base)):
        _require(rel not in canonical_members, f"new overlay collides with canonical package member: {rel}")
        if rel.startswith("checks/") and rel.endswith(".py"):
            continue
        _require("/" not in rel and rel.startswith("r04_") and rel.endswith(".py"),
                 f"new overlay runtime member outside additive r04_*.py grammar: {rel!r}")
    return head


def _safe_archive_files(data: bytes) -> dict[str, bytes]:
    import io
    import tarfile
    from pathlib import PurePosixPath
    files: dict[str, bytes] = {}
    dirs: set[str] = set()
    total = 0
    members = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            members += 1
            _require(members <= 10000, "canonical archive has too many members")
            raw = member.name
            _require("\\" not in raw and "\x00" not in raw, f"canonical archive unsafe path {raw!r}")
            name = raw[2:] if raw.startswith("./") else raw
            _require(name and not name.startswith("./"), f"canonical archive noncanonical path {raw!r}")
            path = PurePosixPath(name)
            _require(not path.is_absolute() and path.parts
                     and all(x not in ("", ".", "..") for x in path.parts),
                     f"canonical archive unsafe path {raw!r}")
            norm = path.as_posix()
            parents = [PurePosixPath(*path.parts[:i]).as_posix() for i in range(1, len(path.parts))]
            _require(not any(parent in files for parent in parents),
                     f"canonical archive file/parent collision at {norm!r}")
            if member.isdir():
                _require(norm not in files, f"canonical archive directory/file collision {norm!r}")
                dirs.add(norm)
                continue
            _require(member.isfile(), f"canonical archive non-regular member {norm!r}")
            _require(norm not in files and norm not in dirs, f"canonical archive duplicate/collision {norm!r}")
            _require(0 <= member.size <= 16 * 1024 * 1024, f"canonical archive member too large: {norm!r}")
            total += member.size
            _require(total <= 128 * 1024 * 1024, "canonical archive expanded size too large")
            handle = tar.extractfile(member)
            _require(handle is not None, f"canonical archive member {norm!r} unreadable")
            blob = handle.read(member.size + 1)
            _require(len(blob) == member.size, f"canonical archive size mismatch for {norm!r}")
            files[norm] = blob
            dirs.update(parents)
    _require(files, "canonical archive contains no files")
    return files


def _base_sha(base_apply_v4: Path) -> str:
    marker = base_apply_v4.parent / "base_sha.txt"
    _require(marker.is_file(), "workflow predecessor SHA receipt missing")
    value = marker.read_text(encoding="ascii").strip()
    _require(len(value) == 40 and all(c in "0123456789abcdef" for c in value),
             "workflow predecessor SHA receipt malformed")
    return value


def _run_authenticated_apply_v3(apply_v3_bytes: bytes, package: dict[str, bytes]) -> dict[str, bytes]:
    import os
    import stat
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory(prefix="titan-v4-predecessor-") as td:
        top = Path(td)
        work = top / "work"; trusted = top / "trusted"
        work.mkdir(); trusted.mkdir()
        for name, blob in package.items():
            target = work / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)
        apply_path = trusted / "apply_v3.py"
        apply_path.write_bytes(apply_v3_bytes)
        wrapper = (
            'import importlib.util, pathlib, sys\n'
            'path=pathlib.Path(sys.argv[1]); work=pathlib.Path(sys.argv[2])\n'
            'spec=importlib.util.spec_from_file_location("_titan_authenticated_apply_v3", path)\n'
            'if spec is None or spec.loader is None: raise SystemExit(91)\n'
            'mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)\n'
            'apply=getattr(mod,"apply",None)\n'
            'if not callable(apply): raise SystemExit(92)\n'
            'result=apply(str(work))\n'
            'if result != str(work): raise SystemExit(93)\n'
        )
        proc = subprocess.run(
            [_titan_bootstrap_sys.executable, "-I", "-S", "-c", wrapper, str(apply_path), str(work)],
            cwd=str(trusted), env={"PATH": os.environ.get("PATH", ""), "PYTHONNOUSERSITE": "1"},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False,
        )
        _require(proc.returncode == 0,
                 f"authenticated predecessor apply_v3 failed rc={proc.returncode}")
        out: dict[str, bytes] = {}
        for root, dirs, names in os.walk(work, topdown=True, followlinks=False):
            rootp = Path(root)
            for dirname in list(dirs):
                q = rootp / dirname; mode = os.lstat(q).st_mode
                _require(stat.S_ISDIR(mode) and not stat.S_ISLNK(mode),
                         f"pre-V4 package non-directory/symlink dir: {q}")
            for filename in names:
                q = rootp / filename; mode = os.lstat(q).st_mode
                _require(stat.S_ISREG(mode) and not stat.S_ISLNK(mode),
                         f"pre-V4 package non-regular/symlink file: {q}")
                rel = q.relative_to(work).as_posix(); _static_safe_path(rel, "pre-V4 package path")
                _require(rel not in out, f"duplicate pre-V4 package path: {rel}")
                out[rel] = q.read_bytes()
        _require(out, "pre-V4 package empty after authenticated apply_v3")
        return out


def _trusted_pre_v4_package(base_apply_v4: Path, head_keys: tuple[str, ...]) -> tuple[dict[str, bytes], bytes]:
    # Reproduce frozen build_v3 prefix without importing build_v3 or executing HEAD apply_v4.
    import hashlib
    repo = _git_repo()
    head_sha = _git_out(repo, "rev-parse", "HEAD").decode("ascii").strip()
    base_sha = _base_sha(base_apply_v4)
    _assert_source_root_custody(repo, head_sha)

    manifest_path = HERE / "V3-MANIFEST.json"
    build_path = HERE / "build_v3.py"
    apply_v3_path = HERE / "apply_v3.py"
    archive_path = HERE.parent.parent / "exports" / "titan-current.tar.gz"
    manifest_bytes = manifest_path.read_bytes(); build_bytes = build_path.read_bytes(); apply_v3_bytes = apply_v3_path.read_bytes()

    # Tie the retained oracle to the exact predecessor Git objects, not mutable paths.
    for rel, current in (("V3-MANIFEST.json", manifest_bytes), ("build_v3.py", build_bytes), ("apply_v3.py", apply_v3_bytes)):
        _require(_git_blob_at(repo, base_sha, _SOURCE_PREFIX + "/" + rel) == current,
                 f"predecessor-frozen {rel} bytes differ from BASE Git object")

    manifest = json.loads(manifest_bytes.decode("utf-8"))
    _require(manifest.get("schema") == "titan.v3-integration.v1"
             and manifest.get("operation") == "titan-v3-integration-20260909-01",
             "predecessor V3 manifest identity changed")
    _require(manifest.get("base", {}).get("sha256") == _V3_BASE_SHA256,
             "predecessor V3 manifest base pin changed")
    releases = manifest.get("releases")
    _require(isinstance(releases, list) and releases
             and releases[-1].get("version") == "3.1"
             and releases[-1].get("tree_commit") == _V31_TREE_COMMIT,
             "predecessor V3.1 release identity changed")
    _require(manifest.get("overlay", {}).get("apply_v3.py") == _APPLY_V3_SHA256,
             "predecessor V3 manifest apply_v3 pin changed")
    _require(_git_blob_sha1(build_bytes) == _BUILD_V3_GIT_BLOB_SHA1,
             "predecessor build_v3.py recipe bytes changed")
    _require(hashlib.sha256(apply_v3_bytes).hexdigest() == _APPLY_V3_SHA256,
             "predecessor apply_v3.py bytes changed")
    archive_bytes = archive_path.read_bytes()
    _require(hashlib.sha256(archive_bytes).hexdigest() == _V3_BASE_SHA256,
             "canonical archive does not match frozen V3 pin")

    package = _safe_archive_files(archive_bytes)
    canonical_main = package.get("main.py")
    _require(type(canonical_main) is bytes, "canonical archive missing main.py")
    package.update(_validated_head_overlay(repo, base_sha, head_sha, set(package)))
    after = _run_authenticated_apply_v3(apply_v3_bytes, package)

    _require(manifest_path.read_bytes() == manifest_bytes, "V3 manifest changed during materialization")
    _require(build_path.read_bytes() == build_bytes, "build_v3 recipe changed during materialization")
    _require(apply_v3_path.read_bytes() == apply_v3_bytes, "apply_v3 source changed during materialization")
    _require(archive_path.read_bytes() == archive_bytes, "canonical archive changed during materialization")
    return after, canonical_main


def _materialization_self_test() -> None:
    import io, tarfile
    def archive(members):
        raw=io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w:gz") as tar:
            for name, kind, payload in members:
                info=tarfile.TarInfo(name)
                if kind == "file":
                    info.size=len(payload); tar.addfile(info, io.BytesIO(payload))
                elif kind == "symlink":
                    info.type=tarfile.SYMTYPE; info.linkname="main.py"; tar.addfile(info)
        return raw.getvalue()
    _require(_safe_archive_files(archive([("main.py","file",b"x\n")])) == {"main.py": b"x\n"},
             "safe canonical tar positive fixture failed")
    for bad in [
        [("../escape","file",b"x")],
        [("main.py","symlink",b"")],
        [("./main.py","file",b"x"),("main.py","file",b"y")],
    ]:
        try: _safe_archive_files(archive(bad))
        except SystemExit: pass
        else: _fail("canonical tar poison false-passed")


import copy

class V4MonotonicityError(RuntimeError):
    pass


def req(cond: bool, msg: str) -> None:
    if not cond:
        raise V4MonotonicityError(msg)


def dump(node: ast.AST) -> str:
    return ast.dump(node, include_attributes=False)


def parse_bytes(raw: bytes, name: str) -> ast.Module:
    try:
        return ast.parse(raw.decode("utf-8"), filename=name)
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise V4MonotonicityError(f"{name}: invalid UTF-8/Python: {exc}") from exc


def key_meta(keys):
    out = []
    for key in keys:
        req(type(key) is str and key.startswith("r04_") and key[4:].isidentifier(), f"bad V4 key {key!r}")
        suffix = key[4:]
        out.append((key, suffix, suffix.upper()))
    req(out and len(out) == len({x[0] for x in out}), "V4 keys must be nonempty/unique")
    return tuple(out)


def strip_docstrings(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body:
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and type(first.value.value) is str:
                del body[0]


def unique_top(tree: ast.Module, kind, name: str):
    found = [x for x in tree.body if isinstance(x, kind) and x.name == name]
    req(len(found) == 1, f"expected one top-level {name}, found {len(found)}")
    return found[0]


def same_scope_bound_names(fn: ast.FunctionDef) -> set[str]:
    bound = {a.arg for a in (*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs)}
    if fn.args.vararg:
        bound.add(fn.args.vararg.arg)
    if fn.args.kwarg:
        bound.add(fn.args.kwarg.arg)

    class V(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            if node is fn:
                for s in node.body:
                    self.visit(s)
            else:
                bound.add(node.name)
        visit_AsyncFunctionDef = visit_FunctionDef
        def visit_ClassDef(self, node):
            bound.add(node.name)
        def visit_Lambda(self, node):
            return
        def visit_Name(self, node):
            if isinstance(node.ctx, (ast.Store, ast.Del)):
                bound.add(node.id)
        def visit_Import(self, node):
            for a in node.names:
                bound.add(a.asname or a.name.split('.', 1)[0])
        def visit_ImportFrom(self, node):
            for a in node.names:
                if a.name != '*':
                    bound.add(a.asname or a.name)
        def visit_ExceptHandler(self, node):
            if node.name:
                bound.add(node.name)
            for s in node.body:
                self.visit(s)
    V().visit(fn)
    return bound


def subtree_name_mentions(fn: ast.FunctionDef) -> set[str]:
    names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
    names.update(a.arg for n in ast.walk(fn) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
                 for a in (*n.args.posonlyargs, *n.args.args, *n.args.kwonlyargs))
    return names


def bound_inside(node: ast.AST) -> set[str]:
    # Conservative: bindings anywhere in an admitted seam, excluding bindings
    # inside newly-created nested scopes (their definition name still binds here).
    bound: set[str] = set()
    class V(ast.NodeVisitor):
        def visit_FunctionDef(self, n):
            bound.add(n.name)
        visit_AsyncFunctionDef = visit_FunctionDef
        def visit_ClassDef(self, n):
            bound.add(n.name)
        def visit_Lambda(self, n):
            return
        def visit_Name(self, n):
            if isinstance(n.ctx, (ast.Store, ast.Del)):
                bound.add(n.id)
        def visit_Import(self, n):
            for a in n.names:
                bound.add(a.asname or a.name.split('.', 1)[0])
        def visit_ImportFrom(self, n):
            for a in n.names:
                if a.name != '*':
                    bound.add(a.asname or a.name)
        def visit_ExceptHandler(self, n):
            if n.name:
                bound.add(n.name)
            self.generic_visit(n)
    V().visit(node)
    return bound


def first_positive_flag(test: ast.AST, flags: set[str]) -> str | None:
    if isinstance(test, ast.Name) and test.id in flags:
        return test.id
    # Flag must be the first `and` operand so FLAG=False short-circuits every
    # remaining test expression.  OR / reordered expressions are not inert.
    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And) and test.values:
        first = test.values[0]
        if isinstance(first, ast.Name) and first.id in flags:
            return first.id
    return None


def strip_guarded_seams_in_function(post_fn: ast.FunctionDef, pre_fn: ast.FunctionDef, flags: set[str], seam_counts: dict[str, int]) -> None:
    pre_bound = same_scope_bound_names(pre_fn)
    pre_mentions = subtree_name_mentions(pre_fn)

    def clean_list(stmts: list[ast.stmt]) -> list[ast.stmt]:
        out: list[ast.stmt] = []
        for stmt in stmts:
            if isinstance(stmt, ast.If):
                flag = first_positive_flag(stmt.test, flags)
                if flag is not None:
                    req(not stmt.orelse, f"{post_fn.name}: admitted {flag} seam may not have else")
                    req(not any(isinstance(n, (ast.Global, ast.Nonlocal)) for n in ast.walk(stmt)),
                        f"{post_fn.name}: {flag} seam changes global/nonlocal binding")
                    for name in bound_inside(stmt):
                        req(name in pre_bound or name not in pre_mentions,
                            f"{post_fn.name}: {flag} seam makes predecessor name {name!r} local")
                    seam_counts[flag] += 1
                    continue
            # Recurse only within the same lexical function. Nested functions are
            # normalized independently by name below, not through their parent.
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out.append(stmt)
                continue
            for field, value in ast.iter_fields(stmt):
                if isinstance(value, list) and value and all(isinstance(x, ast.stmt) for x in value):
                    setattr(stmt, field, clean_list(value))
            out.append(stmt)
        return out
    post_fn.body = clean_list(post_fn.body)


def function_map(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    found: dict[str, list[ast.FunctionDef]] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef):
            found.setdefault(n.name, []).append(n)
    return {name: xs[0] for name, xs in found.items() if len(xs) == 1}


def remove_install_args(fn: ast.FunctionDef, metas) -> None:
    targets = {suffix for _, suffix, _ in metas}
    req(not any(a.arg in targets for a in fn.args.posonlyargs), "V4 install suffix became positional-only")
    args = list(fn.args.args)
    defaults = list(fn.args.defaults)
    first_default = len(args) - len(defaults)
    pairs = []
    for i, arg in enumerate(args):
        default = defaults[i - first_default] if i >= first_default else None
        pairs.append((arg, default))
    seen = set()
    kept = []
    for arg, default in pairs:
        if arg.arg in targets:
            req(isinstance(default, ast.Constant) and default.value is None,
                f"install suffix {arg.arg} must default literal None")
            seen.add(arg.arg)
        else:
            kept.append((arg, default))
    # kw-only is supported only if exact None; canonical currently uses ordinary args.
    new_kw_args = []
    new_kw_defs = []
    for arg, default in zip(fn.args.kwonlyargs, fn.args.kw_defaults):
        if arg.arg in targets:
            req(isinstance(default, ast.Constant) and default.value is None,
                f"kw-only install suffix {arg.arg} must default literal None")
            seen.add(arg.arg)
        else:
            new_kw_args.append(arg); new_kw_defs.append(default)
    req(seen == targets, f"install suffix parameter set mismatch: got {sorted(seen)}")
    fn.args.args = [a for a, _ in kept]
    # Reconstruct trailing defaults and reject impossible gaps after removal.
    marks = [d is not None for _, d in kept]
    if any(marks):
        first = marks.index(True)
        req(all(marks[first:]), "install defaults no longer form a trailing suffix")
        fn.args.defaults = [d for _, d in kept[first:]]
    else:
        fn.args.defaults = []
    fn.args.kwonlyargs = new_kw_args
    fn.args.kw_defaults = new_kw_defs


def exact_setter(stmt: ast.stmt, suffix: str, flag: str) -> bool:
    if not (isinstance(stmt, ast.If) and not stmt.orelse and len(stmt.body) == 1):
        return False
    t = stmt.test
    if not (isinstance(t, ast.Compare) and isinstance(t.left, ast.Name) and t.left.id == suffix
            and len(t.ops) == 1 and isinstance(t.ops[0], ast.IsNot)
            and len(t.comparators) == 1 and isinstance(t.comparators[0], ast.Constant)
            and t.comparators[0].value is None):
        return False
    a = stmt.body[0]
    return (
        isinstance(a, ast.Assign) and len(a.targets) == 1
        and isinstance(a.targets[0], ast.Name) and a.targets[0].id == flag
        and isinstance(a.value, ast.Call) and isinstance(a.value.func, ast.Name) and a.value.func.id == "bool"
        and len(a.value.args) == 1 and not a.value.keywords
        and isinstance(a.value.args[0], ast.Name) and a.value.args[0].id == suffix
    )


def clean_install(fn: ast.FunctionDef, metas) -> None:
    remove_install_args(fn, metas)
    flags = {flag for _, _, flag in metas}
    setters = {flag: 0 for flag in flags}
    out = []
    for stmt in fn.body:
        if isinstance(stmt, ast.Global):
            names = [x for x in stmt.names if x not in flags]
            if names:
                stmt.names = names; out.append(stmt)
            continue
        matched = None
        for _, suffix, flag in metas:
            if exact_setter(stmt, suffix, flag):
                matched = flag; break
        if matched:
            setters[matched] += 1
            continue
        out.append(stmt)
    req(all(v == 1 for v in setters.values()), f"install setter counts mismatch: {setters}")
    fn.body = out


def prune_fastpath_flags(tree: ast.Module, flags: set[str]) -> None:
    class V(ast.NodeTransformer):
        def visit_If(self, node):
            self.generic_visit(node)
            t = node.test
            if not (isinstance(t, ast.UnaryOp) and isinstance(t.op, ast.Not)
                    and isinstance(t.operand, ast.BoolOp) and isinstance(t.operand.op, ast.Or)):
                return node
            if not (len(node.body) == 1 and isinstance(node.body[0], ast.Return)
                    and isinstance(node.body[0].value, ast.Call)):
                return node
            call = node.body[0].value
            if not (isinstance(call.func, ast.Name) and call.func.id == "_v3_core"):
                return node
            values = [v for v in t.operand.values if not (isinstance(v, ast.Name) and v.id in flags)]
            req(values, "V4 fastpath normalization erased predecessor condition")
            if len(values) == 1:
                t.operand = values[0]
            else:
                t.operand.values = values
            return node
    V().visit(tree)


def normalize_router(pre_raw: bytes, post_raw: bytes, metas) -> tuple[ast.Module, ast.Module]:
    pre = parse_bytes(pre_raw, "pre-router.py")
    post = parse_bytes(post_raw, "post-router.py")
    strip_docstrings(pre); strip_docstrings(post)
    flags = {flag for _, _, flag in metas}

    # New module flags must be exact default-OFF declarations and absent in predecessor.
    for flag in flags:
        req(not any(isinstance(n, ast.Name) and n.id == flag for n in ast.walk(pre)),
            f"predecessor already names new flag {flag}")
        hits = [s for s in post.body if isinstance(s, ast.Assign) and len(s.targets) == 1
                and isinstance(s.targets[0], ast.Name) and s.targets[0].id == flag
                and isinstance(s.value, ast.Constant) and s.value.value is False]
        req(len(hits) == 1, f"{flag}: expected one module literal-False declaration")
        post.body.remove(hits[0])

    pre_install = unique_top(pre, ast.FunctionDef, "install")
    post_install = unique_top(post, ast.FunctionDef, "install")
    clean_install(post_install, metas)

    # Remove only branches whose first condition is a new flag. Before removal,
    # prove the branch cannot change predecessor lexical binding while OFF.
    pre_funcs = function_map(pre)
    post_funcs = function_map(post)
    seam_counts = {flag: 0 for flag in flags}
    for name, pfn in post_funcs.items():
        if name == "install" or name not in pre_funcs:
            continue
        strip_guarded_seams_in_function(pfn, pre_funcs[name], flags, seam_counts)
    req(all(v >= 1 for v in seam_counts.values()), f"missing positive guarded seam(s): {seam_counts}")

    prune_fastpath_flags(post, flags)
    req(dump(pre) == dump(post), "router changes are not reducible to default-OFF V4 plumbing/seams")
    return pre, post


def is_false_field(stmt: ast.stmt, key: str) -> bool:
    return (
        isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id == key
        and isinstance(stmt.annotation, ast.Name) and stmt.annotation.id == "bool"
        and isinstance(stmt.value, ast.Constant) and stmt.value.value is False
        and stmt.simple == 1
    )


def is_bool_feature(node: ast.AST, key: str) -> bool:
    return (
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "bool"
        and len(node.args) == 1 and not node.keywords
        and isinstance(node.args[0], ast.Attribute) and node.args[0].attr == key
        and isinstance(node.args[0].value, ast.Attribute) and node.args[0].value.attr == "features"
        and isinstance(node.args[0].value.value, ast.Name) and node.args[0].value.value.id == "self"
    )


def is_diag(stmt: ast.stmt, suffix: str, key: str) -> bool:
    if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and is_bool_feature(stmt.value, key)):
        return False
    t = stmt.targets[0]
    return (
        isinstance(t, ast.Subscript)
        and isinstance(t.value, ast.Attribute) and t.value.attr == "diagnostics"
        and isinstance(t.value.value, ast.Name) and t.value.value.id == "self"
        and isinstance(t.slice, ast.Constant) and t.slice.value == suffix
    )


def normalize_runtime(pre_raw: bytes, post_raw: bytes, metas) -> tuple[ast.Module, ast.Module]:
    pre = parse_bytes(pre_raw, "pre-runtime.py")
    post = parse_bytes(post_raw, "post-runtime.py")
    strip_docstrings(pre); strip_docstrings(post)
    pre_features = unique_top(pre, ast.ClassDef, "Features")
    post_features = unique_top(post, ast.ClassDef, "Features")

    for key, suffix, flag in metas:
        req(not any(isinstance(n, ast.Attribute) and n.attr == key for n in ast.walk(pre)),
            f"predecessor already references new feature {key}")
        hits = [s for s in post_features.body if is_false_field(s, key)]
        req(len(hits) == 1, f"{key}: expected one Features bool=False field")
        post_features.body.remove(hits[0])

    # One authenticated install() call carries every new suffix as bool(self.features.<key>).
    install_calls = [n for n in ast.walk(post) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Name) and n.func.id == "install"]
    candidates = []
    suffixes = {suffix for _, suffix, _ in metas}
    for call in install_calls:
        names = {kw.arg for kw in call.keywords if kw.arg is not None}
        if suffixes <= names:
            candidates.append(call)
    req(len(candidates) == 1, f"expected one runtime install call carrying V4 keys, found {len(candidates)}")
    call = candidates[0]
    for key, suffix, _ in metas:
        kws = [kw for kw in call.keywords if kw.arg == suffix]
        req(len(kws) == 1 and is_bool_feature(kws[0].value, key),
            f"runtime install kwarg {suffix} is not exact bool(self.features.{key})")
        call.keywords.remove(kws[0])

    # Remove exactly one additive diagnostics line per new key, recursively.
    diag_counts = {key: 0 for key, _, _ in metas}
    def clean(stmts: list[ast.stmt]) -> list[ast.stmt]:
        out = []
        for s in stmts:
            matched = None
            for key, suffix, _ in metas:
                if is_diag(s, suffix, key):
                    matched = key; break
            if matched:
                diag_counts[matched] += 1
                continue
            if not isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                for field, value in ast.iter_fields(s):
                    if isinstance(value, list) and value and all(isinstance(x, ast.stmt) for x in value):
                        setattr(s, field, clean(value))
            else:
                # Diagnostics can live inside methods; recurse explicitly into them.
                s.body = clean(s.body)
            out.append(s)
        return out
    post.body = clean(post.body)
    req(all(v == 1 for v in diag_counts.values()), f"diagnostic counts mismatch: {diag_counts}")
    req(dump(pre) == dump(post), "runtime changes are not reducible to additive V4 field/install/diagnostic plumbing")
    return pre, post


def assert_default_off_predecessor_equivalence(pre_router: bytes, post_router: bytes,
                                                pre_runtime: bytes, post_runtime: bytes,
                                                keys) -> None:
    metas = key_meta(keys)
    normalize_router(pre_router, post_router, metas)
    normalize_runtime(pre_runtime, post_runtime, metas)




import symtable
from dataclasses import dataclass

class BindingCustodyError(RuntimeError):
    pass

@dataclass(frozen=True)
class BindingClass:
    parameter: bool
    local: bool
    global_: bool
    declared_global: bool
    nonlocal_: bool
    free: bool

def _binding(symbol: symtable.Symbol) -> BindingClass:
    return BindingClass(parameter=symbol.is_parameter(), local=symbol.is_local(), global_=symbol.is_global(), declared_global=symbol.is_declared_global(), nonlocal_=symbol.is_nonlocal(), free=symbol.is_free())

def _scope_kind(table: symtable.SymbolTable) -> str:
    value=table.get_type(); return getattr(value,'value',str(value))

def _children_by_key(table):
    out={}
    for child in table.get_children(): out.setdefault((_scope_kind(child),child.get_name()),[]).append(child)
    return out

def _compare_scope(base, head, path):
    if (_scope_kind(base),base.get_name()) != (_scope_kind(head),head.get_name()):
        raise BindingCustodyError(f'scope identity drift at {path}: {_scope_kind(base)}:{base.get_name()} -> {_scope_kind(head)}:{head.get_name()}')
    head_ids=set(head.get_identifiers())
    for name in base.get_identifiers():
        if name not in head_ids: raise BindingCustodyError(f'predecessor symbol {path}:{name!r} disappeared')
        before=_binding(base.lookup(name)); after=_binding(head.lookup(name))
        if before != after: raise BindingCustodyError(f'predecessor binding class changed at {path}:{name!r}: {before} -> {after}')
    bc=_children_by_key(base); hc=_children_by_key(head)
    if set(bc)!=set(hc): raise BindingCustodyError(f'lexical scope topology changed at {path}: missing={sorted(set(bc)-set(hc))!r} extra={sorted(set(hc)-set(bc))!r}')
    for key in sorted(bc):
        bg,hg=bc[key],hc[key]
        if len(bg)!=len(hg): raise BindingCustodyError(f'lexical scope multiplicity changed at {path}/{key}: {len(bg)} -> {len(hg)}')
        for index,(b,h) in enumerate(zip(bg,hg,strict=True)):
            kind,name=key; _compare_scope(b,h,f'{path}/{kind}:{name}[{index}]')

def require_predecessor_binding_custody(base_source:str, head_source:str, *, filename:str)->None:
    try:
        base=symtable.symtable(base_source,f'BASE:{filename}','exec'); head=symtable.symtable(head_source,f'HEAD:{filename}','exec')
    except SyntaxError as exc: raise BindingCustodyError(f'cannot build symbol table for {filename}: {exc}') from exc
    _compare_scope(base,head,f'module:{filename}')

def _binding_self_test():
    base='''VALUE = 7\nHELPER = lambda: 3\n\ndef f(flag):\n    action = flag + 1\n    return VALUE + action\n'''
    good='''VALUE = 7\nHELPER = lambda: 3\nNEW_FLAG = False\n\ndef f(flag, new_switch=None):\n    action = flag + 1\n    if NEW_FLAG:\n        import math as r04_new_helper\n        player = flag\n        state = None\n        tape = ()\n        action = action + r04_new_helper.floor(player)\n    return VALUE + action\n'''
    require_predecessor_binding_custody(base,good,filename='good.py')
    capture='''VALUE = 7\nHELPER = lambda: 3\nNEW_FLAG = False\n\ndef f(flag):\n    action = flag + 1\n    if NEW_FLAG:\n        VALUE = 9\n    return VALUE + action\n'''
    try: require_predecessor_binding_custody(base,capture,filename='capture.py')
    except BindingCustodyError: pass
    else: raise AssertionError('binding capture false-green')


def _static_apply_self_test() -> None:
    good = r'''"fixture"
import io
import json
import os
KEYS = ("r04_fixture",)
def _replace_once(text, old, new, label):
    count = text.count(old)
    assert count == 1, "%s: expected 1 match, found %d" % (label, count)
    return text.replace(old, new)
def apply(src):
    def read(name):
        return io.open(os.path.join(src, name), encoding="utf-8", newline="").read()
    def write(name, text):
        with io.open(os.path.join(src, name), "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    router = read("r04_full_router.py")
    router = _replace_once(router, "OLD", "NEW", "fixture")
    write("r04_full_router.py", router)
    runtime = read("titan_runtime.py")
    runtime = _replace_once(runtime, "RUNTIME_OLD", "RUNTIME_NEW", "runtime-fixture")
    write("titan_runtime.py", runtime)
    cfg_path = os.path.join(src, "TITAN-CONFIG.json")
    data = json.loads(io.open(cfg_path, encoding="utf-8").read())
    for key in KEYS:
        assert key not in data, key
        data[key] = False
    with io.open(cfg_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(data, indent=2) + "\n")
    return src
'''
    program = _parse_static_apply_v4(good, filename="<static-fixture>")
    out = _interpret_static_apply_v4({
        "r04_full_router.py": b"x OLD y\n",
        "titan_runtime.py": b"RUNTIME_OLD\n",
        "TITAN-CONFIG.json": b"{}\n",
    }, program)
    _require(out["r04_full_router.py"] == b"x NEW y\n"
             and out["titan_runtime.py"] == b"RUNTIME_NEW\n"
             and json.loads(out["TITAN-CONFIG.json"]) == {"r04_fixture": False},
             "static apply_v4 positive fixture failed")

    poisons = [
        good + "\nraise SystemExit(0)\n",
        good.replace("import io\n", "import io\nimport __main__\n"),
        good.replace('read("r04_full_router.py")', "read(os.environ['TARGET'])"),
        good.replace('router = _replace_once(router, "OLD", "NEW", "fixture")',
                     'if os.getenv("X"):\n        router = _replace_once(router, "OLD", "NEW", "fixture")'),
        good.replace('router = _replace_once(router, "OLD", "NEW", "fixture")',
                     'open("result.sentinel", "w").write("safe")\n    router = _replace_once(router, "OLD", "NEW", "fixture")'),
        good.replace('router = read("r04_full_router.py")', 'write = read("r04_full_router.py")')
            .replace('router = _replace_once(router, "OLD", "NEW", "fixture")',
                     'write = _replace_once(write, "OLD", "NEW", "fixture")')
            .replace('write("r04_full_router.py", router)', 'write("r04_full_router.py", write)'),
        good.replace('router = read("r04_full_router.py")', 'src = read("r04_full_router.py")')
            .replace('router = _replace_once(router, "OLD", "NEW", "fixture")',
                     'src = _replace_once(src, "OLD", "NEW", "fixture")')
            .replace('write("r04_full_router.py", router)', 'write("r04_full_router.py", src)'),
    ]
    for i, poison in enumerate(poisons):
        try:
            _parse_static_apply_v4(poison, filename=f"<poison-{i}>")
        except (_StaticApplyError, SyntaxError):
            continue
        _fail(f"static apply_v4 poison {i} false-passed")

    for raw in (b"no anchor\n", b"OLD OLD\n"):
        try:
            _interpret_static_apply_v4({"r04_full_router.py": raw, "titan_runtime.py": b"RUNTIME_OLD\n", "TITAN-CONFIG.json": b"{}\n"}, program)
        except _StaticApplyError:
            continue
        _fail("static apply_v4 missing/duplicate replacement anchor false-passed")

def _literal_keys(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    value = _bindings(tree.body).get("KEYS")
    _require(isinstance(value, ast.AST), f"{path}: KEYS is not a final literal binding")
    lit = _literal(value)
    _require(isinstance(lit, (tuple, list)) and lit, f"{path}: KEYS must be a nonempty literal tuple/list")
    keys = tuple(lit)
    _require(all(type(k) is str and k for k in keys), f"{path}: KEYS contains invalid entries")
    _require(len(keys) == len(set(keys)), f"{path}: KEYS contains duplicates")
    return keys


def _self_test() -> None:
    _static_apply_self_test()
    _materialization_self_test()
    _binding_self_test()
    _require(_static_truth(ast.parse("not True", mode="eval").body) is False, "not folding")
    _require(_static_truth(ast.parse("FLAG and False", mode="eval").body) is False, "and folding")
    _require(_static_truth(ast.parse("FLAG or True", mode="eval").body) is True, "or folding")
    _require(_static_truth(ast.parse("1 == 0", mode="eval").body) is False, "compare folding")

    compound = ast.parse("""\ndef f():\n    if True:\n        return 1\n    forbidden()\n""").body[0]
    _require(isinstance(compound, ast.FunctionDef), "fixture")
    _require(not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "forbidden"
                     for n in _live_nodes_block(compound.body)), "compound terminator false-pass")

    async_dead = ast.parse("""\nasync def f():\n    async for _ in ():\n        proof()\n    forbidden()\n""").body[0]
    _require(isinstance(async_dead, ast.AsyncFunctionDef), "fixture")
    _require(not any(isinstance(n, ast.Call) for n in _live_nodes_block(async_dead.body)), "literal AsyncFor false-pass")

    rebind = ast.parse("""\nclass TitanAgent:\n    def act(self): return None\nif True:\n    TitanAgent = object()\n""")
    _require(not isinstance(_bindings(rebind.body).get("TitanAgent"), ast.ClassDef), "final class rebind false-pass")

    decorated = ast.parse("""\nclass TitanAgent:\n    def act(self): return self._seller_state(None)\n    @staticmethod\n    def _seller_state(consumer): return consumer\n""")
    _require(len(_reachable_agent_methods(decorated, _final_class(decorated, "TitanAgent"))) == 2,
             "canonical builtin staticmethod rejected")
    shadowed = ast.parse("""\nstaticmethod = lambda f: (lambda *a: None)\nclass TitanAgent:\n    def act(self): return self._seller_state(None)\n    @staticmethod\n    def _seller_state(consumer): return consumer\n""")
    try:
        _reachable_agent_methods(shadowed, _final_class(shadowed, "TitanAgent"))
    except SystemExit:
        pass
    else:
        _fail("shadowed staticmethod false-pass")

    feat_ok = ast.parse("""\nfrom dataclasses import dataclass\n@dataclass(frozen=True)\nclass Features:\n    r04_x: bool = False\n""")
    _require(_safe_features_decorator(feat_ok, _final_class(feat_ok, "Features")),
             "canonical dataclass decorator rejected")
    feat_bad = ast.parse("""\nfrom dataclasses import dataclass\ndataclass = lambda *a, **k: (lambda c: c)\n@dataclass(frozen=True)\nclass Features:\n    r04_x: bool = False\n""")
    _require(not _safe_features_decorator(feat_bad, _final_class(feat_bad, "Features")),
             "shadowed dataclass false-pass")

    router = ast.parse("""\nFLAG=False\ndef helper(o,c=None):\n    if FLAG and c is not None:\n        import r04_x\n        action = r04_x.apply_x(o)\n        return action\n    return o\ndef v3_agent(o,c=None): return helper(o,c)\ndef install(*, x=None):\n    global FLAG\n    if x is not None:\n        FLAG=bool(x)\n    return v3_agent\n""")
    install = _final_function(router, "install")
    _require(_install_setter_ok(router, install, "FLAG", "x"), "canonical setter missed")
    root = _install_root(install)
    _require(root == "v3_agent", "install root missed")
    _require(_router_feature_seam(router, root, "FLAG", "r04_x"), "key seam missed")

    generic = ast.parse("""\nFLAG=False\ndef v3_agent(o,c=None):\n    if not (False or FLAG):\n        return o\n    return o\ndef install(*, x=None):\n    global FLAG\n    if x is not None: FLAG=bool(x)\n    return v3_agent\n""")
    _require(not _router_feature_seam(generic, "v3_agent", "FLAG", "r04_x"), "generic dispatch false-pass")

    setter_clobber = ast.parse("""\nFLAG=False\ndef install(*, x=None):\n    global FLAG\n    if x is not None: FLAG=bool(x)\n    FLAG=False\n    return v3_agent\n""")
    _require(not _install_setter_ok(setter_clobber, _final_function(setter_clobber, "install"), "FLAG", "x"),
             "later FLAG clobber false-pass")
    suffix_rebind = ast.parse("""\nFLAG=False\ndef install(*, x=None):\n    global FLAG\n    x=False\n    if x is not None: FLAG=bool(x)\n    return v3_agent\n""")
    _require(not _install_setter_ok(suffix_rebind, _final_function(suffix_rebind, "install"), "FLAG", "x"),
             "suffix rebind false-pass")

    runtime = ast.parse("""\nclass TitanAgent:\n    def act(self): return self.route()\n    def route(self):\n        from r04_full_router import install\n        output = install(x=bool(self.features.r04_x))(None, None)\n        return output\n""")
    reach = _reachable_agent_methods(runtime, _final_class(runtime, "TitanAgent"))
    _require(_runtime_install_wired(runtime, reach, "r04_x", "x"), "trusted runtime bridge missed")
    clobber = ast.parse("""\nclass TitanAgent:\n    def act(self):\n        from r04_full_router import install\n        output = install(x=bool(self.features.r04_x))(None, None)\n        output = object()\n        return output\n""")
    _require(not _runtime_install_wired(clobber, _reachable_agent_methods(clobber, _final_class(clobber, "TitanAgent")), "r04_x", "x"),
             "trusted result clobber false-pass")
    exclusive = ast.parse("""\nclass TitanAgent:\n    def act(self):\n        from r04_full_router import install\n        if self.features.r04_x:\n            output = install(x=bool(self.features.r04_x))(None, None)\n        else:\n            output = object()\n        return output\n""")
    _require(_runtime_install_wired(exclusive, _reachable_agent_methods(exclusive, _final_class(exclusive, "TitanAgent")), "r04_x", "x"),
             "exclusive sibling assignment falsely clobbered trusted result")
    stars = ast.parse("""\nclass TitanAgent:\n    def act(self):\n        from r04_full_router import install\n        return install(x=bool(self.features.r04_x), **opts)(None,None)\n""")
    _require(not _runtime_install_wired(stars, _reachable_agent_methods(stars, _final_class(stars, "TitanAgent")), "r04_x", "x"),
             "**kwargs ambiguity false-pass")

    mutate = ast.parse("""\nclass TitanAgent:\n    def __init__(self): self.features = forged\n    def act(self): return None\n""")
    methods = _class_methods(_final_class(mutate, "TitanAgent"))
    _require(_unsafe_runtime_mutation(methods["__init__"], "r04_x", set(methods)) is not None,
             "self.features replacement missed")
    shadow = ast.parse("""\nclass TitanAgent:\n    def __init__(self): self.route = lambda: None\n    def act(self): return self.route()\n    def route(self): return None\n""")
    methods = _class_methods(_final_class(shadow, "TitanAgent"))
    _require(_unsafe_runtime_mutation(methods["__init__"], "r04_x", {"act", "route"}) is not None,
             "instance method shadow missed")

    proxy = ast.parse("""\nclass TitanAgent:\n    def __init__(self): self.__dict__['features'] = forged\n    def act(self): return None\n""")
    methods = _class_methods(_final_class(proxy, "TitanAgent"))
    _require(_unsafe_runtime_mutation(methods["__init__"], "r04_x", set(methods)) is not None,
             "self.__dict__ features replacement missed")
    objset = ast.parse("""\nclass TitanAgent:\n    def __init__(self): object.__setattr__(self, 'features', forged)\n    def act(self): return None\n""")
    methods = _class_methods(_final_class(objset, "TitanAgent"))
    _require(_unsafe_runtime_mutation(methods["__init__"], "r04_x", set(methods)) is not None,
             "object.__setattr__ features replacement missed")
    ctor_ok = ast.parse("""\nclass TitanAgent:
    def __init__(self, features=None, *, fourth_quadrant_admission=None):
        self.features = features or Features()
""")
    _require(_exact_agent_ctor(_class_methods(_final_class(ctor_ok, "TitanAgent"))["__init__"]),
             "canonical TitanAgent ctor rejected")
    ctor_poison = ast.parse("""\nclass TitanAgent:
    def __init__(self, ignored, features=Features(r04_x=True), *, fourth_quadrant_admission=None):
        self.features = features or Features()
""")
    _require(not _exact_agent_ctor(_class_methods(_final_class(ctor_poison, "TitanAgent"))["__init__"]),
             "constructor parameter-binding poison false-pass")
    fmut = ast.parse("""\nclass Features:\n    r04_x = False\n    def __post_init__(self): object.__setattr__(self, 'r04_x', True)\n""")
    fpost = _class_methods(_final_class(fmut, "Features"))["__post_init__"]
    _require(_unsafe_features_mutation(fpost, "r04_x") is not None,
             "Features __post_init__ mutation missed")
    fproxy = ast.parse("""\nclass Features:
    r04_x = False
    def __post_init__(self):
        d = vars(self)
        d['r04_x'] = True
""")
    fproxy_post = _class_methods(_final_class(fproxy, "Features"))["__post_init__"]
    _require(_unsafe_features_mutation(fproxy_post, "r04_x") is not None,
             "aliased vars(self) Features proxy poison false-pass")
    rproxy = ast.parse("""\nclass TitanAgent:
    def act(self):
        d = vars(self.features)
        d['r04_x'] = True
        return None
""")
    rproxy_act = _class_methods(_final_class(rproxy, "TitanAgent"))["act"]
    _require(_unsafe_runtime_mutation(rproxy_act, "r04_x", {"act"}) is not None,
             "aliased vars(self.features) runtime proxy poison false-pass")
    hook_assign = ast.parse("""\nclass Features:
    __bool__ = evil
""")
    _require(_class_binds(_final_class(hook_assign, "Features"), "__bool__"),
             "class-scope Features.__bool__ assignment poison missed")
    type_patch = ast.parse("""\nclass Features: pass
type.__setattr__(Features, '__bool__', evil)
""")
    _require(_post_class_attribute_write(type_patch, "Features", {"__bool__"}) is not None,
             "type.__setattr__ post-class hook poison false-pass")
    dyn_patch = ast.parse("""\nclass TitanAgent: pass
setattr(TitanAgent, name, evil)
""")
    _require(_post_class_attribute_write(dyn_patch, "TitanAgent", {"act"}) is not None,
             "dynamic post-class protected-name poison false-pass")

    canonical_main = b"canonical-main-bytes\n"
    _require(_entrypoint_bytes_ok(canonical_main, canonical_main),
             "canonical entrypoint bytes rejected")
    _require(not _entrypoint_bytes_ok(canonical_main + b"# overlay poison\n", canonical_main),
             "overlay main replacement false-pass")
    _require(not _entrypoint_bytes_ok(canonical_main.replace(b"canonical", b"forced-on"), canonical_main),
             "apply_v4 main rewrite false-pass")

    try_finally = ast.parse("""
def f():
    try:
        return 1
    finally:
        pass
    forbidden()
""").body[0]
    _require(isinstance(try_finally, ast.FunctionDef) and not any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "forbidden"
        for n in _live_nodes_block(try_finally.body)), "try/finally termination false-pass")
    infinite = ast.parse("""
def f():
    while True:
        work()
    forbidden()
""").body[0]
    _require(isinstance(infinite, ast.FunctionDef) and not any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "forbidden"
        for n in _live_nodes_block(infinite.body)), "while True fallthrough false-pass")
    suppressible = ast.parse("""
def f(cm):
    with cm:
        raise RuntimeError()
    proof()
""").body[0]
    _require(isinstance(suppressible, ast.FunctionDef) and any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "proof"
        for n in _live_nodes_block(suppressible.body)), "with-body raise incorrectly killed tail")

    dead_handler = ast.parse("""\ndef f():\n    try:\n        return 1\n    except Exception:\n        proof()\n    forbidden()\n""").body[0]
    _require(isinstance(dead_handler, ast.FunctionDef) and not any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "proof"
        for n in _live_nodes_block(dead_handler.body)), "dead try handler/tail false-pass")

    local_root = ast.parse("""\ndef install():\n    v3_agent = fake\n    return v3_agent\n""")
    _require(_install_root(_final_function(local_root, "install")) is None,
             "install local-root shadow false-pass")

    binds = ast.parse("""\ndef f(v):\n    if (x := v): pass\n    match v:\n        case {'k': y}: pass\n    return x, y\n""").body[0]
    _require(isinstance(binds, ast.FunctionDef) and {"x", "y"}.issubset(_function_local_names(binds)),
             "walrus/match binding extraction missed")


def check(base_apply_v4: Path) -> None:
    _self_test()
    try:
        base_source = _decode_canonical_python_bytes(base_apply_v4.read_bytes(), str(base_apply_v4))
        head_source = _decode_canonical_python_bytes(APPLY_V4.read_bytes(), str(APPLY_V4))
        base_program = _parse_static_apply_v4(base_source, filename=str(base_apply_v4))
        head_program = _parse_static_apply_v4(head_source, filename=str(APPLY_V4))
    except _StaticApplyError as exc:
        _fail(f"static apply_v4 grammar rejection: {exc}")
    base_keys = base_program[0]
    head_keys = head_program[0]
    it = iter(head_keys)
    _require(all(any(candidate == key for candidate in it) for key in base_keys),
             "V4 recomposition reordered/removed already-landed key(s)")
    new_keys = tuple(key for key in head_keys if key not in set(base_keys))

    pre_v4, canonical_main = _trusted_pre_v4_package(base_apply_v4, head_keys)
    try:
        base_files = _interpret_static_apply_v4(pre_v4, base_program)
        files = _interpret_static_apply_v4(pre_v4, head_program)
    except _StaticApplyError as exc:
        _fail(f"static apply_v4 interpretation failed: {exc}")

    # Existing config semantics are frozen; HEAD may only add literal-False new keys.
    base_cfg = json.loads(base_files["TITAN-CONFIG.json"].decode("utf-8"))
    head_cfg = json.loads(files["TITAN-CONFIG.json"].decode("utf-8"))
    projected_cfg = dict(head_cfg)
    for key in new_keys:
        _require(projected_cfg.pop(key, _UNKNOWN) is False, f"{key}: new config key not exact False")
    _require(projected_cfg == base_cfg, "HEAD changed predecessor TITAN-CONFIG semantics")

    for target in ("r04_full_router.py", "titan_runtime.py"):
        _decode_canonical_python_bytes(base_files[target], "BASE:" + target)
        _decode_canonical_python_bytes(files[target], "HEAD:" + target)
    if new_keys:
        try:
            assert_default_off_predecessor_equivalence(
                base_files["r04_full_router.py"], files["r04_full_router.py"],
                base_files["titan_runtime.py"], files["titan_runtime.py"], new_keys)
            require_predecessor_binding_custody(
                _decode_canonical_python_bytes(base_files["r04_full_router.py"], "BASE:r04_full_router.py"),
                _decode_canonical_python_bytes(files["r04_full_router.py"], "HEAD:r04_full_router.py"),
                filename="r04_full_router.py")
            require_predecessor_binding_custody(
                _decode_canonical_python_bytes(base_files["titan_runtime.py"], "BASE:titan_runtime.py"),
                _decode_canonical_python_bytes(files["titan_runtime.py"], "HEAD:titan_runtime.py"),
                filename="titan_runtime.py")
        except (V4MonotonicityError, BindingCustodyError) as exc:
            _fail(f"default-OFF predecessor equivalence failed: {exc}")
    for name in ("TITAN-CONFIG.json", "titan_runtime.py", "r04_full_router.py", "main.py"):
        _require(name in files, f"materialized package missing {name}")
    config = json.loads(files["TITAN-CONFIG.json"].decode("utf-8"))
    runtime = ast.parse(_decode_canonical_python_bytes(files["titan_runtime.py"], "titan_runtime.py"), filename="titan_runtime.py")
    router = ast.parse(_decode_canonical_python_bytes(files["r04_full_router.py"], "r04_full_router.py"), filename="r04_full_router.py")
    _require(_entrypoint_bytes_ok(files["main.py"], canonical_main),
             "bootstrap V1 requires final materialized main.py byte-identical to digest-pinned canonical main.py")

    features = _final_class(runtime, "Features")
    agent = _final_class(runtime, "TitanAgent")
    _require(_plain_class(features), "Features bases/metaclass are not allowed")
    _require(_plain_class(agent), "TitanAgent bases/metaclass are not allowed")
    _require(_safe_features_decorator(runtime, features), "Features has an untrusted decorator")
    _require(not agent.decorator_list, "TitanAgent has a decorator")
    feature_defaults = _feature_defaults(features)
    feature_methods = _class_methods(features)
    dangerous_feature_hooks = {"__bool__", "__len__", "__setattr__", "__delattr__", "__getattr__", "__getattribute__"}
    bound_feature_hooks = {name for name in dangerous_feature_hooks if _class_binds(features, name)}
    _require(not bound_feature_hooks,
             "Features may not bind truthiness/attribute-proxy hooks under effective-OFF custody: "
             + ", ".join(sorted(bound_feature_hooks)))
    feature_post = feature_methods.get("__post_init__")
    methods = _class_methods(agent)
    ctor = methods.get("__init__")
    _require(ctor is not None and _exact_agent_ctor(ctor),
             "TitanAgent.__init__ must retain exact canonical features parameter binding/root assignment")
    reachable = _reachable_agent_methods(runtime, agent)
    protected_methods = {fn.name for fn in reachable}

    post = _post_class_attribute_write(runtime, "TitanAgent", protected_methods)
    _require(post is None, f"post-class TitanAgent.{post} monkeypatch is not allowed")
    postf = _post_class_attribute_write(runtime, "Features", set(head_keys) | dangerous_feature_hooks | {"__post_init__"})
    _require(postf is None, f"post-class Features.{postf} mutation is not allowed")

    mutation_surfaces = set(reachable)
    for name in ("__init__", "__post_init__"):
        if name in methods: mutation_surfaces.add(methods[name])

    install = _final_function(router, "install")
    root = _install_root(install)
    _require(root is not None, "router install() must return/select one audited production root")
    _final_function(router, root)
    router_bindings = _bindings(router.body)

    for key in head_keys:
        _require(key in config and type(config[key]) is bool and config[key] is False,
                 f"{key}: bootstrap V1 requires materialized config False")
        _require(key in feature_defaults and type(feature_defaults[key]) is bool and feature_defaults[key] is False,
                 f"{key}: Features default must remain False")
        if feature_post is not None:
            reason = _unsafe_features_mutation(feature_post, key)
            _require(reason is None, f"{key}: effective-OFF Features.__post_init__ violation: {reason}")
        for fn in mutation_surfaces:
            reason = _unsafe_runtime_mutation(fn, key, protected_methods)
            _require(reason is None, f"{key}: effective-OFF custody violation in {fn.name}: {reason}")

        if not key.startswith("r04_"):
            _require(any(_is_self_feature(n, key) and isinstance(n.ctx, ast.Load)
                         for fn in reachable for n in _live_nodes_block(fn.body)),
                     f"{key}: live TitanAgent path never reads self.features.{key}")
            continue

        suffix = key.removeprefix("r04_"); flag = suffix.upper()
        binding = router_bindings.get(flag)
        _require(isinstance(binding, ast.AST) and type(_literal(binding)) is bool and _literal(binding) is False,
                 f"{key}: router {flag} must be final source-default False")
        keywordable = {a.arg for a in (*install.args.args, *install.args.kwonlyargs)}
        positional_only = {a.arg for a in install.args.posonlyargs}
        _require(suffix in keywordable and suffix not in positional_only,
                 f"{key}: install({suffix}=...) must be keyword-callable")
        _require(_global_declared(install, flag), f"{key}: install() missing global {flag}")
        _require(_install_setter_ok(router, install, flag, suffix),
                 f"{key}: install() setter is not sealed FLAG=bool(suffix) under suffix is not None")
        _require(_router_feature_seam(router, root, flag, key),
                 f"{key}: no positive live {flag}-gated matching {key} behavior transform")
        _require(_runtime_install_wired(runtime, reachable, key, suffix),
                 f"{key}: live TitanAgent chain lacks sealed trusted r04_full_router.install({suffix}=bool(self.features.{key})) action path")

    print("V4 PLUMBING OK", "base", list(base_keys), "head", list(head_keys),
          "mode", "bootstrap-all-off", "root", root,
          "reachable_agent_methods", sorted(fn.name for fn in reachable))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-apply-v4", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        _self_test(); print("V4 PLUMBING SELF-TEST OK"); return
    _require(args.base_apply_v4 is not None, "--base-apply-v4 is required")
    check(args.base_apply_v4)


if __name__ == "__main__":
    main()
