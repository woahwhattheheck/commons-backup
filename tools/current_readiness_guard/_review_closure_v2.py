from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping, Sequence

from ._flow_time import (
    _direct_time_requirements,
    _expr_sources,
    _origins,
    _projection_call,
    _retained_time_argument,
)
from ._model import (
    Finding,
    _PROCESS_CLOCK,
    _authority_name,
    _collect_function_specs,
    _function_params,
    _historical_surface,
    _local_defs,
    _name,
    _positive_state,
    _public,
    _trusted_clock_names,
)

_GUARD_CALL_WORDS = ("verify", "validate", "authorize", "check")
_BOOLEAN_SURFACE_WORDS = ("current", "verify", "ready", "evaluate", "qualify", "gate")


def _resolve_call(raw: str, spec, specs_by_key: Mapping[str, object]) -> str | None:
    if not raw:
        return None
    if raw in specs_by_key:
        return raw
    if "." not in raw:
        candidate = f"{spec.key}.<locals>.{raw}"
        if candidate in specs_by_key:
            return candidate
        parent = spec.lexical_parent
        while parent is not None:
            candidate = f"{parent}.<locals>.{raw}"
            if candidate in specs_by_key:
                return candidate
            parent_spec = specs_by_key.get(parent)
            parent = getattr(parent_spec, "lexical_parent", None)
    if spec.owner is not None:
        if raw.startswith("self.") or raw.startswith("cls."):
            candidate = f"{spec.owner}.{raw.split('.', 1)[1]}"
            if candidate in specs_by_key:
                return candidate
        owner_short = spec.owner.rsplit(".", 1)[-1]
        if raw.startswith(owner_short + "."):
            candidate = f"{spec.owner}.{raw.split('.', 1)[1]}"
            if candidate in specs_by_key:
                return candidate
    return None


def _call_argument_by_param(call: ast.Call, params: Sequence[str], parameter: str) -> ast.AST | None:
    try:
        index = list(params).index(parameter)
    except ValueError:
        return None
    if index < len(call.args):
        return call.args[index]
    for keyword in call.keywords:
        if keyword.arg == parameter:
            return keyword.value
    return None


def _authority_refs(node: ast.AST | None, authority_params: set[str]) -> set[str]:
    if node is None:
        return set()
    return {
        child.id
        for child in ast.walk(node)
        if isinstance(child, ast.Name) and child.id in authority_params
    }


def _direct_authority_facts(node: ast.AST, authority_params: set[str], *, truth: bool) -> set[str]:
    if isinstance(node, ast.Name) and node.id in authority_params:
        return {node.id} if truth else set()
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return _direct_authority_facts(node.operand, authority_params, truth=not truth)
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And) and truth:
            result: set[str] = set()
            for value in node.values:
                result |= _direct_authority_facts(value, authority_params, truth=True)
            return result
        if isinstance(node.op, ast.Or) and not truth:
            result: set[str] = set()
            for value in node.values:
                result |= _direct_authority_facts(value, authority_params, truth=False)
            return result
        return set()
    if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
        left, op, right = node.left, node.ops[0], node.comparators[0]
        name: str | None = None
        constant: object = object()
        if isinstance(left, ast.Name) and left.id in authority_params and isinstance(right, ast.Constant):
            name, constant = left.id, right.value
        elif isinstance(right, ast.Name) and right.id in authority_params and isinstance(left, ast.Constant):
            name, constant = right.id, left.value
        if name is not None:
            positive = (
                (constant is None and isinstance(op, (ast.IsNot, ast.NotEq)))
                or (constant is True and isinstance(op, (ast.Is, ast.Eq)))
                or (constant is False and isinstance(op, (ast.IsNot, ast.NotEq)))
            )
            if truth and positive:
                return {name}
            if not truth and constant is None and isinstance(op, (ast.Is, ast.Eq)):
                return {name}
    if truth and isinstance(node, ast.Call) and _name(node.func) == "bool" and len(node.args) == 1:
        if isinstance(node.args[0], ast.Name) and node.args[0].id in authority_params:
            return {node.args[0].id}
    return set()


def _copy_bound_env(
    env: Mapping[str, tuple[tuple[ast.AST, frozenset[str]], ...]],
) -> dict[str, tuple[tuple[ast.AST, frozenset[str]], ...]]:
    return {name: tuple(values) for name, values in env.items()}


