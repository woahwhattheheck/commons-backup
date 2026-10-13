#!/usr/bin/env python3
"""#12620 support donor: scope-pruned E184 bridge call collection.

This is deliberately NOT a liveness engine.  The sole checker passes its existing
hardened live/outcome iterator in as ``live_nodes``.  This helper only answers a
narrow question for each statement the incumbent engine has already admitted:
which direct Name(...) calls occur in that same lexical scope, without letting a
nested def/class/lambda forge an E184 bridge edge.
"""
from __future__ import annotations

import ast
from collections.abc import Callable, Iterable, Iterator


class ScopeBridgeError(RuntimeError):
    pass


def req(condition: bool, message: str) -> None:
    if not condition:
        raise ScopeBridgeError(message)


def _calls_in_live_statement(stmt: ast.stmt, wanted: frozenset[str]) -> tuple[ast.Call, ...]:
    """Collect wanted direct Name(...) calls from one already-live statement.

    Important boundaries:
    * child statement bodies are never traversed here; the incumbent live/outcome
      iterator owns those control-flow decisions and will yield admitted children;
    * nested function/class bodies and lambda bodies are lexical-scope barriers;
    * expression trees attached directly to the live statement are traversed;
      eager comprehensions are visited normally, while generator expressions
      expose only their outermost iterable at construction time. Their element,
      filters, and later iterators are deferred until iteration and cannot prove
      an E184 bridge edge merely because the generator object is constructed.

    Treating a nested def/class statement itself as a bridge source would let a
    dead lexical decoy certify `_v3_core -> _v3_stack`, `Policy.act ->
    advance_sales`, etc.  Therefore a barrier statement yields no bridge calls.
    """
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return ()

    found: list[ast.Call] = []

    class Visitor(ast.NodeVisitor):
        def generic_visit(self, node: ast.AST) -> None:
            for _field, value in ast.iter_fields(node):
                if isinstance(value, ast.stmt):
                    # Child statements are owned by live_nodes(), not this walker.
                    continue
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, ast.stmt):
                            continue
                        if isinstance(item, ast.AST):
                            self.visit(item)
                    continue
                if isinstance(value, ast.AST):
                    self.visit(value)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            return

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            return

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            return

        def visit_Lambda(self, node: ast.Lambda) -> None:
            return

        def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
            # Python evaluates only the outermost iterable when constructing a
            # generator expression. The element, filters, and later generator
            # clauses are deferred until iteration, which this collector does
            # not prove. Preserve calls in the eager outer iterable only.
            if node.generators:
                self.visit(node.generators[0].iter)
            return

        def visit_Call(self, node: ast.Call) -> None:
            if isinstance(node.func, ast.Name) and node.func.id in wanted:
                found.append(node)
            self.generic_visit(node)

    Visitor().visit(stmt)
    return tuple(found)


def scope_pruned_calls(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    name: str,
    live_nodes: Callable[[Iterable[ast.stmt]], Iterable[ast.stmt]],
) -> tuple[ast.Call, ...]:
    """Use the incumbent liveness engine, then collect only same-scope calls."""
    req(type(name) is str and bool(name), "bridge name must be a non-empty string")
    out: list[ast.Call] = []
    wanted = frozenset({name})
    for stmt in live_nodes(fn.body):
        req(isinstance(stmt, ast.stmt), "live_nodes yielded non-statement")
        out.extend(_calls_in_live_statement(stmt, wanted))
    return tuple(out)


def scope_pruned_call_names(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    candidates: Iterable[str],
    live_nodes: Callable[[Iterable[ast.stmt]], Iterable[ast.stmt]],
) -> frozenset[str]:
    """Return direct candidate call names in the same lexical scope only."""
    wanted = frozenset(candidates)
    req(all(type(name) is str and name for name in wanted), "invalid bridge candidate")
    out: set[str] = set()
    for stmt in live_nodes(fn.body):
        req(isinstance(stmt, ast.stmt), "live_nodes yielded non-statement")
        for call in _calls_in_live_statement(stmt, wanted):
            req(isinstance(call.func, ast.Name), "collector produced non-Name call")
            out.add(call.func.id)
    return frozenset(out)


def _fixture_fn(source: str, name: str = "f") -> ast.FunctionDef:
    tree = ast.parse(source)
    found = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    req(len(found) == 1, f"fixture expected one {name}")
    return found[0]


