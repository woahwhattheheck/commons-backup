# SPDX-License-Identifier: Apache-2.0
"""Execute green controls then assertion-reject independent policy defects."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
MUTANTS = {
    'seed_not_debited': ("private['seeds'][crop] -= 1", "private['seeds'][crop] -= 0"),
    'feed_not_debited': ("inv['WHEAT'] -= 1", "inv['WHEAT'] -= 0"),
    'unbounded_drop': ("min(n, max(0, capacity - sum(private['shed'].values())))", "n"),
    'input_farm_alias': ("farm = deepcopy(observation['farms'][seat])", "farm = observation['farms'][seat]"),
    'input_private_alias': ("private = deepcopy(observation['private'])", "private = observation['private']"),
    'new_hand_acts_now': ("'hands': actions[1:]", "'hands': actions[1:] + [['PASS']]"),
    'ignore_market_limit': ("'market': market[:limit]", "'market': market"),
    'no_cargo_feed_accounting': ("feed = stock.get('WHEAT', 0) + sum(i.get('WHEAT', 0) for i in private['inventories'])", "feed = stock.get('WHEAT', 0)"),
}

def check(runtime, optimized):
    source = (HERE / 'reactive_challengers.py').read_text()
    results = {}
    for label, change in [('green', None), *MUTANTS.items()]:
        with tempfile.TemporaryDirectory(prefix='orchard-mutation-') as tmp:
            root = Path(tmp)
            for name in ('bench_challengers.py', 'test_reactive_challengers.py'):
                shutil.copy2(HERE / name, root / name)
            modified = source
            if change is not None:
                old, new = change
                if source.count(old) != 1:
                    raise ValueError(f'Mutation anchor no longer unique: {label}')
                modified = source.replace(old, new)
            (root / 'reactive_challengers.py').write_text(modified)
            command = [sys.executable, *(['-O'] if optimized else []),
                       str(root / 'test_reactive_challengers.py'), '--runtime', str(runtime)]
            proc = subprocess.run(command, capture_output=True, text=True, timeout=30)
            text = proc.stdout + proc.stderr
            if label == 'green':
                accepted = proc.returncode == 0 and '\nOK\n' in text
            else:
                accepted = (proc.returncode != 0 and 'FAIL:' in text
                            and 'AssertionError' in text and 'ERROR:' not in text)
            results[label] = {'expected_outcome': accepted, 'returncode': proc.returncode, 'log': text}
            if not accepted:
                raise AssertionError(f'Control failed: {label}, optimized={optimized}\n{text}')
    return results

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    results = {mode: check(args.runtime, optimized) for mode, optimized in [('normal',False),('optimized',True)]}
    args.output.write_text(json.dumps(results, indent=2, sort_keys=True) + '\n')
    print('Green controls pass; 8/8 semantic defects assertion-rejected in each mode.')

if __name__ == '__main__':
    main()
