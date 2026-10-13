"""Parse workflow steps, shell entrypoints, and literal sparse patterns."""
from __future__ import annotations

import json
import re
import shlex
from pathlib import Path, PurePosixPath
from typing import Iterator, Sequence

from tools.workflow_sparse_import_closure_common import (
    Entry, Job, Step, ContractError, _finding_key,
)

_PYTHON = re.compile(r"^(?:python(?:3(?:\.\d+)?)?|pypy(?:3)?)$")
_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$", re.S)
_SAFE_JOB = re.compile(r"^[A-Za-z0-9_.-]+$")
_SAFE_PATH = re.compile(r"^[A-Za-z0-9_./-]+$")
_BLOCK = re.compile(r"^[>|][+-]?$")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))

def _dequote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        if value[0] == "'":
            return value[1:-1].replace("''", "'")
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, str) else value[1:-1]
        except json.JSONDecodeError:
            return value[1:-1]
    return value

def _block_value(lines: Sequence[str], key_index: int, key_indent: int) -> tuple[str, int]:
    """Return a YAML literal block and the first line after it."""
    collected: list[str] = []
    index = key_index + 1
    while index < len(lines):
        raw = lines[index]
        if raw.strip() and _indent(raw) <= key_indent:
            break
        collected.append(raw)
        index += 1
    nonblank = [_indent(line) for line in collected if line.strip()]
    content_indent = min(nonblank) if nonblank else key_indent + 2
    value = "\n".join(
        line[content_indent:] if len(line) >= content_indent else ""
        for line in collected
    )
    return value, index

def _step_value(lines: Sequence[str], key: str) -> tuple[str | None, bool]:
    """Read a top-level step key, supporting first-line '- key:' syntax."""
    patterns = (
        re.compile(r"^ {6}-\s*" + re.escape(key) + r":(?:\s*(.*))?$"),
        re.compile(r"^ {8}" + re.escape(key) + r":(?:\s*(.*))?$"),
    )
    for index, line in enumerate(lines):
        for pattern in patterns:
            match = pattern.match(line)
            if not match:
                continue
            tail = (match.group(1) or "").strip()
            key_indent = 6 if line.startswith("      -") else 8
            if _BLOCK.fullmatch(tail):
                value, _ = _block_value(lines, index, key_indent)
                return value, True
            if tail:
                return _dequote(tail), True
            return "", True
    return None, False

def _sparse_value(lines: Sequence[str]) -> tuple[tuple[str, ...] | None, bool]:
    """Read with.sparse-checkout. None/True means ordinary full checkout."""
    for index, line in enumerate(lines):
        match = re.match(r"^ {10}sparse-checkout:(?:\s*(.*))?$", line)
        if not match:
            continue
        tail = (match.group(1) or "").strip()
        if _BLOCK.fullmatch(tail):
            value, _ = _block_value(lines, index, 10)
            return tuple(value.splitlines()), True
        # Inline values and expressions are valid Actions input, but this compiler
        # deliberately does not invent their selection semantics.
        if tail:
            return (tail,), False
        return tuple(), False
    return None, True

