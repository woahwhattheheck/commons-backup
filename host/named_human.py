"""Conservative hygiene checks for labels intended to name a human actor.

This module does *not* authenticate a person and does not grant authorization. A
passing label is only syntactically free of obvious automation/service markers;
callers must enforce identity, role, approval, and permission separately.
"""
from __future__ import annotations

import unicodedata
from typing import Any


RESERVED_IDENTITY_TOKENS = frozenset(
    {
        "ai",
        "agent",
        "auto",
        "automated",
        "automation",
        "bot",
        "robot",
        "service",
        "system",
    }
)
_MAX_RESERVED_TOKEN_LENGTH = max(map(len, RESERVED_IDENTITY_TOKENS))


def _alphabetic_runs(label: str) -> tuple[str, ...]:
    """Split an NFKC-normalized, case-folded label into Unicode alphabetic runs."""

    normalized = unicodedata.normalize("NFKC", label).casefold()
    runs: list[str] = []
    current: list[str] = []
    for char in normalized:
        if char.isalpha():
            current.append(char)
            continue
        if current:
            runs.append("".join(current))
            current.clear()
    if current:
        runs.append("".join(current))
    return tuple(runs)


def _has_segmented_reserved_token(runs: tuple[str, ...]) -> bool:
    """Catch reserved words reconstructed from two or more adjacent runs."""

    for start in range(len(runs)):
        joined = runs[start]
        if len(joined) >= _MAX_RESERVED_TOKEN_LENGTH:
            continue
        for stop in range(start + 1, len(runs)):
            joined += runs[stop]
            if joined in RESERVED_IDENTITY_TOKENS:
                return True
            if len(joined) >= _MAX_RESERVED_TOKEN_LENGTH:
                break
    return False


def is_named_human_label(label: Any, *, min_parts: int = 1) -> bool:
    """Return whether ``label`` is a plausible human-name *label*.

    The result is a presentation-layer hygiene signal only. It is not evidence that
    a real person supplied the label and must never substitute for authentication or
    an authorization/approval check.
    """

    if isinstance(min_parts, bool) or not isinstance(min_parts, int) or min_parts < 1:
        raise ValueError("min_parts must be a positive integer")
    if not isinstance(label, str):
        return False

    runs = _alphabetic_runs(label)
    if len(runs) < min_parts:
        return False
    if any(token in RESERVED_IDENTITY_TOKENS for token in runs):
        return False
    if _has_segmented_reserved_token(runs):
        return False
    return True
