# SPDX-License-Identifier: Apache-2.0
"""Source-pinned native transfer/placement performance component for canonical V4.

Only three function spans change. Unrelated pricing/projection edits survive.
No policy, default, configuration, global cache or runtime import is added.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
from pathlib import Path

BASE_BLOB = "044a4f9c0a4a44dde10ada57563238bcaf82075d"
ORIGINALS = {'_is_shed_adjacent': '7c7fd5bcf44d45a4a4b4542a38732de4c6355b4d1bf40ebb3f622307450a6080',
 '_spawn_hand': '9363b458c1bb35c89b3ae17675313237695fb2195e06cec9ad5d4ede7d8ffa96',
 '_drop_inventories_to_shed': 'b8d7918fdd18f84bab1dd3c4f6679b56984c4c6b09ff294707c8f7a7a72f3291'}
GEOMETRY_SHA256 = '4ca4f7993bc17274631f0a0758a59eb261eff6bcc48a5c94ec51f278bbdc97a5'
REPLACEMENTS = {'_is_shed_adjacent': 'def _is_shed_adjacent(pos, board_size):\n'
                      '    """PORTAGE: integer-grid fast path; retain generic tuple/set behavior."""\n'
                      '    point = tuple(pos)\n'
                      '    if (type(board_size) is int and len(point) == 2\n'
                      '            and type(point[0]) is int and type(point[1]) is int):\n'
                      '        half = board_size // 2\n'
                      '        return half - 1 <= point[0] <= half and half - 1 <= point[1] <= half\n'
                      '    return point in {(x, y) for (x, y) in _shed_access_tiles(board_size)}',
 '_spawn_hand': 'def _spawn_hand(farm, board_size):\n'
                '    """First free shed-access tile (NWSE order); ties broken by min occupancy."""\n'
                '    occupants = {tile: 0 for tile in _shed_access_tiles(board_size)}\n'
                '    all_pos = [tuple(farm["farmer"])] + [tuple(p) for p in farm["hands"]]\n'
                '    for pos in all_pos:\n'
                '        if pos in occupants:\n'
                '            occupants[pos] += 1\n'
                '    # PORTAGE: dict insertion order is the original NWSE tie-break.\n'
                '    if type(board_size) is int:\n'
                '        return list(min(occupants, key=occupants.get))\n'
                '    best = sorted(occupants.items(), key=lambda kv: (kv[1], '
                '_shed_access_tiles(board_size).index(kv[0])))\n'
                '    return list(best[0][0])',
 '_drop_inventories_to_shed': 'def _drop_inventories_to_shed(private, capacity):\n'
                              '    """Drop every per-farmer inventory into the shed up to `capacity`; '
                              'overflow is discarded.\n'
                              '    Seeds are tracked separately in private["seeds"] and don\'t pass '
                              'through the shed."""\n'
                              '    shed = private["shed"]\n'
                              '    for inv in private["inventories"]:\n'
                              '        for item, n in list(inv.items()):\n'
                              '            if n <= 0:\n'
                              '                del inv[item]\n'
                              '                continue\n'
                              '            # PORTAGE: same values/order and recomputation, no stale '
                              'total.\n'
                              '            current = (sum(shed.values()) if type(shed) is dict\n'
                              '                       else sum(v for k, v in shed.items()))\n'
                              '            room = max(0, capacity - current)\n'
                              '            take = min(n, room)\n'
                              '            if take > 0:\n'
                              '                shed[item] = shed.get(item, 0) + take\n'
                              '            del inv[item]'}

def spans(source: bytes) -> dict[str, tuple[int, int]]:
    """Locate uniquely defined, undecorated top-level functions by UTF-8 offsets."""
    if type(source) is not bytes:
        raise TypeError("source must be bytes")
    tree = ast.parse(source.decode("utf-8"))
    wanted = set(ORIGINALS) | {"_shed_access_tiles"}
    offsets = [0]
    for line in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    result = {}
    for name in wanted:
        found = [n for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                 and n.name == name]
        if (len(found) != 1 or found[0] not in tree.body
                or type(found[0]) is not ast.FunctionDef or found[0].decorator_list):
            raise ValueError("ambiguous or decorated definition: " + name)
        for n in ast.walk(tree):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and n.id == name:
                raise ValueError("rebound definition: " + name)
            if isinstance(n, ast.alias) and (n.asname or n.name.split('.')[0]) == name:
                raise ValueError("import-shadowed definition: " + name)
        n = found[0]
        result[name] = (offsets[n.lineno - 1] + n.col_offset,
                        offsets[n.end_lineno - 1] + n.end_col_offset)
    return result


def compose(source: bytes) -> bytes:
    """Accept pinned originals or exact postimages; reject drift before any write."""
    locations = spans(source)
    a, b = locations["_shed_access_tiles"]
    if hashlib.sha256(source[a:b]).hexdigest() != GEOMETRY_SHA256:
        raise ValueError("shed geometry dependency drift")
    changes = []
    for name, old_hash in ORIGINALS.items():
        a, b = locations[name]
        replacement = REPLACEMENTS[name].encode("utf-8")
        if source[a:b] == replacement:
            continue
        if hashlib.sha256(source[a:b]).hexdigest() != old_hash:
            raise ValueError("owned function drift: " + name)
        changes.append((a, b, replacement))
    for a, b, replacement in sorted(changes, reverse=True):
        source = source[:a] + replacement + source[b:]
    compile(source, "portage-composed-mechanics.py", "exec")
    return source


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.is_symlink() or args.output.resolve() == args.source.resolve():
        parser.error("output must be a new, separate non-symlink file")
    try:
        result = compose(args.source.read_bytes())
        with args.output.open("xb") as handle:
            handle.write(result)
    except (OSError, ValueError, SyntaxError, UnicodeError) as exc:
        parser.exit(2, str(exc) + "\n")
    print(hashlib.sha256(result).hexdigest())


if __name__ == "__main__":
    main()
