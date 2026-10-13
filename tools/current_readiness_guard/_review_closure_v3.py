from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence

from ._model import (
    Finding,
    _authority_name,
    _collect_function_specs,
    _function_params,
    _historical_surface,
    _local_defs,
    _name,
    _positive_state,
    _public,
)
from ._review_closure_v2 import (
    _BOOLEAN_SURFACE_WORDS,
    _GUARD_CALL_WORDS,
    _authority_refs,
    _boolean_positive_expression,
    _call_argument_by_param,
    _direct_authority_facts,
    _iter_return_paths,
    _module_static_strings,
    _resolve_call,
    _truth_controlled_by_parameter,
)

_MAX_STATIC_CHOICES = 64


def _static_values(
    node: ast.AST | None,
    local_defs: Mapping[str, Sequence[ast.AST]],
    globals_: Mapping[str, frozenset[str]],
    *,
    seen: frozenset[str] = frozenset(),
) -> frozenset[str]:
    if node is None:
        return frozenset()
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return frozenset({node.value})
    if isinstance(node, ast.Name):
        result = set(globals_.get(node.id, frozenset()))
        if node.id in local_defs and node.id not in seen:
            next_seen = seen | {node.id}
            for value in local_defs[node.id]:
                result.update(_static_values(value, local_defs, globals_, seen=next_seen))
                if len(result) > _MAX_STATIC_CHOICES:
                    return frozenset()
        return frozenset(result)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _static_values(node.left, local_defs, globals_, seen=seen)
        right = _static_values(node.right, local_defs, globals_, seen=seen)
        if not left or not right or len(left) * len(right) > _MAX_STATIC_CHOICES:
            return frozenset()
        return frozenset(a + b for a in left for b in right)
    if isinstance(node, ast.JoinedStr):
        values: set[str] = {""}
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                choices = {part.value}
            elif isinstance(part, ast.FormattedValue):
                choices = set(_static_values(part.value, local_defs, globals_, seen=seen))
            else:
                return frozenset()
            if not choices or len(values) * len(choices) > _MAX_STATIC_CHOICES:
                return frozenset()
            values = {prefix + choice for prefix in values for choice in choices}
        return frozenset(values)
    if isinstance(node, ast.IfExp):
        return _static_values(node.body, local_defs, globals_, seen=seen) | _static_values(
            node.orelse, local_defs, globals_, seen=seen
        )
    return frozenset()


def _alias_target(node: ast.AST, aliases: Mapping[str, str]) -> str | None:
    raw = _name(node)
    if not raw:
        return None
    seen: set[str] = set()
    while raw in aliases and raw not in seen:
        seen.add(raw)
        raw = aliases[raw]
    return raw


_UNRESOLVED_ALIAS = "<unresolved>"


def _record_alias_candidate(candidates: dict[str, set[str]], name: str, value: ast.AST) -> None:
    raw = _name(value)
    candidates.setdefault(name, set()).add(raw if raw else _UNRESOLVED_ALIAS)


def _finalize_aliases(candidates: Mapping[str, set[str]]) -> tuple[dict[str, str], set[str]]:
    aliases: dict[str, str] = {}
    ambiguous: set[str] = set()
    for name, values in candidates.items():
        if len(values) == 1:
            only = next(iter(values))
            if only == _UNRESOLVED_ALIAS:
                ambiguous.add(name)
            else:
                aliases[name] = only
        else:
            ambiguous.add(name)
    return aliases, ambiguous


def _module_aliases(tree: ast.Module) -> tuple[dict[str, str], set[str]]:
    candidates: dict[str, set[str]] = {}
    for statement in tree.body:
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
            continue
        value = statement.value
        if value is None:
            continue
        targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
        for target in targets:
            if isinstance(target, ast.Name):
                _record_alias_candidate(candidates, target.id, value)
    return _finalize_aliases(candidates)


def _class_aliases(tree: ast.Module) -> tuple[dict[str, str], set[str]]:
    candidates: dict[str, set[str]] = {}

    def collect(statements: Sequence[ast.stmt], owner: str | None = None) -> None:
        for statement in statements:
            if not isinstance(statement, ast.ClassDef):
                continue
            class_key = f"{owner}.{statement.name}" if owner else statement.name
            for member in statement.body:
                if isinstance(member, (ast.Assign, ast.AnnAssign)):
                    value = member.value
                    if value is None:
                        continue
                    targets = member.targets if isinstance(member, ast.Assign) else [member.target]
                    for target in targets:
                        if isinstance(target, ast.Name):
                            raw = _name(value)
                            if raw and "." not in raw:
                                raw = f"{class_key}.{raw}"
                            elif not raw:
                                raw = _UNRESOLVED_ALIAS
                            candidates.setdefault(f"{class_key}.{target.id}", set()).add(raw)
                elif isinstance(member, ast.ClassDef):
                    collect([member], class_key)

    collect(tree.body)
    return _finalize_aliases(candidates)


