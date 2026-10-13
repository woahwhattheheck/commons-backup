#!/usr/bin/env python3
"""Replay the pinned WHEAT count-contract repair from local Git objects only.

Run from a Commons checkout, or pass --root. Uses a temporary directory, Python
stdlib and Git; never fetches, changes branches, writes source or submits work.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ORIGINAL_TESTS = ['test_titan_v5_wheat_feed_carry_oracle',
                  'test_titan_v5_wheat_feed_carry_followup']
NEW_TEST = 'test_titan_v5_wheat_feed_carry_count_contract'


def run(args: list[str], cwd: Path, expected: int = 0) -> subprocess.CompletedProcess:
    result = subprocess.run(args, cwd=cwd,
                            env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'),
                            capture_output=True, text=True, timeout=120, check=False)
    if result.returncode != expected:
        raise RuntimeError(f'unexpected exit {result.returncode}: {args!r}\n'
                           f'{result.stdout}\n{result.stderr}')
    return result


def git_blob(root: Path, sha: str) -> bytes:
    result = subprocess.run(['git', '-C', str(root), 'cat-file', 'blob', sha],
                            capture_output=True, timeout=30, check=False)
    if result.returncode:
        raise RuntimeError(f'local Git blob {sha} unavailable; no network fetch attempted: '
                           + result.stderr.decode('utf-8', errors='replace'))
    raw = result.stdout
    actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if actual != sha:
        raise RuntimeError(f'Git blob integrity mismatch: expected {sha}, got {actual}')
    return raw


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd(),
                        help='Commons checkout with the pinned history (default: cwd)')
    parser.add_argument('--parity', action='store_true',
                        help='also execute the 260,268-input boundary slice in both modes')
    args = parser.parse_args()
    root = args.root.resolve()
    if shutil.which('git') is None:
        raise RuntimeError('Git executable is required')
    bindings = json.loads((HERE / 'source-bindings.json').read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory(prefix='wheat-count-contract-') as temporary:
        work = Path(temporary)
        for version in ('original', 'patched'):
            for entry in bindings[version]:
                relative = Path(entry['path'])
                if relative.is_absolute() or '..' in relative.parts:
                    raise RuntimeError('invalid retained relative path')
                target = work / version / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(git_blob(root, entry['git_blob']))
        print('PASS: all pinned original and repaired Git blob identities', flush=True)
        before, after = work / 'original', work / 'patched'
        for flags in ([], ['-O']):
            result = run([sys.executable, *flags, '-m', 'unittest', '-v',
                          *ORIGINAL_TESTS], before)
            if 'Ran 19 tests' not in result.stderr:
                raise RuntimeError('baseline test enrollment differs from retained 19')
        print('PASS: original 19/19 tests, normal and optimized', flush=True)
        shutil.copy2(after / (NEW_TEST + '.py'), before / (NEW_TEST + '.py'))
        result = run([sys.executable, '-m', 'unittest', '-v', NEW_TEST], before, 1)
        if 'Ran 12 tests' not in result.stderr or 'FAILED (failures=28)' not in result.stderr:
            raise RuntimeError('negative control did not reproduce all 28 count failures')
        print('PASS: original source distinguished by 28 failing regression subcases', flush=True)
        for flags in ([], ['-O']):
            result = run([sys.executable, *flags, '-m', 'unittest', '-v',
                          *ORIGINAL_TESTS, NEW_TEST], after)
            if 'Ran 31 tests' not in result.stderr:
                raise RuntimeError('repaired test enrollment differs from retained 31')
        print('PASS: repaired 31/31 tests, normal and optimized', flush=True)
        if args.parity:
            shutil.copy2(HERE / 'verify_valid_parity.py', work / 'verify_valid_parity.py')
            observations = []
            for flags in ([], ['-O']):
                result = run([sys.executable, *flags, str(work / 'verify_valid_parity.py')], work)
                observations.append(json.loads(result.stdout))
            for key in ('state', 'counts', 'ordered_output_sha256'):
                if observations[0][key] != observations[1][key]:
                    raise RuntimeError('normal/optimized parity disagreement: ' + key)
            print(json.dumps({'parity': observations}, indent=2), flush=True)
    print('SCOPE: pinned diagnostic only; no hosted-CI, gameplay, promotion or publication action')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
        print('REPLAY FAILED: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
