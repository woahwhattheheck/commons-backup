#!/usr/bin/env python3
"""Small fail-closed lints for defect classes with reliable static signatures.

The registry deliberately contains manual-only classes too.  This program emits
only rules whose source signature can be checked without guessing semantics.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

WORKFLOW_SUFFIXES = {".yml", ".yaml"}
CLEAN_TREE_RE = re.compile(
    r"(?:git\s+diff(?:\s+--(?:quiet|exit-code|check))?|git\s+status\s+--porcelain|test\s+-z\s+.*git\s+status\s+--porcelain)"
)
PY_COMPILE_RE = re.compile(r"\bpython(?:3(?:\.\d+)?)?\b[^\n]*\s-m\s+py_compile\b")
NO_BYTECODE_RE = re.compile(r"(?:\bpython(?:3(?:\.\d+)?)?\s+-B\b|\bPYTHONDONTWRITEBYTECODE\s*=\s*1\b)")
RUN_BLOCK_RE = re.compile(r"^(?P<indent>\s*)(?:-\s+)?run\s*:\s*[|>]\s*(?:#.*)?$")
RUN_INLINE_RE = re.compile(r"^(?P<indent>\s*)(?:-\s+)?run\s*:\s*(?P<body>.+?)\s*$")
LIST_ITEM_RE = re.compile(r"^(?P<indent>\s*)-\s+")
UPLOAD_RE = re.compile(r"\buses\s*:\s*actions/upload-artifact@", re.IGNORECASE)
ALWAYS_RE = re.compile(r"\bif\s*:\s*(?:\$\{\{\s*)?always\(\)(?:\s*\}\})?\s*(?:#.*)?$", re.IGNORECASE)
EXPR_RE = re.compile(r"\$\{\{")


@dataclass(frozen=True)
class Finding:
    defect_id: str
    path: str
    line: int
    message: str


def _indent_width(text: str) -> int:
    return len(text) - len(text.lstrip(" "))


def _run_blocks(lines: list[str]) -> Iterable[tuple[int, int, str]]:
    """Yield (start line index, end-exclusive index, command text)."""
    i = 0
    while i < len(lines):
        match = RUN_BLOCK_RE.match(lines[i])
        if match:
            base = len(match.group("indent"))
            start = i
            i += 1
            body: list[str] = []
            while i < len(lines):
                raw = lines[i]
                if raw.strip() and _indent_width(raw) <= base:
                    break
                body.append(raw)
                i += 1
            yield start, i, "\n".join(body)
            continue
        inline = RUN_INLINE_RE.match(lines[i])
        if inline and not inline.group("body").lstrip().startswith(("|", ">")):
            yield i, i + 1, inline.group("body")
        i += 1


def _step_slices(lines: list[str]) -> Iterable[tuple[int, int]]:
    """Conservatively split YAML list items; sufficient for individual steps."""
    starts: list[tuple[int, int]] = []
    for i, line in enumerate(lines):
        match = LIST_ITEM_RE.match(line)
        if match:
            starts.append((i, len(match.group("indent"))))
    for pos, (start, indent) in enumerate(starts):
        end = len(lines)
        for next_start, next_indent in starts[pos + 1 :]:
            if next_indent <= indent:
                end = next_start
                break
        yield start, end


def lint_workflow(path: Path, text: str) -> list[Finding]:
    lines = text.splitlines()
    findings: list[Finding] = []

    for start, end, body in _run_blocks(lines):
        body_lines = lines[start:end]
        # Expressions are risky specifically in multiline run bodies; inline run
        # expressions are not classified by this rule.
        if end > start + 1:
            for offset, raw in enumerate(body_lines[1:], start=1):
                if EXPR_RE.search(raw):
                    findings.append(Finding(
                        "workflow.run_block_expression",
                        path.as_posix(),
                        start + offset + 1,
                        "multiline run block contains a GitHub expression; pass the value via env/input instead",
                    ))

        py_match = PY_COMPILE_RE.search(body)
        clean_matches = list(CLEAN_TREE_RE.finditer(body))
        if py_match and clean_matches and any(m.start() > py_match.start() for m in clean_matches):
            if not NO_BYTECODE_RE.search(body):
                # Report the first physical line containing py_compile.
                line_no = start + 1
                for idx in range(start, end):
                    if "py_compile" in lines[idx]:
                        line_no = idx + 1
                        break
                findings.append(Finding(
                    "workflow.py_compile_clean_tree",
                    path.as_posix(),
                    line_no,
                    "py_compile precedes a clean-tree assertion without -B or PYTHONDONTWRITEBYTECODE=1",
                ))

    for start, end in _step_slices(lines):
        step = "\n".join(lines[start:end])
        if UPLOAD_RE.search(step) and any(ALWAYS_RE.search(line.strip()) for line in lines[start:end]):
            use_line = next((idx + 1 for idx in range(start, end) if UPLOAD_RE.search(lines[idx])), start + 1)
            findings.append(Finding(
                "workflow.artifact_always",
                path.as_posix(),
                use_line,
                "upload-artifact step is guarded by if: always(); failed/stale evidence can be retained",
            ))

    return findings


def iter_workflows(paths: Iterable[Path]) -> Iterable[Path]:
    seen: set[Path] = set()
    for supplied in paths:
        if supplied.is_dir():
            candidates = (p for p in supplied.rglob("*") if p.is_file() and p.suffix.lower() in WORKFLOW_SUFFIXES)
        elif supplied.is_file() and supplied.suffix.lower() in WORKFLOW_SUFFIXES:
            candidates = (supplied,)
        else:
            continue
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield candidate


def lint_paths(paths: Iterable[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_workflows(paths):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            findings.append(Finding(
                "lint.unreadable_input", path.as_posix(), 1, f"cannot read workflow as UTF-8: {exc}"
            ))
            continue
        findings.extend(lint_workflow(path, text))
    return sorted(findings, key=lambda f: (f.path, f.line, f.defect_id))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, default=[Path(".github/workflows")])
    parser.add_argument("--json", action="store_true", help="emit a JSON array")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    findings = lint_paths(args.paths)
    if args.json:
        print(json.dumps([asdict(item) for item in findings], sort_keys=True, indent=2))
    else:
        for item in findings:
            print(f"{item.path}:{item.line}: {item.defect_id}: {item.message}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
