# SPDX-License-Identifier: Apache-2.0
"""Reject six deliberately broken CF1 DROP continuations in both Python modes."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
MUTATIONS = {
    'ignore_whole_farm_capacity': ('if total + 1 > 100:', 'if False:'),
    'ignore_delayed_cargo_sales': (
        'if any(quantity > 0 and item in sold for item, quantity in inventories[actor].items()):',
        'if False:'),
    'ignore_other_harvest_production': ('total += 6', 'total += 0'),
    'ignore_cow_site_exclusivity': (
        "if command != ['DROP'] or sites.count((x, y)) != 1:", "if command != ['DROP']:"),
    'inspect_dead_raw_market_suffix': ('for row in market[:10]:', 'for row in market:'),
    'allow_incomplete_days': (
        'not 0 <= step <= 695 or step % 24 != 23', 'not 0 <= step <= 719'),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-dir', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = (HERE / 'drop_continuation.py').read_text()
    rows = []
    with tempfile.TemporaryDirectory(prefix='cf1-drop-mutants-') as temp:
        for name, (old, new) in MUTATIONS.items():
            if source.count(old) != 1:
                raise ValueError(f'{name}: source anchor no longer unique')
            mutant = Path(temp) / (name+'.py')
            mutant.write_text(source.replace(old, new, 1))
            for optimized in (False, True):
                env = dict(os.environ, TITAN_ENGINE_DIR=args.engine_dir,
                           TITAN_CF1_DROP_SOURCE=str(mutant))
                command = [sys.executable] + (['-O'] if optimized else []) + [
                    '-m', 'unittest', 'check_eod_drop_fert']
                run = subprocess.run(command, cwd=HERE, env=env, capture_output=True, text=True, timeout=20)
                log = run.stdout + run.stderr
                rejected = (run.returncode == 1 and 'Ran 22 tests' in log
                            and 'FAILED (failures=' in log and 'errors=' not in log)
                rows.append({'name': name, 'optimized': optimized,
                             'returncode': run.returncode, 'assertion_rejected': rejected,
                             'mutant_sha256': hashlib.sha256(mutant.read_bytes()).hexdigest(),
                             'log_sha256': hashlib.sha256(log.encode()).hexdigest()})
                if not rejected:
                    print(log, file=sys.stderr)
                    raise RuntimeError(f'{name} optimized={optimized}: not assertion-killed')
    args.output.write_text(json.dumps({'schema': 'cf1-drop-mutations/v1', 'results': rows}, indent=2)+'\n')
    print(f'{len(rows)}/{len(rows)} source mutation executions assertion-killed')


if __name__ == '__main__':
    main()
