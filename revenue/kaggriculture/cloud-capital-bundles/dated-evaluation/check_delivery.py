# SPDX-License-Identifier: Apache-2.0
"""Run OSPREY's original callback tests on the published source location.

The evidence directory is the extracted, unchanged development ZIP. This runner
executes the twelve original binding tests, not the saved game panel.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root', type=Path, required=True)
    args = parser.parse_args()
    evidence = args.evidence_root.resolve()
    receipt = json.loads((HERE / 'RECOVERY.json').read_text())
    files = (
        ('dated_callback', HERE.parent / 'dated_callback.py', 'callback_sha256'),
        ('probe_support', evidence / 'probe_support.py', 'original_support_sha256'),
        ('osprey_recovered_tests', HERE / 'test_callback.py', 'original_test_sha256'),
    )
    absent = object()
    previous = {}
    try:
        for name, path, digest_key in files:
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != receipt[digest_key]:
                raise ValueError(f'Published recovery source differs: {path}')
            spec = importlib.util.spec_from_file_location(name, path)
            if spec is None:
                raise ImportError(f'Cannot create module specification for {path}')
            module = importlib.util.module_from_spec(spec)
            previous[name] = sys.modules.get(name, absent)
            sys.modules[name] = module
            # Execute the captured bytes, not an unrelated cached bytecode file.
            exec(compile(data, str(path), 'exec'), module.__dict__)
        suite = unittest.defaultTestLoader.loadTestsFromModule(module)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        print(json.dumps({'scope': 'relocated original binding tests; no games',
                          'tests': result.testsRun, 'failures': len(result.failures),
                          'errors': len(result.errors),
                          'successful': result.wasSuccessful(),
                          'callback_sha256': receipt['callback_sha256']}))
        return 0 if result.wasSuccessful() else 1
    finally:
        for name, old in previous.items():
            if old is absent:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


if __name__ == '__main__':
    raise SystemExit(main())
