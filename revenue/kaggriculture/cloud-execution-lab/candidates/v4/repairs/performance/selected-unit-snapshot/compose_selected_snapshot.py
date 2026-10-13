# SPDX-License-Identifier: Apache-2.0
"""Compose just the native selected-snapshot copy seam, never a legacy builder."""
from __future__ import annotations
import argparse
import ast
import hashlib
from pathlib import Path

RUNTIME_BLOB = 'b952c9c228ecbde592bf3d2df01638677abb0d24'
OLD = """        post = deepcopy(obs)
        post['farms'][int(obs['player'])], post['private'] = pair
        return post
"""
NEW = """        return selected_unit_snapshot(obs, obs['player'], pair)
"""
IMPORT = 'from selected_unit_snapshot import selected_unit_snapshot\n'


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def compose(data: bytes) -> bytes:
    """Require the exact current preimage, then check the method-local seam.

    A moved runtime is an integration task, not permission to reset other work.
    This intentionally fails closed rather than guessing a composed preimage.
    """
    if git_blob(data) != RUNTIME_BLOB:
        raise ValueError('runtime preimage differs; reconcile peer changes explicitly')
    source = data.decode('utf-8')
    tree = ast.parse(source)
    klass = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'TitanAgent')
    method = next(n for n in klass.body if isinstance(n, ast.FunctionDef)
                  and n.name == '_selected_snapshot')
    lines = source.splitlines(keepends=True)
    body = ''.join(lines[method.lineno - 1:method.end_lineno])
    if body.count(OLD.rstrip('\n')) != 1 or source.count(OLD) != 1:
        raise ValueError('selected-snapshot seam is not unique')
    out = source.replace(OLD, NEW, 1).replace('from copy import deepcopy\n',
                                            'from copy import deepcopy\n' + IMPORT, 1)
    ast.parse(out)
    return out.encode('utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runtime', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.runtime.resolve() == args.output.resolve():
        parser.error('output must not overwrite the input runtime')
    if args.output.exists():
        parser.error('output already exists; use a fresh composition path')
    try:
        data = compose(args.runtime.read_bytes())
        with args.output.open('xb') as target:
            target.write(data)
    except (OSError, UnicodeError, ValueError, SyntaxError, StopIteration) as exc:
        parser.exit(2, f'composition failed: {exc}\n')
    print(git_blob(data))


if __name__ == '__main__':
    main()
