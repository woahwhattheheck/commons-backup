#!/usr/bin/env python3
"""Produce a version-bound native-test adaptation patch, without editing a checkout.

The saved-draft byte reader changes from File.text to File.arrayBuffer. The
upstream Node test doubles and browser timing gate must follow that I/O seam.
This prepares only the test-fixture delta. It does not assert that the upstream
real-compiler suite has executed in this review environment.
"""
from __future__ import annotations
import argparse
import difflib
import hashlib
from pathlib import Path

PREFIX = Path('revenue/uiowa_rfq_18649_workbench')
PINS = {
 'test_app.js': 'bd7830a99efb728d4cf620372c86559d8fc5c2eb',
 'browser_resume_acceptance.py': '85e3221b04d6ad85c0eb033c883b40d5adb2ab84',
}

def git_blob(raw: bytes) -> str:
    return hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest()

def once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError('Expected one exact fixture seam; refusing to guess')
    return source.replace(old, new, 1)

def rewrite(name: str, source: str) -> str:
    if name == 'test_app.js':
        source = once(source,
          'return { size: Buffer.byteLength(contents), text: async () => contents };',
          'return { size: Buffer.byteLength(contents), text: async () => contents,\n'
          '    arrayBuffer: async () => Uint8Array.from(Buffer.from(contents, "utf8")).buffer };')
        source = once(source,
          'return { file: { size: Buffer.byteLength(contents), text: () => wait.promise }, finish: () => wait.resolve(contents) };',
          'return { file: { size: Buffer.byteLength(contents), text: () => wait.promise,\n'
          '    arrayBuffer: () => wait.promise.then(text => Uint8Array.from(Buffer.from(text, "utf8")).buffer) },\n'
          '    finish: () => wait.resolve(contents) };')
        return once(source, 'Blob, TextEncoder, URLSearchParams,', 'Blob, TextEncoder, TextDecoder, URLSearchParams,')
    if name == 'browser_resume_acceptance.py':
        source = once(source, "# Hold the browser's actual File.text await, then resolve it explicitly.",
           "# Hold the browser's actual File.arrayBuffer await, then resolve it explicitly.")
        source = once(source, 'const original = File.prototype.text;', 'const original = File.prototype.arrayBuffer;')
        return once(source, 'File.prototype.text = function () {', 'File.prototype.arrayBuffer = function () {')
    raise ValueError('Unrecognized fixture filename')

def prepare(repo: Path) -> str:
    parts = []
    for name, pin in PINS.items():
        path = repo / PREFIX / name
        raw = path.read_bytes()
        if git_blob(raw) != pin:
            raise ValueError(f'{path}: source differs from the reviewed c4c305db fixture; reconcile current source first')
        before = raw.decode('utf-8')
        after = rewrite(name, before)
        parts.extend(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
            fromfile=f'a/{PREFIX}/{name}', tofile=f'b/{PREFIX}/{name}'))
    return ''.join(parts)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New output file only; never overwrites')
    args = parser.parse_args()
    try:
        patch = prepare(args.repo)
        with args.output.open('x', encoding='utf-8', newline='') as handle:
            handle.write(patch)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.exit(2, f'REFUSED: {exc}\n')
