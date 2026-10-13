# SPDX-License-Identifier: Apache-2.0
"""Compose bounded immutable geometry caching into existing native mechanics.

Only the authenticated geometry seam changes. Other performance components can
compose independently; the source tree and submission archive are never edited
by importing this module. Run the CLI on an explicit staged copy.
"""
from __future__ import annotations
import argparse
import ast
from pathlib import Path

CORNERS = '''def _shed_access_tiles(board_size):
    """Four inner-corner tiles around the shed, in NWSE order."""
    half = board_size // 2
    return [(half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half)]'''
BEFORE = '''def _is_shed_adjacent(pos, board_size):
    return tuple(pos) in {(x, y) for (x, y) in _shed_access_tiles(board_size)}'''
AFTER = '''from functools import lru_cache as _shed_geometry_cache


@_shed_geometry_cache(maxsize=16, typed=True)
def _cached_shed_access(board_size):
    """Bounded immutable geometry only; no observation or episode state."""
    return frozenset(_shed_access_tiles(board_size))


def _is_shed_adjacent(pos, board_size):
    return tuple(pos) in _cached_shed_access(board_size)'''


def compose(source: str) -> str:
    """Authenticate two exact function bodies and replace only membership work.

    Deliberately reject repeated application and changed geometry definitions.
    Unrelated source edits are retained byte-for-byte, allowing composition with
    scalar quote work without resetting a newer mechanics file to an old blob.
    """
    tree = ast.parse(source)
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    nodes = {n.name: n for n in functions}
    for name, expected in (("_shed_access_tiles", CORNERS),
                           ("_is_shed_adjacent", BEFORE)):
        node = nodes.get(name)
        if (sum(n.name == name for n in functions) != 1 or node is None
                or node.decorator_list or ast.get_source_segment(source, node) != expected):
            raise ValueError("Geometry source moved: " + name)
    if "_cached_shed_access" in source or "_shed_geometry_cache" in source:
        raise ValueError("Geometry cache already present or name collision")
    if source.count(BEFORE) != 1:
        raise ValueError("Ambiguous geometry source")
    result = source.replace(BEFORE, AFTER, 1)
    compile(result, "composed-mechanics", "exec")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("Use a distinct staged output, not an in-place source write")
    result = compose(args.source.read_bytes().decode("utf-8"))
    args.output.write_bytes(result.encode("utf-8"))


if __name__ == "__main__":
    main()
