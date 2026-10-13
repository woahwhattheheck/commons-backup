from __future__ import annotations

from collections.abc import Callable

from ._model import *

_ValueEnv = dict[str, tuple[_BoundValue, ...]]
_CallResolver = Callable[[str], str | None]


def _copy_env(env: _ValueEnv) -> _ValueEnv:
    return {name: tuple(values) for name, values in env.items()}


def _value_identity(value: _BoundValue) -> tuple[str, tuple[str, ...]]:
    return (ast.dump(value.expression, include_attributes=False), tuple(sorted(value.authority_facts)))


def _merge_envs(*environments: _ValueEnv) -> _ValueEnv:
    out: _ValueEnv = {}
    names = set().union(*(env.keys() for env in environments)) if environments else set()
    for name in names:
        seen: set[tuple[str, tuple[str, ...]]] = set()
        merged: list[_BoundValue] = []
        for env in environments:
            for value in env.get(name, ()):
                identity = _value_identity(value)
                if identity not in seen:
                    seen.add(identity)
                    merged.append(value)
        if merged:
            out[name] = tuple(merged)
    return out


def _assignment_targets(node: ast.AST) -> list[str]:
    targets: list[ast.AST] = []
    if isinstance(node, ast.Assign):
        targets.extend(node.targets)
    elif isinstance(node, (ast.AnnAssign, ast.NamedExpr, ast.AugAssign)):
        targets.append(node.target)

    def names(target: ast.AST) -> list[str]:
        if isinstance(target, ast.Name):
            return [target.id]
        if isinstance(target, (ast.Tuple, ast.List)):
            result: list[str] = []
            for item in target.elts:
                result.extend(names(item))
            return result
        return []

    result: list[str] = []
    for target in targets:
        result.extend(names(target))
    return result


def _assignment_value(node: ast.AST) -> ast.AST | None:
    if isinstance(node, ast.Assign):
        return node.value
    if isinstance(node, ast.AnnAssign):
        return node.value
    if isinstance(node, ast.NamedExpr):
        return node.value
    if isinstance(node, ast.AugAssign):
        return ast.BinOp(left=node.target, op=node.op, right=node.value)
    return None


def _positive_field(name: str) -> bool:
    token = name.strip().lower()
    if token in {
        "ready", "is_ready", "valid", "is_valid", "clear", "reusable",
        "authorized", "submission_ready", "external_send_authorized",
        "side_effects_authorized", "ready_for_bid_consumption",
        "current_verified", "production_certified",
    }:
        return True
    return token.endswith(("_ready", "_authorized", "_verified", "_clear", "_valid", "_certified"))


def _truthy_requirements(
    node: ast.AST | None,
    *,
    env: _ValueEnv,
    facts: frozenset[str],
    authority_params: set[str],
    seen_names: frozenset[str] = frozenset(),
) -> list[frozenset[str]]:
    if node is None:
        return []
    if isinstance(node, ast.Name):
        if node.id in env and node.id not in seen_names:
            out: list[frozenset[str]] = []
            for bound in env[node.id]:
                out.extend(
                    _truthy_requirements(
                        bound.expression,
                        env=env,
                        facts=frozenset(set(facts) | set(bound.authority_facts)),
                        authority_params=authority_params,
                        seen_names=seen_names | {node.id},
                    )
                )
            return out
        if node.id in authority_params:
            return [frozenset(set(facts) | {node.id})]
        return [facts]
    if isinstance(node, ast.Constant) and node.value is True:
        return [facts]
    if isinstance(node, ast.IfExp):
        true_facts = frozenset(
            set(facts) | _condition_authority_facts(node.test, authority_params, truth=True)
        )
        false_facts = frozenset(
            set(facts) | _condition_authority_facts(node.test, authority_params, truth=False)
        )
        return [
            *_truthy_requirements(
                node.body,
                env=env,
                facts=true_facts,
                authority_params=authority_params,
                seen_names=seen_names,
            ),
            *_truthy_requirements(
                node.orelse,
                env=env,
                facts=false_facts,
                authority_params=authority_params,
                seen_names=seen_names,
            ),
        ]
    if isinstance(node, (ast.BoolOp, ast.Compare, ast.UnaryOp, ast.Call, ast.Attribute, ast.Subscript)):
        controlling = _condition_authority_facts(node, authority_params, truth=True)
        return [frozenset(set(facts) | controlling)]
    return []


