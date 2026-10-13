# SPDX-License-Identifier: Apache-2.0
"""Repair one exact current-ABI loader seam, never materialize legacy V4.

This tool produces a separate reviewed source file. It does not import the
runtime, alter defaults, write to a repository, publish, or execute a game.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

ORIGINAL_SHA256 = 'ad25182f731fb8b31fc4855b55dd96cc4ead622d08c03986073f0c4fc84b3296'
REPAIRED_SHA256 = 'f1ae4ac3f3140dbf5f0598778bcaaa403336047292855c043442e8377220ae5f'
OLD_HIT = '    if cache and key in _MODULE_CACHE:\n        return _MODULE_CACHE[key]\n'
NEW_HIT = '''    if cache and key in _MODULE_CACHE:
        # A different relocated package may have rebound this public name.
        # Restore this completed module before a sibling imports the name.
        module = _MODULE_CACHE[key]
        sys.modules[name] = module
        return module
'''


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def load_span(source: str) -> tuple[int, int, str]:
    """Return the sole undecorated top-level load function's exact source span."""
    tree = ast.parse(source)
    matches = [node for node in tree.body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
               and node.name == 'load']
    if len(matches) != 1 or not isinstance(matches[0], ast.FunctionDef):
        raise ValueError('Expected exactly one synchronous top-level load function')
    node = matches[0]
    if node.decorator_list:
        raise ValueError('Decorated loader is outside this reviewed seam')
    lines = source.splitlines(keepends=True)
    start = sum(map(len, lines[:node.lineno - 1]))
    end = sum(map(len, lines[:node.end_lineno]))
    return start, end, source[start:end]


def repair_source(data: bytes) -> tuple[bytes, dict]:
    """Change only the reviewed cache-hit branch; preserve all surrounding bytes.

    Matching the entire function, rather than the full runtime, permits disjoint
    current-main peer edits. Any loader drift is an explicit review boundary.
    An already-exact repaired function is a byte-for-byte no-op.
    """
    if not isinstance(data, bytes):
        raise TypeError('Source must be bytes')
    text = data.decode('utf-8')
    start, end, old = load_span(text)
    before = hashlib.sha256(old.encode('utf-8')).hexdigest()
    if before == REPAIRED_SHA256:
        repaired = data
        changed = False
    elif before == ORIGINAL_SHA256:
        if old.count(OLD_HIT) != 1:
            raise ValueError('Reviewed cache-hit seam is not unique')
        new = old.replace(OLD_HIT, NEW_HIT, 1)
        if hashlib.sha256(new.encode('utf-8')).hexdigest() != REPAIRED_SHA256:
            raise ValueError('Repaired loader identity mismatch')
        repaired = (text[:start] + new + text[end:]).encode('utf-8')
        compile(repaired, '<repaired-titan-runtime>', 'exec')
        changed = True
    else:
        raise ValueError(f'Loader source drift: {before}; review current bytes')
    return repaired, {
        'schema': 'titan-v4-loader-binding-repair/v1',
        'changed': changed,
        'input_git_blob': git_blob(data),
        'output_git_blob': git_blob(repaired),
        'input_sha256': hashlib.sha256(data).hexdigest(),
        'output_sha256': hashlib.sha256(repaired).hexdigest(),
        'load_before_sha256': before,
        'load_after_sha256': REPAIRED_SHA256,
        'scope': 'sequential cached-module import binding only',
        'published': False,
        'full_current_runtime_tested': False,
        'gameplay_strength_claim': False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runtime', type=Path, help='Current-main titan_runtime.py')
    parser.add_argument('--output', type=Path, required=True, help='New, separate output file')
    args = parser.parse_args()
    try:
        if args.runtime.resolve() == args.output.resolve():
            raise ValueError('Output must differ from the input; inspect before integration')
        original = args.runtime.read_bytes()
        repaired, report = repair_source(original)
        # Exclusive creation also rejects a concurrent writer, symlink or file.
        with args.output.open('xb') as target:
            target.write(repaired)
        print(json.dumps(report, sort_keys=True, indent=2))
        return 0
    except (OSError, UnicodeError, ValueError, SyntaxError, TypeError) as error:
        parser.exit(2, f'{type(error).__name__}: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
