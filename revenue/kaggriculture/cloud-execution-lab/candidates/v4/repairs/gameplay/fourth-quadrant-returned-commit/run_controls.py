# SPDX-License-Identifier: Apache-2.0
"""Run exact predecessor and semantic mutants through the independent suite."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from compose import LAND_CHECK, compose, git_blob


def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('mutation anchor is not unique: ' + old)
    return source.replace(old, new, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    original = (args.package / 'fourth_quadrant.py').read_bytes()
    good = compose(original).decode('utf-8')
    prefix = "and returned.get('market', [])[:cap] == selected.get('market', [])[:cap]"
    variants = {
        'predecessor': original.decode('utf-8'),
        'ignore_market_prefix': once(good, prefix, 'and True'),
        'filter_empty_slots': once(good, prefix,
            "and [o for o in returned.get('market', []) if o][:cap] == [o for o in selected.get('market', []) if o][:cap]"),
        'zero_cap_not_engine_normalized': once(good,
            "cap = max(1, int(self.configuration.get('maxMarketOrdersPerTurn', 10)))",
            "cap = max(0, int(self.configuration.get('maxMarketOrdersPerTurn', 10)))"),
        'ignore_surplus_actors': once(good,
            "and returned.get('hands', []) == selected.get('hands', [])", 'and True'),
        'ignore_observed_acquisition': once(good, LAND_CHECK, ''),
        'ignore_locked_target_cells': once(good,
            "                    if any(farm['tiles'][y][x] == 'LOCKED' for x, y in proposal['tiles']):\n                        return False\n", ''),
        'retain_rejected_pending': once(good,
            '        pending, selected = self.pending, self.selected\n        self.pending = None; self.selected = None\n',
            '        pending, selected = self.pending, self.selected\n'),
    }
    results = []
    for name, source in variants.items():
        compile(source, '<' + name + '>', 'exec')
        with tempfile.TemporaryDirectory(prefix='landreturn-control-') as tmp:
            target = Path(tmp) / 'candidate.py'
            target.write_text(source)
            receipt = args.output / (name + '.json')
            command = [sys.executable] + (['-O'] if sys.flags.optimize else []) + [
                str(Path(__file__).with_name('check_landreturn.py')), '--package', str(args.package.resolve()),
                '--target-source', str(target), '--receipt', str(receipt.resolve())]
            run = subprocess.run(command, capture_output=True, timeout=15)
            log = args.output / (name + '.log')
            log.write_bytes(run.stdout + run.stderr)
            data = json.loads(receipt.read_text()) if receipt.is_file() else {}
            killed = (run.returncode == 1 and data.get('tests_run') == 20
                      and data.get('failures', 0) > 0 and data.get('skipped') == 0)
            results.append({'control': name, 'target_blob': git_blob(source.encode()),
                'returncode': run.returncode, 'tests_run': data.get('tests_run'),
                'failures': data.get('failures'), 'errors': data.get('errors'),
                'assertion_killed': killed, 'receipt_blob': git_blob(receipt.read_bytes()) if receipt.is_file() else None,
                'log_blob': git_blob(log.read_bytes())})
            print(name, 'assertion-killed' if killed else 'INVALID CONTROL',
                  data.get('failures'), data.get('errors'), flush=True)
    summary = {'optimization': sys.flags.optimize, 'controls': results,
               'control_count': len(results), 'semantic_mutants': len(results)-1,
               'all_assertion_killed': all(r['assertion_killed'] for r in results),
               'runner_blob': git_blob(Path(__file__).read_bytes())}
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
    return 0 if summary['all_assertion_killed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
