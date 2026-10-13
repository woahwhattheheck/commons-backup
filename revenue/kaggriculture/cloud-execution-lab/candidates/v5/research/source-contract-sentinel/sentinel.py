#!/usr/bin/env python3
"""Heuristic source-contract drift sentinel for TITAN V5.

This tool is deliberately advisory by default.  It finds boundary idioms that
have repeatedly diverged from the pinned evaluator contract so reviewers can
inspect them before a policy carrier is merged.  It does not claim that every
finding is a bug.

Suppression syntax, on the finding line or immediately above it:
    # contract-sentinel: ignore=RAW_OPCODE_INDEX
    # contract-sentinel: ignore=RAW_OPCODE_INDEX,EXACT_ROW_LEN3
    # contract-sentinel: ignore=*
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Iterable, Iterator, Sequence

RULE_RAW_OPCODE_INDEX = "RAW_OPCODE_INDEX"
RULE_EXACT_ROW_LEN3 = "EXACT_ROW_LEN3"
RULE_PUBLIC_OBS_COERCION = "PUBLIC_OBS_COERCION"
RULE_TRUTHY_CONFIG_COERCION = "TRUTHY_CONFIG_COERCION"
RULE_INPUT_ERROR = "INPUT_ERROR"

RULES = (
    RULE_RAW_OPCODE_INDEX,
    RULE_EXACT_ROW_LEN3,
    RULE_PUBLIC_OBS_COERCION,
    RULE_TRUTHY_CONFIG_COERCION,
)

_ROW_NAMES = frozenset({"a", "entry", "o", "order", "row"})
_OBS_NAMES = frozenset({"obs", "observation"})
_CONFIG_NAMES = frozenset({"cfg", "config", "configuration", "feature_data", "features"})
_PUBLIC_FIELDS = frozenset({"day", "hour", "player", "step"})
_SUPPRESSION = re.compile(r"#\s*contract-sentinel:\s*ignore=([A-Z0-9_*, -]+)")


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    line: int
    column: int
    rule: str
    message: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _slice_value(node: ast.Subscript) -> ast.AST:
    return node.slice


def _literal(node: ast.AST) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    return None


def _root_name(node: ast.AST) -> str | None:
    while isinstance(node, (ast.Subscript, ast.Attribute, ast.Call)):
        if isinstance(node, ast.Subscript):
            node = node.value
        elif isinstance(node, ast.Attribute):
            node = node.value
        else:
            if isinstance(node.func, ast.Attribute):
                node = node.func.value
            else:
                break
    return node.id if isinstance(node, ast.Name) else None


def _mentions_public_observation(node: ast.AST) -> bool:
    for part in ast.walk(node):
        if isinstance(part, ast.Subscript):
            root = _root_name(part)
            if root in _OBS_NAMES and _literal(_slice_value(part)) in _PUBLIC_FIELDS:
                return True
        if isinstance(part, ast.Call) and isinstance(part.func, ast.Attribute):
            root = _root_name(part.func.value)
            if root in _OBS_NAMES and part.func.attr == "get" and part.args:
                if _literal(part.args[0]) in _PUBLIC_FIELDS:
                    return True
    return False


def _mentions_config(node: ast.AST) -> bool:
    return any(isinstance(part, ast.Name) and part.id in _CONFIG_NAMES for part in ast.walk(node))


def _len3_subject(node: ast.Compare) -> ast.Name | None:
    if len(node.ops) != 1 or len(node.comparators) != 1:
        return None
    if not isinstance(node.ops[0], (ast.Eq, ast.NotEq)):
        return None
    left, right = node.left, node.comparators[0]
    call = left if isinstance(left, ast.Call) else right if isinstance(right, ast.Call) else None
    value = right if call is left else left if call is right else None
    if call is None or value is None or _literal(value) != 3:
        return None
    if not isinstance(call.func, ast.Name) or call.func.id != "len" or len(call.args) != 1:
        return None
    subject = call.args[0]
    return subject if isinstance(subject, ast.Name) and subject.id in _ROW_NAMES else None


def _raw_opcode_subject(node: ast.Subscript) -> ast.Name | None:
    if _literal(_slice_value(node)) != 0:
        return None
    value = node.value
    return value if isinstance(value, ast.Name) and value.id in _ROW_NAMES else None


def _suppressed(lines: Sequence[str], line: int, rule: str) -> bool:
    for index in (line - 1, line - 2):
        if not (0 <= index < len(lines)):
            continue
        match = _SUPPRESSION.search(lines[index])
        if not match:
            continue
        tokens = {token.strip() for token in match.group(1).split(",")}
        if "*" in tokens or rule in tokens:
            return True
    return False


def scan_source(source: str, path: str = "<memory>") -> list[Finding]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [Finding(path, exc.lineno or 1, exc.offset or 0, "SYNTAX_ERROR", str(exc.msg))]
    lines = source.splitlines()
    findings: list[Finding] = []
    seen: set[tuple[int, int, str]] = set()

    def add(node: ast.AST, rule: str, message: str) -> None:
        line = int(getattr(node, "lineno", 1))
        column = int(getattr(node, "col_offset", 0))
        key = (line, column, rule)
        if key in seen or _suppressed(lines, line, rule):
            return
        seen.add(key)
        findings.append(Finding(path, line, column, rule, message))

    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            subject = _raw_opcode_subject(node)
            if subject is not None:
                add(
                    node,
                    RULE_RAW_OPCODE_INDEX,
                    f"raw {subject.id}[0] opcode access; confirm list/nonempty guard and pinned parser grammar",
                )
        elif isinstance(node, ast.Compare):
            subject = _len3_subject(node)
            if subject is not None:
                add(
                    node,
                    RULE_EXACT_ROW_LEN3,
                    f"exact len({subject.id}) ==/!= 3 boundary; confirm pinned parser accepts/rejects trailing fields",
                )
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"int", "float"} and node.args and _mentions_public_observation(node.args[0]):
                add(
                    node,
                    RULE_PUBLIC_OBS_COERCION,
                    "public observation field is numerically coerced; confirm exact-type/range/clock binding",
                )
            elif node.func.id == "bool" and node.args and _mentions_config(node.args[0]):
                add(
                    node,
                    RULE_TRUTHY_CONFIG_COERCION,
                    "config/feature value is coerced by truthiness; confirm exact declared type before side effects",
                )

    return sorted(findings)


def iter_python_files(roots: Iterable[Path]) -> Iterator[Path]:
    seen: set[Path] = set()
    for root in roots:
        root = root.resolve()
        if root.is_file():
            candidates = [root] if root.suffix == ".py" else []
        elif root.is_dir():
            candidates = root.rglob("*.py")
        else:
            continue
        for path in candidates:
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            parts = set(resolved.parts)
            if "__pycache__" in parts:
                continue
            yield resolved


def _display_path(path: Path, display_root: Path | None) -> str:
    if display_root is not None:
        try:
            return path.relative_to(display_root).as_posix()
        except ValueError:
            pass
    return path.as_posix()


def scan_paths(roots: Iterable[Path], *, display_root: Path | None = None) -> list[Finding]:
    display_root = display_root.resolve() if display_root is not None else None
    findings: list[Finding] = []
    valid_roots: list[Path] = []
    for requested in roots:
        try:
            root = requested.resolve()
        except OSError:
            findings.append(
                Finding(requested.as_posix(), 1, 0, RULE_INPUT_ERROR, "cannot resolve scan root")
            )
            continue
        label = _display_path(root, display_root)
        if not root.exists():
            findings.append(Finding(label, 1, 0, RULE_INPUT_ERROR, "scan root does not exist"))
            continue
        if root.is_file() and root.suffix != ".py":
            findings.append(
                Finding(label, 1, 0, RULE_INPUT_ERROR, "scan root is not a Python file")
            )
            continue
        if not root.is_file() and not root.is_dir():
            findings.append(
                Finding(label, 1, 0, RULE_INPUT_ERROR, "scan root is not a regular file or directory")
            )
            continue
        valid_roots.append(root)

    for path in iter_python_files(valid_roots):
        label = _display_path(path, display_root)
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeError:
            findings.append(
                Finding(label, 1, 0, RULE_INPUT_ERROR, "cannot read Python source as UTF-8")
            )
            continue
        except OSError:
            findings.append(Finding(label, 1, 0, RULE_INPUT_ERROR, "cannot read Python source"))
            continue
        findings.extend(scan_source(source, label))
    return sorted(findings)


def _default_roots(script: Path) -> tuple[Path, ...]:
    lab = script.resolve().parents[4]
    return (
        lab / "main.py",
        lab / "titan_runtime.py",
        lab / "spatial_tempo.py",
        lab / "early_capital.py",
        lab / "fourth_quadrant.py",
        lab / "terminal_history_join.py",
        lab / "reference" / "titan-current",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", type=Path, help="files/directories to scan")
    parser.add_argument("--json", action="store_true", help="emit deterministic JSON")
    parser.add_argument(
        "--fail-on",
        action="append",
        choices=RULES + ("SYNTAX_ERROR", RULE_INPUT_ERROR),
        default=[],
        help="return 1 when this rule is present (repeatable)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="make finding paths relative to this directory",
    )
    args = parser.parse_args(argv)
    script = Path(__file__)
    roots = tuple(args.roots) or _default_roots(script)
    findings = scan_paths(roots, display_root=args.repo_root)

    if args.json:
        print(json.dumps([finding.to_dict() for finding in findings], sort_keys=True, indent=2))
    else:
        for finding in findings:
            print(
                f"{finding.path}:{finding.line}:{finding.column + 1}: "
                f"{finding.rule}: {finding.message}"
            )
        print(f"source-contract-sentinel: {len(findings)} finding(s)")

    if any(finding.rule == RULE_INPUT_ERROR for finding in findings):
        return 2
    fail_rules = set(args.fail_on)
    return int(any(finding.rule in fail_rules for finding in findings))


if __name__ == "__main__":
    raise SystemExit(main())