def _positive_expression(
    node: ast.AST | None,
    *,
    env: _ValueEnv,
    facts: frozenset[str],
    authority_params: set[str],
    globals_: Mapping[str, str],
    resolve_call: _CallResolver,
    seen_names: frozenset[str] = frozenset(),
) -> tuple[list[frozenset[str]], list[_CallSite]]:
    if node is None:
        return [], []
    if isinstance(node, ast.Name) and node.id in env and node.id not in seen_names:
        requirements: list[frozenset[str]] = []
        calls: list[_CallSite] = []
        for bound in env[node.id]:
            child_requirements, child_calls = _positive_expression(
                bound.expression,
                env=env,
                facts=frozenset(set(facts) | set(bound.authority_facts)),
                authority_params=authority_params,
                globals_=globals_,
                resolve_call=resolve_call,
                seen_names=seen_names | {node.id},
            )
            requirements.extend(child_requirements)
            calls.extend(child_calls)
        return requirements, calls

    requirements: list[frozenset[str]] = []
    calls: list[_CallSite] = []
    if isinstance(node, (ast.Constant, ast.Name, ast.Attribute)) and _contains_positive(node, {}, globals_):
        requirements.append(facts)

    if isinstance(node, ast.Call):
        resolved_callees: set[str] = set()
        direct_callee = resolve_call(_name(node.func))
        if direct_callee is not None:
            resolved_callees.add(direct_callee)
        lambda_bodies: list[tuple[ast.AST, frozenset[str]]] = []
        if isinstance(node.func, ast.Lambda):
            lambda_bodies.append((node.func.body, facts))
        elif isinstance(node.func, ast.Name) and node.func.id in env:
            for bound in env[node.func.id]:
                if isinstance(bound.expression, ast.Lambda):
                    lambda_bodies.append(
                        (
                            bound.expression.body,
                            frozenset(set(facts) | set(bound.authority_facts)),
                        )
                    )
                else:
                    alias_callee = resolve_call(_name(bound.expression))
                    if alias_callee is not None:
                        resolved_callees.add(alias_callee)
        for callee in sorted(resolved_callees):
            calls.append(_CallSite(callee, node, facts))
        for body, body_facts in lambda_bodies:
            child_requirements, child_calls = _positive_expression(
                body,
                env=env,
                facts=body_facts,
                authority_params=authority_params,
                globals_=globals_,
                resolve_call=resolve_call,
                seen_names=seen_names,
            )
            requirements.extend(child_requirements)
            calls.extend(child_calls)
        for argument in node.args:
            child_requirements, child_calls = _positive_expression(
                argument,
                env=env,
                facts=facts,
                authority_params=authority_params,
                globals_=globals_,
                resolve_call=resolve_call,
                seen_names=seen_names,
            )
            requirements.extend(child_requirements)
            calls.extend(child_calls)
        for keyword in node.keywords:
            if keyword.arg is not None and _positive_field(keyword.arg):
                requirements.extend(
                    _truthy_requirements(
                        keyword.value,
                        env=env,
                        facts=facts,
                        authority_params=authority_params,
                        seen_names=seen_names,
                    )
                )
            child_requirements, child_calls = _positive_expression(
                keyword.value,
                env=env,
                facts=facts,
                authority_params=authority_params,
                globals_=globals_,
                resolve_call=resolve_call,
                seen_names=seen_names,
            )
            requirements.extend(child_requirements)
            calls.extend(child_calls)
        return requirements, calls

    if isinstance(node, ast.IfExp):
        true_facts = frozenset(
            set(facts) | _condition_authority_facts(node.test, authority_params, truth=True)
        )
        false_facts = frozenset(
            set(facts) | _condition_authority_facts(node.test, authority_params, truth=False)
        )
        for value, branch_facts in ((node.body, true_facts), (node.orelse, false_facts)):
            child_requirements, child_calls = _positive_expression(
                value,
                env=env,
                facts=branch_facts,
                authority_params=authority_params,
                globals_=globals_,
                resolve_call=resolve_call,
                seen_names=seen_names,
            )
            requirements.extend(child_requirements)
            calls.extend(child_calls)
        return requirements, calls

    if isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and isinstance(key.value, str) and _positive_field(key.value):
                requirements.extend(
                    _truthy_requirements(
                        value,
                        env=env,
                        facts=facts,
                        authority_params=authority_params,
                        seen_names=seen_names,
                    )
                )
            child_requirements, child_calls = _positive_expression(
                value,
                env=env,
                facts=facts,
                authority_params=authority_params,
                globals_=globals_,
                resolve_call=resolve_call,
                seen_names=seen_names,
            )
            requirements.extend(child_requirements)
            calls.extend(child_calls)
        return requirements, calls

    children = list(node.elts) if isinstance(node, (ast.List, ast.Tuple, ast.Set)) else []
    for value in children:
        child_requirements, child_calls = _positive_expression(
            value,
            env=env,
            facts=facts,
            authority_params=authority_params,
            globals_=globals_,
            resolve_call=resolve_call,
            seen_names=seen_names,
        )
        requirements.extend(child_requirements)
        calls.extend(child_calls)
    return requirements, calls

def _assign_into_env(statement: ast.AST, env: _ValueEnv, facts: frozenset[str]) -> None:
    value = _assignment_value(statement)
    if value is None:
        return
    bound = (_BoundValue(value, facts),)
    for name in _assignment_targets(statement):
        env[name] = bound


