# SPDX-License-Identifier: Apache-2.0
"""Exact-method, byte-preserving seed funding prefix repair; not a runtime hook."""
from __future__ import annotations

import argparse
import ast
import hashlib
from pathlib import Path

METHOD_SHA256 = "b3bf094820b77a7b871b017c78fdfa18ef3663c94970c96c2eb572e5c693ff01"
CHANGES = (
    (
        "        if not self.features.seed or not any(o and o[0] == 'BUY_SEED' for o in selected['market']):\n"
        "            return selected\n",
        "        if not self.features.seed:\n"
        "            return selected\n"
        "        maximum = max(1, int(cfg.get('maxMarketOrdersPerTurn', 10)))\n"
        "        # Raw slots beyond the engine cap cannot own funding or seed demand.\n"
        "        if not any(o and o[0] == 'BUY_SEED' for o in selected['market'][:maximum]):\n"
        "            return selected\n",
    ),
    (
        "self.controller.cur, int(cfg.get('maxMarketOrdersPerTurn', 10)),",
        "self.controller.cur, maximum,",
    ),
    (
        "enumerate(zip(selected['market'], proposed['market']))",
        "enumerate(zip(selected['market'][:maximum], proposed['market'][:maximum]))",
    ),
    (
        "for i in edits for o in selected['market'][i+1:])",
        "for i in edits for o in selected['market'][i+1:maximum])",
    ),
)


def method_bounds(source: bytes) -> tuple[int, int]:
    """Find the single direct TitanAgent method without importing source code."""
    text = source.decode("utf-8")
    tree = ast.parse(text)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "TitanAgent"]
    if len(classes) != 1:
        raise ValueError("expected one top-level TitanAgent")
    methods = [n for n in classes[0].body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_seed_selected"]
    if len(methods) != 1 or not isinstance(methods[0], ast.FunctionDef) or methods[0].decorator_list:
        raise ValueError("expected one undecorated synchronous _seed_selected")
    method = methods[0]
    lines = source.splitlines(keepends=True)
    return sum(map(len, lines[:method.lineno - 1])), sum(map(len, lines[:method.end_lineno]))


def extract_method(source: bytes) -> bytes:
    start, end = method_bounds(source)
    return source[start:end]


def repair(source: bytes) -> bytes:
    """Patch only reviewed bytes; reject drift; an exact repeat is a no-op."""
    start, end = method_bounds(source)
    before = source[start:end]
    text = before.decode("utf-8")
    if hashlib.sha256(before).hexdigest() == METHOD_SHA256:
        for old, new in CHANGES:
            if text.count(old) != 1:
                raise ValueError("missing or ambiguous repair anchor")
            text = text.replace(old, new, 1)
    else:
        # Authenticate the complete predecessor by reversing all four changes.
        original = text
        for old, new in reversed(CHANGES):
            if original.count(new) != 1:
                raise ValueError("_seed_selected drift: re-review required")
            original = original.replace(new, old, 1)
        if hashlib.sha256(original.encode("utf-8")).hexdigest() != METHOD_SHA256:
            raise ValueError("_seed_selected drift: re-review required")
        return source
    output = source[:start] + text.encode("utf-8") + source[end:]
    ast.parse(output.decode("utf-8"))
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path, help="new scratch file; never overwrites")
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("in-place production editing is not supported")
    try:
        output = repair(args.source.read_bytes())
        with args.output.open("xb") as stream:
            stream.write(output)
    except (OSError, UnicodeError, SyntaxError, ValueError) as error:
        parser.exit(2, f"repair refused: {error}\n")
    print(hashlib.sha256(output).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
