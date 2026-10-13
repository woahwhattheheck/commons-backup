#!/usr/bin/env python3
"""Fail closed on truthy activation of changed default-OFF TITAN V4 seams.

This validator is intentionally incremental: callers provide the files changed by
one pull request. Existing untouched research debt therefore cannot block an
unrelated repair, while newly added or edited ``enabled=False`` boundaries must
preserve literal-bool activation semantics.

The contract is deliberately narrow and mechanical. A callable whose parameter
is literally named ``enabled`` and defaults to the bool ``False`` may not rely on
Python truthiness, value/equality comparisons, or identity-to-False to decide
activation. Only literal ``enabled is True`` is a safe positive identity test.
A top-level fail-closed guard that rejects every non-bool (or everything except
literal True) before the first truthiness use also makes later truthiness safe.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence

DEFAULT_SCOPE = PurePosixPath(
    "revenue/kaggriculture/cloud-execution-lab/candidates/v4"
)


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    line: int
    column: int
    function: str
    message: str


MESSAGE = (
    "default-OFF enabled=False has a fail-open boolean use; require "
    "enabled is True / an earlier enabled is not True exit guard, "
    "or reject non-bools first"
)


def _literal_bool(node: ast.AST, value: bool) -> bool:
    return (
        isinstance(node, ast.Constant)
        and type(node.value) is bool
        and node.value is value
    )


def _name(node: ast.AST, value: str) -> bool:
    return isinstance(node, ast.Name) and node.id == value


def _call(node: ast.AST, name: str, argc: int | None = None) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == name
        and (argc is None or len(node.args) == argc)
        and not node.keywords
    )


def _enabled_default_false(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    positional = [*fn.args.posonlyargs, *fn.args.args]
    defaults = fn.args.defaults
    if defaults:
        for arg, default in zip(positional[-len(defaults):], defaults):
            if arg.arg == "enabled" and _literal_bool(default, False):
                return True
    for arg, default in zip(fn.args.kwonlyargs, fn.args.kw_defaults):
        if (
            arg.arg == "enabled"
            and default is not None
            and _literal_bool(default, False)
        ):
            return True
    return False


def _enabled_bool_identity(node: ast.AST) -> tuple[type[ast.cmpop], bool] | None:
    """Return (operator type, literal bool) for a direct enabled identity test."""
    if (
        not isinstance(node, ast.Compare)
        or len(node.ops) != 1
        or len(node.comparators) != 1
        or not isinstance(node.ops[0], (ast.Is, ast.IsNot))
    ):
        return None
    left, right = node.left, node.comparators[0]
    if _name(left, "enabled"):
        if _literal_bool(right, True):
            return type(node.ops[0]), True
        if _literal_bool(right, False):
            return type(node.ops[0]), False
    if _name(right, "enabled"):
        if _literal_bool(left, True):
            return type(node.ops[0]), True
        if _literal_bool(left, False):
            return type(node.ops[0]), False
    return None


def _unsafe_boolean_nodes(node: ast.AST) -> list[ast.AST]:
    """Return direct fail-open boolean/coercion uses of ``enabled``."""
    if _name(node, "enabled"):
        return [node]

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return _unsafe_boolean_nodes(node.operand)

    if isinstance(node, ast.BoolOp):
        out: list[ast.AST] = []
        for value in node.values:
            out.extend(_unsafe_boolean_nodes(value))
        return out

    if isinstance(node, ast.NamedExpr):
        return _unsafe_boolean_nodes(node.value)

    if isinstance(node, ast.Compare):
        identity = _enabled_bool_identity(node)
        if identity is not None:
            op_type, literal = identity
            # Only a positive literal-True test is intrinsically safe.
            # "is not True" is safe only when recognized separately as an
            # exiting fail-closed guard. Identity to False lets non-bools
            # bypass default-OFF semantics and is therefore unsafe here.
            if op_type is ast.Is and literal is True:
                return []
            values = [node.left, *node.comparators]
            return [next(value for value in values if _name(value, "enabled"))]

        values = [node.left, *node.comparators]
        direct_enabled = next(
            (value for value in values if _name(value, "enabled")),
            None,
        )
        if direct_enabled is not None:
            # Any other direct comparison computes activation from value/equality
            # semantics rather than literal-bool identity. This includes numeric
            # equality/order and membership such as ``enabled == 1`` or
            # ``enabled in (1,)``; truthy non-bools may satisfy those forms.
            return [direct_enabled]
        return []

    if _call(node, "bool", 1) and _name(node.args[0], "enabled"):
        return [node.args[0]]

    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"any", "all"}
        and len(node.args) == 1
        and not node.keywords
    ):
        iterable = node.args[0]
        if isinstance(iterable, (ast.Tuple, ast.List, ast.Set)):
            for item in iterable.elts:
                hits = _unsafe_boolean_nodes(item)
                if hits:
                    return hits
        elif isinstance(iterable, ast.Dict):
            for item in iterable.keys:
                if item is None:
                    continue
                hits = _unsafe_boolean_nodes(item)
                if hits:
                    return hits
        elif isinstance(iterable, (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
            hits = _unsafe_boolean_nodes(iterable.elt)
            if hits:
                return hits
        elif isinstance(iterable, ast.DictComp):
            hits = _unsafe_boolean_nodes(iterable.key)
            if hits:
                return hits

    # Deliberately do not guess about arbitrary helper(enabled) calls. This
    # guard targets Python boolean activation, not semantic review of helpers.
    return []


def _suite_always_exits(body: Sequence[ast.stmt]) -> bool:
    if not body:
        return False
    tail = body[-1]
    if isinstance(tail, (ast.Return, ast.Raise)):
        return True
    if isinstance(tail, ast.If):
        return (
            bool(tail.orelse)
            and _suite_always_exits(tail.body)
            and _suite_always_exits(tail.orelse)
        )
    return False


def _is_nonbool_reject_test(node: ast.AST) -> bool:
    # "enabled is not True" is the strongest/default contract: only literal
    # True can proceed after an exiting top-level guard.
    identity = _enabled_bool_identity(node)
    if identity == (ast.IsNot, True):
        return True

    if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
        left, right = node.left, node.comparators[0]
        if isinstance(node.ops[0], ast.IsNot):
            if (
                _call(left, "type", 1)
                and _name(left.args[0], "enabled")
                and _name(right, "bool")
            ):
                return True
            if (
                _name(left, "bool")
                and _call(right, "type", 1)
                and _name(right.args[0], "enabled")
            ):
                return True

    # if not isinstance(enabled, bool): return/raise
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        call = node.operand
        if _call(call, "isinstance", 2):
            return _name(call.args[0], "enabled") and _name(call.args[1], "bool")
    return False


def _is_strict_guard(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.If)
        and _is_nonbool_reject_test(stmt.test)
        and _suite_always_exits(stmt.body)
    )


def _strict_guard_line(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> int | None:
    lines = [stmt.lineno for stmt in fn.body if _is_strict_guard(stmt)]
    return min(lines) if lines else None


class _TruthinessVisitor(ast.NodeVisitor):
    def __init__(self, root: ast.FunctionDef | ast.AsyncFunctionDef):
        self.root = root
        self.hits: list[ast.AST] = []

    def _record(self, node: ast.AST) -> None:
        self.hits.extend(_unsafe_boolean_nodes(node))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        if node is self.root:
            for stmt in node.body:
                self.visit(stmt)
        # Nested callables have their own parameters and are analyzed separately.

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        if node is self.root:
            for stmt in node.body:
                self.visit(stmt)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:  # noqa: N802
        return

    def visit_If(self, node: ast.If) -> None:  # noqa: N802
        if not _is_strict_guard(node):
            self._record(node.test)
        for stmt in [*node.body, *node.orelse]:
            self.visit(stmt)

    def visit_While(self, node: ast.While) -> None:  # noqa: N802
        self._record(node.test)
        for stmt in [*node.body, *node.orelse]:
            self.visit(stmt)

    def visit_Assert(self, node: ast.Assert) -> None:  # noqa: N802
        self._record(node.test)
        if node.msg is not None:
            self.visit(node.msg)

    def visit_IfExp(self, node: ast.IfExp) -> None:  # noqa: N802
        self._record(node.test)
        self.visit(node.body)
        self.visit(node.orelse)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        hits = _unsafe_boolean_nodes(node)
        if hits:
            self.hits.extend(hits)
            # Do not descend into the same direct coercion and double count it.
            return
        self.generic_visit(node)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:  # noqa: N802
        if isinstance(node.op, ast.Not):
            hits = _unsafe_boolean_nodes(node)
            if hits:
                self.hits.extend(hits)
                return
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:  # noqa: N802
        hits = _unsafe_boolean_nodes(node)
        if hits:
            self.hits.extend(hits)
            # Still inspect child calls/comparisons that may produce a distinct
            # finding on another enabled use.
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:  # noqa: N802
        hits = _unsafe_boolean_nodes(node)
        if hits:
            self.hits.extend(hits)
            return
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:  # noqa: N802
        self.visit(node.iter)
        for item in node.ifs:
            self._record(item)


def analyze_source(source: str, *, path: str = "<memory>") -> list[Finding]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [
            Finding(
                path=path,
                line=exc.lineno or 0,
                column=exc.offset or 0,
                function="<module>",
                message=f"cannot parse Python source: {exc.msg}",
            )
        ]

    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _enabled_default_false(node):
            continue

        visitor = _TruthinessVisitor(node)
        visitor.visit(node)
        hits = sorted(
            set(visitor.hits),
            key=lambda hit: (
                getattr(hit, "lineno", 0),
                getattr(hit, "col_offset", 0),
            ),
        )
        if not hits:
            continue

        guard_line = _strict_guard_line(node)
        first_hit_line = getattr(hits[0], "lineno", 0)
        if guard_line is not None and guard_line < first_hit_line:
            continue

        for hit in hits:
            findings.append(
                Finding(
                    path=path,
                    line=getattr(hit, "lineno", node.lineno),
                    column=getattr(hit, "col_offset", 0) + 1,
                    function=node.name,
                    message=MESSAGE,
                )
            )
    return sorted(set(findings))


def _safe_relative(raw: str) -> PurePosixPath | None:
    raw = raw.strip()
    if not raw or "\\" in raw:
        return None
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        return None
    return path


def scan_paths(
    root: Path,
    paths: Iterable[str],
    *,
    scope: PurePosixPath = DEFAULT_SCOPE,
) -> tuple[list[Finding], list[str]]:
    root = root.resolve()
    selected: set[PurePosixPath] = set()
    errors: list[str] = []

    for raw in paths:
        rel = _safe_relative(raw)
        if rel is None:
            if raw.strip():
                errors.append(f"unsafe changed path {raw.strip()!r}")
            continue
        try:
            rel.relative_to(scope)
        except ValueError:
            continue
        if rel.suffix != ".py":
            continue
        selected.add(rel)

    findings: list[Finding] = []
    for rel in sorted(selected, key=str):
        target = root.joinpath(*rel.parts)
        if target.is_symlink():
            errors.append(f"{rel}: changed Python source must not be a symlink")
            continue
        if not target.is_file():
            errors.append(f"{rel}: changed Python source is missing or not a regular file")
            continue
        try:
            source = target.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"{rel}: cannot read UTF-8 source: {exc}")
            continue
        findings.extend(analyze_source(source, path=rel.as_posix()))

    return sorted(findings), sorted(errors)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="repo-relative changed paths")
    parser.add_argument("--root", default=os.getcwd())
    parser.add_argument("--scope", default=DEFAULT_SCOPE.as_posix())
    parser.add_argument("--paths-from-stdin", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    raw_paths = list(args.paths)
    if args.paths_from_stdin:
        raw_paths.extend(line.rstrip("\n") for line in __import__("sys").stdin)
    scope = _safe_relative(args.scope)
    if scope is None:
        parser.error("--scope must be a safe repo-relative path")

    findings, errors = scan_paths(Path(args.root), raw_paths, scope=scope)
    ok = not findings and not errors

    if args.json:
        print(
            json.dumps(
                {
                    "ok": ok,
                    "findings": [asdict(item) for item in findings],
                    "errors": errors,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    else:
        for error in errors:
            print(f"ERROR: {error}")
        for finding in findings:
            print(
                f"{finding.path}:{finding.line}:{finding.column}: "
                f"{finding.function}: {finding.message}"
            )
        checked = len(
            {
                p
                for p in (_safe_relative(item) for item in raw_paths)
                if p is not None
                and p.suffix == ".py"
                and (p == scope or scope in p.parents)
            }
        )
        print(
            f"TITAN V4 activation contract: {'PASS' if ok else 'FAIL'} "
            f"({checked} changed Python path(s), {len(findings)} finding(s), "
            f"{len(errors)} error(s))"
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