def _flat_live(body: Iterable[ast.stmt]) -> Iterator[ast.stmt]:
    """Self-test stand-in only; production must supply incumbent hardened liveness."""
    yield from body


def self_test() -> None:
    checks = [0]

    def check(condition: bool, label: str) -> None:
        checks[0] += 1
        req(condition, label)

    direct = _fixture_fn("""
def f(x):
    return target(x)
""")
    check(len(scope_pruned_calls(direct, "target", _flat_live)) == 1,
          "direct bridge call was missed")

    nested_def = _fixture_fn("""
def f(x):
    def decoy():
        return target(x)
    return x
""")
    check(not scope_pruned_calls(nested_def, "target", _flat_live),
          "nested local def forged bridge edge")

    nested_async = _fixture_fn("""
def f(x):
    async def decoy():
        return target(x)
    return x
""")
    check(not scope_pruned_calls(nested_async, "target", _flat_live),
          "nested async def forged bridge edge")

    nested_class = _fixture_fn("""
def f(x):
    class Decoy:
        def method(self):
            return target(x)
    return x
""")
    check(not scope_pruned_calls(nested_class, "target", _flat_live),
          "nested class forged bridge edge")

    nested_lambda = _fixture_fn("""
def f(x):
    decoy = lambda: target(x)
    return x
""")
    check(not scope_pruned_calls(nested_lambda, "target", _flat_live),
          "lambda body forged bridge edge")

    # Call in an expression directly owned by an already-live statement remains.
    comprehension = _fixture_fn("""
def f(xs):
    return [target(x) for x in xs]
""")
    check(len(scope_pruned_calls(comprehension, "target", _flat_live)) == 1,
          "executed comprehension bridge call was pruned")

    generator_element = _fixture_fn("""
def f(xs):
    return (target(x) for x in xs)
""")
    check(not scope_pruned_calls(generator_element, "target", _flat_live),
          "deferred generator element forged bridge edge")

    generator_filter = _fixture_fn("""
def f(xs):
    return (x for x in xs if target(x))
""")
    check(not scope_pruned_calls(generator_filter, "target", _flat_live),
          "deferred generator filter forged bridge edge")

    generator_later_iter = _fixture_fn("""
def f(xs):
    return (y for x in xs for y in target(x))
""")
    check(not scope_pruned_calls(generator_later_iter, "target", _flat_live),
          "deferred later generator iterable forged bridge edge")

    generator_outer_iter = _fixture_fn("""
def f(xs):
    return (x for x in target(xs))
""")
    check(len(scope_pruned_calls(generator_outer_iter, "target", _flat_live)) == 1,
          "eager generator outer iterable bridge call was pruned")

    # Parent-edge selection must ignore nested decoys while retaining the direct edge.
    parent = _fixture_fn("""
def f(x):
    def decoy():
        return P_BAD(x)
    return P_GOOD(x)
""")
    check(scope_pruned_call_names(parent, {"P_BAD", "P_GOOD"}, _flat_live) == frozenset({"P_GOOD"}),
          "parent-edge name set was forged by nested def")

    # The collector must not recurse into child statement bodies on its own.  This
    # is what prevents it from bypassing the incumbent liveness engine.
    guarded = _fixture_fn("""
def f(x):
    if flag:
        return target(x)
    return x
""")
    check(not scope_pruned_calls(guarded, "target", _flat_live),
          "collector bypassed liveness owner by descending child statement body")

    # Exact E184 bridge-family decoys from the correction.
    for caller, callee in [
        ("_v3_core", "_v3_stack"),
        ("_v3_stack", "POLICY_AGENT"),
        ("generated_parent", "_OLDER_PARENT"),
        ("policy_act", "advance_sales"),
    ]:
        fn = _fixture_fn(f"""
def f(x):
    def decoy():
        return {callee}(x)
    return x
""")
        check(not scope_pruned_calls(fn, callee, _flat_live),
              f"{caller}->{callee} nested-def poison false-passed")

    if checks[0] != 16:
        raise ScopeBridgeError(f"self-test vector count mismatch: {checks[0]} != 16")


if __name__ == "__main__":
    self_test()
    print("#12620 E184 SCOPE-PRUNED BRIDGE DONOR SELF-TEST OK (16 explicit checks)")
