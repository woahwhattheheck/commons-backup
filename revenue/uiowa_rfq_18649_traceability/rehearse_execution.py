#!/usr/bin/env python3
"""Exercise the existing auditor against a finite set of synthetic local lanes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

PREFIX = 'uiowa_rfq_18649_demo_'
EXPECTED = {
    'clean': 'CLEAN',
    'empty': 'NO_TESTS_EXECUTED',
    'failed': 'TESTS_NOT_GREEN',
    'foreign': 'WRITES_OUTSIDE_LANE',
    'mutating': 'NON_HERMETIC',
    'no_modules': 'NO_TESTS',
    'partial': 'PARTIAL_TEST_COVERAGE',
    'self_sealing': 'SELF_SEALING',
    'skipped': 'NO_TESTS_EXECUTED',
    'unknown': 'TEST_EXECUTION_UNKNOWN',
}
PASS = ('import unittest\nclass T(unittest.TestCase):\n'
        '    def test_example(self):\n        self.assertTrue(True)\n')
SKIP = ('import unittest\n@unittest.skip("synthetic prerequisite absent")\n'
        'class S(unittest.TestCase):\n'
        '    def test_example(self):\n        self.fail("must not run")\n')


def _fixture_tree(root: Path) -> None:
    """Write only fixed synthetic examples in the freshly owned temp directory."""
    sources = {
        'clean': PASS,
        'empty': '# Intentionally no unittest cases.\n',
        'failed': PASS.replace('self.assertTrue(True)', 'self.assertEqual(1, 2)'),
        'foreign': PASS.replace('self.assertTrue(True)',
            '__import__("pathlib").Path("../' + PREFIX + 'clean/borrowed.txt")'
            '.write_text("synthetic cross-lane write", encoding="utf-8")'),
        'mutating': PASS.replace('self.assertTrue(True)',
            '__import__("pathlib").Path("record.txt")'
            '.write_text("AFTER", encoding="utf-8")'),
        'partial': PASS + '\n' + SKIP,
        'self_sealing': PASS.replace('self.assertTrue(True)',
            '__import__("pathlib").Path("manifest.json")'
            '.write_text(__import__("json").dumps({"sha256": "1" * 64}), '
            'encoding="utf-8")'),
        'skipped': SKIP,
        'unknown': 'raise SystemExit(0)  # No runner receipt is produced.\n',
    }
    for name in EXPECTED:
        lane = root / (PREFIX + name)
        lane.mkdir()
        (lane / 'README.txt').write_text('SYNTHETIC REHEARSAL ONLY\n', encoding='utf-8')
        if name in sources:
            (lane / 'test_example.py').write_text(sources[name], encoding='utf-8')
    (root / (PREFIX + 'mutating') / 'record.txt').write_text('BEFORE', encoding='utf-8')
    (root / (PREFIX + 'self_sealing') / 'manifest.json').write_text(
        json.dumps({'sha256': '0' * 64}), encoding='utf-8')


def _bytes(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob('*')) if p.is_file()}


def run_rehearsal() -> dict:
    auditor = Path(__file__).with_name('audit_self_sealing.py')
    source_before = auditor.read_bytes()
    command = [sys.executable]
    if sys.flags.optimize:
        command.append('-' + 'O' * sys.flags.optimize)
    with tempfile.TemporaryDirectory(prefix='auditor-operator-rehearsal-') as tmp:
        root = Path(tmp)
        _fixture_tree(root)
        before = _bytes(root)
        child = subprocess.run(command + [str(auditor), str(root), '--format',
                               'json', '--require-clean'], capture_output=True,
                               text=True, errors='replace', timeout=30)
        results = json.loads(child.stdout)
        unchanged = before == _bytes(root) and source_before == auditor.read_bytes()
    if not isinstance(results, list):
        raise ValueError('auditor result is not a list')
    expected_names = {PREFIX + name for name in EXPECTED}
    observed_names = [r.get('lane') for r in results if isinstance(r, dict)]
    mismatches = []
    if len(observed_names) != len(results) or len(set(observed_names)) != len(results):
        mismatches.append('missing or duplicate lane identities')
    if set(observed_names) != expected_names:
        mismatches.append('auditor did not report exactly the synthetic lane set')
    rows = []
    for result in results:
        if not isinstance(result, dict):
            continue
        name = result.get('lane', '')
        short_name = name.removeprefix(PREFIX) if isinstance(name, str) else ''
        expected = EXPECTED.get(short_name)
        if expected is None or result.get('verdict') != expected:
            mismatches.append('verdict mismatch: ' + str(name))
        runs = (result.get('suite') or {}).get('runs', [])
        rows.append({'lane': short_name, 'expected': expected,
                     'observed': result.get('verdict'),
                     'execution': [r.get('execution') for r in runs],
                     'mutated_files': len(result.get('mutated', []))})
    if child.returncode != 1:
        mismatches.append('expected strict exit 1 for deliberately defective lanes')
    if not unchanged:
        mismatches.append('source or synthetic input changed')
    return {
        'kind': 'SYNTHETIC_OPERATOR_REHEARSAL',
        'rehearsal_passed': not mismatches,
        'auditor_all_clean': bool(results) and all(
            isinstance(r, dict) and r.get('verdict') == 'CLEAN' for r in results),
        'audit_exit_code': child.returncode,
        'auditor_sha256': hashlib.sha256(source_before).hexdigest(),
        'optimization': sys.flags.optimize,
        'source_and_input_unchanged': unchanged,
        'rows': sorted(rows, key=lambda row: row['lane']),
        'mismatches': mismatches,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Run a synthetic auditor rehearsal.')
    parser.add_argument('--format', choices=('text', 'json'), default='text')
    args = parser.parse_args(argv)
    try:
        report = run_rehearsal()
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
        report = {'kind': 'SYNTHETIC_OPERATOR_REHEARSAL', 'rehearsal_passed': False,
                  'auditor_all_clean': None,
                  'error': type(exc).__name__ + ': ' + str(exc)}
    if args.format == 'json':
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print('SYNTHETIC REHEARSAL — success means expected defects were observed.')
        for row in report.get('rows', []):
            print('%-14s %-24s expected=%s' %
                  (row['lane'], row['observed'], row['expected']))
        print('rehearsal_passed=%s; auditor_all_clean=%s' %
              (report['rehearsal_passed'], report['auditor_all_clean']))
        for message in report.get('mismatches', []):
            print(message)
        if 'error' in report:
            print(report['error'])
    return 0 if report['rehearsal_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
