# SPDX-License-Identifier: Apache-2.0
"""Source-only current-ABI repair. Does not install or activate a runtime."""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys

BASELINE_BLOB = 'b952c9c228ecbde592bf3d2df01638677abb0d24'
BEFORE = '727cfe6039279752d08cf1d419df1f1fde01ee11f58b54ffa6fac9e0b321968b'
AFTER = '0340c322c3b4bd2090cfe570b1240eb536da5d66f2e737ed929f0736f28ebee1'
LATCH = '            self.ready = False\n            # Retain only the route'
LATCHED = '            initialization_completed = self.ready\n' + LATCH
FINALIZE = '            output = self._finish_production(obs, output, cfg)\n'
GUARDED = '''            # Readiness, not attribute presence or stage, certifies that all
            # controller-dependent finalizers were installed. Reconstruction
            # can leave old attributes even when the new initialization fails.
            if initialization_completed:
                output = self._finish_production(obs, output, cfg)
            else:
                self.diagnostics['finalizer_skipped'] = 'incomplete_initialization'
'''


def blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def act_span(source: str) -> tuple[list[str], int, int]:
    tree = ast.parse(source)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'TitanAgent']
    if len(classes) != 1:
        raise ValueError('expected exactly one TitanAgent class')
    methods = [n for n in classes[0].body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == 'act']
    if len(methods) != 1 or not isinstance(methods[0], ast.FunctionDef) or methods[0].decorator_list:
        raise ValueError('expected one undecorated synchronous TitanAgent.act')
    method = methods[0]
    return source.splitlines(keepends=True), method.lineno - 1, method.end_lineno


def repair(data: bytes) -> bytes:
    """Pin the entire act method; preserve every byte outside that method.

    Other consumers may have changed since BASELINE_BLOB. A changed act body
    is rejected rather than rebased by an unsafe substring-only replacement.
    """
    source = data.decode('utf-8', errors='strict')
    lines, start, stop = act_span(source)
    method = ''.join(lines[start:stop])
    digest = hashlib.sha256(method.encode()).hexdigest()
    if digest == AFTER:
        return data
    if digest != BEFORE:
        raise ValueError('unrecognized TitanAgent.act SHA256: ' + digest)
    if method.count(LATCH) != 1 or method.count(FINALIZE) != 1:
        raise ValueError('ambiguous recovery edit anchors')
    fixed = method.replace(LATCH, LATCHED, 1).replace(FINALIZE, GUARDED, 1)
    if hashlib.sha256(fixed.encode()).hexdigest() != AFTER:
        raise ValueError('unexpected repair postimage')
    result = ''.join(lines[:start]) + fixed + ''.join(lines[stop:])
    compile(result, '<deadline-recovery-candidate>', 'exec')
    return result.encode('utf-8')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path, help='new candidate file; never overwritten')
    args = parser.parse_args(argv)
    try:
        before = args.source.read_bytes()
        after = repair(before)
        with args.output.open('xb') as handle:
            handle.write(after)
    except (OSError, UnicodeError, ValueError, SyntaxError, RecursionError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({'input_blob': blob(before), 'output_blob': blob(after),
                      'changed': before != after, 'runtime_activated': False}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
