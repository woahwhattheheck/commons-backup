"""Local receipt helper; mutates temporary copies only, never published source."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).parent
source = (root / 'audit_paired_panel.py').read_text()
tests = (root / 'test_audit_paired_panel.py').read_text()
mutants = [
    ('missing_cells', 'for key in sorted(expected - set(counts)):', 'for key in []:',
     'test_missing_both_arms_is_not_invisible'),
    ('duplicates', 'if count > 1:', 'if False:',
     'test_identical_duplicate_is_not_extra_evidence'),
    ('mixed_pins', 'mismatches = [pin for pin, value in matches.items() if row[pin] != value]',
     'mismatches = []', 'test_all_pin_mismatches_are_rejected'),
    ('confirmation_overlap', 'if overlap:', 'if False:',
     'test_confirmation_reuses_world_under_other_opponent_rejects'),
    ('ancestor_history', '_check(all(set(p["prior_plan_sha256"]) <= set(prior_hashes) for p in prior_plans),',
     '_check(True,', 'test_transitive_tuning_history_cannot_disappear'),
    ('bool_integer', 'type(value) is int and value >= 0',
     'isinstance(value, int) and value >= 0', 'test_unexpected_seed_opponent_and_seat_arm_domain'),
    ('duplicate_json', '_check(key not in out, f"duplicate JSON key: {key}")',
     'pass', 'test_strict_json_duplicate_key_and_constants'),
]
results = []
with tempfile.TemporaryDirectory() as directory:
    work = Path(directory)
    (work / 'test_audit_paired_panel.py').write_text(tests)
    for name, old, new, test in mutants:
        if source.count(old) != 1:
            raise RuntimeError(f'mutation anchor not unique: {name}')
        (work / 'audit_paired_panel.py').write_text(source.replace(old, new))
        for optimize in (False, True):
            # No bytecode cache is reused between distinct mutant sources.
            completed = subprocess.run([sys.executable, '-B', *(['-O'] if optimize else []),
                                        '-m', 'unittest', 'test_audit_paired_panel.PanelTests.' + test],
                                       cwd=work, capture_output=True, text=True, timeout=15)
            record = {'mutant': name, 'optimized': optimize,
                      'test': test,
                      'rejected': (completed.returncode != 0
                                   and 'Ran 1 test' in completed.stderr
                                   and ('\nFAIL:' in completed.stderr
                                        or '\nERROR:' in completed.stderr)
                                   and 'Failed to import test module' not in completed.stderr
                                   and 'SyntaxError:' not in completed.stderr)}
            results.append(record)
            if not record['rejected']:
                raise RuntimeError(f'undetected mutant: {record}')
(root / 'mutation_receipt.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps({'mutants': len(mutants), 'mode_runs': len(results),
                  'all_rejected': all(r['rejected'] for r in results)}, indent=2))
