# SPDX-License-Identifier: Apache-2.0
"""Source-bound current-native MarketPath lifetime component.

Consumes QUICKSTEP's existing helper verbatim. Writes only an explicit output;
never edits an input, production tree, archive, configuration or GC settings.
This changes ownership of private cache callables, NOT generic bound methods.
Apply after whole-file-pinned optimizer transforms. Existing cleanup is retained.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

HELPER_GIT = '1438a95e69e76c97542b9b95bff1ca3745fa284e'
HELPER_REPO_PATH = 'revenue/kaggriculture/cloud-quickstep/scoped_method_cache.py'
BASE = '''    def __init__(self, item, inventory, params, shops, config, now, end):
        self.item,self.inventory,self.params=item,inventory,params
        self.shops,self.config,self.now,self.end=shops,config,now,end
        self.quote=lru_cache(maxsize=2048)(lambda inv:m.market_price(item,inv,params))
        self.single=lru_cache(maxsize=8192)(self._single)
        self.joint=lru_cache(maxsize=8192)(self._joint)
'''
CANDIDATE = BASE.replace('lru_cache(maxsize=8192)(self._single)',
                         'scoped_method_cache(self._single,maxsize=8192)').replace(
                         'lru_cache(maxsize=8192)(self._joint)',
                         'scoped_method_cache(self._joint,maxsize=8192)')
IMPORT = 'from scoped_method_cache import scoped_method_cache\n'
IMPORT_BASE = 'from functools import lru_cache\n'


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def authenticate_helper(data: bytes) -> None:
    if git_blob(data) != HELPER_GIT:
        raise ValueError('QUICKSTEP helper identity mismatch')


def constructor_span(source: str) -> tuple[int, int, str]:
    tree = ast.parse(source)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MarketPath']
    if len(classes) != 1:
        raise ValueError('exactly one top-level MarketPath required')
    cls = classes[0]
    initializers = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '__init__']
    if len(initializers) != 1 or initializers[0].decorator_list:
        raise ValueError('one undecorated native constructor required')
    for name in ('_single', '_joint'):
        methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name]
        if len(methods) != 1 or methods[0].decorator_list:
            raise ValueError('ordinary native Python cache method required: ' + name)
    node = initializers[0]
    lines = source.splitlines(keepends=True)
    start = sum(map(len, lines[:node.lineno - 1]))
    end = sum(map(len, lines[:node.end_lineno]))
    return start, end, source[start:end]


def compose(data: bytes, helper: bytes) -> tuple[bytes, dict]:
    authenticate_helper(helper)
    source = data.decode('utf-8')
    start, end, actual = constructor_span(source)
    if actual == CANDIDATE:
        if source.count(IMPORT) != 1:
            raise ValueError('patched constructor has missing/duplicate helper import')
        output = data
        state = 'already_applied'
    elif actual == BASE:
        if 'scoped_method_cache' in source:
            raise ValueError('mixed helper ownership/source; explicit rebase required')
        if source.count(IMPORT_BASE) != 1:
            raise ValueError('native import anchor is not unique')
        result = source[:start] + CANDIDATE + source[end:]
        result = result.replace(IMPORT_BASE, IMPORT_BASE + IMPORT, 1)
        output = result.encode('utf-8')
        state = 'applied'
        # Exact reversibility certifies preservation of unrelated peer bytes.
        reverted = result.replace(IMPORT, '', 1).replace(CANDIDATE, BASE, 1)
        if reverted != source:
            raise ValueError('unexpected non-constructor source change')
    else:
        raise ValueError('owned constructor span drift; explicit composition required')
    compile(output, '<scoped-constructor>', 'exec')
    return output, dict(state=state, input_git=git_blob(data), output_git=git_blob(output),
                        output_sha256=hashlib.sha256(output).hexdigest(), helper_git=HELPER_GIT,
                        constructor_git=git_blob(actual.encode('utf-8')))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--helper', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.source.resolve() == args.out.resolve() or args.helper.resolve() == args.out.resolve():
            raise ValueError('refusing to overwrite an input')
        if args.out.exists():
            raise ValueError('output already exists; use a fresh explicit scratch path')
        result, receipt = compose(args.source.read_bytes(), args.helper.read_bytes())
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open('xb') as stream:
            stream.write(result)
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except (OSError, ValueError, SyntaxError) as error:
        parser.exit(2, 'REFUSED: ' + str(error) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
