"""Shared model for the workflow sparse-import closure compiler."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

SCHEMA = "commons-workflow-sparse-import-closure/v1"
CONFIG_SCHEMA = "commons-workflow-sparse-import-closure-config/v1"
_STATUS_RANK = {"PASS": 0, "SKIP": 0, "UNKNOWN": 1, "FAIL": 2}


class ContractError(ValueError):
    """The audit invocation or config is malformed."""

@dataclass(frozen=True)
class Step:
    number: int
    name: str
    uses: str | None
    run: str | None
    sparse_checkout: tuple[str, ...] | None
    sparse_literal: bool

@dataclass(frozen=True)
class Job:
    name: str
    steps: tuple[Step, ...]

@dataclass(frozen=True)
class Entry:
    kind: str
    target: str
    command: str

def _status(values: Iterable[str]) -> str:
    rows = list(values)
    if not rows or all(value == "SKIP" for value in rows):
        return "SKIP"
    result = "PASS"
    for value in rows:
        if _STATUS_RANK.get(value, 2) > _STATUS_RANK[result]:
            result = value
    return result

def _finding_key(value: dict[str, object]) -> tuple[str, ...]:
    return tuple(str(value.get(key, "")) for key in (
        "code", "workflow", "job", "step", "source", "line", "target", "import", "command"
    ))
