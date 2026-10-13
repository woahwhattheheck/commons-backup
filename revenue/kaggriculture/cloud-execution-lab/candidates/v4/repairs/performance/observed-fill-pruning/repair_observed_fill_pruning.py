# SPDX-License-Identifier: Apache-2.0
"""Source-local TITAN V4 fill-inference optimization; no gameplay activation.

Only the authenticated top-level reconcile_shed_fills function is replaced.
Other definitions, including parsing and observation/action binding, stay exact.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
from pathlib import Path

PREDECESSOR_BLOB = 'cabe10ad3d683351077c9597ad7bb36cb58ce9c6'
PREIMAGE_FUNCTION_SHA256 = '1bd6e288346a869f73738c6caa3f30f63eb29fe1f59a2799b19189ec8a9f5b0a'
POSTIMAGE_FUNCTION_SHA256 = '38944719f9ad104068f5b377f7dc02599c9c61875a4016c5c7a4ed9ee217453a'
FUNCTION = 'reconcile_shed_fills'
DEPENDENCY_SHA256 = {'PRODUCTS': '066ced252326ee2242a477c9a4b23542df9a503c4233c9d4a34d691fe68e9ce2', 'ANIMALS': '1f8599444ef015389d8600d465dc5116b3e7e5b8db32292d35d397075d56210e', 'MAX_SLOT_UNITS': '5178fcde62876d238838c0778bbb88cdab3756bb41c3562e519c90e3225f190b', '_unknown': 'eb244a1f0c37adca8f5b2422f07ff5405944b48ffa3d8815c914691cee64a750', '_count': 'a43c809bba08943a6fa5cdbb03253df218434863895e8491fa47d40121a8a65f', '_stock': '9d253f6f017bde8a92d6e880ee8f4087f57bd0a92319be5d5801348bedfc3643', '_config': 'a5d3f9e51a6654bba6d8042a55c69d29abd883676922f0b9f14c8a5610f977d4', '_parse': '70993a1c21dd1685e1665412af5eb01b9152763b7858b0eaf4fe46596ead3f67', '_merge': 'd6a0047f101be7cb3bb727cf0e6472f8c88c17ad03848d7346013b6dedcc2842'}
PAYLOAD = Path(__file__).with_name('reconcile_shed_fills.py.inc')


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def _span(data: bytes) -> tuple[int, int, bytes]:
    tree = ast.parse(data)
    candidates = [node for node in tree.body
                  if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and node.name == FUNCTION]
    if len(candidates) != 1 or type(candidates[0]) is not ast.FunctionDef:
        raise ValueError('expected one synchronous top-level reconciliation function')
    node = candidates[0]
    if node.decorator_list:
        raise ValueError('unexpected reconciliation decorator')
    lines = data.splitlines(keepends=True)
    start = sum(map(len, lines[:node.lineno - 1]))
    end = sum(map(len, lines[:node.end_lineno]))
    return start, end, data[start:end]


def _check_dependencies(data: bytes) -> None:
    lines = data.splitlines(keepends=True)
    found = {}
    for node in ast.parse(data).body:
        name = (node.name if isinstance(node, ast.FunctionDef) else
                node.targets[0].id if isinstance(node, ast.Assign)
                and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) else None)
        if name in DEPENDENCY_SHA256:
            if name in found:
                raise ValueError('duplicate reconciliation dependency')
            fragment = b''.join(lines[node.lineno-1:node.end_lineno])
            found[name] = hashlib.sha256(fragment).hexdigest()
    if found != DEPENDENCY_SHA256:
        raise ValueError('reconciliation dependency changed; review before porting')


def repair(source: bytes) -> bytes:
    """Preserve unrelated bytes; reject changed target semantics; be idempotent."""
    if not isinstance(source, bytes):
        raise TypeError('source must be bytes')
    _check_dependencies(source)
    start, end, old = _span(source)
    digest = hashlib.sha256(old).hexdigest()
    payload = PAYLOAD.read_bytes()
    if hashlib.sha256(payload).hexdigest() != POSTIMAGE_FUNCTION_SHA256:
        raise ValueError('replacement function custody mismatch')
    if digest == POSTIMAGE_FUNCTION_SHA256:
        return source
    if digest != PREIMAGE_FUNCTION_SHA256:
        raise ValueError('reconciliation function has changed; review current source before porting')
    result = source[:start] + payload + source[end:]
    ast.parse(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('write to a separate output for review, not directly over production')
    try:
        original = args.source.read_bytes()
        result = repair(original)
        with args.output.open('xb') as destination:
            destination.write(result)
    except (OSError, TypeError, ValueError, SyntaxError) as error:
        parser.exit(2, f'{error}\n')
    print(f'predecessor_blob={git_blob(original)} output_blob={git_blob(result)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