def _aliases_for_function(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    base_aliases: Mapping[str, str],
    base_ambiguous: set[str],
) -> tuple[dict[str, str], set[str]]:
    aliases = dict(base_aliases)
    ambiguous = set(base_ambiguous)
    defs = _local_defs(fn)
    for _ in range(max(1, len(defs) + 1)):
        changed = False
        for name, values in defs.items():
            resolved: set[str] = set()
            unresolved = False
            for value in values:
                target = _alias_target(value, aliases)
                if target is None:
                    unresolved = True
                else:
                    resolved.add(target)
            if unresolved or len(resolved) != 1:
                if name not in ambiguous or name in aliases:
                    aliases.pop(name, None)
                    ambiguous.add(name)
                    changed = True
            else:
                target = next(iter(resolved))
                if aliases.get(name) != target or name in ambiguous:
                    aliases[name] = target
                    ambiguous.discard(name)
                    changed = True
        if not changed:
            break
    return aliases, ambiguous


def _condition_facts_factory(
    spec,
    specs_by_key: Mapping[str, object],
    aliases: Mapping[str, str],
    ambiguous: set[str],
):
    def condition(node: ast.AST, authority_params: set[str], truth: bool) -> set[str]:
        direct = _direct_authority_facts(node, authority_params, truth=truth)
        if direct or not truth or not isinstance(node, ast.Call):
            return direct
        call_name = _name(node.func)
        refs = _authority_refs(node, authority_params)
        if not refs:
            return set()

        canonical_call = call_name
        if spec.owner is not None and (call_name.startswith("self.") or call_name.startswith("cls.")):
            canonical_call = f"{spec.owner}.{call_name.split('.', 1)[1]}"
        if call_name in ambiguous or canonical_call in ambiguous:
            return set()

        target_name = aliases.get(call_name, aliases.get(canonical_call, call_name))
        if not any(
            word in call_name.lower() or word in target_name.lower()
            for word in _GUARD_CALL_WORDS
        ):
            return set()

        resolved = _resolve_call(target_name, spec, specs_by_key)
        if resolved is None:
            if canonical_call != call_name:
                return set()
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


def _expand_return(
    expression: ast.AST | None,
    env: Mapping[str, tuple[tuple[ast.AST, frozenset[str]], ...]],
    facts: frozenset[str],
    *,
    seen: frozenset[str] = frozenset(),
) -> list[tuple[ast.AST | None, frozenset[str]]]:
    if isinstance(expression, ast.Name) and expression.id in env and expression.id not in seen:
        out: list[tuple[ast.AST | None, frozenset[str]]] = []
        next_seen = seen | {expression.id}
        for bound_expression, bound_facts in env[expression.id]:
            out.extend(
                _expand_return(
                    bound_expression,
                    env,
                    frozenset(set(facts) | set(bound_facts)),
                    seen=next_seen,
                )
            )
        return out
    return [(expression, facts)]


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

    specs = _collect_function_specs(tree)
    specs_by_key = {spec.key: spec for spec in specs}
    globals_ = _module_static_strings(tree)
    module_aliases, module_ambiguous = _module_aliases(tree)
    class_aliases, class_ambiguous = _class_aliases(tree)
    base_aliases = {**module_aliases, **class_aliases}
    base_ambiguous = module_ambiguous | class_ambiguous
    out: list[Finding] = []

    for spec in specs:
        fn = spec.node
        if not spec.surface or not _public(fn) or _historical_surface(fn):
            continue
        authority_params = {name for name in _function_params(fn) if _authority_name(name)}
        aliases, ambiguous = _aliases_for_function(fn, base_aliases, base_ambiguous)
        condition = _condition_facts_factory(spec, specs_by_key, aliases, ambiguous)
        paths, _, _, _ = _iter_return_paths(
            fn.body, authority_params, condition_facts=condition
        )

        risky = False
        for expression, facts, env in paths:
            local_map = {
                name: tuple(item[0] for item in bounds) for name, bounds in env.items()
            }
            for expanded, expanded_facts in _expand_return(expression, env, facts):
                static_positive = any(
                    _positive_state(value)
                    for value in _static_values(expanded, local_map, globals_)
                )
                boolean_positive = False
                boolean_facts: set[str] = set()
                if any(word in fn.name.lower() for word in _BOOLEAN_SURFACE_WORDS):
                    boolean_positive, boolean_facts = _boolean_positive_expression(
                        expanded, authority_params
                    )
                if (static_positive or boolean_positive) and not expanded_facts and not boolean_facts:
                    risky = True
                    break
            if risky:
                break

        if risky:
            out.append(
                Finding(
                    path,
                    fn.lineno,
                    fn.col_offset + 1,
                    "CRG003",
                    "a current-positive path remains uncontrolled after local-composition and validator-alias resolution",
                    spec.key,
                )
            )

    return sorted(set(out))


__all__ = ["additional_findings"]
