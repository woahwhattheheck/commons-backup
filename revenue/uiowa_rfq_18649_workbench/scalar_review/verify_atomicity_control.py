#!/usr/bin/env python3
"""Reproduce the old test's blind spot using a deliberately partial-restoring copy.

This offline test-quality experiment never changes source input files. It uses
prepare_fixture.py to pin the existing four workbench assets and apply only the
already-reviewed scalar correction in a new directory. Browser tests abort all
network requests. No compiler/HTTP/hosted or production-atomicity claim is made.
"""
from __future__ import annotations
import argparse
import ast
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from prepare_fixture import EXPECTED, git_blob, prepare

HERE = Path(__file__).resolve().parent
TARGET = 'test_invalid_last_cell_preserves_all_twelve_notes_atomically'
WEAK_TEST_BLOB = '5a7874763bdd6d15147c021ad2af66941e8c9a21'
WEAK_METHOD = " def " + TARGET + "(self):\n  self.assert_rejected('Final cell \\ud800',11)\n"
SEAM = b'    const restored = HandoffImport.parseDraft(contents, report);'
PARTIAL = b'''    // NEGATIVE CONTROL ONLY: incorrectly apply rows before full validation.
    const premature = JSON.parse(contents);
    for (const row of premature.cell_notes.slice(0, -1)) {
      state.notes.set(keyFor(row), row.analyst_note);
      state.dispositions.set(keyFor(row), row.disposition);
    }
'''


def weak_test(raw: bytes) -> bytes:
    """Restore only the former test method and verify the exact historical blob."""
    text = raw.decode('utf-8')
    functions = [node for node in ast.walk(ast.parse(text))
                 if isinstance(node, ast.FunctionDef) and node.name == TARGET]
    if len(functions) != 1:
        raise ValueError('the atomicity test method is not unique')
    method = functions[0]
    lines = text.splitlines(keepends=True)
    result = ''.join(lines[:method.lineno-1]) + WEAK_METHOD + ''.join(lines[method.end_lineno:])
    encoded = result.encode('utf-8')
    if git_blob(encoded) != WEAK_TEST_BLOB:
        raise ValueError('historical test reconstruction changed; review before rebinding')
    return encoded


def run_case(script: Path, source: Path, *, optimized: bool, targeted: bool) -> dict:
    command = [sys.executable, '-B']
    if optimized:
        command += ['-O', '-W', 'error::ResourceWarning']
    command.append(str(script))
    if targeted:
        command.append('ScalarNoteBrowserTests.' + TARGET)
    environment = {**os.environ, 'WORKBENCH_SOURCE': str(source)}
    result = subprocess.run(command, env=environment, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=60, check=False)
    return {'command': command, 'source': str(source), 'exit_code': result.returncode,
            'output': result.stdout.decode('utf-8', errors='strict')}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True, help='new directory; parent must exist')
    parser.add_argument('--optimized', action='store_true')
    args = parser.parse_args()
    try:
        source = args.source.resolve()
        out = args.out.resolve()
        runner = HERE / 'browser_scalar_acceptance.py'
        current_test = runner.read_bytes()
        historical_test = weak_test(current_test)
        # Validation in prepare completes before its new output directory exists.
        manifest = prepare(source, out)
        (out / 'historical_browser_test.py').write_bytes(historical_test)
        mutant = out / 'partial-mutant'
        mutant.mkdir()
        for name in EXPECTED:
            shutil.copyfile(out / 'after' / name, mutant / name)
        raw = (mutant / 'app.js').read_bytes()
        if raw.count(SEAM) != 1:
            raise ValueError('the mutation seam is not unique')
        injection = PARTIAL.replace(b'\n', b'\r\n') if b'\r\n' in raw else PARTIAL
        (mutant / 'app.js').write_bytes(raw.replace(SEAM, injection + SEAM))
        cases = {
            'strong_correct_full_suite': run_case(runner, out / 'after', optimized=args.optimized, targeted=False),
            'historical_weak_mutant': run_case(out / 'historical_browser_test.py', mutant, optimized=args.optimized, targeted=True),
            'strong_mutant': run_case(runner, mutant, optimized=args.optimized, targeted=True),
        }
        normal = cases['strong_correct_full_suite']
        weak = cases['historical_weak_mutant']
        strong = cases['strong_mutant']
        checks = {
            'real_scalar_fixed_app_passes_all_nine': normal['exit_code'] == 0 and bool(re.search(r'Ran 9 tests .*\n\nOK\s*$', normal['output'])),
            'old_test_misses_partial_application': weak['exit_code'] == 0 and bool(re.search(r'Ran 1 test .*\n\nOK\s*$', weak['output'])),
            'strong_test_detects_review_replacement': strong['exit_code'] == 1 and 'FAILED (failures=1)' in strong['output'] and 'Rejected final row must preserve the entire original review' in strong['output'] and 'ERROR:' not in strong['output'],
            'source_still_matches': all(git_blob((source/name).read_bytes()) == value for name, value in EXPECTED.items()),
        }
        report = {
            'schema': 'scalar-note-atomicity-test-quality/v1',
            'optimized': args.optimized, 'checks': checks,
            'source_manifest': manifest,
            'test_blob': git_blob(current_test), 'historical_test_blob': WEAK_TEST_BLOB,
            'mutant_app_blob': git_blob((mutant / 'app.js').read_bytes()),
            'cases': cases,
            'limitation': 'Deliberately broken test copy, not an observed production atomicity defect. Browser-local synthetic report only; no HTTP, parent compiler, hosted CI or layout acceptance.',
        }
        with (out / 'ATOMICITY_EXECUTION.json').open('x', encoding='utf-8') as handle:
            json.dump(report, handle, indent=2, ensure_ascii=True)
            handle.write('\n')
        print(json.dumps({'checks': checks, 'receipt': str(out/'ATOMICITY_EXECUTION.json')}, indent=2))
        return 0 if all(checks.values()) else 1
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
