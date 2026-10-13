# SPDX-License-Identifier: Apache-2.0
"""Paired full-game parity on the exact checked archive, not current source HEAD.

Uses the archive's unchanged official interpreter/process evaluator and native
main.py::agent. Only the two lifecycle source outputs differ in the candidate.
No network, release write, feature override, new opponent or Kaggle submission.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tarfile
import tempfile
from repair_return_lifecycle import repair, git_blob

ARCHIVE_SHA256 = 'b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9'
MANIFEST_SHA256 = 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'
OUTPUT_BLOBS = {'titan_runtime.py': '863a36442bd0f2b475db4c2647a27daf933bba83',
                'integrated_selected.py': '53a610f9abaab64690d7a555bf283b87aa282e51'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_archive(path):
    require(not path.is_symlink() and path.is_file(), 'archive must be a regular file')
    require(hashlib.sha256(path.read_bytes()).hexdigest() == ARCHIVE_SHA256,
            'checked archive identity mismatch')
    files = {}
    with tarfile.open(path) as archive:
        for row in archive.getmembers():
            name = Path(row.name)
            require(row.isfile() and not name.is_absolute() and '..' not in name.parts,
                    'unsafe or nonregular archive member')
            require(row.name not in files, 'duplicate archive member')
            require(row.size <= 4_000_000, 'unexpected member size')
            files[row.name] = archive.extractfile(row).read()
    require(len(files) == 110, 'expected 109 runtime members plus SOURCE.json')
    require(hashlib.sha256(files['SOURCE.json']).hexdigest() == MANIFEST_SHA256,
            'checked source manifest mismatch')
    manifest = json.loads(files['SOURCE.json'])['runtime']
    require(set(files) == set(manifest) | {'SOURCE.json'}, 'runtime member set mismatch')
    for name, record in manifest.items():
        require(len(files[name]) == record['bytes'] and
                hashlib.sha256(files[name]).hexdigest() == record['sha256'],
                'runtime member mismatch: ' + name)
    return files


def write_package(root, files):
    root.mkdir()
    for name, data in files.items():
        target = root/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def run(archive, seed):
    files = read_archive(archive)
    patched = dict(files)
    patched.update(repair(files['titan_runtime.py'], files['integrated_selected.py']))
    require({name for name in files if files[name] != patched[name]} == set(OUTPUT_BLOBS),
            'unexpected changed member set')
    for name, expected in OUTPUT_BLOBS.items():
        require(git_blob(patched[name]) == expected, 'patched member mismatch: ' + name)
    report = {'schema': 'titan.return-lifecycle.checked-release-parity/v1',
              'scope': 'Exact checked b567 archive with native configuration; NOT current source HEAD, V4-wide composition or hosted Kaggle.',
              'archive_sha256': ARCHIVE_SHA256, 'manifest_sha256': MANIFEST_SHA256,
              'runtime_members_verified': 109, 'source_manifest_verified': True,
              'changed_members': sorted(OUTPUT_BLOBS), 'output_blobs': OUTPUT_BLOBS,
              'configuration_sha256': hashlib.sha256(files['TITAN-CONFIG.json']).hexdigest(),
              'python': sys.version.split()[0], 'opponent': 'official_starter',
              'seed': seed, 'games': [], 'pairs': [], 'production_promoted': False,
              'default_changed': False, 'new_archive_written': False, 'kaggle_changed': False}
    with tempfile.TemporaryDirectory(prefix='titan-lifecycle-parity-') as tmp:
        root = Path(tmp)
        baseline, candidate = root/'baseline', root/'candidate'
        write_package(baseline, files); write_package(candidate, patched)
        evaluator = baseline/'checks/reference/evaluator/evaluate.py'
        spec = importlib.util.spec_from_file_location('_lifecycle_release_eval', evaluator)
        ev = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = ev
        spec.loader.exec_module(ev)
        cache = baseline/'checks/reference/engine'
        loader = baseline/'checks/reference/evaluator/loader.py'
        engine, _ = ev.get_engine(cache, loader=loader, prepare=False)
        # The inherited evaluator already verifies every engine source before
        # calling its offline loader, including in its isolated child actors.
        for seat in (0, 1):
            pair = {}
            for name, package in [('baseline', baseline), ('candidate', candidate)]:
                agents = ['official_starter', 'official_starter']
                agents[seat] = str(package/'main.py') + '::agent'
                result = ev.play(engine, agents, cache, loader, seed, seat,
                                 action_timeout=1.0, startup_timeout=10.0,
                                 game_timeout=180.0)
                result['variant'] = name
                pair[name] = result
                report['games'].append(result)
                print(json.dumps({'variant': name, 'seat': seat, 'status': result['status'],
                      'steps': result['steps'], 'scores': result['scores'],
                      'trace_sha256': result['trace_sha256'],
                      'failure': result['failure']}, sort_keys=True), flush=True)
            good = all(x['status'] == 'complete' and x['steps'] == 719 and
                       x['failure'] is None for x in pair.values())
            report['pairs'].append({'seat': seat, 'both_complete': good,
                'same_scores': pair['baseline']['scores'] == pair['candidate']['scores'],
                'same_whole_game_trace': pair['baseline']['trace_sha256'] == pair['candidate']['trace_sha256']})
    report['passed'] = all(row['both_complete'] and row['same_scores'] and
                           row['same_whole_game_trace'] for row in report['pairs'])
    report['limits'] = ['One seed and one baseline opponent, both seats: parity smoke only, no strength estimate.',
                        'This release differs from current source HEAD; particularly selected_action_sell.py in b567 is 7d0f4e68, not HEAD68b82183 at validation.',
                        'Normal native frozen configuration only. Ordered custody is covered by separate component tests.',
                        'Offline POSIX process evaluator, not hosted Kaggle RPC.']
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=9922999)
    args = parser.parse_args()
    require(not args.output.exists() and not args.output.is_symlink(), 'output already exists')
    result = run(args.archive, args.seed)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
