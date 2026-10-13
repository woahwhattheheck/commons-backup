#!/usr/bin/env python3
"""Fail closed on bare actions/checkout@v4 in evidence workflows.

An evidence workflow is either explicitly marked with
``# evidence-workflow: true`` or has an evidence-oriented filename token.
The linter intentionally checks one narrow defect class: an
``actions/checkout@v4`` step in such a workflow must have a ``with:`` block
containing a non-empty ``ref:``. It does not try to prove that the ref
expression itself is authoritative; the reusable exact-head workflow is the
preferred primitive when a caller needs that stronger guarantee.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

EVIDENCE_NAME_TOKENS = (
    "evidence",
    "proof",
    "receipt",
    "attest",
    "audit",
    "review",
    "validation",
    "gate",
)
MARKER_RE = re.compile(r"^\s*#\s*evidence-workflow\s*:\s*true\s*$", re.IGNORECASE)
CHECKOUT_RE = re.compile(
    r"^(?P<indent>\s*)(?P<dash>-\s+)?uses\s*:\s*[\"']?actions/checkout@v4[\"']?\s*(?:#.*)?$"
)
LIST_ITEM_RE = re.compile(r"^(?P<indent>\s*)-\s+")
WITH_RE = re.compile(r"^(?P<indent>\s*)with\s*:\s*(?:#.*)?$")
# Match a direct mapping key under with: at a specific indent (spaces only for indent).
KEY_RE = re.compile(r"^(?P<indent>\s*)(?P<key>[A-Za-z0-9_-]+)\s*:\s*(?P<value>.*)$")


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    message: str


def is_evidence_workflow(path: Path, text: str) -> bool:
    if any(MARKER_RE.match(line) for line in text.splitlines()):
        return True
    pieces = tuple(
        piece
        for piece in re.split(r"[^a-z0-9]+", path.stem.lower().replace("_", "-"))
        if piece
    )
    return any(token in pieces for token in EVIDENCE_NAME_TOKENS)


def _step_indent(lines: Sequence[str], checkout_index: int) -> int:
    match = CHECKOUT_RE.match(lines[checkout_index])
    assert match is not None
    uses_indent = len(match.group("indent"))
    if match.group("dash"):
        return uses_indent
    for idx in range(checkout_index - 1, -1, -1):
        raw = lines[idx]
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        item = LIST_ITEM_RE.match(raw)
        if item:
            item_indent = len(item.group("indent"))
            if item_indent < uses_indent:
                return item_indent
        leading = len(raw) - len(raw.lstrip(" "))
        if leading < uses_indent:
            break
    return uses_indent


def _step_end(lines: Sequence[str], checkout_index: int, step_indent: int) -> int:
    for idx in range(checkout_index + 1, len(lines)):
        raw = lines[idx]
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        leading = len(raw) - len(raw.lstrip(" "))
        if leading < step_indent:
            return idx
        item = LIST_ITEM_RE.match(raw)
        if item and len(item.group("indent")) == step_indent:
            return idx
    return len(lines)


def _scalar_is_nonempty(value: str) -> bool:
    """Return True only if the YAML scalar text is a non-empty value.

    Treats quoted-empty, null/Null/~ , empty flow, and empty block indicators as empty.
    Does not expand expressions; any non-empty expression text counts as present.
    """
    v = value.strip()
    if not v or v.startswith("#"):
        return False
    # Strip trailing comment if present (simple, not full YAML).
    if " #" in v:
        v = v.split(" #", 1)[0].rstrip()
    # Quoted empty
    if v in ('""', "''"):
        return False
    # Explicit null
    if v.lower() in ("null", "~"):
        return False
    # Empty block/folded scalar indicators with no content on same line
    if v in ("|", ">", "|-", ">-", "|+", ">+"):
        return False
    # Non-empty block indicator with content after? rare; still treat indicator-only empty
    if re.match(r"^[|>][-+]?\s*$", v):
        return False
    return True


def checkout_has_ref(lines: Sequence[str], checkout_index: int) -> bool:
    step_indent = _step_indent(lines, checkout_index)
    end = _step_end(lines, checkout_index, step_indent)
    with_indent = None
    # Expected key indent under with: is with_indent + 2 (common YAML style).
    # Accept any key whose indent is strictly greater than with_indent and
    # that is a direct sibling (not deeper nested under another key's block).
    # We track the current direct-child indent once we see the first key.
    key_indent = None
    for idx in range(checkout_index + 1, end):
        raw = lines[idx]
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        leading = len(raw) - len(raw.lstrip(" "))
        if with_indent is not None and leading <= with_indent:
            with_indent = None
            key_indent = None
        with_match = WITH_RE.match(raw)
        if with_match and len(with_match.group("indent")) > step_indent:
            with_indent = len(with_match.group("indent"))
            key_indent = None
            continue
        if with_indent is None:
            continue
        key_match = KEY_RE.match(raw)
        if not key_match:
            # Continuation of a block scalar or list under a previous key.
            # Do not treat nested "ref:" text inside another scalar as a with.ref.
            continue
        this_indent = len(key_match.group("indent"))
        if this_indent <= with_indent:
            with_indent = None
            key_indent = None
            continue
        if key_indent is None:
            key_indent = this_indent
        # Only accept keys at the exact direct-child indent under with:
        if this_indent != key_indent:
            # Nested mapping or deeper; ignore.
            continue
        if key_match.group("key") != "ref":
            continue
        if _scalar_is_nonempty(key_match.group("value")):
            return True
    return False


def lint_text(path: Path, text: str) -> list[Violation]:
    if not is_evidence_workflow(path, text):
        return []
    lines = text.splitlines()
    out: list[Violation] = []
    for idx, line in enumerate(lines):
        if CHECKOUT_RE.match(line) and not checkout_has_ref(lines, idx):
            out.append(
                Violation(
                    path=str(path),
                    line=idx + 1,
                    message=(
                        "bare actions/checkout@v4 in evidence workflow; add with.ref "
                        "bound to an immutable/exact head or delegate exact-head proof "
                        "to .github/workflows/exact-head-checkout.yml"
                    ),
                )
            )
    return out


def discover(paths: Iterable[str]) -> list[Path]:
    supplied = [Path(p) for p in paths]
    if supplied:
        return [p for p in supplied if p.is_file()]
    root = Path(".github/workflows")
    if not root.exists():
        return []
    return sorted({*root.glob("*.yml"), *root.glob("*.yaml")})


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "paths",
        nargs="*",
        help="workflow files; defaults to .github/workflows/*.{yml,yaml}",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    violations: list[Violation] = []
    for path in discover(args.paths):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            violations.append(Violation(str(path), 0, f"unreadable workflow: {exc}"))
            continue
        violations.extend(lint_text(path, text))

    if args.as_json:
        print(json.dumps([asdict(item) for item in violations], sort_keys=True))
    else:
        for item in violations:
            print(f"{item.path}:{item.line}: {item.message}", file=sys.stderr)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
