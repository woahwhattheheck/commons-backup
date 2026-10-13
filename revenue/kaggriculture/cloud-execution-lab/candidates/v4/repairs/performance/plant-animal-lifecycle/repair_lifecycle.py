# SPDX-License-Identifier: Apache-2.0
"""Method-pinned row-local traversal for the existing native mechanics module.

Pure source transformation only: no import, download, production install, global
state, changed physiology, or alternate agent. Surrounding peer edits survive.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
from pathlib import Path

BASE_BLOB = "044a4f9c0a4a44dde10ada57563238bcaf82075d"
FUNCTION_SHA256 = {
    "_decay_plants": "aac4a2dffe4fcfe2e608ad2a7f50241ee497d0a8919d26f0ecb062ba9bfdf40c",
    "_daily_refresh_plants": "d4f651c87a027ed0da36ab6484a55173c9e50ec1b1766cf8b10b09860defb853",
    "_daily_refresh_animals": "ba957381e16ca43f8e39c9cddfa982a2a91936e1af22864eb821cdc9ee15a3e0",
}


def function_spans(source: str) -> dict[str, tuple[int, int, str]]:
    """Return exact top-level source spans; duplicate target names fail closed."""
    lines = source.splitlines(keepends=True)
    found = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in FUNCTION_SHA256:
            if node.name in found or node.decorator_list:
                raise ValueError(f"duplicate or decorated target: {node.name}")
            end = node.end_lineno
            if end is None:
                raise ValueError("Python AST lacks source end positions")
            found[node.name] = (node.lineno - 1, end, "".join(lines[node.lineno - 1:end]))
    if set(found) != set(FUNCTION_SHA256):
        raise ValueError(f"missing lifecycle targets: {set(FUNCTION_SHA256) - set(found)}")
    return found


def _row_local(text: str) -> str:
    # Retain the original square-prefix visit order, including wide/ragged rows.
    # Caching a row never copies it: in-place mutations and alias semantics stay.
    before = '    board_size = len(farm["tiles"])\n'
    if text.count(before) != 1:
        raise ValueError("unexpected board-size binding")
    text = text.replace(before, '    tiles = farm["tiles"]\n    board_size = len(tiles)\n    columns = range(board_size)\n', 1)
    before = '    for y in range(board_size):\n        for x in range(board_size):\n'
    if text.count(before) != 1:
        raise ValueError("unexpected board traversal")
    text = text.replace(before, '    for y in range(board_size):\n        row = tiles[y]\n        for x in columns:\n', 1)
    return text.replace('farm["tiles"][y][x]', 'row[x]')


def repair_source(source: str) -> str:
    """Transform all three authenticated methods atomically in a source string.

    Inputs are the plain list/dict data emitted by the official JSON game. This
    is not an equivalence claim for custom mappings with side-effecting getters.
    Unknown/already-transformed methods fail closed; other methods are untouched.
    """
    if not isinstance(source, str):
        raise TypeError("source must be UTF-8 decoded text")
    spans = function_spans(source)
    edits = []
    for name, (start, end, text) in spans.items():
        actual = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if actual != FUNCTION_SHA256[name]:
            raise ValueError(f"source drift in {name}: expected {FUNCTION_SHA256[name]}, got {actual}")
        edits.append((start, end, _row_local(text)))
    lines = source.splitlines(keepends=True)
    for start, end, replacement in sorted(edits, reverse=True):
        lines[start:end] = [replacement]
    result = "".join(lines)
    ast.parse(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="native mechanics.py")
    parser.add_argument("output", type=Path, help="new staging file; must not exist")
    args = parser.parse_args()
    result = repair_source(args.source.read_bytes().decode("utf-8"))
    # Never overwrite the input or a peer's already-written output.
    with args.output.open("x", encoding="utf-8", newline="") as output:
        output.write(result)
    print(hashlib.sha256(result.encode("utf-8")).hexdigest())


if __name__ == "__main__":
    main()