def _merge_bound_envs(
    *environments: Mapping[str, tuple[tuple[ast.AST, frozenset[str]], ...]],
) -> dict[str, tuple[tuple[ast.AST, frozenset[str]], ...]]:
    out: dict[str, tuple[tuple[ast.AST, frozenset[str]], ...]] = {}
    names: set[str] = set()
    for env in environments:
        names.update(env)
    for name in names:
        seen: set[tuple[str, tuple[str, ...]]] = set()
        merged: list[tuple[ast.AST, frozenset[str]]] = []
        for env in environments:
            for expression, facts in env.get(name, ()):
                identity = (ast.dump(expression, include_attributes=False), tuple(sorted(facts)))
                if identity not in seen:
                    seen.add(identity)
                    merged.append((expression, facts))
        if merged:
            out[name] = tuple(merged)
    return out


def _bind_assignment(
    statement: ast.stmt,
    env: dict[str, tuple[tuple[ast.AST, frozenset[str]], ...]],
    facts: frozenset[str],
) -> None:
    value: ast.AST | None = None
    targets: list[ast.AST] = []
    if isinstance(statement, ast.Assign):
        value = statement.value
        targets = list(statement.targets)
    elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
        value = statement.value
        targets = [statement.target]
    if value is None:
        return
    bound = ((value, facts),)
    for target in targets:
        if isinstance(target, ast.Name):
            env[target.id] = bound


def _iter_return_paths(
    statements: Sequence[ast.stmt],
    authority_params: set[str],
    *,
    facts: frozenset[str] = frozenset(),
    env: Mapping[str, tuple[tuple[ast.AST, frozenset[str]], ...]] | None = None,
    condition_facts,
) -> tuple[
    list[tuple[ast.AST | None, frozenset[str], dict[str, tuple[tuple[ast.AST, frozenset[str]], ...]]]],
    bool,
    frozenset[str],
    dict[str, tuple[tuple[ast.AST, frozenset[str]], ...]],
]:
    out: list[
        tuple[ast.AST | None, frozenset[str], dict[str, tuple[tuple[ast.AST, frozenset[str]], ...]]]
    ] = []
    current = set(facts)
    current_env = _copy_bound_env(env or {})
    for statement in statements:
        if isinstance(statement, ast.Return):
            out.append((statement.value, frozenset(current), _copy_bound_env(current_env)))
            return out, False, frozenset(current), current_env
        if isinstance(statement, ast.Raise):
            return out, False, frozenset(current), current_env
        if isinstance(statement, (ast.Assign, ast.AnnAssign)):
            _bind_assignment(statement, current_env, frozenset(current))
            continue
        if isinstance(statement, ast.If):
            true_facts = frozenset(current | condition_facts(statement.test, authority_params, True))
            false_facts = frozenset(current | condition_facts(statement.test, authority_params, False))
            body_paths, body_fall, body_end, body_env = _iter_return_paths(
                statement.body,
                authority_params,
                facts=true_facts,
                env=current_env,
                condition_facts=condition_facts,
            )
            if statement.orelse:
                else_paths, else_fall, else_end, else_env = _iter_return_paths(
                    statement.orelse,
                    authority_params,
                    facts=false_facts,
                    env=current_env,
                    condition_facts=condition_facts,
                )
            else:
                else_paths, else_fall, else_end, else_env = (
                    [],
                    True,
                    false_facts,
                    _copy_bound_env(current_env),
                )
            out.extend(body_paths)
            out.extend(else_paths)
            if body_fall and else_fall:
                current = set(body_end & else_end)
                current_env = _merge_bound_envs(body_env, else_env)
            elif body_fall:
                current = set(body_end)
                current_env = body_env
            elif else_fall:
                current = set(else_end)
                current_env = else_env
            else:
                return out, False, frozenset(current), current_env
            continue
    return out, True, frozenset(current), current_env


def _direct_return_paths(
    statements: Sequence[ast.stmt],
    authority_params: set[str],
    *,
    facts: frozenset[str] = frozenset(),
    condition_facts,
) -> list[tuple[ast.AST | None, frozenset[str]]]:
    paths, _, _, _ = _iter_return_paths(
        statements,
        authority_params,
        facts=facts,
        condition_facts=condition_facts,
    )
    return [(expression, path_facts) for expression, path_facts, _env in paths]


