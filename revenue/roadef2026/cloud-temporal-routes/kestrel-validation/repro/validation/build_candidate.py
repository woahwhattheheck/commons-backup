#!/usr/bin/env python3
"""Produce an isolated optional solver variant; never edits the given source."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

PINS = {
    '41f5dc54290f6d548f6cf61d8d7047e096c1065eba04f421b1778a32a68d9ab9': 'SEDGE archived S139',
    '322ec2e6bec9ab17c4cdf74c52d8e40414ce90cf60f9e53aaee2531cce652ab1': 'fleet 2885d176',
}

def adapt(data: bytes) -> bytes:
    digest = hashlib.sha256(data).hexdigest()
    if digest not in PINS:
        raise ValueError('Unrecognized source revision: review and deliberately bind a new pin')
    text = data.decode('utf-8')
    marker = '\npublic:\n    Solver('
    finish = '        writeSolution();\n        statistics();\n'
    if text.count(marker) != 1 or text.count(finish) != 1:
        raise ValueError('Expected existing Solver boundaries were not unique')
    text = '#include "temporal_dp.hpp"\n' + text
    text = text.replace(marker, '\n#include "temporal_pass.inc"\n' + marker)
    text = text.replace(finish, '        temporalSweep();\n' + finish)
    return text.encode('utf-8')

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--vendor', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    args = parser.parse_args()
    base, out = args.base.resolve(), args.output.resolve()
    if out == base.parent or out in base.parents:
        raise ValueError('Use a separate build directory, not the source directory')
    out.mkdir(parents=True, exist_ok=True)
    data = base.read_bytes()
    candidate = adapt(data)
    for name in ('temporal_dp.hpp', 'temporal_pass.inc'):
        shutil.copyfile(Path(__file__).resolve().parent / name, out / name)
    (out / 'main.cpp').write_bytes(candidate)
    command = [args.cxx, '-std=c++20', '-O2', '-DNDEBUG', '-I', str(args.vendor.resolve()),
               str(out / 'main.cpp'), '-o', str(out / 'candidate')]
    result = subprocess.run(command, capture_output=True, text=True, timeout=90)
    (out / 'build.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    result.check_returncode()
    receipt = {'base_sha256': hashlib.sha256(data).hexdigest(),
               'base_name': PINS[hashlib.sha256(data).hexdigest()],
               'candidate_sha256': hashlib.sha256(candidate).hexdigest(),
               'binary_sha256': hashlib.sha256((out / 'candidate').read_bytes()).hexdigest(),
               'compiler': subprocess.check_output([args.cxx, '--version'], text=True).splitlines()[0],
               'command': command, 'optional_default': 'disabled'}
    (out / 'BUILD.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt, indent=2))

if __name__ == '__main__':
    main()