def _collect_positive_paths(
    statements: Sequence[ast.stmt],
    *,
    facts: frozenset[str],
    authority_params: set[str],
    env: _ValueEnv,
    globals_: Mapping[str, str],
    resolve_call: _CallResolver,
) -> tuple[list[frozenset[str]], list[_CallSite], bool, frozenset[str], _ValueEnv]:
    requirements: list[frozenset[str]] = []
    calls: list[_CallSite] = []
    current_facts = set(facts)
    current_env = _copy_env(env)

    for statement in statements:
        if isinstance(statement, ast.Return):
            direct, returned_calls = _positive_expression(
                statement.value,
                env=current_env,
                facts=frozenset(current_facts),
                authority_params=authority_params,
                globals_=globals_,
                resolve_call=resolve_call,
            )
            requirements.extend(direct)
            calls.extend(returned_calls)
            return requirements, calls, False, frozenset(current_facts), current_env
        if isinstance(statement, ast.Raise):
            return requirements, calls, False, frozenset(current_facts), current_env
        if isinstance(statement, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            _assign_into_env(statement, current_env, frozenset(current_facts))
            continue
        if isinstance(statement, ast.If):
            true_facts = frozenset(
                current_facts | _condition_authority_facts(statement.test, authority_params, truth=True)
            )
            false_facts = frozenset(
                current_facts | _condition_authority_facts(statement.test, authority_params, truth=False)
            )
            body_req, body_calls, body_fall, body_end, body_env = _collect_positive_paths(
                statement.body,
                facts=true_facts,
                authority_params=authority_params,
                env=current_env,
                globals_=globals_,
                resolve_call=resolve_call,
            )
            if statement.orelse:
                else_req, else_calls, else_fall, else_end, else_env = _collect_positive_paths(
                    statement.orelse,
                    facts=false_facts,
                    authority_params=authority_params,
                    env=current_env,
                    globals_=globals_,
                    resolve_call=resolve_call,
                )
            else:
                else_req, else_calls, else_fall, else_end, else_env = (
                    [], [], True, false_facts, _copy_env(current_env)
                )
            requirements.extend(body_req)
            requirements.extend(else_req)
            calls.extend(body_calls)
            calls.extend(else_calls)
            if body_fall and else_fall:
                current_facts = set(body_end & else_end)
                current_env = _merge_envs(body_env, else_env)
            elif body_fall:
                current_facts = set(body_end)
                current_env = body_env
            elif else_fall:
                current_facts = set(else_end)
                current_env = else_env
            else:
                return requirements, calls, False, frozenset(current_facts), current_env
            continue

        if isinstance(statement, (ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith)):
            body = getattr(statement, "body", [])
            body_req, body_calls, _, _, body_env = _collect_positive_paths(
                body,
                facts=frozenset(current_facts),
                authority_params=authority_params,
                env=current_env,
                globals_=globals_,
                resolve_call=resolve_call,
            )
            requirements.extend(body_req)
            calls.extend(body_calls)
            current_env = _merge_envs(current_env, body_env)
            orelse = getattr(statement, "orelse", [])
            if orelse:
                else_req, else_calls, _, _, else_env = _collect_positive_paths(
                    orelse,
                    facts=frozenset(current_facts),
                    authority_params=authority_params,
                    env=current_env,
                    globals_=globals_,
                    resolve_call=resolve_call,
                )
                requirements.extend(else_req)
                calls.extend(else_calls)
                current_env = _merge_envs(current_env, else_env)
            continue

        if isinstance(statement, ast.Try):
            branch_envs: list[_ValueEnv] = []
            branches = [statement.body, *(handler.body for handler in statement.handlers), statement.orelse]
            for block in branches:
                if not block:
                    continue
                branch_req, branch_calls, branch_fall, _, branch_env = _collect_positive_paths(
                    block,
                    facts=frozenset(current_facts),
                    authority_params=authority_params,
                    env=current_env,
                    globals_=globals_,
                    resolve_call=resolve_call,
                )
                requirements.extend(branch_req)
                calls.extend(branch_calls)
                if branch_fall:
                    branch_envs.append(branch_env)
            current_env = _merge_envs(current_env, *branch_envs)
            if statement.finalbody:
                final_req, final_calls, final_fall, final_end, final_env = _collect_positive_paths(
                    statement.finalbody,
                    facts=frozenset(current_facts),
                    authority_params=authority_params,
                    env=current_env,
                    globals_=globals_,
                    resolve_call=resolve_call,
                )
                requirements.extend(final_req)
                calls.extend(final_calls)
                if not final_fall:
                    return requirements, calls, False, final_end, final_env
                current_facts = set(final_end)
                current_env = final_env
            continue

        if isinstance(statement, ast.Match):
            case_envs: list[_ValueEnv] = []
            for case in statement.cases:
                case_req, case_calls, case_fall, _, case_env = _collect_positive_paths(
                    case.body,
                    facts=frozenset(current_facts),
                    authority_params=authority_params,
                    env=current_env,
                    globals_=globals_,
                    resolve_call=resolve_call,
                )
                requirements.extend(case_req)
                calls.extend(case_calls)
                if case_fall:
                    case_envs.append(case_env)
            current_env = _merge_envs(current_env, *case_envs)

    return requirements, calls, True, frozenset(current_facts), current_env



__all__ = [name for name in globals() if not name.startswith("__")]
