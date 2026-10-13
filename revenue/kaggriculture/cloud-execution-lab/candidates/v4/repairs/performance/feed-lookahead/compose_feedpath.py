# SPDX-License-Identifier: Apache-2.0
"""Inline native actor lookup without repeated whole-crew list allocation.

Only three source-local loops change; no mutable state is cached. The exact
reference helpers and enumerate(positions) headers are authenticated. Other
method edits are preserved. Not a runtime module or an activation mechanism.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path

HELPERS = {
    '_units': '924270bf03d7299c6ad2e8e42696957be25ddbd78d9dbe56edfda07aa6028f23',
    '_action': '90e5709b28e8a7b2db15b15ef0fb880a56a592d329ae13980643571d1be6954a',
}
TARGETS = {'_feed_window': 12, '_bonus_water_service': 12, 'protect_operating_stock': 8}
INLINE = """_fp_farmer = row.get('farmer') or ['PASS']
_fp_hands = row.get('hands') or []
if type(_fp_hands) is list:
    if actor == 0:
        action = _fp_farmer
    elif actor <= len(_fp_hands):
        action = _fp_hands[actor - 1]
    else:
        action = None
else:
    _fp_units = [_fp_farmer, *_fp_hands]
    action = _fp_units[actor] if actor < len(_fp_units) else None
action = action if action else ['PASS']
"""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fragments(source: str) -> dict[str, tuple[int, int, str]]:
    lines = source.splitlines(keepends=True)
    result = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in result:
                raise ValueError('duplicate top-level function: ' + node.name)
            result[node.name] = (node.lineno-1, node.end_lineno,
                                 ''.join(lines[node.lineno-1:node.end_lineno]))
    return result


def compose(source: str) -> str:
    if '\r' in source:
        raise ValueError('only LF source is supported')
    funcs = fragments(source)
    for name, expected in HELPERS.items():
        if name not in funcs or digest(funcs[name][2].encode()) != expected:
            raise ValueError('reference helper drift: ' + name)
    replacements = []
    modes = []
    for name, depth in TARGETS.items():
        if name not in funcs:
            raise ValueError('missing consumer: ' + name)
        start, stop, body = funcs[name]
        indent = ' ' * depth
        suffix = '; op = action[0]' if name == '_bonus_water_service' else ''
        header = indent + 'for actor, pos in enumerate(positions):\n'
        old = header + indent + '    action = _action(row, actor)' + suffix + '\n'
        new = header + ''.join(indent+'    '+line+'\n' for line in INLINE.splitlines())
        if suffix:
            new += indent + '    op = action[0]\n'
        if body.count(old) == 1 and new not in body:
            if any(token in body for token in ('_fp_farmer', '_fp_hands', '_fp_units')):
                raise ValueError('reserved local name collision: ' + name)
            modes.append('original')
            replacements.append((start, stop, body.replace(old, new, 1)))
        elif body.count(new) == 1 and old not in body:
            modes.append('composed')
        else:
            raise ValueError('consumer loop drift: ' + name)
    if len(set(modes)) != 1:
        raise ValueError('partial composition requires explicit reconciliation')
    lines = source.splitlines(keepends=True)
    for start, stop, body in sorted(replacements, reverse=True):
        lines[start:stop] = [body]
    output = ''.join(lines)
    ast.parse(output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('write to a separate scratch file; never overwrite the input')
    raw = args.source.read_bytes()
    result = compose(raw.decode('utf-8')).encode('utf-8')
    args.output.write_bytes(result)
    print(json.dumps({'input_sha256': digest(raw), 'output_sha256': digest(result),
                      'changed': result != raw, 'source_activation': False}, sort_keys=True))


if __name__ == '__main__':
    main()
