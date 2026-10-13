#!/usr/bin/env python3
"""Constrain duplicate GitHub Actions push gates to the default branch.

This tool scans .github/workflows/*.yml and *.yaml under one or more repository
roots. By default it only changes workflows that have BOTH structured `push`
and `pull_request` triggers. That preserves pull-request CI while preventing a
feature-branch push (especially a merge/rebase from main) from launching a
second copy of the same path-scoped workflow.

No third-party dependencies are required. The default mode is --check and does
not write files. Use --diff to review, then --write to apply atomically.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import stat
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

_ON_RE = re.compile(
    r'^(?P<indent> *)(?P<key>on|["\']on["\']):(?P<tail>[^\r\n]*)$'
)
_EVENT_RE = re.compile(
    r'^(?P<indent> *)(?P<key>push|pull_request):(?P<tail>[^\r\n]*)$'
)
_DIRECT_KEY_RE = re.compile(
    r'^(?P<indent> *)(?P<key>[A-Za-z0-9_-]+):(?P<tail>[^\r\n]*)$'
)


@dataclass(frozen=True)
class TransformResult:
    changed: bool
    status: str
    detail: str
    text: str


@dataclass(frozen=True)
class FileResult:
    path: str
    status: str
    detail: str
    changed: bool


def _content(line: str) -> str:
    return line.rstrip("\r\n")


def _newline_for(text: str) -> str:
    if "\r\n" in text:
        return "\r\n"
    return "\n"


def _indent_width(line: str) -> int:
    stripped = line.lstrip(" ")
    return len(line) - len(stripped)


def _is_blank_or_comment(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith("#")


def _next_block_end(lines: Sequence[str], start: int, parent_indent: int) -> int:
    """Return the first line after a YAML mapping block."""
    for index in range(start + 1, len(lines)):
        raw = _content(lines[index])
        if _is_blank_or_comment(raw):
            continue
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            return index
        if _indent_width(raw) <= parent_indent:
            return index
    return len(lines)


def transform_text(
    text: str,
    *,
    default_branch: str = "main",
    include_push_only: bool = False,
) -> TransformResult:
    if not default_branch or any(ch.isspace() for ch in default_branch):
        raise ValueError("default_branch must be a non-empty branch name without whitespace")

    newline = _newline_for(text)
    lines = text.splitlines(keepends=True)
    if not lines and text == "":
        return TransformResult(False, "no_on_block", "empty file", text)

    on_index = None
    on_match = None
    for index, line in enumerate(lines):
        raw = _content(line)
        match = _ON_RE.match(raw)
        if match and len(match.group("indent")) == 0:
            on_index = index
            on_match = match
            break

    if on_index is None or on_match is None:
        # Inline forms such as `on: [push, pull_request]` are deliberately not
        # rewritten because converting arbitrary flow YAML safely requires a
        # parser and can alter comments/anchors.
        for line in lines:
            raw = _content(line)
            if re.match(r'^(?:on|["\']on["\']):\s*\S', raw):
                return TransformResult(
                    False,
                    "inline_on_skipped",
                    "top-level on trigger uses inline/flow syntax",
                    text,
                )
        return TransformResult(False, "no_on_block", "no structured top-level on block", text)

    on_tail = on_match.group("tail").strip()
    if on_tail and not on_tail.startswith("#"):
        return TransformResult(
            False,
            "inline_on_skipped",
            "top-level on trigger has an inline value",
            text,
        )

    on_indent = len(on_match.group("indent"))
    block_end = _next_block_end(lines, on_index, on_indent)
    event_indent = on_indent + 2

    push_index = None
    push_match = None
    has_pull_request = False
    for index in range(on_index + 1, block_end):
        raw = _content(lines[index])
        match = _EVENT_RE.match(raw)
        if not match or len(match.group("indent")) != event_indent:
            continue
        if match.group("key") == "push":
            push_index = index
            push_match = match
        elif match.group("key") == "pull_request":
            has_pull_request = True

    if push_index is None or push_match is None:
        return TransformResult(False, "no_push", "workflow has no structured push trigger", text)

    if not has_pull_request and not include_push_only:
        return TransformResult(
            False,
            "push_only_skipped",
            "workflow has no structured pull_request trigger",
            text,
        )

    push_tail = push_match.group("tail").strip()
    if push_tail and not push_tail.startswith("#") and push_tail not in {"{}", "{ }"}:
        return TransformResult(
            False,
            "inline_push_skipped",
            "push trigger uses an inline value that was not rewritten",
            text,
        )

    push_indent = len(push_match.group("indent"))
    push_end = _next_block_end(lines, push_index, push_indent)

    for index in range(push_index + 1, push_end):
        raw = _content(lines[index])
        match = _DIRECT_KEY_RE.match(raw)
        if not match or len(match.group("indent")) != push_indent + 2:
            continue
        if match.group("key") == "branches":
            return TransformResult(
                False,
                "already_scoped",
                "push trigger already declares branches",
                text,
            )
        if match.group("key") == "branches-ignore":
            return TransformResult(
                False,
                "branches_ignore_skipped",
                "push trigger declares branches-ignore; manual semantic review required",
                text,
            )

    old_line = lines[push_index]
    old_raw = _content(old_line)
    old_ending = old_line[len(old_raw):] or newline

    # Normalize only an empty inline map. Preserve comments on ordinary `push:`.
    if push_tail in {"{}", "{ }"}:
        prefix = old_raw[: old_raw.index(":") + 1]
        lines[push_index] = prefix + old_ending

    insertion = (" " * (push_indent + 2)) + f"branches: [{default_branch}]" + newline
    lines.insert(push_index + 1, insertion)
    transformed = "".join(lines)

    return TransformResult(
        True,
        "changed",
        f"scoped push trigger to {default_branch!r}",
        transformed,
    )


def workflow_files(root: Path) -> Iterable[Path]:
    workflows = root / ".github" / "workflows"
    if not workflows.is_dir():
        return ()
    files = sorted(
        path
        for pattern in ("*.yml", "*.yaml")
        for path in workflows.rglob(pattern)
        if path.is_file() and not path.is_symlink()
    )
    return files


def _atomic_write(path: Path, text: str) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, mode)
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "roots",
        nargs="*",
        type=Path,
        default=[Path(".")],
        help="repository roots (default: current directory)",
    )
    parser.add_argument("--default-branch", default="main")
    parser.add_argument(
        "--include-push-only",
        action="store_true",
        help="also scope workflows with push but no pull_request trigger",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="report drift; do not write (default)")
    mode.add_argument("--diff", action="store_true", help="print unified diffs; do not write")
    mode.add_argument("--write", action="store_true", help="apply changes atomically")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="return exit 2 for unsupported inline/branches-ignore forms",
    )
    parser.add_argument("--json-report", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    mode = "write" if args.write else "diff" if args.diff else "check"
    results: list[FileResult] = []
    changed_count = 0
    unsupported_count = 0

    for root in args.roots:
        root = root.resolve()
        files = tuple(workflow_files(root))
        if not files:
            results.append(
                FileResult(str(root), "no_workflows", "no .github/workflows YAML files", False)
            )
            continue

        for path in files:
            with path.open("r", encoding="utf-8", newline="") as handle:
                original = handle.read()
            outcome = transform_text(
                original,
                default_branch=args.default_branch,
                include_push_only=args.include_push_only,
            )
            relative = str(path.relative_to(root))
            results.append(
                FileResult(relative, outcome.status, outcome.detail, outcome.changed)
            )

            if outcome.status in {
                "inline_on_skipped",
                "inline_push_skipped",
                "branches_ignore_skipped",
            }:
                unsupported_count += 1

            if not outcome.changed:
                continue

            changed_count += 1
            if mode == "diff":
                sys.stdout.writelines(
                    difflib.unified_diff(
                        original.splitlines(keepends=True),
                        outcome.text.splitlines(keepends=True),
                        fromfile=f"a/{relative}",
                        tofile=f"b/{relative}",
                    )
                )
            elif mode == "write":
                _atomic_write(path, outcome.text)

    summary = {
        "mode": mode,
        "roots": [str(path.resolve()) for path in args.roots],
        "default_branch": args.default_branch,
        "include_push_only": args.include_push_only,
        "files_seen": len(results),
        "changes_required_or_applied": changed_count,
        "unsupported_requiring_review": unsupported_count,
        "results": [asdict(item) for item in results],
    }

    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        args.json_report.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    if mode != "diff":
        print(json.dumps(summary, indent=2, sort_keys=True))

    if args.strict and unsupported_count:
        return 2
    if mode in {"check", "diff"} and changed_count:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
