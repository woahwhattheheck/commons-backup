# SPDX-License-Identifier: Apache-2.0
"""Run the real W2 checker against behavior faults and invalid references."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
MUTATIONS = {
    'invent_wheat': ('if actor < len(wheat) and wheat[actor] >= 1:', 'if True:'),
    'ignore_prefix_feed': ('animal["fed"] = True', 'animal["fed"] = False'),
    'wrong_seat': ('farm, private = farms[player]', 'farm, private = farms[1 - player]'),
    'ignore_season': ('and animal["useful"]', 'and True'),
    'ignore_authored_care': ('and site not in care_sites', 'and True'),
    'multiple_rewrites': ('                animal["cared"] = True\n    return changes',
                          '                animal["cared"] = False\n    return changes'),
    'mutate_parent': ('result = deepcopy(action)', 'result = action'),
    'rewrite_nonliteral': ('row == ["FEED"]', 'row[0] == "FEED"'),
    'wrong_bank_bound': ('bonus <= day - placed + 1', 'bonus <= 3'),
}


def invoke(source, native, optimized):
    env = dict(os.environ, W2_SOURCE=str(source), TITAN_NATIVE_ROOT=str(native),
               PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run([sys.executable, *(['-O'] if optimized else []), '-B',
        str(HERE / 'check_dead_feed_care.py')], env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
    lines = [line[11:] for line in result.stdout.splitlines() if line.startswith('W2_RECEIPT=')]
    if len(lines) != 1:
        raise RuntimeError('Checker returned no unique structured receipt: ' + result.stdout[-2000:])
    return result, json.loads(lines[0])


def main():
    native = Path(os.environ['TITAN_NATIVE_ROOT']).resolve()
    source = HERE / 'dead_feed_care.py'
    body = source.read_text()
    records = []
    scope = os.environ.get('W2_SCOPE', 'all')
    if scope not in ('all', 'semantic', 'reference'):
        raise ValueError('W2_SCOPE must be all, semantic or reference')
    mode = os.environ.get('W2_MODE', 'both')
    if mode not in ('normal', 'optimized', 'both'):
        raise ValueError('W2_MODE must be normal, optimized or both')
    modes = (False, True) if mode == 'both' else (mode == 'optimized',)
    for optimized in modes:
        baseline, receipt = invoke(source, native, optimized)
        if baseline.returncode or receipt['failures'] or receipt['errors'] or receipt['skips']:
            raise RuntimeError('Unchanged positive control did not pass')
        records.append({'name': 'unchanged', 'optimized': optimized, 'receipt': receipt,
                        'log': baseline.stdout})
        with tempfile.TemporaryDirectory(prefix='w2-faults-') as directory:
            temp = Path(directory)
            for name, (old, new) in (MUTATIONS.items() if scope != 'reference' else ()):
                print("CHECK", optimized, name, flush=True)
                if body.count(old) != 1:
                    raise ValueError(f'Fault preimage not unique: {name}')
                path = temp / (name + '.py')
                path.write_text(body.replace(old, new))
                result, observed = invoke(path, native, optimized)
                if result.returncode == 0 or observed['failures'] < 1 or observed['errors'] or observed['skips']:
                    raise RuntimeError(f'{name}: no assertion-only rejection: {observed}')
                records.append({'name': name, 'optimized': optimized, 'receipt': observed,
                                'log': result.stdout})
            # Reference defects are infrastructure rejection, not semantic kills.
            reference = temp / 'native/checks/reference'
            shutil.copytree(native / 'checks/reference', reference)
            for relative in (receipt['pins'] if scope != 'semantic' else ()):
                target = reference / relative
                original = target.read_bytes()
                for fault in ('missing', 'changed'):
                    print("REFERENCE", optimized, relative, fault, flush=True)
                    if fault == 'missing':
                        target.unlink()
                    else:
                        target.write_bytes(original + b'\n# deliberate trust-root fault\n')
                    result, observed = invoke(source, temp / 'native', optimized)
                    if result.returncode == 0 or observed['tests'] or observed['errors'] != 1:
                        raise RuntimeError('Reference fault did not reject before execution')
                    records.append({'name': relative + ':' + fault, 'optimized': optimized,
                                    'receipt': observed, 'log': result.stdout})
                    target.write_bytes(original)
    output = {'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'semantic_faults_per_mode': len(MUTATIONS) if scope != 'reference' else 0,
              'reference_faults_per_mode': 10 if scope != 'semantic' else 0,
              'records': records}
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / 'FAULT-VALIDATION.json'
    destination.write_text(json.dumps(output, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'semantic_faults_per_mode': len(MUTATIONS) if scope != 'reference' else 0,
              'reference_faults_per_mode': 10 if scope != 'semantic' else 0,
                      'records': len(records), 'output': str(destination)}))


if __name__ == '__main__':
    main()
