#!/usr/bin/env python3
"""Deterministically inventory likely TITAN W10 producer integration seams.

The scanner is deliberately static and observation-only. It ranks source files
and symbols by lifecycle vocabulary, records exact source hashes, and never
claims that a lexical hit proves runtime behavior.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import os
import re
import tokenize
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

SCAN_SCHEMA = "titan.w10.producer-surface-scan/v1"
DEFAULT_SCOPE = "revenue/kaggriculture/cloud-execution-lab"
EXCLUDED_PARTS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    "venv",
    "node_modules",
}
SELF_SCOPE_PARTS = ("analysis", "w10-fertilizer-cycle")

_PHASE_PATTERNS: tuple[tuple[str, re.Pattern[str], int], ...] = (
    (
        "fertilizer",
        re.compile(
            r"(?:fertili[sz]\w*|compost\w*|manure\w*|soil\s*amend\w*)", re.I
        ),
        7,
    ),
    (
        "production",
        re.compile(r"(?:produc\w*|yield\w*|growth\w*|crop\w*|matur\w*)", re.I),
        2,
    ),
    ("harvest", re.compile(r"(?:harvest\w*|reap\w*|gather\w*)", re.I), 5),
    (
        "storage",
        re.compile(
            r"(?:deposit\w*|inventory\w*|warehouse\w*|shed\w*|stor(?:e|age|ed|ing)\w*)",
            re.I,
        ),
        5,
    ),
    (
        "sale_cash",
        re.compile(
            r"(?:sell\w*|sale\w*|market\w*|cash\w*|revenue\w*|price\w*)", re.I
        ),
        6,
    ),
    (
        "timing_action",
        re.compile(r"(?:tick\w*|worker\w*|action\w*|travel\w*|move\w*|step\w*)", re.I),
        2,
    ),
    (
        "protection",
        re.compile(
            r"(?:obligation\w*|commitment\w*|protect\w*|reserve\w*|shortfall\w*)",
            re.I,
        ),
        4,
    ),
)
_PHASE_WEIGHTS = {phase: weight for phase, _, weight in _PHASE_PATTERNS}
_DOWNSTREAM_PHASES = {"harvest", "storage", "sale_cash"}


class ScanError(ValueError):
    """Raised when the requested scan cannot be performed safely."""


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _normalize_token(token: str) -> str:
    token = token.strip().lower().replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", token)


def _token_hits(text: str) -> dict[str, list[dict[str, Any]]]:
    hits: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, int, str]] = set()
    tokens: list[tokenize.TokenInfo] = []
    try:
        stream = tokenize.generate_tokens(io.StringIO(text).readline)
        while True:
            tokens.append(next(stream))
    except StopIteration:
        pass
    except (tokenize.TokenError, IndentationError):
        # Preserve lexical evidence emitted before the malformed tail. The AST
        # parse error is reported separately; partial tokenization must not
        # silently erase the candidate surface.
        pass

    for token in tokens:
        if token.type not in (tokenize.NAME, tokenize.STRING):
            continue
        normalized = _normalize_token(token.string)
        if not normalized:
            continue
        for phase, pattern, _ in _PHASE_PATTERNS:
            if pattern.search(normalized) is None:
                continue
            clipped = normalized[:96]
            key = (phase, token.start[0], clipped)
            if key in seen or len(hits[phase]) >= 100:
                continue
            seen.add(key)
            hits[phase].append({"line": token.start[0], "token": clipped})

    return {phase: rows for phase, rows in sorted(hits.items())}


def _symbol_inventory(
    text: str, hits: Mapping[str, Sequence[Mapping[str, Any]]]
) -> tuple[list[dict[str, Any]], str | None]:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [], f"SyntaxError:{exc.lineno or 0}:{exc.offset or 0}:{exc.msg}"

    symbols: list[dict[str, Any]] = []
    stack: list[str] = []

    class Visitor(ast.NodeVisitor):
        def _record(self, node: ast.AST, name: str, kind: str) -> None:
            qualified = ".".join((*stack, name)) if stack else name
            start = int(getattr(node, "lineno", 0) or 0)
            end = int(getattr(node, "end_lineno", start) or start)
            phases = sorted(
                phase
                for phase, rows in hits.items()
                if any(start <= int(row["line"]) <= end for row in rows)
            )
            symbols.append(
                {
                    "kind": kind,
                    "name": qualified,
                    "line": start,
                    "end_line": end,
                    "phases": phases,
                }
            )

        def visit_ClassDef(self, node: ast.ClassDef) -> Any:
            self._record(node, node.name, "class")
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
            self._record(node, node.name, "function")
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
            self._record(node, node.name, "async-function")
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

    Visitor().visit(tree)
    symbols.sort(key=lambda row: (row["line"], row["kind"], row["name"]))
    return symbols, None


def _score(phases: Sequence[str], symbols: Sequence[Mapping[str, Any]]) -> int:
    score = sum(_PHASE_WEIGHTS[phase] for phase in phases)
    score += sum(2 for symbol in symbols if len(symbol["phases"]) >= 2)
    if "fertilizer" in phases and _DOWNSTREAM_PHASES.issubset(phases):
        score += 12
    elif "fertilizer" in phases and _DOWNSTREAM_PHASES.intersection(phases):
        score += 5
    return score


def _iter_python_files(scope: Path) -> Iterable[Path]:
    for directory, dirnames, filenames in os.walk(scope, followlinks=False):
        current = Path(directory)
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name not in EXCLUDED_PARTS and not (current / name).is_symlink()
        )
        for filename in sorted(filenames):
            path = current / filename
            if filename.endswith(".py") and not path.is_symlink():
                yield path


def _is_self_analysis(relative: Path) -> bool:
    parts = relative.parts
    for index in range(len(parts) - len(SELF_SCOPE_PARTS) + 1):
        if parts[index : index + len(SELF_SCOPE_PARTS)] == SELF_SCOPE_PARTS:
            return True
    return False


def scan_repository(
    *,
    root: Path,
    scope: Path | str = Path(DEFAULT_SCOPE),
    max_file_bytes: int = 2 * 1024 * 1024,
    max_files: int = 10_000,
    max_results: int = 500,
) -> dict[str, Any]:
    """Return a deterministic lexical/AST inventory of likely producer seams."""

    if max_file_bytes < 1 or max_files < 1 or max_results < 1:
        raise ScanError("scan limits must be positive integers")

    root = root.resolve()
    if not root.is_dir() or root.is_symlink():
        raise ScanError("root must be a real directory, not a symlink")

    requested_scope = Path(scope)
    if requested_scope.is_absolute():
        resolved_scope = requested_scope.resolve()
    else:
        resolved_scope = (root / requested_scope).resolve()
    if not _under(resolved_scope, root):
        raise ScanError("scope escapes root")
    if not resolved_scope.is_dir() or resolved_scope.is_symlink():
        raise ScanError("scope must be a real directory inside root")

    scope_name = resolved_scope.relative_to(root).as_posix() or "."
    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    scanned_files = 0

    for path in _iter_python_files(resolved_scope):
        scanned_files += 1
        if scanned_files > max_files:
            raise ScanError(f"scan exceeds max_files={max_files}")
        relative = path.relative_to(root)
        relative_name = relative.as_posix()
        if _is_self_analysis(relative):
            continue
        try:
            raw = path.read_bytes()
        except OSError as exc:
            skipped.append(
                {
                    "path": relative_name,
                    "reason": f"read-error:{type(exc).__name__}",
                }
            )
            continue
        if len(raw) > max_file_bytes:
            skipped.append({"path": relative_name, "reason": "oversized"})
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            skipped.append({"path": relative_name, "reason": "non-utf8"})
            continue

        hits = _token_hits(text)
        phases = sorted(hits)
        if not phases:
            continue
        symbols, parse_error = _symbol_inventory(text, hits)
        score = _score(phases, symbols)
        candidates.append(
            {
                "path": relative_name,
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "score": score,
                "phases": phases,
                "full_cycle_candidate": "fertilizer" in phases
                and _DOWNSTREAM_PHASES.issubset(phases),
                "parse_error": parse_error,
                "hits": hits,
                "symbols": symbols,
            }
        )

    candidates.sort(key=lambda row: (-row["score"], row["path"]))
    truncated = len(candidates) > max_results
    candidates = candidates[:max_results]
    skipped.sort(key=lambda row: (row["path"], row["reason"]))
    surface_found = any(
        "fertilizer" in row["phases"]
        and _DOWNSTREAM_PHASES.intersection(row["phases"])
        for row in candidates
    )

    body: dict[str, Any] = {
        "schema": SCAN_SCHEMA,
        "decision": "SURFACE_FOUND" if surface_found else "NO_SURFACE",
        "scope": scope_name,
        "limits": {
            "max_file_bytes": max_file_bytes,
            "max_files": max_files,
            "max_results": max_results,
        },
        "counts": {
            "scanned_python_files": scanned_files,
            "candidate_files": len(candidates),
            "skipped_files": len(skipped),
        },
        "truncated": truncated,
        "candidates": candidates,
        "skipped": skipped,
        "warning": (
            "Lexical/AST ranking identifies integration seams; it does not prove "
            "runtime behavior or authorize producer mutation."
        ),
    }
    body["result_sha256"] = canonical_sha256(body)
    return body


def _default_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / ".git").exists() or (parent / "README.md").is_file():
            return parent
    # A standalone copied script may have no repository marker or six parents.
    # In that case use its containing directory instead of raising at startup.
    return current.parent


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inventory likely TITAN W10 producer integration surfaces."
    )
    parser.add_argument("--root", type=Path, default=_default_root())
    parser.add_argument("--scope", type=Path, default=Path(DEFAULT_SCOPE))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--allow-empty", action="store_true")
    parser.add_argument("--max-file-bytes", type=int, default=2 * 1024 * 1024)
    parser.add_argument("--max-files", type=int, default=10_000)
    parser.add_argument("--max-results", type=int, default=500)
    args = parser.parse_args(argv)

    try:
        result = scan_repository(
            root=args.root,
            scope=args.scope,
            max_file_bytes=args.max_file_bytes,
            max_files=args.max_files,
            max_results=args.max_results,
        )
    except ScanError as exc:
        parser.error(str(exc))

    rendered = json.dumps(
        result,
        sort_keys=True,
        indent=2 if args.pretty else None,
        separators=None if args.pretty else (",", ":"),
    ) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if args.allow_empty or result["decision"] == "SURFACE_FOUND" else 1


if __name__ == "__main__":
    raise SystemExit(main())
