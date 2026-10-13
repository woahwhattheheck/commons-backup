#!/usr/bin/env python3
"""Recreate the existing SciPy launch pack and verify its original byte pins.

The existing public-bank builder copies the licensed source and emits the
existing adapter. This helper does not edit any policy or loader source.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def prepare(output: Path) -> dict:
    source = ROOT / 'cloud-policy-portfolio/revision2/vendor/opponents'
    builder = ROOT / 'cloud-opponent-frontier/runtime/public_bank/bank.py'
    freeze = json.loads((HERE.parent / 'source-freeze.json').read_text())
    expected = {row['path'][5:]: row['sha256'] for row in freeze['files']
                if row['path'].startswith('bank/')}
    if not output.exists():
        sys.path.insert(0, str(builder.parent))
        spec = importlib.util.spec_from_file_location('cold_start_bank_builder', builder)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.prepare(source / 'sources', source / 'contract', output, include_scipy=True)
    checks = {}
    for name, digest in expected.items():
        actual = hashlib.sha256((output / name).read_bytes()).hexdigest()
        if actual != digest:
            raise ValueError(f'Existing WIDEFIELD bank pin differs: {name}')
        checks[name] = actual
    return {'bank': str(output.resolve()), 'files': checks,
            'verified_original_files': len(checks),
            'freeze_sha256': hashlib.sha256((HERE.parent / 'source-freeze.json').read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.output), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
