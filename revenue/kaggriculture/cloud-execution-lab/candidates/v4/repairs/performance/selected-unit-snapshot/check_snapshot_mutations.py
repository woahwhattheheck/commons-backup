# SPDX-License-Identifier: Apache-2.0
"""Require graph tests to reject six executable wrong copy implementations."""
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent


def main():
    original = (HERE / 'selected_unit_snapshot.py').read_text()
    mutants = {
        'shallow_retained_objects': '''from copy import deepcopy

def selected_unit_snapshot(obs, player, pair):
    out = dict(obs)
    out['farms'] = list(obs['farms'])
    out['farms'][int(player)], out['private'] = pair
    return out
''',
        'remap_discarded_objects_globally': '''from copy import deepcopy

def selected_unit_snapshot(obs, player, pair):
    i = int(player)
    return deepcopy(obs, {id(obs['farms'][i]): pair[0], id(obs['private']): pair[1]})
''',
        'copy_pair_instead_of_borrowing': original.replace(
            '    farms = obs[\'farms\']\n', '    pair = deepcopy(pair)\n    farms = obs[\'farms\']\n', 1),
        'discard_root_memo': original.replace(
            'memo = {id(obs): post, id(farms): copied_farms}', 'memo = {id(farms): copied_farms}', 1),
        'discard_farms_memo': original.replace(
            'memo = {id(obs): post, id(farms): copied_farms}', 'memo = {id(obs): post}', 1),
        'always_replace_seat_zero': original.replace('index %= len(farms)', 'index = 0', 1),
    }
    report = []
    for optimized in (False, True):
        for name, source in mutants.items():
            if source == original:
                raise ValueError('mutation was not applied: ' + name)
            compile(source, name, 'exec')
            with tempfile.TemporaryDirectory(prefix='quarry-mutant-') as tmp:
                root = Path(tmp)
                for filename in ('test_selected_snapshot.py', 'compose_selected_snapshot.py'):
                    shutil.copy2(HERE / filename, root / filename)
                (root / 'selected_unit_snapshot.py').write_text(source)
                cmd = [sys.executable] + (['-O'] if optimized else []) + [
                    '-m', 'unittest', '-f', 'test_selected_snapshot.SnapshotGraphTests']
                proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True,
                                      timeout=20, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
                # A loader failure or zero tests is not a semantic mutation kill.
                if proc.returncode == 0 or not re.search(r'Ran [1-9][0-9]* tests?', proc.stderr):
                    raise RuntimeError('mutation did not fail the actual graph suite: ' + name + proc.stderr[-2000:])
                if 'AssertionError' not in proc.stderr:
                    raise RuntimeError('mutation failed without a graph assertion: ' + name)
                report.append({'mutant': name, 'optimized': optimized,
                               'exit_code': proc.returncode, 'graph_assertion_failure': True})
    print(json.dumps({'success': True, 'cases': report}, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