def parse_workflow_bytes(text: str, path: str = "<workflow>") -> tuple[Job, ...]:
    """Parse only the workflow job/step surface needed by this compiler."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if "\t" in text:
        raise ContractError(f"{path}: tab-indented YAML is unsupported")
    lines = text.splitlines()
    jobs_line = next(
        (index for index, line in enumerate(lines) if line == "jobs:"),
        None,
    )
    if jobs_line is None:
        return tuple()

    job_starts: list[tuple[int, str]] = []
    for index in range(jobs_line + 1, len(lines)):
        line = lines[index]
        if line.strip() and _indent(line) == 0:
            break
        match = re.match(r"^ {2}([A-Za-z0-9_.-]+):(?:\s*(?:#.*)?)?$", line)
        if match and _SAFE_JOB.fullmatch(match.group(1)):
            job_starts.append((index, match.group(1)))
    jobs: list[Job] = []
    for offset, (start, name) in enumerate(job_starts):
        end = job_starts[offset + 1][0] if offset + 1 < len(job_starts) else len(lines)
        # Do not let the last job consume a later top-level section.
        for index in range(start + 1, end):
            if lines[index].strip() and _indent(lines[index]) == 0:
                end = index
                break
        steps_line = next(
            (index for index in range(start + 1, end)
             if re.match(r"^ {4}steps:(?:\s*(?:#.*)?)?$", lines[index])),
            None,
        )
        if steps_line is None:
            jobs.append(Job(name=name, steps=tuple()))
            continue
        step_starts = [
            index for index in range(steps_line + 1, end)
            if re.match(r"^ {6}-(?:\s|$)", lines[index])
        ]
        steps: list[Step] = []
        for number, step_start in enumerate(step_starts, 1):
            step_end = step_starts[number] if number < len(step_starts) else end
            segment = lines[step_start:step_end]
            uses, _ = _step_value(segment, "uses")
            run, _ = _step_value(segment, "run")
            step_name, _ = _step_value(segment, "name")
            sparse, literal = _sparse_value(segment)
            steps.append(
                Step(
                    number=number,
                    name=step_name or f"step-{number}",
                    uses=uses,
                    run=run,
                    sparse_checkout=sparse,
                    sparse_literal=literal,
                )
            )
        jobs.append(Job(name=name, steps=tuple(steps)))
    return tuple(jobs)

def _shell_segments(script: str) -> Iterator[list[str]]:
    # Fold ordinary shell continuations, then parse each shell command line.
    # Heredoc bodies remain separate lines and are ignored unless a line itself
    # starts with a recognized Python runner.
    script = re.sub(r"\\\s*\n", " ", script.replace("\r\n", "\n").replace("\r", "\n"))
    for line in script.splitlines():
        if not line.strip():
            continue
        try:
            lexer = shlex.shlex(line, posix=True, punctuation_chars=";&|")
            lexer.whitespace_split = True
            lexer.commenters = "#"
            tokens = list(lexer)
        except ValueError:
            continue
        current: list[str] = []
        for token in tokens:
            if token in {";", "&&", "||", "&"} or (token and set(token) <= {";", "&", "|"}):
                if current:
                    yield current
                    current = []
            else:
                current.append(token)
        if current:
            yield current

def _strip_prefix(tokens: list[str]) -> list[str]:
    tokens = list(tokens)
    while tokens and _ENV_ASSIGN.match(tokens[0]):
        tokens.pop(0)
    if tokens and tokens[0] == "env":
        tokens.pop(0)
        while tokens and (_ENV_ASSIGN.match(tokens[0]) or tokens[0].startswith("-")):
            tokens.pop(0)
    while len(tokens) >= 2 and tokens[0] in {"uv", "poetry", "pipenv"} and tokens[1] == "run":
        tokens = tokens[2:]
    return tokens

def _python_name(token: str) -> bool:
    return bool(_PYTHON.fullmatch(PurePosixPath(token).name))

def _path_token(token: str) -> str:
    token = token.split("::", 1)[0]
    return token.rstrip(",:")

def _targets_from_test_runner(kind: str, args: Sequence[str], command: str) -> list[Entry]:
    result: list[Entry] = []
    skip_next = False
    for token in args:
        if skip_next:
            skip_next = False
            continue
        if token in {"-k", "-m", "--maxfail", "--ignore", "--rootdir", "-p"}:
            skip_next = True
            continue
        if token.startswith("-"):
            continue
        target = _path_token(token)
        if target.endswith(".py") or "/" in target or target.startswith("."):
            result.append(Entry(kind="path", target=target, command=command))
        elif kind == "unittest" and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", target):
            # unittest accepts dotted modules and class/method suffixes. Resolution
            # progressively trims the suffix until a local module exists.
            result.append(Entry(kind="module-prefix", target=target, command=command))
    return result

def extract_entries(script: str) -> tuple[list[Entry], list[dict[str, object]]]:
    entries: list[Entry] = []
    findings: list[dict[str, object]] = []
    for raw in _shell_segments(script):
        tokens = _strip_prefix(raw)
        if not tokens:
            continue
        command = shlex.join(raw)
        first = PurePosixPath(tokens[0]).name
        if first in {"pytest", "py.test"}:
            if len(tokens) == 1:
                findings.append({"code": "IMPLICIT_TEST_DISCOVERY", "command": command, "target": first})
            else:
                entries.extend(_targets_from_test_runner("pytest", tokens[1:], command))
            continue
        if first in {"unittest"}:
            if len(tokens) == 1 or tokens[1] == "discover":
                findings.append({"code": "IMPLICIT_TEST_DISCOVERY", "command": command, "target": first})
            else:
                entries.extend(_targets_from_test_runner("unittest", tokens[1:], command))
            continue
        if not _python_name(tokens[0]):
            continue
        args = tokens[1:]
        index = 0
        while index < len(args):
            token = args[index]
            if token == "-m":
                if index + 1 >= len(args):
                    findings.append({"code": "MALFORMED_PYTHON_COMMAND", "command": command})
                    break
                module = args[index + 1]
                rest = args[index + 2:]
                if module in {"pytest", "unittest"}:
                    if not rest or (module == "unittest" and rest[0] == "discover"):
                        findings.append({
                            "code": "IMPLICIT_TEST_DISCOVERY",
                            "command": command,
                            "target": module,
                        })
                    else:
                        entries.extend(_targets_from_test_runner(module, rest, command))
                elif module == "py_compile":
                    for candidate in rest:
                        if candidate.startswith("-"):
                            continue
                        candidate = _path_token(candidate)
                        if candidate.endswith(".py"):
                            entries.append(Entry("path", candidate, command))
                elif "$" in module or "${{" in module:
                    findings.append({"code": "DYNAMIC_ENTRYPOINT", "command": command, "target": module})
                else:
                    entries.append(Entry("module", module, command))
                break
            if token in {"-c", "-"}:
                # Inline Python is not a repository entrypoint. Literal source is
                # intentionally not interpreted as shell/YAML/Python simultaneously.
                break
            if token in {"-X", "-W"}:
                index += 2
                continue
            if token.startswith("-"):
                index += 1
                continue
            target = _path_token(token)
            if "$" in target or "${{" in target:
                findings.append({"code": "DYNAMIC_ENTRYPOINT", "command": command, "target": target})
            elif target.endswith(".py"):
                entries.append(Entry("path", target, command))
            break
        # otherwise this is an interactive/version invocation
    unique = {(entry.kind, entry.target, entry.command): entry for entry in entries}
    return [unique[key] for key in sorted(unique)], sorted(findings, key=_finding_key)

def normalize_patterns(lines: Sequence[str]) -> tuple[list[str], list[dict[str, object]]]:
    patterns: list[str] = []
    findings: list[dict[str, object]] = []
    for raw in lines:
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        if (value.startswith("!") or "${{" in value or any(char in value for char in "*?[")
                or "\\" in value):
            findings.append({"code": "UNSUPPORTED_SPARSE_PATTERN", "pattern": value})
            continue
        value = value.lstrip("/")
        while value.startswith("./"):
            value = value[2:]
        pure = PurePosixPath(value)
        if not value or pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            findings.append({"code": "UNSUPPORTED_SPARSE_PATTERN", "pattern": raw.strip()})
            continue
        if not _SAFE_PATH.fullmatch(value):
            findings.append({"code": "UNSUPPORTED_SPARSE_PATTERN", "pattern": raw.strip()})
            continue
        patterns.append(value.rstrip("/"))
    return sorted(set(patterns)), sorted(findings, key=_finding_key)

def _selected(root: Path, rel: str, patterns: Sequence[str]) -> bool:
    rel = PurePosixPath(rel).as_posix()
    for pattern in patterns:
        candidate = root / pattern
        if rel == pattern:
            return True
        if candidate.is_dir() and rel.startswith(pattern + "/"):
            return True
    return False

