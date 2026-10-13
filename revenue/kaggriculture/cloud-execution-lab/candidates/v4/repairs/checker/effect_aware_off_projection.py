from __future__ import annotations

import ast
import copy
from collections.abc import Iterable


def _is_bool_constant(node: ast.AST, value: bool | None = None) -> bool:
    if not isinstance(node, ast.Constant) or type(node.value) is not bool:
        return False
    return value is None or node.value is value


class _OffSubstituter(ast.NodeTransformer):
    def __init__(self, off_names: frozenset[str]):
        self.off_names = off_names

    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Load) and node.id in self.off_names:
            return ast.copy_location(ast.Constant(False), node)
        return node


def _subst_value(node: ast.expr, off_names: frozenset[str]) -> ast.expr:
    return _OffSubstituter(off_names).visit(copy.deepcopy(node))


def _fold_truth_expr(node: ast.expr, off_names: frozenset[str]) -> ast.expr:
    """Substitute OFF flags and simplify only in a truth-consumed context.

    BoolOp simplification is evaluation-order preserving: a decisive constant may
    discard only operands to its RIGHT. Operands to its left remain unless they
    are literal booleans, so an effectful prefix can never disappear.
    """
    node = copy.deepcopy(node)

    def fold(expr: ast.expr) -> ast.expr:
        if isinstance(expr, ast.Name) and isinstance(expr.ctx, ast.Load) and expr.id in off_names:
            return ast.copy_location(ast.Constant(False), expr)

        if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not):
            operand = fold(expr.operand)
            if _is_bool_constant(operand):
                return ast.copy_location(ast.Constant(not operand.value), expr)
            expr.operand = operand
            return expr

        if isinstance(expr, ast.BoolOp):
            values = [fold(value) for value in expr.values]
            kept: list[ast.expr] = []
            if isinstance(expr.op, ast.And):
                for value in values:
                    if _is_bool_constant(value, True):
                        continue
                    kept.append(value)
                    if _is_bool_constant(value, False):
                        break
                if not kept:
                    return ast.copy_location(ast.Constant(True), expr)
            else:
                for value in values:
                    if _is_bool_constant(value, False):
                        continue
                    kept.append(value)
                    if _is_bool_constant(value, True):
                        break
                if not kept:
                    return ast.copy_location(ast.Constant(False), expr)
            if len(kept) == 1:
                return ast.copy_location(kept[0], expr)
            expr.values = kept
            return expr

        if isinstance(expr, ast.IfExp):
            test = fold(expr.test)
            body = fold(expr.body)
            orelse = fold(expr.orelse)
            if _is_bool_constant(test):
                return ast.copy_location(body if test.value else orelse, expr)
            expr.test, expr.body, expr.orelse = test, body, orelse
            return expr

        # Value-producing subexpressions (Call args, Compare operands, arithmetic,
        # attribute/subscript expressions, etc.) are NOT boolean-folded. Only
        # substitute authenticated OFF names. This avoids changing e.g. the value
        # of `0 or False` when it is passed to a function rather than truth-tested.
        return _subst_value(expr, off_names)

    return fold(node)


def project_statements_off(statements: Iterable[ast.stmt], new_flags: Iterable[str]) -> list[ast.stmt]:
    off = frozenset(new_flags)

    def block(items: Iterable[ast.stmt]) -> list[ast.stmt]:
        out: list[ast.stmt] = []
        for original in items:
            stmt = copy.deepcopy(original)
            if isinstance(stmt, ast.If):
                test = _fold_truth_expr(stmt.test, off)
                if _is_bool_constant(test):
                    out.extend(block(stmt.body if test.value else stmt.orelse))
                    continue
                stmt.test = test
                stmt.body = block(stmt.body)
                stmt.orelse = block(stmt.orelse)
                out.append(stmt)
                continue
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                stmt.body = block(stmt.body)
            out.append(stmt)
        return out

    return block(statements)


def _dump(source: str, flags=("NEW_FLAG",)) -> str:
    tree = ast.parse(source)
    tree.body = project_statements_off(tree.body, flags)
    ast.fix_missing_locations(tree)
    return ast.dump(tree, include_attributes=False)


def _req(condition: bool, message: str, checks: list[int]) -> None:
    checks[0] += 1
    if not condition:
        raise AssertionError(message)


def self_test() -> None:
    checks = [0]
    base = """
def route(action, cfg):
    if EXISTING:
        action = old(action)
    return action
"""
    additive = """
def route(action, cfg):
    if EXISTING or NEW_FLAG:
        action = old(action)
    if NEW_FLAG and cfg is not None:
        action = apply_new(action)
    return action
"""
    _req(_dump(additive) == _dump(base), "valid OFF-inert additive seam did not reduce to BASE", checks)

    side_effect_predecessor = """
def route(action, cfg):
    if (action.update({'__v4_poison__': 1}) or True) and EXISTING:
        action = old(action)
    return action
"""
    _req(_dump(side_effect_predecessor) != _dump(base), "effectful predecessor prefix was erased", checks)

    side_effect_new_seam = """
def route(action, cfg):
    if EXISTING:
        action = old(action)
    if (side_effect() or True) and NEW_FLAG:
        action = apply_new(action)
    return action
"""
    _req(_dump(side_effect_new_seam) != _dump(base), "effect before OFF flag was erased", checks)

    safe_short_circuit = """
def route(action, cfg):
    if EXISTING or False or NEW_FLAG:
        action = old(action)
    if False and side_effect():
        action = never(action)
    if NEW_FLAG and side_effect():
        action = never2(action)
    return action
"""
    _req(_dump(safe_short_circuit) == _dump(base), "safe leftmost short-circuit did not normalize", checks)

    narrowed_old_behavior = """
def route(action, cfg):
    if EXISTING and NEW_FLAG:
        action = old(action)
    return action
"""
    _req(_dump(narrowed_old_behavior) != _dump(base), "new flag silently disabled predecessor behavior", checks)

    # Value-context boolean expressions must not be algebraically folded: Python
    # BoolOps return operands, not booleans.  Only authenticated flag substitution
    # is legal beneath Call/Compare/arithmetic value contexts.
    value_context = _fold_truth_expr(
        ast.parse("if sink((0 or NEW_FLAG)):\n    pass\n").body[0].test,
        frozenset({"NEW_FLAG"}),
    )
    _req("BoolOp" in ast.dump(value_context), "value-context BoolOp was unsafely simplified", checks)

    left_or = _fold_truth_expr(
        ast.parse("if side_effect() or True:\n    pass\n").body[0].test,
        frozenset({"NEW_FLAG"}),
    )
    _req(isinstance(left_or, ast.BoolOp) and len(left_or.values) == 2, "OR lost effectful left prefix", checks)

    left_and = _fold_truth_expr(
        ast.parse("if side_effect() and False:\n    pass\n").body[0].test,
        frozenset({"NEW_FLAG"}),
    )
    _req(isinstance(left_and, ast.BoolOp) and len(left_and.values) == 2, "AND lost effectful left prefix", checks)

    # This count is itself checked with an explicit branch, so optimized mode
    # cannot silently erase the vector oracle the way assert-only tests do.
    if checks[0] != 8:
        raise AssertionError(f"self-test vector count mismatch: {checks[0]} != 8")


if __name__ == "__main__":
    self_test()
    print("#12620 EFFECT-AWARE OFF-PROJECTION SELF-TEST OK (8 explicit checks)")
