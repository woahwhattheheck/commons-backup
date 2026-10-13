"""Reject deliberate auditor defects with named behavioral assertion failures."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

MUTANTS = [
    ('raw-slot-compaction',
     'return deepcopy(self._frames[step]["actions"][self.seat])',
     'action = deepcopy(self._frames[step]["actions"][self.seat])\n        action["market"] = [row for row in action.get("market", []) if row]\n        return action',
     'test_raw_prefix_and_surplus_hands_not_normalized'),
    ('input-alias', '"actions": deepcopy(actions)', '"actions": actions', 'test_input_tape_detached'),
    ('invent-filled-units', 'row["filled"] += int(bool(result))', 'row["filled"] += 1',
     'test_unaffordable_buy_is_attempt_not_fill'),
    ('erase-physical-drift',
     '    def _compare(self, key: str, reference: Any, actual: Any, step: int):\n',
     '    def _compare(self, key: str, reference: Any, actual: Any, step: int):\n        if "own_production" in key:\n            return\n',
     'test_shed_divergence_not_confused_with_market'),
    ('overwrite-first-witness', 'if key not in self.first:', 'if True:',
     'test_first_witness_is_earliest_not_latest'),
    ('allow-repeated-callback', 'if step != self.next_step:\n            raise ReplayError',
     'if step > self.next_step:\n            raise ReplayError', 'test_callback_sequence_rejected'),
    ('invent-hire-fills', 'row["filled"] += len(farm["hands"]) - before_hands',
     'row["filled"] += 1', 'test_hire_calls_are_not_hires_when_no_cash'),
    ('reverse-cash-sign', 'row["cash_delta"] += farm["money"] - before\n',
     'row["cash_delta"] -= farm["money"] - before\n', 'test_partial_fill_matches_stock_and_cash'),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    here = Path(__file__).resolve().parent
    good = (here / 'tape_integrity.py').read_text()
    report = {'schema': 'titan-replay-mutations/1', 'parent_optimized': bool(sys.flags.optimize),
              'source_sha256': hashlib.sha256(good.encode()).hexdigest(), 'mutants': []}
    for name, old, new, expected in MUTANTS:
        if old not in good:
            raise RuntimeError(f'mutant preimage absent: {name}')
        # Only the named source is altered. Engine/evaluator/native pins remain exact.
        bad = good.replace(old, new)
        with tempfile.TemporaryDirectory(prefix='titan-tape-mutant-') as directory:
            target = Path(directory)
            (target/'tape_integrity.py').write_text(bad)
            for filename in ('check_replay_integrity.py', 'run_counterfactual_probe.py'):
                shutil.copyfile(here/filename, target/filename)
            proof = args.output / f'{name}.json'
            command = [sys.executable] + (['-O'] if sys.flags.optimize else []) + [
                str(target/'check_replay_integrity.py'), '--native', str(args.native.resolve()), '--report', str(proof.resolve())]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            (args.output/f'{name}.log').write_text(result.stdout+result.stderr)
            data = json.loads(proof.read_text()) if proof.exists() else {}
            failing = [r['test'] for r in data.get('failures', [])]
            killed = (result.returncode == 1 and data.get('tests_run') == 43 and
                      not data.get('errors') and data.get('skips') == 0 and
                      any(expected in test for test in failing))
            row = {'name': name, 'expected_behavioral_test': expected, 'returncode': result.returncode,
                   'tests_run': data.get('tests_run'), 'assertion_failures': len(failing),
                   'errors': len(data.get('errors', [])), 'killed_by_assertion': killed,
                   'source_sha256': hashlib.sha256(bad.encode()).hexdigest()}
            report['mutants'].append(row); print(json.dumps(row), flush=True)
    report['all_killed'] = all(x['killed_by_assertion'] for x in report['mutants'])
    (args.output/'RESULTS.json').write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    return 0 if report['all_killed'] else 1


if __name__ == '__main__': raise SystemExit(main())
