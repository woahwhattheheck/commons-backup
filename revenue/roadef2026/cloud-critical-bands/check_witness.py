#!/usr/bin/env python3
"""Execute or inspect the four retained mechanism cases with a supplied checker."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from decimal import Decimal
from test_critical_bands import run_case

CASES = ('original-witness', 'disabled', 'enabled', 'cap32')

def inspect_saved(root: Path) -> dict:
    reports = {}
    correspondence = []
    for name in CASES:
        native = json.loads((root / name / 'stats.json').read_text(), parse_float=Decimal)
        own = {(r['t'], r['from'], r['to']): Decimal(r['sat']) for r in native['loads']}
        for precision in (6, 12):
            raw = (root / name / f'checker-{precision}.json').read_bytes()
            report = json.loads(raw, parse_float=Decimal)
            if report.get('valid') is not True:
                raise ValueError(f'{name}: checker did not validate the output')
            actual = {(r['t'], r['from'], r['to']): Decimal(r['sat']) for r in report['saturations']}
            if len(actual) != len(report['saturations']) or actual.keys() != own.keys():
                raise ValueError(f'{name}: incomplete or duplicate checker coordinates')
            if any(not v.is_finite() or v < 0 for v in actual.values()):
                raise ValueError(f'{name}: invalid saturation value')
            error = max(abs(own[key] - actual[key]) for key in own)
            if error > Decimal('0.000001' if precision == 6 else '0.000000000002'):
                raise ValueError(f'{name}: native and checker loads differ')
            if sum(native['budget_used']) != report['total_cost']:
                raise ValueError(f'{name}: transition costs differ')
            reports[name, precision] = sorted(actual.values(), reverse=True)
            correspondence.append({'case': name, 'precision': precision, 'load_count': len(actual),
                                   'maximum_absolute_difference': str(error), 'total_cost': report['total_cost'],
                                   'checker_sha256': hashlib.sha256(raw).hexdigest()})
    for precision in (6, 12):
        before, after = reports['original-witness', precision], reports['enabled', precision]
        if (reports['disabled', precision] != before or reports['cap32', precision] != before or
                before[:40] != after[:40] or before[40] != 1 or after[40] != Decimal('.1') or not after < before):
            raise ValueError('Expected lower-rank discriminator or controls differ')
    return {'schema': 'roadef.critical-bands-witness.v1', 'first_improved_rank': 41,
            'before': '1.0', 'after': '0.1', 'unchanged_peak': '2.0', 'unchanged_total_cost': 0,
            'cases': 4, 'checker_outputs': 8, 'correspondence': correspondence}

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--checker', type=Path)
    p.add_argument('--read-existing', action='store_true', help='Inspect saved outputs without any solver/checker call')
    args = p.parse_args()
    if not args.read_existing:
        if args.checker is None:
            p.error('--checker is required for execution')
        args.output.mkdir(parents=True, exist_ok=False)
        cases = [run_case(args.output, 'original-witness'), run_case(args.output, 'disabled', enabled=0),
                 run_case(args.output, 'enabled', enabled=1), run_case(args.output, 'cap32', enabled=1, cap=32)]
        for item in cases:
            case = item['case']
            for precision in (6, 12):
                command = [str(args.checker), '--net', str(case/'network.json'), '--tm', str(case/'traffic.json'),
                           '--scenario', str(case/'scenario.json'), '--srpaths', str(item['output']),
                           '--max-decimal-places', str(precision)]
                result = subprocess.run(command, capture_output=True, timeout=30)
                (case/f'checker-{precision}.json').write_bytes(result.stdout)
                (case/f'checker-{precision}.stderr').write_bytes(result.stderr)
                (case/f'checker-{precision}-command.json').write_text(json.dumps(command)+'\n')
                if result.returncode:
                    raise RuntimeError(f'{case.name}: checker exited {result.returncode}; raw output retained')
    summary = inspect_saved(args.output)
    (args.output/'WITNESS-RESULTS.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, sort_keys=True))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
