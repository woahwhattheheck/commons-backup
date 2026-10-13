#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compose independently supplied ROADEF kernel revisions without a checkout.

Every donor is a full source derived from the supplied baseline. Git's three-way
file merge preserves disjoint changes and reports conflicting ones. This command
never updates a repository, source donor, solver setting or submission artifact.
"""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Mapping


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compose(baseline: bytes, donors: Mapping[str, bytes], *,
            verify_orders: bool = True) -> tuple[bytes, dict]:
    if not shutil.which('git'):
        raise RuntimeError('git merge-file is required')
    baseline.decode('utf-8')
    for name, value in donors.items():
        if not name or '\n' in name:
            raise ValueError('A donor must have a nonempty single-line label')
        value.decode('utf-8')
    names = tuple(sorted(donors))
    if verify_orders and len(names) > 4:
        raise ValueError('Exhaustive merge-order verification is limited to four donors')
    orders = tuple(itertools.permutations(names)) if verify_orders else (names,)
    expected = None
    records = []
    with tempfile.TemporaryDirectory(prefix='roadef-kernel-join-') as temporary:
        root = Path(temporary)
        base, current, incoming = [root/name for name in ('base.cpp', 'current.cpp', 'incoming.cpp')]
        base.write_bytes(baseline)
        for order in orders:
            current.write_bytes(baseline)
            for name in order:
                incoming.write_bytes(donors[name])
                result = subprocess.run(['git', 'merge-file', '-p', str(current), str(base), str(incoming)],
                                        capture_output=True, timeout=15)
                if result.returncode:
                    raise ValueError(f'Kernel merge conflict/error at donor {name!r}: '
                                     f'exit={result.returncode}; {result.stderr.decode(errors="replace")}')
                current.write_bytes(result.stdout)
            output = current.read_bytes()
            if expected is None:
                expected = output
            elif expected != output:
                raise ValueError('Donor order changes merged source; explicit composition is required')
            records.append({'order': list(order), 'sha256': digest(output)})
    assert expected is not None
    return expected, {'baseline_sha256': digest(baseline),
                      'donors': {name: digest(value) for name, value in sorted(donors.items())},
                      'merged_sha256': digest(expected), 'merged_bytes': len(expected),
                      'merge_orders': records}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--donor', action='append', default=[], metavar='NAME=PATH')
    parser.add_argument('--out', type=Path, required=True,
                        help='New output directory containing main.cpp and COMPOSITION.json')
    args = parser.parse_args()
    donors = {}
    for spec in args.donor:
        name, separator, path = spec.partition('=')
        if not separator or name in donors:
            parser.error('Each donor needs a unique NAME=PATH')
        donors[name] = Path(path).read_bytes()
    # Finish validation and merging before creating any persistent output.
    source, report = compose(args.baseline.read_bytes(), donors)
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out/'main.cpp').write_bytes(source)
    (args.out/'COMPOSITION.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
