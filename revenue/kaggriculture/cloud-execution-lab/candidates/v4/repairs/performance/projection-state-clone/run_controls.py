# SPDX-License-Identifier: Apache-2.0
"""Eight deliberately wrong graph copiers must fail behavioral assertions."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
MUTATIONS = (
    ('shallow_children', 'append(_clone(item, memo))', 'append(item)',
     'test_alias_graph_and_isolation'),
    ('forget_aliases', 'memo[ident] = result', '# broken: no memo binding',
     'test_alias_graph_and_isolation'),
    ('subclass_bypass', 'if kind is list:', 'if isinstance(value, list):',
     'test_builtin_subclasses_retain_hooks'),
    ('ignore_atomic_memo', 'cached = memo.get(ident, _MISSING)',
     'cached = _MISSING if type(value) in _ATOMIC else memo.get(ident, _MISSING)',
     'test_prefilled_memo_including_atoms_and_none'),
    ('key_before_value', 'result[_clone(key, memo)] = _clone(item, memo)',
     'copied_key = _clone(key, memo)\n            result[copied_key] = _clone(item, memo)',
     'test_custom_key_value_copy_order'),
    ('foreign_fresh_memo', 'return deepcopy(value, memo)', 'return deepcopy(value)',
     'test_other_containers_and_foreign_alias'),
    ('discard_original_lifetime', '_keep_alive(value, memo)', 'pass  # broken lifetime',
     'test_keeps_originals_alive'),
    ('reuse_top_level_memo', 'memo = {}', "memo = globals().setdefault('_BROKEN_SHARED_MEMO', {})",
     'test_separate_top_level_memos'),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--unitflow', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Refusing to overwrite a controls receipt')
    original = (HERE / 'projection_clone.py').read_text()
    records = []
    with tempfile.TemporaryDirectory(prefix='livepath-controls-') as td:
        for name, before, after, case in MUTATIONS:
            if before not in original:
                raise RuntimeError(f'Mutation anchor missing: {name}')
            text = original.replace(before, after)
            path = Path(td) / (name + '.py'); path.write_text(text)
            command = [sys.executable, *(['-O'] if sys.flags.optimize else []),
                       str(HERE / 'test_projection_clone.py'), '--package', str(args.package),
                       '--unitflow', str(args.unitflow), '--clone-file', str(path),
                       '--case', 'GraphContracts.' + case]
            run = subprocess.run(command, capture_output=True, text=True, timeout=30)
            try:
                status = json.loads(run.stdout.strip().splitlines()[-1])
            except (ValueError, IndexError) as exc:
                raise RuntimeError(f'Mutant infrastructure error: {name}\n{run.stderr}') from exc
            if run.returncode != 1 or status['failures'] < 1 or status['errors'] or status['skips']:
                raise RuntimeError(f'Not an assertion-only rejection: {name}: {status}\n{run.stderr}')
            records.append({'mutant': name, 'sha256': hashlib.sha256(text.encode()).hexdigest(),
                            'case': case, 'status': status, 'stderr': run.stderr})
    receipt = {'optimized': bool(sys.flags.optimize), 'mutants': records,
               'assertion_rejected': len(records), 'infrastructure_errors': 0}
    args.output.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'assertion_rejected': len(records), 'infrastructure_errors': 0,
                      'optimized': bool(sys.flags.optimize)}))


if __name__ == '__main__':
    main()
