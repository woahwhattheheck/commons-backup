"""Run finite local acceptance checks and record exact source identities.

Usage: python evidence/run_validation.py --out NEW_DIRECTORY
No dependency installation, network request, repository write, or hosted job.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def source_hashes() -> dict[str, str]:
    files = sorted({*ROOT.glob('cashiering_lab/*.py'), *ROOT.glob('tests/*.py'),
                    *ROOT.glob('examples/*.json'), *ROOT.glob('evidence/*.py')})
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    output = args.out.resolve()
    output.mkdir(parents=False, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    before = source_hashes()
    runs = []

    def run(label: str, argv: list[str], expected: int = 0) -> None:
        tick = time.perf_counter()
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=120)
        log = output / f'{label}.log'
        log.write_text(result.stdout + result.stderr, encoding='utf-8')
        counts = re.findall(r'Ran (\d+) tests? in', result.stderr)
        entry = dict(label=label, argv=argv, expected_exit=expected,
                     actual_exit=result.returncode,
                     seconds=round(time.perf_counter()-tick, 6),
                     tests=int(counts[-1]) if counts else None,
                     log=log.name, log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
        entry['pass'] = result.returncode == expected
        runs.append(entry)
        if not entry['pass']:
            raise RuntimeError(f'{label} returned {result.returncode}; expected {expected}; see {log}')

    error = None
    try:
        run('unittest_normal', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'])
        run('unittest_optimized', [sys.executable, '-O', '-m', 'unittest', 'discover', '-s', 'tests', '-v'])
        modules = [str(p.relative_to(ROOT)) for p in sorted(ROOT.glob('cashiering_lab/*.py'))]
        modules += [str(p.relative_to(ROOT)) for p in sorted(ROOT.glob('tests/*.py'))]
        modules += [str(p.relative_to(ROOT)) for p in sorted(ROOT.glob('evidence/*.py'))]
        run('py_compile', [sys.executable, '-m', 'py_compile', *modules])
        for name, optimized, expected in [('clean', False, 0), ('exceptions', True, 1)]:
            flags = ['-O'] if optimized else []
            target = output / f'bundle-{name}'
            run(f'compile_{name}', [sys.executable, *flags, '-m', 'cashiering_lab', 'compile',
                                   f'examples/{name}.json', '--out', str(target)], expected)
            run(f'verify_{name}', [sys.executable, *flags, '-m', 'cashiering_lab', 'verify', str(target)])
        for rows in (1000, 5000, 10000):
            run(f'benchmark_{rows}', [sys.executable, 'evidence/benchmark.py', '--transactions', str(rows)])
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        error = f'{type(exc).__name__}: {exc}'
    after = source_hashes()
    receipt = dict(schema='cashiering-local-validation/1',
                   started_at_utc=started, finished_at_utc=datetime.now(timezone.utc).isoformat(),
                   python=platform.python_version(), executable=sys.executable,
                   platform=platform.platform(), machine=platform.machine(),
                   optimized_parent=bool(sys.flags.optimize),
                   source_before_sha256=before, source_after_sha256=after,
                   source_unchanged=before == after, runs=runs, error=error,
                   status='PASS' if error is None and before == after else 'FAIL',
                   evidence_scope='LOCAL_SYNTHETIC_AUTHOR_EXECUTION_NOT_INDEPENDENT_OR_HOSTED_OR_PRODUCTION',
                   performs_remote_publication=False, performs_deployment=False)
    (output/'receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True)+'\n')
    print(json.dumps({k:receipt[k] for k in ('status','python','source_unchanged','error')}, sort_keys=True))
    return 0 if receipt['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
