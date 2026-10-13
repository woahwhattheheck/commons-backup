"""Execute seven independent broken-contract controls in normal and -O Python.

The exact unmodified contract must pass first in each mode. A mutant counts as
rejected only after all 22 unit tests run without errors/skips and at least one
assertion fails. Missing files, import failures and timeouts are NOT kills.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

MUTANTS = {
    "occupied_slot_accepted": ('if not _empty_slot(old[0]):', 'if False:'),
    "other_slots_unchecked": ('if _encoded(new[1:]) != _encoded(old[1:]):', 'if False:'),
    "extra_rows_allowed": ('elif len(new) != 1:', 'elif False:'),
    "nonmarket_edits_allowed": ('if _encoded(b_rest) != _encoded(a_rest):', 'if False:'),
    "scalar_types_conflated": ('if _encoded(b_rest) != _encoded(a_rest):', 'if b_rest != a_rest:'),
    "dead_suffix_treated_active": ('enumerate(new[1:cap], 1)', 'enumerate(new[1:], 1)'),
    "capital_hazards_ignored": ('if row[0] in RESOURCE_ORDERS:', 'if False:'),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    helper = root / 'join_queue_contract.py'
    source = helper.read_text()
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for optimized in (False, True):
            for name, replacement in [('control', None), *MUTANTS.items()]:
                text = source
                if replacement is not None:
                    old, new = replacement
                    if text.count(old) != 1:
                        raise RuntimeError('mutation anchor drift: ' + name)
                    text = text.replace(old, new)
                candidate = tmp / (name + ('_O' if optimized else '') + '.py')
                candidate.write_text(text)
                report = candidate.with_suffix('.json')
                command = [sys.executable] + (['-O'] if optimized else [])
                command += [str(root / 'check_join_queue_contract.py'), '--unit-only',
                            '--contract', str(candidate), '--receipt', str(report)]
                proc = subprocess.run(command, capture_output=True, timeout=20)
                if not report.exists():
                    raise RuntimeError('non-test failure: ' + name)
                data = json.loads(report.read_text())
                expected = (proc.returncode == 0 and data['failures'] == 0) if name == 'control' else (
                    proc.returncode == 1 and data['failures'] > 0)
                if not expected or data['tests'] != 22 or data['errors'] or data['skipped']:
                    raise RuntimeError('invalid or surviving control: ' + name)
                results.append({'name': name, 'optimized': optimized,
                                'tests': data['tests'], 'assertion_failures': data['failures'],
                                'errors': data['errors'], 'returncode': proc.returncode,
                                'stdout_sha256': hashlib.sha256(proc.stdout).hexdigest(),
                                'stderr_sha256': hashlib.sha256(proc.stderr).hexdigest(),
                                'candidate_blob': data['contract_blob']})
    args.receipt.write_text(json.dumps({'controls': results, 'mutants_rejected_per_mode': 7}, indent=2, sort_keys=True) + '\n')
    print('Both unchanged controls pass; 7/7 assertion-rejected mutants in each mode.')


if __name__ == '__main__':
    main()
