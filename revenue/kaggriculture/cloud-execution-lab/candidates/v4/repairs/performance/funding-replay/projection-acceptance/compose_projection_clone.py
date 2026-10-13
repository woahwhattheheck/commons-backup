#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Apply authenticated, method-local copy edits to a separate scratch package.

Reads the baseline without altering it. Preserves all bytes outside the three
explicit method spans; an already-composed method is accepted unchanged. A
same-method conflict requires explicit rebase, not a whole-module overwrite.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
# Filled at publication by source-generation step; checked before reading edits.
EDITS_SHA256 = '5340602c62668cb9f52c03ecb05982982632dbb00689335719a4ea94635572f7'
HELPER_SHA256 = 'b1212e80ea36d6f5b898497e38c9d8a89ab48d31c26f27a8ea39093bb52a67d4'


class CompositionError(ValueError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def authenticated_inputs() -> tuple[list[dict], bytes]:
    edits = (HERE / 'edits.json').read_bytes()
    helper = (HERE / 'projection_state_clone.py').read_bytes()
    if sha256(edits) != EDITS_SHA256 or sha256(helper) != HELPER_SHA256:
        raise CompositionError('source packet hash mismatch')
    return json.loads(edits), helper


def compose_bytes(name: str, source: bytes, edits: list[dict]) -> bytes:
    relevant = [x for x in edits if x['file'] == name]
    if not relevant:
        raise CompositionError(f'unregistered source: {name}')
    text = source.decode('utf-8')
    lines = text.splitlines(keepends=True)
    nodes = [n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)]
    spans = []
    for edit in relevant:
        found = [n for n in nodes if n.name == edit['function']]
        if len(found) != 1:
            raise CompositionError(f'function cardinality: {name}:{edit["function"]}')
        node = found[0]
        before = ''.join(lines[node.lineno-1:node.end_lineno])
        if before == edit['after'] and sha256(before.encode()) == edit['after_sha256']:
            continue
        if before != edit['before'] or sha256(before.encode()) != edit['before_sha256']:
            raise CompositionError(f'method source drift: {name}:{node.name}')
        spans.append((node.lineno-1, node.end_lineno, edit['after']))
    for start, end, replacement in sorted(spans, reverse=True):
        lines[start:end] = [replacement]
    result = ''.join(lines).encode('utf-8')
    compile(result, name, 'exec')
    return result


def compose_package(source: Path, output: Path, scope: str = 'all') -> dict:
    source = source.resolve(strict=True)
    output = output.resolve(strict=False)
    if source == output or source in output.parents or output in source.parents:
        raise CompositionError('scratch output must be separate from source')
    if output.exists():
        raise CompositionError('scratch output already exists')
    edits, helper = authenticated_inputs()
    if scope == 'funding':
        edits = [item for item in edits if item['function'] == '_funding_trace']
    elif scope != 'all':
        raise CompositionError('unknown scope')
    names = sorted({x['file'] for x in edits})
    before = {name: (source / name).read_bytes() for name in names}
    after = {name: compose_bytes(name, data, edits) for name, data in before.items()}
    existing = source / 'projection_state_clone.py'
    if existing.exists() and existing.read_bytes() != helper:
        raise CompositionError('existing helper does not match packet')
    # Runtime packages are expected to be regular, self-contained source trees.
    if any(p.is_symlink() for p in source.rglob('*')):
        raise CompositionError('source package contains symlinks')
    try:
        shutil.copytree(source, output, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for name, data in after.items():
            (output / name).write_bytes(data)
        (output / 'projection_state_clone.py').write_bytes(helper)
        for name, data in before.items():
            if (source / name).read_bytes() != data:
                raise CompositionError('source changed during composition')
        for name, data in after.items():
            if (output / name).read_bytes() != data:
                raise CompositionError('scratch readback mismatch')
    except BaseException:
        if output.exists():
            shutil.rmtree(output)
        raise
    return {'files': {name: {'before_sha256': sha256(before[name]),
                              'after_sha256': sha256(after[name])} for name in names},
            'helper_sha256': sha256(helper)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--scope', choices=['all','funding'], default='funding')
    args = parser.parse_args()
    if args.receipt:
        receipt_path = args.receipt.resolve(strict=False)
        for protected in (args.source.resolve(strict=True), args.output.resolve(strict=False)):
            if receipt_path == protected or protected in receipt_path.parents:
                raise CompositionError('receipt must be outside both runtime trees')
        if receipt_path.exists():
            raise CompositionError('receipt already exists')
    receipt = compose_package(args.source, args.output, args.scope)
    encoded = json.dumps(receipt, indent=2) + '\n'
    if args.receipt:
        args.receipt.write_text(encoded)
    print(encoded, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
