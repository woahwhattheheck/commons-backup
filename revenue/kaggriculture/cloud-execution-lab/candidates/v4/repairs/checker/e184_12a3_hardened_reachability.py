#!/usr/bin/env python3
"""#12620 support donor: E184 reachability/capture theorem for exact 12a3.

DONOR ONLY.  This does not replace the incumbent checker, liveness engine, or
control-flow model.  Production integration passes exact 12a3 helpers:

    check_e184_runtime_reason(runtime_src, _live_nodes_block, _function_local_names)

The theorem proves the live V4 R04 production topology reaches E184's final
sale-advance semantics through the actual source-order captures, while rejecting
nested/local bridge-name decoys.  Candidate Python is never executed.
"""
from __future__ import annotations

import ast
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass


PARENT_NAME = re.compile(r"^_(?:V[0-9A-Z]+|SALE)_PARENT$")
_FN = ast.FunctionDef | ast.AsyncFunctionDef


class E184Reject(RuntimeError):
    pass


def req(condition: bool, message: str) -> None:
    if not condition:
        raise E184Reject(message)


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


def _top_level_bound_names(stmt: ast.stmt) -> set[str]:
    """Names bound by this module statement, excluding deferred lexical bodies."""
    out: set[str] = set()

    class V(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            out.add(node.name)
        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            out.add(node.name)
        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            out.add(node.name)
        def visit_Lambda(self, node: ast.Lambda) -> None:
            return
        def visit_Name(self, node: ast.Name) -> None:
            if isinstance(node.ctx, ast.Store):
                out.add(node.id)
        def visit_alias(self, node: ast.alias) -> None:
            out.add(node.asname or node.name.split('.', 1)[0])
        def visit_Global(self, node: ast.Global) -> None:
            return
        def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
            return

    V().visit(stmt)
    return out


def _simple_name_targets(stmt: ast.Assign) -> list[str] | None:
    names: list[str] = []
    for target in stmt.targets:
        if not isinstance(target, ast.Name):
            return None
        names.append(target.id)
    return names


@dataclass(frozen=True)
class ModuleState:
    final: dict[str, ast.AST]
    captures: dict[str, _FN]
    native_advance: _FN
    native_capture_lineno: int
    final_advance: _FN
    policy_class: ast.ClassDef


def _module_state(tree: ast.Module) -> ModuleState:
    """Replay relevant module bindings in source order, fail closed on custody ambiguity."""
    cur: dict[str, ast.AST] = {}
    captures: dict[str, _FN] = {}
    advance_defs: list[_FN] = []
    native: _FN | None = None
    native_line = -1
    protected_exact = {"POLICY_AGENT", "_SALE_NATIVE_ADVANCE"}

    def protected_name(name: str) -> bool:
        return name in protected_exact or bool(PARENT_NAME.match(name))

    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = stmt.name
            if protected_name(name):
                raise E184Reject(f"protected capture name {name} rebound by definition")
            cur[name] = stmt
            if name == "advance_sales" and isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                advance_defs.append(stmt)
            continue

        if isinstance(stmt, ast.Assign):
            targets = _simple_name_targets(stmt)
            bound = set().union(*(_target_names(t) for t in stmt.targets)) if stmt.targets else set()
            if targets is None:
                if any(protected_name(n) or n in {"advance_sales", "Policy"} for n in bound):
                    raise E184Reject("compound binding touches E184 custody name")
                continue

            value_obj: ast.AST | None = None
            if isinstance(stmt.value, ast.Name):
                value_obj = cur.get(stmt.value.id)

            for name in targets:
                if name in captures or (name == "_SALE_NATIVE_ADVANCE" and native is not None):
                    raise E184Reject(f"protected capture {name} rebound")

                if name == "_SALE_NATIVE_ADVANCE":
                    if not (isinstance(stmt.value, ast.Name) and stmt.value.id == "advance_sales"):
                        raise E184Reject("native sale capture is not exact advance_sales name")
                    if len(advance_defs) != 1 or value_obj is not advance_defs[0]:
                        raise E184Reject("native sale capture does not bind unique pre-E184 advance_sales")
                    native = advance_defs[0]
                    native_line = stmt.lineno

                if name == "POLICY_AGENT" or PARENT_NAME.match(name):
                    if not isinstance(value_obj, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        raise E184Reject(f"{name} does not capture a live function identity")
                    captures[name] = value_obj

                # Ordinary simple assignment updates the module's current binding.
                if value_obj is not None:
                    cur[name] = value_obj
                else:
                    cur[name] = stmt.value
            continue

        if isinstance(stmt, ast.Delete):
            for target in stmt.targets:
                for name in _target_names(target):
                    if protected_name(name):
                        raise E184Reject(f"protected capture {name} deleted")
                    cur.pop(name, None)
            continue

        bound = _top_level_bound_names(stmt)
        if any(protected_name(n) or n in {"advance_sales", "Policy"} for n in bound):
            raise E184Reject("noncanonical module binding touches E184 custody name")

    req(native is not None and native_line > 0, "missing source-order _SALE_NATIVE_ADVANCE capture")
    final_advance = cur.get("advance_sales")
    req(isinstance(final_advance, (ast.FunctionDef, ast.AsyncFunctionDef)), "final advance_sales is not a function")
    req(final_advance is not native, "final advance_sales never replaced native function")
    req(final_advance.lineno > native_line, "final advance_sales is not after native capture")
    policy = cur.get("Policy")
    req(isinstance(policy, ast.ClassDef), "final Policy binding is not a class")
    req("POLICY_AGENT" in captures, "missing source-order POLICY_AGENT function capture")
    return ModuleState(cur, captures, native, native_line, final_advance, policy)


def _direct_name_calls(
    fn: _FN,
    target: str,
    live_nodes: Callable[[Iterable[ast.stmt]], Iterable[ast.AST]],
    local_names: Callable[[_FN], set[str]],
) -> tuple[ast.Call, ...]:
    # If Python resolves target locally, a syntactically matching Name call is not
    # evidence for the audited module/capture edge.
    if target in local_names(fn):
        return ()
    return tuple(
        node for node in live_nodes(fn.body)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == target
    )


def _has_exact_policy_return(
    fn: _FN,
    live_nodes: Callable[[Iterable[ast.stmt]], Iterable[ast.AST]],
    local_names: Callable[[_FN], set[str]],
) -> bool:
    if "_POLICY" in local_names(fn):
        return False
    for node in live_nodes(fn.body):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if call.keywords or len(call.args) != 1:
            continue
        func = call.func
        if not (isinstance(func, ast.Attribute) and func.attr == "act"):
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "_POLICY"):
            continue
        if isinstance(call.args[0], ast.Name) and call.args[0].id == "observation":
            return True
    return False


def _resolve_captured_agent(
    fn: _FN,
    captures: dict[str, _FN],
    live_nodes: Callable[[Iterable[ast.stmt]], Iterable[ast.AST]],
    local_names: Callable[[_FN], set[str]],
    seen: set[int] | None = None,
) -> bool:
    seen = set() if seen is None else seen
    if id(fn) in seen:
        return False
    seen.add(id(fn))
    if _has_exact_policy_return(fn, live_nodes, local_names):
        return True
    edges: set[_FN] = set()
    locals_ = local_names(fn)
    for name, target in captures.items():
        if name == "POLICY_AGENT" or name in locals_:
            continue
        if _direct_name_calls(fn, name, live_nodes, local_names):
            edges.add(target)
    return len(edges) == 1 and _resolve_captured_agent(next(iter(edges)), captures, live_nodes, local_names, seen)


def _class_method(cls: ast.ClassDef, name: str) -> _FN:
    found = [node for node in cls.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    req(len(found) == 1, f"Policy must contain exactly one {name} method")
    req(not found[0].decorator_list, f"Policy.{name} must be undecorated")
    return found[0]


def _args_exact(fn: _FN, names: tuple[str, ...]) -> bool:
    if fn.args.posonlyargs or fn.args.vararg or fn.args.kwarg or fn.args.kwonlyargs or fn.args.defaults or fn.args.kw_defaults:
        return False
    return tuple(arg.arg for arg in fn.args.args) == names


def _exact_native_delegate(
    final: _FN,
    native_capture_lineno: int,
    local_names: Callable[[_FN], set[str]],
) -> bool:
    """Prove the final E184 advance keeps the native pre-288 path exactly."""
    if final.lineno <= native_capture_lineno:
        return False
    if not _args_exact(final, ("action", "view", "state", "tape", "step")):
        return False
    locals_ = local_names(final)
    if "_SALE_NATIVE_ADVANCE" in locals_ or "ADVANCE_START" in locals_:
        return False
    body = list(final.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    if not body or not isinstance(body[0], ast.If):
        return False
    gate = body[0]
    if gate.orelse or len(gate.body) != 1 or not isinstance(gate.body[0], ast.Return):
        return False
    test = gate.test
    if not (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name) and test.left.id == "step"
        and len(test.ops) == 1 and isinstance(test.ops[0], ast.Lt)
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Name) and test.comparators[0].id == "ADVANCE_START"
    ):
        return False
    call = gate.body[0].value
    if not isinstance(call, ast.Call) or call.keywords:
        return False
    if not (isinstance(call.func, ast.Name) and call.func.id == "_SALE_NATIVE_ADVANCE"):
        return False
    if tuple(arg.id for arg in call.args if isinstance(arg, ast.Name)) != ("action", "view", "state", "tape", "step"):
        return False
    if len(call.args) != 5 or not all(isinstance(arg, ast.Name) for arg in call.args):
        return False
    return True


def check_e184_runtime_reason(
    source: str,
    live_nodes: Callable[[Iterable[ast.stmt]], Iterable[ast.AST]],
    local_names: Callable[[_FN], set[str]],
) -> str | None:
    """Return None only when the exact E184 production topology is statically proved."""
    try:
        tree = ast.parse(source)
        state = _module_state(tree)

        if not _exact_native_delegate(state.final_advance, state.native_capture_lineno, local_names):
            return "final advance_sales does not exactly delegate pre-ADVANCE_START to captured native"

        policy_act = _class_method(state.policy_class, "act")
        if not _direct_name_calls(policy_act, "advance_sales", live_nodes, local_names):
            return "Policy.act does not reach module advance_sales"

        for caller_name, callee_name in (
            ("v3_agent", "_v3_core"),
            ("_v3_core", "_v3_stack"),
            ("_v3_stack", "POLICY_AGENT"),
        ):
            caller = state.final.get(caller_name)
            if not isinstance(caller, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return f"missing final {caller_name}()"
            if not _direct_name_calls(caller, callee_name, live_nodes, local_names):
                return f"{caller_name} does not reach authenticated {callee_name} edge"

        policy_agent = state.captures["POLICY_AGENT"]
        if not _resolve_captured_agent(policy_agent, state.captures, live_nodes, local_names):
            return "POLICY_AGENT capture chain does not terminate at exact _POLICY.act(observation)"
        return None
    except (SyntaxError, E184Reject, ValueError, TypeError) as exc:
        return f"E184 theorem rejected runtime: {exc}"


# ---- standalone optimized-stable tests ------------------------------------

def _fixture_live_nodes(statements: Iterable[ast.stmt]) -> Iterable[ast.AST]:
    """Conservative lexical-scope walk for donor tests only."""
    def expr(node: ast.AST):
        if isinstance(node, (ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            return
        yield node
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda,
                                  ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                continue
            yield from expr(child)
    for stmt in statements:
        yield stmt
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for child in ast.iter_child_nodes(stmt):
            if isinstance(child, ast.stmt):
                yield from _fixture_live_nodes((child,))
            else:
                yield from expr(child)
        if isinstance(stmt, (ast.Return, ast.Raise)):
            break


def _fixture_local_names(fn: _FN) -> set[str]:
    out = {a.arg for a in (*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs)}
    if fn.args.vararg: out.add(fn.args.vararg.arg)
    if fn.args.kwarg: out.add(fn.args.kwarg.arg)
    globals_: set[str] = set()
    class V(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            out.add(node.name)
        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            out.add(node.name)
        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            out.add(node.name)
        def visit_Lambda(self, node: ast.Lambda) -> None: return
        def visit_Global(self, node: ast.Global) -> None: globals_.update(node.names)
        def visit_Name(self, node: ast.Name) -> None:
            if isinstance(node.ctx, ast.Store): out.add(node.id)
    v = V()
    for stmt in fn.body:
        v.visit(stmt)
    return out - globals_


def _base_source(*, core="return _v3_stack(observation, configuration)",
                 stack="return POLICY_AGENT(observation, configuration)",
                 v3="return _v3_core(observation, configuration)",
                 policy="advance_sales(action, view, state, tape, step)\n        return action",
                 sale_parent="return _POLICY.act(observation)",
                 final_gate="if step < ADVANCE_START:\n        return _SALE_NATIVE_ADVANCE(action, view, state, tape, step)\n    return None") -> str:
    return f'''\nADVANCE_START = 288\n\ndef advance_sales(action, view, state, tape, step):\n    return action\n\nclass Policy:\n    def act(self, observation):\n        action = {{}}; view = state = tape = None; step = 1\n        {policy}\n\n_POLICY = Policy()\n\ndef agent(observation, configuration=None):\n    {sale_parent}\n\n_V216_PARENT = agent\ndel agent\ndef agent(observation, configuration=None):\n    return _V216_PARENT(observation, configuration)\n\n_SALE_NATIVE_ADVANCE = advance_sales\n\ndef advance_sales(action, view, state, tape, step):\n    {final_gate}\n\n_SALE_PARENT = agent\ndel agent\ndef agent(observation, configuration=None):\n    return _SALE_PARENT(observation, configuration)\n\nPOLICY_AGENT = agent\n\ndef _v3_stack(observation, configuration=None):\n    {stack}\n\ndef _v3_core(observation, configuration=None):\n    {core}\n\ndef v3_agent(observation, configuration=None):\n    {v3}\n'''


def self_test(live_nodes=_fixture_live_nodes, local_names=_fixture_local_names) -> None:
    checks = [0]
    def good(src: str, label: str) -> None:
        checks[0] += 1
        reason = check_e184_runtime_reason(src, live_nodes, local_names)
        req(reason is None, f"{label}: {reason}")
    def bad(src: str, label: str) -> None:
        checks[0] += 1
        reason = check_e184_runtime_reason(src, live_nodes, local_names)
        req(reason is not None, f"{label}: false PASS")

    good(_base_source(), "canonical positive")

    bad(_base_source(core="def decoy():\n        return _v3_stack(observation, configuration)\n    return {}"),
        "nested _v3_core->_v3_stack decoy")
    bad(_base_source(stack="def decoy():\n        return POLICY_AGENT(observation, configuration)\n    return {}"),
        "nested _v3_stack->POLICY_AGENT decoy")
    bad(_base_source(sale_parent="def decoy():\n        return _POLICY.act(observation)\n    return {}"),
        "nested parent->_POLICY decoy")
    bad(_base_source(policy="def decoy():\n            advance_sales(action, view, state, tape, step)\n        return action"),
        "nested Policy.act->advance_sales decoy")

    # Locally shadowed bridge names must not authenticate module edges.
    bad(_base_source(core="_v3_stack = lambda *a: {}\n    return _v3_stack(observation, configuration)"),
        "local _v3_stack shadow")
    bad(_base_source(stack="POLICY_AGENT = lambda *a: {}\n    return POLICY_AGENT(observation, configuration)"),
        "local POLICY_AGENT shadow")
    bad(_base_source(policy="advance_sales = lambda *a: None\n        advance_sales(action, view, state, tape, step)\n        return action"),
        "local advance_sales shadow")
    bad(_base_source(sale_parent="_POLICY = object()\n    return _POLICY.act(observation)"),
        "local _POLICY shadow")

    bad(_base_source(final_gate="if False:\n        return _SALE_NATIVE_ADVANCE(action, view, state, tape, step)\n    return None"),
        "false native delegate gate")
    bad(_base_source(final_gate="if step <= ADVANCE_START:\n        return _SALE_NATIVE_ADVANCE(action, view, state, tape, step)\n    return None"),
        "wrong native delegate comparator")

    # Capture must bind the unique first advance_sales before the final redefine.
    bad(_base_source().replace("_SALE_NATIVE_ADVANCE = advance_sales", "advance_sales = lambda *a: None\n_SALE_NATIVE_ADVANCE = advance_sales"),
        "native capture after ambiguous redefine")
    bad(_base_source().replace("_SALE_NATIVE_ADVANCE = advance_sales", "_SALE_NATIVE_ADVANCE = other"),
        "native capture wrong name")

    # Parent capture identity must be source-ordered and immutable.
    bad(_base_source().replace("_SALE_PARENT = agent", "_SALE_PARENT = agent\n_SALE_PARENT = agent"),
        "parent capture rebound")
    bad(_base_source().replace("POLICY_AGENT = agent", "POLICY_AGENT = agent\nPOLICY_AGENT = lambda *a: {}"),
        "POLICY_AGENT rebound")

    # Multiple captured-parent layers remain valid if the exact chain terminates at _POLICY.act.
    good(_base_source().replace("_SALE_PARENT = agent", "_V999_PARENT = agent\ndel agent\ndef agent(observation, configuration=None):\n    return _V999_PARENT(observation, configuration)\n\n_SALE_PARENT = agent"),
         "multi-parent capture chain")

    req(checks[0] == 16, f"self-test vector count mismatch: {checks[0]} != 16")


if __name__ == "__main__":
    self_test()
    print("#12620 12A3 E184 ADAPTER SELF-TEST OK (16 explicit checks)")