def _truth_controlled_by_parameter(fn: ast.FunctionDef | ast.AsyncFunctionDef, parameter: str) -> bool:
    controls = {parameter}

    def condition(node: ast.AST, params: set[str], truth: bool) -> set[str]:
        return _direct_authority_facts(node, params, truth=truth)

    paths = _direct_return_paths(fn.body, controls, condition_facts=condition)
    if not paths:
        return False
    saw_accept = False
    for expression, facts in paths:
        if isinstance(expression, ast.Constant) and expression.value in {False, None}:
            continue
        saw_accept = True
        direct = _direct_authority_facts(expression, controls, truth=True) if expression else set()
        if parameter not in facts and parameter not in direct:
            return False
    return saw_accept


def _condition_facts_factory(spec, specs_by_key: Mapping[str, object]):
    def condition(node: ast.AST, authority_params: set[str], truth: bool) -> set[str]:
        direct = _direct_authority_facts(node, authority_params, truth=truth)
        if direct or not truth or not isinstance(node, ast.Call):
            return direct
        call_name = _name(node.func)
        refs = _authority_refs(node, authority_params)
        if not refs or not any(word in call_name.lower() for word in _GUARD_CALL_WORDS):
            return set()
        resolved = _resolve_call(call_name, spec, specs_by_key)
        if resolved is None:
            # Preserve the predecessor contract for an opaque external validator.
            return refs
        callee_spec = specs_by_key[resolved]
        callee_params = _function_params(callee_spec.node)
        controlled: set[str] = set()
        for caller_parameter in refs:
            for callee_parameter in callee_params:
                argument = _call_argument_by_param(node, callee_params, callee_parameter)
                if (
                    isinstance(argument, ast.Name)
                    and argument.id == caller_parameter
                    and _truth_controlled_by_parameter(callee_spec.node, callee_parameter)
                ):
                    controlled.add(caller_parameter)
        return controlled

    return condition


def _static_string_values(
    node: ast.AST | None,
    globals_: Mapping[str, frozenset[str]],
    *,
    seen: frozenset[str] = frozenset(),
) -> frozenset[str]:
    if node is None:
        return frozenset()
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return frozenset({node.value})
    if isinstance(node, ast.Name) and node.id in globals_ and node.id not in seen:
        return globals_[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _static_string_values(node.left, globals_, seen=seen)
        right = _static_string_values(node.right, globals_, seen=seen)
        if left and right and len(left) * len(right) <= 32:
            return frozenset(a + b for a in left for b in right)
        return frozenset()
    if isinstance(node, ast.JoinedStr):
        values: set[str] = {""}
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                choices = {part.value}
            elif isinstance(part, ast.FormattedValue):
                choices = set(_static_string_values(part.value, globals_, seen=seen))
            else:
                return frozenset()
            if not choices or len(values) * len(choices) > 32:
                return frozenset()
            values = {prefix + choice for prefix in values for choice in choices}
        return frozenset(values)
    return frozenset()


def _module_static_strings(tree: ast.Module) -> dict[str, frozenset[str]]:
    assignments: list[tuple[str, ast.AST]] = []
    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    assignments.append((target.id, statement.value))
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name) and statement.value:
            assignments.append((statement.target.id, statement.value))
    out: dict[str, frozenset[str]] = {}
    for _ in range(max(1, len(assignments) + 1)):
        changed = False
        for name, expression in assignments:
            values = _static_string_values(expression, out)
            if values and out.get(name) != values:
                out[name] = values
                changed = True
        if not changed:
            break
    return out


def _boolean_positive_expression(node: ast.AST | None, authority_params: set[str]) -> tuple[bool, set[str]]:
    if node is None:
        return False, set()
    if isinstance(node, ast.Constant) and node.value is True:
        return True, set()
    if isinstance(node, ast.Name) and node.id in authority_params:
        return True, {node.id}
    if isinstance(node, ast.Compare):
        return True, _direct_authority_facts(node, authority_params, truth=True)
    if isinstance(node, ast.Call) and _name(node.func) == "bool":
        return True, _direct_authority_facts(node, authority_params, truth=True)
    if isinstance(node, (ast.BoolOp, ast.UnaryOp)):
        return True, _direct_authority_facts(node, authority_params, truth=True)
    return False, set()


