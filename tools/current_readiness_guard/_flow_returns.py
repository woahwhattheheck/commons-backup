from __future__ import annotations

from ._model import *
from ._flow_positive import _assignment_targets, _assignment_value
from ._flow_time import *

def _failure_state(value: str) -> bool:
    token = value.strip().upper()
    return token in {"FALSE", "ERROR", "FAIL", "FAILED", "NO", "REJECTED"} or token.startswith(_NONCURRENT_PREFIXES)


def _literal_safe_failure(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        if node.value is False or node.value is None:
            return True
        if isinstance(node.value, str):
            return _failure_state(node.value)
    if isinstance(node, ast.Attribute):
        return _failure_state(node.attr)
    return False


def _return_statuses(
    node: ast.AST | None,
    *,
    status_env: Mapping[str, frozenset[str]],
    params: set[str],
    origins: Mapping[str, set[str]],
    defs: Mapping[str, Sequence[ast.AST]],
    trusted_clock_names: frozenset[str],
    seen: frozenset[str] = frozenset(),
) -> frozenset[str]:
    if node is None:
        return frozenset({_SAFE_FAILURE})
    if _literal_safe_failure(node):
        return frozenset({_SAFE_FAILURE})
    if isinstance(node, ast.Name):
        if node.id in status_env:
            return status_env[node.id]
        return frozenset({_UNSAFE_ACCEPT})
    if isinstance(node, ast.Call):
        if _projection_call(node):
            supplied = [*node.args, *(keyword.value for keyword in node.keywords)]
            if any(
                _PROCESS_CLOCK
                in _expr_sources(
                    argument,
                    params=params,
                    origins=origins,
                    defs=defs,
                    trusted_clock_names=trusted_clock_names,
                )
                for argument in supplied
            ):
                return frozenset({_PROCESS_REQUIRED})
        child_statuses: set[str] = set()
        for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
            child_statuses.update(
                _return_statuses(
                    argument,
                    status_env=status_env,
                    params=params,
                    origins=origins,
                    defs=defs,
                    trusted_clock_names=trusted_clock_names,
                    seen=seen,
                )
            )
        if _PROCESS_REQUIRED in child_statuses and _UNSAFE_ACCEPT not in child_statuses:
            return frozenset({_PROCESS_REQUIRED})
        return frozenset({_UNSAFE_ACCEPT})
    if isinstance(node, (ast.Attribute, ast.Subscript)):
        base = node.value
        return _return_statuses(
            base,
            status_env=status_env,
            params=params,
            origins=origins,
            defs=defs,
            trusted_clock_names=trusted_clock_names,
            seen=seen,
        )
    if isinstance(node, ast.Compare):
        statuses: set[str] = set()
        for operand in [node.left, *node.comparators]:
            statuses.update(
                _return_statuses(
                    operand,
                    status_env=status_env,
                    params=params,
                    origins=origins,
                    defs=defs,
                    trusted_clock_names=trusted_clock_names,
                    seen=seen,
                )
            )
        return frozenset({_PROCESS_REQUIRED}) if _PROCESS_REQUIRED in statuses else frozenset({_UNSAFE_ACCEPT})
    if isinstance(node, ast.UnaryOp):
        return _return_statuses(
            node.operand,
            status_env=status_env,
            params=params,
            origins=origins,
            defs=defs,
            trusted_clock_names=trusted_clock_names,
            seen=seen,
        )
    if isinstance(node, ast.BoolOp):
        parts = [
            _return_statuses(
                value,
                status_env=status_env,
                params=params,
                origins=origins,
                defs=defs,
                trusted_clock_names=trusted_clock_names,
                seen=seen,
            )
            for value in node.values
        ]
        if isinstance(node.op, ast.And):
            if any(_PROCESS_REQUIRED in part for part in parts):
                return frozenset({_PROCESS_REQUIRED})
            if all(part <= {_SAFE_FAILURE} for part in parts):
                return frozenset({_SAFE_FAILURE})
            return frozenset({_UNSAFE_ACCEPT})
        if any(_UNSAFE_ACCEPT in part for part in parts):
            return frozenset({_UNSAFE_ACCEPT})
        if any(_PROCESS_REQUIRED in part for part in parts):
            return frozenset({_PROCESS_REQUIRED})
        return frozenset({_SAFE_FAILURE})
    if isinstance(node, ast.IfExp):
        return frozenset().union(
            _return_statuses(
                node.body,
                status_env=status_env,
                params=params,
                origins=origins,
                defs=defs,
                trusted_clock_names=trusted_clock_names,
                seen=seen,
            ),
            _return_statuses(
                node.orelse,
                status_env=status_env,
                params=params,
                origins=origins,
                defs=defs,
                trusted_clock_names=trusted_clock_names,
                seen=seen,
            ),
        )
    if isinstance(node, ast.Dict):
        statuses: set[str] = set()
        for value in node.values:
            statuses.update(
                _return_statuses(
                    value,
                    status_env=status_env,
                    params=params,
                    origins=origins,
                    defs=defs,
                    trusted_clock_names=trusted_clock_names,
                    seen=seen,
                )
            )
        if _UNSAFE_ACCEPT in statuses:
            return frozenset({_UNSAFE_ACCEPT})
        if _PROCESS_REQUIRED in statuses:
            return frozenset({_PROCESS_REQUIRED})
        return frozenset({_SAFE_FAILURE})
    return frozenset({_UNSAFE_ACCEPT})


def _merge_status_envs(*environments: Mapping[str, frozenset[str]]) -> dict[str, frozenset[str]]:
    names = set().union(*(env.keys() for env in environments)) if environments else set()
    return {
        name: frozenset().union(*(env.get(name, frozenset()) for env in environments))
        for name in names
    }


def _collect_return_statuses(
    statements: Sequence[ast.stmt],
    *,
    status_env: Mapping[str, frozenset[str]],
    params: set[str],
    origins: Mapping[str, set[str]],
    defs: Mapping[str, Sequence[ast.AST]],
    trusted_clock_names: frozenset[str],
) -> tuple[list[frozenset[str]], bool, dict[str, frozenset[str]]]:
    returns: list[frozenset[str]] = []
    env = dict(status_env)
    for statement in statements:
        if isinstance(statement, ast.Return):
            returns.append(
                _return_statuses(
                    statement.value,
                    status_env=env,
                    params=params,
                    origins=origins,
                    defs=defs,
                    trusted_clock_names=trusted_clock_names,
                )
            )
            return returns, False, env
        if isinstance(statement, ast.Raise):
            return returns, False, env
        if isinstance(statement, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            value = _assignment_value(statement)
            if value is not None:
                status = _return_statuses(
                    value,
                    status_env=env,
                    params=params,
                    origins=origins,
                    defs=defs,
                    trusted_clock_names=trusted_clock_names,
                )
                for target in _assignment_targets(statement):
                    env[target] = status
            continue
        if isinstance(statement, ast.If):
            body_returns, body_fall, body_env = _collect_return_statuses(
                statement.body,
                status_env=env,
                params=params,
                origins=origins,
                defs=defs,
                trusted_clock_names=trusted_clock_names,
            )
            if statement.orelse:
                else_returns, else_fall, else_env = _collect_return_statuses(
                    statement.orelse,
                    status_env=env,
                    params=params,
                    origins=origins,
                    defs=defs,
                    trusted_clock_names=trusted_clock_names,
                )
            else:
                else_returns, else_fall, else_env = [], True, dict(env)
            returns.extend(body_returns)
            returns.extend(else_returns)
            if body_fall and else_fall:
                env = _merge_status_envs(body_env, else_env)
            elif body_fall:
                env = body_env
            elif else_fall:
                env = else_env
            else:
                return returns, False, env
    return returns, True, env


def _process_projection_result_used(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    params: set[str],
    origins: Mapping[str, set[str]],
    defs: Mapping[str, Sequence[ast.AST]],
    trusted_clock_names: frozenset[str],
) -> bool:
    returns, _, _ = _collect_return_statuses(
        fn.body,
        status_env={},
        params=params,
        origins=origins,
        defs=defs,
        trusted_clock_names=trusted_clock_names,
    )
    if not returns:
        return False
    return all(_UNSAFE_ACCEPT not in statuses for statuses in returns)

def _direct_retained_replay(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    defs: Mapping[str, Sequence[ast.AST]],
    trusted_clock_names: frozenset[str],
) -> bool:
    params = set(_function_params(fn))
    origins = _origins(fn, defs, trusted_clock_names)
    retained = any(
        isinstance(node, ast.Call)
        and _projection_call(node)
        and _retained_time_argument(
            node,
            params=params,
            origins=origins,
            defs=defs,
            trusted_clock_names=trusted_clock_names,
        )
        for node in ast.walk(fn)
    )
    if not retained:
        return False
    return not _process_projection_result_used(
        fn,
        params=params,
        origins=origins,
        defs=defs,
        trusted_clock_names=trusted_clock_names,
    )


__all__ = [name for name in globals() if not name.startswith("__")]
