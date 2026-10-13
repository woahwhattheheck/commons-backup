from __future__ import annotations

from ._model import *
from ._flow_positive import _assignment_targets, _assignment_value

def _trusted_clock_call(
    node: ast.Call,
    *,
    params: set[str],
    defs: Mapping[str, Sequence[ast.AST]],
    trusted_clock_names: frozenset[str],
) -> bool:
    name = _name(node.func)
    if name not in trusted_clock_names:
        return False
    root = name.split(".", 1)[0]
    return root not in params and root not in defs


def _expr_sources(
    node: ast.AST | None,
    *,
    params: set[str],
    origins: Mapping[str, set[str]],
    defs: Mapping[str, Sequence[ast.AST]],
    trusted_clock_names: frozenset[str],
    seen: frozenset[str] = frozenset(),
) -> set[str]:
    if node is None:
        return set()
    if isinstance(node, ast.Name):
        if node.id in origins:
            return set(origins[node.id])
        if node.id in params:
            return {node.id}
        if node.id in defs and node.id not in seen:
            result: set[str] = set()
            for value in defs[node.id]:
                result |= _expr_sources(
                    value,
                    params=params,
                    origins=origins,
                    defs=defs,
                    trusted_clock_names=trusted_clock_names,
                    seen=seen | {node.id},
                )
            return result
        return set()
    if isinstance(node, ast.Call):
        if _trusted_clock_call(
            node,
            params=params,
            defs=defs,
            trusted_clock_names=trusted_clock_names,
        ):
            return {_PROCESS_CLOCK}
        result = _expr_sources(
            node.func,
            params=params,
            origins=origins,
            defs=defs,
            trusted_clock_names=trusted_clock_names,
            seen=seen,
        )
        for argument in node.args:
            result |= _expr_sources(
                argument,
                params=params,
                origins=origins,
                defs=defs,
                trusted_clock_names=trusted_clock_names,
                seen=seen,
            )
        for keyword in node.keywords:
            result |= _expr_sources(
                keyword.value,
                params=params,
                origins=origins,
                defs=defs,
                trusted_clock_names=trusted_clock_names,
                seen=seen,
            )
        return result
    result: set[str] = set()
    for child in ast.iter_child_nodes(node):
        result |= _expr_sources(
            child,
            params=params,
            origins=origins,
            defs=defs,
            trusted_clock_names=trusted_clock_names,
            seen=seen,
        )
    return result


def _origins(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    defs: Mapping[str, Sequence[ast.AST]],
    trusted_clock_names: frozenset[str],
) -> dict[str, set[str]]:
    params = set(_function_params(fn))
    out: dict[str, set[str]] = {name: {name} for name in params}
    for _ in range(12):
        changed = False
        for node in ast.walk(fn):
            value = _assignment_value(node)
            if value is None:
                continue
            sources = _expr_sources(
                value,
                params=params,
                origins=out,
                defs=defs,
                trusted_clock_names=trusted_clock_names,
            )
            for target in _assignment_targets(node):
                before = set(out.get(target, set()))
                merged = before | sources
                if merged != before:
                    out[target] = merged
                    changed = True
        if not changed:
            break
    return out


def _deadline_expr(node: ast.AST) -> bool:
    return _has_word(node, _DEADLINE_WORDS)


def _direct_time_requirements(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    defs: Mapping[str, Sequence[ast.AST]],
    trusted_clock_names: frozenset[str],
) -> list[frozenset[str]]:
    params = set(_function_params(fn))
    origins = _origins(fn, defs, trusted_clock_names)
    out: list[frozenset[str]] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Compare):
            continue
        operands = [node.left, *node.comparators]
        for left in operands:
            sources = _expr_sources(
                left,
                params=params,
                origins=origins,
                defs=defs,
                trusted_clock_names=trusted_clock_names,
            )
            caller_sources = frozenset(source for source in sources if source in params)
            if caller_sources and any(right is not left and _deadline_expr(right) for right in operands):
                out.append(caller_sources)
                break
    return out


def _call_argument(call: ast.Call, callee: _FunctionModel, parameter: str) -> ast.AST | None:
    try:
        index = callee.params.index(parameter)
    except ValueError:
        return None
    if index < len(call.args):
        return call.args[index]
    for keyword in call.keywords:
        if keyword.arg == parameter:
            return keyword.value
    return None


def _projection_call(call: ast.Call) -> bool:
    name = _name(call.func).lower()
    return any(
        word in name
        for word in ("compile", "evaluate", "qualify", "project", "semantic", "readiness", "gate", "state")
    )


def _retained_time_argument(
    call: ast.Call,
    *,
    params: set[str],
    origins: Mapping[str, set[str]],
    defs: Mapping[str, Sequence[ast.AST]],
    trusted_clock_names: frozenset[str],
) -> bool:
    for keyword in call.keywords:
        sources = _expr_sources(
            keyword.value,
            params=params,
            origins=origins,
            defs=defs,
            trusted_clock_names=trusted_clock_names,
        )
        if sources & params and (
            (keyword.arg is not None and any(word in keyword.arg.lower() for word in _TIME_WORDS))
            or _has_word(keyword.value, _TIME_WORDS)
        ):
            return True
    for argument in call.args:
        sources = _expr_sources(
            argument,
            params=params,
            origins=origins,
            defs=defs,
            trusted_clock_names=trusted_clock_names,
        )
        if sources & params and _has_word(argument, _TIME_WORDS):
            return True
    return False


_PROCESS_REQUIRED = "PROCESS_REQUIRED"
_SAFE_FAILURE = "SAFE_FAILURE"
_UNSAFE_ACCEPT = "UNSAFE_ACCEPT"



__all__ = [name for name in globals() if not name.startswith("__")]