def _surface_crg003_findings(tree: ast.Module, path: str) -> list[Finding]:
    specs = _collect_function_specs(tree)
    specs_by_key = {spec.key: spec for spec in specs}
    globals_ = _module_static_strings(tree)
    out: list[Finding] = []
    for spec in specs:
        fn = spec.node
        if not spec.surface or not _public(fn) or _historical_surface(fn):
            continue
        authority_params = {name for name in _function_params(fn) if _authority_name(name)}
        condition = _condition_facts_factory(spec, specs_by_key)
        paths = _direct_return_paths(fn.body, authority_params, condition_facts=condition)
        risky = False
        for expression, facts in paths:
            static_positive = any(
                _positive_state(value) for value in _static_string_values(expression, globals_)
            )
            boolean_positive = False
            boolean_facts: set[str] = set()
            if any(word in fn.name.lower() for word in _BOOLEAN_SURFACE_WORDS):
                boolean_positive, boolean_facts = _boolean_positive_expression(expression, authority_params)
            if not static_positive and not boolean_positive:
                continue
            if not facts and not boolean_facts:
                risky = True
                break
        if risky:
            out.append(
                Finding(
                    path,
                    fn.lineno,
                    fn.col_offset + 1,
                    "CRG003",
                    "a current-positive path is not controlled by an actually consumed independent authority parameter",
                    spec.key,
                )
            )
    return out


class _DirectCallCollector(ast.NodeVisitor):
    def __init__(self, root: ast.FunctionDef | ast.AsyncFunctionDef):
        self.root = root
        self.calls: list[ast.Call] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node is self.root:
            for statement in node.body:
                self.visit(statement)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if node is self.root:
            for statement in node.body:
                self.visit(statement)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return

    def visit_Call(self, node: ast.Call) -> None:
        self.calls.append(node)
        self.generic_visit(node)


def _parameter_affects_projection(fn: ast.FunctionDef | ast.AsyncFunctionDef, parameter: str, trusted) -> bool:
    defs = _local_defs(fn)
    params = set(_function_params(fn))
    origins = _origins(fn, defs, trusted)
    collector = _DirectCallCollector(fn)
    collector.visit(fn)
    for node in ast.walk(fn):
        if isinstance(node, ast.Return):
            if parameter in _expr_sources(
                node.value,
                params=params,
                origins=origins,
                defs=defs,
                trusted_clock_names=trusted,
            ):
                return True
    if any(parameter in requirement for requirement in _direct_time_requirements(fn, defs, trusted)):
        return True
    return False


def _surface_crg004_findings(tree: ast.Module, path: str) -> list[Finding]:
    specs = _collect_function_specs(tree)
    specs_by_key = {spec.key: spec for spec in specs}
    trusted = _trusted_clock_names(tree)
    out: list[Finding] = []
    for spec in specs:
        fn = spec.node
        if not spec.surface or not _public(fn) or "verify" not in fn.name.lower():
            continue
        params = set(_function_params(fn))
        defs = _local_defs(fn)
        origins = _origins(fn, defs, trusted)
        collector = _DirectCallCollector(fn)
        collector.visit(fn)
        retained = any(
            _projection_call(call)
            and _retained_time_argument(
                call,
                params=params,
                origins=origins,
                defs=defs,
                trusted_clock_names=trusted,
            )
            for call in collector.calls
        )
        if not retained:
            continue
        ineffective = False
        for call in collector.calls:
            if not _projection_call(call):
                continue
            resolved = _resolve_call(_name(call.func), spec, specs_by_key)
            if resolved is None:
                continue
            callee = specs_by_key[resolved]
            callee_params = _function_params(callee.node)
            for parameter in callee_params:
                argument = _call_argument_by_param(call, callee_params, parameter)
                if argument is None:
                    continue
                sources = _expr_sources(
                    argument,
                    params=params,
                    origins=origins,
                    defs=defs,
                    trusted_clock_names=trusted,
                )
                if _PROCESS_CLOCK in sources and not _parameter_affects_projection(
                    callee.node, parameter, trusted
                ):
                    ineffective = True
                    break
            if ineffective:
                break
        if ineffective:
            out.append(
                Finding(
                    path,
                    fn.lineno,
                    fn.col_offset + 1,
                    "CRG004",
                    "process-clock argument is passed to a same-module projection that does not consume it in the projection result/currentness decision",
                    spec.key,
                )
            )
    return out


def additional_findings(source: str | bytes, *, path: str = "<memory>") -> list[Finding]:
    if isinstance(source, bytes):
        try:
            source = source.decode("utf-8", "strict")
        except UnicodeDecodeError:
            return []
    if not isinstance(source, str):
        return []
    try:
        tree = ast.parse(source, filename=path)
    except (SyntaxError, ValueError):
        return []
    return sorted(set([*_surface_crg003_findings(tree, path), *_surface_crg004_findings(tree, path)]))


__all__ = ["additional_findings", "_iter_return_paths"]
