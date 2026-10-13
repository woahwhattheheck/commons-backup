# SPDX-License-Identifier: Apache-2.0
"""Run explicit test-only faults against the source-integrity gate."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

MUTATIONS = {
    "accept_duplicate_class": ('if len(classes) != 1:', 'if not classes:'),
    "accept_duplicate_method": ('if len(methods) != 1 or not isinstance(methods[0], ast.FunctionDef)',
                                'if not methods or not isinstance(methods[0], ast.FunctionDef)'),
    "accept_decorated_method": ('or methods[0].decorator_list:', 'or False:'),
    "skip_initial_source_authentication": ('if hashlib.sha256(before).hexdigest() == METHOD_SHA256:', 'if True:'),
    "skip_repaired_source_authentication": ('if hashlib.sha256(original.encode("utf-8")).hexdigest() != METHOD_SHA256:', 'if False:'),
    "append_unreviewed_outside_byte": ('return output\n', 'return output + b"\\n"\n'),
    "overwrite_existing_scratch": ('args.output.open("xb")', 'args.output.open("wb")'),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--repair', type=Path, default=Path(__file__).with_name('repair_seed_funding_prefix.py'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('normal', 'optimized', 'both'), default='both')
    args = parser.parse_args()
    check = Path(__file__).with_name('check_seed_prefix_source_integrity.py')
    original = args.repair.read_text()
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        for label, (old, new) in MUTATIONS.items():
            if original.count(old) != 1:
                raise ValueError(f'negative-control source drift: {label}')
            raw = original.replace(old, new, 1).encode()
            path = Path(directory) / (label + '.py')
            path.write_bytes(raw)
            compile(raw, str(path), 'exec')  # faults must remain importable Python
            for optimized in ((False, True) if args.mode == 'both' else (args.mode == 'optimized',)):
                command = [sys.executable] + (['-O'] if optimized else []) + [
                    str(check), '--runtime', str(args.runtime.resolve()),
                    '--repair', str(path), '--allow-mutant']
                result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                combined = result.stdout + result.stderr
                killed = result.returncode == 1 and 'FAILED (' in combined and 'Ran 22 tests' in combined
                rows.append({'mutation': label, 'optimized': optimized,
                             'mutant_sha256': hashlib.sha256(raw).hexdigest(),
                             'exit_code': result.returncode, 'killed': killed,
                             'log_sha256': hashlib.sha256(combined.encode()).hexdigest(),
                             'summary': combined[combined.rfind('Ran 22 tests'):].strip()})
                print(label, optimized, killed, flush=True)
                args.output.write_text(json.dumps({'complete': False, 'rows': rows}, indent=2) + '\n')
    report = {'schema': 1, 'scope': 'source-authentication-and-CLI-only',
              'per_mode_mutations': len(MUTATIONS), 'rows': rows,
              'all_killed': all(row['killed'] for row in rows)}
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report['all_killed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
